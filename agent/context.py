"""
Módulo de Resolución de Contexto y Menciones de Archivos (@file) para AETHER.
Inspirado en Antigravity y Cursor: expande sintaxis @archivo.py inyectando
automáticamente su contenido y facilitando el autocompletado en el prompt.
"""

import difflib
from pathlib import Path
import re
from typing import List, Optional, Tuple

from prompt_toolkit.completion import Completer, Completion

from tools.base import DEFAULT_IGNORED_DIRS


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
        if f.is_file() and not any(p in f.parts for p in DEFAULT_IGNORED_DIRS)
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
    direct_file_tokens = re.findall(
        r"\b([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|jsx|tsx|json|md|html|css|txt|yaml|yml|sql|rs|go|c|cpp|h))\b",
        prompt,
        flags=re.IGNORECASE
    )
    all_tokens = list(dict.fromkeys(at_tokens + direct_file_tokens))
    if not all_tokens:
        return prompt, []

    attached_files: List[Path] = []
    context_blocks: List[str] = []
    clean_prompt = prompt

    for token in all_tokens:
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
                via_tag = f" VÍA @{token}" if token in at_tokens else ""

                if len(lines) <= 120 and len(content) <= 5000:
                    block = (
                        f"📄 [CONTEXTO ADJUNTO{via_tag} ({rel_path})]:\n"
                        f"```{ext}\n{content}\n```"
                    )
                else:
                    header = "\n".join(lines[:35])
                    outline_str = ""
                    if ext == "py":
                        try:
                            from tools.search_tools import get_file_outline
                            outline_str = f"\n\nESQUEMA ESTRUCTURAL AST:\n{get_file_outline(str(matched_file))}"
                        except Exception:
                            outline_str = ""

                    block = (
                        f"📄 [CONTEXTO ESTRUCTURADO{via_tag} ({rel_path} - {len(lines)} líneas)]:\n"
                        f"```{ext}\n{header}\n# ... (código truncado para preservar tokens de contexto) ...\n```"
                        f"{outline_str}"
                    )
                context_blocks.append(block)

                # Reemplazar @token por la ruta relativa en el prompt del usuario si venía con @
                if f"@{token}" in clean_prompt:
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
    final_prompt = (
        f"{full_context}\n\n"
        f"[INSTRUCCIÓN DE CONTEXTO]: El contenido y esquema estructural del archivo ya está completamente provisto arriba. "
        f"NO llames a ninguna herramienta (ni 'get_repo_map', ni 'list_directory', ni 'read_file'). "
        f"Tu respuesta DEBE SER DIRECTAMENTE una explicación en texto técnico detallando el archivo.\n\n"
        f"[CONSULTA DEL USUARIO]:\n{clean_prompt}"
    )
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
            if any(p in f.parts for p in DEFAULT_IGNORED_DIRS):
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


class AetherCLICompleter(Completer):
    """
    Completador interactivo de línea de comandos para AETHER:
    - Autocompleta comandos slash ('/') con descripción al escribir '/'
    - Autocompleta subcomandos (ej: '/mode agent | ask | plan | review')
    - Autocompleta archivos del espacio de trabajo al escribir '@' con búsqueda difusa
    - NO muestra ningún menú al escribir texto normal (cero distracción visual ni saltos de cursor)
    """
    COMMANDS = {
        "/help": "Muestra la guía interactiva y todos los comandos",
        "/mode": "Cambia el modo operativo: /mode agent | ask | plan | review",
        "/mode agent": "Plenos poderes de creación, edición y ejecución autónoma",
        "/mode ask": "Modo Solo Lectura: inspecciona código y responde dudas",
        "/mode plan": "Diseña el plan de arquitectura antes de tocar código",
        "/mode review": "Supervisión interactiva con diffs antes de cada cambio",
        "/plan": "Activa el modo de planificación arquitectónica",
        "/test": "Ejecuta las pruebas unitarias con pytest",
        "/diff": "Muestra las diferencias de código pendientes (git diff)",
        "/commit": "Genera un commit atómico con mensaje semántico",
        "/compact": "Compacta el historial para liberar tokens en VRAM",
        "/undo": "Revierte al checkpoint o commit anterior en 1 segundo",
        "/checkpoint": "Crea un punto de restauración Git inmediato",
        "/checkpoint create": "Guarda un snapshot del código actual",
        "/checkpoint undo": "Revierte al último checkpoint",
        "/model": "Cambia el modelo de Ollama en caliente",
        "/memory": "Consulta o busca en la memoria semántica persistente",
        "/memory list": "Lista todos los recuerdos y decisiones guardadas",
        "/memory search": "Busca semánticamente en los recuerdos",
        "/voice": "Muestra la integración con el asistente de voz",
        "/clear": "Reinicia el historial y contexto de la conversación",
        "/telemetry": "Muestra métricas de rendimiento y llamadas",
        "/sessions": "Lista las sesiones persistentes disponibles",
        "/resume": "Reanuda una sesión previa por ID",
        "/export": "Exporta la sesión actual a Markdown",
        "/exit": "Finaliza la sesión de AETHER",
    }

    MODE_OPTIONS = {
        "agent": "Plenos poderes de creación y ejecución autónoma",
        "ask": "Modo Solo Lectura: inspecciona código sin modificarlo",
        "plan": "Diseña la arquitectura antes de tocar código",
        "review": "Supervisión interactiva con diffs antes de cambios",
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._cached_files: List[str] = []
        self._last_scan_time = 0.0

    def _get_files(self) -> List[str]:
        import time
        now = time.time()
        # Caché de 3 segundos para evitar escaneo intensivo del disco en cada pulsación
        if not self._cached_files or (now - self._last_scan_time) > 3.0:
            self._cached_files = get_workspace_file_mentions(self.base_dir)
            self._last_scan_time = now
        return self._cached_files

    def get_completions(self, document, complete_event):
        line = document.current_line_before_cursor
        word = document.get_word_before_cursor(WORD=True)

        # 1. Subcomandos de /mode
        if line.startswith("/mode "):
            arg = line[len("/mode "):].lower().strip()
            for opt, desc in self.MODE_OPTIONS.items():
                if opt.startswith(arg):
                    yield Completion(opt, start_position=-len(arg), display=opt, display_meta=desc)
            return

        # 2. Comandos Slash (si la palabra o la línea empieza con /)
        if word.startswith("/"):
            q = word.lower()
            for cmd, desc in self.COMMANDS.items():
                if cmd.lower().startswith(q):
                    yield Completion(cmd, start_position=-len(word), display=cmd, display_meta=desc)
            return

        # 3. Menciones de Archivos (si la palabra empieza con @)
        if word.startswith("@"):
            q = word[1:].lower()
            files = self._get_files()
            matches = []
            for f in files:
                f_name = f[1:] if f.startswith("@") else f
                if not q:
                    matches.append((0, f, f_name))
                elif q in f_name.lower():
                    base = Path(f_name).name.lower()
                    priority = 0 if f_name.lower().startswith(q) or base.startswith(q) else 1
                    matches.append((priority, f, f_name))

            if q:
                matches.sort(key=lambda x: (x[0], len(x[2])))

            for _, f_token, f_name in matches[:30]:
                yield Completion(
                    f"@{f_name}",
                    start_position=-len(word),
                    display=f"@{f_name}",
                    display_meta="Archivo"
                )
            return

        # 4. Texto normal: no mostrar menú flotante
        return

