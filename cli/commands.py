"""
Despachador y manejador de comandos slash (/command) para AETHER Agent CLI.
Modulariza toda la lógica de control, sesión, Git y herramientas especiales de la consola.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agent.session import SessionManager
from agent.telemetry import TelemetryLogger
from tools.git_tools import create_checkpoint, get_git_diff, get_git_status, undo_checkpoint
from tools.repomap import generate_repo_map
from tools.agent_tools import list_memories, search_memory
from cli.ui import console as default_console, render_response


def handle_slash_command(
    user_input: str,
    orchestrator,
    console: Console = default_console
) -> Optional[bool]:
    """
    Procesa un comando de barra inclinada (slash command) si el usuario lo ingresó.

    Retorna:
        - False: si el comando indica terminar la sesión (/exit, /quit).
        - True: si era un comando slash y fue procesado (la consola debe continuar el bucle).
        - None: si la entrada NO es un comando slash (debe pasar al bucle ReAct del agente).
    """
    if not user_input.startswith("/"):
        return None

    cmd = user_input.split()[0].lower()

    # Comandos de salida
    if cmd in ["/exit", "/quit"]:
        console.print("[dim]Sesión finalizada. ¡Hasta pronto![/dim]")
        return False

    # Cancelación de turno o tarea activa
    elif cmd in ["/cancel", "/stop"]:
        if hasattr(orchestrator, "cancel_active_turn"):
            orchestrator.cancel_active_turn()
        else:
            if hasattr(orchestrator, "state"):
                from agent.state import AgentState
                orchestrator.state = AgentState.IDLE
        console.print("[bold yellow]🛑 Turno o tarea cancelada. El agente está en reposo (IDLE) y listo para nuevas instrucciones.[/bold yellow]")
        return True

    # Cambio de directorio de trabajo
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
        return True

    # Generación y visualización del mapa de repositorio
    elif cmd == "/map":
        repo_map = generate_repo_map()
        console.print(Panel(repo_map, title="[bold cyan]📦 Arquitectura del Repositorio (Repo-Map)[/bold cyan]", border_style="cyan", box=box.ROUNDED))
        return True

    # Ejecución de pruebas unitarias y auto-sanación opcional
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
                    fix_prompt = (
                        f"Las pruebas fallaron con el siguiente resultado:\n{out}\n"
                        f"Analiza el error y repara el código de inmediato para que todos los tests pasen."
                    )
                    with console.status("[bold cyan]AETHER auto-reparando el código...[/bold cyan]", spinner="dots"):
                        fix_answer = orchestrator.run_turn(fix_prompt)
                    render_response(fix_answer)
        except FileNotFoundError:
            console.print("[bold red]No se encontró pytest instalado en el entorno. Ejecuta 'pip install pytest'.[/bold red]")
        return True

    # Creación de commit Git con diff semántico
    elif cmd == "/commit":
        commit_msg = user_input[len(user_input.split()[0]):].strip()
        diff_text = get_git_diff()
        if not diff_text or "No hay diferencias" in diff_text:
            console.print("[yellow]No hay modificaciones pendientes de commitear en el proyecto.[/yellow]")
            return True

        if not commit_msg:
            commit_msg = f"feat(agent): autonomous update in {Path.cwd().name}"

        subprocess.run(["git", "add", "-A"], capture_output=True)
        res = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            console.print(f"[bold green]✅ Commit realizado:[/] {commit_msg}")
        else:
            console.print(f"[bold red]Error en commit:[/] {res.stderr.strip() or res.stdout.strip()}")
        return True

    # Exportar sesión completa a Markdown
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
        return True

    # Inspeccionar diff de Git actual
    elif cmd == "/diff":
        diff = get_git_diff()
        console.print(Panel(Syntax(diff, "diff", theme="monokai", line_numbers=True), title="Git Diff Actual", box=box.ROUNDED))
        return True

    # Ver estado del agente y métricas VRAM
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
        return True

    # Listar historial de sesiones
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
        return True

    # Reanudar sesión previa por session_id
    elif cmd == "/resume":
        target_id = user_input[len(user_input.split()[0]):].strip()
        if not target_id:
            console.print("[bold red]Uso:[/] /resume <session_id>")
            return True
        sm = SessionManager()
        past_msgs = sm.get_session_messages(target_id)
        if not past_msgs:
            console.print(f"[bold red]Error:[/] No se encontraron mensajes para la sesión '{target_id}'.")
        else:
            orchestrator.session_id = target_id
            orchestrator.memory.messages = past_msgs
            console.print(f"[bold green]✅ Sesión '{target_id}' reanudada con {len(past_msgs)} mensajes cargados en contexto.[/bold green]")
        return True

    # Telemetría y estadísticas de rendimiento
    elif cmd == "/telemetry":
        tlog = TelemetryLogger()
        summary = tlog.get_summary()
        failures = summary.get("tool_failures", 0)
        failure_rate = summary.get("tool_failure_rate_percent", summary.get("tool_failure_rate", 0.0))
        telem_text = f"""[bold]Turnos Totales de Agente:[/] {summary.get('total_turns', 0)}
