"""
Punto de entrada de la consola interactiva CLI para AETHER Agent.
Interfaz enriquecida construida con 'rich' y 'prompt_toolkit'.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.table import Table
from rich.rule import Rule
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.shortcuts import CompleteStyle

from agent.orchestrator import AgentOrchestrator
from agent.checkpoints import SafeCheckpointManager
from agent.session import SessionManager
from agent.telemetry import TelemetryLogger
from tools.git_tools import create_checkpoint, get_git_diff, get_git_status, undo_checkpoint
from tools.repomap import generate_repo_map

console = Console()


def render_banner(model_name: str, ollama_ok: bool):
    status_icon = "🟢" if ollama_ok else "🔴"
    status_text = "Conectado a Ollama (100% Offline)" if ollama_ok else "Ollama no detectado ('ollama serve')"
    status_style = "green" if ollama_ok else "bold red"

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="default")

    table.add_row("Modelo", f"[magenta]{model_name}[/magenta] [dim](RTX 4060 Optimizado)[/dim]")
    table.add_row("Inferencia", f"{status_icon} [{status_style}]{status_text}[/{status_style}]")
    table.add_row("Directorio", f"[yellow]{Path.cwd()}[/yellow]")
    table.add_row("Comandos", "[dim]/help · /plan · /test · /diff · /commit · /mode · /compact · /exit[/dim]")

    console.print(
        Panel(
            table,
            title="[bold cyan]⚡ AETHER IDE[/bold cyan]",
            subtitle="[dim]Local Agentic Software Engineer[/dim]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def handle_thought(thought: str):
    clean = thought.strip()
    if not clean:
        return
    # Ignorar dumps accidentales de JSON o llamadas a herramientas
    if clean.startswith("{") and ("name" in clean or "arguments" in clean or "function" in clean):
        return
    # Ignorar bloques de código markdown sueltos
    if clean.startswith("```"):
        return

    lines = [l for l in clean.splitlines() if l.strip()]
    if not lines:
        return

    # Si es breve (1 a 2 líneas), renderizar como una nota limpia inline
    if len(lines) <= 2 and len(clean) < 160:
        console.print(f"[bold blue]💭[/bold blue] [dim italic]{clean}[/dim italic]")
    else:
        preview_lines = lines[:6]
        preview_text = "\n".join(preview_lines)
        if len(lines) > 6:
            preview_text += f"\n[dim]... (+{len(lines) - 6} líneas de análisis)[/dim]"
        console.print(
            Panel(
                preview_text,
                title="[bold blue]💭 Razonamiento[/bold blue]",
                border_style="dim blue",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )


def handle_tool_call(tool_name: str, args: dict):
    if tool_name in ["write_file", "create_file"]:
        path = args.get("path", "")
        content = args.get("content", "")
        lines = len(content.splitlines()) if content else 0
        chars = len(content)
        detail = f" [dim]({lines} líneas, {chars} bytes)[/dim]" if chars else ""
        console.print(f"⚙️  [bold cyan]{tool_name}[/] [bold yellow]{path}[/bold yellow]{detail}")

    elif tool_name == "edit_file":
        path = args.get("path", "")
        target = args.get("target")
        detail = " [dim](reemplazo dirigido)[/dim]" if target else " [dim](actualización)[/dim]"
        console.print(f"⚙️  [bold cyan]edit_file[/] [bold yellow]{path}[/bold yellow]{detail}")

    elif tool_name == "read_file":
        path = args.get("path", "")
        start = args.get("start_line", 1)
        end = args.get("end_line")
        range_str = f" [dim](L{start}-{end})[/dim]" if end else f" [dim](L{start}+)[/dim]"
        console.print(f"⚙️  [bold cyan]read_file[/] [bold yellow]{path}[/bold yellow]{range_str}")

    elif tool_name == "run_command":
        cmd = args.get("command", "")
        console.print(f"⚙️  [bold cyan]run_command[/] [bold yellow]$ {cmd}[/bold yellow]")

    elif tool_name == "run_tests":
        target = args.get("test_target")
        t_str = f" [bold yellow]{target}[/bold yellow]" if target else " [dim](suite completa)[/dim]"
        console.print(f"⚙️  [bold cyan]run_tests[/]{t_str}")

    elif tool_name == "update_plan":
        step = args.get("current_step", "")
        s_str = f" [dim](Paso {step})[/dim]" if step else ""
        console.print(f"⚙️  [bold cyan]update_plan[/] [bold yellow].aether/plans/plan_activo.md[/bold yellow]{s_str}")

    elif tool_name in ["conclude_turn", "finish_turn", "complete_task", "finish", "done"]:
        summary = args.get("summary", "")
        s_str = f" [dim]({summary[:60]}...)[/dim]" if len(summary) > 60 else (f" [dim]({summary})[/dim]" if summary else "")
        console.print(f"🏁 [bold green]{tool_name}[/]{s_str}")

    else:
        clean_args = []
        for k, v in args.items():
            if isinstance(v, str):
                v_clean = v.replace("\n", " ").strip()
                if len(v_clean) > 30:
                    v_clean = v_clean[:30] + "..."
                clean_args.append(f"{k}='{v_clean}'")
            else:
                clean_args.append(f"{k}={v}")
        args_str = ", ".join(clean_args)
        if len(args_str) > 80:
            args_str = args_str[:80] + "..."
        console.print(f"⚙️  [bold cyan]{tool_name}[/][dim]({args_str})[/dim]")


def handle_tool_result(tool_name: str, result: str):
    preview = result.strip()

    # Manejo visual de Circuit Breakers y advertencias del sistema
    if "[CIRCUIT BREAKER" in preview or "⛔" in preview:
        m = re.search(r"⛔\s*\[CIRCUIT BREAKER[^\]]*\]:\s*([^\n\r]+)", preview)
        reason = m.group(1).strip() if m else preview[:120]
        act_m = re.search(r"•\s*Tu SIGUIENTE ACCIÓN OBLIGATORIA es\s*([^\n\r]+)", preview)
        action = f" ➔ [yellow]{act_m.group(1).strip()}[/yellow]" if act_m else ""
        console.print(f"  [bold yellow]⛔ Circuit Breaker:[/] [bold]{reason}[/bold]{action}")
        return

    # Operaciones de creación / escritura de archivos
    if tool_name in ["write_file", "create_file"]:
        first_line = preview.splitlines()[0] if preview else "Archivo escrito."
        if "Éxito" in preview or "exitosamente" in preview.lower() or "creado" in preview.lower():
            console.print(f"  [bold green]✔[/bold green] [green]{first_line}[/green]")
        else:
            console.print(f"  [bold red]✖[/bold red] [red]{first_line}[/red]")
        return

    # Operaciones de edición
    if tool_name == "edit_file":
        first_line = preview.splitlines()[0] if preview else "Edición aplicada."
        if "Éxito" in preview or "exitosamente" in preview.lower() or "modificado" in preview.lower():
            console.print(f"  [bold green]✔[/bold green] [green]{first_line}[/green]")
        else:
            console.print(f"  [bold red]✖[/bold red] [red]{first_line}[/red]")
        return

    # Lectura de archivos
    if tool_name == "read_file":
        lines_count = len(preview.splitlines())
        console.print(f"  [bold green]✔[/bold green] [dim]Leídas {lines_count} líneas ({len(preview)} bytes)[/dim]")
        return

    # Actualización de plan
    if tool_name == "update_plan":
        console.print(f"  [bold green]✔[/bold green] [green]Plan activo sincronizado[/green]")
        return

    # Ejecución de pruebas unitarias (run_tests)
    if tool_name == "run_tests":
        if "Código de salida: 0" in preview:
            m = re.search(r"=+\s*(\d+\s+passed[^\n\r=]*)=+", preview)
            summary = m.group(1).strip() if m else "Todos los tests pasaron exitosamente"
            console.print(f"  [bold green]✔[/bold green] [bold green]Pruebas superadas:[/] [green]{summary}[/green]")
        else:
            fail_match = re.findall(r"(?:FAILED|ERROR)\s+[^\n\r]+", preview)
            fails = "\n".join(fail_match[:4]) if fail_match else preview[:250]
            console.print(
                Panel(
                    fails,
                    title="[bold red]❌ Pruebas Fallaron (Exit Code 1)[/bold red]",
                    border_style="red",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
        return

    # Errores generales
    if preview.startswith("Error") or "falló" in preview.lower():
        first_line = preview.splitlines()[0] if preview else "Error en la herramienta."
        console.print(f"  [bold red]✖[/bold red] [red]{first_line}[/red]")
        return

    # Resultados genéricos (salida corta vs panel)
    lines = preview.splitlines()
    if len(lines) <= 2 and len(preview) < 160:
        console.print(f"  [dim]› {preview}[/dim]")
    else:
        disp = "\n".join(lines[:8])
        if len(lines) > 8:
            disp += f"\n[dim]... (+{len(lines) - 8} líneas)[/dim]"
        console.print(
            Panel(
                disp,
                title=f"[dim]Resultado: {tool_name}[/dim]",
                border_style="dim",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )


def render_response(answer: str):
    console.print()
    console.rule("[bold cyan]✦ Respuesta AETHER[/bold cyan]", style="cyan")
    console.print(Markdown(answer.strip()))
    console.rule(style="dim cyan")
    console.print()


COMMANDS_META = {
    "/help": "Muestra la guía completa de comandos y atajos",
    "/plan": "Diseñar o consultar el plan de arquitectura activo",
    "/test": "Ejecuta la suite de pruebas unitarias con pytest",
    "/diff": "Muestra las diferencias Git respecto al último commit",
    "/commit": "Genera un commit atómico con mensaje semántico",
    "/mode": "Cambia el modo operativo: /mode [agent|ask|plan|review]",
    "/model": "Cambia el modelo de Ollama en caliente",
    "/compact": "Compacta el historial para liberar contexto",
    "/undo": "Revierte al checkpoint o commit anterior",
    "/checkpoint": "Crea un punto de restauración Git inmediato",
    "/map": "Genera el mapa estructural del repositorio",
    "/status": "Muestra el estado del agente y métricas VRAM",
    "/sessions": "Lista el historial de sesiones SQLite",
    "/resume": "Reanuda una sesión previa por session_id",
    "/memory": "Gestiona hechos y reglas en memoria a largo plazo",
    "/telemetry": "Muestra telemetría de latencia y herramientas",
    "/export": "Exporta la sesión actual a un archivo Markdown",
    "/voice": "Instrucciones de integración con Asistente de Voz",
    "/clear": "Limpia el contexto y memoria de la sesión actual",
    "/cd": "Cambia el directorio de trabajo del agente",
    "/exit": "Finaliza y sale de la consola de AETHER",
    "/quit": "Finaliza y sale de la consola de AETHER",
}

COMPLETION_WORDS = list(COMMANDS_META.keys()) + [
    "/mode agent", "/mode ask", "/mode plan", "/mode review",
    "/memory list", "/checkpoint create", "/checkpoint undo"
]


def confirm_prompt(question: str) -> bool:
    """Solicita confirmación al usuario para acciones de riesgo o revisiones de código."""
    if "--- a/" in question or "+++ b/" in question or "@@ " in question:
        lines = question.splitlines()
        diff_lines = []
        header_lines = []
        footer_lines = []
        in_diff = False
        finished_diff = False

        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@ "):
                in_diff = True
                diff_lines.append(line)
            elif in_diff and (line.startswith("+") or line.startswith("-") or line.startswith(" ") or not line.strip()):
                diff_lines.append(line)
            elif in_diff:
                in_diff = False
                finished_diff = True
                footer_lines.append(line)
            elif not finished_diff:
                header_lines.append(line)
            else:
                footer_lines.append(line)

        header_text = "\n".join(header_lines).strip()
        footer_text = "\n".join(footer_lines).strip()
        diff_text = "\n".join(diff_lines)

        if header_text:
            console.print(f"\n[bold magenta]🔍 MODO REVIEW — SUPERVISIÓN DE CAMBIOS[/bold magenta]\n[dim]{header_text}[/dim]")
        if diff_text:
            console.print(
                Panel(
                    Syntax(diff_text, "diff", theme="monokai", line_numbers=True),
                    title="[bold magenta]🔍 Vista Previa de Cambios (Unified Diff)[/bold magenta]",
                    border_style="magenta",
                    box=box.ROUNDED,
                )
            )
        prompt_label = footer_text or "¿Autorizar esta modificación?"
        resp = console.input(f"[bold yellow]{prompt_label} (s/N): [/bold yellow]").strip().lower()
        return resp in ["s", "si", "y", "yes"]

    console.print(f"\n[bold red]⚠️  ADVERTENCIA DE SEGURIDAD[/bold red]\n{question}")
    resp = console.input("[bold yellow]¿Autorizar acción? (s/N): [/bold yellow]").strip().lower()
    return resp in ["s", "si", "y", "yes"]


def main():
    parser = argparse.ArgumentParser(description="AETHER Agent CLI")
    parser.add_argument("-p", "--prompt", type=str, default=None, help="Ejecutar una tarea en modo no interactivo y salir")
    parser.add_argument("--model", type=str, default="qwen2.5-coder:7b", help="Modelo de Ollama a utilizar")
    cli_args, unknown = parser.parse_known_args()

    model = cli_args.model
    orchestrator = AgentOrchestrator(
        model=model,
        on_thought=handle_thought,
        on_tool_call=handle_tool_call,
        on_tool_result=handle_tool_result,
        confirm_callback=confirm_prompt
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
    from agent.context import AetherCLICompleter, resolve_at_file_mentions
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

        cmd = user_input.split()[0].lower() if user_input.startswith("/") else ""

        # Comandos especiales
        if cmd in ["/exit", "/quit"]:
            console.print("[dim]Sesión finalizada. ¡Hasta pronto![/dim]")
            break

        elif cmd == "/cd":
            target_dir = user_input[len(user_input.split()[0]):].strip()
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
                    console.print(Panel(repo_map, title=f"[bold cyan]📦 Repo-Map de {p.name}[/bold cyan]", border_style="cyan", box=box.ROUNDED))
                else:
                    console.print(f"[bold red]Error:[/] La ruta '{target_dir}' no existe o no es un directorio válido.")
            continue

        elif cmd == "/map":
            repo_map = generate_repo_map()
            console.print(Panel(repo_map, title="[bold cyan]📦 Arquitectura del Repositorio (Repo-Map)[/bold cyan]", border_style="cyan", box=box.ROUNDED))
            continue

        elif cmd == "/test":
            test_target = user_input[len(user_input.split()[0]):].strip()
            cmd_args = ["pytest", "-v"] if not test_target else ["pytest", "-v", test_target]
            console.print(f"[bold yellow]🧪 Ejecutando pruebas con {' '.join(cmd_args)}...[/bold yellow]")
            try:
                proc = subprocess.run(cmd_args, capture_output=True, text=True, encoding="utf-8", errors="replace")
                out = proc.stdout.strip() or proc.stderr.strip()
                color = "green" if proc.returncode == 0 else "red"
                status_title = "✅ Tests Pasaron" if proc.returncode == 0 else "❌ Tests Fallaron"
                console.print(Panel(out, title=f"[{color}]{status_title}[/{color}]", border_style=color, box=box.ROUNDED))

                if proc.returncode != 0:
                    auto_fix = console.input("\n[bold yellow]¿Deseas que AETHER repare los errores automáticamente? (S/n): [/bold yellow]").strip().lower()
                    if auto_fix in ["", "s", "si", "y", "yes"]:
                        fix_prompt = f"Las pruebas fallaron con el siguiente resultado:\n{out}\nAnaliza el error y repara el código de inmediato para que todos los tests pasen."
                        with console.status("[bold cyan]AETHER auto-reparando el código...[/bold cyan]", spinner="dots"):
                            fix_answer = orchestrator.run_turn(fix_prompt)
                        render_response(fix_answer)
            except FileNotFoundError:
                console.print("[bold red]No se encontró pytest instalado en el entorno. Ejecuta 'pip install pytest'.[/bold red]")
            continue

        elif cmd == "/commit":
            commit_msg = user_input[len(user_input.split()[0]):].strip()
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

        elif cmd == "/export":
            filename = user_input[len(user_input.split()[0]):].strip() or f"aether_sesion_{Path.cwd().name}.md"
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

        elif cmd == "/diff":
            diff = get_git_diff()
            console.print(Panel(Syntax(diff, "diff", theme="monokai", line_numbers=True), title="Git Diff Actual", box=box.ROUNDED))
            continue

        elif cmd == "/status":
            git_st = get_git_status()
            token_count = orchestrator.memory.estimate_tokens()
            msg_count = len(orchestrator.memory.get_messages())
            status_report = f"""[bold]Modelo:[/] {orchestrator.model}
