"""
Motor de Artefactos Estructurados para AETHER IDE.
Gestiona documentos de alto nivel (planes de arquitectura, especificaciones,
reportes de pruebas, diagramas Mermaid) almacenados en .aether/artifacts/.
Incluye metadatos JSON (UserFacing, RequestFeedback, resumen y versionado).
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


@dataclass
class ArtifactMetadata:
    artifact_id: str
    title: str
    summary: str
    user_facing: bool = True
    request_feedback: bool = False
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    tags: List[str] = field(default_factory=list)


def _slugify(text: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", clean)[:40] or "artifact"


_ACTIVE_ARTIFACT_SESSION: Optional[str] = None


def set_active_artifact_session(session_id: Optional[str]):
    """Establece la sesión activa en contexto para asociar los artefactos creados."""
    global _ACTIVE_ARTIFACT_SESSION
    _ACTIVE_ARTIFACT_SESSION = session_id


def get_active_artifact_session() -> str:
    """Obtiene el identificador de sesión activo para artefactos."""
    global _ACTIVE_ARTIFACT_SESSION
    return _ACTIVE_ARTIFACT_SESSION or "default"


class ArtifactManager:
    """
    Gestor central de artefactos persistentes de AETHER.
    Separa el contenido Markdown de los metadatos de visualización y control.
    """

    def __init__(self, workspace_root: Optional[Path] = None, session_id: Optional[str] = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.session_id = session_id or get_active_artifact_session()
        self.artifacts_dir = self.workspace_root / ".aether" / "artifacts" / self.session_id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create_artifact(
        self,
        title: str,
        content: str,
        summary: str,
        user_facing: bool = True,
        request_feedback: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Crea un nuevo artefacto persistente y almacena sus metadatos asociados."""
        timestamp = datetime.now().isoformat()
        slug = _slugify(title)
        artifact_id = f"{slug}_{int(datetime.now().timestamp())}"

        doc_path = self.artifacts_dir / f"{artifact_id}.md"
        meta_path = self.artifacts_dir / f"{artifact_id}.meta.json"

        meta = ArtifactMetadata(
            artifact_id=artifact_id,
            title=title,
            summary=summary,
            user_facing=user_facing,
            request_feedback=request_feedback,
            created_at=timestamp,
            updated_at=timestamp,
            version=1,
            tags=tags or [],
        )

        doc_path.write_text(content, encoding="utf-8")
        meta_path.write_text(json.dumps(asdict(meta), indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_id": artifact_id,
            "title": title,
            "path": str(doc_path.relative_to(self.workspace_root)).replace("\\", "/"),
            "user_facing": user_facing,
            "request_feedback": request_feedback,
            "version": 1,
        }

    def update_artifact(
        self,
        artifact_id: str,
        content: str,
        summary: Optional[str] = None,
        request_feedback: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Actualiza el contenido de un artefacto existente incrementando su versión."""
        doc_path = self.artifacts_dir / f"{artifact_id}.md"
        meta_path = self.artifacts_dir / f"{artifact_id}.meta.json"

        if not doc_path.exists() or not meta_path.exists():
            # Buscar en todo el árbol de artefactos por si pertenece a otra sesión
            candidates = list((self.workspace_root / ".aether" / "artifacts").glob(f"**/{artifact_id}.md"))
            if not candidates:
                raise FileNotFoundError(f"Artefacto con ID '{artifact_id}' no encontrado.")
            doc_path = candidates[0]
            meta_path = doc_path.with_suffix(".meta.json")

        meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_data["version"] = meta_data.get("version", 1) + 1
        meta_data["updated_at"] = datetime.now().isoformat()
        if summary:
            meta_data["summary"] = summary
        if request_feedback is not None:
            meta_data["request_feedback"] = request_feedback

        doc_path.write_text(content, encoding="utf-8")
        meta_path.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_id": artifact_id,
            "title": meta_data.get("title", ""),
            "version": meta_data["version"],
            "summary": meta_data.get("summary", ""),
            "updated_at": meta_data["updated_at"],
        }

    def read_artifact(self, artifact_id: str) -> Dict[str, Any]:
        """Lee el contenido y metadatos de un artefacto."""
        doc_path = self.artifacts_dir / f"{artifact_id}.md"
        meta_path = self.artifacts_dir / f"{artifact_id}.meta.json"

        if not doc_path.exists():
            candidates = list((self.workspace_root / ".aether" / "artifacts").glob(f"**/{artifact_id}.md"))
            if not candidates:
                raise FileNotFoundError(f"Artefacto '{artifact_id}' no encontrado.")
            doc_path = candidates[0]
            meta_path = doc_path.with_suffix(".meta.json")

        content = doc_path.read_text(encoding="utf-8")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

        return {
            "artifact_id": artifact_id,
            "content": content,
            "metadata": meta,
        }

    def list_artifacts(self) -> List[Dict[str, Any]]:
        """Lista todos los artefactos disponibles ordenados cronológicamente."""
        results = []
        base = self.workspace_root / ".aether" / "artifacts"
        if not base.exists():
            return results

        meta_files = list(base.glob("**/*.meta.json"))
        for mf in meta_files:
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                doc_path = mf.with_suffix(".md")
                data["has_content"] = doc_path.exists()
                results.append(data)
            except Exception:
                continue

        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results
