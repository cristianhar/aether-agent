import pytest
from pathlib import Path
from tools.search_tools import list_directory, search_codebase
from tools.file_tools import write_file


def test_list_directory_and_search(tmp_path):
    # Crear estructura de prueba
    sub_dir = tmp_path / "src"
    sub_dir.mkdir()
    file_a = sub_dir / "service.py"
    write_file(str(file_a), "def authenticate_user(token):\n    return token == 'secret'\n")

    # List directory
    tree = list_directory(str(tmp_path))
    assert "src/" in tree
    assert "service.py" in tree

    # Search codebase
    search_res = search_codebase("authenticate_user", str(tmp_path))
    assert "service.py" in search_res
    assert "authenticate_user" in search_res


def test_search_codebase_with_file_pattern_and_pattern_kwarg(tmp_path):
    sub_dir = tmp_path / "app"
    sub_dir.mkdir()
    py_file = sub_dir / "logic.py"
    txt_file = sub_dir / "notes.txt"

    write_file(str(py_file), "def calculate_discount(price):\n    return price * 0.9\n")
    write_file(str(txt_file), "calculate_discount is documented here\n")

    # Búsqueda con pattern kwarg y file_pattern='*.py'
    res_py = search_codebase(pattern="calculate_discount", path=str(tmp_path), file_pattern="*.py")
    assert "logic.py" in res_py
    assert "notes.txt" not in res_py

    # Dispatcher execute_tool con grep_search
    from tools.registry import execute_tool
    res_dispatch = execute_tool("grep_search", {"query": "calculate_discount", "path": str(tmp_path), "file_pattern": "*.py"})
    assert "logic.py" in res_dispatch
    assert "calculate_discount" in res_dispatch


