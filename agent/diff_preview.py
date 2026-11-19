"""
Módulo de Previsualización y Generación de Unified Diff de AETHER IDE.
Genera diffs unificados para modo REVIEW y confirmaciones interactivas de usuario.
"""

import difflib
from pathlib import Path
from typing import Any, Dict, Optional


def generate_tool_diff(tool_name: str, args: Dict[str, Any]) -> str:
    """Genera un Unified Diff estructurado para previsualización en Modo Review."""
    from tools.file_tools import get_absolute_path

    path_arg = str(args.get("path") or args.get("source") or "").strip().strip("'\"")
    if not path_arg:
        return f"Operación {tool_name} sin ruta especificada."

    try:
        abs_path = get_absolute_path(path_arg)
    except Exception:
        abs_path = Path(path_arg)

    old_content = ""
    if abs_path.is_file():
        try:
            old_content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            old_content = ""

    if tool_name == "write_file":
        new_content = str(args.get("content", ""))
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path_arg}",
            tofile=f"b/{path_arg}",
            lineterm="",
        )
        diff_lines = [line.rstrip("\r\n") for line in diff]
        return "\n".join(diff_lines) if diff_lines else f"(Sin cambios de contenido en {path_arg})"

    elif tool_name == "edit_file":
        target = args.get("target")
        replacement = args.get("replacement", args.get("content", ""))
        if replacement is None:
            replacement = ""

        simulated_content = None
        if target and target in old_content:
            simulated_content = old_content.replace(target, replacement, 1)
        else:
            from tools.file_tools import find_fuzzy_target
            match_info = find_fuzzy_target(old_content, target) if target else None
            if match_info:
                matched_target, _, delta = match_info
                rep_adjusted = replacement
                if delta > 0:
                    rep_adjusted = "\n".join(" " * delta + l if l.strip() else l for l in replacement.split("\n"))
                simulated_content = old_content.replace(matched_target, rep_adjusted, 1)

        if simulated_content is not None:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = simulated_content.splitlines(keepends=True)
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{path_arg}",
                tofile=f"b/{path_arg}",
                lineterm="",
            )
            diff_lines = [line.rstrip("\r\n") for line in diff]
            return "\n".join(diff_lines) if diff_lines else f"(Edición sin cambios netos en {path_arg})"
        else:
            t_lines = (target or "(bloque objetivo)").splitlines(keepends=True)
            r_lines = replacement.splitlines(keepends=True)
            diff = difflib.unified_diff(
                t_lines,
                r_lines,
                fromfile=f"a/{path_arg} (anterior)",
                tofile=f"b/{path_arg} (propuesto)",
                lineterm="",
            )
            diff_lines = [line.rstrip("\r\n") for line in diff]
            return "\n".join(diff_lines) if diff_lines else f"Reemplazo en {path_arg}:\n- {target}\n+ {replacement}"

    elif tool_name == "delete_file":
        old_lines = old_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            [],
            fromfile=f"a/{path_arg}",
            tofile="/dev/null",
            lineterm="",
        )
        diff_lines = [line.rstrip("\r\n") for line in diff]
        return "\n".join(diff_lines) if diff_lines else f"Eliminación de {path_arg}"

    return f"Operación '{tool_name}' sobre '{path_arg}'"
