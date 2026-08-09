#!/usr/bin/env bash
# Instalador de Kimi Memory (bash / Git Bash / WSL / macOS / Linux)
# Asume que se ejecuta desde el directorio del repositorio clonado.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="${HOME}/.kimi-code/plugins/kimi-memory"
SKILL_DIR="${HOME}/.kimi/skills/kimi-memory"
MCP_CONFIG_DIR="${HOME}/.kimi"
MCP_CONFIG="${MCP_CONFIG_DIR}/mcp.json"

echo "== Kimi Memory =="
echo "Repo:    ${REPO_DIR}"
echo "Plugin:  ${PLUGIN_DIR}"
echo "Skill:   ${SKILL_DIR}"

# Verificar Python
if command -v python &>/dev/null; then
    PYTHON=python
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "Error: se requiere Python 3.10+"
    exit 1
fi

# Preferir ruta absoluta para evitar problemas de PATH
PYTHON_ABS="$(command -v "${PYTHON}")"

echo "Python: ${PYTHON_ABS}"

# Verificar FTS5
"${PYTHON}" - <<'PY'
import sqlite3, sys
conn = sqlite3.connect(':memory:')
try:
    conn.execute('CREATE VIRTUAL TABLE t USING fts5(x)')
    print('SQLite FTS5: OK')
except Exception as e:
    print('SQLite FTS5 NO disponible:', e)
    sys.exit(1)
PY

# Copiar plugin
echo "Copiando plugin a ${PLUGIN_DIR}..."
mkdir -p "${PLUGIN_DIR}"
cp -f "${REPO_DIR}/memory_mcp.py" "${PLUGIN_DIR}/"
cp -f "${REPO_DIR}/memory_web.py" "${PLUGIN_DIR}/"
cp -f "${REPO_DIR}/test_mcp.py" "${PLUGIN_DIR}/"
cp -f "${REPO_DIR}/kimi.plugin.json" "${PLUGIN_DIR}/"

# Copiar hooks
if [ -d "${REPO_DIR}/hooks" ]; then
    echo "Copiando hooks a ${PLUGIN_DIR}/hooks..."
    mkdir -p "${PLUGIN_DIR}/hooks"
    cp -f "${REPO_DIR}/hooks/"* "${PLUGIN_DIR}/hooks/"
fi

# Copiar skill
echo "Copiando skill a ${SKILL_DIR}..."
mkdir -p "${SKILL_DIR}"
cp -f "${REPO_DIR}/skills/kimi-memory/SKILL.md" "${SKILL_DIR}/"

# Crear ~/.kimi/mcp.json si no existe
mkdir -p "${MCP_CONFIG_DIR}"
if [ ! -f "${MCP_CONFIG}" ]; then
    echo "{}" > "${MCP_CONFIG}"
fi

# Actualizar ~/.kimi/mcp.json con jq si está disponible; si no, usar Python
MEMORY_DB="${HOME}/.kimi-code/memory.db"

if command -v jq &>/dev/null; then
    jq --arg cmd "${PYTHON_ABS}" \
       --arg arg "${PLUGIN_DIR}/memory_mcp.py" \
       --arg db "${MEMORY_DB}" \
       '.mcpServers["kimi-memory"] = {command: $cmd, args: ["-u", $arg], env: {KIMI_MEMORY_DB: $db}}' \
       "${MCP_CONFIG}" > "${MCP_CONFIG}.tmp" && mv "${MCP_CONFIG}.tmp" "${MCP_CONFIG}"
else
    "${PYTHON}" - <<PY
import json, os
path = os.path.expanduser("${MCP_CONFIG}")
with open(path, "r") as f:
    cfg = json.load(f)
cfg.setdefault("mcpServers", {})
cfg["mcpServers"]["kimi-memory"] = {
    "command": "${PYTHON_ABS}",
    "args": ["-u", "${PLUGIN_DIR}/memory_mcp.py"],
    "env": {"KIMI_MEMORY_DB": "${MEMORY_DB}"}
}
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
print("MCP config actualizado:", path)
PY
fi

echo ""
echo "Instalación lista. Configuración MCP guardada en: ${MCP_CONFIG}"
echo "Para activar el plugin en Kimi Code CLI:"
echo "  /plugins install ${PLUGIN_DIR}"
echo "  /plugins reload"
echo ""
echo "Para probar el servidor MCP manualmente:"
echo "  ${PYTHON} ${PLUGIN_DIR}/test_mcp.py"
echo ""
echo "Nota: reinicia Kimi Code CLI para que reconozca el servidor MCP."
