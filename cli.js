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
const PLUGIN_DIR = path.join(HOME, ".kimi-code", "plugins", "kimi-memory");
const SKILL_DIR = path.join(HOME, ".kimi", "skills", "kimi-memory");
const MCP_CONFIG = path.join(HOME, ".kimi", "mcp.json");
const KIMI_CONFIG = path.join(HOME, ".kimi", "config.toml");
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
      KIMI_MEMORY_DB: path.join(HOME, ".kimi-code", "memory.db"),
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

function hookCommand() {
  const hookPath = path.join(PLUGIN_DIR, "hooks", "session_end.py");
  return IS_WIN
    ? `python %USERPROFILE%\\.kimi-code\\plugins\\kimi-memory\\hooks\\session_end.py`
    : `python ${hookPath}`;
}

function installHook() {
  if (!fs.existsSync(KIMI_CONFIG)) {
    warn(`No existe ${KIMI_CONFIG}. Creando uno mínimo.`);
    fs.writeFileSync(KIMI_CONFIG, "", "utf-8");
  }
  let content = fs.readFileSync(KIMI_CONFIG, "utf-8");
  const cmd = hookCommand();
  const hookBlock = IS_WIN
    ? `[[hooks]]\nevent = "SessionEnd"\ncommand = '${cmd}'\n`
    : `[[hooks]]\nevent = "SessionEnd"\ncommand = "${cmd}"\n`;

  if (content.includes(cmd)) {
    log("El hook SessionEnd ya está configurado.");
    return;
  }

  // Kimi por defecto pone `hooks = []`, que es incompatible con [[hooks]].
  // Reemplazamos ese array vacío por el array of tables.
  if (/^\s*hooks\s*=\s*\[\]\s*$/m.test(content)) {
    content = content.replace(/^\s*hooks\s*=\s*\[\]\s*$/m, hookBlock.trim());
  } else {
    content = content.trimEnd() + "\n\n" + hookBlock;
  }

  fs.writeFileSync(KIMI_CONFIG, content, "utf-8");
  ok("Hook SessionEnd agregado a config.toml");
}

function removeHook() {
  if (!fs.existsSync(KIMI_CONFIG)) return;
  let content = fs.readFileSync(KIMI_CONFIG, "utf-8");
  const cmd = hookCommand();
  const lines = content.split(/\r?\n/);
  const out = [];
  let skip = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() === "[[hooks]]" && lines[i + 1] && lines[i + 1].includes("SessionEnd") && lines[i + 2] && lines[i + 2].includes(cmd)) {
      skip = 3;
      continue;
    }
    if (skip > 0) {
      skip--;
      continue;
    }
    out.push(lines[i]);
  }
  fs.writeFileSync(KIMI_CONFIG, out.join("\n"), "utf-8");
  ok("Hook SessionEnd removido de config.toml");
}

function install(includeHook) {
  log("== Instalando kimi-memory ==");
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
    log("Configurando hook SessionEnd...");
    installHook();
  }

  log("");
  ok("Instalación completa.");
  log("Reiniciá Kimi Code CLI para que reconozca el servidor MCP.");
  if (includeHook) {
    log("El hook SessionEnd guardará automáticamente resúmenes al cerrar sesiones.");
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
  --hook    Configura el hook SessionEnd para guardar resúmenes automáticos.

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
