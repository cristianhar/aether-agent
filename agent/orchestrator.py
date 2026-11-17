"""
Orquestador y Bucle ReAct principal para el Agente AETHER.
Maneja la comunicación con Ollama, ejecución de herramientas y bucle de autocorrección.
"""

import json
from typing import Any, Callable, Dict, List, Optional
import httpx

from agent.memory import ConversationMemory
from agent.prompts import SYSTEM_PROMPT
from agent.safety import check_command_safety
from tools.registry import TOOLS_SCHEMA, execute_tool


class AgentOrchestrator:
    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        host: str = "http://127.0.0.1:11434",
        system_prompt: str = SYSTEM_PROMPT,
        max_iterations: int = 15,
        on_thought: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        confirm_callback: Optional[Callable[[str], bool]] = None,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.max_iterations = max_iterations
        self.memory = ConversationMemory(system_prompt=system_prompt)

        # Callbacks de UI (para Rich CLI)
        self.on_thought = on_thought
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result
        self.confirm_callback = confirm_callback

    def check_ollama_alive(self) -> bool:
        """Verifica si el servicio de Ollama está respondiendo."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.host}/api/version")
                return res.status_code == 200
        except Exception:
            return False

    def run_turn(self, user_prompt: str) -> str:
        """
        Ejecuta el bucle ReAct completo para una solicitud del usuario.
        """
        self.memory.add_user_message(user_prompt)
        final_answer = ""

        for iteration in range(1, self.max_iterations + 1):
            messages = self.memory.get_messages()

            payload = {
                "model": self.model,
                "messages": messages,
                "tools": TOOLS_SCHEMA,
                "stream": False,
                "options": {
                    "temperature": 0.2,  # Baja temperatura para código preciso y tool-calling
                    "num_ctx": 8192,
                }
            }

            try:
                with httpx.Client(timeout=180.0) as client:
                    resp = client.post(f"{self.host}/api/chat", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.ConnectError:
                return (
                    f"Error de conexión: No se pudo contactar a Ollama en {self.host}.\n"
                    "Asegúrate de que Ollama esté ejecutándose ('ollama serve')."
                )
            except Exception as e:
                return f"Error al comunicar con Ollama: {str(e)}"

            msg = data.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            # Notificar pensamiento/contenido al usuario si existe
            if content and self.on_thought:
                self.on_thought(content)

            # Si el modelo no solicita ninguna herramienta, ha concluido su tarea
            if not tool_calls:
                self.memory.add_assistant_message(content=content)
                final_answer = content
                break

            # Si hay llamadas a herramientas, registrar el mensaje del asistente
            self.memory.add_assistant_message(content=content, tool_calls=tool_calls)

            # Procesar cada herramienta solicitada
            for tc in tool_calls:
                func_data = tc.get("function", {})
                tool_name = func_data.get("name", "")
                args = func_data.get("arguments", {})

                # Si arguments viene serializado en string, parsearlo a dict
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}

                # Notificar a la UI
                if self.on_tool_call:
                    self.on_tool_call(tool_name, args)

                # Control de seguridad: Si es un comando de shell, evaluar peligrosidad
                if tool_name == "run_command":
                    cmd_str = args.get("command", "")
                    is_safe, reason = check_command_safety(cmd_str)
                    if not is_safe:
                        should_run = False
                        if self.confirm_callback:
                            should_run = self.confirm_callback(
                                f"Comando de riesgo detectado: '{cmd_str}'\nMotivo: {reason}\n¿Deseas permitir su ejecución?"
                            )
                        if not should_run:
                            tool_result = f"Ejecución bloqueada por seguridad: {reason}"
                            self.memory.add_tool_result(name=tool_name, content=tool_result)
                            if self.on_tool_result:
                                self.on_tool_result(tool_name, tool_result)
                            continue

                # Ejecutar la herramienta en el sistema
                tool_result = execute_tool(tool_name, args)

                if self.on_tool_result:
                    self.on_tool_result(tool_name, tool_result)

                # Alimentar el resultado de vuelta a la memoria
                self.memory.add_tool_result(name=tool_name, content=tool_result)

        if not final_answer:
            final_answer = "La tarea alcanzó el número máximo de iteraciones sin finalizar formalmente."

        return final_answer

