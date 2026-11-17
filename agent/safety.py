"""
Módulo de seguridad para el Agente.
Previene la ejecución involuntaria de comandos destructivos o accesos fuera del workspace.
"""

import re
from pathlib import Path
from typing import Tuple

# Patrones de comandos de alto riesgo que requieren confirmación o bloqueo
DANGEROUS_PATTERNS = [
    r"\brm\s+-[rf]{1,2}",
    r"\bdel\s+/[sfq]",
    r"\brmdir\s+/[sq]",
    r"\bformat(\s+[a-z]:)?",
    r"\bdiskpart\b",
    r"\bdrop\s+database\b",
    r"\bdrop\s+table\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[fdx]{1,3}",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\btaskkill\s+/f\s+/im\s+explorer\.exe",
]


def check_command_safety(command: str) -> Tuple[bool, str]:
    """
    Verifica si un comando es potencialmente destructivo.
    Retorna (es_seguro: bool, motivo: str).
    """
    cmd_lower = command.strip().lower()

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return False, f"El comando coincide con un patrón potencialmente peligroso: '{pattern}'"

    return True, "Comando seguro."


def is_path_safe(path: str, base_dir: Path) -> bool:
    """
    Verifica que la ruta no intente escapar de la raíz del proyecto.
    """
    try:
        resolved = (base_dir / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        # Verificar que resolved comience con base_dir
        return resolved == base_dir or base_dir in resolved.parents
    except Exception:
        return False
