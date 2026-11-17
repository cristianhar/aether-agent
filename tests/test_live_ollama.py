"""
Prueba de integración viva con Ollama local.
Verifica que el orquestador se conecte correctamente a Ollama.
"""

from agent.orchestrator import AgentOrchestrator


def test_ollama_alive():
    orchestrator = AgentOrchestrator(model="llama3.2:3b")
    is_alive = orchestrator.check_ollama_alive()
    print(f"Ollama activo: {is_alive}")
    assert is_alive, "Ollama no respondió en http://127.0.0.1:11434"


if __name__ == "__main__":
    test_ollama_alive()
