"""Real GenerateContent SDK serialization with no network or hardware."""
import json
import httpx
import pytest
from google import genai
from google.genai import types
from iris.brain.brain import Brain
from iris.brain.providers import GeminiProvider
from iris.logs.action_log import ActionLog
from iris.security.permissions import Permission, PermissionGate
from iris.tools.builtins import register_tools
from iris.tools.registry import Tool, ToolRegistry, ToolResult


def client_with_transport(handler):
    return genai.Client(api_key="offline-gemini-fixture", vertexai=False,
        http_options=types.HttpOptions(timeout=20000, retry_options=types.HttpRetryOptions(attempts=1),
            client_args={"transport": httpx.MockTransport(handler)}))


def make_brain(tmp_path, handler):
    client = client_with_transport(handler)
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    return Brain(client, "gemini-2.5-flash", registry,
        provider=GeminiProvider(client, "gemini-2.5-flash"), retry_wait=lambda seconds: False)


def candidate(parts, finish="STOP"):
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}]}


@pytest.mark.parametrize("native_id", [None, "call-1"])
def test_sdk_round_trip_tool_schemas_and_results(tmp_path, native_id):
    requests = []
    def handler(request):
        assert request.url.path.endswith("/models/gemini-2.5-flash:generateContent")
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            function = {"name": "get_time", "args": {}}
            if native_id:
                function["id"] = native_id
            payload = candidate([{"functionCall": function, "thoughtSignature": "c2lnbmF0dXJl"}])
        else:
            payload = candidate([{"text": "Done."}])
        return httpx.Response(200, json=payload)
    brain = make_brain(tmp_path, handler)
    brain.registry.register(Tool("get_time", {"type": "object", "properties": {}, "required": []},
        Permission.AUTO, lambda: ToolResult("verified", "The time is 10:30.")))
    try:
        assert "10:30" in brain.run("what time is it")
        assert len(requests) == 2
        first = requests[0]
        assert "store" not in first and "input" not in first
        assert first["systemInstruction"]["parts"][0]["text"]
        declaration = first["tools"][0]["functionDeclarations"][0]
        schema = declaration.get("parametersJsonSchema", declaration.get("parameters_json_schema"))
        assert schema["additionalProperties"] is False
        assert "parameters" not in declaration
        assert requests[1]["contents"][1]["parts"][0]["thoughtSignature"] == "c2lnbmF0dXJl"
        feedback = requests[1]["contents"][-1]["parts"][0]["functionResponse"]
        assert feedback.get("id") == native_id
        assert feedback["response"]["status"] == "verified"
    finally:
        brain.close()


def test_sdk_hello_with_all_seven_tool_schemas(tmp_path):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=candidate([{"text": "Hello! How can I help?"}]))
    brain = make_brain(tmp_path, handler)
    register_tools(brain.registry)
    try:
        assert brain.run("Hello") == "Hello! How can I help?"
        tools = requests[0]["tools"][0]["functionDeclarations"]
        assert len(tools) == 7
        schemas = {tool["name"]: tool.get("parametersJsonSchema", tool.get("parameters_json_schema")) for tool in tools}
        assert schemas["type_text"]["properties"]["text"]["maxLength"] == 500
        assert schemas["type_text"]["properties"]["text"]["pattern"] == "^[ -~]+$"
        assert schemas["scroll"]["properties"]["amount"]["maximum"] == 20
        assert all(schema["additionalProperties"] is False for schema in schemas.values())
    finally:
        brain.close()


@pytest.mark.parametrize("failure", ["status", "transport", "timeout"])
def test_sdk_retries_disabled_and_brain_retries_once(tmp_path, failure):
    requests = []
    def handler(request):
        requests.append(request)
        if failure == "transport":
            raise httpx.ConnectError("offline-gemini-fixture")
        if failure == "timeout":
            raise httpx.ReadTimeout("offline-gemini-fixture")
        return httpx.Response(503, json={"error": {"code": 503, "message": "offline-gemini-fixture", "status": "UNAVAILABLE"}})
    brain = make_brain(tmp_path, handler)
    try:
        reply = brain.run("hello")
        assert {"status": "unavailable, HTTP 503", "transport": "transport", "timeout": "timeout"}[failure] in reply
        assert len(requests) == 2
        assert "offline-gemini-fixture" not in brain.registry.action_log.path.read_text()
    finally:
        brain.close()


@pytest.mark.parametrize("status,category,attempts", [(400, "request", 1), (401, "auth", 1),
    (403, "permission", 1), (404, "not_found", 1), (429, "quota", 2), (503, "unavailable", 2)])
def test_sdk_http_diagnostics_are_safe(tmp_path, status, category, attempts):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"code": status,
            "message": "offline-gemini-fixture Authorization Bearer private user content", "status": "UNKNOWN"}})
    brain = make_brain(tmp_path, handler)
    try:
        reply = brain.run("Hello")
        assert f"{category}, HTTP {status}" in reply
        assert len(requests) == attempts
        log = brain.registry.action_log.path.read_text()
        for sensitive in ("offline-gemini-fixture", "Authorization", "Bearer", "private user content"):
            assert sensitive not in reply and sensitive not in log
        if status == 404:
            assert "model" in reply and "access" in reply
            assert "API key" not in reply
    finally:
        brain.close()


@pytest.mark.parametrize("reason,category", [("API_KEY_INVALID", "auth"), ("API_KEY_IP_ADDRESS_BLOCKED", "permission")])
def test_sdk_errorinfo_classification_without_message_leaks(tmp_path, reason, category):
    def handler(request):
        return httpx.Response(400, json={"error": {"code": 400, "message": "offline-gemini-fixture",
            "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason,
                         "metadata": {"api_key": "offline-gemini-fixture", "request": "private"}}]}})
    brain = make_brain(tmp_path, handler)
    try:
        assert f"{category}, HTTP 400" in brain.run("Hello")
        assert "offline-gemini-fixture" not in brain.registry.action_log.path.read_text()
    finally:
        brain.close()


def test_sdk_never_reexecutes_tools_after_retry(tmp_path):
    requests, executions = [], []
    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(200, json=candidate([{"functionCall": {"name": "get_time", "args": {}}}]))
        if len(requests) == 2:
            return httpx.Response(503, json={"error": {"code": 503, "message": "unavailable"}})
        return httpx.Response(200, json=candidate([{"text": "Done."}]))
    brain = make_brain(tmp_path, handler)
    def get_time():
        executions.append(1)
        return ToolResult("verified", "The time is 10:30.")
    brain.registry.register(Tool("get_time", {"type": "object", "properties": {}, "required": []}, Permission.AUTO, get_time))
    try:
        assert "10:30" in brain.run("What time is it?")
        assert len(executions) == 1
        assert requests[1] == requests[2]
    finally:
        brain.close()
