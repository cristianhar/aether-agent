import tempfile
from pathlib import Path
from tools.patch_engine import PatchEngine, PatchOperation, compute_sha256


def test_patch_engine_single_atomic_edit():
    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = Path(tmp_dir) / "service.py"
        filepath.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

        res = PatchEngine.apply_single_patch(
            filepath=filepath,
            old_text="return 'world'",
            new_text="return 'AETHER'",
        )

        assert res.success is True
        assert "def hello():\n    return 'AETHER'\n" == filepath.read_text(encoding="utf-8")
        assert "return 'AETHER'" in res.diff
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            exact_content = f.read()
        assert res.new_sha256 == compute_sha256(exact_content)


def test_patch_engine_concurrency_sha_check():
    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = Path(tmp_dir) / "config.py"
        filepath.write_text("DEBUG = True\n", encoding="utf-8")

        # Proveer un SHA incorrecto para simular edición externa concurrente
        res = PatchEngine.apply_single_patch(
            filepath=filepath,
            old_text="DEBUG = True",
            new_text="DEBUG = False",
            expected_sha256="deadbeef12345678",
        )

        assert res.success is False
        assert "Conflicto de concurrencia" in res.error
        # El archivo debe permanecer intacto
        assert filepath.read_text(encoding="utf-8") == "DEBUG = True\n"


def test_patch_engine_ambiguous_matches():
    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = Path(tmp_dir) / "loop.py"
        filepath.write_text("value = 1\nvalue = 1\n", encoding="utf-8")

        res = PatchEngine.apply_single_patch(
            filepath=filepath,
            old_text="value = 1",
            new_text="value = 2",
        )

        assert res.success is False
        assert "Ambigüedad" in res.error


def test_patch_engine_transaction_rollback():
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_a = Path(tmp_dir) / "a.py"
        file_b = Path(tmp_dir) / "b.py"

        file_a.write_text("def a(): return 1\n", encoding="utf-8")
        file_b.write_text("def b(): return 2\n", encoding="utf-8")

        # Operación donde el segundo parche fallará (texto no existente)
        ops = [
            PatchOperation(filepath=file_a, old_text="return 1", new_text="return 100"),
            PatchOperation(filepath=file_b, old_text="return NON_EXISTENT", new_text="return 200"),
        ]

        success, results, error_msg = PatchEngine.apply_transaction(ops)

        assert success is False
        assert "Transacción abortada" in error_msg
        # file_a debió ser revertido a su contenido original a pesar de que su parche individual fue exitoso
        assert file_a.read_text(encoding="utf-8") == "def a(): return 1\n"
        assert file_b.read_text(encoding="utf-8") == "def b(): return 2\n"
