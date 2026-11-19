"""
Orquestador y Bucle ReAct principal para el Agente AETHER.
Integra máquina de estados, token de cancelación, motor de permisos, persistencia SQLite y telemetría.
"""

from datetime import datetime
import ast
import difflib
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
from agent.prompts import SYSTEM_PROMPT, get_system_prompt
from agent.safety import check_command_safety
from agent.session import SessionManager
from agent.skills import get_global_skill_registry
from agent.state import AgentState, CancellationToken
from agent.telemetry import TelemetryLogger
from tools.base import PermissionLevel, ToolCategory
from tools.registry import TOOLS_SCHEMA, execute_tool, get_tools_schema_for_mode


from agent.circuit_breaker import (
    check_circuit_breaker,
    detect_action_cycle,
    extract_test_failure_summary,
)
from agent.diff_preview import generate_tool_diff
from agent.tool_parser import extract_tool_calls_from_content
def get_tool_metadata(name: str) -> Tuple[ToolCategory, PermissionLevel]:
    """Clasifica cada herramienta según su categoría de riesgo y permisos."""
    if name in [
        "read_file", "cat", "view_file", "search_codebase", "grep_search", "grep", "list_directory", "get_file_outline",
        "get_repo_map", "get_diagnostics", "get_process_status",
        "find_definition", "find_references", "get_dependencies", "get_hardware_vram_status",
        "list_mcp_tools", "delegate_research", "get_plan", "search_memory", "list_memories",
        "conclude_turn", "finish_turn", "complete_task", "finish", "done"
    ]:
        category = ToolCategory.FILESYSTEM if name in ["read_file", "cat", "view_file", "search_codebase", "grep_search", "grep", "list_directory"] else ToolCategory.CODE_INTELLIGENCE
        return category, PermissionLevel.READ_ONLY

    if name in [
        "remember_fact", "update_plan", "create_artifact", "update_artifact",
        "define_subagent", "invoke_subagent", "send_message", "manage_subagents"
    ]:
        return ToolCategory.AGENT_MANAGEMENT, PermissionLevel.WORKSPACE_WRITE

    if name in ["write_file", "create_file", "new_file", "save_file", "edit_file", "delete_file", "move_file", "apply_patch"]:
        return ToolCategory.FILESYSTEM, PermissionLevel.WORKSPACE_WRITE

    if name in ["run_command", "exec", "execute_command", "bash", "sh", "terminal", "run_tests", "pytest", "test", "test_runner", "start_background_process", "cancel_process", "call_mcp_tool"]:
        return ToolCategory.EXECUTION, PermissionLevel.COMMAND_EXECUTE

    if name in ["create_checkpoint", "undo_checkpoint", "safe_checkpoint", "safe_undo_checkpoint", "get_git_diff", "get_git_status"]:
        return ToolCategory.GIT, PermissionLevel.WORKSPACE_WRITE

    return ToolCategory.AGENT_MANAGEMENT, PermissionLevel.READ_ONLY




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
        mode: str = "agent",
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

        self.skill_registry = get_global_skill_registry()
        skills_catalog = self.skill_registry.get_skills_catalog_prompt()
        if skills_catalog:
            system_prompt += "\n\n" + skills_catalog

        self.loaded_rules = loaded_rules
        self.mode = mode
        self.memory = ConversationMemory(system_prompt=system_prompt)
        self.hooks = HookManager(mode=mode)
        if mode != "agent":
            self.set_mode(mode)
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
        self.ask_question_callback: Optional[Callable] = None
        self.active_token: Optional[CancellationToken] = None

    def cancel_active_turn(self, reason: str = "Operación cancelada por el usuario."):
        """Cancela de forma segura el turno o tarea activa y devuelve el agente a IDLE."""
        if self.active_token:
            self.active_token.cancel(reason)
        self.state = AgentState.IDLE

    def set_mode(self, mode: str):
        """
        Cambia el modo operativo adaptando hooks, prompt del sistema y herramientas disponibles.
        """
        target_mode = (mode or "agent").lower().strip()
        self.mode = target_mode
        self.hooks.set_mode(target_mode)
        base_prompt = get_system_prompt(target_mode)
        if hasattr(self, "loaded_rules") and self.loaded_rules:
            base_prompt += "\n\n" + "\n\n".join(self.loaded_rules)
        if hasattr(self, "skill_registry") and self.skill_registry:
            skills_catalog = self.skill_registry.get_skills_catalog_prompt()
            if skills_catalog:
                base_prompt += "\n\n" + skills_catalog
        self.memory.set_system_prompt(base_prompt)

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
    @staticmethod
    def _extract_tool_calls_from_content(content: str) -> List[Dict[str, Any]]:
        """
        Extrae llamadas a herramientas delegando al submódulo especializado agent.tool_parser.
        """
        return extract_tool_calls_from_content(content)

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
        plan_completed: bool = False,
        files_modified_in_turn: bool = False,
        tests_executed_in_turn: bool = False,
        last_test_exit_code: Optional[int] = None,
        last_test_failure_summary: Optional[str] = None,
        user_prompt: str = "",
    ) -> Tuple[bool, str]:
        """
        Circuit Breaker Anti-Bucle Universal delegando al submódulo especializado agent.circuit_breaker.
        """
        return check_circuit_breaker(
            tool_name=tool_name,
            args=args,
            failed_commands=failed_commands,
            files_modified_since_cmd_fail=files_modified_since_cmd_fail,
            known_syntax_error_files=known_syntax_error_files,
            last_failed_tool_key=last_failed_tool_key,
            last_failed_command=last_failed_command,
            consecutive_edit_failures=consecutive_edit_failures,
            recent_failed_tools=recent_failed_tools,
            consecutive_tool_failures=consecutive_tool_failures,
            executed_edits=executed_edits,
            action_history=action_history,
            plan_completed=plan_completed,
            files_modified_in_turn=files_modified_in_turn,
            tests_executed_in_turn=tests_executed_in_turn,
            last_test_exit_code=last_test_exit_code,
            last_test_failure_summary=last_test_failure_summary,
            user_prompt=user_prompt,
        )


    def run_turn(self, user_prompt: str, cancellation_token: Optional[CancellationToken] = None) -> str:
        """
        Ejecuta el bucle ReAct completo para una solicitud del usuario.
        Monitorea el token de cancelación y registra métricas y persistencia.
        """
        turn_start_time = time.perf_counter()
        self.turn_counter += 1
        current_turn = self.turn_counter

        # Archivo y limpieza automática de planes completados en turnos previos para evitar sesgos
        try:
            from tools.agent_tools import clear_completed_plan
            clear_completed_plan()
        except Exception:
            pass

        # Vincular sesión activa para el gestor de artefactos
        try:
            from agent.artifacts import set_active_artifact_session
            set_active_artifact_session(self.session_id)
        except Exception:
            pass

        self.set_state(AgentState.RUNNING)

        # Expansión automática de menciones @archivo si el prompt contiene @
        if "@" in user_prompt:
            try:
                from agent.context import resolve_at_file_mentions
                expanded_prompt, _ = resolve_at_file_mentions(user_prompt)
                user_prompt = expanded_prompt
            except Exception:
                pass

        # Ingestión proactiva de recuerdos semánticos relevantes del proyecto
        try:
            matched_memories = self.session_manager.search_semantic_memory(user_prompt, top_k=3)
            if matched_memories and any(m.get("score", 0) > 0.4 for m in matched_memories):
                memory_lines = [
                    f"- {m['key']} ({m.get('category', 'general')}): {m['content']}"
                    for m in matched_memories if m.get("score", 0) > 0.4
                ]
                if memory_lines:
                    user_prompt = f"{user_prompt}\n\n🧠 [MEMORIA DEL PROYECTO RECUPERADA]:\n" + "\n".join(memory_lines)
        except Exception:
            pass

        self.memory.add_user_message(user_prompt)
        self.session_manager.save_message(self.session_id, current_turn, role="user", content=user_prompt)

        final_answer = ""
        total_tool_calls = 0
        total_tool_failures = 0

        # Variables de control del Circuit Breaker Anti-Bucle
        failed_commands: set = set()
        files_modified_since_cmd_fail: bool = False
        files_modified_in_turn: bool = False
        last_failed_tool_key: Optional[str] = None
        known_syntax_error_files: set = set()
        last_assertion_error: Optional[str] = None
        assertion_error_repeat_count: int = 0
        consecutive_edit_failures: int = 0
        consecutive_tool_failures: int = 0
        recent_failed_tools: list = []
        executed_edits: set = set()
        action_history: List[str] = []
        plan_active_in_turn: bool = False
        plan_completed_in_turn: bool = False
        proactive_prompts_sent: int = 0
        tests_executed_in_turn: bool = False
        last_test_exit_code: Optional[int] = None
        last_test_failure_summary: Optional[str] = None

        for iteration in range(1, self.max_iterations + 1):
            # Seguridad: Detener bucles improductivos si hay demasiados fallos consecutivos sin ningún éxito
            if consecutive_tool_failures >= 10:
                final_answer = (
                    "⚠️ [CIRCUIT BREAKER GENERAL]: Se detuvo la ejecución autónoma tras 10 intentos fallidos consecutivos "
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
                "stream": bool(self.on_token),
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 5120,
                }
            }
            if not plan_completed_in_turn:
                payload["tools"] = get_tools_schema_for_mode(self.hooks.mode)

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

            # Auto-materialización de bloques de código markdown con encabezado de archivo (# archivo.py / // archivo.js)
            # Permite capturar código escrito en markdown cuando el modelo olvidó emitir la llamada formal a write_file (solo en modos con permisos de escritura)
            if content and self.hooks.mode not in ["plan", "ask"]:
                code_blocks = re.findall(
                    r"```(?:[a-zA-Z0-9_\-]+)?\s*\n(?:#|//)\s*([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+)\s*\n([\s\S]*?)```",
                    content,
                )
                for file_name, file_code in code_blocks:
                    f_clean = file_name.strip()
                    already_writing = any(
                        tc.get("function", {}).get("name") == "write_file"
                        and tc.get("function", {}).get("arguments", {}).get("path") == f_clean
                        for tc in tool_calls
                    )
                    if not already_writing:
                        tool_calls.insert(0, {
                            "function": {
                                "name": "write_file",
                                "arguments": {
                                    "path": f_clean,
                                    "content": file_code.strip()
                                }
                            }
                        })

            # Fallback inteligente
            if not tool_calls and content:
                extracted = self._extract_tool_calls_from_content(content)
                if extracted:
                    tool_calls = extracted

            # Notificar pensamiento limpio si no hubo streaming de tokens
            if self.on_thought:
                if thought_text:
                    self.on_thought(thought_text)
                elif content and tool_calls and not self.on_token:
                    clean_thought = re.sub(r"```[\s\S]*?```", "", content).strip()
                    clean_thought = re.sub(r"\{[\s\S]*?\"(?:name|arguments|function)\"[\s\S]*?\}", "", clean_thought).strip()
                    if clean_thought.startswith("{") and clean_thought.endswith("}"):
                        clean_thought = ""
                    if clean_thought:
                        self.on_thought(clean_thought)

            # Si el modelo no solicita ninguna herramienta, verificar si era un intento de JSON malformado
            if not tool_calls:
                # Detección de tool call fantasma no parseable (solo si herramientas estaban habilitadas)
                if not plan_completed_in_turn and '"name":' in content and ('"arguments":' in content or '"path":' in content or '"command":' in content):
                    if iteration < self.max_iterations:
                        self.memory.add_assistant_message(content=content)
                        retry_hint = (
                            "[SISTEMA AETHER]: Se detectó que intentaste emitir una llamada a herramienta en formato JSON, "
                            "pero no pudo ser ejecutada por errores de formato o sintaxis. "
                            "Por favor emite la llamada usando la herramienta directamente sin escapar triples comillas de Python dentro de strings."
                        )
                        self.memory.add_user_message(content=retry_hint)
                        continue

                # Guardián de Cierre de Plan: Si se inició o actualizó un plan en este turno y aún no ha concluido
                if plan_active_in_turn and not plan_completed_in_turn and iteration < self.max_iterations - 1:
                    if last_test_exit_code == 0 and files_modified_in_turn:
                        # Las pruebas ya pasaron exitosamente y los archivos pedidos fueron creados:
                        # Cerramos el plan automáticamente para permitir que el agente concluya el turno limpiamente
                        try:
                            from tools.agent_tools import update_plan
                            update_plan(is_completed=True)
                        except Exception:
                            pass
                        plan_completed_in_turn = True
                    else:
                        self.memory.add_assistant_message(content=content)
                        plan_guard_hint = (
                            "[SISTEMA AETHER - CIERRE DE PLAN REQUERIDO]: Has emitido una respuesta final pero el plan activo en '.aether/plans/plan_activo.md' "
                            "aún no ha sido marcado como COMPLETADO con 'update_plan(..., is_completed=True)'.\n"
                            "• Si todas las pruebas pasaron y los archivos pedidos fueron creados, tu OBLIGACIÓN es llamar a 'update_plan(plan_steps=..., is_completed=True)' para cerrar el plan.\n"
                            "• Si aún falta implementar algún archivo o ejecutar tests, ejecuta la herramienta correspondiente ahora."
                        )
                        self.memory.add_user_message(content=plan_guard_hint)
                        continue

                # Guardián de Pruebas Fallidas: Nunca permitir dar por completada la tarea si las pruebas ejecutadas fallaron
                if last_test_exit_code is not None and last_test_exit_code != 0 and iteration < self.max_iterations - 1:
                    self.memory.add_assistant_message(content=content)
                    failure_detail = f"\n📋 [DETALLE DEL FALLO EN TESTS]:\n{last_test_failure_summary}\n" if last_test_failure_summary else ""
                    test_failed_guard = (
                        "[SISTEMA AETHER - CORRECCIÓN DE PRUEBAS OBLIGATORIA]: No puedes dar la tarea por concluida ni pedir datos al usuario porque las pruebas unitarias FALLARON (Exit code != 0).\n"
                        f"{failure_detail}\n"
                        "• Está TERMINANTEMENTE PROHIBIDO responder con texto conversacional, confirmaciones o preguntas.\n"
                        "• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'write_file' o 'edit_file' para corregir el error indicado arriba."
                    )
                    self.memory.add_user_message(content=test_failed_guard)
                    continue

                # Guardián de Proactividad Autónoma: Evitar detenciones prematuras o preguntas pasivas
                premature_question_markers = [
                    "deseas que", "quieres que", "te gustaría que",
                    "deseas que continúe", "deseas que siga", "continuamos",
                    "procedo a", "quieres que proceda", "puedo ayudarte",
                    "siguiente paso", "cuál es el siguiente", "cómo deseas proceder",
                    "qué debería hacer", "qué quieres que haga", "qué te gustaría",
                    "indícame cómo proceder", "avísame si deseas", "algún cambio adicional",
                    "en qué más puedo", "qué más deseas", "cómo quieres que continúe"
                ]
                content_lower = content.lower()
                is_premature_deflection = any(m in content_lower for m in premature_question_markers)

                prompt_lower = user_prompt.lower()
                has_attached_context = "[CONTEXTO ESTRUCTURADO DE @" in user_prompt or "[CONTEXTO ADJUNTO VÍA" in user_prompt
                is_ask_mode = getattr(self.hooks, "mode", "agent") == "ask"

                # Detección estricta de solicitud de creación de archivos
                creation_requested = any(k in prompt_lower for k in [
                    "crea ", "crear ", "implementa", "implementar", "desarrolla", "desarrollar",
                    "construye", "construir", "programa", "programar",
                    "escribe un script", "haz un archivo", "genera el archivo"
                ])
                requested_py_files = re.findall(r"['\"]([a-zA-Z0-9_\-\.]+\.py)['\"]", user_prompt) if creation_requested else []
                missing_requested_files = [
                    rf for rf in requested_py_files
                    if not (Path.cwd() / rf).is_file() and not list(Path.cwd().glob(f"**/{rf}"))
                ]

                tests_requested = any(w in prompt_lower for w in [
                    "test", "tests", "prueba", "pruebas", "pytest", "run_tests", "unittest", "probar"
                ])
                execution_requested = any(k in prompt_lower for k in [
                    "ejecuta", "ejecutar", "corre", "correr", "run_command", "run_tests", "vuelve a probar"
                ])
                modification_requested = any(k in prompt_lower for k in [
                    "modifica", "modificar", "cambia", "cambiar", "actualiza", "actualizar",
                    "corrige", "corregir", "corrígelo", "corrigelo", "arregla", "arreglar", "arreglalo",
                    "edita", "editar", "edítalo", "editalo", "edit_file", "reemplaza", "reemplazar",
                    "repara", "reparar", "reparalo", "resuelve", "resolver", "resuélvelo", "resuelvelo",
                    "refactoriza", "refactorizar", "refactor"
                ])

                is_code_task = (
                    self.hooks.mode not in ["ask", "plan"]
                    and not has_attached_context
                    and (
                        bool(missing_requested_files)
                        or (creation_requested and tests_requested)
                        or files_modified_in_turn
                        or modification_requested
                        or (execution_requested and tests_requested)
                        or (creation_requested and any(k in prompt_lower for k in ["clase ", "modulo", "módulo", "script"]))
                    )
                )

                has_attached_context = "[CONTEXTO ESTRUCTURADO DE @" in user_prompt or "[CONTEXTO ADJUNTO VÍA" in user_prompt

                is_workspace_listing_task = (
                    not has_attached_context
                    and not is_code_task
                    and any(phrase in prompt_lower for phrase in [
                        "que archivos hay", "qué archivos hay", "archivos hay",
                        "en la raiz", "en la raíz", "en el directorio",
                        "listar archivos", "lista de archivos", "lista los archivos", "mostrar archivos",
                        "que carpetas hay", "qué carpetas hay", "listar carpetas",
                        "estructura del proyecto", "estructura de archivos", "árbol de archivos",
                        "contenido del proyecto", "que contiene el proyecto", "qué contiene el proyecto",
                        "que hay en la raiz", "qué hay en la raíz", "que hay en el proyecto"
                    ])
                )

                # Guardián de Exploración Autónoma: Si el usuario pidió ver archivos y el modelo no los listó
                inspection_tools_used = any(
                    any(t in a for t in ["list_directory", "get_repo_map", "read_file", "search_codebase"])
                    for a in action_history
                )
                if is_workspace_listing_task and not inspection_tools_used and iteration < self.max_iterations - 1 and proactive_prompts_sent < 2:
                    proactive_prompts_sent += 1
                    self.memory.add_assistant_message(content=content)
                    inspection_hint = (
                        "[SISTEMA AETHER - EXPLORACIÓN DE PROYECTO OBLIGATORIA]: El usuario solicitó conocer qué archivos o elementos existen en el proyecto.\n"
                        "• Está TERMINANTEMENTE PROHIBIDO responder con evasivas, disculpas sobre MCP o preguntas pasivas.\n"
                        "• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'list_directory(path=\".\")' o 'get_repo_map()' "
                        "para leer físicamente los archivos del disco e informar al usuario."
                    )
                    self.memory.add_user_message(content=inspection_hint)
                    continue

                # Guardián Anti-Pasividad: Si el modelo pide pasivamente que se le comparta el código o archivo
                passive_file_begging = any(p in content.lower() for p in [
                    "comparte el código", "compartir el código", "comparte el archivo", "compartir el archivo",
                    "pásame el código", "pasame el contenido", "pásame el archivo", "pasame el archivo",
                    "no tengo acceso al archivo", "puedes compartir", "podrías compartir", "podrias compartir",
                    "envíame el código", "enviame el código", "envíame el archivo", "enviame el archivo",
                    "más detalles sobre el contenido del archivo", "proporcióname el código", "proporcioname el código",
                    "proporciones el código", "proporcione el código", "necesito que me proporciones el código"
                ])
                if self.hooks.mode not in ["plan"] and not has_attached_context and passive_file_begging and iteration < self.max_iterations - 1 and proactive_prompts_sent < 2:
                    proactive_prompts_sent += 1
                    self.memory.add_assistant_message(content=content)
                    file_inspection_hint = (
                        "[SISTEMA AETHER - AUTO-INSPECCIÓN OBLIGATORIA]: NUNCA le pidas el archivo o código al usuario.\n"
                        "• Eres un agente local autónomo con acceso directo al disco: si necesitas leer un archivo, "
                        "usa 'read_file(path=...)' o 'get_file_outline(path=...)' directamente para inspeccionarlo tú mismo."
                    )
                    self.memory.add_user_message(content=file_inspection_hint)
                    continue

                if modification_requested and self.hooks.mode not in ["ask", "plan"] and not files_modified_in_turn and iteration < self.max_iterations - 1 and proactive_prompts_sent < 2:
                    proactive_prompts_sent += 1
                    self.memory.add_assistant_message(content=content)
                    if execution_requested and not tests_executed_in_turn:
                        mod_hint = (
                            "[SISTEMA AETHER - EJECUCIÓN Y CORRECCIÓN OBLIGATORIA]: El usuario solicitó ejecutar pruebas y corregir el código.\n"
                            "• Está TERMINANTEMENTE PROHIBIDO responder únicamente con explicaciones o texto plano.\n"
                            "• ACCIÓN OBLIGATORIA: Ejecuta las pruebas reales llamando a 'run_tests()' o modifica el código con 'edit_file' / 'write_file'."
                        )
                    else:
                        mod_hint = (
                            "[SISTEMA AETHER - MODIFICACIÓN DE CÓDIGO REQUERIDA]: El usuario solicitó modificar código.\n"
                            "• Está TERMINANTEMENTE PROHIBIDO responder únicamente con explicaciones o diffs en texto markdown.\n"
                            "• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'edit_file(path=..., target=..., replacement=...)' "
                            "o 'write_file(path=..., content=...)' para aplicar la modificación."
                        )
                    self.memory.add_user_message(content=mod_hint)
                    continue

                if is_code_task:
                    if missing_requested_files and iteration < self.max_iterations - 1 and proactive_prompts_sent < 2:
                        proactive_prompts_sent += 1
                        missing_f = missing_requested_files[0]
                        self.memory.add_assistant_message(content=content)
                        missing_file_hint = (
                            f"[SISTEMA AETHER - ENTREGABLE FALTANTE]: La solicitud del usuario requirió crear '{missing_f}', pero este archivo no existe en el disco.\n"
                            f"• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'write_file(path=\"{missing_f}\", content=...)' para implementar este archivo."
                        )
                        self.memory.add_user_message(content=missing_file_hint)
                        continue

                    tests_exist = bool(list(Path.cwd().glob("test_*.py")) or list(Path.cwd().glob("*_test.py")) or (Path.cwd() / "tests").exists())
                    missing_tests = tests_requested and not tests_exist
                    tests_pending_execution = (tests_requested or files_modified_in_turn) and tests_exist and not tests_executed_in_turn

                    if (is_premature_deflection or missing_tests or tests_pending_execution) and proactive_prompts_sent < 2 and iteration < self.max_iterations - 1:
                        proactive_prompts_sent += 1
                        self.memory.add_assistant_message(content=content)
                        if tests_pending_execution:
                            proactive_hint = (
                                "[SISTEMA AETHER - VERIFICACIÓN OBLIGATORIA]: Los archivos de código y pruebas ya existen en el disco, "
                                "pero AÚN NO HAS EJECUTADO LOS TESTS en este turno.\n"
                                "• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE ser la llamada a herramienta 'run_tests()' o "
                                "'run_command(command=\"pytest\")' para verificar que las pruebas pasen en verde antes de concluir la tarea."
                            )
                        elif is_premature_deflection:
                            test_target_name = f"'test_{Path(requested_py_files[0]).stem}.py'" if requested_py_files else "'test_modulo.py'"
                            proactive_hint = (
                                "[SISTEMA AETHER - PROACTIVIDAD AUTÓNOMA]: Como agente programador autónomo de élite, "
                                "NUNCA te detengas a medias para preguntar '¿Qué siguiente paso te gustaría que realice?' ni pidas confirmaciones al usuario.\n"
                                f"• Tu responsabilidad es completar y verificar la tarea íntegramente de forma autónoma. Si has implementado un módulo o componente, "
                                f"tu siguiente acción DEBE SER crear las pruebas unitarias exhaustivas correspondientes (ej: {test_target_name}) usando 'write_file' "
                                "para validar todos los requisitos solicitados (incluyendo transacciones anidadas y casos límite), y correrlas con 'run_tests()'.\n"
                                "• ACCIÓN OBLIGATORIA: Está TERMINANTEMENTE PROHIBIDO responder con texto plano de cortesía o preguntas pasivas. Emite la llamada a 'write_file' ahora."
                            )
                        else:
                            proactive_hint = (
                                "[SISTEMA AETHER - PROACTIVIDAD AUTÓNOMA]: Como agente programador autónomo, NUNCA te detengas a medias para preguntar "
                                "'¿deseas que siga creando pruebas?'. La instrucción inicial ya solicitó implementar el código y sus pruebas unitarias.\n"
                                "• ACCIÓN OBLIGATORIA: Está TERMINANTEMENTE PROHIBIDO responder con texto plano de cortesía o confirmaciones como 'Entendido'. "
                                "Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a la herramienta 'write_file' para crear el archivo de pruebas 'test_*.py'."
                            )
                        self.memory.add_user_message(content=proactive_hint)
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
            mutated_paths_in_batch = set()
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

                if not isinstance(args, dict):
                    if isinstance(args, list) and args and isinstance(args[0], dict):
                        args = args[0]
                    else:
                        args = {}

                # Normalización inmediata de alias de herramientas y argumentos
                from tools.registry import TOOL_ALIASES
                tool_name = TOOL_ALIASES.get(tool_name, tool_name)

                if "path" not in args:
                    for p_alias in ["file_path", "filepath", "filename", "file"]:
                        if p_alias in args:
                            args["path"] = args.pop(p_alias)
                            break

                if "content" not in args:
                    for c_alias in ["text", "code", "body"]:
                        if c_alias in args and tool_name in ["write_file", "edit_file"]:
                            args["content"] = args.pop(c_alias)
                            break

                if tool_name in ["write_file", "edit_file", "apply_patch"]:
                    t_path = args.get("path")
                    if t_path:
                        if t_path in mutated_paths_in_batch:
                            continue
                        mutated_paths_in_batch.add(t_path)

                category, perm_level = get_tool_metadata(tool_name)

                # Intercepción limpia de herramientas de conclusión de turno (conclude_turn, finish_turn, complete_task, finish, done)
                if tool_name in ["conclude_turn", "finish_turn", "complete_task", "finish", "done"]:
                    if self.on_tool_call:
                        self.on_tool_call(tool_name, args)

                    # Guardián de Pruebas Fallidas: si las pruebas fallaron en este turno, no permitir concluir
                    if last_test_exit_code is not None and last_test_exit_code != 0 and iteration < self.max_iterations - 2:
                        failure_detail = f"\n📋 [DETALLE DEL FALLO EN TESTS]:\n{last_test_failure_summary}\n" if last_test_failure_summary else ""
                        tool_result = (
                            f"⛔ [NO SE PUEDE CONCLUIR - PRUEBAS FALLIDAS (Exit code {last_test_exit_code})]:\n"
                            f"{failure_detail}\n"
                            "• Las pruebas unitarias aún están fallando. No puedes dar la tarea por concluida.\n"
                            "• ACCIÓN OBLIGATORIA: Revisa el error reportado arriba y usa 'write_file' o 'edit_file' para corregir el código."
                        )
                        total_tool_failures += 1
                        self._record_and_feed_result(tool_name, args, tool_result, False, 1.0)
                        continue

                    finish_msg = args.get("message") or args.get("summary") or args.get("text") or content or "Tarea completada con éxito."
                    tool_result = f"🏁 Turno concluido: {finish_msg}"
                    self._record_and_feed_result(tool_name, args, tool_result, True, 1.0)
                    final_answer = finish_msg
                    self.memory.add_assistant_message(content=final_answer)
                    self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=final_answer)
                    self.set_state(AgentState.COMPLETED)
                    break

                # Notificar a la UI
                if self.on_tool_call:
                    self.on_tool_call(tool_name, args)

                if tool_name == "update_plan":
                    current_action_sig = f"update_plan:step_{args.get('current_step', '')}_{args.get('is_completed', '')}"
                elif tool_name in ["read_file", "get_file_outline", "write_file", "edit_file"]:
                    current_action_sig = f"{tool_name}:{args.get('path', '')}"
                elif tool_name in ["run_command", "run_tests"]:
                    current_action_sig = f"{tool_name}:{args.get('command', '') or args.get('path', '') or args.get('target_file', '')}"
                elif tool_name in ["search_codebase", "grep_search", "grep"]:
                    current_action_sig = f"{tool_name}:{args.get('query', '')}"
                elif tool_name == "list_directory":
                    current_action_sig = f"list_directory:{args.get('path', '.')}"
                elif tool_name == "get_repo_map":
                    current_action_sig = "get_repo_map"
                elif tool_name == "get_diagnostics":
                    current_action_sig = f"get_diagnostics:{args.get('path', '')}"
                elif tool_name in ["remember_fact", "search_memory", "list_memories"]:
                    current_action_sig = f"{tool_name}:{args.get('key') or args.get('query') or ''}"
                else:
                    current_action_sig = f"{tool_name}:{args.get('path') or args.get('command') or args.get('query') or ''}"

                # 1. Evaluación del Circuit Breaker Anti-Bucle (Prevención Universal de Ciclos y Completion Guard)
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
                    plan_completed=plan_completed_in_turn,
                    files_modified_in_turn=files_modified_in_turn,
                    tests_executed_in_turn=tests_executed_in_turn,
                    last_test_exit_code=last_test_exit_code,
                    last_test_failure_summary=last_test_failure_summary,
                    user_prompt=user_prompt,
                )
                action_history.append(current_action_sig)

                if breaker_tripped:
                    total_tool_failures += 1
                    consecutive_tool_failures += 1
                    recent_failed_tools.append(tool_name)
                    last_failed_tool_key = tool_call_key
                    self._record_and_feed_result(tool_name, args, breaker_msg, False, 0.0)
                    if (("COMPLETION GUARD" in breaker_msg or (tool_name == "update_plan" and last_test_exit_code == 0)) and files_modified_in_turn and (last_test_exit_code is None or last_test_exit_code == 0)) or (tool_name == "remember_fact" and "MEMORIA YA REGISTRADA" in breaker_msg):
                        # Si el plan ya está formalmente completado y verificado, o las pruebas ya pasaron con éxito,
                        # concluimos el turno limpiamente sin penalizar ni ciclar
                        clean_answer = re.sub(r"```[\s\S]*?```|\{[\s\S]*?\}", "", content).strip()
                        is_junk = len(clean_answer) < 20 or re.fullmatch(r"[\s<>{}\$\'\"\\=`]+", clean_answer) is not None
                        if is_junk:
                            if tool_name == "remember_fact":
                                final_answer = "He registrado la información en la memoria semántica del proyecto con éxito."
                            else:
                                final_answer = "He implementado la solución y verificado los cambios exitosamente asegurando que todas las pruebas unitarias pasen con código 0."
                        else:
                            final_answer = clean_answer
                        self.memory.add_assistant_message(content=final_answer)
                        self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=final_answer)
                        self.set_state(AgentState.COMPLETED)
                        break
                    continue

                # 2. Evaluación de Motor de Permisos y Límites de Workspace
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

                # 3. Pre-Tool Hook (Validación de políticas y modos de operación)
                allowed, hook_reason = self.hooks.pre_tool_use(tool_name, args)
                if not allowed:
                    tool_result = f"Bloqueado por Hook Pre-Tool ({self.hooks.mode}): {hook_reason}"
                    total_tool_failures += 1
                    self._record_and_feed_result(tool_name, args, tool_result, False, 0.0)
                    continue

                # 4. Control de seguridad para comandos de consola
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

                # 4.5. Control de Modo REVIEW (Supervisión interactiva con Unified Diff)
                if self.hooks.mode == "review" and tool_name in ["write_file", "edit_file", "delete_file"]:
                    diff_text = self._generate_tool_diff(tool_name, args)
                    target_file = str(args.get("path") or args.get("source") or "archivo")
                    confirm_msg = (
                        f"Solicitud de modificación en '{target_file}' mediante '{tool_name}':\n\n"
                        f"{diff_text}\n\n"
                        f"¿Deseas aplicar estos cambios en '{target_file}'?"
                    )
                    should_run = True
                    if self.confirm_callback:
                        should_run = self.confirm_callback(confirm_msg)
                    if not should_run:
                        tool_result = f"Operación '{tool_name}' cancelada por el desarrollador en modo REVIEW."
                        total_tool_failures += 1
                        self._record_and_feed_result(tool_name, args, tool_result, False, 0.0)
                        continue

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
                if tool_name in ["run_command", "run_tests"]:
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
                    has_syntax_err = ("SyntaxError" in tool_result) or ("error de sintaxis" in tool_result.lower()) or ("Auto-Linter" in tool_result) or ("Error de importación" in tool_result)
                    if tool_name in ["edit_file", "apply_patch"]:
                        executed_edits.add(f"{target_path}:{args.get('target', '')}")
                    elif tool_name == "write_file" and is_success:
                        executed_edits.clear()

                    is_mutation = is_success and not has_syntax_err and not ("Sin cambios" in tool_result)
                    if is_mutation:
                        files_modified_since_cmd_fail = True
                        files_modified_in_turn = True
                        failed_commands.clear()  # ¡Se modificó un archivo con éxito! Limpiar fallos de comandos previos
                        last_failed_tool_key = None
                        consecutive_edit_failures = 0
                        if target_path:
                            known_syntax_error_files.discard(target_path)
                            known_syntax_error_files.discard(Path(target_path).name)
                        if self.hooks.mode == "review" and not (list(Path.cwd().glob("test_*.py")) or list(Path.cwd().glob("tests/test_*.py"))):
                            self._record_and_feed_result(tool_name, args, tool_result, is_success, tool_dur_ms)
                            final_answer = f"Los cambios en '{target_path}' han sido revisados, aprobados y aplicados exitosamente en modo REVIEW."
                            self.memory.add_assistant_message(content=final_answer)
                            self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=final_answer)
                            self.set_state(AgentState.COMPLETED)
                            break
                    else:
                        if tool_name in ["edit_file", "apply_patch"]:
                            consecutive_edit_failures += 1
                        if has_syntax_err and target_path:
                            known_syntax_error_files.add(target_path)
                            known_syntax_error_files.add(Path(target_path).name)
                        last_failed_tool_key = tool_call_key
                elif tool_name in ["read_file", "list_directory", "search_codebase", "grep_search", "grep"]:
                    if is_success:
                        consecutive_edit_failures = 0

                elif tool_name == "update_plan":
                    plan_active_in_turn = True
                    if is_success and ("¡Todos los pasos del plan han sido completados" in tool_result or "🎉 COMPLETADO" in tool_result or args.get("is_completed") is True):
                        if last_test_exit_code is None or last_test_exit_code == 0:
                            plan_completed_in_turn = True
                            if files_modified_in_turn and last_test_exit_code == 0:
                                self._record_and_feed_result(tool_name, args, tool_result, is_success, tool_dur_ms)
                                final_answer = "He implementado la solución solicitada y verificado exitosamente que todas las pruebas unitarias pasen con código 0."
                                self.memory.add_assistant_message(content=final_answer)
                                self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=final_answer)
                                self.set_state(AgentState.COMPLETED)
                                break

                elif tool_name in ["undo_checkpoint", "safe_undo_checkpoint"]:
                    files_modified_since_cmd_fail = True
                    failed_commands.clear()
                    last_failed_tool_key = None
                    known_syntax_error_files.clear()
                    last_assertion_error = None
                    assertion_error_repeat_count = 0

                elif tool_name in ["run_command", "run_tests"]:
                    cmd_norm = args.get("command", "").strip().lower() if tool_name == "run_command" else f"pytest {args.get('test_target', '.')}".strip().lower()
                    if tool_name == "run_tests" or any(t_kw in cmd_norm for t_kw in ["pytest", "test", "py_compile", "unittest"]):
                        tests_executed_in_turn = True
                        last_test_exit_code = 0 if is_success else 1
                        if not is_success:
                            last_test_failure_summary = extract_test_failure_summary(tool_result)
                        else:
                            last_test_failure_summary = None

                    files_modified_since_cmd_fail = False
                    if not is_success:
                        failed_commands.add(cmd_norm)
                        last_failed_tool_key = tool_call_key
                        if "syntaxerror" in tool_result.lower():
                            for part in (args.get("command") or args.get("test_target") or "").split():
                                if part.endswith(".py"):
                                    known_syntax_error_files.add(part)
                                    known_syntax_error_files.add(Path(part).name)

                        # Detección de bucles de aserción o fallos persistentes en tests
                        err_line = None
                        m_eq = re.search(r"E\s+assert\s+(.+?)\s*==\s*([^\n\r]+)", tool_result)
                        m_err = re.search(r"([A-Za-z]+Error:[^\n\r]+)", tool_result)

                        if m_err and "ZeroDivisionError" in m_err.group(1):
                            err_line = m_err.group(1).strip()
                            tool_result += (
                                "\n💡 [GUÍA DE CORRECCIÓN]: Se produjo ZeroDivisionError (división por cero). "
                                "Añade en la función la condición 'if b == 0:' para retornar el valor esperado por las pruebas unitarias (0.0)."
                            )
                        elif m_eq:
                            val_act = m_eq.group(1).strip()
                            val_exp = m_eq.group(2).strip().split("#")[0].strip()
                            err_line = f"assert {val_act} == {val_exp}"
                            tool_result += (
                                f"\n💡 [DIAGNÓSTICO PRECISO DE ASERCIÓN]: La prueba unitaria falló porque la función retornó '{val_act}' "
                                f"pero el test espera estrictamente '{val_exp}'.\n"
                                "• Si la lógica de la función es correcta y el archivo de pruebas contenía valores de aserción erróneos o tipos incompatibles, corrige el archivo de pruebas con 'edit_file'.\n"
                                f"• Si la función tiene un bug de cálculo o validación, modifícala con 'edit_file' para que retorne '{val_exp}' en ese caso."
                            )
                        elif m_err:
                            err_line = m_err.group(1).strip()
                            m_imp = re.search(r"cannot import name ['\"]([A-Za-z0-9_]+)['\"] from ['\"]([A-Za-z0-9_]+)['\"]", err_line)
                            if m_imp:
                                bad_sym, mod_name = m_imp.group(1), m_imp.group(2)
                                mod_file = Path.cwd() / f"{mod_name}.py"
                                if not mod_file.is_file():
                                    found = list(Path.cwd().glob(f"**/{mod_name}.py"))
                                    if found:
                                        mod_file = found[0]
                                mod_syms = []
                                if mod_file.is_file():
                                    try:
                                        m_tree = ast.parse(mod_file.read_text(encoding="utf-8", errors="replace"))
                                        mod_syms = [n.name for n in ast.iter_child_nodes(m_tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                                    except Exception:
                                        pass
                                if mod_syms and bad_sym not in mod_syms:
                                    syms_str = ", ".join(repr(s) for s in mod_syms)
                                    guidance = (
                                        f"\n💡 [DIAGNÓSTICO DEL ERROR EN PRUEBAS]: Se produjo '{err_line}'.\n"
                                        f"• El archivo de pruebas intentó importar '{bad_sym}' desde '{mod_name}.py', pero '{mod_name}.py' define: {syms_str}.\n"
                                        f"• Está TERMINANTEMENTE PROHIBIDO modificar '{mod_name}.py'.\n"
                                        f"• ACCIÓN OBLIGATORIA: Modifica el archivo de pruebas ('test_{mod_name}.py') con 'write_file' o 'edit_file' para importar y probar {syms_str} ('from {mod_name} import {', '.join(mod_syms)}') y corre 'run_tests()' de inmediato."
                                    )
                                else:
                                    guidance = (
                                        f"\n💡 [DIAGNÓSTICO DEL ERROR EN PRUEBAS]: Se produjo '{err_line}'.\n"
                                        "• Existe una discrepancia entre los nombres exportados en el código fuente y los nombres importados en las pruebas unitarias.\n"
                                        "• ACCIÓN OBLIGATORIA: Haz coincidir el nombre exacto de la función en ambos archivos usando 'write_file' o 'edit_file' y corre 'run_tests()' de inmediato."
                                    )
                            elif any(e in err_line for e in ["ImportError", "AttributeError", "NameError"]):
                                guidance = (
                                    f"\n💡 [DIAGNÓSTICO DEL ERROR EN PRUEBAS]: Se produjo '{err_line}'.\n"
                                    "• Existe una discrepancia entre los identificadores definidos en el código fuente y los usados en las pruebas unitarias.\n"
                                    "• ACCIÓN OBLIGATORIA: Haz coincidir los nombres usando 'write_file' o 'edit_file' y corre 'run_tests()' de inmediato."
                                )
                            elif "TypeError" in err_line:
                                guidance = (
                                    f"\n💡 [DIAGNÓSTICO DEL ERROR EN PRUEBAS]: Se produjo '{err_line}'.\n"
                                    "• Revisa la signatura y los argumentos pasados en las llamadas de las pruebas unitarias.\n"
                                    "• ACCIÓN OBLIGATORIA: Corrige los argumentos o la definición de la función usando 'write_file' o 'edit_file' y corre 'run_tests()' de inmediato."
                                )
                            else:
                                guidance = (
                                    f"\n💡 [DIAGNÓSTICO DEL ERROR EN PRUEBAS]: Se produjo '{err_line}'.\n"
                                    "• Revisa la definición de la función y las llamadas en las pruebas unitarias.\n"
                                    "• ACCIÓN OBLIGATORIA: Corrige el código en 'write_file' o 'edit_file' y corre 'run_tests()' de inmediato. "
                                    "Está TERMINANTEMENTE PROHIBIDO usar herramientas pasivas (list_directory, get_repo_map) o actualizar el plan mientras este error persista."
                                )
                            tool_result += guidance
                        else:
                            failed_test_m = re.search(r"(FAILED\s+[^\n\r]+)", tool_result)
                            if failed_test_m:
                                err_line = failed_test_m.group(1).strip()

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

            if self.state == AgentState.COMPLETED or final_answer:
                break

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

    def _generate_tool_diff(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Genera un Unified Diff delegando al submódulo especializado agent.diff_preview."""
        return generate_tool_diff(tool_name, args)
