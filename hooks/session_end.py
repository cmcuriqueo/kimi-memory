#!/usr/bin/env python3
"""Hook SessionEnd para Kimi Memory.

Recibe JSON por stdin con los datos del hook de Kimi CLI, busca el contexto de
la sesión recién finalizada y guarda un resumen en la memoria persistente.

Para registrarlo en ~/.kimi/config.toml:

    [[hooks]]
    event = "SessionEnd"
    command = "python ~/.kimi-code/plugins/kimi-memory/hooks/session_end.py"

El resumen no intenta reemplazar al usuario: simplemente captura los temas
tocados, el directorio de trabajo y las herramientas más usadas, para que en
la próxima sesión `memory_search` pueda recuperar contexto.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SESSIONS_ROOT = Path.home() / ".kimi" / "sessions"
PLUGIN_DIR = Path.home() / ".kimi-code" / "plugins" / "kimi-memory"

# Asegurar que podamos importar memory_mcp
sys.path.insert(0, str(PLUGIN_DIR))
try:
    import memory_mcp
except Exception as e:
    print(f"[kimi-memory-hook] Error importando memory_mcp: {e}", file=sys.stderr)
    sys.exit(0)  # fail-open


def find_session_dir(session_id: str) -> Path | None:
    if not SESSIONS_ROOT.exists():
        return None
    for work_dir_hash_dir in SESSIONS_ROOT.iterdir():
        if not work_dir_hash_dir.is_dir():
            continue
        candidate = work_dir_hash_dir / session_id
        if candidate.is_dir():
            return candidate
    return None


def extract_user_prompts(context_file: Path, max_prompts: int = 5) -> list[str]:
    prompts: list[str] = []
    try:
        with context_file.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("role") == "user":
                    content = msg.get("content")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, dict):
                                parts.append(str(part.get("text", "")))
                            elif isinstance(part, str):
                                parts.append(part)
                        text = " ".join(p for p in parts if p)
                    text = text.strip()
                    if text:
                        prompts.append(text)
                        if len(prompts) >= max_prompts:
                            break
    except OSError:
        pass
    return prompts


def extract_tool_names(context_file: Path, max_tools: int = 10) -> list[str]:
    tools: list[str] = []
    seen: set[str] = set()
    try:
        with context_file.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            name = item.get("name")
                            if name and name not in seen:
                                seen.add(name)
                                tools.append(name)
                                if len(tools) >= max_tools:
                                    break
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            func = tc.get("function", {})
                            name = func.get("name") if isinstance(func, dict) else None
                            if name and name not in seen:
                                seen.add(name)
                                tools.append(name)
                                if len(tools) >= max_tools:
                                    break
                if len(tools) >= max_tools:
                    break
    except OSError:
        pass
    return tools


def derive_project(cwd: str) -> str | None:
    path = Path(cwd)
    # Usar el nombre del directorio actual como proyecto por defecto.
    name = path.name.strip()
    return name if name else None


def summarize_session(session_id: str, cwd: str, reason: str, prompts: list[str], tools: list[str]) -> str:
    lines: list[str] = []
    lines.append(f"Sesión finalizada en {cwd} (motivo: {reason}).")
    if prompts:
        lines.append("Temas tratados:")
        for p in prompts:
            snippet = p[:120] + "…" if len(p) > 120 else p
            lines.append(f"- {snippet}")
    if tools:
        lines.append(f"Herramientas usadas: {', '.join(tools)}.")
    return "\n".join(lines)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[kimi-memory-hook] JSON inválido: {e}", file=sys.stderr)
        sys.exit(0)

    event = payload.get("hook_event_name", "SessionEnd")
    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "")
    reason = payload.get("reason", "exit")

    if not session_id:
        print("[kimi-memory-hook] Sin session_id", file=sys.stderr)
        sys.exit(0)

    session_dir = find_session_dir(session_id)
    prompts: list[str] = []
    tools: list[str] = []
    if session_dir:
        context_file = session_dir / "context.jsonl"
        if context_file.exists():
            prompts = extract_user_prompts(context_file)
            tools = extract_tool_names(context_file)

    if not prompts and not tools:
        # No hay contenido suficiente; guardar un recuerdo mínimo.
        content = f"Sesión en {cwd} finalizada ({reason}). No se detectaron prompts ni herramientas."
    else:
        content = summarize_session(session_id, cwd, reason, prompts, tools)

    project = derive_project(cwd)
    try:
        result = memory_mcp.add_memory(
            content=content,
            category="session_summary",
            project=project,
        )
        print(f"[kimi-memory-hook] Guardado: {result}", file=sys.stderr)
    except Exception as e:
        print(f"[kimi-memory-hook] Error guardando memoria: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
