"""
Módulo de Resolución de Contexto y Menciones de Archivos (@file) para AETHER.
Inspirado en Antigravity y Cursor: expande sintaxis @archivo.py inyectando
automáticamente su contenido y facilitando el autocompletado en el prompt.
"""

import difflib
from pathlib import Path
import re
from typing import List, Optional, Tuple

IGNORED_DIRS = {
    ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
    ".aether", "e2e_sandbox", "node_modules", "site-packages",
    "dist", "build", ".idea", ".vscode"
}


def find_matching_file(token: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Localiza un archivo en el espacio de trabajo a partir de un token de mención (@archivo).
    Soporta rutas relativas directas, coincidencia exacta de nombre y coincidencia difusa (typos).
    """
    if base_dir is None:
        base_dir = Path.cwd()

    clean = token.lstrip("@").strip().strip("'\"").replace("\\", "/")
    if not clean:
        return None

    # 1. Ruta relativa directa
    direct_p = (base_dir / clean).resolve()
    if direct_p.is_file():
        return direct_p

    target_name = Path(clean).name.lower()
    if not target_name:
        return None

    all_files = [
        f for f in base_dir.rglob("*")
        if f.is_file() and not any(p in f.parts for p in IGNORED_DIRS)
    ]

    # 2. Coincidencia exacta por nombre de archivo
    exact = [f for f in all_files if f.name.lower() == target_name]
    if exact:
        if "test" not in target_name:
            non_tests = [f for f in exact if "test" not in f.name.lower()]
            if non_tests:
                return non_tests[0]
        return exact[0]

    # 3. Coincidencia difusa con difflib (para errores tipográficos como file_tool.py -> file_tools.py)
    names = [f.name for f in all_files]
    matches = difflib.get_close_matches(target_name, names, n=3, cutoff=0.6)
    if matches:
        best_name = matches[0]
        cands = [f for f in all_files if f.name == best_name]
        if "test" not in target_name:
            non_tests = [f for f in cands if "test" not in f.name.lower()]
            if non_tests:
                return non_tests[0]
        return cands[0]

    return None


def resolve_at_file_mentions(
    prompt: str,
    base_dir: Optional[Path] = None,
    max_lines_full: int = 600
) -> Tuple[str, List[Path]]:
    """
    Detecta menciones @archivo en el prompt del usuario, lee su contenido del disco
    e inyecta el código relevante como contexto estructurado.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    at_tokens = re.findall(r"@([a-zA-Z0-9_\-\./\\]+)", prompt)
    if not at_tokens:
        return prompt, []

    attached_files: List[Path] = []
    context_blocks: List[str] = []
    clean_prompt = prompt

    for token in at_tokens:
        matched_file = find_matching_file(token, base_dir)
        if matched_file and matched_file not in attached_files:
            attached_files.append(matched_file)
            try:
                content = matched_file.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                try:
                    rel_path = matched_file.relative_to(base_dir).as_posix()
                except Exception:
                    rel_path = matched_file.name

                ext = matched_file.suffix.lstrip(".") or "text"

                if len(lines) <= max_lines_full:
                    block = (
                        f"📄 [CONTEXTO ADJUNTO VÍA @{token} ({rel_path})]:\n"
                        f"```{ext}\n{content}\n```"
                    )
                else:
                    truncated = "\n".join(lines[:max_lines_full])
                    block = (
                        f"📄 [CONTEXTO ADJUNTO VÍA @{token} ({rel_path} - Primeras {max_lines_full} de {len(lines)} líneas)]:\n"
                        f"```{ext}\n{truncated}\n...\n```"
                    )
                context_blocks.append(block)

                # Reemplazar @token por la ruta relativa en el prompt del usuario
                clean_prompt = clean_prompt.replace(f"@{token}", rel_path)
            except Exception:
                pass

    if not attached_files:
        return prompt, []

    # Si el usuario solo escribió "@archivo" sin ninguna instrucción adicional
    remainder = clean_prompt.strip()
    is_only_files = False
    try:
        attached_rel_paths = {f.relative_to(base_dir).as_posix() for f in attached_files}
        is_only_files = remainder in attached_rel_paths or not remainder
    except Exception:
        is_only_files = not remainder

    if is_only_files:
        try:
            file_list = ", ".join(f"'{f.relative_to(base_dir).as_posix()}'" for f in attached_files)
        except Exception:
            file_list = ", ".join(f"'{f.name}'" for f in attached_files)
        clean_prompt = (
            f"Analiza detalladamente el archivo adjunto {file_list}. "
            f"Explica su propósito general, responsabilidades arquitectónicas, clases, funciones y cómo se integra con el resto del sistema."
        )

    full_context = "\n\n".join(context_blocks)
    final_prompt = f"{full_context}\n\n[CONSULTA DEL USUARIO]:\n{clean_prompt}"
    return final_prompt, attached_files


def get_workspace_file_mentions(base_dir: Optional[Path] = None, max_results: int = 150) -> List[str]:
    """
    Genera la lista de menciones de archivos disponibles en el espacio de trabajo (@archivo)
    para el autocompletado en prompt_toolkit.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    allowed_exts = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".txt", ".sh", ".bat", ".ts", ".js", ".html", ".css"}
    mentions = set()

    try:
        for f in base_dir.rglob("*"):
            if not f.is_file():
                continue
            if any(p in f.parts for p in IGNORED_DIRS):
                continue
            if f.suffix.lower() not in allowed_exts:
                continue

            try:
                rel = f.relative_to(base_dir).as_posix()
                mentions.add(f"@{rel}")
                mentions.add(f"@{f.name}")
            except Exception:
                pass

            if len(mentions) >= max_results * 2:
                break
    except Exception:
        pass

    return sorted(mentions)
