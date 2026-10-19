from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from iris.brain.brain import Brain
from iris.brain.providers import GeminiProvider, OpenAIProvider, ProviderError
from iris.logs.action_log import ActionLog
from iris.security.permissions import Permission, PermissionGate
from iris.tools.registry import Tool, ToolRegistry, ToolResult


class Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return deepcopy(vars(self))


def call(name="open_app", arguments=None, call_id="first"):
    return Item(type="function_call", id=call_id, name=name,
                arguments={"name": "notepad"} if arguments is None else arguments)


def response(*steps, text="Done, it definitely opened.", status="completed"):
    parts = []
    for step in steps:
        if step.type == "function_call":
            function = {"name": step.name, "args": step.arguments}
            if step.id is not None:
                function["id"] = step.id
            parts.append({"function_call": function})
        else:
            parts.append({"text": "private thought", "thought": True,
                          "thought_signature": step.signature.encode()})
    if text is not None:
        parts.append({"text": text})
    return SimpleNamespace(candidates=[SimpleNamespace(content={"role": "model", "parts": parts},
        finish_reason="STOP" if status in {"completed", "requires_action"} else "SAFETY")])


@pytest.fixture
def gemini(tmp_path):
    client = Mock()
    handler = Mock(return_value=ToolResult("verified", "Opened notepad; a new process appeared."))
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log", ("gemini-fixture-secret",)))
    registry.register(Tool("open_app", {"type": "object", "properties": {"name": {"type": "string"}},
                                       "required": ["name"]}, Permission.AUTO, handler))
    brain = Brain(client, "gemini-fixture-model", registry,
                  provider=GeminiProvider(client, "gemini-fixture-model"),
                  secrets=("gemini-fixture-secret",), retry_wait=Mock(return_value=False))
    return brain, client, handler


def test_gemini_tools_results_and_native_thought_replay(gemini):
    brain, client, handler = gemini
    thought = Item(type="thought", signature="opaque-signature", summary=[])
    client.models.generate_content.side_effect = [response(thought, call(), status="requires_action"), response()]
    assert "Verified" in brain.run("open notepad")
    handler.assert_called_once_with(name="notepad")
    first, second = [item.kwargs for item in client.models.generate_content.call_args_list]
    assert first["model"] == "gemini-fixture-model"
    assert first["config"]["tool_config"]["function_calling_config"]["mode"] == "AUTO"
    assert first["config"]["automatic_function_calling"]["disable"] is True
    assert first["contents"][0] == {"role": "user", "parts": [{"text": "open notepad"}]}
    declaration = first["config"]["tools"][0]["function_declarations"][0]
    assert declaration["parameters_json_schema"]["additionalProperties"] is False
    assert "strict" not in declaration and "parameters" not in declaration
    assert second["contents"][1]["parts"][0]["thought_signature"] == b"opaque-signature"
    feedback = second["contents"][-1]["parts"][0]["function_response"]
    assert feedback["id"] == "first"
    assert feedback["name"] == "open_app"
    assert feedback["response"]["status"] == "verified"
    assert "Current laptop date and time" in first["config"]["system_instruction"]


@pytest.mark.parametrize("status", ["unverified", "failed"])
def test_gemini_never_overrides_tool_status(gemini, status):
    brain, client, handler = gemini
    handler.return_value = ToolResult(status, "Could not check the app.")
    client.models.generate_content.side_effect = [response(call()), response()]
    answer = brain.run("open notepad")
    assert "definitely" not in answer and "Done" not in answer
    assert "Could not check" in answer
    assert json.loads(brain.registry.action_log.path.read_text())["result"]["status"] == status


@pytest.mark.parametrize("arguments", [{}, {"name": 12}, {"name": True}, {"name": "notepad", "script": "bad"},
                                       ["notepad"], "not JSON", {"name": float("nan")}])
def test_gemini_malformed_arguments_never_run(gemini, arguments):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = [response(call(arguments=arguments)), response()]
    assert "Failed" in brain.run("open notepad")
    handler.assert_not_called()


def test_gemini_unknown_and_confirm_tools_do_not_run(gemini):
    brain, client, handler = gemini
    brain.registry.register(Tool("send_email", {"type": "object", "properties": {}, "required": []},
                                 Permission.CONFIRM, handler))
    client.models.generate_content.side_effect = [response(call("shell", {}, "one"), call("send_email", {}, "two")), response()]
    answer = brain.run("send something")
    handler.assert_not_called()
    assert "shell" not in answer
    assert "permission denied" in answer
    assert len(brain.registry.action_log.path.read_text().splitlines()) == 2


