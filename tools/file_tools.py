"""
Herramientas atómicas para manipulación de archivos y código.
Diseñadas para maximizar precisión y minimizar consumo de tokens de contexto.
"""

import ast
import os
import shutil
import hashlib
from pathlib import Path
import re
from typing import Optional


def calculate_file_hash(path: Path) -> Optional[str]:
    """Calcula la huella criptográfica SHA-256 de un archivo en disco."""
    if not path.exists() or not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def get_absolute_path(path_str: str, base_dir: Optional[Path] = None) -> Path:
    base = base_dir or Path.cwd()
    expanded = os.path.expandvars(os.path.expanduser(path_str))
    target_path = Path(expanded)
    if not target_path.is_absolute():
        target_path = (base / target_path).resolve()
    else:
        target_path = target_path.resolve()
    return target_path


def read_file(path: str, start_line: int = 1, end_line: int = 200) -> str:
    """
    Lee un rango de líneas de un archivo de texto con numeración de líneas.
    """
    file_path = get_absolute_path(path)
    if not file_path.exists():
        return (
            f"Error: El archivo '{path}' no existe en la ruta {file_path}.\n"
            f"• Si deseas CREAR este archivo, debes usar 'write_file(path=\"{path}\", content=...)'.\n"
            f"• Si deseas ver qué archivos existen en esta carpeta, usa 'list_directory'."
        )
    if file_path.is_dir():
        return f"Error: '{path}' es un directorio, no un archivo de texto."

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error al leer el archivo '{path}': {str(e)}"

    total_lines = len(lines)
    if total_lines == 0:
        return f"El archivo '{path}' está vacío."

    # Normalizar rangos (1-indexed a 0-indexed)
    start_idx = max(0, start_line - 1)
    end_idx = min(total_lines, end_line)

    if start_idx >= total_lines:
        return f"Error: start_line ({start_line}) excede el total de líneas ({total_lines})."

    output = [f"--- {path} (Líneas {start_idx + 1} a {end_idx} de {total_lines}) ---"]
    for i in range(start_idx, end_idx):
        output.append(f"{i + 1:4d} | {lines[i].rstrip()}")

    return "\n".join(output)


def check_syntax(file_path: Path, new_content: str) -> Optional[str]:
    """
    Superpoder: Auto-Linter sintáctico instantáneo.
    Detecta SyntaxErrors en archivos Python y JSON al instante de ser modificados.
    """
    if file_path.suffix == ".py":
        try:
            import ast
            ast.parse(new_content, filename=str(file_path))
        except SyntaxError as se:
            snippet = se.text.strip() if se.text else ""
            return f"⚠️ [Auto-Linter] Error de sintaxis en línea {se.lineno}: {se.msg} -> '{snippet}'"
    elif file_path.suffix == ".json":
        try:
            import json
            json.loads(new_content)
        except Exception as je:
            return f"⚠️ [Auto-Linter] JSON inválido: {je}"
    return None


def auto_heal_missing_imports(file_path: Path, content: str) -> str:
    """
    Auto-Sanador Estático de Importaciones:
    Previene NameError en tiempo de ejecución inyectando automáticamente
    módulos estándar y anotaciones de tipos omitidos comúnmente por LLMs locales.
    """
    if file_path.suffix != ".py":
        return content

    try:
        tree = ast.parse(content)
    except Exception:
        return content

    imported = set()
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imported.add(n.asname or n.name)
        elif isinstance(node, ast.ImportFrom):
            for n in node.names:
                imported.add(n.asname or n.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)

    used_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)

    needed_imports = []
    typing_keys = {"Optional", "Union", "Any", "Callable", "Dict", "List", "Tuple"}
    if typing_keys.intersection(used_names) - imported - defined:
        needed_imports.append("from typing import Any, Callable, Dict, List, Optional, Tuple, Union\n")

    std_map = {
        "time": "import time\n",
        "math": "import math\n",
        "json": "import json\n",
        "os": "import os\n",
        "sys": "import sys\n",
        "re": "import re\n",
    }
    for mod_name, import_stmt in std_map.items():
        if mod_name in used_names and mod_name not in imported and mod_name not in defined:
            needed_imports.append(import_stmt)

    if needed_imports:
        content = "".join(needed_imports) + content

    # Auto-sanación de discrepancias de nombres entre archivo de pruebas y módulo fuente
    # Ej: test_kv_store.py importa KeyValueStore cuando kv_store.py define KVStore
    if file_path.name.startswith("test_"):
        sibling_stem = file_path.stem[5:]
        sibling_path = file_path.parent / f"{sibling_stem}.py"
        if sibling_path.is_file():
            try:
                s_tree = ast.parse(sibling_path.read_text(encoding="utf-8", errors="replace"))
                s_classes = [n.name for n in ast.walk(s_tree) if isinstance(n, ast.ClassDef)]
                if len(s_classes) == 1:
                    target_class = s_classes[0]
                    pattern = rf"from\s+{sibling_stem}\s+import\s+([A-Za-z0-9_]+)"
                    for m in re.finditer(pattern, content):
                        imported_name = m.group(1)
                        if imported_name != target_class and imported_name != "*":
                            content = content.replace(
                                m.group(0),
                                f"from {sibling_stem} import {target_class} as {imported_name}"
                            )
            except Exception:
                pass

    return content


