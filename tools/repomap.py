"""
Repo-Map Generator inspirado en Aider.
Genera un mapa conciso y ultra-optimizado en tokens de la estructura del proyecto,
mostrando archivos, clases, métodos, firmas y funciones principales.
Permite al agente comprender repositorios enteros en ~300 tokens sin leer miles de líneas.
"""

import ast
import os
import re
from pathlib import Path
from typing import List, Optional

from tools.base import DEFAULT_IGNORED_DIRS, DEFAULT_IGNORED_EXTENSIONS



def _extract_py_symbols(filepath: Path) -> List[str]:
    """Extrae clases, métodos y funciones de un archivo Python usando AST."""
    symbols = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content, filename=str(filepath))
    except Exception:
        return symbols

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(f"class {node.name}:")
            for item in node.body:
                if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                    args = [a.arg for a in item.args.args if a.arg != "self"]
                    symbols.append(f"    def {item.name}({', '.join(args[:4])})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            symbols.append(f"def {node.name}({', '.join(args[:4])})")

    return symbols


def _extract_js_ts_symbols(filepath: Path) -> List[str]:
    """Extrae componentes, clases y funciones en archivos JS/TS."""
    symbols = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return symbols

    # Funciones exportadas y clases
    funcs = re.findall(r"(?:export\s+(?:default\s+)?)?(?:function|class)\s+([a-zA-Z0-9_]+)", content)
    for f in funcs[:6]:
        symbols.append(f"function {f}()")

    # Componentes React: const App = () => ...
    components = re.findall(r"(?:export\s+)?const\s+([A-Z][a-zA-Z0-9_]*)\s*=", content)
    for c in components[:4]:
        name = f"component {c}"
        if name not in symbols and f"function {c}()" not in symbols:
            symbols.append(name)

    return symbols


def generate_repo_map(root_dir: str = ".", max_files: int = 40) -> str:
    """
    Escanea el espacio de trabajo y genera el mapa arquitectónico del repositorio.
    """
    root = Path(root_dir).resolve()
    lines = [f"📦 REPO-MAP: {root.name}/"]
    count = 0

    for current_dir, dirs, files in os.walk(root):
        # Filtrar directorios ignorados
        dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORED_DIRS and not d.startswith(".")]

        rel_dir = Path(current_dir).relative_to(root)
        if rel_dir == Path("."):
            indent = ""
        else:
            indent = "  " * len(rel_dir.parts)
            lines.append(f"{indent}📁 {rel_dir.name}/")
            indent += "  "

        for f in sorted(files):
            if count >= max_files:
                lines.append(f"{indent}... [archivos restantes omitidos para ahorrar tokens]")
                return "\n".join(lines)

            file_path = Path(current_dir) / f
            if file_path.suffix in DEFAULT_IGNORED_EXTENSIONS or f.startswith("."):
                continue

            count += 1
            if file_path.suffix == ".py":
                symbols = _extract_py_symbols(file_path)
                lines.append(f"{indent}📄 {f}")
                for sym in symbols[:6]:
                    lines.append(f"{indent}    {sym}")
                if len(symbols) > 6:
                    lines.append(f"{indent}    ... ({len(symbols) - 6} símbolos más)")
            elif file_path.suffix in (".js", ".ts", ".jsx", ".tsx"):
                symbols = _extract_js_ts_symbols(file_path)
                lines.append(f"{indent}📄 {f}")
                for sym in symbols[:4]:
                    lines.append(f"{indent}    {sym}")
            else:
                lines.append(f"{indent}📄 {f}")

    return "\n".join(lines)
