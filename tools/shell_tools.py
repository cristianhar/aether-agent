"""
Herramienta de ejecución de comandos de terminal de forma controlada.
Captura stdout, stderr y código de salida con límite de tiempo de seguridad.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


def run_command(command: str, cwd: Optional[str] = None, timeout: int = 45) -> str:
    """
    Ejecuta un comando en la shell del sistema (PowerShell en Windows / Bash en POSIX)
    con control estricto de timeout y límites de salida para proteger el contexto del LLM.
    """
    work_dir = Path(cwd).resolve() if cwd else Path.cwd()
    if not work_dir.exists():
        return f"Error: El directorio de trabajo especificado '{cwd}' no existe."

    try:
        if os.name == "nt":
            args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
            process = subprocess.run(
                args,
                cwd=str(work_dir),
                shell=False,
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

        return "\n".join(result)

    except subprocess.TimeoutExpired:
        return f"Error: El comando excedió el tiempo límite de ejecución ({timeout} segundos)."
    except Exception as e:
        return f"Error inesperado al ejecutar el comando '{command}': {str(e)}"
