"""
Herramientas de control de versiones con Git para checkpoints y rollback instantáneo.
Garantiza que cualquier modificación del agente pueda deshacerse con total seguridad.
"""

import subprocess
from pathlib import Path
from typing import Optional


def _run_git(args: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    work_dir = str(cwd.resolve() if cwd else Path.cwd())
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except FileNotFoundError:
        return 1, "", "Git no está instalado o no se encuentra en el PATH del sistema."
    except Exception as e:
        return 1, "", str(e)


def is_git_repo(path: Optional[Path] = None) -> bool:
    code, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"], path)
    return code == 0 and out == "true"


def init_repo_if_needed(path: Optional[Path] = None) -> str:
    """Inicializa un repositorio Git si la carpeta actual no lo es."""
    if not is_git_repo(path):
        code, out, err = _run_git(["init"], path)
        if code != 0:
            return f"Error al inicializar Git: {err}"
        return "Repositorio Git inicializado correctamente."
    return "Ya es un repositorio Git."


def create_checkpoint(message: str = "agent-checkpoint") -> str:
    """
    Crea un commit temporal o snapshot que guarda el estado exacto del proyecto.
    Permite restaurar con 'undo_checkpoint'.
    """
    if not is_git_repo():
        init_repo_if_needed()

    # Añadir todos los archivos modificados
    code_add, _, err_add = _run_git(["add", "-A"])
    if code_add != 0:
        return f"Error al añadir archivos al checkpoint: {err_add}"

    # Comprobar si hay cambios para commitear
    code_status, out_status, _ = _run_git(["status", "--porcelain"])
    if not out_status:
        return "Checkpoint: No hay cambios pendientes de guardar (árbol de trabajo limpio)."

    # Crear commit con mensaje
    code_commit, out_commit, err_commit = _run_git(["commit", "-m", f"[AETHER CHECKPOINT] {message}"])
    if code_commit != 0:
        return f"Error al generar commit de checkpoint: {err_commit}"

    return f"Éxito: Checkpoint guardado. ({out_commit.splitlines()[0] if out_commit else 'Listo'})"


def undo_checkpoint() -> str:
    """
    Revierte el último checkpoint o descarta todos los cambios no guardados.
    """
    if not is_git_repo():
        return "Error: No es un repositorio Git activo."

    # Comprobar si hay commits en el repositorio
    code_log, _, _ = _run_git(["rev-parse", "HEAD"])
    if code_log != 0:
        # Aún no hay commits, solo descartar cambios en el working tree
        _run_git(["clean", "-fd"])
        return "Éxito: Se descartaron todos los archivos no rastreados (repositorio inicial)."

    # Revertir cambios de working tree y retroceder 1 commit si era un checkpoint del agente
    code_reset, out_reset, err_reset = _run_git(["reset", "--hard", "HEAD~1"])
    if code_reset == 0:
        return "Éxito: Se ha revertido el último checkpoint. El proyecto volvió al estado anterior."
    else:
        # Si no se puede hacer HEAD~1 (ej. solo hay 1 commit), limpiar el working tree al HEAD actual
        _run_git(["reset", "--hard", "HEAD"])
        _run_git(["clean", "-fd"])
        return "Éxito: Se descartaron todas las modificaciones no commiteadas volviendo a HEAD."


def get_git_diff() -> str:
    """
    Retorna el diff coloreable de todas las modificaciones actuales sin commitear.
    """
    if not is_git_repo():
        return "Aviso: El directorio actual no es un repositorio Git."

    code, out, err = _run_git(["diff", "HEAD"])
    if code != 0 or not out:
        # Probar diff sin HEAD (cambios en working tree frente a index)
        _, out_unstaged, _ = _run_git(["diff"])
        if out_unstaged:
            return out_unstaged
        return "No hay diferencias de código pendientes (árbol limpio)."

    max_chars = 3500
    if len(out) > max_chars:
        return out[:max_chars] + f"\n... [Diff truncado: {len(out) - max_chars} caracteres adicionales]"
    return out


def get_git_status() -> str:
    """Retorna el estado de los archivos en Git."""
    if not is_git_repo():
        return "No es un repositorio Git."
    _, out, _ = _run_git(["status", "-s"])
    return out if out else "Árbol de trabajo completamente limpio."

