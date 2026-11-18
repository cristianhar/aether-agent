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


def test_edit_file_empty_target_rejected(tmp_path):
    f = tmp_path / "module.py"
    f.write_text("import os\n", encoding="utf-8")

    res = edit_file(str(f), target="", replacement="import time\n")
    assert "Error de parámetro 'target'" in res
    assert "no puede ser una cadena vacía" in res
    assert "write_file" in res


def test_edit_file_noop_rejected(tmp_path):
    f = tmp_path / "module2.py"
    f.write_text("x = 10\n", encoding="utf-8")

    res = edit_file(str(f), target="x = 10", replacement="x = 10")
    assert "Error / Sin cambios" in res
    assert "IDÉNTICO" in res


def test_calculate_file_hash_and_sha_noop(tmp_path):
    from tools.file_tools import calculate_file_hash
    f = tmp_path / "data.txt"
    f.write_text("hello world", encoding="utf-8")

    h1 = calculate_file_hash(f)
    assert h1 is not None
    assert len(h1) == 64


def test_edit_file_fuzzy_similarity_match(tmp_path):
    f = tmp_path / "async_mod.py"
    original = """@pytest.mark.asyncio
async def test_something():
    res = await run_task()
    assert res is True
"""
    f.write_text(original, encoding="utf-8")

    # Target con typo leve (falta 'async' en def)
    target = """@pytest.mark.asyncio
def test_something():
    res = await run_task()
    assert res is True
"""
    replacement = """def test_something():
    res = run_sync_task()
    assert res is True
"""
    res = edit_file(str(f), target=target, replacement=replacement)
    assert "Éxito" in res
    assert "coincidencia difusa" in res

    content = f.read_text(encoding="utf-8")
    assert "run_sync_task" in content


def test_edit_file_preserves_indentation_on_unindented_target(tmp_path):
    """Verifica que si el target y replacement vienen sin indentación, se conserve la sangría del bloque original en disco."""
    f = tmp_path / "calc.py"
    original = "class Calculator:\n    def get_result(self):\n        return 42\n"
    f.write_text(original, encoding="utf-8")

    # Target y replacement sin los 8 espacios de sangría
    res = edit_file(str(f), target="return 42", replacement="return 100")
    assert "Éxito" in res

    new_content = f.read_text(encoding="utf-8")
    # Debe preservar los 8 espacios de indentación para no romper la sintaxis de Python
    assert "        return 100\n" in new_content


def test_edit_file_noop_guidance(tmp_path):
    """Verifica que un intento de edición idéntica (no-op) incluya directivas accionables."""
    f = tmp_path / "calc.py"
    f.write_text("def calc(): return 42\n", encoding="utf-8")

    res = edit_file(str(f), target="return 42", replacement="return 42")
    assert "Sin cambios (Idéntico)" in res
    assert "INSTRUCCIÓN DE AUTO-CORRECCIÓN" in res
    assert "AssertionError" in res


def test_edit_file_on_nonexistent_file_guides_write_file(tmp_path):
    """Verifica que intentar editar un archivo inexistente guíe al modelo a crearlo con write_file."""
    res = edit_file(str(tmp_path / "nonexistent.py"), target="foo", replacement="bar")
    assert "no existe" in res
    assert "write_file" in res


