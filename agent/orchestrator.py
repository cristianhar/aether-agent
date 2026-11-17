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


class AgentOrchestrator:
    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        host: str = "http://127.0.0.1:11434",
        system_prompt: str = SYSTEM_PROMPT,
        max_iterations: int = 15,
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

        # Ingestión de reglas de proyecto (.aetherrules, CONVENTIONS.md o .cursorrules)
        for rules_name in [".aetherrules", "CONVENTIONS.md", ".cursorrules"]:
            rules_path = Path.cwd() / rules_name
            if rules_path.exists():
                try:
                    custom_rules = rules_path.read_text(encoding="utf-8").strip()
                    if custom_rules:
                        system_prompt += f"\n\n<custom_project_rules source='{rules_name}'>\n{custom_rules}\n</custom_project_rules>"
                        break
                except Exception:
                    pass

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

        # Bloques de código markdown pasivos (ej: ```python ... ```) NO se sintetizan
        # automáticamente como llamadas a herramientas. Esto previene escrituras fantasma
        # cuando el modelo simplemente está explicando un concepto en texto al usuario.
        return []

    def _check_circuit_breaker(
        self,
        tool_name: str,
        args: Dict[str, Any],
        last_failed_command: Optional[str],
        files_modified_since_cmd_fail: bool,
        known_syntax_error_files: set,
        consecutive_tool_counts: Dict[str, int],
    ) -> Tuple[bool, str]:
        """
        Circuit Breaker Anti-Bucle:
        Previene bucles repetitivos donde el modelo:
        1. Repite el mismo comando de consola que ya falló sin haber modificado ningún archivo.
        2. Intenta ejecutar un script que contiene un SyntaxError detectado sin haberlo editado.
        3. Llama repetidamente a la misma herramienta con argumentos idénticos tras un fallo previo.
        """
        tool_call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"

        # Regla 1: run_command idéntico tras un fallo sin modificar archivos
        if tool_name == "run_command":
            cmd_norm = args.get("command", "").strip().lower()
            if last_failed_command and cmd_norm == last_failed_command and not files_modified_since_cmd_fail:
                msg = (
                    f"⛔ [CIRCUIT BREAKER]: El comando '{args.get('command')}' ya falló previamente y NO has modificado ningún archivo en el disco desde entonces.\n"
                    "Volver a ejecutar el mismo comando sin cambios producirá exactamente el mismo error.\n"
                    "Tu razonamiento indicaba que ibas a corregir el archivo, pero llamaste a 'run_command' en lugar de 'edit_file'.\n"
                    "ACCIÓN OBLIGATORIA: Debes llamar a 'edit_file' o 'write_file' para corregir el código antes de volver a ejecutar el comando."
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

        # Regla 3: Herramienta idéntica consecutiva tras un fallo previo
        if consecutive_tool_counts.get(tool_call_key, 0) >= 1:
            msg = (
                f"⛔ [CIRCUIT BREAKER]: La herramienta '{tool_name}' con estos mismos argumentos ya fue ejecutada y falló.\n"
                "Está PROHIBIDO repetir la misma acción fallida consecutivamente sin cambiar los parámetros.\n"
                "Cambia tus argumentos o utiliza una herramienta diferente (ej: edit_file, read_file o search_codebase)."
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
        last_failed_command: Optional[str] = None
        files_modified_since_cmd_fail: bool = False
        consecutive_tool_counts: Dict[str, int] = {}
        known_syntax_error_files: set = set()

        for iteration in range(1, self.max_iterations + 1):
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

            # Fallback inteligente
            if not tool_calls and content:
                extracted = self._extract_tool_calls_from_content(content)
                if extracted:
                    tool_calls = extracted

            # Notificar pensamiento limpio si no hubo streaming de tokens
            if content and self.on_thought and not self.on_token:
                clean_thought = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", content).strip()
                if clean_thought.startswith("{") and clean_thought.endswith("}"):
                    clean_thought = ""
                if clean_thought:
                    self.on_thought(clean_thought)

            # Si el modelo no solicita ninguna herramienta, ha concluido
            if not tool_calls:
                self.memory.add_assistant_message(content=content)
                self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=content)
                final_answer = content
                self.set_state(AgentState.COMPLETED)
                break

            # Si hay llamadas a herramientas, registrar mensaje
            self.memory.add_assistant_message(content=content, tool_calls=tool_calls)
            self.session_manager.save_message(self.session_id, current_turn, role="assistant", content=content, tool_calls=tool_calls)

            # Procesar cada herramienta solicitada
            for tc in tool_calls:
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
                    last_failed_command=last_failed_command,
                    files_modified_since_cmd_fail=files_modified_since_cmd_fail,
                    known_syntax_error_files=known_syntax_error_files,
                    consecutive_tool_counts=consecutive_tool_counts,
                )
                if breaker_tripped:
                    total_tool_failures += 1
                    self._record_and_feed_result(tool_name, args, breaker_msg, False, 0.0)
                    continue

                # 5. Ejecución de la herramienta con cronometraje
                tool_start = time.perf_counter()
                tool_result = execute_tool(tool_name, args)
                tool_dur_ms = (time.perf_counter() - tool_start) * 1000.0

                # 6. Post-Tool Hook
                tool_result = self.hooks.post_tool_use(tool_name, args, tool_result)

                # 7. Evaluación del éxito del resultado
                if tool_name == "run_command":
                    is_cmd_success = ("Código de salida: 0" in tool_result) and not tool_result.startswith("Error:")
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
                    if is_success and not has_syntax_err:
                        files_modified_since_cmd_fail = True
                        last_failed_command = None
                        if target_path:
                            known_syntax_error_files.discard(target_path)
                            known_syntax_error_files.discard(Path(target_path).name)
                    elif has_syntax_err and target_path:
                        known_syntax_error_files.add(target_path)
                        known_syntax_error_files.add(Path(target_path).name)

                elif tool_name in ["undo_checkpoint", "safe_undo_checkpoint"]:
                    files_modified_since_cmd_fail = True
                    last_failed_command = None
                    known_syntax_error_files.clear()

                elif tool_name == "run_command":
                    cmd_norm = args.get("command", "").strip().lower()
                    if not is_success:
                        last_failed_command = cmd_norm
                        files_modified_since_cmd_fail = False
                        if "syntaxerror" in tool_result.lower():
                            for part in args.get("command", "").split():
                                if part.endswith(".py"):
                                    known_syntax_error_files.add(part)
                                    known_syntax_error_files.add(Path(part).name)
                    else:
                        last_failed_command = None

                if not is_success:
                    consecutive_tool_counts[tool_call_key] = consecutive_tool_counts.get(tool_call_key, 0) + 1
                    total_tool_failures += 1
                    if iteration < self.max_iterations:
                        tool_result += "\n[SISTEMA AETHER]: Se detectó un error en la ejecución. Analiza la causa raíz, aplica la corrección con edit_file, apply_patch o write_file y vuelve a probar."
                else:
                    consecutive_tool_counts.pop(tool_call_key, None)

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