[bold]Sesión Activa:[/] [cyan]{orchestrator.session_id}[/cyan]
[bold]Estado Formal:[/] [green]{orchestrator.state.value}[/green]
[bold]Modo Operativo:[/] [cyan]{orchestrator.hooks.mode.upper()}[/cyan]
[bold]Mensajes en Contexto:[/] {msg_count} turnos (~{token_count} tokens)
[bold]Directorio:[/] {Path.cwd()}

[bold cyan]--- Estado de Git ---[/bold cyan]
{git_st}"""
            console.print(Panel(status_report, title="[bold green]📊 Estado del Sistema AETHER[/bold green]", border_style="green", box=box.ROUNDED))
            continue

        elif cmd in ["/sessions", "/session"]:
            sm = SessionManager()
            sessions = sm.list_sessions(limit=10)
            if not sessions:
                console.print("[yellow]No hay sesiones previas registradas.[/yellow]")
            else:
                lines = ["[bold cyan]ID Sesión | Fecha | Estado | Modelo[/bold cyan]"]
                for s in sessions:
                    active_marker = " (activa)" if s["session_id"] == orchestrator.session_id else ""
                    lines.append(f"• [green]{s['session_id']}[/green]{active_marker} | {s['updated_at'][:19]} | {s['state']} | {s['model']}")
                console.print(Panel("\n".join(lines), title="🗄️ Historial de Sesiones Persistentes", border_style="cyan", box=box.ROUNDED))
            continue

        elif cmd == "/resume":
            target_id = user_input[len(user_input.split()[0]):].strip()
            if not target_id:
                console.print("[bold red]Uso:[/] /resume <session_id>")
                continue
            sm = SessionManager()
            past_msgs = sm.get_session_messages(target_id)
            if not past_msgs:
                console.print(f"[bold red]Error:[/] No se encontraron mensajes para la sesión '{target_id}'.")
            else:
                orchestrator.session_id = target_id
                orchestrator.memory.messages = past_msgs
                console.print(f"[bold green]✅ Sesión '{target_id}' reanudada con {len(past_msgs)} mensajes cargados en contexto.[/bold green]")
            continue

        elif cmd == "/telemetry":
            tlog = TelemetryLogger()
            summary = tlog.get_summary()
            telem_text = f"""[bold]Turnos Totales de Agente:[/] {summary['total_turns']}
