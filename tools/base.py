"""
Modelos base y tipos estructurados para las herramientas del Agente AETHER.
Compatible con Pydantic v2 y Ollama / OpenAI tool calling schema.
"""

from enum import Enum
import json
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ToolCategory(str, Enum):
    FILESYSTEM = "filesystem"
    CODE_INTELLIGENCE = "code_intelligence"
    EXECUTION = "execution"
    GIT = "git"
    AGENT_MANAGEMENT = "agent_management"


DEFAULT_IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "dist",
    "build", "egg-info", "target", ".aether", "site-packages",
    "e2e_sandbox"
}

DEFAULT_IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib",
    ".bin", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".lock"
}


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    COMMAND_EXECUTE = "command_execute"
    ADMIN_DESTRUCTIVE = "admin_destructive"


class ToolResult(BaseModel):
    """Resultado estructurado retornado por cualquier herramienta de AETHER."""
    success: bool = True
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_agent_string(self) -> str:
        """Formatea el resultado de forma concisa y clara para el contexto del LLM."""
        if not self.success:
            err_msg = self.error or "Error desconocido"
            return f"❌ Fallo (Código {self.exit_code}): {err_msg}\n{self.output}".strip()

        if not self.output:
            return "✅ Operación completada con éxito (sin salida)."

        return self.output.strip()

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
