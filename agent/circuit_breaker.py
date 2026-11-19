"""
Módulo de Circuit Breaker y Detección de Ciclos de AETHER IDE.
Contiene la lógica de guardas anti-bucles periódicos, protecciones matemáticas
de ventana deslizante y validaciones heurísticas para evitar ping-pong y estancamiento.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple


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



def extract_test_failure_summary(tool_result: str) -> str:
    """Extrae un resumen limpio de los fallos de tests reportados por pytest o unittest."""
    if not tool_result:
        return ""
    lines = tool_result.splitlines()
    failures = []
    for line in lines:
        s = line.strip()
        if (
            s.startswith("E   ")
            or s.startswith("FAILED ")
            or s.startswith(">   ")
            or re.search(r"\.py:\d+:", s)
            or any(s.startswith(f"{ex}:") or f" {ex}:" in s for ex in [
                "AssertionError", "AttributeError", "ImportError", "TypeError",
                "NameError", "SyntaxError", "ValueError", "KeyError", "IndexError"
            ])
        ):
            failures.append(s)
    if failures:
        return "\n".join(failures[:12])
    non_empty = [l.strip() for l in lines if l.strip()]
    return "\n".join(non_empty[-6:])



def check_circuit_breaker(
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
    if not isinstance(args, dict):
        if isinstance(args, list) and args and isinstance(args[0], dict):
            args = args[0]
        else:
            args = {}

    passive_tools = {
        "read_file", "list_directory", "search_codebase", "grep_search", "grep", "get_file_outline",
        "get_git_status", "get_git_diff", "get_diagnostics", "find_definition",
        "find_references", "get_dependencies", "get_hardware_vram_status", "get_repo_map",
        "get_plan", "conclude_turn", "finish_turn", "complete_task", "finish", "done"
    }

    # Completion Guard: Si el plan fue completado, no permitir nuevas herramientas activas de mutación
    if plan_completed and tool_name not in passive_tools:
        return True, (
            "⛔ [COMPLETION GUARD]: Todos los pasos del plan ya han sido completados y verificados formalmente. "
            "Está prohibido ejecutar más herramientas o crear archivos adicionales en este turno. "
            "Concluye tu turno ahora resumiendo la solución para el usuario en tu respuesta final."
        )

    # Bloqueo de remember_fact repetido
    if tool_name == "remember_fact" and action_history:
        rem_calls = [a for a in action_history if a.startswith("remember_fact:")]
        if len(rem_calls) >= 1:
            return True, (
                "⛔ [CIRCUIT BREAKER - MEMORIA YA REGISTRADA]: El hecho ya fue registrado exitosamente en la memoria del proyecto.\n"
                "• Está TERMINANTEMENTE PROHIBIDO volver a llamar a 'remember_fact' en este turno.\n"
                "• ACCIÓN OBLIGATORIA: Concluye tu turno ahora y responde al usuario confirmando que la información quedó guardada."
            )

    # Bloqueo de search_memory repetido con el mismo query
    if tool_name == "search_memory" and action_history:
        query_str = str(args.get("query") or "").strip()
        same_mem = [a for a in action_history if a == f"search_memory:{query_str}"]
        if len(same_mem) >= 1:
            return True, (
                f"⛔ [CIRCUIT BREAKER - BÚSQUEDA DE MEMORIA DUPLICADA]: Ya consultaste la memoria con '{query_str}'.\n"
                "• ACCIÓN OBLIGATORIA: Concluye tu turno y responde al usuario con los datos de memoria obtenidos arriba."
            )

    # Regla Anti-Alucinación de Archivos Genéricos (module.py, test_module.py, etc.)
    if tool_name in ["write_file", "edit_file"]:
        target_p = str(args.get("path", "") or "")
        target_name = Path(target_p).name.lower()
        generic_hallucinations = {
            "module.py", "test_module.py", "example.py", "test_example.py",
            "sample.py", "test_sample.py", "foo.py", "test_foo.py", "bar.py",
            "unit_tests.py", "test_math.py", "math_library.py"
        }
        if target_name in generic_hallucinations and target_name not in user_prompt.lower():
            return True, (
                f"⛔ [CIRCUIT BREAKER - ARCHIVO GENÉRICO BLOQUEADO]: '{target_name}' es un archivo de plantilla genérica alucinado.\n"
                "• Está TERMINANTEMENTE PROHIBIDO crear módulos ficticios como 'module.py' o 'test_module.py'.\n"
                "• ACCIÓN OBLIGATORIA: Revisa la solicitud inicial del usuario e implementa ÚNICAMENTE los archivos especificados en la tarea."
            )

    # Bloqueo de herramientas de memoria persistente durante depuración activa de fallos en tests
    if tool_name in ["remember_fact", "search_memory", "list_memories"] and last_test_exit_code is not None and last_test_exit_code != 0:
        return True, (
            "⛔ [CIRCUIT BREAKER]: Las pruebas unitarias están fallando actualmente.\n"
            "• Concéntrate en depurar y corregir el código con 'edit_file' o 'write_file' y luego ejecutar 'run_tests()'.\n"
            "• NO uses herramientas de memoria persistente mientras haya errores activos en los tests."
        )

    # Regla: Verificación Obligatoria tras Modificación de Código
    if tool_name in ["write_file", "edit_file"]:
        target_path_str = str(args.get("path", "") or "")
        target_file_obj = Path(target_path_str) if target_path_str else None
        if target_file_obj and not target_file_obj.name.startswith("test_"):
            recent_writes = [
                a for a in (action_history or [])
                if (a.startswith("write_file:") or a.startswith("edit_file:"))
                and target_file_obj.name in a
            ]
            if len(recent_writes) >= 1:
                # Caso A: Las pruebas fallaron previamente y el archivo ya fue modificado
                if last_test_exit_code is not None and last_test_exit_code != 0 and files_modified_since_cmd_fail:
                    return True, (
                        f"⛔ [CIRCUIT BREAKER - VERIFICACIÓN OBLIGATORIA]: Ya aplicaste una modificación sobre '{target_file_obj.name}'.\n"
                        f"• Está TERMINANTEMENTE PROHIBIDO volver a modificar o sobrescribir '{target_file_obj.name}' sin haber comprobado el resultado.\n"
                        "• ACCIÓN OBLIGATORIA: Tu siguiente llamada DEBE SER 'run_tests()' o 'run_command(command=\"pytest\")' para verificar si el error fue resuelto."
                    )
                # Caso B: Refactorización o edición inicial realizada pero aún no se ejecutan las pruebas
                stem = target_file_obj.stem
                test_files = list(Path.cwd().glob(f"test_{stem}.py")) or list(Path.cwd().glob("test_*.py"))
                if test_files and not tests_executed_in_turn:
                    return True, (
                        f"⛔ [CIRCUIT BREAKER - VERIFICACIÓN OBLIGATORIA]: Ya modificaste el código en '{target_file_obj.name}'.\n"
                        f"• Está TERMINANTEMENTE PROHIBIDO volver a sobrescribir '{target_file_obj.name}' antes de comprobar que las pruebas unitarias pasen.\n"
                        "• ACCIÓN OBLIGATORIA: Tu siguiente llamada DEBE SER 'run_tests()' o 'run_command(command=\"pytest\")' para verificar la refactorización."
                    )

    # Regla Anti-Bucle de Inspección Pasiva tras Verificación Exitosa de Código
    if tool_name in ["get_repo_map", "list_directory", "search_codebase", "grep_search", "grep"]:
        if last_test_exit_code == 0 and files_modified_in_turn:
            return True, (
                "⛔ [COMPLETION GUARD]: Todas las pruebas unitarias ya pasaron exitosamente (Exit code 0) "
                "y los archivos requeridos están completos en disco. Concluye tu turno ahora resumiendo la solución para el usuario."
            )

    if tool_name in ["read_file", "get_file_outline", "get_git_diff", "get_git_status", "get_repo_map", "list_directory", "search_codebase", "grep_search", "grep", "get_diagnostics"]:

        # Bloqueo de get_diagnostics repetido en el mismo archivo
        if tool_name == "get_diagnostics" and action_history:
            target_p = str(args.get("path", "") or "")
            same_diag = [a for a in action_history if a.startswith(f"get_diagnostics:{target_p}")]
            if len(same_diag) >= 1:
                return True, (
                    f"⛔ [CIRCUIT BREAKER - DIAGNÓSTICO DUPLICADO]: Ya obtuviste el diagnóstico de '{target_p}'. El código no tiene errores de sintaxis.\n"
                    "• ACCIÓN OBLIGATORIA: Modifica el archivo de implementación ('math_lib.py') con 'edit_file' para corregir la aserción y corre 'run_tests()'."
                )

        # Bloqueo de get_repo_map repetido
        if tool_name == "get_repo_map" and action_history:
            repo_map_calls = [a for a in action_history if a.startswith("get_repo_map")]
            if len(repo_map_calls) >= 1:
                return True, (
                    "⛔ [CIRCUIT BREAKER - INSPECCIÓN DUPLICADA]: Ya has obtenido el mapa completo del repositorio (get_repo_map) "
                    "y su estructura está en tu contexto. No vuelvas a solicitarlo.\n"
                    "• ACCIÓN OBLIGATORIA: Procede a responder directamente la consulta del usuario o a estructurar el plan/código solicitado."
                )

        # Bloqueo de búsqueda duplicada con mismo query
        if tool_name in ["search_codebase", "grep_search", "grep"] and action_history:
            query_str = str(args.get("query") or "").strip()
            if query_str:
                same_search = [a for a in action_history if a == f"{tool_name}:{query_str}"]
                if len(same_search) >= 1:
                    return True, (
                        f"⛔ [CIRCUIT BREAKER - BÚSQUEDA DUPLICADA]: Ya ejecutaste la búsqueda de '{query_str}' anteriormente.\n"
                        "• ACCIÓN OBLIGATORIA: Analiza la información obtenida y responde al usuario o avanza en la tarea sin repetir la misma búsqueda."
                    )

        # Bloqueo de list_directory repetido en misma ruta
        if tool_name == "list_directory" and action_history:
            path_str = str(args.get("path", ".") or ".").strip()
            same_list = [a for a in action_history if a == f"list_directory:{path_str}"]
            if len(same_list) >= 1:
                return True, (
                    f"⛔ [CIRCUIT BREAKER - LISTADO DUPLICADO]: Ya listaste el directorio '{path_str}'.\n"
                    "• ACCIÓN OBLIGATORIA: Usa la lista de archivos disponible en el historial para proceder."
                )

        target_path_str = str(args.get("path", "") or "")
        if target_path_str and action_history:
            target_base = Path(target_path_str).name
            recent_reads = [
                a for a in action_history[-4:]
                if (a.startswith("read_file:") or a.startswith("get_file_outline:"))
                and (target_path_str in a or (target_base and target_base in a))
            ]
            if len(recent_reads) >= 2:
                return True, (
                    f"⛔ [CIRCUIT BREAKER - INSPECCIÓN REPETITIVA]: Ya has inspeccionado '{target_base}' repetidamente y su contenido "
                    "completo está presente arriba en la conversación. No vuelvas a leerlo.\n"
                    "• ACCIÓN OBLIGATORIA: Tu siguiente herramienta DEBE ser 'write_file' o 'edit_file' para corregir el código fuente o las pruebas, o responder al usuario si estás en modo lectura/plan."
                )

        # Detección de ciclos periódicos en herramientas pasivas
        if action_history and len(action_history) >= 2:
            passive_history = [a for a in action_history if any(a.startswith(f"{p}:") or a == p for p in passive_tools)]
            if tool_name == "get_repo_map":
                curr_sig = "get_repo_map"
            elif tool_name in ["search_codebase", "grep_search", "grep"]:
                curr_sig = f"{tool_name}:{args.get('query', '')}"
            elif tool_name == "list_directory":
                curr_sig = f"list_directory:{args.get('path', '.')}"
            else:
                curr_sig = f"{tool_name}:{args.get('path', '')}"
            candidate_passive = list(passive_history) + [curr_sig]
            cycle_p = detect_action_cycle(candidate_passive, max_period=3, min_repeats=2)
            if cycle_p:
                period_p, pattern_p = cycle_p
                cycle_p_str = " ➔ ".join(pattern_p)
                return True, (
                    f"⛔ [CIRCUIT BREAKER - CICLO DE INSPECCIÓN DETECTADO]: Has entrado en un ciclo repetitivo de inspección ({cycle_p_str}).\n"
                    "Ya dispones de toda la información del entorno en tu contexto de conversación.\n"
                    "• ACCIÓN OBLIGATORIA: Detén de inmediato las herramientas de inspección y responde al usuario con la arquitectura, diseño o explicación solicitada."
                )

    tool_call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"

    # Regla 0: Detector Matemático Universal de Ciclos Periódicos (Periodos p=1, 2, 3)
    # Aplica a herramientas activas de mutación o ejecución
    active_action_history = [a for a in (action_history or []) if not any(a.startswith(f"{p}:") or a == p for p in passive_tools)]
    if tool_name not in passive_tools and active_action_history:
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
            # Si es write_file, verificar si es una mutación genuina (contenido diferente al del disco)
            is_genuine_mutation = False
            if tool_name == "write_file" and target_path_str:
                try:
                    p_disk = Path(target_path_str).resolve()
                    new_c = str(args.get("content", ""))
                    if p_disk.is_file():
                        curr_c = p_disk.read_text(encoding="utf-8", errors="replace")
                        if curr_c.strip() != new_c.strip():
                            stem = Path(target_path_str).stem
                            if not stem.startswith("test_"):
                                expected_test = f"test_{stem}.py"
                                if expected_test in user_prompt and not (Path.cwd() / expected_test).is_file():
                                    consecutive_writes = sum(1 for a in active_action_history[-3:] if a.startswith(f"write_file:{target_path_str}"))
                                    is_genuine_mutation = consecutive_writes < 1
                                else:
                                    is_genuine_mutation = True
                            else:
                                is_genuine_mutation = True
                    else:
                        is_genuine_mutation = True
                except Exception:
                    pass

            if not is_genuine_mutation:
                if tool_name == "update_plan":
                    current_signature = f"update_plan:step_{args.get('current_step', '')}_{args.get('is_completed', '')}"
                elif tool_name in ["remember_fact", "search_memory", "list_memories"]:
                    current_signature = f"{tool_name}:{args.get('key') or args.get('query') or ''}"
                else:
                    current_signature = f"{tool_name}:{args.get('path') or args.get('command') or ''}"
                candidate_history = list(active_action_history) + [current_signature]
                cycle = detect_action_cycle(candidate_history, max_period=3, min_repeats=2)
                if cycle:
                    period, pattern = cycle
                    # Condición de bloqueo para ciclo periódico:
                    # 1. Herramienta de ejecución/test (run_command, run_tests) repitiéndose sin mutación en disco
                    # 2. Periodo 1: repetición inmediata de la misma herramienta con los mismos argumentos
                    # 3. Periodo >= 2: permitir hasta 3 ciclos completos para depuración/TDD antes de bloquear
                    is_test_cmd_without_changes = (tool_name in ["run_command", "run_tests"] and not files_modified_since_cmd_fail)
                    is_immediate_repeat = (period == 1 and active_action_history and active_action_history[-1] == current_signature)

                    pattern_repeats = 0
                    req_len = period
                    if active_action_history and len(active_action_history) >= req_len:
                        for k in range(len(active_action_history) - req_len, -1, -req_len):
                            if active_action_history[k:k+req_len] == pattern:
                                pattern_repeats += 1
                            else:
                                break

                    should_block_cycle = is_test_cmd_without_changes or is_immediate_repeat or (pattern_repeats >= 2)
                    if should_block_cycle:
                        cycle_str = " ➔ ".join(pattern)
                        if tool_name in ["run_command", "run_tests"]:
                            if last_test_exit_code == 0:
                                cycle_hint = (
                                    "• Las pruebas ya pasaron exitosamente (Exit code 0): tu verificación ha CONCLUIDO CON ÉXITO. "
                                    "NO vuelvas a ejecutar el comando. Concluye el turno e informa al usuario en tu respuesta final."
                                )
                            elif last_test_exit_code is not None and last_test_exit_code != 0:
                                failure_detail = f"\n📋 [DETALLE DEL FALLO EN TESTS]:\n{last_test_failure_summary}\n" if last_test_failure_summary else ""
                                cycle_hint = (
                                    "• Las pruebas FALLARON (Exit code != 0). NO puedes dar la tarea por concluida ni repetir el comando sin cambios.\n"
                                    f"{failure_detail}"
                                    "• ACCIÓN OBLIGATORIA: Analiza el Traceback o fallo reportado y modifica el código fuente o el archivo de pruebas usando 'write_file' o 'edit_file'."
                                )
                            else:
                                cycle_hint = (
                                    "• Si las pruebas ya pasaron exitosamente (Exit code 0), tu verificación ha CONCLUIDO CON ÉXITO: NO vuelvas a ejecutar el mismo comando. Concluye el turno e informa al usuario en tu respuesta final.\n"
                                    "• Si las pruebas fallaron, debes modificar el código fuente con 'write_file' o 'edit_file' antes de volver a ejecutarlas."
                                )
                        else:
                            target_file_obj = Path(target_path_str) if target_path_str else None
                            if target_file_obj and target_file_obj.suffix == ".py":
                                t_stem = target_file_obj.stem
                                if t_stem.startswith("test_"):
                                    cycle_hint = (
                                        f"• El archivo de pruebas '{target_file_obj.name}' ya fue creado y guardado en disco.\n"
                                        "• Tu SIGUIENTE ACCIÓN OBLIGATORIA es ejecutar las pruebas llamando a 'run_tests()' o 'run_command(command=\"pytest\")'.\n"
                                        f"• NO vuelvas a escribir '{target_file_obj.name}' sin haber ejecutado las pruebas primero."
                                    )
                                else:
                                    expected_test_file = f"test_{t_stem}.py"
                                    test_exists = (Path.cwd() / expected_test_file).is_file()
                                    if test_exists:
                                        failure_detail = f"\n📋 [DETALLE DEL FALLO EN TESTS]:\n{last_test_failure_summary}\n" if last_test_failure_summary else ""
                                        cycle_hint = (
                                            f"• El archivo '{target_file_obj.name}' y sus pruebas '{expected_test_file}' ya existen en disco, "
                                            "pero tus acciones consecutivas no están produciendo modificaciones efectivas.\n"
                                            f"{failure_detail}"
                                            f"• ACCIÓN OBLIGATORIA: Debes cambiar la lógica del código en '{target_file_obj.name}' o '{expected_test_file}' usando 'write_file' para corregir el fallo, o ejecutar 'run_tests()'."
                                        )
                                    else:
                                        cycle_hint = (
                                            f"• El archivo '{target_file_obj.name}' ya fue creado y guardado en disco.\n"
                                            f"• Tu SIGUIENTE ACCIÓN OBLIGATORIA es llamar a 'write_file(path=\"{expected_test_file}\", content=...)' para implementar las pruebas unitarias de '{target_file_obj.name}'.\n"
                                            f"• NUNCA inventes nombres de archivos no pedidos. Implementa '{expected_test_file}'."
                                        )
                            else:
                                prompt_test_files = re.findall(r"\b(test_[a-zA-Z0-9_\-\.]+\.py)\b", user_prompt)
                                prompt_src_files = [f for f in re.findall(r"\b([a-zA-Z0-9_\-\.]+\.py)\b", user_prompt) if not f.startswith("test_")]
                                missing_src = [f for f in prompt_src_files if not (Path.cwd() / f).is_file()]

                                if tool_name == "update_plan":
                                    cycle_hint = (
                                        "• Ya actualizaste el plan anteriormente con este mismo estado. "
                                        "Avanza a la implementación del siguiente paso o concluye el turno si el plan fue completado."
                                    )
                                elif missing_src:
                                    target_src = missing_src[0]
                                    cycle_hint = (
                                        f"• El archivo solicitado '{target_src}' AÚN NO HA SIDO CREADO en el disco.\n"
                                        f"• Tu SIGUIENTE ACCIÓN OBLIGATORIA es llamar a 'write_file(path=\"{target_src}\", content=...)' para implementarlo.\n"
                                        f"• NO vuelvas a llamar a '{tool_name}' sin haber creado el código fuente primero."
                                    )
                                elif prompt_test_files and not (Path.cwd() / prompt_test_files[0]).is_file():
                                    target_test = prompt_test_files[0]
                                    cycle_hint = (
                                        f"• El archivo de pruebas '{target_test}' aún no ha sido creado en el disco.\n"
                                        f"• Tu SIGUIENTE ACCIÓN OBLIGATORIA es llamar a 'write_file(path=\"{target_test}\", content=...)' para implementarlo.\n"
                                        f"• NO vuelvas a llamar a '{tool_name}' sin avanzar en la tarea."
                                    )
                                else:
                                    cycle_hint = (
                                        "• Si ya creaste tanto el código como las pruebas, ejecútalas usando 'run_tests()' o 'run_command(command=\"pytest\")'.\n"
                                        f"• NO vuelvas a llamar a '{tool_name}' con los mismos argumentos sin avanzar en la tarea."
                                    )
                        msg = (
                            f"⛔ [CIRCUIT BREAKER UNIVERSAL - CICLO PERIÓDICO DETECTADO (Periodo {period})]:\n"
                            f"La acción '{current_signature}' se está repitiendo consecutivamente sin modificaciones en el disco: {cycle_str}.\n"
                            f"{cycle_hint}"
                        )
                        return True, msg

    # Combinar failed_commands con last_failed_command para retrocompatibilidad
    active_failed_cmds = set(failed_commands or set())
    if last_failed_command:
        active_failed_cmds.add(last_failed_command.strip().lower())

    # Regla 1: run_command / run_tests que ya falló previamente sin haber modificado archivos
    if tool_name in ["run_command", "run_tests"]:
        cmd_norm = args.get("command", "").strip().lower() if tool_name == "run_command" else f"pytest {args.get('test_target', '.')}".strip().lower()
        if active_failed_cmds and cmd_norm in active_failed_cmds and not files_modified_since_cmd_fail:
            if consecutive_edit_failures >= 1:
                action_hint = "• ACCIÓN OBLIGATORIA: Tus intentos de edición no han modificado el archivo exitosamente. Usa 'read_file' para inspeccionar el archivo o reescríbelo con 'write_file'. NO vuelvas a ejecutar el mismo comando sin cambios en disco."
            else:
                action_hint = "• ACCIÓN OBLIGATORIA: Si aún no has corregido el código, usa 'read_file' para inspeccionarlo, 'edit_file' para modificar el bloque exacto, o 'write_file' para reescribirlo. Si la verificación ya concluyó con éxito, concluye el turno e informa al usuario en tu respuesta final para que lo ejecute en su propia terminal."
            target_cmd_display = args.get("command") or f"run_tests({args.get('test_target', '')})"
            msg = (
                f"⛔ [CIRCUIT BREAKER]: El comando de pruebas '{target_cmd_display}' ya falló previamente y NO has modificado ningún archivo en el disco desde entonces.\n"
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

    # Regla 7: Bloqueo de completitud prematura o bucles de update_plan
    if tool_name == "update_plan":
        is_marking_completed = bool(args.get("is_completed"))
        if is_marking_completed and last_test_exit_code is not None and last_test_exit_code != 0:
            failure_detail = f"\n📋 [DETALLE DEL FALLO EN TESTS]:\n{last_test_failure_summary}\n" if last_test_failure_summary else ""
            return True, (
                "⛔ [CIRCUIT BREAKER - COMPLETITUD PREMATURA BLOQUEADA]: Intentas marcar el plan como COMPLETADO, "
                f"pero la última ejecución de pruebas falló (Exit Code {last_test_exit_code}).\n"
                f"{failure_detail}"
                "• ACCIÓN OBLIGATORIA: No puedes completar el plan mientras las pruebas fallen. Corrige el código o los tests primero usando 'write_file' o 'edit_file', y vuelve a ejecutar 'run_tests()'."
            )
        if is_marking_completed and not files_modified_in_turn:
            if any(k in user_prompt.lower() for k in ["crea", "implementa", "modifica", "refactoriza", "cambia", "corrige"]):
                return True, (
                    "⛔ [CIRCUIT BREAKER - COMPLETITUD PREMATURA BLOQUEADA]: Intentas marcar el plan como COMPLETADO, "
                    "pero aún no has aplicado la modificación o refactorización solicitada sobre el código en disco.\n"
                    "• ACCIÓN OBLIGATORIA: Modifica primero el archivo con 'edit_file' o 'write_file', ejecuta 'run_tests()' para verificar, y solo después completa el plan."
                )
        # Bloqueo de llamadas repetidas a update_plan sin haber mutado código en tareas de desarrollo
        if not is_marking_completed and action_history:
            plan_calls = [a for a in action_history if a.startswith("update_plan:")]
            is_code_task = any(k in user_prompt.lower() for k in ["crea", "implementa", "modifica", "refactoriza", "cambia", "corrige"])
            if is_code_task and len(plan_calls) >= 1 and not files_modified_since_cmd_fail and not files_modified_in_turn:
                prompt_src_files = [f for f in re.findall(r"\b([a-zA-Z0-9_\-\.]+\.py)\b", user_prompt) if not f.startswith("test_")]
                target_file_hint = f" en '{prompt_src_files[0]}'" if prompt_src_files else ""
                return True, (
                    "⛔ [CIRCUIT BREAKER - PLAN YA DEFINIDO]: El plan ya fue registrado formalmente en el entorno.\n"
                    "• Está TERMINANTEMENTE PROHIBIDO seguir llamando a 'update_plan' sin haber implementado o modificado código.\n"
                    f"• ACCIÓN OBLIGATORIA: Tu siguiente herramienta DEBE SER 'edit_file'{target_file_hint} o 'write_file'{target_file_hint} para realizar los cambios solicitados (sin usar marcadores '<>')."
                )

    if tool_name == "get_plan" and action_history:
        plan_updates = [a for a in action_history if a.startswith("update_plan:")]
        if len(plan_updates) >= 1 and not files_modified_in_turn:
            prompt_src_files = [f for f in re.findall(r"\b([a-zA-Z0-9_\-\.]+\.py)\b", user_prompt) if not f.startswith("test_")]
            target_file_hint = f" en '{prompt_src_files[0]}'" if prompt_src_files else ""
            return True, (
                "⛔ [CIRCUIT BREAKER - CONSULTA REDUNDANTE]: Acabas de actualizar el plan y su contenido completo está en tu contexto.\n"
                f"• ACCIÓN OBLIGATORIA: Procede de inmediato a modificar el código fuente con 'edit_file'{target_file_hint} o 'write_file'{target_file_hint}."
            )

    return False, ""
