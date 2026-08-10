#!/usr/bin/env node
/**
 * kimi-memory installer
 *
 * Usage:
 *   npx kimi-memory install [--hook]
 *   npx kimi-memory uninstall
 *   npx kimi-memory update [--hook]
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync, spawn } = require("child_process");

const HOME = os.homedir();

// El CLI actual usa ~/.kimi-code; versiones viejas usan ~/.kimi.
// Se prefiere ~/.kimi-code si existe; si no, ~/.kimi.
function detectConfigHome() {
  const kimiCode = path.join(HOME, ".kimi-code");
  if (fs.existsSync(kimiCode)) return kimiCode;
  return path.join(HOME, ".kimi");
}

const CONFIG_HOME = detectConfigHome();
const PLUGIN_DIR = path.join(CONFIG_HOME, "plugins", "kimi-memory");
const SKILL_DIR = path.join(CONFIG_HOME, "skills", "kimi-memory");
const MCP_CONFIG = path.join(CONFIG_HOME, "mcp.json");
const KIMI_CONFIG = path.join(CONFIG_HOME, "config.toml");
const MEMORY_DB = path.join(CONFIG_HOME, "memory.db");
const PKG_DIR = __dirname;

const IS_WIN = process.platform === "win32";

function log(msg) {
  console.log(`[kimi-memory] ${msg}`);
}

function warn(msg) {
  console.warn(`[kimi-memory] ⚠️  ${msg}`);
}

function error(msg) {
  console.error(`[kimi-memory] ❌ ${msg}`);
}

function ok(msg) {
  console.log(`[kimi-memory] ✅ ${msg}`);
}

function exec(cmd, opts = {}) {
  return execSync(cmd, { encoding: "utf-8", stdio: "pipe", ...opts });
}

function findPython() {
  const candidates = IS_WIN ? ["python", "py -3", "python3"] : ["python3", "python"];
  for (const c of candidates) {
    try {
      const version = exec(`${c} --version`).trim();
      const abs = exec(IS_WIN ? `where ${c.split(" ")[0]}` : `command -v ${c.split(" ")[0]}`).trim().split(/\r?\n/)[0];
      if (abs && version.toLowerCase().includes("python 3")) {
        return { cmd: c, abs, version };
      }
    } catch {
      // continue
    }
  }
  return null;
}

function verifyFTS5(pythonCmd) {
  const script = `import sqlite3, sys; conn = sqlite3.connect(':memory:'); conn.execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('OK')`;
  try {
    const out = exec(`${pythonCmd} -c "${script}"`);
    return out.includes("OK");
  } catch {
    return false;
  }
}

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function copyFile(src, dst) {
  ensureDir(path.dirname(dst));
  fs.copyFileSync(src, dst);
}

function copyPluginFiles() {
  ensureDir(PLUGIN_DIR);
  copyFile(path.join(PKG_DIR, "memory_mcp.py"), path.join(PLUGIN_DIR, "memory_mcp.py"));
  copyFile(path.join(PKG_DIR, "memory_web.py"), path.join(PLUGIN_DIR, "memory_web.py"));
  copyFile(path.join(PKG_DIR, "test_mcp.py"), path.join(PLUGIN_DIR, "test_mcp.py"));
  copyFile(path.join(PKG_DIR, "kimi.plugin.json"), path.join(PLUGIN_DIR, "kimi.plugin.json"));

  const hooksSrc = path.join(PKG_DIR, "hooks");
  const hooksDst = path.join(PLUGIN_DIR, "hooks");
  if (fs.existsSync(hooksSrc)) {
    ensureDir(hooksDst);
    for (const f of fs.readdirSync(hooksSrc)) {
      if (f.endsWith(".py")) {
        copyFile(path.join(hooksSrc, f), path.join(hooksDst, f));
      }
    }
  }
}

function copySkill() {
  ensureDir(SKILL_DIR);
  copyFile(
    path.join(PKG_DIR, "skills", "kimi-memory", "SKILL.md"),
    path.join(SKILL_DIR, "SKILL.md")
  );
}

function updateMcpConfig(pythonAbs) {
  ensureDir(path.dirname(MCP_CONFIG));
  let cfg = {};
  if (fs.existsSync(MCP_CONFIG)) {
    try {
      cfg = JSON.parse(fs.readFileSync(MCP_CONFIG, "utf-8"));
    } catch (e) {
      warn(`No se pudo parsear ${MCP_CONFIG}, se sobreescribirá.`);
    }
  }
  cfg.mcpServers = cfg.mcpServers || {};
  cfg.mcpServers["kimi-memory"] = {
    command: pythonAbs,
    args: ["-u", path.join(PLUGIN_DIR, "memory_mcp.py")],
    env: {
      KIMI_MEMORY_DB: MEMORY_DB,
    },
  };
  fs.writeFileSync(MCP_CONFIG, JSON.stringify(cfg, null, 2), "utf-8");
  ok(`Configuración MCP guardada en ${MCP_CONFIG}`);
}

function removeMcpConfig() {
  if (!fs.existsSync(MCP_CONFIG)) return;
  let cfg = {};
  try {
    cfg = JSON.parse(fs.readFileSync(MCP_CONFIG, "utf-8"));
  } catch {
    return;
  }
  if (cfg.mcpServers && cfg.mcpServers["kimi-memory"]) {
    delete cfg.mcpServers["kimi-memory"];
    fs.writeFileSync(MCP_CONFIG, JSON.stringify(cfg, null, 2), "utf-8");
    ok("kimi-memory removido de mcp.json");
  }
}

const HOOK_EVENTS = [
  { event: "SessionEnd" },
  // Incluye nombres de tools del CLI actual (Write|Edit) y del viejo (WriteFile|StrReplaceFile).
  { event: "PostToolUse", matcher: "Write|Edit|WriteFile|StrReplaceFile" },
  { event: "UserPromptSubmit" },
  { event: "PreCompact" },
  { event: "StopFailure" },
];

function hookCommand(pythonAbs) {
  const hookPath = path.join(PLUGIN_DIR, "hooks", "memory_hook.py");
  return IS_WIN
    ? `"${pythonAbs}" "${hookPath}"`
    : `${pythonAbs} ${hookPath}`;
}

function legacyHookCommands() {
  // Subcadenas que identifican cualquier variante vieja del hook
  // (distintos intérpretes, comillas o rutas) para removerla al actualizar.
  return ["memory_hook.py", "session_end.py"];
}

function hookBlock(event, matcher, pythonAbs) {
  const cmd = hookCommand(pythonAbs);
  let block = `[[hooks]]\nevent = "${event}"\n`;
  if (matcher) {
    block += `matcher = "${matcher}"\n`;
  }
  // TOML literal string (comillas simples): backslashes y comillas dobles
  // del comando quedan literales (importante para rutas de Windows).
  if (cmd.includes("'")) {
    block += `command = "${cmd.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"\n`;
  } else {
    block += `command = '${cmd}'\n`;
  }
  return block;
}

function removeHookBlocks(content, commands) {
  const cmdSet = new Set(Array.isArray(commands) ? commands : [commands]);
  const lines = content.split(/\r?\n/);
  const out = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i].trim() === "[[hooks]]") {
      const block = [];
      let j = i;
      while (j < lines.length) {
        block.push(lines[j]);
        j++;
        if (j < lines.length && lines[j].trim() === "[[hooks]]") {
          break;
        }
      }
      const blockText = block.join("\n");
      if (![...cmdSet].some((cmd) => blockText.includes(cmd))) {
        out.push(...block);
      }
      i = j;
      continue;
    }
    out.push(lines[i]);
    i++;
  }
  return out.join("\n");
}

function installHook(pythonAbs) {
  if (!fs.existsSync(KIMI_CONFIG)) {
    warn(`No existe ${KIMI_CONFIG}. Creando uno mínimo.`);
    fs.writeFileSync(KIMI_CONFIG, "", "utf-8");
  }
  let content = fs.readFileSync(KIMI_CONFIG, "utf-8");
  const cmd = hookCommand(pythonAbs);

  // Remover configuraciones viejas (session_end.py, `python <path>`) y evitar duplicados.
  content = removeHookBlocks(content, [...legacyHookCommands(), cmd]);

  if (content.includes(cmd)) {
    log("Los hooks de kimi-memory ya están configurados.");
    return;
  }

  const blocks = HOOK_EVENTS.map((h) => hookBlock(h.event, h.matcher, pythonAbs)).join("\n");

  // Kimi por defecto pone `hooks = []`, que es incompatible con [[hooks]].
  // Reemplazamos ese array vacío por los bloques de hooks.
  if (/^\s*hooks\s*=\s*\[\]\s*$/m.test(content)) {
    content = content.replace(/^\s*hooks\s*=\s*\[\]\s*$/m, blocks.trim());
  } else {
    // Los [[hooks]] son claves top-level: deben ir ANTES de la primera
    // tabla [sección]; si se agregan al final quedarían dentro de la última
    // tabla y TOML fallaría o los ignoraría.
    const firstTable = content.search(/^\s*\[/m);
    if (firstTable === -1) {
      content = content.trimEnd() + "\n\n" + blocks + "\n";
    } else {
      content =
        content.slice(0, firstTable).trimEnd() +
        "\n\n" + blocks + "\n\n" +
        content.slice(firstTable);
    }
  }

  fs.writeFileSync(KIMI_CONFIG, content, "utf-8");
  ok(`Hooks de kimi-memory agregados a ${KIMI_CONFIG}`);
}

function removeHook() {
  if (!fs.existsSync(KIMI_CONFIG)) return;
  let content = fs.readFileSync(KIMI_CONFIG, "utf-8");
  content = removeHookBlocks(content, legacyHookCommands());
  fs.writeFileSync(KIMI_CONFIG, content, "utf-8");
  ok("Hooks de kimi-memory removidos de config.toml");
}

function install(includeHook) {
  log("== Instalando kimi-memory ==");
  log(`Config home: ${CONFIG_HOME}`);
  const py = findPython();
  if (!py) {
    error("No se encontró Python 3.10+. Instalalo e intentá de nuevo.");
    process.exit(1);
  }
  log(`Python: ${py.abs} (${py.version})`);

  log("Verificando SQLite FTS5...");
  if (!verifyFTS5(py.cmd)) {
    error("SQLite FTS5 no está disponible.");
    process.exit(1);
  }
  ok("SQLite FTS5 OK");

  log("Copiando plugin...");
  copyPluginFiles();
  ok(`Plugin copiado a ${PLUGIN_DIR}`);

  log("Copiando skill...");
  copySkill();
  ok(`Skill copiado a ${SKILL_DIR}`);

  log("Actualizando configuración MCP...");
  updateMcpConfig(py.abs);

  if (includeHook) {
    log("Configurando hooks de Kimi Memory...");
    installHook(py.abs);
  }

  log("");
  ok("Instalación completa.");
  log("Reiniciá Kimi Code CLI para que reconozca el servidor MCP.");
  if (includeHook) {
    log("Los hooks guardarán automáticamente contexto de sesión, cambios de archivos, prompts, compactación y errores.");
  }
}

function uninstall() {
  log("== Desinstalando kimi-memory ==");
  if (fs.existsSync(PLUGIN_DIR)) {
    fs.rmSync(PLUGIN_DIR, { recursive: true, force: true });
    ok(`Plugin removido de ${PLUGIN_DIR}`);
  }
  if (fs.existsSync(SKILL_DIR)) {
    fs.rmSync(SKILL_DIR, { recursive: true, force: true });
    ok(`Skill removido de ${SKILL_DIR}`);
  }
  removeMcpConfig();
  removeHook();
  ok("Desinstalación completa.");
}

function update(includeHook) {
  log("== Actualizando kimi-memory ==");
  uninstall();
  install(includeHook);
}

function showHelp() {
  console.log(`
kimi-memory installer

Uso:
  npx kimi-memory install [--hook]   Instala el plugin, skill y config MCP.
  npx kimi-memory uninstall          Remueve todo.
  npx kimi-memory update [--hook]    Actualiza a la última versión.
  npx kimi-memory --help             Muestra esta ayuda.

Opciones:
  --hook    Configura los hooks de Kimi Memory (SessionEnd, PostToolUse, UserPromptSubmit, PreCompact, StopFailure).

Requiere:
  - Node.js 18+
  - Python 3.10+ con SQLite FTS5
  - Kimi Code CLI
`);
}

function main() {
  const args = process.argv.slice(2);
  if (args.length === 0 || args.includes("--help") || args.includes("-h")) {
    showHelp();
    process.exit(0);
  }

  const command = args[0];
  const includeHook = args.includes("--hook");

  switch (command) {
    case "install":
      install(includeHook);
      break;
    case "uninstall":
      uninstall();
      break;
    case "update":
      update(includeHook);
      break;
    default:
      error(`Comando desconocido: ${command}`);
      showHelp();
      process.exit(1);
  }
}

main();
