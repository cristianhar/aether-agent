"""
Herramientas de búsqueda y exploración de código base.
Permite descubrir estructura de carpetas y buscar definiciones léxicas.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "dist", "build"
}

EXCLUDED_EXTENSIONS = {
    ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz"
}


def list_directory(path: str = ".", max_depth: int = 2) -> str:
    """
    Lista el árbol de archivos y carpetas del proyecto excluyendo dependencias y temporales.
    """
    root_dir = Path(path).resolve()
    if not root_dir.exists():
        return f"Error: La ruta '{path}' no existe."
    if not root_dir.is_dir():
        return f"Error: '{path}' es un archivo, no un directorio."

    lines: List[str] = [f"Directorio: {root_dir.name}/"]

    def walk(current_dir: Path, current_depth: int, prefix: str):
        if current_depth > max_depth:
            return

        try:
            entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        # Filtrar excluidos
        valid_entries = [
            e for e in entries
            if e.name not in EXCLUDED_DIRS and not e.name.startswith(".")
        ]

        for i, entry in enumerate(valid_entries):
            is_last = (i == len(valid_entries) - 1)
            connector = "└── " if is_last else "├── "
            new_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                walk(entry, current_depth + 1, new_prefix)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    walk(root_dir, 1, "")
    if len(lines) == 1:
        return f"El directorio '{path}' no contiene archivos visibles."

    return "\n".join(lines[:300])  # Máximo 300 líneas


def search_codebase(query: str, path: str = ".", file_pattern: Optional[str] = None) -> str:
    """
    Busca ocurrencias textuales de 'query' en el código fuente.
    Utiliza ripgrep si está disponible; de lo contrario usa búsqueda nativa en Python.
    """
    search_path = Path(path).resolve()
    if not search_path.exists():
        return f"Error: La ruta '{path}' no existe."

    # Intentar usar ripgrep (rg) primero si está en el PATH
    rg_binary = shutil.which("rg")
    if rg_binary:
        cmd = [rg_binary, "--line-number", "--color", "never", "--max-count", "20", "--fixed-strings"]
        for excluded in EXCLUDED_DIRS:
            cmd.extend(["--glob", f"!{excluded}/*"])
        if file_pattern:
            cmd.extend(["--glob", file_pattern])
        cmd.extend([query, str(search_path)])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
            output = res.stdout.strip()
            if output:
                return f"Resultados de búsqueda con ripgrep para '{query}':\n" + output[:3000]
            return f"No se encontraron coincidencias para '{query}'."
        except Exception:
            pass  # Fallback a Python nativo

    # Búsqueda nativa recursiva en Python
    matches: List[str] = []
    query_lower = query.lower()

    for root, dirs, files in os.walk(search_path):
        # Excluir carpetas no deseadas in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

        for file_name in files:
            if file_pattern and not Path(file_name).match(file_pattern):
                continue
            ext = Path(file_name).suffix.lower()
            if ext in EXCLUDED_EXTENSIONS:
                continue

            file_full_path = Path(root) / file_name
            try:
                with open(file_full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if query_lower in line.lower():
                            rel_path = file_full_path.relative_to(search_path)
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                            if len(matches) >= 30:
                                break
            except Exception:
                continue

            if len(matches) >= 30:
                break
        if len(matches) >= 30:
            break

    if not matches:
        return f"No se encontraron coincidencias para '{query}' en '{path}'."

    res_str = f"Resultados de búsqueda ({len(matches)} coincidencias):\n" + "\n".join(matches)
    if len(matches) >= 30:
        res_str += "\n... [Búsqueda limitada a las primeras 30 coincidencias]"
    return res_str
