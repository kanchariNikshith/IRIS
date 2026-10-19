from unittest.mock import Mock

from iris.logs.action_log import ActionLog
from iris.security.permissions import PermissionGate, Permission
from iris.tools.registry import Tool, ToolRegistry, ToolResult


def registry(tmp_path):
    value = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    handler = Mock(return_value=ToolResult("verified", "A mock action completed."))
    value.register(Tool("test_action", {"type": "object", "properties": {}}, Permission.AUTO, handler))
    return value, handler


def test_result_observer_runs_after_log_and_cannot_change_execution(tmp_path):
    value, handler = registry(tmp_path)
    def observer(name, result):
        assert value.action_log.path.exists()
        assert name == "test_action" and result.status == "verified"
        raise RuntimeError("UI failure")
    value.on_result = observer
    assert value.execute("test_action", {}).status == "verified"
    handler.assert_called_once()


def test_result_observer_sees_log_storage_failure_honestly(tmp_path):
    value, handler = registry(tmp_path)
    value.action_log.write = Mock(side_effect=OSError("fixture-secret"))
    value.on_result = Mock()
    assert value.execute("test_action", {}).status == "failed"
    assert value.on_result.call_args.args[1].status == "failed"
    handler.assert_called_once()


def test_gui_default_confirmation_callback_uses_existing_gate(tmp_path):
    value, _ = registry(tmp_path)
    handler = Mock(return_value=ToolResult("verified", "Confirmed mock action."))
    value.register(Tool("confirmed_action", {"type": "object", "properties": {}}, Permission.CONFIRM, handler))
    def default(request):
        value.gate.resolve(request.id, turn_id=request.turn_id, approved=True)
    value.on_confirmation = default
    assert value.execute("confirmed_action", {}, turn_id="turn-1").status == "verified"
    handler.assert_called_once()
