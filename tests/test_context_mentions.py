import pytest
from pathlib import Path
from agent.context import find_matching_file, resolve_at_file_mentions, get_workspace_file_mentions


def test_find_matching_file_exact(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    f = sub / "app.py"
    f.write_text("print('hello')", encoding="utf-8")

    res = find_matching_file("src/app.py", tmp_path)
    assert res == f


def test_find_matching_file_name_match(tmp_path):
    sub = tmp_path / "tools"
    sub.mkdir()
    f = sub / "worker.py"
    f.write_text("def work(): pass", encoding="utf-8")

    res = find_matching_file("worker.py", tmp_path)
    assert res == f


def test_find_matching_file_fuzzy_typo(tmp_path):
    sub = tmp_path / "tools"
    sub.mkdir()
    f = sub / "file_tools.py"
    f.write_text("def read(): pass", encoding="utf-8")

    # Typo: 'file_tool.py' sin la 's'
    res = find_matching_file("file_tool.py", tmp_path)
    assert res == f


def test_resolve_at_file_mentions_inlines_content(tmp_path):
    f = tmp_path / "calc.py"
    f.write_text("def add(a, b): return a + b\n", encoding="utf-8")

    prompt = "que hace el archivo @calc.py"
    expanded, attached = resolve_at_file_mentions(prompt, tmp_path)

    assert len(attached) == 1
    assert attached[0] == f
    assert "[CONTEXTO ADJUNTO VÍA @calc.py" in expanded
    assert "def add(a, b): return a + b" in expanded
    assert "que hace el archivo calc.py" in expanded


def test_resolve_at_file_mentions_bare_at_query(tmp_path):
    f = tmp_path / "models.py"
    f.write_text("class User: pass\n", encoding="utf-8")

    # Usuario escribe solo '@models.py'
    prompt = "@models.py"
    expanded, attached = resolve_at_file_mentions(prompt, tmp_path)

    assert len(attached) == 1
    assert "class User: pass" in expanded
    assert "Analiza detalladamente el archivo adjunto 'models.py'" in expanded


def test_get_workspace_file_mentions():
    mentions = get_workspace_file_mentions(Path.cwd())
    assert len(mentions) > 0
    assert any("main.py" in m for m in mentions)
