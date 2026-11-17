import tempfile
from pathlib import Path
from tools.diagnostics import check_python_syntax, check_json_syntax, get_diagnostics


def test_python_syntax_diagnostics():
    valid_code = "def add(a, b):\n    return a + b\n"
    res = check_python_syntax(valid_code)
    assert res["valid"] is True
    assert len(res["errors"]) == 0

    invalid_code = "def broken(:\n    pass"
    res_inv = check_python_syntax(invalid_code)
    assert res_inv["valid"] is False
    assert len(res_inv["errors"]) > 0


def test_json_syntax_diagnostics():
    valid_json = '{"model": "qwen2.5", "tokens": 100}'
    assert check_json_syntax(valid_json)["valid"] is True

    invalid_json = '{"model": "qwen2.5", tokens: 100'
    res = check_json_syntax(invalid_json)
    assert res["valid"] is False
    assert len(res["errors"]) > 0


def test_get_diagnostics_file_inspection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "app.py"
        p.write_text("print('All good')\n", encoding="utf-8")

        report = get_diagnostics(str(p))
        assert "Diagnóstico limpio" in report

        p.write_text("print('Unclosed string\n", encoding="utf-8")
        report_bad = get_diagnostics(str(p))
        assert "Errores sintácticos detectados" in report_bad
