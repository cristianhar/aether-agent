"""
Punto de entrada de la consola interactiva CLI para AETHER Agent.
Interfaz enriquecida construida con 'rich' y 'prompt_toolkit'.
"""

import os
import subprocess
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
from tools.repomap import generate_repo_map

console = Console()


def render_banner(model_name: str, ollama_ok: bool):
    status_color = "green" if ollama_ok else "bold red"
    status_text = "CONECTADO A OLLAMA" if ollama_ok else "OLLAMA NO DETECTADO (Ejecuta 'ollama serve')"

    banner_text = f"""[bold cyan]⚡ AETHER IDE — Local Agentic Developer[/bold cyan]
[dim]Local-first Autonomous Coding Agent · RTX 4060 Optimized · 100% Offline[/dim]

[bold]Modelo activo:[/] [magenta]{model_name}[/magenta]
[bold]Estado de inferencia:[/] [{status_color}]{status_text}[/{status_color}]
[bold]Directorio de trabajo:[/] [yellow]{Path.cwd()}[/yellow]

[dim]Comandos: /cd <ruta> | /map | /test | /commit | /diff | /export | /undo | /model <nombre> | /clear | /exit[/dim]
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
            console.print("[dim]Sesión finalizada. ¡Hasta pronto![/dim]")
            break

        elif user_input.startswith("/cd"):
            target_dir = user_input[len("/cd"):].strip()
            if not target_dir:
                console.print(f"[bold yellow]Directorio actual:[/] {Path.cwd()}")
            else:
                p = Path(target_dir).expanduser().resolve()
                if p.exists() and p.is_dir():
                    os.chdir(p)
                    console.print(f"[bold green]Directorio cambiado a:[/] {p}")
                    orchestrator.memory.clear()
                    console.print("[dim]Contexto reiniciado para el nuevo proyecto.[/dim]")
                    repo_map = generate_repo_map(str(p), max_files=15)
                    console.print(Panel(repo_map, title=f"[bold cyan]📦 Repo-Map de {p.name}[/bold cyan]", border_style="cyan"))
                else:
                    console.print(f"[bold red]Error:[/] La ruta '{target_dir}' no existe o no es un directorio válido.")
            continue

        elif user_input == "/map":
            repo_map = generate_repo_map()
            console.print(Panel(repo_map, title="[bold cyan]📦 Arquitectura del Repositorio (Repo-Map)[/bold cyan]", border_style="cyan"))
            continue

        elif user_input.startswith("/test"):
            test_target = user_input[len("/test"):].strip()
            cmd = ["pytest", "-v"] if not test_target else ["pytest", "-v", test_target]
            console.print(f"[bold yellow]🧪 Ejecutando pruebas con {' '.join(cmd)}...[/bold yellow]")
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                out = proc.stdout.strip() or proc.stderr.strip()
                color = "green" if proc.returncode == 0 else "red"
                status_title = "✅ Tests Pasaron" if proc.returncode == 0 else "❌ Tests Fallaron"
                console.print(Panel(out, title=f"[{color}]{status_title}[/{color}]", border_style=color))

                if proc.returncode != 0:
                    auto_fix = console.input("\n[bold yellow]¿Deseas que AETHER repare los errores automáticamente? (S/n): [/bold yellow]").strip().lower()
                    if auto_fix in ["", "s", "si", "y", "yes"]:
                        fix_prompt = f"Las pruebas fallaron con el siguiente resultado:\n{out}\nAnaliza el error y repara el código de inmediato para que todos los tests pasen."
                        with console.status("[bold cyan]AETHER auto-reparando el código...[/bold cyan]", spinner="dots"):
                            fix_answer = orchestrator.run_turn(fix_prompt)
                        console.print(Markdown(fix_answer))
            except FileNotFoundError:
                console.print("[bold red]No se encontró pytest instalado en el entorno. Ejecuta 'pip install pytest'.[/bold red]")
            continue

        elif user_input.startswith("/commit"):
            commit_msg = user_input[len("/commit"):].strip()
            diff_text = get_git_diff()
            if not diff_text or "No hay diferencias" in diff_text:
                console.print("[yellow]No hay modificaciones pendientes de commitear en el proyecto.[/yellow]")
                continue

            if not commit_msg:
                commit_msg = f"feat(agent): autonomous update in {Path.cwd().name}"

            subprocess.run(["git", "add", "-A"], capture_output=True)
            res = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True, encoding="utf-8")
            if res.returncode == 0:
                console.print(f"[bold green]✅ Commit realizado:[/] {commit_msg}")
            else:
                console.print(f"[bold red]Error en commit:[/] {res.stderr.strip() or res.stdout.strip()}")
            continue

        elif user_input.startswith("/export"):
            filename = user_input[len("/export"):].strip() or f"aether_sesion_{Path.cwd().name}.md"
            msgs = orchestrator.memory.get_messages()
            md_lines = [f"# Sesión AETHER IDE — {Path.cwd().name}\n"]
            for m in msgs:
                role = m.get("role", "").upper()
                content = m.get("content", "")
                if role != "SYSTEM" and content:
                    md_lines.append(f"### {role}:\n{content}\n")
            out_path = Path.cwd() / filename
            out_path.write_text("\n".join(md_lines), encoding="utf-8")
            console.print(f"[bold green]✅ Sesión exportada exitosamente a:[/] {out_path}")
            continue

        elif user_input == "/diff":
            diff = get_git_diff()
            console.print(Panel(Syntax(diff, "diff", theme="monokai", line_numbers=True), title="Git Diff Actual"))
            continue

        elif user_input == "/status":
            git_st = get_git_status()
            token_count = orchestrator.memory.estimate_tokens()
            msg_count = len(orchestrator.memory.get_messages())
            status_report = f"""[bold]Modelo:[/] {orchestrator.model}
