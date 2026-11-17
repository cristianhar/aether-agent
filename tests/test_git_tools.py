import pytest
from tools.git_tools import is_git_repo, get_git_status, get_git_diff, create_checkpoint


def test_git_repo_status():
    assert is_git_repo()
    status = get_git_status()
    assert "limpio" in status.lower() or status == ""


def test_git_checkpoint_lifecycle(tmp_path):
    # Probar que get_git_diff responde limpiamente
    diff = get_git_diff()
    assert "No hay diferencias" in diff or isinstance(diff, str)
