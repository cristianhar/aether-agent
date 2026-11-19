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


def test_aether_cli_completer_slash_and_at_and_normal_text(tmp_path):
    from agent.context import AetherCLICompleter
    from prompt_toolkit.document import Document

    # Crear archivos de prueba
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "server.py").write_text("y = 2\n", encoding="utf-8")

    completer = AetherCLICompleter(tmp_path)

    # 1. Al presionar '/' debe autocompletar comandos slash
    doc_slash = Document("/", cursor_position=1)
    slash_comps = [c.text for c in completer.get_completions(doc_slash, None)]
    assert "/help" in slash_comps
    assert "/mode" in slash_comps
    assert "/plan" in slash_comps

    # 2. Subcomandos de /mode
    doc_mode = Document("/mode ", cursor_position=6)
    mode_comps = [c.text for c in completer.get_completions(doc_mode, None)]
    assert "agent" in mode_comps
    assert "ask" in mode_comps
    assert "plan" in mode_comps
    assert "review" in mode_comps

    # 3. Al presionar '@' debe mostrar archivos del proyecto
    doc_at = Document("@", cursor_position=1)
    at_comps = [c.text for c in completer.get_completions(doc_at, None)]
    assert "@app.py" in at_comps
    assert "@server.py" in at_comps

    # 4. Al presionar '@' en medio del texto con filtro
    doc_text_at = Document("inspecciona el archivo @app", cursor_position=len("inspecciona el archivo @app"))
    text_at_comps = [c.text for c in completer.get_completions(doc_text_at, None)]
    assert "@app.py" in text_at_comps
    assert "@server.py" not in text_at_comps

    # 5. Texto normal sin '/' y sin '@': NO debe mostrar ningún menú emergente
    doc_normal = Document("hola agente como estas", cursor_position=len("hola agente como estas"))
    normal_comps = [c.text for c in completer.get_completions(doc_normal, None)]
    assert len(normal_comps) == 0

