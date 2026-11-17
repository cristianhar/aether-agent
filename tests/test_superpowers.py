import os
import tempfile
import pytest
from tools.file_tools import edit_file, write_file
from tools.search_tools import get_file_outline
from tools.web_tools import search_web, fetch_web_page

def test_fuzzy_matching_edit():
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as f:
        f.write("def calculate(x, y):\n    # Some comment\n    result = x + y\n    return result\n")
        temp_path = f.name

    try:
        # Target con espacios finales omitidos o diferencia leve
        target = "    result = x + y \n    return result"
        replacement = "    result = (x + y) * 2\n    return result"
        res = edit_file(temp_path, target, replacement)
        assert "Éxito" in res
        assert "coincidencia inteligente de espacios" in res

        with open(temp_path, "r") as f:
            new_code = f.read()
        assert "(x + y) * 2" in new_code
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_auto_linter_detects_syntax_error():
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as f:
        f.write("def valid_func():\n    pass\n")
        temp_path = f.name

    try:
        # Modificar introduciendo un error de sintaxis intencional (olvido de dos puntos y paréntesis)
        target = "    pass"
        replacement = "    if True\n        print('bad')"
        res = edit_file(temp_path, target, replacement)
        assert "Éxito" in res
        assert "Auto-Linter" in res
        assert "Error de sintaxis" in res
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_get_file_outline():
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as f:
        f.write("""
class GameTrainer:
    '''Clase para manipular memoria.'''
    def __init__(self, pid: int):
        self.pid = pid

    def read_address(self, addr: int) -> int:
        return 100

def top_level_helper():
    pass
""")
        temp_path = f.name

    try:
        outline = get_file_outline(temp_path)
        assert "class GameTrainer" in outline
        assert "def __init__(self, pid)" in outline
        assert "def read_address(self, addr)" in outline
        assert "def top_level_helper()" in outline
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_web_search_and_fetch():
    res = search_web("python pymem documentation", max_results=2)
    assert ("Resultados de búsqueda" in res) or ("Aviso de red" in res)

    # Test fetch_web_page con una URL segura
    page = fetch_web_page("https://example.com", max_chars=500)
    assert ("Example Domain" in page) or ("Error al descargar" in page)
