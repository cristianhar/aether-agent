import pytest
from pathlib import Path
from tools.file_tools import read_file, write_file, edit_file, delete_file, move_file


def test_write_and_read_file(tmp_path):
    test_file = tmp_path / "hello.py"
    content = "def greet():\n    return 'Hello World'\n"

    # Test escribir archivo
    res_write = write_file(str(test_file), content)
    assert "Éxito" in res_write
    assert test_file.exists()

    # Test leer archivo con rangos
    res_read = read_file(str(test_file), start_line=1, end_line=2)
    assert "greet" in res_read
    assert "1 | def greet():" in res_read


def test_edit_file_exact_match(tmp_path):
    test_file = tmp_path / "calc.py"
    content = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
    write_file(str(test_file), content)

    # Reemplazo atómico
    target = "def add(a, b):\n    return a + b"
    replacement = "def add(a, b):\n    # Suma optimizada\n    return a + b"

    res_edit = edit_file(str(test_file), target, replacement)
    assert "Éxito" in res_edit

    updated = read_file(str(test_file))
    assert "# Suma optimizada" in updated


def test_edit_file_ambiguous_fails(tmp_path):
    test_file = tmp_path / "duplicate.py"
    content = "x = 10\nx = 10\n"
    write_file(str(test_file), content)

    # Intento de editar sin contexto suficiente
    res_edit = edit_file(str(test_file), "x = 10", "x = 20")
    assert "Error: El texto 'target' aparece 2 veces" in res_edit


def test_delete_and_move_file(tmp_path):
    f1 = tmp_path / "orig.txt"
    f2 = tmp_path / "moved.txt"
    f1.write_text("sample content", encoding="utf-8")

    res_move = move_file(str(f1), str(f2))
    assert "Éxito" in res_move
    assert not f1.exists()
    assert f2.exists()

    res_del = delete_file(str(f2))
    assert "Éxito" in res_del
    assert not f2.exists()


