"""
Herramienta de ejecución de comandos de terminal de forma controlada.
Captura stdout, stderr y código de salida con límite de tiempo de seguridad.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


def _generate_shell_diagnostics(command: str, work_dir: Path, exit_code: int, stdout: str, stderr: str) -> Optional[str]:
    """
    Normalizador Universal de Trazas de Ejecución (Políglota: Python, Node/TS, Rust, Go, C/C++).
    Identifica de forma dinámica y sin hardcodeos de librerías:
    1. El archivo fuente culpable del fallo y su número de línea.
    2. La causa raíz / última línea del error.
    3. Una directiva limpia de acción sugerida.
    """
    raw_output = f"{stdout}\n{stderr}".strip()
    is_cancelled = "operation cancelled" in raw_output.lower() or "operation aborted" in raw_output.lower()

    if exit_code == 0 and not is_cancelled:
        return None

    lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if not lines and not is_cancelled:
        return None

    # 1. Localizar archivo y línea culpable (patrones estándar de compiladores e intérpretes)
    loc_pattern = r'(?:File "|\bat |-->\s*|\b)([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9_]+)[\'"]?(?:,\s*line\s*|:)(\d+)'

    culprit_file = None
    culprit_line = None

    for line in reversed(lines):
        m = re.search(loc_pattern, line)
        if m:
            candidate_file = m.group(1).replace("\\", "/")
            if not any(ignore in candidate_file.lower() for ignore in [".venv", "site-packages", "node_modules", "rustlib"]):
                culprit_file = Path(candidate_file).name
                culprit_line = m.group(2)
                break

    # 2. Localizar la causa raíz (última línea relevante de error)
    root_cause = lines[-1] if lines else "Error no especificado"
    for line in reversed(lines):
        if any(err_kw in line for err_kw in ["Error:", "Exception:", "FAILED", "error[", "panic:", "AssertionError", "SyntaxError"]):
            root_cause = line
            break

    if len(root_cause) > 200:
        root_cause = root_cause[:200] + "..."

    # 3. Construir banner contextual universal
    file_info = f"'{culprit_file}' (línea {culprit_line})" if culprit_file and culprit_line else ("en el proyecto" if culprit_file else "durante la ejecución")
    action_suggestion = f"Inspecciona {file_info} con 'read_file' y corrige el código fuente con 'edit_file' o 'write_file'." if culprit_file else "Analiza el error y modifica los archivos afectados antes de reintentar."

    banner = (
        f"🚨 [DIAGNÓSTICO UNIVERSAL DE EJECUCIÓN (Código de salida {exit_code})]:\n"
        f"• Comando: {command}\n"
        f"• Fallo detectado: {file_info}\n"
        f"• Causa raíz: {root_cause}\n"
        f"• ACCIÓN RECOMENDADA: {action_suggestion}"
    )

    structural_hints = []
    combined = raw_output.lower()
    if is_cancelled:
        tool_hint = f" ({lines[0]})" if lines and "cancelled" not in lines[0].lower() and len(lines[0]) < 60 else ""
        structural_hints.append(
            f"⚠️ [OPERACIÓN CANCELADA]: El comando{tool_hint} se canceló automáticamente ('Operation cancelled') "
            "porque solicitó confirmación interactiva en una consola no interactiva. Para scaffolding, pasa banderas no interactivas o crea los archivos con 'write_file'."
        )
    if ("enoent" in combined or "no such file or directory" in combined) and "package.json" in combined:
        try:
            sub_pkgs = list(work_dir.glob("*/package.json"))
            if sub_pkgs:
                sub_dirs = [p.parent.name for p in sub_pkgs if p.parent.name != "node_modules"][:3]
                if sub_dirs:
                    structural_hints.append(
                        f"💡 [DIAGNÓSTICO DE RUTA]: Se detectó 'package.json' en subdirectorios: {sub_dirs}. Pasa cwd='{sub_dirs[0]}' para ejecutar comandos allí."
                    )
        except Exception:
            pass

    # Detección universal de discrepancias en aserciones de tests (Python AssertionError, Node assert, Rust assertion)
    assert_m = re.search(r"(?:AssertionError|assert(?:ion)? failed|ERR_ASSERTION)[^\n\r:]*:?\s*([^\n\r!=]+?)\s*(?:!=|!==)\s*([^\n\r]+)", raw_output, re.IGNORECASE)
    if assert_m:
        val_actual = assert_m.group(1).strip()
        val_expected = assert_m.group(2).strip()
        if len(val_actual) < 80 and len(val_expected) < 80:
            structural_hints.append(
                f"💡 [DISCREPANCIA EN TEST DETECTADA]: La prueba falló porque el resultado obtenido fue '{val_actual}', pero se esperaba '{val_expected}'.\n"
                f"• Si el código de producción tiene un error de cálculo o lógica, corrígelo con 'edit_file' para que produzca '{val_expected}'.\n"
                f"• Si el cálculo de producción es el correcto y el test tenía una expectativa mal calculada, edita el archivo de pruebas con 'edit_file' para esperar '{val_actual}'."
            )

    all_parts = [banner] + structural_hints
    return "\n\n".join(all_parts)


def run_command(command: str, cwd: Optional[str] = None, timeout: int = 45) -> str:
    """
    Ejecuta un comando en la shell del sistema (PowerShell en Windows / Bash en POSIX)
    con control estricto de timeout y límites de salida para proteger el contexto del LLM.
    """
    work_dir = Path(cwd).resolve() if cwd else Path.cwd()
    if not work_dir.exists():
        return (
            f"Error: El directorio de trabajo especificado '{cwd}' no existe.\n"
            f"• El directorio de trabajo actual del proyecto es '{Path.cwd()}'.\n"
            "• Para ejecutar comandos en el proyecto actual, omite el argumento 'cwd' (o pasa cwd='.')."
        )

    try:
        normalized_command = command.strip()

        # Inyectar entorno virtual (.venv / venv) en PATH buscando en work_dir o hacia arriba en sus padres
        env = os.environ.copy()
        current_check = work_dir
        for _ in range(5):
            for venv_name in [".venv", "venv"]:
                venv_bin = current_check / venv_name / ("Scripts" if os.name == "nt" else "bin")
                if venv_bin.exists():
                    env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
                    env["VIRTUAL_ENV"] = str(venv_bin.parent)
                    break
            if "VIRTUAL_ENV" in env:
                break
            if current_check.parent == current_check:
                break
            current_check = current_check.parent

        if os.name == "nt":
            # Normalización inteligente de comandos Linux/POSIX hacia Windows
            if normalized_command.startswith("python3 "):
                normalized_command = "python " + normalized_command[8:]
            elif normalized_command.startswith("pip3 "):
                normalized_command = "pip " + normalized_command[5:]
            elif normalized_command == "python3":
                normalized_command = "python"
            elif normalized_command == "pip3":
                normalized_command = "pip"

            args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", normalized_command]
            process = subprocess.run(
                args,
                cwd=str(work_dir),
                env=env,
                shell=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
        else:
            process = subprocess.run(
                command,
                cwd=str(work_dir),
                env=env,
                shell=True,
                executable="/bin/bash" if Path("/bin/bash").exists() else None,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )

        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        exit_code = process.returncode

        # Limitar longitud de salida para no desbordar el contexto
        max_output_chars = 4000
        if len(stdout) > max_output_chars:
            stdout = stdout[:max_output_chars] + f"\n... [Salida truncada: {len(stdout) - max_output_chars} caracteres adicionales]"
        if len(stderr) > max_output_chars:
            stderr = stderr[:max_output_chars] + f"\n... [Error truncado: {len(stderr) - max_output_chars} caracteres adicionales]"

        # Si una herramienta CLI interactiva (como create-vite) se cancela automáticamente por falta de TTY,
        # forzar código de error para que el agente no crea falsamente que la operación tuvo éxito.
        combined_lower = f"{stdout}\n{stderr}".lower()
        if "operation cancelled" in combined_lower or "operation aborted" in combined_lower or "operación cancelada" in combined_lower:
            exit_code = 1

        result = [f"Código de salida: {exit_code}"]
        if stdout:
            result.append(f"--- STDOUT ---\n{stdout}")
        if stderr:
            result.append(f"--- STDERR ---\n{stderr}")
        if not stdout and not stderr:
            result.append("(El comando finalizó sin salida en consola)")

        diag = _generate_shell_diagnostics(normalized_command, work_dir, exit_code, stdout, stderr)
        if diag:
            result.append(f"\n{diag}")

        return "\n".join(result)

    except subprocess.TimeoutExpired:
        return f"Error: El comando excedió el tiempo límite de ejecución ({timeout} segundos)."
    except Exception as e:
        return f"Error inesperado al ejecutar el comando '{command}': {str(e)}"
