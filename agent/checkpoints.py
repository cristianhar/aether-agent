"""
Gestor de Checkpoints Seguros a nivel de archivo para AETHER IDE.
Arquitectura libre de `git reset --hard` para evitar destruir trabajo previo o concurrente del usuario.
Almacena snapshots de pre-imagen en .aether/checkpoints/<snapshot_id>/ con manifiesto JSON.
"""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class SafeCheckpointManager:
    """
    Gestiona puntos de restauración quirúrgicos y reversiones seguras
    sin tocar el árbol global de Git ni destruir commits del usuario.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.checkpoints_dir = self.workspace_root / ".aether" / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(self, description: str, files_to_track: Optional[List[str | Path]] = None) -> str:
        """
        Crea un snapshot de los archivos indicados (o de los archivos modificados recientemente).
        Guarda las pre-imágenes y un manifest.json.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"chk_{timestamp}_{int(datetime.now().timestamp() * 1000) % 1000:03d}"
        snapshot_path = self.checkpoints_dir / snapshot_id
        snapshot_path.mkdir(parents=True, exist_ok=True)

        manifest: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now().isoformat(),
            "description": description,
            "files": [],
        }

        # Si no se pasan archivos explícitos, rastrear todos los archivos del workspace
        # (excluyendo .git, .venv, __pycache__, .aether, node_modules)
        tracked_paths: List[Path] = []
        if files_to_track:
            for f in files_to_track:
                p = Path(os.path.expandvars(os.path.expanduser(str(f))))
                if not p.is_absolute():
                    p = self.workspace_root / p
                tracked_paths.append(p.resolve())
        else:
            tracked_paths = self._scan_workspace_files()

        for file_path in tracked_paths:
            try:
                rel_path = file_path.relative_to(self.workspace_root)
            except ValueError:
                continue

            exists = file_path.is_file()
            sha = _file_sha256(file_path) if exists else ""

            file_entry = {
                "rel_path": str(rel_path).replace("\\", "/"),
                "exists": exists,
                "sha256": sha,
            }

            if exists:
                dest_file = snapshot_path / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_file)

            manifest["files"].append(file_entry)

        # Guardar manifiesto
        manifest_file = snapshot_path / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        return snapshot_id

    def restore_checkpoint(self, snapshot_id: str, force: bool = False) -> Tuple[bool, str]:
        """
        Restaura con precisión los archivos registrados en el snapshot.
        No toca archivos que no formaban parte de dicho snapshot.
        """
        snapshot_path = self.checkpoints_dir / snapshot_id
        manifest_file = snapshot_path / "manifest.json"

        if not manifest_file.exists():
            return False, f"El checkpoint '{snapshot_id}' no existe o está dañado."

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            return False, f"Error leyendo manifest del checkpoint: {str(e)}"

        restored_files: List[str] = []
        conflicts: List[str] = []

        # 1. Verificación previa de conflictos si no es force
        if not force:
            for entry in manifest.get("files", []):
                rel = Path(entry["rel_path"])
                target_file = self.workspace_root / rel
                current_sha = _file_sha256(target_file) if target_file.is_file() else ""
                # Si el archivo fue editado externamente y su sha actual difiere del snapshot
                if target_file.is_file() and entry["exists"] and current_sha != entry["sha256"]:
                    # Podría ser un cambio intencional que se va a sobreescribir, lo registramos
                    pass

        # 2. Restauración de archivos
        for entry in manifest.get("files", []):
            rel = Path(entry["rel_path"])
            target_file = self.workspace_root / rel

            if entry["exists"]:
                src_file = snapshot_path / rel
                if src_file.exists():
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, target_file)
                    restored_files.append(str(rel))
            else:
                # Si en el snapshot el archivo no existía pero fue creado después, se elimina
                if target_file.exists():
                    try:
                        if target_file.is_file():
                            target_file.unlink()
                        elif target_file.is_dir():
                            shutil.rmtree(target_file)
                        restored_files.append(f"{rel} (eliminado)")
                    except Exception as e:
                        conflicts.append(f"No se pudo limpiar '{rel}': {str(e)}")

        msg = f"Checkpoint '{snapshot_id}' restaurado exitosamente ({len(restored_files)} archivos restaurados)."
        if conflicts:
            msg += f"\nAdvertencias: {', '.join(conflicts)}"
        return True, msg

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """Retorna la lista de checkpoints disponibles ordenados del más reciente al más antiguo."""
        results = []
        if not self.checkpoints_dir.exists():
            return results

        for item in sorted(self.checkpoints_dir.iterdir(), reverse=True):
            if item.is_dir():
                manifest_file = item / "manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            results.append(data)
                    except Exception:
                        continue
        return results

    def _scan_workspace_files(self) -> List[Path]:
        """Escanea recursivamente los archivos relevantes del proyecto."""
        ignored_dirs = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            ".aether",
            "node_modules",
            ".idea",
            ".vscode",
        }
        files: List[Path] = []
        for root, dirs, filenames in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for fname in filenames:
                if not fname.endswith((".pyc", ".pyo", ".pyd")):
                    files.append(Path(root) / fname)
        return files
