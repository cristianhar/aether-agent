"""
Punto de entrada de la consola interactiva CLI para AETHER Agent.
Interfaz modular de alta fidelidad construida con 'rich' y 'prompt_toolkit'.
"""

import argparse
import sys
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.shortcuts import CompleteStyle

from agent.orchestrator import AgentOrchestrator
from agent.context import AetherCLICompleter, resolve_at_file_mentions
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
    "main",
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


def main():
    parser = argparse.ArgumentParser(description="AETHER Agent CLI")
    parser.add_argument("-p", "--prompt", type=str, default=None, help="Ejecutar una tarea en modo no interactivo y salir")
    parser.add_argument("--model", type=str, default="qwen2.5-coder:7b", help="Modelo de Ollama a utilizar")
    cli_args, _ = parser.parse_known_args()

    model = cli_args.model
    orchestrator = AgentOrchestrator(
        model=model,
        on_thought=handle_thought,
        on_tool_call=handle_tool_call,
        on_tool_result=handle_tool_result,
        confirm_callback=confirm_prompt,
    )

    ollama_ok = orchestrator.check_ollama_alive()
    render_banner(model, ollama_ok)

    # Modo Headless / One-Shot (ejecución directa por CLI o scripts)
    if cli_args.prompt:
        if not ollama_ok:
            console.print("[bold red]❌ Error: Ollama no está en ejecución. Inícialo con 'ollama serve'.[/bold red]")
            sys.exit(1)
        console.print(f"\n[bold cyan]AETHER ❯[/bold cyan] {cli_args.prompt}\n")
        with console.status("[bold cyan]AETHER pensando y ejecutando herramientas...[/bold cyan]", spinner="dots"):
            answer = orchestrator.run_turn(cli_args.prompt)
        render_response(answer)
        return

    # Inicialización de historial persistente y auto-completado interactivo
    cli_completer = AetherCLICompleter(Path.cwd())
    history_file = Path.cwd() / ".aether" / "cli_history.txt"
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        cli_history = FileHistory(str(history_file))
    except Exception:
        cli_history = InMemoryHistory()

    try:
        session = PromptSession(
            history=cli_history,
            completer=cli_completer,
            complete_while_typing=True,
            reserve_space_for_menu=6,
            complete_style=CompleteStyle.COLUMN,
        )
    except Exception:
        session = None

    while True:
        console.print()
        try:
            if session:
                user_input = session.prompt(HTML("<b><ansicyan>AETHER ❯ </ansicyan></b>")).strip()
            else:
                user_input = input("AETHER ❯ ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Saliendo de AETHER IDE... ¡Hasta pronto![/dim]")
            break
        except Exception:
            try:
                user_input = input("AETHER ❯ ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Saliendo de AETHER IDE... ¡Hasta pronto![/dim]")
                break

        if not user_input:
            continue

        # Procesar comandos slash (/help, /plan, /cd, /mode, /undo, /exit, etc.)
        slash_result = handle_slash_command(user_input, orchestrator, console)
        if slash_result is False:
            break
        elif slash_result is True:
            continue

        # Validar conexión a Ollama antes de enviar tarea al modelo
        if not orchestrator.check_ollama_alive():
            console.print("[bold red]❌ Error: Ollama no está en ejecución. Inícialo con 'ollama serve'.[/bold red]")
            continue

        # Resolución y confirmación visual de menciones @archivo
        expanded_input, attached_files = resolve_at_file_mentions(user_input)
        if attached_files:
            for af in attached_files:
                try:
                    rel_p = af.relative_to(Path.cwd()).as_posix()
                except Exception:
                    rel_p = af.name
                line_cnt = len(af.read_text(encoding="utf-8", errors="replace").splitlines())
                console.print(f"  [dim]📎 Archivo adjuntado:[/] [bold cyan]{rel_p}[/bold cyan] [dim]({line_cnt} líneas)[/dim]")
            user_input = expanded_input

        # Ejecutar bucle ReAct
        with console.status("[bold cyan]AETHER pensando y ejecutando herramientas...[/bold cyan]", spinner="dots"):
            answer = orchestrator.run_turn(user_input)

        render_response(answer)


if __name__ == "__main__":
    main()