def test_gemini_eight_call_budget_and_serial_dispatch(gemini):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = [response(*(call(call_id=str(i)) for i in range(12))), response()]
    assert "limit" in brain.run("many actions")
    assert handler.call_count == 8
    final = client.models.generate_content.call_args.kwargs
    assert final["config"]["tool_config"]["function_calling_config"]["mode"] == "NONE"
    feedback = final["contents"][-1]["parts"]
    assert [i["function_response"]["id"] for i in feedback] == [str(i) for i in range(12)]
    assert len(brain.registry.action_log.path.read_text().splitlines()) == 12


def test_gemini_ignores_calls_from_disabled_final_request(gemini):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = [response(call(call_id=str(i))) for i in range(9)]
    assert "limit" in brain.run("many actions")
    assert handler.call_count == 8
    assert client.models.generate_content.call_count == 9


def test_duplicate_id_is_not_executed_twice(gemini):
    brain, client, handler = gemini
    client.models.generate_content.return_value = response(call(), call())
    assert "Duplicate" in brain.run("open notepad twice")
    assert handler.call_count == 1
    assert client.models.generate_content.call_count == 1


def test_gemini_late_response_cannot_run_tools(gemini):
    brain, client, handler = gemini
    ready, release, finished = Event(), Event(), Event()
    def request(**kwargs):
        ready.set()
        try:
            assert release.wait(3)
            return response(call())
        finally:
            finished.set()
    client.models.generate_content.side_effect = request
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(brain.run, "open notepad")
        try:
            assert ready.wait(2)
            brain.registry.gate.stop()
            assert future.result(timeout=2) == "Stopped."
        finally:
            release.set()
            assert finished.wait(2)
    handler.assert_not_called()


def test_gemini_cancellation_between_tools(gemini):
    brain, client, handler = gemini
    def run(name):
        brain.registry.gate.stop()
        return ToolResult("unverified", "Dispatched.")
    handler.side_effect = run
    client.models.generate_content.return_value = response(call(call_id="one"), call(call_id="two"))
    assert brain.run("two actions") == "Stopped."
    assert handler.call_count == 1


class StatusError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__("gemini-fixture-secret private SDK body")


@pytest.mark.parametrize("status,expected,attempts", [(401, "auth, HTTP 401", 1), (403, "permission, HTTP 403", 1),
    (429, "quota, HTTP 429", 2), (503, "unavailable, HTTP 503", 2), (400, "request, HTTP 400", 1),
    (404, "not_found, HTTP 404", 1)])
def test_gemini_error_mapping_and_retry(gemini, status, expected, attempts):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = StatusError(status)
    assert expected in brain.run("hello")
    assert client.models.generate_content.call_count == attempts
    assert "gemini-fixture-secret" not in brain.registry.action_log.path.read_text()
    handler.assert_not_called()


def test_gemini_retry_after_result_does_not_reexecute_tool(gemini):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = [response(call()), httpx.ConnectError("gemini-fixture-secret"), response()]
    assert "Verified" in brain.run("open notepad")
    assert handler.call_count == 1 and client.models.generate_content.call_count == 3
    requests = client.models.generate_content.call_args_list
    assert requests[1].kwargs["contents"] == requests[2].kwargs["contents"]


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete"])
def test_gemini_blocked_response_does_not_execute(gemini, status):
    brain, client, handler = gemini
    client.models.generate_content.return_value = response(call(), status=status)
    assert "blocked" in brain.run("open notepad")
    handler.assert_not_called()


def test_gemini_fresh_turn_history_and_secret_redaction(gemini):
    brain, client, handler = gemini
    client.models.generate_content.return_value = response(text="Hello gemini-fixture-secret.")
    for _ in range(7):
        assert brain.run("hello gemini-fixture-secret") == "Hello [REDACTED]."
    assert len(brain.history) == 10
    assert len(client.models.generate_content.call_args.kwargs["contents"]) == 11
    assert all(i["role"] in {"user", "model"} for i in client.models.generate_content.call_args.kwargs["contents"])
    assert "gemini-fixture-secret" not in str(client.models.generate_content.call_args)
    handler.assert_not_called()


@pytest.mark.parametrize("provider_name", ["openai", "gemini"])
@pytest.mark.parametrize("command", ["open Instagram", "please launch Notepad", "can you open Gmail?",
                                    "what time is it", "do that", "hello; open Instagram"])
