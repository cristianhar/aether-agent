"""
Sistema de Hooks Deterministas inspirado en Claude Code.
Ejecuta validaciones automáticas antes y después de cada llamada a herramienta:
- PreToolUse: Evaluación de seguridad, verificación de permisos y restricciones de modo.
- PostToolUse: Auto-Linter sintáctico, chequeo de integridad y telemetría.
"""

from typing import Any, Dict, Optional, Tuple
from agent.safety import check_command_safety


class HookManager:
    def __init__(self, mode: str = "agent"):
        self.mode = mode  # "agent", "ask", "plan"

    def set_mode(self, new_mode: str):
        if new_mode in ["agent", "ask", "plan"]:
            self.mode = new_mode

    def pre_tool_use(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Hook ejecutado antes de cualquier herramienta.
        Retorna (autorizado: bool, motivo_o_error: str).
        """
        # Restricciones en modo ASK (Solo lectura)
        if self.mode == "ask":
            forbidden_in_ask = {"write_file", "edit_file", "run_command", "create_checkpoint", "undo_checkpoint"}
            if tool_name in forbidden_in_ask:
                return False, f"Herramienta '{tool_name}' bloqueada: El agente está en modo 'ASK' (Solo Lectura)."

        # Validación de seguridad en comandos de terminal
        if tool_name == "run_command":
            cmd = args.get("command", "")
            is_safe, reason = check_command_safety(cmd)
            if not is_safe:
                return False, f"Comando de alto riesgo bloqueado por política de seguridad: {reason}"

        return True, "OK"

    def post_tool_use(self, tool_name: str, args: Dict[str, Any], result: str) -> str:
        """
        Hook ejecutado después de que la herramienta terminó.
        Puede enriquecer el resultado o inyectar advertencias sintácticas.
        """
        # Si fue una edición o escritura de archivo, el Auto-Linter ya evaluó sintaxis
        # Si la salida de run_command indica fallo, inyectar alerta de auto-sanación
        if tool_name == "run_command" and ("Código de salida: 1" in result or "Traceback" in result):
            if "EOFError" in result:
                result += "\n[HOOK POST-TOOL]: El comando falló por EOFError (esperaba teclado). Recuerda no ejecutar bucles interactivos input() directamente."

        return result
