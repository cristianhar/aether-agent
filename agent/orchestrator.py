"""
Orquestador y Bucle ReAct principal para el Agente AETHER.
Integra máquina de estados, token de cancelación, motor de permisos, persistencia SQLite y telemetría.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx

from agent.hooks import HookManager
from agent.memory import ConversationMemory
from agent.permissions import PermissionDecision, PermissionEngine, PermissionRequest
from agent.prompts import SYSTEM_PROMPT
from agent.safety import check_command_safety
from agent.session import SessionManager
from agent.state import AgentState, CancellationToken
from agent.telemetry import TelemetryLogger
from tools.base import PermissionLevel, ToolCategory
from tools.registry import TOOLS_SCHEMA, execute_tool


def get_tool_metadata(name: str) -> Tuple[ToolCategory, PermissionLevel]:
    """Clasifica cada herramienta según su categoría de riesgo y permisos."""
    if name in [
        "read_file", "search_codebase", "list_directory", "get_file_outline",
        "get_repo_map", "get_diagnostics", "get_process_status",
        "find_definition", "find_references", "get_dependencies", "get_hardware_vram_status",
        "list_mcp_tools"
    ]:
        category = ToolCategory.FILESYSTEM if name in ["read_file", "search_codebase", "list_directory"] else ToolCategory.CODE_INTELLIGENCE
        return category, PermissionLevel.READ_ONLY

    if name in ["write_file", "edit_file", "delete_file", "move_file", "apply_patch"]:
        return ToolCategory.FILESYSTEM, PermissionLevel.WORKSPACE_WRITE

    if name in ["run_command", "run_tests", "start_background_process", "cancel_process", "call_mcp_tool"]:
        return ToolCategory.EXECUTION, PermissionLevel.COMMAND_EXECUTE

    if name in ["create_checkpoint", "undo_checkpoint", "safe_checkpoint", "safe_undo_checkpoint", "get_git_diff", "get_git_status"]:
        return ToolCategory.GIT, PermissionLevel.WORKSPACE_WRITE

    return ToolCategory.AGENT_MANAGEMENT, PermissionLevel.READ_ONLY


def detect_action_cycle(action_history: List[str], max_period: int = 3, min_repeats: int = 2) -> Optional[Tuple[int, List[str]]]:
    """
    Algoritmo Matemático de Detección de Ciclos Periódicos (Sliding Window Periodicity).
    Detecta de forma genérica y agnóstica si la secuencia de acciones recientes forma un ciclo
    periódico de longitud p in [1, max_period] repetido al menos min_repeats veces.
    Retorna (periodo_p, ciclo_de_acciones) si se detecta un bucle, o None si no hay ciclo.
    """
    n = len(action_history)
    for p in range(1, max_period + 1):
        required_len = p * min_repeats
        if n < required_len:
            continue
        window = action_history[-required_len:]
        pattern = window[:p]
        is_cycle = True
        for i in range(required_len):
            if window[i] != pattern[i % p]:
                is_cycle = False
                break
        if is_cycle:
            return p, pattern
    return None


class AgentOrchestrator:
    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        host: str = "http://127.0.0.1:11434",
        system_prompt: str = SYSTEM_PROMPT,
        max_iterations: int = 25,
        session_id: Optional[str] = None,
        session_manager: Optional[SessionManager] = None,
        permission_engine: Optional[PermissionEngine] = None,
        telemetry_logger: Optional[TelemetryLogger] = None,
        on_thought: Optional[Callable[[str], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        on_state_change: Optional[Callable[[AgentState], None]] = None,
        confirm_callback: Optional[Callable[[str], bool]] = None,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.max_iterations = max_iterations

        # Ingestión dinámica de reglas de proyecto (.aetherrules, AGENTS.md, CONVENTIONS.md, .cursorrules)
        loaded_rules = []
        for rules_name in [".aetherrules", "AGENTS.md", "CONVENTIONS.md", ".cursorrules"]:
            rules_path = Path.cwd() / rules_name
            if rules_path.is_file():
                try:
                    custom_rules = rules_path.read_text(encoding="utf-8", errors="replace").strip()
                    if custom_rules:
                        loaded_rules.append(f"<custom_project_rules source='{rules_name}'>\n{custom_rules}\n</custom_project_rules>")
                except Exception:
                    pass

        modular_rules_dir = Path.cwd() / ".aether" / "rules"
        if modular_rules_dir.is_dir():
            for r_file in modular_rules_dir.glob("*.md"):
                try:
                    r_text = r_file.read_text(encoding="utf-8", errors="replace").strip()
                    if r_text:
                        loaded_rules.append(f"<custom_project_rules source='{r_file.name}'>\n{r_text}\n</custom_project_rules>")
                except Exception:
                    pass

        if loaded_rules:
            system_prompt += "\n\n" + "\n\n".join(loaded_rules)

        self.memory = ConversationMemory(system_prompt=system_prompt)
        self.hooks = HookManager(mode="agent")
        self.permissions = permission_engine or PermissionEngine()
        self.session_manager = session_manager or SessionManager()
        self.telemetry = telemetry_logger or TelemetryLogger()

        self.session_id = session_id or self.session_manager.create_session(model=self.model)
        self.state = AgentState.IDLE
        self.turn_counter = 0

        # Callbacks de UI (para Rich CLI)
        self.on_thought = on_thought
        self.on_token = on_token
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result
        self.on_state_change = on_state_change
        self.confirm_callback = confirm_callback

    def set_state(self, new_state: AgentState):
        """Actualiza el estado formal del agente y notifica a observadores."""
        self.state = new_state
        self.session_manager.update_session_state(self.session_id, new_state.value)
        if self.on_state_change:
            self.on_state_change(new_state)

    def check_ollama_alive(self) -> bool:
        """Verifica si el servicio de Ollama está respondiendo."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.host}/api/version")
                return res.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _extract_tool_calls_from_content(content: str) -> List[Dict[str, Any]]:
        """
        Extrae llamadas a herramientas cuando Ollama/Qwen las devuelve
        embebidas en 'content' (JSON plano o bloques markdown), o sintetiza
        write_file si el modelo devolvió bloques de código pasivos.
        """
        if not content or not content.strip():
            return []

        extracted = []

        # 1. Bloques markdown de herramientas ```json ... ```
        blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        for b in blocks:
            b = b.strip()
            try:
                data = json.loads(b)
                if isinstance(data, dict):
                    if "name" in data and "arguments" in data:
                        extracted.append({"function": data})
                    elif "function" in data:
                        extracted.append(data)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "name" in item and "arguments" in item:
                            extracted.append({"function": item})
            except Exception:
                pass

        if extracted:
            return extracted

        # 2. JSON directo en el contenido
        try:
            data = json.loads(content.strip())
            if isinstance(data, dict):
                if "name" in data and "arguments" in data:
                    return [{"function": data}]
                elif "function" in data:
                    return [data]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item and "arguments" in item:
                        extracted.append({"function": item})
                if extracted:
                    return extracted
        except Exception:
            pass

        # 3. Escaneo con JSONDecoder para llamadas embebidas
        decoder = json.JSONDecoder()
        pos = 0
        raw = content
        while pos < len(raw):
            idx = raw.find('{', pos)
            if idx == -1:
                break
            try:
                obj, end_pos = decoder.raw_decode(raw[idx:])
                if isinstance(obj, dict):
                    if "name" in obj and "arguments" in obj:
                        extracted.append({"function": obj})
                        pos = idx + end_pos
                        continue
                    elif "function" in obj and isinstance(obj["function"], dict):
                        extracted.append(obj)
                        pos = idx + end_pos
                        continue
                pos = idx + 1
            except Exception:
                pos = idx + 1

        if extracted:
            return extracted

        # 4. Rescate resiliente por expresiones regulares para JSON malformado (comillas o escapes inválidos de modelos 7B)
        name_match = re.search(r'"name":\s*"([a-zA-Z0-9_]+)"', content)
        if name_match:
            tool_name = name_match.group(1)
            # Rescate para write_file
            if tool_name == "write_file":
                p_match = re.search(r'"path":\s*"([^"]+)"', content)
                c_match = re.search(r'"content":\s*"(.*)"\s*\}\s*\}', content, re.DOTALL)
                if p_match and c_match:
                    raw_content = c_match.group(1)
                    clean_content = (
                        raw_content.replace("\\n", "\n")
                        .replace("\\t", "\t")
                        .replace('\\"', '"')
                    )
                    clean_content = re.sub(r'f""\\+"', 'f"""', clean_content)
                    clean_content = re.sub(r'""\\+"', '"""', clean_content)
                    clean_content = clean_content.replace('\\\\', '\\')
                    return [{
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "path": p_match.group(1),
                                "content": clean_content
                            }
                        }
                    }]

            # Rescate para run_command
            elif tool_name == "run_command":
                cmd_match = re.search(r'"command":\s*"([^"]+)"', content)
                if cmd_match:
                    return [{
                        "function": {
                            "name": "run_command",
                            "arguments": {
                                "command": cmd_match.group(1)
                            }
                        }
                    }]

            # Rescate para edit_file
            elif tool_name == "edit_file":
                p_match = re.search(r'"path":\s*"([^"]+)"', content)
                t_match = re.search(r'"target":\s*"(.*?)"(?:\s*,\s*"replacement")', content, re.DOTALL)
                r_match = re.search(r'"replacement":\s*"(.*?)"\s*\}\s*\}', content, re.DOTALL)
                if p_match and t_match and r_match:
                    return [{
                        "function": {
                            "name": "edit_file",
                            "arguments": {
                                "path": p_match.group(1),
                                "target": t_match.group(1).replace("\\n", "\n").replace('\\"', '"'),
                                "replacement": r_match.group(1).replace("\\n", "\n").replace('\\"', '"')
                            }
                        }
                    }]

        return []

    def _check_circuit_breaker(
        self,
        tool_name: str,
        args: Dict[str, Any],
        failed_commands: Optional[set] = None,
        files_modified_since_cmd_fail: bool = False,
        known_syntax_error_files: Optional[set] = None,
        last_failed_tool_key: Optional[str] = None,
        last_failed_command: Optional[str] = None,
        consecutive_edit_failures: int = 0,
        recent_failed_tools: Optional[list] = None,
        consecutive_tool_failures: int = 0,
        executed_edits: Optional[set] = None,
        action_history: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Circuit Breaker Anti-Bucle Universal:
        Previene bucles repetitivos de forma matemática y basada en estado:
        0. Detección matemática universal de ciclos periódicos (periodos p=1, 2, 3) sin mutación de disco.
        1. Repite comandos de consola que ya fallaron sin haber modificado ningún archivo.
        2. Intenta ejecutar un script que contiene un SyntaxError detectado sin haberlo editado.
        3. Llama repetidamente a la misma herramienta con argumentos idénticos inmediatamente después de haber fallado.
        4. Alterna a ciegas entre herramientas de edición sin leer el código real.
        5. Cae en un bucle alternante oscilante (ping-pong) entre dos herramientas diferentes.
        6. Repite exactamente la misma edición que no produjo cambios o no resolvió el fallo.
        """
        passive_tools = {
            "read_file", "list_directory", "search_codebase", "get_file_outline",
            "get_git_status", "get_git_diff", "get_diagnostics", "find_definition",
            "find_references", "get_dependencies", "get_hardware_vram_status", "get_repo_map"
        }

        tool_call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"

        # Regla 0: Detector Matemático Universal de Ciclos Periódicos (Periodos p=1, 2, 3)
        # Solo aplica a herramientas activas de mutación o ejecución (no a inspección pasiva)
        if tool_name not in passive_tools and action_history and len(action_history) >= 2:
            target_path_str = str(args.get("path", "") or "")
            target_file_name = Path(target_path_str).name if target_path_str else ""
            is_fixing_syntax = (
                tool_name in ["edit_file", "write_file"]
                and bool(known_syntax_error_files)
                and any(
                    err_f in target_path_str
                    or (target_file_name and target_file_name in err_f)
                    or (target_file_name and Path(err_f).name == target_file_name)
                    for err_f in known_syntax_error_files
                )
            )
            if not is_fixing_syntax:
                current_signature = f"{tool_name}:{args.get('path') or args.get('command') or ''}"
                candidate_history = list(action_history) + [current_signature]
                cycle = detect_action_cycle(candidate_history, max_period=3, min_repeats=2)
                if cycle and not files_modified_since_cmd_fail:
                    period, pattern = cycle
                    cycle_str = " ➔ ".join(pattern)
                    msg = (
                        f"⛔ [CIRCUIT BREAKER UNIVERSAL - CICLO PERIÓDICO DETECTADO (Periodo {period})]:\n"
                        f"Has caído en una secuencia cíclica repetitiva de acciones: {cycle_str}.\n"
                        "Esta secuencia ya se ejecutó previamente y no produjo ninguna modificación efectiva en el estado del disco.\n"
                        "• ACCIÓN OBLIGATORIA: Rompe el ciclo inmediatamente. Si una prueba falla o una edición no surte efecto, "
                        "revisa la causa raíz del error o reescribe el archivo afectado completamente usando 'write_file'."
                    )
                    return True, msg

        # Combinar failed_commands con last_failed_command para retrocompatibilidad
        active_failed_cmds = set(failed_commands or set())
        if last_failed_command:
            active_failed_cmds.add(last_failed_command.strip().lower())

        # Regla 1: run_command que ya falló previamente sin haber modificado archivos
        if tool_name == "run_command":
            cmd_norm = args.get("command", "").strip().lower()
            if active_failed_cmds and cmd_norm in active_failed_cmds and not files_modified_since_cmd_fail:
                if consecutive_edit_failures >= 1:
                    action_hint = "• ACCIÓN OBLIGATORIA: Tus intentos de edición no han modificado el archivo exitosamente. Usa 'read_file' para inspeccionar el archivo o reescríbelo con 'write_file'. NO vuelvas a ejecutar el mismo comando sin cambios en disco."
                else:
                    action_hint = "• ACCIÓN OBLIGATORIA: Si aún no has corregido el código, usa 'read_file' para inspeccionarlo, 'edit_file' para modificar el bloque exacto, o 'write_file' para reescribirlo. Si la verificación ya concluyó con éxito, concluye el turno e informa al usuario en tu respuesta final para que lo ejecute en su propia terminal."
                msg = (
                    f"⛔ [CIRCUIT BREAKER]: El comando '{args.get('command')}' ya falló previamente y NO has modificado ningún archivo en el disco desde entonces.\n"
                    "• Volver a ejecutar el mismo comando sin cambios en disco producirá exactamente el mismo error.\n"
                    "• Si faltaba una librería o paquete, instálala usando 'pip install <libreria>'.\n"
                    f"{action_hint}"
                )
                return True, msg

            # Regla 2: Ejecución de script con SyntaxError pendiente
            if known_syntax_error_files:
                for err_file in list(known_syntax_error_files):
                    err_base = Path(err_file).name.lower()
                    if err_base in cmd_norm:
                        msg = (
                            f"⛔ [CIRCUIT BREAKER]: El archivo '{err_file}' tiene un SyntaxError pendiente de corrección en el disco.\n"
                            f"No puedes ejecutar '{args.get('command')}' hasta haber corregido la sintaxis de '{err_file}'.\n"
                            f"ACCIÓN OBLIGATORIA: Llama a 'edit_file' con path='{err_file}' para corregir la sintaxis antes de volver a ejecutar."
                        )
                        return True, msg

        # Regla 3: Herramienta idéntica inmediatamente consecutiva tras un fallo previo
        if last_failed_tool_key and last_failed_tool_key == tool_call_key:
            msg = (
                f"⛔ [CIRCUIT BREAKER]: La herramienta '{tool_name}' con estos mismos argumentos ya fue ejecutada inmediatamente antes y falló.\n"
                "Está PROHIBIDO repetir la misma acción fallida consecutivamente sin cambiar los parámetros.\n"
                "Cambia tus argumentos o utiliza una herramienta diferente (ej: edit_file, read_file o search_codebase)."
            )
            return True, msg

        # Regla 4: Bloqueo de bucle alternante de edición a ciegas (edit_file / apply_patch fallando >= 2 veces)
        if tool_name in ("edit_file", "apply_patch") and consecutive_edit_failures >= 2:
            target_p = args.get("path", "")
            file_preview = ""
            try:
                real_p = Path(target_p).resolve()
                if real_p.exists() and real_p.is_file():
                    file_text = real_p.read_text(encoding="utf-8", errors="replace")
                    file_preview = f"\n\n📄 [CÓDIGO REAL EN DISCO DE '{target_p}']:\n```python\n{file_text}\n```\n"
            except Exception:
                pass

            msg = (
                f"⛔ [CIRCUIT BREAKER - EDICIÓN A CIEGAS BLOQUEADA]: Llevas {consecutive_edit_failures} intentos consecutivos fallidos modificando '{target_p}' porque el texto 'target' no coincide con el archivo en disco.\n"
                "Está TERMINANTEMENTE PROHIBIDO seguir enviando llamadas de edición a ciegas sin ver el código real.\n"
                f"Para ayudarte, aquí tienes el código físico actual del archivo:{file_preview}"
                f"• ACCIÓN OBLIGATORIA: Reescribe el módulo completo usando 'write_file(path=\"{target_p}\", content=...)' con el código final corregido, o lee líneas adicionales con 'read_file(path=\"{target_p}\")'."
            )
            return True, msg

        # Regla 5: Detección de bucle oscilante multi-herramienta (Ping-Pong entre 2 herramientas fallidas)
        if recent_failed_tools and len(recent_failed_tools) >= 3 and consecutive_tool_failures >= 3:
            w = recent_failed_tools[-3:] + [tool_name]
            # Patrón A-B-A-B
            if w[0] == w[2] and w[1] == w[3] and w[0] != w[1]:
                # Si la herramienta es edit_file pero está intentando modificar un archivo diferente al fallido, no bloquear
                last_edit_path = None
                for t in reversed(action_history or []):
                    if t.startswith("edit_file:"):
                        last_edit_path = t[len("edit_file:"):].strip()
                        break
                current_path = str(args.get("path") or "").strip()
                is_switching_file = bool(last_edit_path and current_path and Path(last_edit_path).name != Path(current_path).name)

                if not is_switching_file:
                    msg = (
                        f"⛔ [CIRCUIT BREAKER - BUCLE ALTERNANTE DETECTADO]: Has entrado en un bucle repetitivo alternando entre '{w[0]}' y '{w[1]}'.\n"
                        f"Ambas herramientas están fallando sucesivamente porque no has modificado la causa real del problema.\n"
                        f"• ACCIÓN OBLIGATORIA: Detén la alternancia. Si necesitas corregir un archivo, usa 'write_file' para reescribirlo completamente con la solución correcta o inspecciónalo primero con 'read_file'."
                    )
                    return True, msg

        # Regla 6: Bloqueo de ediciones repetidas con argumentos idénticos
        if tool_name in ("edit_file", "apply_patch") and executed_edits:
            edit_key = f"{args.get('path')}:{args.get('target', '')}"
            if edit_key in executed_edits:
                msg = (
                    f"⛔ [CIRCUIT BREAKER - EDICIÓN REPETIDA BLOQUEADA]: Ya intentaste exactamente esta misma edición con 'target' en '{args.get('path')}'.\n"
                    "Esa edición previa no produjo el resultado esperado o no resolvió el error.\n"
                    f"• ACCIÓN OBLIGATORIA: Aplica una edición diferente, o reescribe el archivo completamente usando 'write_file(path=\"{args.get('path')}\", content=...)'."
                )
                return True, msg

        return False, ""

    def run_turn(self, user_prompt: str, cancellation_token: Optional[CancellationToken] = None) -> str:
        """
        Ejecuta el bucle ReAct completo para una solicitud del usuario.
        Monitorea el token de cancelación y registra métricas y persistencia.
        """
        turn_start_time = time.perf_counter()
        self.turn_counter += 1
        current_turn = self.turn_counter

        self.set_state(AgentState.RUNNING)
        self.memory.add_user_message(user_prompt)
        self.session_manager.save_message(self.session_id, current_turn, role="user", content=user_prompt)

        final_answer = ""
        total_tool_calls = 0
        total_tool_failures = 0

        # Variables de control del Circuit Breaker Anti-Bucle
        failed_commands: set = set()
        files_modified_since_cmd_fail: bool = False
        last_failed_tool_key: Optional[str] = None
        known_syntax_error_files: set = set()
        last_assertion_error: Optional[str] = None
        assertion_error_repeat_count: int = 0
        consecutive_edit_failures: int = 0
        consecutive_tool_failures: int = 0
        recent_failed_tools: list = []
        executed_edits: set = set()
        action_history: List[str] = []

        for iteration in range(1, self.max_iterations + 1):
            # Seguridad: Detener bucles improductivos si hay demasiados fallos consecutivos sin ningún éxito
            if consecutive_tool_failures >= 6:
                final_answer = (
                    "⚠️ [CIRCUIT BREAKER GENERAL]: Se detuvo la ejecución autónoma tras 6 intentos fallidos consecutivos "
                    "para evitar bucles improductivos y proteger los recursos de la máquina.\n"
                    "• Diagnóstico: El modelo no logró mutar los archivos en una dirección que resolviera el fallo.\n"
                    "• Acciones recomendadas:\n"
                    "  1. Revisa los archivos generados y los diagnósticos emitidos arriba.\n"
                    "  2. Si deseas revertir los cambios de este turno al estado previo intacto, ejecuta el comando '/undo'.\n"
                    "  3. Para replantear la tarea con instrucciones más específicas, escribe tu solicitud en el chat."
                )
                self.memory.add_assistant_message(content=final_answer)
                self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=final_answer)
                self.set_state(AgentState.COMPLETED)
                break
            # Comprobar si se solicitó cancelación
            if cancellation_token and cancellation_token.is_cancelled:
                self.set_state(AgentState.CANCELLED)
                cancel_msg = cancellation_token.reason or "Operación cancelada por el usuario."
                self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=cancel_msg)
                return cancel_msg

            messages = self.memory.get_messages()

            payload = {
                "model": self.model,
                "messages": messages,
                "tools": TOOLS_SCHEMA,
                "stream": bool(self.on_token),
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 8192,
                }
            }

            content = ""
            tool_calls = []

            try:
                with httpx.Client(timeout=180.0) as client:
                    if self.on_token:
                        with client.stream("POST", f"{self.host}/api/chat", json=payload) as resp:
                            resp.raise_for_status()
                            for line in resp.iter_lines():
                                if cancellation_token and cancellation_token.is_cancelled:
                                    break
                                if not line:
                                    continue
                                chunk = json.loads(line)
                                msg_chunk = chunk.get("message", {})
                                token = msg_chunk.get("content", "")
                                if token:
                                    content += token
                                    self.on_token(token)
                                if msg_chunk.get("tool_calls"):
                                    tool_calls.extend(msg_chunk["tool_calls"])
                    else:
                        resp = client.post(f"{self.host}/api/chat", json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        msg = data.get("message", {})
                        content = msg.get("content", "")
                        tool_calls = msg.get("tool_calls", [])
            except httpx.ConnectError:
                self.set_state(AgentState.FAILED)
                return (
                    f"Error de conexión: No se pudo contactar a Ollama en {self.host}.\n"
                    "Asegúrate de que Ollama esté ejecutándose ('ollama serve')."
                )
            except Exception as e:
                self.set_state(AgentState.FAILED)
                return f"Error al comunicar con Ollama: {str(e)}"

            if cancellation_token and cancellation_token.is_cancelled:
                self.set_state(AgentState.CANCELLED)
                return cancellation_token.reason or "Operación cancelada por el usuario."

            # Extracción del bloque de pensamiento analítico <thought>...</thought>
            thought_text = ""
            if content:
                thought_match = re.search(r"<thought>([\s\S]*?)</thought>", content, re.IGNORECASE)
                if thought_match:
                    thought_text = thought_match.group(1).strip()
                    content = re.sub(r"<thought>[\s\S]*?</thought>", "", content, flags=re.IGNORECASE).strip()

            # Fallback inteligente
            if not tool_calls and content:
                extracted = self._extract_tool_calls_from_content(content)
                if extracted:
                    tool_calls = extracted

            # Notificar pensamiento limpio si no hubo streaming de tokens
            if self.on_thought:
                if thought_text:
                    self.on_thought(thought_text)
                elif content and not self.on_token:
                    clean_thought = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", content).strip()
                    if clean_thought.startswith("{") and clean_thought.endswith("}"):
                        clean_thought = ""
                    if clean_thought:
                        self.on_thought(clean_thought)

            # Si el modelo no solicita ninguna herramienta, verificar si era un intento de JSON malformado
            if not tool_calls:
                # Detección de tool call fantasma no parseable
                if '"name":' in content and ('"arguments":' in content or '"path":' in content or '"command":' in content):
                    if iteration < self.max_iterations:
                        self.memory.add_assistant_message(content=content)
                        retry_hint = (
                            "[SISTEMA AETHER]: Se detectó que intentaste emitir una llamada a herramienta en formato JSON, "
                            "pero no pudo ser ejecutada por errores de formato o sintaxis. "
                            "Por favor emite la llamada usando la herramienta directamente sin escapar triples comillas de Python dentro de strings."
                        )
                        self.memory.add_user_message(content=retry_hint)
                        continue

                self.memory.add_assistant_message(content=content)
                self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=content)
                final_answer = content
                self.set_state(AgentState.COMPLETED)
                break

            # Si hay llamadas a herramientas, registrar mensaje
            self.memory.add_assistant_message(content=content, tool_calls=tool_calls)
            self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=content, tool_calls=tool_calls)

            # Optimización de concurrencia Antigravity: Si todas las herramientas del turno son de solo lectura,
            # pre-ejecutar en paralelo con ThreadPoolExecutor para reducir la latencia acumulada
            parallel_results: Dict[int, str] = {}
            parsed_calls = []
            for tc in tool_calls:
                func_data = tc.get("function", {})
                t_name = func_data.get("name", "")
                t_args = func_data.get("arguments", {})
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except Exception:
                        t_args = {}
                parsed_calls.append((t_name, t_args))

            all_read_only = len(tool_calls) > 1 and all(
                get_tool_metadata(t_name)[1] == PermissionLevel.READ_ONLY
                for t_name, _ in parsed_calls
            )

            if all_read_only:
                from tools.registry import execute_tools_parallel
                raw_results = execute_tools_parallel(parsed_calls, max_workers=min(4, len(parsed_calls)))
                for idx, res in enumerate(raw_results):
                    parallel_results[idx] = res

            # Procesar cada herramienta solicitada
            for idx, tc in enumerate(tool_calls):
                if cancellation_token and cancellation_token.is_cancelled:
                    self.set_state(AgentState.CANCELLED)
                    return cancellation_token.reason or "Operación cancelada por el usuario."

                total_tool_calls += 1
                func_data = tc.get("function", {})
                tool_name = func_data.get("name", "")
                args = func_data.get("arguments", {})

                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}

                category, perm_level = get_tool_metadata(tool_name)

                # Notificar a la UI
                if self.on_tool_call:
                    self.on_tool_call(tool_name, args)

                # 1. Evaluación de Motor de Permisos y Límites de Workspace
                target_p = args.get("path") or args.get("source")
                cmd_p = args.get("command")
                perm_req = PermissionRequest(
                    tool_name=tool_name,
                    category=category,
                    level=perm_level,
                    target_path=target_p,
                    command=cmd_p,
                    justification="Ejecución de acción autónoma de AETHER",
                )

                decision, reason = self.permissions.evaluate(perm_req)
                if decision == PermissionDecision.DENY:
                    tool_result = f"⛔ Denegado por política de permisos: {reason}"
                    total_tool_failures += 1
                    self._record_and_feed_result(tool_name, args, tool_result, False, 0.0)
                    continue

                # 2. Pre-Tool Hook (Validación de políticas y modos de operación)
                allowed, hook_reason = self.hooks.pre_tool_use(tool_name, args)
                if not allowed:
                    tool_result = f"Bloqueado por Hook Pre-Tool ({self.hooks.mode}): {hook_reason}"
                    total_tool_failures += 1
                    self._record_and_feed_result(tool_name, args, tool_result, False, 0.0)
                    continue

                # 3. Control de seguridad para comandos de consola
                if tool_name == "run_command":
                    cmd_str = args.get("command", "")
                    is_safe, sec_reason = check_command_safety(cmd_str)
                    if not is_safe:
                        should_run = False
                        if self.confirm_callback:
                            should_run = self.confirm_callback(
                                f"Comando de riesgo detectado: '{cmd_str}'\nMotivo: {sec_reason}\n¿Deseas permitir su ejecución?"
                            )
                        if not should_run:
                            tool_result = f"Ejecución bloqueada por seguridad: {sec_reason}"
                            total_tool_failures += 1
                            self._record_and_feed_result(tool_name, args, tool_result, False, 0.0)
                            continue

                # 4. Evaluación del Circuit Breaker Anti-Bucle
                tool_call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                breaker_tripped, breaker_msg = self._check_circuit_breaker(
                    tool_name=tool_name,
                    args=args,
                    failed_commands=failed_commands,
                    files_modified_since_cmd_fail=files_modified_since_cmd_fail,
                    known_syntax_error_files=known_syntax_error_files,
                    last_failed_tool_key=last_failed_tool_key,
                    consecutive_edit_failures=consecutive_edit_failures,
                    recent_failed_tools=recent_failed_tools,
                    consecutive_tool_failures=consecutive_tool_failures,
                    executed_edits=executed_edits,
                    action_history=action_history,
                )
                if breaker_tripped:
                    total_tool_failures += 1
                    consecutive_tool_failures += 1
                    recent_failed_tools.append(tool_name)
                    last_failed_tool_key = tool_call_key
                    self._record_and_feed_result(tool_name, args, breaker_msg, False, 0.0)
                    continue

                if tool_name not in [
                    "read_file", "list_directory", "search_codebase", "get_file_outline",
                    "get_git_status", "get_git_diff", "get_diagnostics", "find_definition",
                    "find_references", "get_dependencies", "get_hardware_vram_status", "get_repo_map"
                ]:
                    current_action_sig = f"{tool_name}:{args.get('path') or args.get('command') or ''}"
                    action_history.append(current_action_sig)

                # 5. Ejecución de la herramienta con cronometraje (usando resultado pre-ejecutado si fue en paralelo)
                tool_start = time.perf_counter()
                if idx in parallel_results:
                    tool_result = parallel_results[idx]
                else:
                    tool_result = execute_tool(tool_name, args)
                tool_dur_ms = (time.perf_counter() - tool_start) * 1000.0

                # 6. Post-Tool Hook
                tool_result = self.hooks.post_tool_use(tool_name, args, tool_result)

                # 7. Evaluación del éxito del resultado
                if tool_name == "run_command":
                    is_cancelled = ("operation cancelled" in tool_result.lower()) or ("operation aborted" in tool_result.lower())
                    is_cmd_success = ("Código de salida: 0" in tool_result) and not tool_result.startswith("Error:") and not is_cancelled
                    is_success = is_cmd_success
                else:
                    is_success = not (
                        tool_result.startswith("Error")
                        or tool_result.startswith("⛔")
                        or "SyntaxError" in tool_result
                        or "error de sintaxis" in tool_result.lower()
                        or "falló" in tool_result.lower()
                    )

                # 8. Actualización del estado del Circuit Breaker
                if tool_name in ["write_file", "edit_file", "apply_patch"]:
                    target_path = args.get("path")
                    has_syntax_err = ("SyntaxError" in tool_result) or ("error de sintaxis" in tool_result.lower())
                    if tool_name in ["edit_file", "apply_patch"]:
                        executed_edits.add(f"{target_path}:{args.get('target', '')}")
                    elif tool_name == "write_file" and is_success:
                        executed_edits.clear()

                    if is_success and not has_syntax_err:
                        files_modified_since_cmd_fail = True
                        failed_commands.clear()  # ¡Se modificó un archivo con éxito! Limpiar fallos de comandos previos
                        action_history.clear()  # ¡Mutación real confirmada en disco! Limpiar ciclo previo
                        last_failed_tool_key = None
                        consecutive_edit_failures = 0
                        if target_path:
                            known_syntax_error_files.discard(target_path)
                            known_syntax_error_files.discard(Path(target_path).name)
                    else:
                        if tool_name in ["edit_file", "apply_patch"]:
                            consecutive_edit_failures += 1
                        if has_syntax_err and target_path:
                            known_syntax_error_files.add(target_path)
                            known_syntax_error_files.add(Path(target_path).name)
                        last_failed_tool_key = tool_call_key
                elif tool_name in ["read_file", "list_directory", "search_codebase"]:
                    if is_success:
                        consecutive_edit_failures = 0

                elif tool_name in ["undo_checkpoint", "safe_undo_checkpoint"]:
                    files_modified_since_cmd_fail = True
                    failed_commands.clear()
                    last_failed_tool_key = None
                    known_syntax_error_files.clear()
                    last_assertion_error = None
                    assertion_error_repeat_count = 0

                elif tool_name == "run_command":
                    cmd_norm = args.get("command", "").strip().lower()
                    if not is_success:
                        failed_commands.add(cmd_norm)
                        files_modified_since_cmd_fail = False
                        last_failed_tool_key = tool_call_key
                        if "syntaxerror" in tool_result.lower():
                            for part in args.get("command", "").split():
                                if part.endswith(".py"):
                                    known_syntax_error_files.add(part)
                                    known_syntax_error_files.add(Path(part).name)

                        # Detección de bucles de aserción o fallos persistentes en tests
                        err_line = None
                        assert_match = re.search(r"(AssertionError:[^\n\r]+)", tool_result)
                        if assert_match:
                            err_line = assert_match.group(1).strip()
                        else:
                            failed_test_m = re.search(r"(FAILED\s+[^\n\r]+)", tool_result)
                            if failed_test_m:
                                err_line = failed_test_m.group(1).strip()

                        if err_line:
                            if last_assertion_error and err_line == last_assertion_error:
                                assertion_error_repeat_count += 1
                            else:
                                last_assertion_error = err_line
                                assertion_error_repeat_count = 1

                            if assertion_error_repeat_count >= 2:
                                tool_result += (
                                    f"\n🚨 [CIRCUIT BREAKER - FALLO PERSISTENTE EN TEST ({assertion_error_repeat_count} veces)]:\n"
                                    f"La prueba sigue fallando con el mismo error: '{err_line}'.\n"
                                    "Tus modificaciones previas NO están resolviendo el fallo o no produjeron cambios efectivos en disco.\n"
                                    "• Si es un test con corrutinas async, convierte la función a síncrona 'def' usando 'asyncio.run()'.\n"
                                    "• Si el error compara dos números (ej: X != Y), el primer número (X) es el valor REAL de Python.\n"
                                    "• ACCIÓN OBLIGATORIA: Abre el archivo y reescríbelo completamente usando 'write_file' con el código correcto."
                                )
                    else:
                        failed_commands.discard(cmd_norm)
                        last_failed_tool_key = None
                        last_assertion_error = None
                        assertion_error_repeat_count = 0
                        # Si fue un comando de instalación de paquetes, limpiar fallos de comandos previos
                        # porque el entorno de dependencias cambió
                        pkg_install_prefixes = (
                            "pip install", "pip3 install", "python -m pip install",
                            "npm install", "npm i ", "pnpm add", "pnpm install", "yarn add"
                        )
                        if any(cmd_norm.startswith(p) for p in pkg_install_prefixes):
                            failed_commands.clear()
                            files_modified_since_cmd_fail = True

                if tool_name in ["read_file", "list_directory", "search_codebase", "get_file_outline", "get_git_status", "get_git_diff"]:
                    # Herramientas de solo lectura pasiva: proveen contexto pero NO modifican estado,
                    # por lo tanto NO resetean consecutive_tool_failures ni recent_failed_tools
                    pass
                elif is_success:
                    consecutive_tool_failures = 0
                    recent_failed_tools.clear()
                    last_failed_tool_key = None
                else:
                    consecutive_tool_failures += 1
                    recent_failed_tools.append(tool_name)
                    last_failed_tool_key = tool_call_key
                    total_tool_failures += 1
                    if iteration < self.max_iterations:
                        if tool_name in ["edit_file", "apply_patch"]:
                            tool_result += "\n[SISTEMA AETHER]: La edición falló porque el texto 'target' no coincide con el archivo en disco. Usa 'read_file' para inspeccionar las líneas exactas o reescribe el módulo con 'write_file'."
                        else:
                            tool_result += "\n[SISTEMA AETHER]: Se detectó un error en la ejecución. Analiza la causa raíz, aplica la corrección con edit_file, apply_patch o write_file y vuelve a probar."

                self._record_and_feed_result(tool_name, args, tool_result, is_success, tool_dur_ms)

        if not final_answer:
            final_answer = "La tarea alcanzó el número máximo de iteraciones sin finalizar formalmente."
            self.set_state(AgentState.COMPLETED)

        turn_duration = time.perf_counter() - turn_start_time
        self.telemetry.record_turn(
            session_id=self.session_id,
            turn_index=current_turn,
            model=self.model,
            duration_seconds=turn_duration,
            tool_calls_count=total_tool_calls,
            tool_failures_count=total_tool_failures,
            user_prompt_length=len(user_prompt),
            agent_response_length=len(final_answer),
        )

        return final_answer

    def _record_and_feed_result(self, tool_name: str, args: Dict[str, Any], result: str, success: bool, latency_ms: float):
        """Registra en UI, Memoria, Persistencia SQLite y Telemetría el resultado de una herramienta."""
        if self.on_tool_result:
            self.on_tool_result(tool_name, result)

        self.memory.add_tool_result(name=tool_name, content=result)
        self.session_manager.record_tool_execution(
            session_id=self.session_id,
            tool_name=tool_name,
            args=args,
            result=result,
            success=success,
            latency_ms=latency_ms,
        )
        category, _ = get_tool_metadata(tool_name)
        self.telemetry.record_tool_execution(
            session_id=self.session_id,
            tool_name=tool_name,
            category=category.value,
            duration_ms=latency_ms,
            success=success,
            error=None if success else result[:100],
        )
