"""R1 routes exercise the real registry/gate/log without network or desktop input."""
import json
from unittest.mock import Mock
import pytest

from iris.brain.brain import Brain
from iris.brain.local import route_local
from iris.config import Config, load_config
from iris.logs.action_log import ActionLog
from iris.main import create_brain
from iris.security.permissions import Permission, PermissionGate
from iris.tools.registry import Tool, ToolRegistry, ToolResult


@pytest.mark.parametrize("text,tool,args", [
    ("IRIS, please open Notepad!", "open_app", {"name": "notepad"}),
    ("What time is it?", "get_time", {}),
    ("open https://example.com/Case?q=One", "open_url", {"url": "https://example.com/Case?q=One"}),
    ("scroll down 20", "scroll", {"direction": "down", "amount": 20}),
    ("scroll to top", "scroll", {"direction": "top"}),
    ("close tab", "press_keys", {"action": "close_tab"}),
    ("close the current tab", "press_keys", {"action": "close_tab"}),
])
def test_exact_routes(text, tool, args):
    assert (route_local(text).tool, route_local(text).arguments) == (tool, args)


@pytest.mark.parametrize("text", ["open Notepad and write hello", "open that", "scroll down 21",
    "scroll down forever", "close tab then send", "open cmd", "open file:///secret",
    "open https://user:password@example.com", "how do I open Notepad?", "send it", "type hello"])
def test_ambiguous_or_unsupported_is_not_local(text):
    assert route_local(text) is None


def test_local_action_preserves_registry_audit_truth_and_cancel(tmp_path):
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    handler = Mock(return_value=ToolResult("unverified", "Launch dispatched."))
    registry.register(Tool("open_app", {"type": "object", "properties": {"name": {"enum": ["notepad"]}},
                                       "required": ["name"]}, Permission.AUTO, handler))
    provider = Mock()
    brain = Brain(None, "fixture", registry, provider=provider, local_commands=True)
    assert brain.run("open Notepad") == "Could not confirm: Launch dispatched."
    provider.start_turn.assert_not_called()
    handler.assert_called_once_with(name="notepad")
    assert json.loads(registry.action_log.path.read_text())["result"]["status"] == "unverified"
    assert brain.metrics.snapshot()["counts"] == {"local_turns": 1}
    registry.gate.stop()
    assert brain.run("open Notepad") == "Stopped."
    assert handler.call_count == 1


def test_local_route_does_not_bypass_confirmation(tmp_path):
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    handler = Mock(return_value=ToolResult("verified", "Opened."))
    registry.register(Tool("open_app", {"type": "object", "properties": {"name": {"type": "string"}}},
                           Permission.CONFIRM, handler))
    registry.on_confirmation = lambda request: registry.gate.resolve(request.id, turn_id=request.turn_id, approved=False)
    brain = Brain(None, "fixture", registry, provider=Mock(), local_commands=True)
    assert "cancelled" in brain.run("open notepad")
    handler.assert_not_called()


def test_missing_cloud_config_real_factory_time_and_cloud_error(tmp_path, monkeypatch):
    monkeypatch.setattr("iris.main.prepare_console_input", Mock())
    config = load_config(tmp_path / "missing", {}, require_cloud=False)
    brain = create_brain(config)
    brain.registry.action_log = ActionLog(tmp_path / "actions.log")
    try:
        assert "Verified" in brain.run("what time is it")
        assert "configuration" in brain.run("explain gravity")
        assert "provider_requests" not in brain.metrics.snapshot()["counts"]
        assert "API key" in brain.history[-1]["content"]
    finally:
        brain.close()


@pytest.mark.parametrize("question,answer", [
    ("What can you do?", "I can open supported apps."),
    ("How do I open Notepad?", "Use the Start menu to open Notepad."),
    ("Can you explain gravity?", "Mass attracts mass."),
    ("What is a date palm?", "A tree."),
    ("Just list the things you can do", "I can open supported apps."),
    ("Which apps can you open?", "I can open Notepad and catalogued apps."),
])
def test_informational_questions_do_not_false_refuse(question, answer):
    assert Brain._no_tool_reply(question, answer) == answer


def test_informational_question_still_rejects_invented_completion():
    assert "no tool ran" in Brain._no_tool_reply("How do I open Notepad?", "Done, I opened it.")
