from unittest.mock import patch, MagicMock
from tools.vram_monitor import get_hardware_vram_status


def test_get_hardware_vram_status():
    status = get_hardware_vram_status()
    assert isinstance(status, str)
    status_lower = status.lower()
    # Debe retornar información útil de VRAM, reposo u Ollama
    assert any(term in status_lower for term in ["vram", "reposo", "ollama", "hardware"])


def test_get_hardware_vram_status_mocked_gpu():
    mock_res = MagicMock()
    mock_res.stdout = "NAME                   ID              SIZE     PROCESSOR    UNTIL\nqwen2.5-coder:7b       2b9044e532b4    4.7 GB   100% GPU     4 minutes from now"
    with patch("subprocess.run", return_value=mock_res):
        status = get_hardware_vram_status()
        assert "4.7 GB" in status
        assert "RENDIMIENTO ÓPTIMO" in status


def test_get_hardware_vram_status_mocked_cpu_offload():
    mock_res = MagicMock()
    mock_res.stdout = "NAME                   ID              SIZE     PROCESSOR    UNTIL\nqwen2.5-coder:14b      abcd1234ef01    9.0 GB   100% CPU     4 minutes from now"
    with patch("subprocess.run", return_value=mock_res):
        status = get_hardware_vram_status()
        assert "ADVERTENCIA CRÍTICA" in status
