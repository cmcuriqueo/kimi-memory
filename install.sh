#!/usr/bin/env bash
# Instalador de Kimi Memory (bash / Git Bash / WSL / macOS / Linux)
# Asume que se ejecuta desde el directorio del repositorio clonado.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# El CLI actual usa ~/.kimi-code; versiones viejas usan ~/.kimi.
if [ -d "${HOME}/.kimi-code" ]; then
    CONFIG_HOME="${HOME}/.kimi-code"
else
    CONFIG_HOME="${HOME}/.kimi"
fi
PLUGIN_DIR="${CONFIG_HOME}/plugins/kimi-memory"
SKILL_DIR="${CONFIG_HOME}/skills/kimi-memory"
MCP_CONFIG="${CONFIG_HOME}/mcp.json"

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
    cp -f "${REPO_DIR}/hooks/"*.py "${PLUGIN_DIR}/hooks/"
fi

# Copiar skill
echo "Copiando skill a ${SKILL_DIR}..."
mkdir -p "${SKILL_DIR}"
cp -f "${REPO_DIR}/skills/kimi-memory/SKILL.md" "${SKILL_DIR}/"

# Crear mcp.json si no existe
mkdir -p "${CONFIG_HOME}"
if [ ! -f "${MCP_CONFIG}" ]; then
    echo "{}" > "${MCP_CONFIG}"
fi

# Normalizar rutas a Windows si estamos en Git Bash / MSYS2
if command -v cygpath &>/dev/null; then
    PYTHON_ABS="$(cygpath -w "${PYTHON_ABS}")"
    PLUGIN_DIR="$(cygpath -w "${PLUGIN_DIR}")"
    SEP="\\"
    MEMORY_DB="$(cygpath -w "${CONFIG_HOME}/memory.db")"
else
    SEP="/"
    MEMORY_DB="${CONFIG_HOME}/memory.db"
fi
MCP_SCRIPT="${PLUGIN_DIR}${SEP}memory_mcp.py"

# Detectar KIMI_MEMORY_GIT_REPO si está definida
GIT_REPO_ARG=""
if [ -n "${KIMI_MEMORY_GIT_REPO:-}" ]; then
    if command -v cygpath &>/dev/null; then
        GIT_REPO_ARG="$(cygpath -w "${KIMI_MEMORY_GIT_REPO}")"
    else
        GIT_REPO_ARG="${KIMI_MEMORY_GIT_REPO}"
    fi
fi

# Actualizar mcp.json con jq si está disponible; si no, usar Python
if command -v jq &>/dev/null; then
    if [ -n "${GIT_REPO_ARG}" ]; then
        jq --arg cmd "${PYTHON_ABS}" \
           --arg arg "${MCP_SCRIPT}" \
           --arg db "${MEMORY_DB}" \
           --arg repo "${GIT_REPO_ARG}" \
           '.mcpServers["kimi-memory"] = {command: $cmd, args: ["-u", $arg], env: {KIMI_MEMORY_DB: $db, KIMI_MEMORY_GIT_REPO: $repo}}' \
           "${MCP_CONFIG}" > "${MCP_CONFIG}.tmp" && mv "${MCP_CONFIG}.tmp" "${MCP_CONFIG}"
    else
        jq --arg cmd "${PYTHON_ABS}" \
           --arg arg "${MCP_SCRIPT}" \
           --arg db "${MEMORY_DB}" \
           '.mcpServers["kimi-memory"] = {command: $cmd, args: ["-u", $arg], env: {KIMI_MEMORY_DB: $db}}' \
           "${MCP_CONFIG}" > "${MCP_CONFIG}.tmp" && mv "${MCP_CONFIG}.tmp" "${MCP_CONFIG}"
    fi
else
    "${PYTHON}" - <<PY
import json
from pathlib import Path
path = Path(r"${MCP_CONFIG}")
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists():
    path.write_text("{}", encoding="utf-8")
cfg = json.loads(path.read_text(encoding="utf-8"))
cfg.setdefault("mcpServers", {})
env = {"KIMI_MEMORY_DB": r"${MEMORY_DB}"}
git_repo = r"${GIT_REPO_ARG}"
if git_repo:
    env["KIMI_MEMORY_GIT_REPO"] = git_repo
cfg["mcpServers"]["kimi-memory"] = {
    "command": r"${PYTHON_ABS}",
    "args": ["-u", r"${MCP_SCRIPT}"],
    "env": env
}
path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
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
