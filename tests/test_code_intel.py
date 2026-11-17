import tempfile
from pathlib import Path
from tools.code_intel import find_definition, find_references, get_dependencies


def test_find_definition_function_and_class():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        models_file = ws / "models.py"
        models_file.write_text(
            "class UserAccount:\n    def __init__(self, username):\n        self.username = username\n\n"
            "def build_user(name):\n    return UserAccount(name)\n",
            encoding="utf-8"
        )

        # 1. Buscar clase
        class_res = find_definition("UserAccount", root_dir=str(ws))
        assert "Clase" in class_res
        assert "models.py:1" in class_res
        assert "class UserAccount" in class_res

        # 2. Buscar función
        func_res = find_definition("build_user", root_dir=str(ws))
        assert "Función" in func_res
        assert "models.py:5" in func_res
        assert "def build_user(name)" in func_res


def test_find_references():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        math_file = ws / "math_utils.py"
        math_file.write_text(
            "def multiply(x, y):\n    return x * y\n\ndef square(x):\n    return multiply(x, x)\n",
            encoding="utf-8"
        )

        main_file = ws / "main.py"
        main_file.write_text("from math_utils import multiply\nres = multiply(4, 5)\n", encoding="utf-8")

        refs = find_references("multiply", root_dir=str(ws))
        assert "main.py" in refs
        assert "math_utils.py" in refs
        assert "multiply(x, x)" in refs


def test_get_dependencies():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        app_file = ws / "app.py"
        app_file.write_text(
            "import os\nimport sys\nimport httpx\nfrom pathlib import Path\n",
            encoding="utf-8"
        )

        deps = get_dependencies(str(app_file))
        assert "Gráfico de Dependencias" in deps
        assert "os" in deps or "sys" in deps
        assert "httpx" in deps