[bold]Llamadas a Herramientas:[/] {summary['total_tool_calls']}
[bold]Fallos / Reintentos de Herramientas:[/] {summary['tool_failures']} ({summary['tool_failure_rate_percent']}%)
[bold]Duración Promedio por Turno:[/] {summary['average_turn_duration_seconds']}s"""
            console.print(Panel(telem_text, title="📈 Telemetría y Rendimiento de AETHER", border_style="magenta", box=box.ROUNDED))
            continue

        elif cmd == "/undo":
            res = undo_checkpoint()
            console.print(f"[bold yellow]{res}[/bold yellow]")
            continue

        elif cmd in ["/checkpoint", "/checkpoints"]:
            msg = user_input[len(user_input.split()[0]):].strip() or "Manual checkpoint"
            res = create_checkpoint(msg)
            console.print(f"[bold green]{res}[/bold green]")
            continue

        elif cmd in ["/model", "/models"]:
            parts = user_input.split()
            if len(parts) > 1:
                model = parts[1]
                orchestrator.model = model
                console.print(f"[bold green]Modelo cambiado a: {model}[/bold green]")
            else:
                console.print(f"[bold yellow]Modelo actual: {orchestrator.model}[/bold yellow]")
            continue

        elif cmd == "/mode":
            parts = user_input.split()
            if len(parts) > 1:
                target_mode = parts[1].lower().strip()
                if target_mode in ["agent", "ask", "plan", "review"]:
                    orchestrator.set_mode(target_mode)
                    mode_colors = {"agent": "green", "ask": "yellow", "plan": "cyan", "review": "magenta"}
                    mode_desc = {
                        "agent": "Modo AGENT: Plenos poderes de creación, edición y ejecución autónoma.",
                        "ask": "Modo ASK (Solo Lectura): El agente solo responde dudas e inspecciona código sin modificarlo.",
                        "plan": "Modo PLAN: Diseña el plan de arquitectura antes de tocar código.",
                        "review": "Modo REVIEW: Supervisión interactiva con previsualización de diffs unificados antes de cada cambio en disco."
                    }
                    console.print(f"[bold {mode_colors[target_mode]}]{mode_desc[target_mode]}[/bold {mode_colors[target_mode]}]")
                else:
                    console.print("[bold red]Modo no válido.[/bold red] Opciones: /mode agent | /mode ask | /mode plan | /mode review")
            else:
                console.print(f"[bold yellow]Modo actual:[/] {orchestrator.hooks.mode.upper()}")
            continue

        elif cmd == "/plan":
            plan_goal = user_input[len(user_input.split()[0]):].strip()
            orchestrator.set_mode("plan")
            console.print("[bold cyan]🧭 Modo PLAN activado (Planificación Arquitectónica).[/bold cyan]")

            if not plan_goal:
                plan_file = Path.cwd() / ".aether" / "plans" / "plan_activo.md"
                if plan_file.is_file():
                    try:
                        content = plan_file.read_text(encoding="utf-8")
                        console.print(Panel(Markdown(content), title="[bold cyan]📋 Plan Activo de AETHER[/bold cyan]", border_style="cyan", box=box.ROUNDED))
                    except Exception as e:
                        console.print(f"[bold red]Error al leer plan:[/] {e}")
                else:
                    console.print("[dim]No hay un plan activo en .aether/plans/plan_activo.md.[/dim]\n[bold cyan]Para diseñar un nuevo plan, escribe:[/] /plan <descripción de la tarea>")
            else:
                prompt_plan = (
                    f"El usuario desea diseñar un plan arquitectónico para la siguiente tarea:\n"
                    f"<task>\n{plan_goal}\n</task>\n"
                    f"Explora la arquitectura existente con 'get_repo_map' o 'search_codebase' si es necesario, "
                    f"y llama OBLIGATORIAMENTE a 'update_plan' con los hitos secuenciales ordenados y los criterios de aceptación observables. "
                    f"NO intentes modificar archivos de código fuente todavía."
                )
                with console.status("[bold cyan]AETHER analizando y diseñando plan arquitectónico...[/bold cyan]", spinner="dots"):
                    plan_result = orchestrator.run_turn(prompt_plan)
                render_response(plan_result)
            continue

        elif cmd == "/voice":
            voice_info = """
