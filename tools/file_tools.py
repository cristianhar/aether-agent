"""
Herramientas atómicas para manipulación de archivos y código.
Diseñadas para maximizar precisión y minimizar consumo de tokens de contexto.
"""

from pathlib import Path
from typing import Optional


def get_absolute_path(path_str: str, base_dir: Optional[Path] = None) -> Path:
    base = base_dir or Path.cwd()
    target_path = Path(path_str)
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
        return f"Error: El archivo '{path}' no existe en la ruta {file_path}."
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


def write_file(path: str, content: str) -> str:
    """
    Crea o sobrescribe un archivo asegurando la creación recursiva de directorios padre.
    """
    file_path = get_absolute_path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Éxito: Archivo '{path}' guardado correctamente ({len(content)} caracteres)."
    except Exception as e:
        return f"Error al escribir en '{path}': {str(e)}"


def edit_file(path: str, target: str, replacement: str) -> str:
    """
    Reemplaza exactamente el bloque 'target' por 'replacement' dentro del archivo.
    Requiere coincidencia exacta de caracteres e indentación.
    """
    file_path = get_absolute_path(path)
    if not file_path.exists():
        return f"Error: El archivo '{path}' no existe."
    if file_path.is_dir():
        return f"Error: '{path}' es un directorio."

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"Error al leer el archivo '{path}': {str(e)}"

    # Normalizar retornos de carro para evitar discrepancias CRLF vs LF
    content_normalized = content.replace("\r\n", "\n")
    target_normalized = target.replace("\r\n", "\n")
    replacement_normalized = replacement.replace("\r\n", "\n")

    count = content_normalized.count(target_normalized)

    if count == 0:
        return (
            f"Error: No se encontró el texto 'target' en '{path}'. "
            "Asegúrate de incluir la indentación exacta y suficientes líneas circundantes para que sea unívoco."
        )

    if count > 1:
        return (
            f"Error: El texto 'target' aparece {count} veces en '{path}'. "
            "Incluye más líneas de contexto circundante para identificar únicamente el bloque a modificar."
        )

    new_content = content_normalized.replace(target_normalized, replacement_normalized, 1)

    # Conservar el formato original de fin de línea si era CRLF
    if "\r\n" in content:
        new_content = new_content.replace("\n", "\r\n")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Éxito: Archivo '{path}' actualizado correctamente con el bloque reemplazado."
    except Exception as e:
        return f"Error al guardar cambios en '{path}': {str(e)}"
