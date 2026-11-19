"""
Registro central de herramientas para el LLM.
Define esquemas OpenAPI / JSON Schema compatibles con la API de Ollama y el despachador de ejecución.
Arquitectura modular con esquemas divididos por dominios funcionales en tools/schemas/.
"""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from tools.file_tools import delete_file, edit_file, move_file, read_file, write_file
from tools.git_tools import create_checkpoint, get_git_diff, get_git_status, undo_checkpoint
from tools.repomap import generate_repo_map
from tools.search_tools import list_directory, search_codebase, get_file_outline
from tools.shell_tools import run_command
from tools.subagent import delegate_task, delegate_research, delegate_test
from tools.web_tools import search_web, fetch_web_page
from tools.diagnostics import get_diagnostics
from tools.patch_engine import PatchEngine
from tools.process_manager import ProcessManager
from tools.agent_tools import (
    update_plan,
    get_plan,
    request_approval,
    get_project_instructions,
    remember_fact,
    search_memory,
    list_memories,
    ask_question_tool,
    create_artifact_tool,
    update_artifact_tool,
    read_artifact_tool,
    list_artifacts_tool,
)
from tools.code_intel import find_definition, find_references, get_dependencies
from tools.vram_monitor import get_hardware_vram_status
from tools.mcp_client import list_mcp_tools, call_mcp_tool_wrapper

# Esquemas de herramientas consolidados desde la arquitectura modular
from tools.schemas import TOOLS_SCHEMA


# Funciones puente para herramientas extendidas
def apply_patch_tool(path: str, target: str, replacement: str, expected_sha256: str = None) -> str:
    res = PatchEngine.apply_single_patch(path, target, replacement, expected_sha256)
    if res.success:
        diff_str = res.diff if res.diff else "(sin cambios textuales en diff)"
        return f"✅ Parche transaccional aplicado con éxito en '{res.filepath.name}'.\nSHA256: {res.old_sha256[:8]} -> {res.new_sha256[:8]}\n\nDiff unificado:\n{diff_str}"
    return f"❌ Fallo al aplicar parche en '{path}': {res.error}"


def run_tests_tool(test_target: str = None) -> str:
    target = test_target.strip() if test_target else ""
    if target and target != ".":
        # Tolerancia a alucinación de prefijo de carpeta (ej: tests/test_foo.py cuando está en la raíz o viceversa)
        target_path = Path(target)
        if not target_path.exists():
            base_name = target_path.name
            if (Path.cwd() / base_name).is_file():
                target = base_name
            elif (Path.cwd() / "tests" / base_name).is_file():
                target = f"tests/{base_name}"
    if not target or target == ".":
        # Buscar pruebas en raíz y en tests/, priorizando el archivo de pruebas más recientemente modificado
        all_tests = [p for p in Path.cwd().glob("test_*.py") if p.is_file()] + [p for p in Path.cwd().glob("tests/test_*.py") if p.is_file()]
        if all_tests:
            all_tests.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            try:
                target = str(all_tests[0].relative_to(Path.cwd())).replace("\\", "/")
            except Exception:
                target = all_tests[0].name
        else:
            target = "."
    elif target.lower() in ["all", "suite", "full"]:
        target = "."
    cmd = f"pytest -v --rootdir=. -o testpaths=. {target}"
    return run_command(cmd)


def conclude_turn_tool(message: str = "Tarea concluida", **kwargs) -> str:
    return f"🏁 Turno concluido: {message}"


def start_background_process_tool(command: str, cwd: str = None) -> str:
    pm = ProcessManager()
    pid_id = pm.start_process(command, cwd)
    return f"🚀 Proceso iniciado en segundo plano con ID '{pid_id}'. Consulta su estado con get_process_status('{pid_id}')."


def get_process_status_tool(process_id: str) -> str:
    pm = ProcessManager()
    status = pm.get_status(process_id)
    if not status.get("success"):
        return f"❌ Error: {status.get('error')}"
    state = "🟢 EN EJECUCIÓN" if status["is_running"] else f"⚪ FINALIZADO (Código {status['exit_code']})"
    output = f"Estado de {status['process_id']} ({state}) [PID: {status['pid']}]:\n"
    if status.get("stdout"):
        output += f"--- STDOUT ---\n{status['stdout']}\n"
    if status.get("stderr"):
        output += f"--- STDERR ---\n{status['stderr']}\n"
    return output.strip()


