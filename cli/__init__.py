"""
Paquete CLI para AETHER Agent — Interfaz interactiva y comandos slash.
"""

from cli.ui import (
    console,
    render_banner,
    render_thought,
    render_response,
    handle_thought,
    handle_tool_call,
    handle_tool_result,
    confirm_prompt,
    COMMANDS_META,
    COMPLETION_WORDS,
)
from cli.commands import handle_slash_command

__all__ = [
    "console",
    "render_banner",
    "render_thought",
    "render_response",
    "handle_thought",
    "handle_tool_call",
    "handle_tool_result",
    "confirm_prompt",
    "COMMANDS_META",
    "COMPLETION_WORDS",
    "handle_slash_command",
]
