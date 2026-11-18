"""
Motor transaccional de parches y edición atómica para AETHER IDE.
Inspirado en el sistema de parches de Aider y Claude Code.
Soporta:
- Verificación de precondiciones (SHA-256 / Snippet pre-existente)
- Reemplazo atómico vía archivo temporal (.tmp + os.replace)
- Preservación de saltos de línea originales (CRLF vs LF)
- Transacciones multi-archivo con reversión (rollback) automática en caso de error
"""

import difflib
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Tuple


def compute_sha256(content: str) -> str:
    """Calcula el hash SHA-256 de una cadena de texto (normalizada a UTF-8)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def detect_line_ending(content: str) -> str:
    """Detecta si el archivo utiliza CRLF (Windows) o LF (Unix)."""
    if "\r\n" in content:
        return "\r\n"
    return "\n"


class PatchOperation:
    def __init__(
        self,
        filepath: str | Path,
        old_text: str,
        new_text: str,
        expected_sha256: Optional[str] = None,
    ):
        self.filepath = Path(filepath).resolve()
        self.old_text = old_text
        self.new_text = new_text
        self.expected_sha256 = expected_sha256


class PatchResult:
    def __init__(
        self,
        filepath: Path,
        success: bool,
        diff: str = "",
        error: Optional[str] = None,
        old_sha256: str = "",
        new_sha256: str = "",
    ):
        self.filepath = filepath
        self.success = success
        self.diff = diff
        self.error = error
        self.old_sha256 = old_sha256
        self.new_sha256 = new_sha256


class PatchEngine:
    """
    Motor seguro de edición de código con garantías ACID a nivel de archivo.
    """

    @staticmethod
    def apply_single_patch(
        filepath: str | Path,
        old_text: str,
        new_text: str,
        expected_sha256: Optional[str] = None,
        fuzzy_tolerance: float = 0.85,
    ) -> PatchResult:
        """
        Aplica una edición a un archivo de forma atómica.
        Garantiza que el archivo no quede corrupto ante excepciones o caídas.
        """
        path = Path(os.path.expandvars(os.path.expanduser(str(filepath)))).resolve()

        if not path.exists():
            return PatchResult(filepath=path, success=False, error=f"El archivo '{path}' no existe.")

        try:
            # 1. Lectura binaria y decodificación para preservar formato
            with open(path, "rb") as f:
                raw_bytes = f.read()

            try:
                original_content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                original_content = raw_bytes.decode("latin-1")

            original_sha = compute_sha256(original_content)
            line_ending = detect_line_ending(original_content)

            # 2. Validación de precondición SHA-256 si fue provisto
            if expected_sha256 and original_sha != expected_sha256:
                return PatchResult(
                    filepath=path,
                    success=False,
                    error=f"Conflicto de concurrencia: SHA256 actual ({original_sha[:8]}) difiere del esperado ({expected_sha256[:8]}).",
                    old_sha256=original_sha,
                )

            # 3. Normalización para matching
            norm_content = original_content.replace("\r\n", "\n")
            norm_old = old_text.replace("\r\n", "\n")
            norm_new = new_text.replace("\r\n", "\n")

            target_match = None
            if norm_old in norm_content:
                occurrences = norm_content.count(norm_old)
                if occurrences > 1:
                    return PatchResult(
                        filepath=path,
                        success=False,
                        error=f"Ambigüedad: El bloque objetivo aparece {occurrences} veces en el archivo. Proporciona más contexto circundante.",
                        old_sha256=original_sha,
                    )
                target_match = norm_old
            else:
                # Intento de Fuzzy matching con difflib si el matching exacto falla
                lines = norm_content.splitlines(keepends=True)
                old_lines = norm_old.splitlines(keepends=True)
                k = len(old_lines)
                best_ratio = 0.0
                best_sub = None

                for i in range(len(lines) - k + 1):
                    sub = "".join(lines[i : i + k])
                    ratio = difflib.SequenceMatcher(None, sub, norm_old).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_sub = sub

                if best_ratio >= fuzzy_tolerance and best_sub:
                    target_match = best_sub
                else:
                    return PatchResult(
                        filepath=path,
                        success=False,
                        error=(
                            f"No se encontró el texto original en el archivo (similitud máxima: {best_ratio*100:.1f}% vs umbral {fuzzy_tolerance*100:.1f}%). "
                            f"ACCIÓN OBLIGATORIA: Ejecuta 'read_file(path=\"{path}\")' para ver el código real o reescribe el módulo con 'write_file'."
                        ),
                        old_sha256=original_sha,
                    )

            # 4. Sustitución preservando los saltos de línea originales del archivo
            updated_content_norm = norm_content.replace(target_match, norm_new, 1)
            if line_ending == "\r\n":
                final_content = updated_content_norm.replace("\n", "\r\n")
            else:
                final_content = updated_content_norm

            new_sha = compute_sha256(final_content)

            # 5. Generar diff unificado
            diff_lines = list(
                difflib.unified_diff(
                    original_content.splitlines(keepends=True),
                    final_content.splitlines(keepends=True),
                    fromfile=f"a/{path.name}",
                    tofile=f"b/{path.name}",
                    n=3,
                )
            )
            unified_diff = "".join(diff_lines)

            # 6. Escritura Atómica vía archivo temporal en el mismo directorio (mismo filesystem para evitar EXDEV)
            parent_dir = path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile("w", dir=parent_dir, delete=False, encoding="utf-8", newline="") as tf:
                temp_path = Path(tf.name)
                tf.write(final_content)
                tf.flush()
                os.fsync(tf.fileno())

            # Reemplazo atómico
            os.replace(temp_path, path)

            return PatchResult(
                filepath=path,
                success=True,
                diff=unified_diff,
                old_sha256=original_sha,
                new_sha256=new_sha,
            )

        except Exception as e:
            return PatchResult(
                filepath=path,
                success=False,
                error=f"Error inesperado al aplicar parche en '{path}': {str(e)}",
            )

    @classmethod
    def apply_transaction(cls, operations: List[PatchOperation]) -> Tuple[bool, List[PatchResult], Optional[str]]:
        """
        Aplica un lote de operaciones de edición de forma transaccional.
        Si alguna operación falla, se revierten todos los archivos modificados previamente en la transacción.
        """
        backups: Dict[Path, str] = {}
        results: List[PatchResult] = []

        for op in operations:
            path = op.filepath
            if not path.exists():
                cls._rollback(backups)
                return False, results, f"El archivo '{path}' no existe. Transacción abortada."

            # Guardar backup en memoria antes de modificar
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    backups[path] = f.read()
            except Exception as e:
                cls._rollback(backups)
                return False, results, f"Fallo al leer '{path}' para backup: {str(e)}"

            res = cls.apply_single_patch(
                filepath=path,
                old_text=op.old_text,
                new_text=op.new_text,
                expected_sha256=op.expected_sha256,
            )
            results.append(res)

            if not res.success:
                # Hubo fallo: revertir todo
                cls._rollback(backups)
                return False, results, f"Transacción abortada: Falló edición en '{path}': {res.error}"

        return True, results, None

    @staticmethod
    def _rollback(backups: Dict[Path, str]):
        """Restaura los archivos a su contenido previo a la transacción."""
        for path, original_content in backups.items():
            try:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(original_content)
            except Exception:
                pass