### 🎙️ Integración con Asistente de Voz Local (Hands-Free Coding)
Para controlar tu desarrollo por voz en paralelo con AETHER:
1. Abre tu terminal en `c:\\Users\\evo_l\\Desktop\\WebsPage\\ChatGptVoiceProject`.
2. Inicia el servidor con `run.bat`.
3. Activa el modo manos libres en la interfaz web (`http://localhost:8000`).
4. Cualquier comando o instrucción de voz que dictes se procesará con latencia ultrabaja (<50ms).
"""
            console.print(Panel(Markdown(voice_info), title="🎙️ Voice Assistant Integration", border_style="cyan", box=box.ROUNDED))
            continue

        elif cmd == "/clear":
            orchestrator.memory.clear()
            console.print("[bold cyan]Historial y contexto reiniciados.[/bold cyan]")
            continue

        elif cmd == "/compact":
            tokens_before = orchestrator.memory.estimate_tokens()
            orchestrator.memory.compact_memory()
            tokens_after = orchestrator.memory.estimate_tokens()
            saved = max(0, tokens_before - tokens_after)
            console.print(f"[bold green]✅ Contexto compactado exitosamente:[/] {tokens_before} ➔ {tokens_after} tokens (~{saved} tokens liberados en VRAM).")
            continue

        elif cmd in ["/memory", "/memories"]:
            mem_arg = user_input[len(user_input.split()[0]):].strip()
            from tools.agent_tools import list_memories, search_memory
            if not mem_arg:
                res = list_memories()
                console.print(Panel(res, title="[bold cyan]🧠 Memoria Semántica Persistente[/bold cyan]", border_style="cyan", box=box.ROUNDED))
            elif mem_arg.startswith("search "):
                q = mem_arg[len("search "):].strip()
                res = search_memory(q)
                console.print(Panel(res, title=f"[bold cyan]🔍 Búsqueda Semántica: '{q}'[/bold cyan]", border_style="cyan", box=box.ROUNDED))
            else:
                res = search_memory(mem_arg)
                console.print(Panel(res, title=f"[bold cyan]🔍 Búsqueda Semántica: '{mem_arg}'[/bold cyan]", border_style="cyan", box=box.ROUNDED))
            continue

        elif cmd == "/help":
            help_table = Table(title="🛠️  Comandos Especiales de AETHER IDE", box=box.ROUNDED, border_style="cyan", header_style="bold cyan")
            help_table.add_column("Comando", style="bold yellow", no_wrap=True)
            help_table.add_column("Descripción", style="default")
            help_table.add_row("/plan [objetivo]", "Diseña y visualiza artefactos de planes arquitectónicos en .aether/plans/")
            help_table.add_row("/test [archivo]", "Ejecuta pruebas con pytest y ofrece auto-sanación instantánea si algo falla")
            help_table.add_row("/diff", "Muestra los cambios actuales de código frente al último commit")
            help_table.add_row("/commit [mensaje]", "Realiza commit atómico de todos los cambios con mensaje convencional")
            help_table.add_row("/cd <ruta>", "Cambia el directorio de trabajo dinámicamente a cualquier proyecto de tu PC")
            help_table.add_row("/map", "Muestra el mapa arquitectónico completo del repositorio (Repo-Map)")
            help_table.add_row("/compact", "Compacta el historial de conversación en un resumen ejecutivo liberando VRAM")
            help_table.add_row("/status", "Muestra el estado de Git, modo operativo y telemetría de tokens en VRAM")
            help_table.add_row("/mode [agent|ask|plan|review]", "Cambia el modo operativo (Agent: autónomo total, Ask: solo lectura, Plan: arquitectura, Review: diff interactivo)")
            help_table.add_row("/model <nombre>", "Cambia el modelo de Ollama en caliente (ej: /model qwen2.5-coder:7b)")
            help_table.add_row("/undo", "Revierte al último checkpoint seguro en 1 segundo")
            help_table.add_row("/checkpoint [mensaje]", "Guarda un punto de restauración seguro con Git")
            help_table.add_row("/sessions", "Lista las sesiones persistentes almacenadas en SQLite (.aether/sessions.db)")
            help_table.add_row("/resume <id>", "Reanuda una sesión previa restaurando el historial completo de mensajes")
            help_table.add_row("/memory [search <q>]", "Consulta o busca hechos persistentes y decisiones en la memoria semántica")
            help_table.add_row("/telemetry", "Muestra métricas de rendimiento, latencia y tasa de éxito de herramientas")
            help_table.add_row("/export [archivo]", "Exporta la sesión completa y código generado a un documento Markdown")
            help_table.add_row("/voice", "Guía de conexión con el Asistente de Voz Local en tiempo real (<50ms)")
            help_table.add_row("/clear", "Limpia el historial de conversación para liberar memoria de contexto")
            help_table.add_row("/exit", "Cierra la sesión de AETHER")
            console.print(help_table)
            continue

        # Manejo de comandos no reconocidos que inician con '/'
        elif user_input.startswith("/"):
            console.print(f"[bold red]❌ Comando no reconocido:[/] '{cmd}'. Escribe [bold cyan]/help[/bold cyan] para ver la lista de comandos disponibles.")
            continue

        # Validar conexión antes de enviar tarea
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