def cancel_process_tool(process_id: str) -> str:
    pm = ProcessManager()
    res = pm.cancel_process(process_id)
    if res.get("success"):
        return f"🛑 {res.get('message')}"
    return f"❌ Error: {res.get('error')}"


def safe_checkpoint_tool(message: str = "Punto de control automático") -> str:
    from agent.checkpoints import SafeCheckpointManager
    mgr = SafeCheckpointManager()
    snap_id = mgr.create_checkpoint(message)
    return f"✅ Checkpoint seguro creado: '{snap_id}' ({message})."


def safe_undo_checkpoint_tool(snapshot_id: str = None) -> str:
    from agent.checkpoints import SafeCheckpointManager
    mgr = SafeCheckpointManager()
    if not snapshot_id:
        checkpoints = mgr.list_checkpoints()
        if not checkpoints:
            return "❌ No existen checkpoints seguros registrados para restaurar."
        snapshot_id = checkpoints[0]["snapshot_id"]
    success, msg = mgr.restore_checkpoint(snapshot_id)
    if success:
        return f"✅ {msg}"
    return f"❌ Fallo al restaurar checkpoint: {msg}"


def execute_skill_tool(skill_name: str, target: str = None) -> str:
    from agent.skills import execute_skill
    return execute_skill(skill_name, target)


# Mapa de ejecutores en Python
TOOL_HANDLERS: Dict[str, Callable[..., Any]] = {
    "read_file": read_file,
    "cat": read_file,
    "view_file": read_file,
    "edit_file": edit_file,
    "write_file": write_file,
    "create_file": write_file,
    "new_file": write_file,
    "save_file": write_file,
    "delete_file": delete_file,
    "move_file": move_file,
    "run_command": run_command,
    "exec": run_command,
    "execute_command": run_command,
    "bash": run_command,
    "sh": run_command,
    "terminal": run_command,
    "search_codebase": search_codebase,
    "grep_search": search_codebase,
    "grep": search_codebase,
    "list_directory": list_directory,
    "get_file_outline": get_file_outline,
    "get_repo_map": generate_repo_map,
    "delegate_task": delegate_task,
    "delegate_research": delegate_research,
    "delegate_test": delegate_test,
    "search_web": search_web,
    "fetch_web_page": fetch_web_page,
    "create_checkpoint": create_checkpoint,
    "undo_checkpoint": undo_checkpoint,
    "get_git_diff": get_git_diff,
    "get_git_status": get_git_status,
    "apply_patch": apply_patch_tool,
    "get_diagnostics": get_diagnostics,
    "run_tests": run_tests_tool,
    "pytest": run_tests_tool,
    "test": run_tests_tool,
    "test_runner": run_tests_tool,
    "conclude_turn": conclude_turn_tool,
    "finish_turn": conclude_turn_tool,
    "complete_task": conclude_turn_tool,
    "finish": conclude_turn_tool,
    "done": conclude_turn_tool,
    "start_background_process": start_background_process_tool,
    "get_process_status": get_process_status_tool,
    "cancel_process": cancel_process_tool,
    "safe_checkpoint": safe_checkpoint_tool,
    "safe_undo_checkpoint": safe_undo_checkpoint_tool,
    "update_plan": update_plan,
    "get_plan": get_plan,
    "remember_fact": remember_fact,
    "search_memory": search_memory,
    "list_memories": list_memories,
    "ask_question": ask_question_tool,
    "create_artifact": create_artifact_tool,
    "update_artifact": update_artifact_tool,
    "read_artifact": read_artifact_tool,
    "list_artifacts": list_artifacts_tool,
    "request_approval": request_approval,
    "get_project_instructions": get_project_instructions,
    "find_definition": find_definition,
    "find_references": find_references,
    "get_dependencies": get_dependencies,
    "get_hardware_vram_status": get_hardware_vram_status,
    "execute_skill": execute_skill_tool,
    "list_mcp_tools": list_mcp_tools,
    "call_mcp_tool": call_mcp_tool_wrapper,
}

