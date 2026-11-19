"""
Guardianes de Turno y Proactividad Autónoma para AETHER IDE.
Intercepta respuestas conversacionales prematuras, desviaciones pasivas,
pruebas pendientes de verificación y cierres automáticos de planes activos.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Optional


@dataclass
class GuardianDecision:
    """Decisión emitida por el motor de guardianes de turno."""
    should_continue: bool = False
    user_hint: Optional[str] = None
    plan_completed: bool = False
    proactive_prompts_sent: int = 0


def evaluate_no_tool_call_guardians(
    content: str,
    user_prompt: str,
    iteration: int,
    max_iterations: int,
    mode: str,
    plan_active_in_turn: bool,
    plan_completed_in_turn: bool,
    last_test_exit_code: Optional[int],
    last_test_failure_summary: Optional[str],
    files_modified_in_turn: bool,
    tests_executed_in_turn: bool,
    action_history: List[str],
    proactive_prompts_sent: int,
) -> GuardianDecision:
    """
    Evalúa si una respuesta del LLM sin llamadas a herramientas es válida para concluir
    el turno o si viola las directivas de proactividad, verificación o cierre de planes.
    """
    # 1. Detección de tool call fantasma malformado en JSON
    if not plan_completed_in_turn and '"name":' in content and ('"arguments":' in content or '"path":' in content or '"command":' in content):
        if iteration < max_iterations:
            retry_hint = (
                "[SISTEMA AETHER]: Se detectó que intentaste emitir una llamada a herramienta en formato JSON, "
                "pero no pudo ser ejecutada por errores de formato o sintaxis. "
                "Por favor emite la llamada usando la herramienta directamente sin escapar triples comillas de Python dentro de strings."
            )
            return GuardianDecision(
                should_continue=True,
                user_hint=retry_hint,
                plan_completed=plan_completed_in_turn,
                proactive_prompts_sent=proactive_prompts_sent,
            )

    # 2. Guardián de Cierre de Plan Activo
    if plan_active_in_turn and not plan_completed_in_turn and iteration < max_iterations - 1:
        if last_test_exit_code == 0 and files_modified_in_turn:
            try:
                from tools.agent_tools import update_plan
                update_plan(is_completed=True)
            except Exception:
                pass
            plan_completed_in_turn = True
        else:
            plan_guard_hint = (
                "[SISTEMA AETHER - CIERRE DE PLAN REQUERIDO]: Has emitido una respuesta final pero el plan activo en '.aether/plans/plan_activo.md' "
                "aún no ha sido marcado como COMPLETADO con 'update_plan(..., is_completed=True)'.\n"
                "• Si todas las pruebas pasaron y los archivos pedidos fueron creados, tu OBLIGACIÓN es llamar a 'update_plan(plan_steps=..., is_completed=True)' para cerrar el plan.\n"
                "• Si aún falta implementar algún archivo o ejecutar tests, ejecuta la herramienta correspondiente ahora."
            )
            return GuardianDecision(
                should_continue=True,
                user_hint=plan_guard_hint,
                plan_completed=plan_completed_in_turn,
                proactive_prompts_sent=proactive_prompts_sent,
            )

    # 3. Guardián de Pruebas Fallidas
    if last_test_exit_code is not None and last_test_exit_code != 0 and iteration < max_iterations - 1:
        failure_detail = f"\n📋 [DETALLE DEL FALLO EN TESTS]:\n{last_test_failure_summary}\n" if last_test_failure_summary else ""
        test_failed_guard = (
            "[SISTEMA AETHER - CORRECCIÓN DE PRUEBAS OBLIGATORIA]: No puedes dar la tarea por concluida ni pedir datos al usuario porque las pruebas unitarias FALLARON (Exit code != 0).\n"
            f"{failure_detail}\n"
            "• Está TERMINANTEMENTE PROHIBIDO responder con texto conversacional, confirmaciones o preguntas.\n"
            "• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'write_file' o 'edit_file' para corregir el error indicado arriba."
        )
        return GuardianDecision(
            should_continue=True,
            user_hint=test_failed_guard,
            plan_completed=plan_completed_in_turn,
            proactive_prompts_sent=proactive_prompts_sent,
        )

    # 4. Análisis de desvío prematuro y pasividad
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
        mode not in ["ask", "plan"]
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

    # 5. Guardián de Exploración Autónoma
    inspection_tools_used = any(
        any(t in a for t in ["list_directory", "get_repo_map", "read_file", "search_codebase"])
        for a in action_history
    )
    if is_workspace_listing_task and not inspection_tools_used and iteration < max_iterations - 1 and proactive_prompts_sent < 2:
        inspection_hint = (
            "[SISTEMA AETHER - EXPLORACIÓN DE PROYECTO OBLIGATORIA]: El usuario solicitó conocer qué archivos o elementos existen en el proyecto.\n"
            "• Está TERMINANTEMENTE PROHIBIDO responder con evasivas, disculpas sobre MCP o preguntas pasivas.\n"
            "• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'list_directory(path=\".\")' o 'get_repo_map()' "
            "para leer físicamente los archivos del disco e informar al usuario."
        )
        return GuardianDecision(
            should_continue=True,
            user_hint=inspection_hint,
            plan_completed=plan_completed_in_turn,
            proactive_prompts_sent=proactive_prompts_sent + 1,
        )

    # 6. Guardián Anti-Pasividad
    passive_file_begging = any(p in content.lower() for p in [
        "comparte el código", "compartir el código", "comparte el archivo", "compartir el archivo",
        "pásame el código", "pasame el contenido", "pásame el archivo", "pasame el archivo",
        "no tengo acceso al archivo", "puedes compartir", "podrías compartir", "podrias compartir",
        "envíame el código", "enviame el código", "envíame el archivo", "enviame el archivo",
        "más detalles sobre el contenido del archivo", "proporcióname el código", "proporcioname el código",
        "proporciones el código", "proporcione el código", "necesito que me proporciones el código"
    ])
    if mode not in ["plan"] and not has_attached_context and passive_file_begging and iteration < max_iterations - 1 and proactive_prompts_sent < 2:
        file_inspection_hint = (
            "[SISTEMA AETHER - AUTO-INSPECCIÓN OBLIGATORIA]: NUNCA le pidas el archivo o código al usuario.\n"
            "• Eres un agente local autónomo con acceso directo al disco: si necesitas leer un archivo, "
            "usa 'read_file(path=...)' o 'get_file_outline(path=...)' directamente para inspeccionarlo tú mismo."
        )
        return GuardianDecision(
            should_continue=True,
            user_hint=file_inspection_hint,
            plan_completed=plan_completed_in_turn,
            proactive_prompts_sent=proactive_prompts_sent + 1,
        )

    # 7. Guardián de Modificación Requerida
    if modification_requested and mode not in ["ask", "plan"] and not files_modified_in_turn and iteration < max_iterations - 1 and proactive_prompts_sent < 2:
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
        return GuardianDecision(
            should_continue=True,
            user_hint=mod_hint,
            plan_completed=plan_completed_in_turn,
            proactive_prompts_sent=proactive_prompts_sent + 1,
        )

    # 8. Guardián de Tareas de Código y Verificación
    if is_code_task:
        if missing_requested_files and iteration < max_iterations - 1 and proactive_prompts_sent < 2:
            missing_f = missing_requested_files[0]
            missing_file_hint = (
                f"[SISTEMA AETHER - ENTREGABLE FALTANTE]: La solicitud del usuario requirió crear '{missing_f}', pero este archivo no existe en el disco.\n"
                f"• ACCIÓN OBLIGATORIA: Tu respuesta en este turno DEBE SER DIRECTAMENTE una llamada a 'write_file(path=\"{missing_f}\", content=...)' para implementar este archivo."
            )
            return GuardianDecision(
                should_continue=True,
                user_hint=missing_file_hint,
                plan_completed=plan_completed_in_turn,
                proactive_prompts_sent=proactive_prompts_sent + 1,
            )

        tests_exist = bool(list(Path.cwd().glob("test_*.py")) or list(Path.cwd().glob("*_test.py")) or (Path.cwd() / "tests").exists())
        missing_tests = tests_requested and not tests_exist
        tests_pending_execution = (tests_requested or files_modified_in_turn) and tests_exist and not tests_executed_in_turn

        if (is_premature_deflection or missing_tests or tests_pending_execution) and proactive_prompts_sent < 2 and iteration < max_iterations - 1:
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
            return GuardianDecision(
                should_continue=True,
                user_hint=proactive_hint,
                plan_completed=plan_completed_in_turn,
                proactive_prompts_sent=proactive_prompts_sent + 1,
            )

    return GuardianDecision(
        should_continue=False,
        user_hint=None,
        plan_completed=plan_completed_in_turn,
        proactive_prompts_sent=proactive_prompts_sent,
    )
