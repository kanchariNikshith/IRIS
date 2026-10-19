import json
from unittest.mock import Mock

import pytest

from iris.logs.action_log import ActionLog
from iris.security.permissions import Permission, PermissionGate
from iris.tools.registry import Tool, ToolRegistry, ToolResult

SCHEMA = {"type": "object", "properties": {"amount": {"type": "integer", "minimum": 1}},
          "required": ["amount"]}


@pytest.fixture
def setup_registry(tmp_path):
    handler = Mock(return_value=ToolResult("verified", "Checked."))
    gate = PermissionGate()
    registry = ToolRegistry(gate, ActionLog(tmp_path / "actions.log", ("fixture-secret",)))
    registry.register(Tool("scroll", SCHEMA, Permission.AUTO, handler))
    return registry, gate, handler


def test_valid_arguments_run_and_log(setup_registry):
    registry, _, handler = setup_registry
    assert registry.execute("scroll", '{"amount":2}').status == "verified"
    handler.assert_called_once_with(amount=2)
    record = json.loads(registry.action_log.path.read_text())
    assert record["result"]["status"] == "verified"


@pytest.mark.parametrize("arguments", ["bad json", "[]", {}, {"amount": 0},
                                     {"amount": True}, {"amount": "2"},
                                     {"amount": 2, "script": "unsafe"}])
def test_invalid_arguments_never_run(setup_registry, arguments):
    registry, _, handler = setup_registry
    assert registry.execute("scroll", arguments).status == "failed"
    handler.assert_not_called()


def test_unknown_and_killed_actions_do_not_run(setup_registry):
    registry, gate, handler = setup_registry
    assert registry.execute("unknown", {}).status == "failed"
    gate.stop()
    assert registry.execute("scroll", {"amount": 1}).status == "failed"
    handler.assert_not_called()
    assert len(registry.action_log.path.read_text().splitlines()) == 2


def test_registration_and_metadata_are_protected(setup_registry):
    registry, _, handler = setup_registry
    with pytest.raises(ValueError):
        registry.register(Tool("scroll", SCHEMA, Permission.AUTO, handler))
    with pytest.raises(ValueError):
        registry.register(Tool("send_email", SCHEMA, Permission.AUTO, handler))
    with pytest.raises(ValueError):
        registry.register(Tool("shell", {"type": "object", "$ref": "https://example.org/schema"},
                               Permission.AUTO, handler))
    definitions = registry.definitions()
    definitions[0]["function"]["parameters"]["required"].clear()
    assert registry.execute("scroll", {}).status == "failed"


def test_confirmation_before_dispatch(setup_registry):
    registry, gate, handler = setup_registry
    registry.register(Tool("send_email", SCHEMA, Permission.CONFIRM, handler))
    assert registry.execute("send_email", {"amount": 1}).status == "failed"
    handler.assert_not_called()
    def confirm(request):
        gate.resolve(request.id, turn_id="turn", approved=True)
    assert registry.execute("send_email", {"amount": 1}, turn_id="turn",
                            on_confirmation=confirm).status == "verified"
    handler.assert_called_once()


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_runtime_error_has_safe_traceback(setup_registry, error_type):
    registry, _, handler = setup_registry
    handler.side_effect = error_type("fixture-secret private email")
    assert registry.execute("scroll", {"amount": 1}).status == "failed"
    log = registry.action_log.path.read_text()
    assert "fixture-secret" not in log
    assert "private email" not in log
    assert "traceback" in json.loads(log)


def test_bad_tool_result_is_failure(setup_registry):
    registry, _, handler = setup_registry
    handler.return_value = "done"
    assert registry.execute("scroll", {"amount": 1}).status == "failed"


def test_log_failure_is_reported(setup_registry, monkeypatch):
    registry, _, _ = setup_registry
    def fail(*args, **kwargs):
        raise OSError("fixture-secret")
    monkeypatch.setattr(registry.action_log, "write", fail)
    result = registry.execute("scroll", {"amount": 1})
    assert result.status == "failed"
    assert "fixture-secret" not in result.message
