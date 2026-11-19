import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from agent.skills import (
    SkillRegistry,
    execute_skill,
    get_global_skill_registry,
    parse_frontmatter_markdown,
)
from cli.commands import handle_slash_command


def test_parse_frontmatter_markdown():
    sample = """---
name: fastapi-deploy
description: "Deploy FastAPI apps to production"
triggers: [deploy, fastapi, uvicorn]
enabled: true
max_workers: 4
---
# Instructions
Step 1: Check requirements.
Step 2: Run uvicorn.
"""
    meta, body = parse_frontmatter_markdown(sample)
    assert meta["name"] == "fastapi-deploy"
    assert meta["description"] == "Deploy FastAPI apps to production"
    assert meta["triggers"] == ["deploy", "fastapi", "uvicorn"]
    assert meta["enabled"] is True
    assert meta["max_workers"] == 4
    assert "# Instructions" in body
    assert "Step 2: Run uvicorn." in body


def test_parse_frontmatter_no_header():
    plain = "# Plain Markdown without frontmatter\nJust content."
    meta, body = parse_frontmatter_markdown(plain)
    assert meta == {}
    assert "Plain Markdown" in body


def test_skill_registry_discovery():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        skills_dir = ws / ".aether" / "skills" / "docker-builder"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text(
            """---
name: docker-builder
description: Builds optimized Docker containers
triggers: [docker, container, dockerfile]
---
# Docker Instructions
Use multi-stage builds.
""",
            encoding="utf-8",
        )

        registry = SkillRegistry(workspace_root=ws)
        assert "docker-builder" in registry.skills
        sk = registry.get_skill("docker-builder")
        assert sk is not None
        assert sk.name == "docker-builder"
        assert "docker" in sk.triggers

        # Match by trigger
        matched = registry.match_skill("Please run container optimization")
        assert matched is not None
        assert matched.name == "docker-builder"

        # Catalog prompt
        catalog = registry.get_skills_catalog_prompt()
        assert "docker-builder" in catalog
        assert "Builds optimized Docker containers" in catalog


def test_execute_skill_dynamic_and_fallback():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        skills_dir = ws / ".agent" / "skills" / "security-scan"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            """---
name: security-scan
description: Inspects credentials and CVE vulnerabilities
triggers: [security, cve, bandit]
---
Execute bandit on codebase.
""",
            encoding="utf-8",
        )

        reg = get_global_skill_registry(workspace_root=ws, force_reload=True)
        assert "security-scan" in reg.skills

        # Dynamic execution
        output = execute_skill("security-scan")
        assert "Habilidad Activa: [SECURITY-SCAN]" in output
        assert "Execute bandit on codebase." in output

        # Unrecognized skill
        missing = execute_skill("non_existent_skill")
        assert "❌ Habilidad 'non_existent_skill' no reconocida" in missing


def test_execute_skill_aliases_native():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        code_file = ws / "sample.py"
        code_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        res_review = execute_skill("code-review", target=str(code_file))
        assert "Reporte de Code Review" in res_review

        res_scaffold = execute_skill("test-scaffold", target=str(code_file))
        assert "test_add_basic" in res_scaffold

        res_deps = execute_skill("dependency-audit", target=str(code_file))
        assert "Gráfico de Dependencias" in res_deps


def test_cli_slash_command_skills():
    mock_orch = MagicMock()
    mock_console = MagicMock()

    # /skills
    assert handle_slash_command("/skills", mock_orch, console=mock_console) is True

    # /skills reload
    assert handle_slash_command("/skills reload", mock_orch, console=mock_console) is True

    # /skills info
    assert handle_slash_command("/skills info code-review", mock_orch, console=mock_console) is True
