from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from openai import APIConnectionError, AuthenticationError
import pytest

from iris.brain.brain import Brain
from iris.logs.action_log import ActionLog
from iris.security.permissions import Permission, PermissionGate
from iris.tools.registry import Tool, ToolRegistry, ToolResult


class Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return deepcopy(vars(self))


def call(name="get_time", arguments="{}", call_id="call-1"):
    return Item(type="function_call", name=name, arguments=arguments, call_id=call_id)


def response(*items, text="Done."):
    return SimpleNamespace(output=list(items), output_text=text)


@pytest.fixture
def setup_brain(tmp_path):
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    handler = Mock(return_value=ToolResult("verified", "The time is 10:30."))
    registry.register(Tool("get_time", {"type": "object", "properties": {}, "required": []}, Permission.AUTO, handler))
    client = Mock()
    brain = Brain(client, "user-selected-model", registry, retry_wait=Mock(return_value=False))
    return brain, client, handler


def test_verified_result_protocol_and_model(setup_brain):
    brain, client, handler = setup_brain
    reasoning = Item(type="reasoning", id="reasoning-1", summary=[])
    client.responses.create.side_effect = [response(reasoning, call()), response(text="Done.")]
    reply = brain.run("what time is it")
    assert "10:30" in reply and "Verified" in reply
    handler.assert_called_once_with()
    first, second = [c.kwargs for c in client.responses.create.call_args_list]
    assert first["model"] == "user-selected-model"
    assert first["store"] is False and first["parallel_tool_calls"] is False
    assert first["tools"][0]["type"] == "function"
    assert "Current laptop date and time" in first["instructions"]
    assert reasoning.model_dump() in second["input"]
    result = second["input"][-1]
    assert result["type"] == "function_call_output" and result["call_id"] == "call-1"
    assert json.loads(result["output"])["status"] == "verified"


@pytest.mark.parametrize("status,message", [("failed", "The app did not open."),
                                            ("unverified", "Couldn't confirm the page loaded.")])
def test_model_cannot_claim_failed_or_unverified_success(setup_brain, status, message):
    brain, client, handler = setup_brain
    handler.return_value = ToolResult(status, message)
    client.responses.create.side_effect = [response(call()), response(text="Done, it definitely worked!")]
    reply = brain.run("open something")
    assert message in reply
    assert "Done" not in reply and "definitely worked" not in reply
    assert status == json.loads(client.responses.create.call_args.kwargs["input"][-1]["output"])["status"]


def test_unknown_and_invalid_tools_refused(setup_brain):
    brain, client, handler = setup_brain
    client.responses.create.side_effect = [response(call("shell", "{}")), response(call(arguments='{"extra":1}', call_id="second")), response()]
    reply = brain.run("run something")
    handler.assert_not_called()
    assert "shell" not in reply and "Done" not in reply
    assert len(brain.registry.action_log.path.read_text().splitlines()) == 2


def test_no_more_than_eight_tools_even_in_batch(setup_brain):
    brain, client, handler = setup_brain
    client.responses.create.side_effect = [response(*(call(call_id=str(i)) for i in range(12))), response()]
    reply = brain.run("many actions")
    assert handler.call_count == 8
    assert client.responses.create.call_args.kwargs["tool_choice"] == "none"
    outputs = [i for i in client.responses.create.call_args.kwargs["input"] if i.get("type") == "function_call_output"]
    assert len(outputs) == 12
    assert "limit" in reply and "not attempted" in reply


def test_loop_limit_and_disabled_calls(setup_brain):
    brain, client, handler = setup_brain
    client.responses.create.side_effect = [response(call(call_id=str(i))) for i in range(9)]
    assert "limit" in brain.run("keep going")
    assert handler.call_count == 8 and client.responses.create.call_count == 9


def test_question_history_is_last_ten_messages(setup_brain):
    brain, client, handler = setup_brain
    client.responses.create.return_value = response(text="Hello.")
    for i in range(8):
        assert brain.run(f"hello {i}") == "Hello."
    assert len(brain.history) == 10
    assert len(client.responses.create.call_args.kwargs["input"]) == 11
    assert all(message["role"] in {"user", "assistant"} for message in brain.history)
    handler.assert_not_called()


def test_api_error_retries_once_without_secret(setup_brain):
    brain, client, handler = setup_brain
    client.responses.create.side_effect = APIConnectionError(message="fixture-secret", request=Mock())
    assert brain.run("hello") == "I can't reach my brain right now."
    assert client.responses.create.call_count == 2
    brain._retry_wait.assert_called_once_with(2.0)
    handler.assert_not_called()


def test_auth_error_and_partial_success(setup_brain):
    brain, client, _ = setup_brain
    auth = AuthenticationError("fixture-secret", response=Mock(status_code=401, headers={}), body=None)
    client.responses.create.side_effect = [response(call()), auth, auth]
    reply = brain.run("get time")
    assert "10:30" in reply and "auth, HTTP 401" in reply
    assert "fixture-secret" not in reply


def test_retry_then_success(setup_brain):
    brain, client, _ = setup_brain
    client.responses.create.side_effect = [APIConnectionError(request=Mock()), response(text="Hello.")]
    assert brain.run("hello") == "Hello."
    assert client.responses.create.call_count == 2


def test_stop_blocks_api_and_tools(setup_brain):
    brain, client, handler = setup_brain
    assert brain.run("stop") == "Stopped."
    assert brain.run("open something") == "Stopped."
    client.responses.create.assert_not_called()
    handler.assert_not_called()


def test_kill_switch_during_tool_batch(setup_brain):
    brain, client, handler = setup_brain
    def first():
        brain.registry.gate.stop()
        return ToolResult("unverified", "Input sent.")
    handler.side_effect = first
    client.responses.create.return_value = response(call(), call(call_id="second"))
    assert brain.run("two actions") == "Stopped."
    assert handler.call_count == 1 and client.responses.create.call_count == 1


def test_secret_masking_and_malformed_response(setup_brain):
    brain, client, _ = setup_brain
    brain.secrets = ("fixture-secret",)
    client.responses.create.return_value = response(text="fixture-secret")
    assert brain.run("hello fixture-secret") == "[REDACTED]"
    assert "fixture-secret" not in str(client.responses.create.call_args)
    client.responses.create.return_value = SimpleNamespace(output=None)
    assert brain.run("hello") == "Something went wrong with that."


def test_model_required(setup_brain):
    brain, client, _ = setup_brain
    with pytest.raises(ValueError, match="OPENAI_MODEL"):
        Brain(client, " ", brain.registry)


def test_kill_switch_during_inflight_api_returns_promptly(setup_brain):
    brain, client, handler = setup_brain
    started, release, finished = Event(), Event(), Event()
    def blocked_request(**kwargs):
        started.set()
        try:
            assert release.wait(3)
            return response(call())
        finally:
            finished.set()
    client.responses.create.side_effect = blocked_request
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(brain.run, "get time")
        try:
            assert started.wait(2)
            brain.registry.gate.stop()
            assert future.result(timeout=2) == "Stopped."
            handler.assert_not_called()
        finally:
            release.set()
            assert finished.wait(2)


def test_runtime_error_log_does_not_include_exception_secret(setup_brain):
    brain, client, _ = setup_brain
    client.responses.create.side_effect = RuntimeError("fixture-secret")
    assert brain.run("hello") == "Something went wrong with that."
    contents = brain.registry.action_log.path.read_text()
    assert "fixture-secret" not in contents and "traceback" in contents
