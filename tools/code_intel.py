"""
Módulo de Inteligencia de Código y Navegación AST (LSP nativo) para AETHER IDE.
Permite encontrar definiciones, referencias cruzadas y mapear dependencias e imports.
"""

import ast
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


def _find_py_files(root: Path) -> List[Path]:
    """Escanea recursivamente archivos Python ignorando carpetas de caché y entorno."""
    ignored = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".aether", "node_modules"}
    py_files = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(r) / f)
    return py_files


def find_definition(symbol: str, root_dir: str = ".") -> str:
    """
    Superpoder Code Intelligence: Localiza la definición exacta (función, método o clase)
    de un símbolo en todos los archivos Python del proyecto mediante análisis AST.
    """
    clean_sym = symbol.strip()
    if not clean_sym:
        return "❌ Error: El símbolo a buscar no puede estar vacío."

    root = Path(os.path.expandvars(os.path.expanduser(root_dir))).resolve()
    py_files = _find_py_files(root)

    matches: List[Dict[str, Any]] = []

    for file_path in py_files:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
        except Exception:
            continue

        rel_path = file_path.relative_to(root) if file_path.is_relative_to(root) else file_path

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == clean_sym:
                # Extraer argumentos
                args = [a.arg for a in node.args.args]
                sig = f"def {node.name}({', '.join(args)})"
                matches.append({
                    "type": "Función",
                    "file": str(rel_path).replace("\\", "/"),
                    "line": node.lineno,
                    "signature": sig,
                })
            elif isinstance(node, ast.ClassDef) and node.name == clean_sym:
                bases = [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else []
                bases_str = f"({', '.join(bases)})" if bases else ""
                sig = f"class {node.name}{bases_str}"
                matches.append({
                    "type": "Clase",
                    "file": str(rel_path).replace("\\", "/"),
                    "line": node.lineno,
                    "signature": sig,
                })

    if not matches:
        return f"ℹ️ No se encontró ninguna definición para el símbolo '{clean_sym}' en '{root.name}'."

    output = [f"📍 Definición encontrada para '{clean_sym}':"]
    for m in matches:
        output.append(f"  • [{m['type']}] {m['file']}:{m['line']}")
        output.append(f"    Firma: `{m['signature']}`")

    return "\n".join(output)


def find_references(symbol: str, root_dir: str = ".") -> str:
    """
    Superpoder Code Intelligence: Encuentra todas las llamadas y referencias cruzadas
    hacia un símbolo en todos los archivos del proyecto.
    """
    clean_sym = symbol.strip()
    if not clean_sym:
        return "❌ Error: El símbolo a buscar no puede estar vacío."

    root = Path(os.path.expandvars(os.path.expanduser(root_dir))).resolve()
    py_files = _find_py_files(root)

    references: List[Dict[str, Any]] = []

    for file_path in py_files:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            tree = ast.parse("".join(lines), filename=str(file_path))
        except Exception:
            continue

        rel_path = file_path.relative_to(root) if file_path.is_relative_to(root) else file_path

        for node in ast.walk(tree):
            found_line = None
            if isinstance(node, ast.Name) and node.id == clean_sym and not isinstance(node.ctx, ast.Store):
                found_line = node.lineno
            elif isinstance(node, ast.Attribute) and node.attr == clean_sym:
                found_line = node.lineno

            if found_line and 1 <= found_line <= len(lines):
                line_text = lines[found_line - 1].strip()
                # Evitar duplicados por la misma línea en el mismo archivo
                if not any(r["file"] == str(rel_path) and r["line"] == found_line for r in references):
                    references.append({
                        "file": str(rel_path).replace("\\", "/"),
                        "line": found_line,
                        "context": line_text,
                    })

    if not references:
        return f"ℹ️ No se encontraron referencias al símbolo '{clean_sym}'."

    output = [f"🔍 Referencias encontradas para '{clean_sym}' ({len(references)} ocurrencias):"]
    for r in references[:25]:
        output.append(f"  • {r['file']}:{r['line']} ❯ {r['context']}")

    if len(references) > 25:
        output.append(f"  ... y {len(references) - 25} referencias adicionales truncadas.")

    return "\n".join(output)


def get_dependencies(path: str) -> str:
    """
    Superpoder Code Intelligence: Analiza el gráfico de dependencias e imports de un archivo.
    Clasifica en estándar, locales del proyecto y paquetes de terceros.
    """
    target = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    if not target.exists():
        return f"❌ Error: El archivo '{path}' no existe."

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        tree = ast.parse(content, filename=str(target))
    except Exception as e:
        return f"❌ Error analizando AST de '{target.name}': {str(e)}"

    stdlib_modules = sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else set()
    standard_libs: Set[str] = set()
    third_party: Set[str] = set()
    local_imports: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in stdlib_modules:
                    standard_libs.add(alias.name)
                elif (target.parent / f"{root_pkg}.py").exists() or (target.parent / root_pkg).is_dir():
                    local_imports.add(alias.name)
                else:
                    third_party.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg in stdlib_modules:
                    standard_libs.add(node.module)
                elif (target.parent / f"{root_pkg}.py").exists() or (target.parent / root_pkg).is_dir():
                    local_imports.add(node.module)
                else:
                    third_party.add(node.module)

    output = [f"📦 Gráfico de Dependencias de `{target.name}`:"]
    if local_imports:
        output.append(f"  • Módulos Locales ({len(local_imports)}): {', '.join(sorted(local_imports))}")
    if third_party:
        output.append(f"  • Librerías de Terceros ({len(third_party)}): {', '.join(sorted(third_party))}")
    if standard_libs:
        output.append(f"  • Biblioteca Estándar ({len(standard_libs)}): {', '.join(sorted(standard_libs))}")

    return "\n".join(output)