def find_fuzzy_target(content: str, target: str) -> Optional[tuple]:
    """
    Superpoder: Fuzzy Matcher inteligente.
    Si la búsqueda exacta falla, busca el bloque tolerando variaciones menores
    de espacios en blanco al final de línea o diferencias leves de sangría.
    Retorna (bloque_original_encontrado, nota) si la coincidencia es única.
    """
    content_lines = content.split("\n")
    target_lines = [l.rstrip() for l in target.split("\n")]
    if not target_lines:
        return None

    m = len(target_lines)
    matches = []

    for i in range(len(content_lines) - m + 1):
        window = content_lines[i : i + m]
        window_stripped = [l.rstrip() for l in window]
        
        # Comparación 1: Tolerancia a espacios finales
        if window_stripped == target_lines:
            matches.append("\n".join(window))
            continue

        # Comparación 2: Tolerancia a sangría proporcional
        if [l.strip() for l in window] == [l.strip() for l in target_lines]:
            matches.append("\n".join(window))

    if len(matches) == 1:
        matched_str = matches[0]
        w_lines = matched_str.split("\n")
        w_indent = len(w_lines[0]) - len(w_lines[0].lstrip())
        t_indent = len(target_lines[0]) - len(target_lines[0].lstrip())
        delta = max(0, w_indent - t_indent)
        return matched_str, " (aplicado mediante coincidencia inteligente de espacios)", delta

    # Comparación 3: Coincidencia difusa profunda con difflib (para omisiones de palabras clave como 'async' o typos leves)
    if not matches and m >= 2:
        from difflib import SequenceMatcher
        best_ratio = 0.0
        best_window = None
        target_str = "\n".join(target_lines)

        for i in range(len(content_lines) - m + 1):
            window_str = "\n".join([line.rstrip() for line in content_lines[i : i + m]])
            ratio = SequenceMatcher(None, window_str, target_str).ratio()
            if ratio >= 0.85:
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_window = "\n".join(content_lines[i : i + m])
                    matches = [best_window]
                elif abs(ratio - best_ratio) < 0.01:
                    matches.append("\n".join(content_lines[i : i + m]))

        if len(matches) == 1 and best_window and best_ratio >= 0.85:
            pct = int(best_ratio * 100)
            w_lines = best_window.split("\n")
            w_indent = len(w_lines[0]) - len(w_lines[0].lstrip())
            t_indent = len(target_lines[0]) - len(target_lines[0].lstrip())
            delta = max(0, w_indent - t_indent)
            return best_window, f" (aplicado mediante coincidencia difusa inteligente al {pct}%)", delta

    return None


