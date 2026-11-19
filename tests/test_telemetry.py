"""
Tests unitarios para el módulo de telemetría (TelemetryLogger).
Verifica:
- Resumen en ausencia de archivo de log (valores por defecto e integridad de claves).
- Registro y agregación correcta de turnos y ejecuciones de herramientas.
- Manejo de fallos y cálculo de tasa porcentual de error.
"""

from agent.telemetry import TelemetryLogger


def test_telemetry_summary_empty(tmp_path):
    """Verifica que el resumen devuelva todas las claves esperadas cuando no hay archivo de log."""
    tlog = TelemetryLogger(workspace_root=tmp_path)
    summary = tlog.get_summary()

    required_keys = [
        "total_turns",
        "total_tool_calls",
        "tool_failures",
        "tool_failure_rate",
        "tool_failure_rate_percent",
        "average_turn_duration_seconds",
    ]
    for key in required_keys:
        assert key in summary, f"Clave faltante en summary vacío: {key}"

    assert summary["total_turns"] == 0
    assert summary["total_tool_calls"] == 0
    assert summary["tool_failures"] == 0
    assert summary["tool_failure_rate"] == 0.0
    assert summary["tool_failure_rate_percent"] == 0.0
    assert summary["average_turn_duration_seconds"] == 0.0


def test_telemetry_record_and_summary_aggregation(tmp_path):
    """Verifica el cálculo de estadísticas con registros reales de turnos y herramientas."""
    tlog = TelemetryLogger(workspace_root=tmp_path)

    # 1. Registrar dos turnos
    tlog.record_turn(
        session_id="s1",
        turn_index=1,
        model="qwen2.5-coder:7b",
        duration_seconds=2.0,
        tool_calls_count=2,
        tool_failures_count=0,
        user_prompt_length=20,
        agent_response_length=50,
    )
    tlog.record_turn(
        session_id="s1",
        turn_index=2,
        model="qwen2.5-coder:7b",
        duration_seconds=4.0,
        tool_calls_count=3,
        tool_failures_count=1,
        user_prompt_length=30,
        agent_response_length=80,
    )

    # 2. Registrar ejecuciones de herramientas: 3 éxitos, 1 fallo
    tlog.record_tool_execution(
        session_id="s1",
        tool_name="read_file",
        category="filesystem",
        duration_ms=15.0,
        success=True,
    )
    tlog.record_tool_execution(
        session_id="s1",
        tool_name="write_file",
        category="filesystem",
        duration_ms=25.0,
        success=True,
    )
    tlog.record_tool_execution(
        session_id="s1",
        tool_name="run_command",
        category="terminal",
        duration_ms=120.0,
        success=True,
    )
    tlog.record_tool_execution(
        session_id="s1",
        tool_name="run_tests",
        category="terminal",
        duration_ms=450.0,
        success=False,
        error="Tests failed with exit code 1",
    )

    summary = tlog.get_summary()

    assert summary["total_turns"] == 2
    assert summary["average_turn_duration_seconds"] == 3.0  # (2.0 + 4.0) / 2
    assert summary["total_tool_calls"] == 4
    assert summary["tool_failures"] == 1
    assert summary["tool_failure_rate_percent"] == 25.0  # 1 / 4 * 100
    assert summary["tool_failure_rate"] == 25.0
