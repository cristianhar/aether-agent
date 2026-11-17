from tools.vram_monitor import get_hardware_vram_status


def test_get_hardware_vram_status():
    status = get_hardware_vram_status()
    assert isinstance(status, str)
    # Debe retornar información útil de VRAM o indicar estado de reposo
    assert any(term in status for term in ["Estado de VRAM", "reposo", "Ollama", "Hardware"])
