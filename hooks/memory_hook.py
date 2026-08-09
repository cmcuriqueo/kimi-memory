#!/usr/bin/env python3
"""Hooks de Kimi Memory para múltiples eventos del ciclo de vida.

Recibe JSON por stdin con los datos del hook de Kimi CLI y guarda observaciones
relevantes en la memoria persistente.

Para registrarlo en ~/.kimi/config.toml:

    [[hooks]]
    event = "SessionEnd"
    command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

    [[hooks]]
    event = "PostToolUse"
    matcher = "WriteFile|StrReplaceFile"
    command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

    [[hooks]]
    event = "UserPromptSubmit"
    command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

    [[hooks]]
    event = "PreCompact"
    command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

    [[hooks]]
    event = "StopFailure"
    command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

El script es intencionalmente fail-open: cualquier error se loguea a stderr y
sale con código 0, para no interrumpir el flujo de Kimi.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path.home() / ".kimi-code" / "plugins" / "kimi-memory"
SESSIONS_ROOT = Path.home() / ".kimi" / "sessions"

sys.path.insert(0, str(PLUGIN_DIR))
try:
    import memory_mcp
except Exception as e:
    print(f"[kimi-memory-hook] Error importando memory_mcp: {e}", file=sys.stderr)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Utilidades compartidas
# ---------------------------------------------------------------------------
def derive_project(cwd: str) -> str | None:
    path = Path(cwd)
    name = path.name.strip()
    return name if name else None


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


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
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


def handle_session_end(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "")
    reason = payload.get("reason", "exit")

    if not session_id:
        print("[kimi-memory-hook] SessionEnd sin session_id", file=sys.stderr)
        return

    session_dir = find_session_dir(session_id)
    prompts: list[str] = []
    tools: list[str] = []
    if session_dir:
        context_file = session_dir / "context.jsonl"
        if context_file.exists():
            prompts = extract_user_prompts(context_file)
            tools = extract_tool_names(context_file)

    if not prompts and not tools:
        content = f"Sesión en {cwd} finalizada ({reason}). No se detectaron prompts ni herramientas."
    else:
        content = summarize_session(session_id, cwd, reason, prompts, tools)

    project = derive_project(cwd)
    tags = ["session-summary"]
    # Extraer keywords de los prompts para taggear el resumen.
    for p in prompts:
        for tag in _extract_tags_from_prompt(p):
            if tag not in tags:
                tags.append(tag)

    result = memory_mcp.add_memory(
        content=content,
        category="session_summary",
        project=project,
        tags=tags,
    )
    print(f"[kimi-memory-hook] SessionEnd guardado: {result}", file=sys.stderr)


def handle_post_tool_use(payload: dict[str, Any]) -> None:
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    cwd = payload.get("cwd", "")

    file_path = ""
    if tool_name == "WriteFile":
        file_path = tool_input.get("path") or tool_input.get("file_path", "")
    elif tool_name == "StrReplaceFile":
        file_path = tool_input.get("path") or tool_input.get("file_path", "")

    if not file_path:
        return

    project = derive_project(cwd)
    path_obj = Path(file_path)
    tags = ["file-change"]
    if path_obj.suffix:
        tags.append(path_obj.suffix.lstrip(".").lower())
    if path_obj.name:
        tags.append(path_obj.name.lower())

    content = f"Archivo modificado durante la sesión: {file_path}"
    result = memory_mcp.add_memory(
        content=content,
        category="file_change",
        project=project,
        tags=tags,
    )
    print(f"[kimi-memory-hook] PostToolUse guardado: {result}", file=sys.stderr)


# Prompts que no aportan contexto valioso
_BORING_PROMPT_RE = re.compile(r"^(hola|hi|hey|gracias|ok|okay|listo|perfecto|dale)\s*[.!?]*$", re.IGNORECASE)

_PROMPT_KEYWORDS = {
    "bug", "bugs", "error", "errores", "falla", "fallo", "falló", "fail",
    "decid", "decisión", "decision", "arquitectura", "architecture",
    "diseño", "design", "refactor", "refactorizar",
    "solución", "solucion", "solution", "fix", "problema", "problem",
    "issue", "depurar", "debug", "pregunta", "preguntas",
}


def _is_interesting_prompt(prompt: str) -> bool:
    if len(prompt) < 20:
        return False
    if _BORING_PROMPT_RE.match(prompt):
        return False
    lower = prompt.lower()
    return any(k in lower for k in _PROMPT_KEYWORDS)


def _extract_tags_from_prompt(prompt: str) -> list[str]:
    tags = ["prompt"]
    lower = prompt.lower()
    keyword_tags = {
        "bug": "bug",
        "error": "error",
        "falla": "error",
        "fallo": "error",
        "autenticación": "auth",
        "autenticacion": "auth",
        "jwt": "jwt",
        "api": "api",
        "refactor": "refactor",
        "arquitectura": "architecture",
        "diseño": "design",
        "decisión": "decision",
        "decision": "decision",
    }
    for keyword, tag in keyword_tags.items():
        if keyword in lower and tag not in tags:
            tags.append(tag)
    return tags


def handle_user_prompt_submit(payload: dict[str, Any]) -> None:
    prompt = payload.get("prompt", "")
    if not prompt or not _is_interesting_prompt(prompt):
        return

    cwd = payload.get("cwd", "")
    project = derive_project(cwd)
    snippet = prompt[:500] + ("…" if len(prompt) > 500 else "")
    content = f"Prompt del usuario: {snippet}"
    result = memory_mcp.add_memory(
        content=content,
        category="prompt",
        project=project,
        tags=_extract_tags_from_prompt(prompt),
    )
    print(f"[kimi-memory-hook] UserPromptSubmit guardado: {result}", file=sys.stderr)


def handle_pre_compact(payload: dict[str, Any]) -> None:
    trigger = payload.get("trigger", "unknown")
    token_count = payload.get("token_count", 0)
    cwd = payload.get("cwd", "")
    session_id = payload.get("session_id", "")

    project = derive_project(cwd)
    content = (
        f"Compactación de contexto en sesión {session_id} "
        f"(trigger: {trigger}, tokens: {token_count}). "
        f"Se va a resumir o descartar contexto antiguo."
    )
    result = memory_mcp.add_memory(
        content=content,
        category="compaction_context",
        project=project,
        tags=["compaction"],
    )
    print(f"[kimi-memory-hook] PreCompact guardado: {result}", file=sys.stderr)


def handle_stop_failure(payload: dict[str, Any]) -> None:
    error_type = payload.get("error_type", "unknown")
    error_message = payload.get("error_message", "")
    cwd = payload.get("cwd", "")

    if not error_message:
        return

    project = derive_project(cwd)
    snippet = error_message[:1000] + ("…" if len(error_message) > 1000 else "")
    content = f"Error en sesión ({error_type}): {snippet}"
    result = memory_mcp.add_memory(
        content=content,
        category="bugfix",
        project=project,
        tags=["bugfix", "error", error_type.lower()],
    )
    print(f"[kimi-memory-hook] StopFailure guardado: {result}", file=sys.stderr)


HANDLERS: dict[str, Any] = {
    "SessionEnd": handle_session_end,
    "PostToolUse": handle_post_tool_use,
    "UserPromptSubmit": handle_user_prompt_submit,
    "PreCompact": handle_pre_compact,
    "StopFailure": handle_stop_failure,
}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[kimi-memory-hook] JSON inválido: {e}", file=sys.stderr)
        sys.exit(0)

    event = payload.get("hook_event_name", "")
    handler = HANDLERS.get(event)
    if not handler:
        print(f"[kimi-memory-hook] Evento no manejado: {event}", file=sys.stderr)
        sys.exit(0)

    try:
        handler(payload)
    except Exception as e:
        print(f"[kimi-memory-hook] Error en handler {event}: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