def write_file(path: str, content: str) -> str:
    """
    Crea o sobrescribe un archivo asegurando la creación recursiva de directorios padre
    e incorpora validación sintáctica automática (Auto-Linter).
    """
    file_path = get_absolute_path(path)
    try:
        # Normalización de strings con escapes literales (\n, \t) producidos por LLMs locales
        if r"\n" in content and "\n" not in content:
            content = content.replace(r"\n", "\n").replace(r"\t", "\t").replace(r'\"', '"')

        content = auto_heal_missing_imports(file_path, content)

        # Chequeo de idempotencia SHA-256 para evitar bucles de sobreescritura idéntica
        if file_path.exists() and file_path.is_file():
            existing_hash = calculate_file_hash(file_path)
            new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if existing_hash == new_hash:
                return (
                    f"Aviso / Sin cambios: El archivo '{path}' ya existe y contiene exactamente este mismo código (SHA256 idéntico).\n"
                    "• No vuelvas a llamar a 'write_file' con el mismo contenido.\n"
                    "• Procede al siguiente paso de tu tarea (ej: crear el archivo de pruebas con 'write_file' o ejecutar las pruebas con 'run_tests')."
                )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        syntax_warn = check_syntax(file_path, content)
        msg = f"Éxito: Archivo '{path}' guardado correctamente ({len(content)} caracteres)."
        if syntax_warn:
            msg += (
                f"\n{syntax_warn}\n"
                f"🚨 [ACCIÓN OBLIGATORIA]: El archivo '{path}' fue guardado pero CONTIENE UN ERROR DE SINTAXIS. "
                "Tu PRÓXIMA herramienta DEBE ser 'edit_file' para corregir la línea indicada antes de cualquier otra cosa. "
                "NUNCA llames a 'run_command' con un archivo que tiene errores de sintaxis."
            )
        return msg
    except Exception as e:
        return f"Error al escribir en '{path}': {str(e)}"


