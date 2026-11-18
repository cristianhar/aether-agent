"""
Sistema de Subagentes Lógicos inspirado en Claude Code.
Permite delegar tareas especializadas (investigación, análisis, auditoría)
a instancias con contextos de memoria aislados, compartiendo el mismo modelo local
sin saturar la ventana de tokens de la GPU.
"""

from typing import Any, Dict, Optional


def delegate_task(task_description: str, isolated_context: bool = True) -> str:
    """
    [SUPERPODER SUBAGENTE] Delega una subtarea específica a un subagente auxiliar
    con su propio contexto de memoria limpio. Úsalo para investigar archivos grandes,
    auditar seguridad o correr pruebas sin contaminar la memoria del agente principal.
    """
    from agent.orchestrator import AgentOrchestrator
    from agent.prompts import SYSTEM_PROMPT

    subagent_prompt = f"""Eres un Subagente Especializado de AETHER.
Tu objetivo único es resolver de forma directa, concisa y exhaustiva la siguiente subtarea delegada por el Agente Principal:
<subtask>
{task_description}
</subtask>

Dispones de herramientas completas para inspeccionar archivos, buscar código y ejecutar pruebas.
Cuando termines, devuelve un resumen ejecutivo de tus hallazgos o el resultado de la tarea.
"""

    # Crear una instancia aislada del orquestador que usa el mismo modelo Ollama
    sub_orchestrator = AgentOrchestrator(
        system_prompt=subagent_prompt,
        max_iterations=6
    )

    try:
        report = sub_orchestrator.run_turn(f"Ejecuta y reporta la subtarea: {task_description}")
        return f"=== INFORME DEL SUBAGENTE ===\n{report}"
    except Exception as e:
        return f"Error en la ejecución del subagente: {str(e)}"


def delegate_research(query: str, target_dir: str = ".") -> str:
    """
    [SUBAGENTE RESEARCHER - SOLO LECTURA]
    Delega una exploración de código o investigación documental a un subagente especializado
    en modo de solo lectura (ASK). No puede modificar archivos ni ejecutar comandos destructivos.
    Devuelve un informe técnico condensado con rutas de archivo y números de línea exactos.
    """
    from agent.orchestrator import AgentOrchestrator
    from agent.hooks import HookManager

    researcher_prompt = f"""Eres el Subagente Investigador (Researcher) de AETHER.
Tu único objetivo es explorar e inspeccionar el código o documentación para responder con precisión quirúrgica la siguiente consulta:
<query>
{query}
</query>
Directorio objetivo: {target_dir}

REGLAS ESTRICTAS DE SEGURIDAD Y EFICIENCIA:
1. Operas en MODO DE SOLO LECTURA. Tienes TERMINANTEMENTE PROHIBIDO modificar o crear archivos.
2. Utiliza 'search_codebase', 'read_file', 'get_file_outline', 'get_repo_map', 'find_definition' y 'find_references'.
3. Cuando encuentres la información requerida, concluye directamente tu respuesta indicando:
   - Archivos y números de línea relevantes.
   - Resumen técnico conciso de cómo funciona el código o la causa del bug.
   - Máximo 150 palabras. No divagues ni repitas el código completo.
"""

    hooks = HookManager(mode="ask")
    sub_orchestrator = AgentOrchestrator(
        system_prompt=researcher_prompt,
        max_iterations=6,
    )
    sub_orchestrator.hooks = hooks

    try:
        report = sub_orchestrator.run_turn(f"Investiga y reporta la consulta: {query}")
        return f"=== INFORME DEL SUBAGENTE RESEARCHER ===\n{report}"
    except Exception as e:
        return f"Error en la ejecución del subagente researcher: {str(e)}"


def delegate_test(test_command: str = "pytest", target_file: Optional[str] = None) -> str:
    """
    [SUBAGENTE TESTER - AUDITORÍA DE PRUEBAS]
    Delega la ejecución y diagnóstico de pruebas a un subagente de auditoría.
    Ejecuta los tests, captura el stack trace y emite un informe estructurado de fallos.
    """
    from agent.orchestrator import AgentOrchestrator

    cmd = f"{test_command} {target_file}" if target_file else test_command
    tester_prompt = f"""Eres el Subagente Auditor de Pruebas (Tester) de AETHER.
Tu misión es ejecutar el comando de pruebas '{cmd}', analizar los resultados y diagnosticar cualquier fallo.
Utiliza 'run_command' para ejecutar las pruebas.
Devuelve un resumen estructurado indicando:
1. Pruebas pasadas y pruebas falladas.
2. Causa raíz exacta y líneas culpables de cada fallo.
"""

    sub_orchestrator = AgentOrchestrator(
        system_prompt=tester_prompt,
        max_iterations=4,
    )

    try:
        report = sub_orchestrator.run_turn(f"Ejecuta las pruebas y reporta los diagnósticos: {cmd}")
        return f"=== INFORME DEL SUBAGENTE TESTER ===\n{report}"
    except Exception as e:
        return f"Error en la ejecución del subagente tester: {str(e)}"
