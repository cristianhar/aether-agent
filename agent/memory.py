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

    def compact_memory(self):
        """
        Compactación de contexto inspirada en Claude Code:
        Sintetiza los turnos antiguos de herramientas en un resumen ejecutivo
        para que el modelo conserve el hilo de las decisiones tomadas sin saturar la VRAM.
        """
        if len(self.messages) <= 6:
            return

        system_msg = self.messages[0]
        initial_user_msg = self.messages[1]

        actions = []
        for m in self.messages[2:-4]:
            if m.get("role") == "tool":
                content = str(m.get("content", ""))
                first_line = content.splitlines()[0] if content else ""
                actions.append(first_line[:80])
            elif m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m.get("tool_calls", []):
                    fn = tc.get("function", {})
                    name = fn.get("name", "tool")
                    args = fn.get("arguments", {})
                    target_arg = args.get("path") or args.get("command") or "" if isinstance(args, dict) else ""
                    actions.append(f"{name}({target_arg})")

        compaction_text = (
            "📋 [COMPACTACIÓN DE CONTEXTO ANTIGRAVITY]: Se compactó el historial previo para optimizar tokens en VRAM.\n"
            "Acciones y verificaciones clave consolidadas:\n• " + "\n• ".join(actions[-8:] if actions else ["Exploración previa"])
        )
        compaction_summary = {
            "role": "system",
            "content": compaction_text
        }

        recent = self.messages[-4:]
        while recent and recent[0].get("role") == "tool":
            recent.pop(0)

        self.messages = [system_msg, initial_user_msg, compaction_summary] + recent

    def _trim_if_needed(self):
        """
        Conserva siempre el system prompt (índice 0) y el mensaje de solicitud original (índice 1).
        Si se supera max_turns o 5000 tokens estimados, compacta el contexto automáticamente.
        """
        if len(self.messages) > self.max_turns or self.estimate_tokens() > 5000:
            self.compact_memory()