TOOL_ALIASES: Dict[str, str] = {
    # Análisis e inspección de código
    "analyze_file": "get_file_outline",
    "inspect_file": "get_file_outline",
    "examine_file": "get_file_outline",
    "inspect_code": "get_file_outline",
    "get_outline": "get_file_outline",
    # Lectura de archivos
    "view_file": "read_file",
    "show_file": "read_file",
    "cat_file": "read_file",
    "open_file": "read_file",
    "get_file_content": "read_file",
    # Listado de archivos / carpetas
    "list_files": "list_directory",
    "dir": "list_directory",
    "ls": "list_directory",
    "get_files": "list_directory",
    "tree": "list_directory",
    # Búsqueda
    "grep": "search_codebase",
    "find_code": "search_codebase",
    "search_text": "search_codebase",
    "search_files": "search_codebase",
    # Ejecución de comandos
    "exec": "run_command",
    "execute_command": "run_command",
    "bash": "run_command",
    "sh": "run_command",
    "terminal": "run_command",
    # Instrucciones del repositorio
    "get_repo_instructions": "get_project_instructions",
    "get_agent_instructions": "get_project_instructions",
    "repo_instructions": "get_project_instructions",
    # Creación / edición de archivos
    "create_file": "write_file",
    "new_file": "write_file",
    "save_file": "write_file",
    "write_code": "write_file",
    "create_code": "write_file",
    "generate_code": "write_file",
    # Tests
    "run_test": "run_tests",
    "test": "run_tests",
    "pytest": "run_tests",
    # Aclaración y preguntas interactivas
    "ask_user": "ask_question",
    "clarify_question": "ask_question",
    "clarify_requirements": "ask_question",
    "ask": "ask_question",
}


def execute_tool(name: str, arguments: Any) -> str:
    """
    Ejecuta una herramienta por nombre validando y normalizando sus argumentos.
    """
    name = TOOL_ALIASES.get(name, name)

    if name not in TOOL_HANDLERS:
        name_lower = name.lower()
        if "instruction" in name_lower or "agent" in name_lower:
            return (
                f"Error: La herramienta '{name}' no existe en el catálogo registrado.\n"
                f"• Si deseas leer las instrucciones del repositorio o proyecto, usa 'read_file(path=\"README.md\")'.\n"
                f"• Si el agente está en modo ASK, está TERMINANTEMENTE PROHIBIDO crear archivos con 'write_file'. Responde la consulta inspeccionando el código existente con 'read_file'."
            )
        valid_tools = ", ".join(sorted(TOOL_HANDLERS.keys())[:15])
        return (
            f"Error: La herramienta '{name}' no existe en el catálogo registrado.\n"
            f"• Herramientas válidas disponibles: {valid_tools}...\n"
            f"• Si deseas inspeccionar código o archivos, utiliza 'read_file' o 'search_codebase'. NUNCA intentes crear archivos con 'write_file' para suplir una herramienta inexistente."
        )

    handler = TOOL_HANDLERS[name]

    # Asegurar que arguments sea un diccionario
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return f"Error: No se pudo decodificar el JSON de argumentos para '{name}': {arguments}"

    if not isinstance(arguments, dict):
        arguments = {}

    # Normalización de alias comunes de parámetros enviados por LLMs locales
    if "path" not in arguments:
        for p_alias in ["file_path", "filepath", "filename", "file"]:
            if p_alias in arguments:
                arguments["path"] = arguments.pop(p_alias)
                break

    if name == "edit_file" and "target" not in arguments:
        if "new_content" in arguments or "content" in arguments:
            cnt = str(arguments.get("new_content") or arguments.get("content") or "")
            target_p = Path(str(arguments.get("path", "")))
            is_full_rewrite = False
            if not target_p.exists():
                is_full_rewrite = True
            else:
                try:
                    existing_len = len(target_p.read_text(encoding="utf-8", errors="replace"))
                    if len(cnt) >= max(50, int(existing_len * 0.6)) and ("def " in cnt or "class " in cnt):
                        is_full_rewrite = True
                except Exception:
                    is_full_rewrite = True
            if is_full_rewrite:
                name = "write_file"
                handler = TOOL_HANDLERS["write_file"]
                if "new_content" in arguments:
                    arguments["content"] = arguments.pop("new_content")

    if "content" not in arguments:
        for c_alias in ["text", "code", "body", "new_content"]:
            if c_alias in arguments and name in ["write_file", "create_file", "new_file", "save_file", "write_code"]:
                arguments["content"] = arguments.pop(c_alias)
                break

    if "command" not in arguments:
        for cmd_alias in ["cmd", "script", "instruction"]:
            if cmd_alias in arguments and name in ["run_command", "exec", "execute_command", "bash", "sh", "terminal"]:
                arguments["command"] = arguments.pop(cmd_alias)
                break

    if "test_target" not in arguments:
        for t_alias in ["target", "path", "file", "target_file"]:
            if t_alias in arguments and name in ["run_tests", "pytest", "test", "test_runner"]:
                arguments["test_target"] = arguments.pop(t_alias)
                break

    try:
        result = handler(**arguments)
        return str(result)
    except TypeError as te:
        return f"Error en los parámetros de la herramienta '{name}': {str(te)}"
    except Exception as e:
        return f"Error durante la ejecución de la herramienta '{name}': {str(e)}"


