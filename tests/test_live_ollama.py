"""
Prueba de integración viva con Ollama local.
Verifica que el orquestador se conecte correctamente a Ollama.
"""

import pytest
from agent.orchestrator import AgentOrchestrator


@pytest.mark.integration
def test_ollama_alive():
    orchestrator = AgentOrchestrator(model="llama3.2:3b")
    is_alive = orchestrator.check_ollama_alive()
    if not is_alive:
        pytest.skip("Ollama no está en ejecución o el entorno no tiene acceso a sockets locales.")
    assert is_alive


if __name__ == "__main__":
    test_ollama_alive()
