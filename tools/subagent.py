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
