"""
Punto de entrada de la consola interactiva CLI para AETHER Agent.
Interfaz enriquecida construida con 'rich' y 'prompt_toolkit'.
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from agent.orchestrator import AgentOrchestrator
from tools.git_tools import create_checkpoint, get_git_diff, get_git_status, undo_checkpoint

console = Console()


def render_banner(model_name: str, ollama_ok: bool):
    status_color = "green" if ollama_ok else "bold red"
    status_text = "CONECTADO A OLLAMA" if ollama_ok else "OLLAMA NO DETECTADO (Ejecuta 'ollama serve')"

    banner_text = f"""[bold cyan]⚡ AETHER IDE — Local Agentic Developer[/bold cyan]
[dim]Local-first Autonomous Coding Agent · RTX 4060 Optimized · 100% Offline[/dim]

[bold]Modelo activo:[/] [magenta]{model_name}[/magenta]
[bold]Estado de inferencia:[/] [{status_color}]{status_text}[/{status_color}]
[bold]Directorio de trabajo:[/] [yellow]{Path.cwd()}[/yellow]

[dim]Comandos especiales: /diff | /undo | /checkpoint | /status | /clear | /model <nombre> | /exit[/dim]
"""
    console.print(Panel(banner_text, border_style="cyan", title="[bold]AETHER v0.1.0[/bold]"))


def handle_thought(thought: str):
    console.print(Panel(f"[dim italic]{thought}[/dim italic]", title="[bold blue]🧠 Pensamiento / Análisis[/bold blue]", border_style="blue"))


def handle_tool_call(tool_name: str, args: dict):
    args_str = ", ".join(f"{k}='{v}'" if isinstance(v, str) and len(v) < 60 else f"{k}={v}" for k, v in args.items())
    if len(args_str) > 120:
        args_str = args_str[:120] + "..."
    console.print(f"[bold cyan]⚙️  Llamando herramienta:[/] [bold yellow]{tool_name}[/bold yellow]({args_str})")


def handle_tool_result(tool_name: str, result: str):
    preview = result.strip()
    if tool_name == "edit_file" and "Éxito" in preview:
        color = "green"
    elif "Error" in preview or "falló" in preview.lower():
        color = "red"
    else:
        color = "dim"

    if len(preview) > 400:
        display_text = preview[:400] + f"\n... [Salida completa de {len(preview)} caracteres]"
    else:
        display_text = preview

    console.print(Panel(display_text, title=f"[{color}]Resultado: {tool_name}[/{color}]", border_style=color))


def confirm_prompt(question: str) -> bool:
    console.print(f"\n[bold red]⚠️  ADVERTENCIA DE SEGURIDAD[/bold red]\n{question}")
    resp = console.input("[bold yellow]¿Autorizar acción? (s/N): [/bold yellow]").strip().lower()
    return resp in ["s", "si", "y", "yes"]


def main():
    model = "qwen2.5-coder:7b"
    orchestrator = AgentOrchestrator(
        model=model,
        on_thought=handle_thought,
        on_tool_call=handle_tool_call,
        on_tool_result=handle_tool_result,
        confirm_callback=confirm_prompt
    )

    ollama_ok = orchestrator.check_ollama_alive()
    render_banner(model, ollama_ok)

    try:
        session = PromptSession(history=InMemoryHistory())
    except Exception:
        session = None

    while True:
        try:
            if session:
                user_input = session.prompt("\nAETHER ❯ ").strip()
            else:
                user_input = input("\nAETHER ❯ ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Saliendo de AETHER IDE... ¡Hasta pronto![/dim]")
            break

        if not user_input:
            continue

        # Comandos especiales
        if user_input in ["/exit", "/quit"]:
            console.print("[dim]Sesión finalizada.[/dim]")
            break

        elif user_input == "/diff":
            diff = get_git_diff()
            console.print(Panel(Syntax(diff, "diff", theme="monokai", line_numbers=True), title="Git Diff Actual"))
            continue

        elif user_input == "/status":
            status = get_git_status()
            console.print(Panel(status, title="Git Status"))
            continue

        elif user_input == "/undo":
            res = undo_checkpoint()
            console.print(f"[bold yellow]{res}[/bold yellow]")
            continue

        elif user_input.startswith("/checkpoint"):
            msg = user_input[len("/checkpoint"):].strip() or "Manual checkpoint"
            res = create_checkpoint(msg)
            console.print(f"[bold green]{res}[/bold green]")
            continue

        elif user_input.startswith("/model"):
            parts = user_input.split()
            if len(parts) > 1:
                model = parts[1]
                orchestrator.model = model
                console.print(f"[bold green]Modelo cambiado a: {model}[/bold green]")
            else:
                console.print(f"[bold yellow]Modelo actual: {orchestrator.model}[/bold yellow]")
            continue

        elif user_input == "/clear":
            orchestrator.memory.clear()
            console.print("[bold cyan]Historial y contexto reiniciados.[/bold cyan]")
            continue

        elif user_input == "/help":
            help_text = """
### Comandos Disponibles:
- **/diff**: Muestra los cambios actuales de código frente al último commit.
- **/status**: Muestra el estado de archivos modificados en Git.
- **/checkpoint [mensaje]**: Guarda un punto de restauración seguro.
- **/undo**: Revierte al último checkpoint seguro en 1 segundo.
- **/model <nombre>**: Cambia el modelo de Ollama en caliente (ej: `/model qwen2.5-coder:3b`).
- **/clear**: Limpia el historial de conversación actual.
- **/exit**: Cierra la sesión de AETHER.
"""
            console.print(Markdown(help_text))
            continue

        # Validar conexión antes de enviar tarea
        if not orchestrator.check_ollama_alive():
            console.print("[bold red]❌ Error: Ollama no está en ejecución. Inícialo con 'ollama serve'.[/bold red]")
            continue

        # Ejecutar bucle ReAct
        with console.status("[bold cyan]AETHER pensando y ejecutando herramientas...[/bold cyan]", spinner="dots"):
            answer = orchestrator.run_turn(user_input)

        console.print("\n[bold green]Respuesta Final:[/bold green]")
        console.print(Markdown(answer))


if __name__ == "__main__":
    main()

