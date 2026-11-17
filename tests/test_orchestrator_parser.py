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

def test_fallback_python_codeblock_synthesis():
    content = """Aquí tienes el juego en Python:
Guarda el código en un archivo llamado `adivinanza.py`:

```python
import random
print(random.randint(1, 10))
```
¡Disfrútalo!"""

    calls = AgentOrchestrator._extract_tool_calls_from_content(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "write_file"
    assert calls[0]["function"]["arguments"]["path"] == "adivinanza.py"
    assert "import random" in calls[0]["function"]["arguments"]["content"]