def execute_tools_parallel(calls: List[tuple], max_workers: int = 4) -> List[str]:
    """
    Ejecuta un lote de herramientas pasivas concurrentemente usando un ThreadPoolExecutor.
    Inspirado en la ejecución concurrente de Antigravity para reducir la latencia de lectura multi-archivo.
    """
    if not calls:
        return []
    if len(calls) == 1:
        name, args = calls[0]
        return [execute_tool(name, args)]

    results: List[Any] = [None] * len(calls)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls))) as executor:
        futures = {
            executor.submit(execute_tool, name, args): idx
            for idx, (name, args) in enumerate(calls)
        }
        for f in futures:
            idx = futures[f]
            results[idx] = f.result()
    return [str(r) for r in results]


# Herramientas permitidas por modo operativo para optimización de tokens en VRAM
ASK_MODE_TOOL_NAMES = {
    "read_file",
    "list_directory",
    "get_repo_map",
    "get_file_outline",
    "search_codebase",
    "grep_search",
    "get_project_instructions",
    "search_memory",
    "list_memories",
    "get_hardware_vram_status",
    "search_web",
    "fetch_web_page",
    "get_git_status",
    "get_git_diff",
    "find_definition",
    "find_references",
    "get_dependencies",
    "list_mcp_tools",
}

PLAN_MODE_TOOL_NAMES = {
    "get_repo_map",
    "get_file_outline",
    "read_file",
    "list_directory",
    "search_codebase",
    "grep_search",
    "update_plan",
    "get_plan",
    "ask_question",
    "create_artifact",
    "update_artifact",
    "read_artifact",
    "list_artifacts",
    "search_memory",
    "list_memories",
    "get_project_instructions",
    "search_web",
    "fetch_web_page",
    "get_git_status",
}

REVIEW_MODE_TOOL_NAMES = {
    "get_git_diff",
    "get_git_status",
    "read_file",
    "get_file_outline",
    "search_codebase",
    "grep_search",
    "get_diagnostics",
    "run_tests",
    "request_approval",
    "edit_file",
    "write_file",
    "apply_patch",
}


def get_tools_schema_for_mode(mode: str = "agent") -> List[Dict[str, Any]]:
    """
    Filtra dinámicamente el esquema de herramientas expuesto a Ollama según el modo operativo.
    Reduce drásticamente el consumo de tokens y previene la confusión de herramientas en LLMs locales.
    """
    mode_clean = (mode or "agent").lower().strip()
    if mode_clean == "ask":
        return [t for t in TOOLS_SCHEMA if t.get("function", {}).get("name") in ASK_MODE_TOOL_NAMES]
    elif mode_clean == "plan":
        return [t for t in TOOLS_SCHEMA if t.get("function", {}).get("name") in PLAN_MODE_TOOL_NAMES]
    elif mode_clean == "review":
        return [t for t in TOOLS_SCHEMA if t.get("function", {}).get("name") in REVIEW_MODE_TOOL_NAMES]
    return TOOLS_SCHEMA
