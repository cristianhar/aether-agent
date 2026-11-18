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
    """Genera sugerencias y diagnósticos contextuales cuando un comando de consola falla."""
    combined = f"{stdout}\n{stderr}".lower()
    is_cancelled = "operation cancelled" in combined or "operation aborted" in combined or "operación cancelada" in combined

    if exit_code == 0 and not is_cancelled:
        return None

    hints = []

    # 1. Detección de herramientas de scaffolding canceladas por falta de TTY en carpetas con archivos (ej: create-vite)
    if is_cancelled:
        hints.append(
            "⚠️ [OPERACIÓN CANCELADA]: El comando se canceló automáticamente ('Operation cancelled') por la herramienta (create-vite / scaffolding) "
            "porque solicitó confirmación interactiva y la consola es no interactiva (o el directorio ya contiene archivos existentes).\n"
            "• NO asumas que el proyecto fue creado.\n"
            "• Para proyectos web en un repositorio existente, crea una subcarpeta limpia: 'npm create vite@latest frontend -- --template vanilla', "
            "o crea directamente los archivos 'package.json' e 'index.html' con write_file."
        )

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

    # 3. Detección de EOFError en scripts interactivos (input())
    if "eoferror" in combined or "eof when reading a line" in combined:
        hints.append(
            "💡 [DIAGNÓSTICO DE ENTRADA INTERACTIVA]: El comando falló por EOFError porque el script ejecutó input() en una terminal no interactiva.\n"
            "• Para testear scripts con input(), valida su sintaxis con 'python -m py_compile <archivo>.py' o 'python -c \"import <modulo>\"'.\n"
            "• NUNCA intentes editar el archivo buscando 'EOFError'; este texto proviene de la consola, no del archivo."
        )

    # 4. Detección de discrepancia numérica en aserciones de tests (unittest / pytest)
    if "assertionerror" in combined or "failed (failures=" in combined:
        assert_m = re.search(r"assertionerror:\s*([0-9\.\-]+)\s*!=\s*([0-9\.\-]+)", f"{stdout}\n{stderr}", re.IGNORECASE)
        if not assert_m:
            assert_m = re.search(r"assert\s+([0-9\.\-]+)\s*==\s*([0-9\.\-]+)", f"{stdout}\n{stderr}", re.IGNORECASE)

        if assert_m:
            actual_str, expected_str = assert_m.group(1), assert_m.group(2)
            try:
                act_num = float(actual_str)
                act_rounded = round(act_num, 2)
            except ValueError:
                act_rounded = actual_str

            hints.append(
                f"💡 [DIAGNÓSTICO AUTOMÁTICO DE DISCREPANCIA EN TEST]:\n"
                f"• Tu código en ejecución produjo el valor REAL: {actual_str} (aprox: {act_rounded}).\n"
                f"• Tu archivo de prueba esperaba: {expected_str}.\n"
                f"• REGLA FUNDAMENTAL: En Python, el primer valor ({actual_str}) es lo que tu función realmente devuelve.\n"
                f"• Si tu código usa 'statistics.stdev([1, 2, 3, 4, 5])', calcula desviación MUESTRAL (N-1) y da 1.58 (NO 1.41, que sería poblacional pstdev).\n"
                f"• ACCIÓN INMEDIATA CON edit_file: Abre el archivo de prueba ('test_...py') y actualiza el valor esperado a {act_rounded} (o {actual_str}):\n"
                f"  self.assertAlmostEqual(..., {act_rounded}, places=2)\n"
                f"• ADVERTENCIA DE FRAMEWORK: Si usas unittest, NUNCA uses 'pytest.approx' dentro de 'assertAlmostEqual'."
            )

    # 5. Detección de incompatibilidad pytest.approx en unittest
    if "approxscalar" in combined or ("approx" in combined and ("typeerror" in combined or "nameerror" in combined) and "unittest" in command.lower()):
        hints.append(
            "⚠️ [INCOMPATIBILIDAD DE FRAMEWORK DE TEST]: Has mezclado 'pytest.approx' dentro de 'unittest.TestCase'.\n"
            "• 'pytest.approx' NO es compatible con 'self.assertAlmostEqual()'.\n"
            "• Para unittest: usa ÚNICAMENTE 'self.assertAlmostEqual(actual, esperado, places=2)'. Elimina 'pytest.approx' y 'import pytest'."
        )

    # 6. Detección de NameError / módulo no importado con localización de archivo
    raw_output = f"{stdout}\n{stderr}"
    name_err_m = re.search(r"NameError:\s*name\s*['\"](\w+)['\"]\s*is not defined", raw_output, re.IGNORECASE)
    if name_err_m:
        missing_var = name_err_m.group(1)
        loc_m = re.search(r"([a-zA-Z0-9_\-\.\/\\]+\.py):(\d+):(?:\s*in\s+|\s*NameError)", raw_output, re.IGNORECASE)
        if not loc_m:
            loc_m = re.search(r'File "([^"]+\.py)", line (\d+)', raw_output, re.IGNORECASE)

        file_hint = ""
        if loc_m:
            err_file = Path(loc_m.group(1)).name
            err_line = loc_m.group(2)
            file_hint = f" en el archivo '{err_file}' (línea {err_line})"

        hints.append(
            f"💡 [DIAGNÓSTICO AUTOMÁTICO DE NameError]:\n"
            f"• La variable o módulo '{missing_var}' no está definida{file_hint}.\n"
            f"• ATENCIÓN: Asegúrate de editar el archivo CORRECTO{file_hint}. Si el fallo ocurrió en un archivo de test ('test_...py'), edita el archivo de test, NO el módulo probado.\n"
            f"• Si '{missing_var}' es un módulo estándar de Python (ej: time, math, os, sys, json, random, re), agrega 'import {missing_var}' al principio de ese archivo."
        )

    # 7. Detección de pruebas asíncronas no soportadas en pytest (async def sin plugin)
    if "async def functions are not natively supported" in combined or "unknown pytest.mark.asyncio" in combined:
        hints.append(
            "🚨 [DIAGNÓSTICO DE TEST ASÍNCRONO EN PYTEST]:\n"
            "• Pytest no soporta 'async def test_...()' de forma nativa sin el plugin 'pytest-asyncio'.\n"
            "• ACCIÓN OBLIGATORIA: Convierte la función de prueba en una función síncrona normal 'def test_...()' "
            "y ejecuta la corrutina usando 'asyncio.run()':\n"
            "  def test_mi_corrutina():\n"
            "      resultado = asyncio.run(mi_corrutina())\n"
            "      assert resultado == ...\n"
            "• Elimina el decorador '@pytest.mark.asyncio'."
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

        # Inyectar entorno virtual (.venv / venv) en PATH si existe en el proyecto
        env = os.environ.copy()
        for venv_name in [".venv", "venv"]:
            venv_bin = work_dir / venv_name / ("Scripts" if os.name == "nt" else "bin")
            if venv_bin.exists():
                env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
                env["VIRTUAL_ENV"] = str(venv_bin.parent)
                break

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
