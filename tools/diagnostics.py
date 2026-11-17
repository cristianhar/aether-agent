"""
Módulo de Diagnósticos y Análisis Estático (AST) para AETHER IDE.
Permite al agente verificar sintaxis y detectar errores antes y después de editar archivos.
"""

import ast
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def check_python_syntax(code: str, filename: str = "<string>") -> Dict[str, Any]:
    """Valida la sintaxis de un archivo Python usando el AST nativo."""
    try:
        ast.parse(code, filename=filename)
        return {"valid": True, "errors": []}
    except SyntaxError as se:
        return {
            "valid": False,
            "errors": [
                {
                    "line": se.lineno or 1,
                    "column": se.offset or 1,
                    "message": str(se.msg),
                    "text": se.text.strip() if se.text else "",
                }
            ],
        }


def check_json_syntax(code: str) -> Dict[str, Any]:
    """Valida la sintaxis de un archivo JSON."""
    try:
        json.loads(code)
        return {"valid": True, "errors": []}
    except json.JSONDecodeError as jde:
        return {
            "valid": False,
            "errors": [
                {
                    "line": jde.lineno,
                    "column": jde.colno,
                    "message": jde.msg,
                    "text": "",
                }
            ],
        }


def get_diagnostics(path: str) -> str:
    """
    Superpoder: Inspecciona un archivo en busca de errores sintácticos o de parsing.
    Soporta Python (.py) y JSON (.json).
    """
    resolved = Path(os.path.expandvars(os.path.expanduser(path))).resolve()

    if not resolved.exists():
        return f"❌ Error: El archivo '{path}' no existe."

    suffix = resolved.suffix.lower()

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"❌ Error leyendo archivo '{path}': {str(e)}"

    if suffix == ".py":
        diag = check_python_syntax(content, filename=str(resolved))
    elif suffix == ".json":
        diag = check_json_syntax(content)
    else:
        return f"ℹ️ Archivo '{path}' no requiere verificación AST (extensión {suffix}). Contenido legible sin errores de I/O."

    if diag["valid"]:
        return f"✅ Diagnóstico limpio: '{resolved.name}' no presenta errores de sintaxis."

    error_lines = []
    for err in diag["errors"]:
        error_lines.append(f"  • Línea {err['line']}, Col {err['column']}: {err['message']}")
        if err["text"]:
            error_lines.append(f"    Contexto: {err['text']}")

    return f"❌ Errores sintácticos detectados en '{resolved.name}':\n" + "\n".join(error_lines)
