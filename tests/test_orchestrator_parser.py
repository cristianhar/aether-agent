import pytest
from agent.orchestrator import AgentOrchestrator

def test_extract_markdown_json_tool_calls():
    content = """Voy a crear el script solicitado:
```json
{
  "name": "write_file",
  "arguments": {
    "path": "app.py",
    "content": "print('hello')"
  }
}
```
"""
    calls = AgentOrchestrator._extract_tool_calls_from_content(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "write_file"
    assert calls[0]["function"]["arguments"]["path"] == "app.py"

def test_extract_raw_json_tool_calls():
    content = '{"name": "run_command", "arguments": {"command": "pytest"}}'
    calls = AgentOrchestrator._extract_tool_calls_from_content(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "run_command"
    assert calls[0]["function"]["arguments"]["command"] == "pytest"

def test_passive_codeblock_is_not_treated_as_tool_call():
    content = """Aquí tienes una explicación técnica en Python:
Puedes definir la función de la siguiente manera:

```python
import random
def get_secret():
    return random.randint(1, 100)
```
Recuerda llamarla dentro de tu función principal."""

    # Un bloque explicativo pasivo NO debe sintetizar una llamada de herramienta
    calls = AgentOrchestrator._extract_tool_calls_from_content(content)
    assert len(calls) == 0


def test_extract_malformed_json_tool_calls_rescued_by_regex():
    """Verifica que tool calls con comillas triples o escapes inválidos de modelos 7B sean rescatadas."""
    malformed_content = """ {
   "name": "write_file",
   "arguments": {
     "path": "todo_manager.py",
     "content": "import sqlite3\\n\\nclass TodoManager:\\n    def listar_pendientes(self):\\n        query = f\\\"\\\"\\\\\\\"SELECT * FROM tasks\\\"\\\"\\\"\\n"
   }
 }"""
    calls = AgentOrchestrator._extract_tool_calls_from_content(malformed_content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "write_file"
    assert calls[0]["function"]["arguments"]["path"] == "todo_manager.py"
    assert "class TodoManager" in calls[0]["function"]["arguments"]["content"]
