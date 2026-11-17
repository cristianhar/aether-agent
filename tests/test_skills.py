import tempfile
from pathlib import Path
from agent.skills import execute_skill


def test_skill_review():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        code_file = ws / "long_module.py"
        # Crear función larga sin docstrings
        body = "\n".join([f"    x_{i} = {i}" for i in range(70)])
        code_file.write_text(f"def huge_processing_job():\n{body}\n    return True\n", encoding="utf-8")

        report = execute_skill("review", target=str(code_file))
        assert "Reporte de Code Review" in report
        assert "es muy extensa" in report


def test_skill_test_scaffold():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        auth_file = ws / "auth.py"
        auth_file.write_text("def authenticate(token):\n    return True\n", encoding="utf-8")

        scaffold = execute_skill("test_gen", target=str(auth_file))
        assert "def test_authenticate_basic():" in scaffold
        assert "test_auth.py" in scaffold


def test_skill_dependencies():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        svc = ws / "service.py"
        svc.write_text("import json\nimport requests\n", encoding="utf-8")

        res = execute_skill("dependencies", target=str(svc))
        assert "Gráfico de Dependencias" in res
        assert "json" in res
