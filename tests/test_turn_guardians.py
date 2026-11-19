from unittest.mock import MagicMock, patch

from agent.turn_guardians import evaluate_no_tool_call_guardians


def test_turn_guardian_malformed_json_call():
    decision = evaluate_no_tool_call_guardians(
        content='{"name": "write_file", "arguments": {"path": "test.py"}}',
        user_prompt="crea el archivo",
        iteration=1,
        max_iterations=10,
        mode="agent",
        plan_active_in_turn=False,
        plan_completed_in_turn=False,
        last_test_exit_code=None,
        last_test_failure_summary=None,
        files_modified_in_turn=False,
        tests_executed_in_turn=False,
        action_history=[],
        proactive_prompts_sent=0,
    )
    assert decision.should_continue is True
    assert "formato JSON" in decision.user_hint


def test_turn_guardian_failed_tests_blocks_completion():
    decision = evaluate_no_tool_call_guardians(
        content="He terminado el trabajo con éxito.",
        user_prompt="implementa la función",
        iteration=1,
        max_iterations=10,
        mode="agent",
        plan_active_in_turn=False,
        plan_completed_in_turn=False,
        last_test_exit_code=1,
        last_test_failure_summary="AssertionError: 1 != 2",
        files_modified_in_turn=True,
        tests_executed_in_turn=True,
        action_history=["run_tests"],
        proactive_prompts_sent=0,
    )
    assert decision.should_continue is True
    assert "CORRECCIÓN DE PRUEBAS OBLIGATORIA" in decision.user_hint


def test_turn_guardian_auto_completes_plan_when_tests_passed():
    with patch("tools.agent_tools.update_plan") as mock_update_plan:
        decision = evaluate_no_tool_call_guardians(
            content="Todo verificado y listo.",
            user_prompt="haz el módulo",
            iteration=2,
            max_iterations=10,
            mode="agent",
            plan_active_in_turn=True,
            plan_completed_in_turn=False,
            last_test_exit_code=0,
            last_test_failure_summary=None,
            files_modified_in_turn=True,
            tests_executed_in_turn=True,
            action_history=["write_file", "run_tests"],
            proactive_prompts_sent=0,
        )
        assert decision.should_continue is False
        assert decision.plan_completed is True
        mock_update_plan.assert_called_once_with(is_completed=True)


def test_turn_guardian_passive_file_begging_intercepted():
    decision = evaluate_no_tool_call_guardians(
        content="¿Podrías compartir el código del archivo?",
        user_prompt="Revisa el archivo core.py",
        iteration=1,
        max_iterations=10,
        mode="agent",
        plan_active_in_turn=False,
        plan_completed_in_turn=False,
        last_test_exit_code=None,
        last_test_failure_summary=None,
        files_modified_in_turn=False,
        tests_executed_in_turn=False,
        action_history=[],
        proactive_prompts_sent=0,
    )
    assert decision.should_continue is True
    assert "AUTO-INSPECCIÓN OBLIGATORIA" in decision.user_hint
