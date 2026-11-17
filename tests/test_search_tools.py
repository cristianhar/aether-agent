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
