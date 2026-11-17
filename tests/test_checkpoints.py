import tempfile
from pathlib import Path
from agent.checkpoints import SafeCheckpointManager


def test_safe_checkpoint_create_and_restore():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir).resolve()
        mgr = SafeCheckpointManager(workspace_root=ws)

        # Crear archivo inicial
        main_py = ws / "main.py"
        main_py.write_text("print('version 1')\n", encoding="utf-8")

        # Tomar checkpoint
        snap_id = mgr.create_checkpoint("Estado inicial v1", files_to_track=[main_py])
        assert snap_id.startswith("chk_")

        # Modificar archivo existente y crear uno nuevo
        main_py.write_text("print('version 2 con bug')", encoding="utf-8")
        unwanted_file = ws / "generated_bug.py"
        unwanted_file.write_text("# archivo nuevo temporal\n", encoding="utf-8")

        # Restaurar checkpoint
        success, msg = mgr.restore_checkpoint(snap_id)
        assert success is True
        assert "restaurado exitosamente" in msg.lower()

        # Verificar que main.py volvió a versión 1
        assert main_py.read_text(encoding="utf-8") == "print('version 1')\n"


def test_safe_checkpoint_list():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir).resolve()
        mgr = SafeCheckpointManager(workspace_root=ws)

        file_x = ws / "test.txt"
        file_x.write_text("hello", encoding="utf-8")

        mgr.create_checkpoint("Primer punto", files_to_track=[file_x])
        mgr.create_checkpoint("Segundo punto", files_to_track=[file_x])

        checkpoints = mgr.list_checkpoints()
        assert len(checkpoints) == 2
        descriptions = [c["description"] for c in checkpoints]
        assert "Primer punto" in descriptions
        assert "Segundo punto" in descriptions