[bold]Mensajes en Contexto:[/] {msg_count} turnos (~{token_count} tokens)
[bold]Directorio:[/] {Path.cwd()}

[bold cyan]--- Estado de Git ---[/bold cyan]
{git_st}"""
            console.print(Panel(status_report, title="[bold green]📊 Estado del Sistema AETHER[/bold green]", border_style="green"))
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

        elif user_input == "/voice":
            voice_info = """
### 🎙️ Integración con Asistente de Voz Local (Hands-Free Coding)
Para controlar tu desarrollo por voz en paralelo con AETHER:
1. Abre tu terminal en `c:\\Users\\evo_l\\Desktop\\WebsPage\\ChatGptVoiceProject`.
2. Inicia el servidor con `run.bat`.
3. Activa el modo manos libres en la interfaz web (`http://localhost:8000`).
4. Cualquier comando o instrucción de voz que dictes se procesará con latencia ultrabaja (<50ms).
"""
            console.print(Panel(Markdown(voice_info), title="🎙️ Voice Assistant Integration", border_style="cyan"))
            continue

        elif user_input == "/clear":
            orchestrator.memory.clear()
            console.print("[bold cyan]Historial y contexto reiniciados.[/bold cyan]")
            continue

        elif user_input == "/help":
            help_text = """
### 🛠️ Comandos Especiales Slash (`/`):
- **/cd <ruta>**: Cambia el directorio de trabajo dinámicamente a cualquier proyecto de tu PC.
- **/map**: Muestra el mapa arquitectónico completo del repositorio (archivos, clases, funciones).
- **/test [archivo]**: Ejecuta pruebas con pytest y ofrece auto-sanación instantánea si algo falla.
- **/commit [mensaje]**: Hace `git add -A` y commit de todos los cambios de forma limpia.
- **/diff**: Muestra los cambios actuales de código frente al último commit con resaltado de sintaxis.
- **/export [archivo]**: Exporta la sesión completa y código generado a un documento Markdown.
- **/status**: Muestra el estado de archivos en Git y telemetría de tokens en VRAM.
- **/undo**: Revierte al último checkpoint seguro en 1 segundo.
- **/checkpoint [mensaje]**: Guarda un punto de restauración seguro con Git.
- **/model <nombre>**: Cambia el modelo de Ollama en caliente (ej: `/model qwen2.5-coder:7b`).
- **/voice**: Guía de conexión con el Asistente de Voz Local en tiempo real.
- **/clear**: Limpia el historial de conversación para liberar memoria de contexto.
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