[bold]Llamadas a Herramientas:[/] {summary.get('total_tool_calls', 0)}
[bold]Fallos / Reintentos de Herramientas:[/] {failures} ({failure_rate}%)
[bold]Duración Promedio por Turno:[/] {summary.get('average_turn_duration_seconds', 0.0)}s"""
        console.print(Panel(telem_text, title="📈 Telemetría y Rendimiento de AETHER", border_style="magenta", box=box.ROUNDED))
        return True

    # Explorador de Artefactos persistentes
    elif cmd in ["/artifacts", "/artifact"]:
        from agent.artifacts import ArtifactManager
        mgr = ArtifactManager(session_id=getattr(orchestrator, "session_id", "default"))
        args = user_input[len(user_input.split()[0]):].strip().split()
        if args and args[0] == "read" and len(args) > 1:
            art_id = args[1]
            try:
                data = mgr.read_artifact(art_id)
                meta = data.get("metadata", {})
                console.print(Panel(Markdown(data["content"]), title=f"[bold cyan]📄 {meta.get('title', art_id)} (v{meta.get('version', 1)})[/bold cyan]", border_style="cyan", box=box.ROUNDED))
            except Exception as e:
                console.print(f"[bold red]Error leyendo artefacto:[/] {e}")
            return True

        items = mgr.list_artifacts()
        if not items:
            console.print("[dim]ℹ️ No hay artefactos generados en este proyecto aún.[/dim]")
            return True

        table = Table(title="📚 Catálogo de Artefactos de AETHER", box=box.ROUNDED, border_style="cyan")
        table.add_column("ID de Artefacto", style="bold cyan")
        table.add_column("Título", style="bold white")
        table.add_column("Versión", justify="center", style="magenta")
        table.add_column("User Facing", justify="center")
        table.add_column("Feedback", justify="center")
        table.add_column("Resumen", style="dim")

        for it in items:
            uf = "✅" if it.get("user_facing") else "❌"
            fb = "⏳ Pendiente" if it.get("request_feedback") else "—"
            table.add_row(
                it.get("artifact_id", ""),
                it.get("title", ""),
                f"v{it.get('version', 1)}",
                uf,
                fb,
                it.get("summary", "")[:50] + ("..." if len(it.get("summary", "")) > 50 else ""),
            )
        console.print(table)
        console.print("[dim]Tip: Usa '/artifacts read <id>' para ver el contenido completo de un artefacto.[/dim]")
        return True

    # Catálogo y gestión de Habilidades Especializadas (Skills Runtime)
    elif cmd in ["/skills", "/skill"]:
        from agent.skills import get_global_skill_registry
        reg = get_global_skill_registry()
        args = user_input[len(user_input.split()[0]):].strip().split()

        if args and args[0] == "reload":
            reg.reload_skills()
            console.print(f"[bold green]✓ Skills recargadas exitosamente ({len(reg.skills)} registradas).[/bold green]")
            return True

        if args and args[0] in ["info", "show", "read"] and len(args) > 1:
            sk_name = args[1]
            sk = reg.get_skill(sk_name)
            if not sk:
                console.print(f"[bold red]Habilidad '{sk_name}' no encontrada.[/bold red]")
            else:
                loc = str(sk.skill_file) if sk.skill_file else "Nativa"
                console.print(Panel(
                    Markdown(f"**Ubicación:** `{loc}`\n\n**Disparadores:** `{', '.join(sk.triggers)}`\n\n---\n\n{sk.instructions}"),
                    title=f"[bold green]🛠️ Skill: {sk.name.upper()}[/bold green]",
                    border_style="green",
                    box=box.ROUNDED,
                ))
            return True

        table = Table(title="🛠️ Habilidades Disponibles de AETHER (Skills)", box=box.ROUNDED, border_style="green")
        table.add_column("Habilidad", style="bold green")
        table.add_column("Tipo", justify="center", style="cyan")
        table.add_column("Disparadores / Triggers", style="magenta")
        table.add_column("Descripción", style="white")

        table.add_row("code-review", "Nativa", "review, audit, code_review", "Auditoría estática de calidad, complejidad y docstrings.")
        table.add_row("test-scaffold", "Nativa", "test_gen, scaffold_tests", "Generador de tests unitarios automáticos con pytest.")
        table.add_row("dependency-audit", "Nativa", "dependencies, deps", "Análisis de grafo de dependencias e importaciones.")

        for sk in sorted(reg.skills.values(), key=lambda s: s.name):
            if sk.name not in ["code-review", "test-scaffold", "dependency-audit"]:
                table.add_row(
                    sk.name,
                    "Dinámica",
                    ", ".join(sk.triggers),
                    sk.description[:60] + ("..." if len(sk.description) > 60 else "")
                )
        console.print(table)
        console.print("[dim]Tip: Usa '/skills reload' para reescanear o '/skills info <nombre>' para ver detalles.[/dim]")
        return True

    # Directorio y gestión de Subagentes jerárquicos
    elif cmd in ["/subagents", "/subagent"]:
        from agent.subagents import get_global_subagent_manager
        mgr = get_global_subagent_manager()
        args = user_input[len(user_input.split()[0]):].strip().split()

        if args and args[0] in ["kill", "terminate"] and len(args) > 1:
            res = mgr.manage_subagents(action="kill", conversation_ids=[args[1]])
            console.print(f"[bold yellow]{res}[/bold yellow]")
            return True

        if args and args[0] in ["status", "info"] and len(args) > 1:
            res = mgr.manage_subagents(action="status", conversation_ids=[args[1]])
            console.print(Panel(Markdown(res), title=f"[bold cyan]🤖 Estado Subagente: {args[1]}[/bold cyan]", border_style="cyan", box=box.ROUNDED))
            return True

        res = mgr.manage_subagents(action="list")
        console.print(Panel(Markdown(res), title="🤖 Directorio de Subagentes", border_style="cyan", box=box.ROUNDED))
        console.print("[dim]Tip: Usa '/subagents status <id>' para ver su buzón o '/subagents kill <id>' para terminarlo.[/dim]")
        return True

    # Deshacer cambios al checkpoint anterior
    elif cmd == "/undo":
        res = undo_checkpoint()
        console.print(f"[bold yellow]{res}[/bold yellow]")
        return True

    # Crear punto de restauración inmediato
    elif cmd in ["/checkpoint", "/checkpoints"]:
        msg = user_input[len(user_input.split()[0]):].strip() or "Manual checkpoint"
        res = create_checkpoint(msg)
        console.print(f"[bold green]{res}[/bold green]")
        return True

    # Cambiar o consultar modelo de Ollama en caliente
    elif cmd in ["/model", "/models"]:
        parts = user_input.split()
        if len(parts) > 1:
            new_model = parts[1]
            orchestrator.model = new_model
            console.print(f"[bold green]Modelo cambiado a: {new_model}[/bold green]")
        else:
            console.print(f"[bold yellow]Modelo actual: {orchestrator.model}[/bold yellow]")
        return True

    # Cambiar modo operativo (agent, ask, plan, review)
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
        return True

    # Diseñar o consultar plan arquitectónico
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
        return True

    # Instrucciones de integración con Asistente de Voz
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
        return True

    # Limpiar historial de sesión
    elif cmd == "/clear":
        orchestrator.memory.clear()
        console.print("[bold cyan]Historial y contexto reiniciados.[/bold cyan]")
        return True

    # Compactar contexto y memoria
    elif cmd == "/compact":
        tokens_before = orchestrator.memory.estimate_tokens()
        orchestrator.memory.compact_memory()
        tokens_after = orchestrator.memory.estimate_tokens()
        saved = max(0, tokens_before - tokens_after)
        console.print(f"[bold green]✅ Contexto compactado exitosamente:[/] {tokens_before} ➔ {tokens_after} tokens (~{saved} tokens liberados en VRAM).")
        return True

    # Consultar o buscar hechos en memoria semántica
    elif cmd in ["/memory", "/memories"]:
        mem_arg = user_input[len(user_input.split()[0]):].strip()
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
        return True

    # Tabla de ayuda con todos los comandos
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
        return True

    # Comando de barra no reconocido
    console.print(f"[bold red]❌ Comando no reconocido:[/] '{cmd}'. Escribe [bold cyan]/help[/bold cyan] para ver la lista de comandos disponibles.")
    return True
