"""
Herramienta de ejecución de comandos de terminal de forma controlada.
Captura stdout, stderr y código de salida con límite de tiempo de seguridad.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


def _generate_shell_diagnostics(command: str, work_dir: Path, exit_code: int, stdout: str, stderr: str) -> Optional[str]:
    """Genera sugerencias y diagnósticos contextuales cuando un comando de consola falla."""
    if exit_code == 0:
        return None

    combined = f"{stdout}\n{stderr}".lower()
    hints = []

    # 1. Detección de proyecto en subcarpeta (ej: npm install en root cuando package.json está en un subproyecto)
    if ("enoent" in combined or "no such file or directory" in combined) and ("package.json" in combined or "npm" in command.lower()):
        try:
            sub_pkgs = list(work_dir.glob("*/package.json"))
            if sub_pkgs:
                sub_dirs = [p.parent.name for p in sub_pkgs if p.parent.name != "node_modules"][:3]
                if sub_dirs:
                    hints.append(
                        f"💡 [DIAGNÓSTICO AUTOMÁTICO DE TERMINAL]: No se encontró 'package.json' en '{work_dir.name}'. "
                        f"Sin embargo, se detectó en los subdirectorios: {sub_dirs}. "
                        "Recuerda que cada llamada a 'run_command' inicia una subterminal independiente. "
                        f"Para ejecutar comandos allí, pasa el parámetro cwd='{sub_dirs[0]}' o encadena 'cd {sub_dirs[0]}; {command}'."
                    )
        except Exception:
            pass

    # 2. Detección de SyntaxError
    if "syntaxerror" in combined:
        hints.append(
            "🚨 [DIAGNÓSTICO DE SINTAXIS]: La ejecución falló con un SyntaxError. "
            "Está PROHIBIDO volver a ejecutar 'run_command' con este script sin antes corregir la sintaxis usando 'edit_file'."
        )

    # 3. Detección de archivo Python inexistente en CWD pero existente en subcarpeta
    if ("can't open file" in combined or "no such file" in combined) and "python" in command.lower():
        try:
            parts = command.split()
            for p in parts:
                if p.endswith(".py"):
                    script_name = Path(p).name
                    matches = list(work_dir.glob(f"**/{script_name}"))
                    matches = [m for m in matches if ".venv" not in str(m) and "__pycache__" not in str(m)]
                    if matches:
                        rel_p = matches[0].relative_to(work_dir)
                        hints.append(
                            f"💡 [DIAGNÓSTICO DE RUTA]: El archivo '{p}' no existe en la raíz actual. "
                            f"Fue localizado en '{rel_p}'. Ejecuta con 'python {rel_p}' o pasa cwd='{rel_p.parent}'."
                        )
                    break
        except Exception:
            pass

    return "\n\n".join(hints) if hints else None


def run_command(command: str, cwd: Optional[str] = None, timeout: int = 45) -> str:
    """
    Ejecuta un comando en la shell del sistema (PowerShell en Windows / Bash en POSIX)
    con control estricto de timeout y límites de salida para proteger el contexto del LLM.
    """
    work_dir = Path(cwd).resolve() if cwd else Path.cwd()
    if not work_dir.exists():
        return f"Error: El directorio de trabajo especificado '{cwd}' no existe."

    try:
        normalized_command = command.strip()
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