def edit_file(
    path: str,
    target: Optional[str] = None,
    replacement: Optional[str] = None,
    content: Optional[str] = None,
) -> str:
    """
    Reemplaza el bloque 'target' por 'replacement' dentro del archivo.
    Incluye fallback con Fuzzy Matching inteligente, Auto-Linter sintáctico
    y auto-rescate a reescritura completa si target no es provisto.
    """
    file_path = get_absolute_path(path)
    if not file_path.exists():
        return (
            f"Error: El archivo '{path}' no existe físicamente en el disco.\n"
            f"• La herramienta 'edit_file' solo puede modificar archivos existentes.\n"
            f"• ACCIÓN OBLIGATORIA: Para CREAR este archivo por primera vez, debes llamar a 'write_file(path=\"{path}\", content=...)'."
        )
    if file_path.is_dir():
        return f"Error: '{path}' es un directorio."

    # Auto-rescate: Si target no fue especificado (None) pero se envió content, reescribir con write_file
    rep_text = replacement if replacement is not None else content
    if target is None and rep_text and rep_text.strip():
        return write_file(path=path, content=rep_text)

    if not target or not target.strip():
        return (
            f"Error de parámetro 'target': El parámetro 'target' no puede ser una cadena vacía ni contener solo espacios.\n"
            f"• Si deseas REESCRIBIR o ACTUALIZAR el archivo completo '{path}', utiliza 'write_file(path=\"{path}\", content=...)'.\n"
            f"• Si deseas INSERTAR código al inicio o final, incluye como 'target' las líneas reales existentes en el archivo usando 'read_file'.\n"
            f"• NUNCA envíes target=''."
        )

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            file_content = f.read()
    except Exception as e:
        return f"Error al leer el archivo '{path}': {str(e)}"

    content_normalized = file_content.replace("\r\n", "\n")
    target_normalized = target.replace("\r\n", "\n")
    replacement_normalized = rep_text.replace("\r\n", "\n")

    count = content_normalized.count(target_normalized)
    note = ""
    indent_delta = 0

    if count == 0:
        fuzzy_match = find_fuzzy_target(content_normalized, target_normalized)
        if fuzzy_match:
            target_normalized, note, indent_delta = fuzzy_match
            count = 1
        else:
            error_signatures = [
                "Traceback (most recent call last)",
                "EOFError",
                "SyntaxError",
                "NameError",
                "TypeError",
                "ValueError",
                "[HOOK POST-TOOL]",
                "[SISTEMA AETHER]",
                "Código de salida:",
                "--- STDERR ---",
                "--- STDOUT ---",
            ]
            if any(sig in target for sig in error_signatures):
                preview = target.strip().replace("\n", " ")[:60]
                return (
                    f"Error de parámetro 'target': Has pasado la salida o mensaje de error de la terminal ('{preview}...') como 'target'. "
                    f"El parámetro 'target' debe ser el CÓDIGO FUENTE REAL que existe físicamente dentro del archivo '{path}', "
                    "NUNCA un mensaje de error de la consola. "
                    f"Usa primero 'read_file(path=\"{path}\")' para ver las líneas de código exactas que deseas modificar."
                )
            return (
                f"Error: No se encontró el texto 'target' en '{path}'. "
                f"El texto que enviaste no coincide exactamente con el archivo en disco. "
                f"ACCIÓN OBLIGATORIA: Ejecuta 'read_file(path=\"{path}\")' para ver las líneas exactas e indentación antes de intentar editarlo nuevamente, o reescribe el archivo con 'write_file'."
            )

    if count > 1:
        return (
            f"Error: El texto 'target' aparece {count} veces en '{path}'. "
            "Incluye más líneas de contexto circundante para identificar únicamente el bloque a modificar, "
            f"o si el archivo es pequeño reescríbelo completamente usando 'write_file(path=\"{path}\", content=...)'."
        )

    hash_before = calculate_file_hash(file_path)

    if indent_delta > 0:
        rep_lines = replacement_normalized.split("\n")
        first_rep_indent = len(rep_lines[0]) - len(rep_lines[0].lstrip()) if rep_lines else 0
        if first_rep_indent == 0:
            replacement_normalized = "\n".join(
                [(" " * indent_delta + l) if l.strip() else l for l in rep_lines]
            )

    if target_normalized == replacement_normalized:
        return (
            f"Error / Sin cambios (Idéntico): El bloque 'replacement' es IDÉNTICO al bloque 'target'. "
            f"No se realizó ninguna modificación en el archivo '{path}'.\n"
            "💡 [INSTRUCCIÓN DE AUTO-CORRECCIÓN]: Enviaste exactamente el mismo código en target y replacement. "
            "Si una prueba previa falló por una aserción ('AssertionError: actual != esperado'):\n"
            f"• Opción A: Modifica la fórmula o lógica en '{path}' para que genere el valor que espera el test.\n"
            "• Opción B: Si la fórmula actual es la correcta y el test tenía un valor esperado erróneo, utiliza 'edit_file' sobre el archivo de pruebas para actualizar el valor esperado.\n"
            "NO vuelvas a enviar 'target == replacement'."
        )

    new_content = content_normalized.replace(target_normalized, replacement_normalized, 1)

    hash_new = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
    if hash_before and hash_before == hash_new:
        return (
            f"Error / Sin cambios (SHA256 idéntico): La sustitución no produjo ningún cambio efectivo en '{path}'. "
            "Revisa el bloque 'target' e intenta con una edición diferente o usa 'write_file'."
        )

    new_content = auto_heal_missing_imports(file_path, new_content)
    if "\r\n" in file_content:
        new_content = new_content.replace("\n", "\r\n")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        syntax_warn = check_syntax(file_path, new_content)
        msg = f"Éxito: Archivo '{path}' actualizado correctamente con el bloque reemplazado{note}."
        if syntax_warn:
            msg += (
                f"\n{syntax_warn}\n"
                f"🚨 [ACCIÓN OBLIGATORIA]: El archivo '{path}' sigue teniendo errores de sintaxis tras el reemplazo. "
                "Llama a 'edit_file' nuevamente para corregir la línea señalada antes de ejecutar pruebas o comandos."
            )
        return msg
    except Exception as e:
        return f"Error al guardar cambios en '{path}': {str(e)}"


def delete_file(path: str) -> str:
    """Elimina de forma segura un archivo existente en el sistema."""
    file_path = get_absolute_path(path)
    if not file_path.exists():
        return f"Aviso: El archivo '{path}' no existe."
    if file_path.is_dir():
        return f"Error: '{path}' es un directorio. Utiliza comandos de terminal para carpetas."
    try:
        file_path.unlink()
        return f"Éxito: Archivo '{path}' eliminado correctamente del disco."
    except Exception as e:
        return f"Error al eliminar '{path}': {str(e)}"


def move_file(source: str, destination: str) -> str:
    """Mueve o renombra un archivo a una nueva ubicación o nombre."""
    src_path = get_absolute_path(source)
    dst_path = get_absolute_path(destination)
    if not src_path.exists():
        return f"Error: El archivo de origen '{source}' no existe."
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        return f"Éxito: Archivo '{source}' movido/renombrado a '{destination}'."
    except Exception as e:
        return f"Error al mover '{source}' a '{destination}': {str(e)}"


