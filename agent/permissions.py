"""
Motor de permisos basado en capacidades y jaula de workspace para AETHER IDE.
Controla y audita el acceso a archivos, comandos y recursos del sistema operativo.
"""

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
from typing import Callable, List, Optional, Set

from tools.base import PermissionLevel, ToolCategory


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK_USER = "ask_user"


@dataclass
class PermissionRequest:
    tool_name: str
    category: ToolCategory
    level: PermissionLevel
    target_path: Optional[str] = None
    command: Optional[str] = None
    justification: str = ""


class PermissionEngine:
    """
    Controlador central de seguridad y permisos de AETHER.
    Garantiza que el agente no destruya archivos fuera del workspace ni ejecute comandos catastróficos.
    """

    DANGEROUS_PATTERNS = [
        r"\bformat\s+[a-zA-Z]:",
        r"\bdel\b.*[a-zA-Z]:\\",
        r"\brmdir\b.*[a-zA-Z]:\\",
        r"\brm\s+-rf\s+/(?:\s|$)",
        r"\bdd\s+if=.*of=/dev/sd",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",  # Fork bomb
        r"\bshutdown\s+[/|-][sSrR]",
    ]

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        approval_callback: Optional[Callable[[PermissionRequest], bool]] = None,
        enforce_workspace_jail: bool = True,
    ):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.approval_callback = approval_callback
        self.enforce_workspace_jail = enforce_workspace_jail
        self.allowed_directories: Set[Path] = {self.workspace_root}
        self._auto_approved_categories: Set[PermissionLevel] = {PermissionLevel.READ_ONLY}

    def add_allowed_directory(self, directory: Path | str) -> None:
        """Agrega un directorio explícito permitido fuera del workspace principal."""
        resolved = Path(directory).resolve()
        self.allowed_directories.add(resolved)

    def set_auto_approve(self, level: PermissionLevel, allowed: bool = True) -> None:
        """Configura si un nivel de permiso se auto-aprueba en modo autónomo."""
        if allowed:
            self._auto_approved_categories.add(level)
        else:
            self._auto_approved_categories.discard(level)

    def is_path_within_boundaries(self, target_path: str | Path) -> bool:
        """Verifica si la ruta solicitada está dentro del workspace o de rutas permitidas."""
        if not self.enforce_workspace_jail:
            return True

        try:
            # Expandir variables de entorno y tildes
            expanded = os.path.expandvars(os.path.expanduser(str(target_path)))
            resolved = Path(expanded).resolve()

            for allowed in self.allowed_directories:
                try:
                    resolved.relative_to(allowed)
                    return True
                except ValueError:
                    continue
            return False
        except Exception:
            return False

    def is_command_safe(self, command: str) -> tuple[bool, Optional[str]]:
        """Analiza si un comando contiene patrones destructivos o no permitidos."""
        clean_cmd = command.strip().lower()

        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                return False, f"Comando bloqueado por regla de seguridad: patrón destructivo '{pattern}'"

        return True, None

    def evaluate(self, request: PermissionRequest) -> tuple[PermissionDecision, Optional[str]]:
        """
        Evalúa una solicitud de acción del agente y retorna la decisión.
        """
        # 1. Validación de ruta (Jail) si aplica
        if request.target_path and request.category in [ToolCategory.FILESYSTEM, ToolCategory.GIT]:
            if not self.is_path_within_boundaries(request.target_path):
                # Si es solo lectura, se puede permitir con advertencia o bloquear si es write
                if request.level in [PermissionLevel.WORKSPACE_WRITE, PermissionLevel.ADMIN_DESTRUCTIVE]:
                    return (
                        PermissionDecision.DENY,
                        f"Violación de límites de workspace: La ruta '{request.target_path}' está fuera de '{self.workspace_root}'.",
                    )

        # 2. Validación de comandos de consola
        if request.command and request.category == ToolCategory.EXECUTION:
            is_safe, reason = self.is_command_safe(request.command)
            if not is_safe:
                return PermissionDecision.DENY, reason

        # 3. Niveles destructivos siempre requieren confirmación
        if request.level == PermissionLevel.ADMIN_DESTRUCTIVE:
            if self.approval_callback:
                approved = self.approval_callback(request)
                if approved:
                    return PermissionDecision.ALLOW, None
                return PermissionDecision.DENY, "Operación destructiva denegada por el usuario."
            return PermissionDecision.ASK_USER, "Operación destructiva requiere aprobación explícita."

        # 4. Chequeo de nivel auto-aprobado
        if request.level in self._auto_approved_categories:
            return PermissionDecision.ALLOW, None

        # 5. Si hay callback de aprobación y el nivel no es auto-aprobado (ej. ASK mode)
        if self.approval_callback:
            if self.approval_callback(request):
                return PermissionDecision.ALLOW, None
            return PermissionDecision.DENY, "Acción denegada por el usuario."

        # Por defecto, workspace write y command execute se permiten en modo autónomo estándar si pasaron los filtros
        return PermissionDecision.ALLOW, None
