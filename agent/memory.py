"""
Gestión de memoria y ventana de contexto para el agente.
Evita el desbordamiento de tokens en la GPU recortando de forma inteligente turnos intermedios.
"""

from typing import Any, Dict, List


class ConversationMemory:
    def __init__(self, system_prompt: str, max_turns: int = 24):
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self._trim_if_needed()

    def add_assistant_message(self, content: str = "", tool_calls: Any = None):
        msg: Dict[str, Any] = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._trim_if_needed()

    def add_tool_result(self, tool_call_id: str = "", content: str = "", name: str = ""):
        msg: Dict[str, Any] = {
            "role": "tool",
            "content": content
        }
        # Soporte para campos de Ollama y OpenAI
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
        if name:
            msg["name"] = name
        self.messages.append(msg)
        self._trim_if_needed()

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages

    def clear(self):
        """Reinicia la memoria conservando únicamente el system prompt."""
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def estimate_tokens(self) -> int:
        """Estima los tokens del contexto (~4 caracteres por token)."""
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        return total_chars // 4

    def _trim_if_needed(self):
        """
        Conserva siempre el system prompt (índice 0) y el mensaje de solicitud original (índice 1).
        Si se supera max_turns, descarta los turnos de herramientas más antiguos.
        """
        if len(self.messages) <= self.max_turns:
            return

        # Mantener system prompt (0) y mensaje inicial de usuario (1)
        system_msg = self.messages[0]
        initial_user_msg = self.messages[1] if len(self.messages) > 1 and self.messages[1]["role"] == "user" else None

        # Conservar los últimos (max_turns - 2) mensajes
        recent_messages = self.messages[-(self.max_turns - 2):]

        # Asegurar que el primer mensaje reciente no sea una respuesta huérfana a una tool
        while recent_messages and recent_messages[0]["role"] == "tool":
            recent_messages.pop(0)

        new_history = [system_msg]
        if initial_user_msg and initial_user_msg not in recent_messages:
            new_history.append(initial_user_msg)
        new_history.extend(recent_messages)

        self.messages = new_history

