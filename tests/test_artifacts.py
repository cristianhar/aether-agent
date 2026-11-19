"""
Tests unitarios para el motor de artefactos estructurados (ArtifactManager):
- Creación, actualización y versionado de documentos en .aether/artifacts/.
- Metadatos JSON (user_facing, request_feedback, version, timestamp).
- Herramientas create_artifact, update_artifact, read_artifact, list_artifacts.
- Comando slash /artifacts.
"""

from rich.console import Console
from agent.artifacts import ArtifactManager
from tools.registry import execute_tool
from cli.commands import handle_slash_command


def test_artifact_lifecycle(tmp_path):
    """Verifica el ciclo de vida completo de un artefacto: create, update, read, list."""
    mgr = ArtifactManager(workspace_root=tmp_path, session_id="test_sess")

    # 1. Crear artefacto
    res_create = mgr.create_artifact(
        title="Arquitectura de Citas",
        content="# Plan de Backend\nArquitectura de microservicios con PostgreSQL.",
        summary="Especificación técnica de microservicios",
        user_facing=True,
        request_feedback=True,
        tags=["architecture", "backend"],
    )
    art_id = res_create["artifact_id"]
    assert "arquitectura_de_citas" in art_id
    assert res_create["version"] == 1
    assert res_create["user_facing"] is True
    assert res_create["request_feedback"] is True

    # 2. Leer artefacto
    res_read = mgr.read_artifact(art_id)
    assert res_read["artifact_id"] == art_id
    assert "PostgreSQL" in res_read["content"]
    assert res_read["metadata"]["version"] == 1
    assert res_read["metadata"]["title"] == "Arquitectura de Citas"

    # 3. Actualizar artefacto
    res_update = mgr.update_artifact(
        artifact_id=art_id,
        content="# Plan de Backend v2\nAgregando soporte para WebSockets.",
        summary="Versión 2 con WebSockets en tiempo real",
    )
    assert res_update["version"] == 2
    assert res_update["summary"] == "Versión 2 con WebSockets en tiempo real"

    # Verificar que el contenido fue actualizado en disco
    updated_read = mgr.read_artifact(art_id)
    assert updated_read["metadata"]["version"] == 2
    assert "WebSockets" in updated_read["content"]

    # 4. Listar artefactos
    items = mgr.list_artifacts()
    assert len(items) >= 1
    assert any(it["artifact_id"] == art_id for it in items)


def test_artifact_tools_via_registry(tmp_path, monkeypatch):
    """Verifica la ejecución de herramientas de artefactos a través del despachador central."""
    monkeypatch.chdir(tmp_path)

    # 1. create_artifact tool
    create_args = {
        "title": "Reporte de Calidad",
        "content": "## Métricas\nCobertura de código: 95%",
        "summary": "Resumen de cobertura de pruebas",
        "user_facing": True,
        "request_feedback": False,
    }
    out_create = execute_tool("create_artifact", create_args)
    assert "✅ Artefacto creado con éxito" in out_create

    # 2. list_artifacts tool
    out_list = execute_tool("list_artifacts", {})
    assert "Reporte de Calidad" in out_list

    # Extraer ID creado
    mgr = ArtifactManager(workspace_root=tmp_path)
    all_art = mgr.list_artifacts()
    assert len(all_art) == 1
    art_id = all_art[0]["artifact_id"]

    # 3. read_artifact tool
    out_read = execute_tool("read_artifact", {"artifact_id": art_id})
    assert "Cobertura de código: 95%" in out_read

    # 4. update_artifact tool
    out_up = execute_tool("update_artifact", {
        "artifact_id": art_id,
        "content": "## Métricas v2\nCobertura de código: 98%",
        "summary": "Actualización a 98% de cobertura"
    })
    assert "actualizado a versión 2" in out_up


def test_slash_artifacts_command():
    """Verifica el comando slash /artifacts y /artifacts read."""
    mock_orch = type("MockOrchestrator", (), {"session_id": "test_slash"})()
    mock_console = Console(record=True)

    # Listar sin artefactos
    assert handle_slash_command("/artifacts", mock_orch, mock_console) is True

    # Crear uno y volver a listar
    mgr = ArtifactManager(session_id="test_slash")
    mgr.create_artifact(
        title="Slash Test Doc",
        content="Contenido de prueba",
        summary="Resumen de prueba",
    )
    assert handle_slash_command("/artifacts", mock_orch, mock_console) is True
    assert handle_slash_command("/artifacts read inexistente", mock_orch, mock_console) is True
