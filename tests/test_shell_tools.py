import pytest
from tools.shell_tools import run_command
from agent.safety import check_command_safety


def test_run_command_stdout():
    res = run_command("echo HelloAether")
    assert "Código de salida: 0" in res
    assert "HelloAether" in res


def test_run_command_nonexistent():
    res = run_command("comando_inexistente_12345")
    assert "Código de salida:" in res
    assert "0" not in res or "Error" in res or "STDERR" in res


def test_command_safety_filtering():
    # Comandos peligrosos deben ser bloqueados
    safe, msg = check_command_safety("rm -rf /")
    assert not safe
    assert "peligroso" in msg

    safe2, msg2 = check_command_safety("git reset --hard")
    assert not safe2

    safe3, msg3 = check_command_safety("format c:")
    assert not safe3

    # Comandos comunes seguros
    safe_ok, _ = check_command_safety("pytest tests/")
    assert safe_ok

    safe_ok2, _ = check_command_safety("git status")
    assert safe_ok2

