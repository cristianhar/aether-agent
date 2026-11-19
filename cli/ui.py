"""
Componentes de interfaz de usuario y renderizado para la consola AETHER.
Construido sobre 'rich' para proveer una experiencia visual de alta fidelidad.
"""

import re
from pathlib import Path
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()


def render_banner(model_name: str, ollama_ok: bool):
    """Renderiza el banner de bienvenida con estado de conexión y hardware."""
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
    """Renderiza el razonamiento interno o reflexiones del modelo en un panel colapsable."""
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


render_thought = handle_thought


def handle_tool_call(tool_name: str, args: dict):
    """Renderiza la invocación de herramientas del agente en la terminal."""
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
    """Renderiza los resultados o errores producidos por las herramientas."""
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
    """Renderiza la respuesta markdown generada por el agente con estilo terminal."""
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