def test_no_tool_success_regression_both_providers(tmp_path, provider_name, command):
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    client = Mock()
    if provider_name == "gemini":
        client.models.generate_content.return_value = response(text="Done, Instagram is open.")
        provider = GeminiProvider(client, "model")
    else:
        client.responses.create.return_value = SimpleNamespace(output=[], output_text="Done, Instagram is open.")
        provider = OpenAIProvider(client, "model")
    brain = Brain(client, "model", registry, provider=provider)
    answer = brain.run(command)
    assert "no tool ran" in answer
    assert "Done" not in answer and "Instagram is open" not in answer


def test_gemini_empty_response_is_safe(gemini):
    brain, client, handler = gemini
    client.models.generate_content.return_value = response(text="")
    assert brain.run("hello") == "I couldn't get a reply."
    handler.assert_not_called()


def test_gemini_bad_call_identity_is_protocol_error(gemini):
    brain, client, handler = gemini
    client.models.generate_content.return_value = response(call(call_id=""))
    assert "protocol" in brain.run("open notepad")
    handler.assert_not_called()


def test_ordinary_question_still_returns_model_answer(gemini):
    brain, client, _ = gemini
    client.models.generate_content.return_value = response(text="Photosynthesis converts light into chemical energy.")
    assert brain.run("what is photosynthesis?") == "Photosynthesis converts light into chemical energy."


def test_shared_guard_rejects_action_claim_inside_question_reply(gemini):
    brain, client, _ = gemini
    client.models.generate_content.return_value = response(text="Done. Notepad is now open.")
    assert "no tool ran" in brain.run("hello")


def test_gemini_cancellation_during_retry_wait(gemini):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = StatusError(503)
    def stop_during_wait(seconds):
        assert seconds == 2.0
        brain.registry.gate.stop()
        return True
    brain._retry_wait = stop_during_wait
    assert brain.run("hello") == "Stopped."
    assert client.models.generate_content.call_count == 1
    handler.assert_not_called()


def test_gemini_stop_before_turn_makes_no_request(gemini):
    brain, client, handler = gemini
    brain.registry.gate.stop()
    assert brain.run("open notepad") == "Stopped."
    client.models.generate_content.assert_not_called()
    handler.assert_not_called()


def test_gemini_secret_in_tool_result_is_masked(gemini):
    brain, client, handler = gemini
    handler.return_value = ToolResult("failed", "gemini-fixture-secret")
    client.models.generate_content.side_effect = [response(call()), response()]
    answer = brain.run("open notepad")
    assert "gemini-fixture-secret" not in answer
    assert "gemini-fixture-secret" not in brain.registry.action_log.path.read_text()
    assert "gemini-fixture-secret" not in str(client.models.generate_content.call_args)


def test_gemini_schema_does_not_change_registry(gemini):
    brain, client, _ = gemini
    original = brain.registry.definitions()
    turn = brain.provider.start_turn([], "instructions", original)
    turn.tools[0]["parameters_json_schema"]["required"].clear()
    assert brain.registry.definitions()[0]["function"]["parameters"]["required"] == ["name"]


def test_gemini_25_calls_without_native_ids_are_correlated(gemini):
    brain, client, handler = gemini
    client.models.generate_content.side_effect = [response(call(call_id=None), call(call_id=None)), response()]
    assert "Verified" in brain.run("open notepad twice")
    assert handler.call_count == 2
    feedback = client.models.generate_content.call_args.kwargs["contents"][-1]["parts"]
    assert len(feedback) == 2
    assert all("id" not in part["function_response"] for part in feedback)


@pytest.mark.parametrize("finish", ["SAFETY", "MAX_TOKENS", "MALFORMED_FUNCTION_CALL"])
def test_bad_finish_reason_never_executes_partial_calls(gemini, finish):
    brain, client, handler = gemini
    reply = response(call())
    reply.candidates[0].finish_reason = finish
    client.models.generate_content.return_value = reply
    assert ("protocol" if finish == "MALFORMED_FUNCTION_CALL" else "blocked") in brain.run("open notepad")
    handler.assert_not_called()


def test_missing_content_has_sanitized_protocol_diagnostic(gemini):
    brain, client, handler = gemini
    client.models.generate_content.return_value = SimpleNamespace(candidates=[SimpleNamespace(content=None)])
    assert "Gemini error (protocol)" in brain.run("Hello")
    handler.assert_not_called()


def test_non_allowlisted_error_reasons_do_not_escape(gemini):
    brain, client, handler = gemini
    error = StatusError(400)
    error.details = {"error": {"message": "gemini-fixture-secret", "details": [
        {"reason": "gemini-fixture-secret"}, {"reason": ["private"]}]}}
    client.models.generate_content.side_effect = error
    answer = brain.run("Hello")
    assert "request, HTTP 400" in answer
    assert "gemini-fixture-secret" not in answer
    handler.assert_not_called()

