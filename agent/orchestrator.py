"""
Orquestador y Bucle ReAct principal para el Agente AETHER.
Maneja la comunicación con Ollama, ejecución de herramientas y bucle de autocorrección.
"""

import json
import re
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

        # 4. Fallback Proactivo: Si el modelo devolvió código en markdown (ej. python)
        # pero olvidó invocar write_file, sintetizar la llamada para crear el archivo real
        code_blocks = re.findall(r"```([a-zA-Z0-9_\-+]*)\s*\n([\s\S]*?)\s*```", content)
        if code_blocks:
            filename_match = re.search(r"[`'\"]([a-zA-Z0-9_\-]+\.(?:py|js|ts|html|css|json|md|txt|sh|bat))[`'\"]", content)
            if not filename_match:
                filename_match = re.search(r"(?:archivo|file|script|llamado)\s+([a-zA-Z0-9_\-]+\.(?:py|js|ts|html|css|json|md|txt|sh|bat))", content, re.IGNORECASE)

            target_filename = filename_match.group(1) if filename_match else "script.py"

            for lang, code_body in code_blocks:
                lang_clean = lang.lower().strip()
                if lang_clean in ("python", "py", "javascript", "js", "html", "css", "json", "md", "") and len(code_body.strip()) > 10:
                    extracted.append({
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "path": target_filename,
                                "content": code_body.strip()
                            }
                        }
                    })
                    break

        return extracted

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

            # Fallback inteligente: si Ollama no pobló tool_calls nativo pero incluyó llamadas en content
            if not tool_calls and content:
                extracted = self._extract_tool_calls_from_content(content)
                if extracted:
                    tool_calls = extracted

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

