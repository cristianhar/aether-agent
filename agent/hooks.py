"""
Sistema de Hooks Deterministas inspirado en Claude Code.
Ejecuta validaciones automáticas antes y después de cada llamada a herramienta:
- PreToolUse: Evaluación de seguridad, verificación de permisos y restricciones de modo.
- PostToolUse: Auto-Linter sintáctico, chequeo de integridad y telemetría.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
from agent.safety import check_command_safety


class HookManager:
    def __init__(self, mode: str = "agent"):
        self.mode = mode  # "agent", "ask", "plan"
        self._pre_hooks: List[Callable[[str, Dict[str, Any]], Tuple[bool, str]]] = []
        self._post_hooks: List[Callable[[str, Dict[str, Any], str], str]] = []

    def set_mode(self, new_mode: str):
        if new_mode in ["agent", "ask", "plan"]:
            self.mode = new_mode

    def register_pre_hook(self, hook_fn: Callable[[str, Dict[str, Any]], Tuple[bool, str]]):
        """Registra un hook dinámico previo a la ejecución de herramientas."""
        self._pre_hooks.append(hook_fn)

    def register_post_hook(self, hook_fn: Callable[[str, Dict[str, Any], str], str]):
        """Registra un hook dinámico posterior a la ejecución de herramientas."""
        self._post_hooks.append(hook_fn)

    def pre_tool_use(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Hook ejecutado antes de cualquier herramienta.
        Retorna (autorizado: bool, motivo_o_error: str).
        """
        # 1. Ejecutar hooks registrados dinámicamente
        for custom_hook in self._pre_hooks:
            try:
                allowed, reason = custom_hook(tool_name, args)
                if not allowed:
                    return False, reason
            except Exception:
                pass

        # 2. Restricciones en modo ASK (Solo lectura)
        if self.mode == "ask":
            forbidden_in_ask = {"write_file", "edit_file", "delete_file", "move_file", "run_command", "create_checkpoint", "undo_checkpoint"}
            if tool_name in forbidden_in_ask:
                return False, f"Herramienta '{tool_name}' bloqueada: El agente está en modo 'ASK' (Solo Lectura)."

        # Restricciones en modo PLAN (Planificación Arquitectónica)
        if self.mode == "plan":
            forbidden_in_plan = {"edit_file", "delete_file", "move_file", "run_command", "create_checkpoint", "undo_checkpoint"}
            if tool_name in forbidden_in_plan:
                return False, f"Herramienta '{tool_name}' bloqueada: El agente está en modo 'PLAN' (Planificación Arquitectónica). Solo se permite inspeccionar código y estructurar el plan con 'update_plan'."
            if tool_name == "write_file":
                dest = str(args.get("path", "")).replace("\\", "/")
                if not (".aether/plans" in dest or ".aether" in dest or "plans" in dest):
                    return False, "Herramienta 'write_file' bloqueada en modo 'PLAN' para archivos de código fuente. Utiliza 'update_plan' para definir el plan de arquitectura antes de implementar."

        # Validación de seguridad en comandos de terminal
        if tool_name == "run_command":
            cmd = args.get("command", "").strip()
            cmd_lower = cmd.lower()

            # Política estricta: Control de Git bajo potestad del desarrollador
            git_forbidden_prefixes = ("git add", "git commit", "git push", "git rm", "git merge", "git rebase")
            if any(cmd_lower.startswith(p) for p in git_forbidden_prefixes):
                return False, (
                    "Comando de Git bloqueado: El control del repositorio pertenece exclusivamente al desarrollador. "
                    "Está terminantemente prohibido ejecutar 'git add' o 'git commit' de forma autónoma. "
                    "Tu trabajo de implementación ha concluido con éxito; concluye el turno ahora e informa al usuario "
                    "para que pueda revisar los cambios con '/diff' y realizar commit con '/commit'."
                )

            is_safe, reason = check_command_safety(cmd)
            if not is_safe:
                return False, f"Comando de alto riesgo bloqueado por política de seguridad: {reason}"

        # Protección del archivo .gitignore
        if tool_name in ["edit_file", "write_file", "delete_file"]:
            target_path = str(args.get("path", "")).replace("\\", "/")
            if target_path.endswith(".gitignore"):
                target_str = str(args.get("target", "") or "")
                content_str = str(args.get("content", "") or "")
                if ".aether" in target_str or ".aether" in content_str:
                    return False, (
                        "Modificación de .gitignore bloqueada: La carpeta '.aether' debe permanecer ignorada por Git. "
                        "No intentes añadir .aether a Git. Concluye tu turno ahora e informa al usuario."
                    )
            # Bloqueo de creación no solicitada de README.md
            if target_path.lower().endswith("readme.md"):
                return False, (
                    "Creación de README.md omitida: El usuario no solicitó documentación README. "
                    "Concéntrate exclusivamente en implementar y hacer pasar las pruebas del código fuente requerido."
                )

        return True, "OK"

    def post_tool_use(self, tool_name: str, args: Dict[str, Any], result: str) -> str:
        """
        Hook ejecutado después de que la herramienta terminó.
        Puede enriquecer el resultado o inyectar advertencias sintácticas.
        """
        # Si fue una edición o escritura de archivo, el Auto-Linter ya evaluó sintaxis
        # Si la salida de run_command indica éxito de pruebas, guiar al modelo a concluir el turno
        if tool_name == "run_command" and "Código de salida: 0" in result:
            if "passed" in result or "test session starts" in result:
                result += (
                    "\n[HOOK POST-TOOL]: ✅ ¡TODAS LAS PRUEBAS PASARON EXITOSAMENTE (Código de salida: 0)!\n"
                    "• Tu verificación ha concluido con éxito. Está PROHIBIDO volver a ejecutar el mismo comando de pruebas.\n"
                    "• Si iniciaste un plan con 'update_plan', ciérralo llamando a 'update_plan(..., is_completed=True)'. De lo contrario, CONCLUYE EL TURNO AHORA e informa al usuario en tu respuesta final el resumen de los archivos creados y pruebas aprobadas."
                )

        # Si se actualizó el plan y quedó completado
        if tool_name == "update_plan" and ("¡Todos los pasos del plan han sido completados" in result or "🎉 COMPLETADO" in result):
            result += (
                "\n[HOOK POST-TOOL]: 🎉 ¡Plan completado y verificado en su totalidad!\n"
                "• CONCLUYE EL TURNO AHORA e informa al usuario en tu respuesta final el resumen de los hitos alcanzados."
            )

        # Si la salida de run_command indica fallo, inyectar alerta de auto-sanación
        if tool_name == "run_command" and ("Código de salida: 1" in result or "Traceback" in result or "FAILED" in result):
            if "EOFError" in result:
                result += (
                    "\n[HOOK POST-TOOL]: 💡 [DIAGNÓSTICO AUTOMÁTICO]: El comando falló con EOFError porque el script ejecutó input() en una terminal no interactiva.\n"
                    "• Para verificar scripts que esperan teclado, ejecuta: run_command(command='python -m py_compile <archivo>.py') o 'python -c \"import <modulo>\"'.\n"
                    "• NUNCA busques 'EOFError' dentro del archivo con edit_file; EOFError es un mensaje de la consola, no código fuente."
                )
            elif "NameError" in result:
                import re
                name_match = re.search(r"NameError:\s+name\s+'([^']+)'\s+is not defined", result)
                missing_name = f" '{name_match.group(1)}'" if name_match else ""
                result += (
                    f"\n[HOOK POST-TOOL]: 💡 [DIAGNÓSTICO AUTOMÁTICO - NOMBRE NO DEFINIDO]:\n"
                    f"• El código falló porque{missing_name} no está importado ni definido.\n"
                    "• Si es un tipo de anotación (ej: Optional, Union, Any, Dict, List, Tuple, Callable), añade al inicio del archivo:\n"
                    "  'from typing import Any, Callable, Dict, List, Optional, Tuple, Union'\n"
                    "• Reescribe el archivo usando 'write_file' con las importaciones necesarias y vuelve a probar."
                )
            elif "ModuleNotFoundError" in result or "ImportError" in result:
                import re
                mod_match = re.search(r"No module named '([^']+)'", result)
                missing_mod = mod_match.group(1) if mod_match else None
                missing_info = f" '{missing_mod}.py'" if missing_mod else " el archivo fuente del módulo"
                result += (
                    f"\n[HOOK POST-TOOL]: 💡 [DIAGNÓSTICO AUTOMÁTICO - MÓDULO NO ENCONTRADO]:\n"
                    f"• Las pruebas no pudieron importar el módulo porque{missing_info} no existe en disco o no fue creado.\n"
                    f"• ACCIÓN OBLIGATORIA: Debes crear{missing_info} inmediatamente usando 'write_file' con la implementación completa solicitada.\n"
                    "• NUNCA elimines las pruebas ni las reemplaces con aserciones triviales como 'assertEqual(1+1, 2)'. Crea el código fuente faltante."
                )
            elif "TypeError" in result:
                result += (
                    "\n[HOOK POST-TOOL]: 💡 [DIAGNÓSTICO AUTOMÁTICO - ERROR DE TIPOS]:\n"
                    "• La prueba falló en la verificación de tipos de datos o argumentos.\n"
                    "• Revisa las firmas y parámetros de la función y actualiza el archivo con 'write_file' o 'edit_file'."
                )
            elif "AssertionError" in result:
                assertion_detail = ""
                if "True is not false" in result:
                    assertion_detail = "\n• Discrepancia booleana: 'assertFalse(...)' falló porque la llamada retornó True. Si estás probando límites de solicitudes, verifica que el bucle haya enviado suficientes solicitudes (>= max_requests) para saturar el cupo antes de esperar False."
                elif "False is not true" in result:
                    assertion_detail = "\n• Discrepancia booleana: 'assertTrue(...)' falló porque la llamada retornó False inesperadamente."
                result += (
                    f"\n[HOOK POST-TOOL]: 💡 [DIAGNÓSTICO AUTOMÁTICO - ASERCIÓN FALLIDA]:{assertion_detail}\n"
                    "• ACCIÓN OBLIGATORIA: Tu SIGUIENTE herramienta DEBE ser 'write_file' o 'edit_file'.\n"
                    "• Corrige el archivo de pruebas ('test_*.py') o la lógica en el archivo fuente de inmediato.\n"
                    "• NUNCA repitas la ejecución de pruebas ni hagas lecturas repetitivas sin antes haber modificado el código en disco."
                )

        # Ejecutar hooks posteriores registrados dinámicamente
        for custom_hook in self._post_hooks:
            try:
                result = custom_hook(tool_name, args, result)
            except Exception:
                pass

        return result
