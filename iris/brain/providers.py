"""Model-only adapters. Tool functions and safety decisions stay in Brain."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Protocol

from iris.tools.registry import ToolResult


class ProviderError(Exception):
    """Sanitized errors; never retain SDK messages, bodies or credentials."""
    def __init__(self, kind: str, retryable: bool = False, *,
                 status_code: int | None = None, provider: str | None = None) -> None:
        allowed = {"configuration", "auth", "permission", "quota", "transport", "timeout", "unavailable",
                   "not_found", "request", "protocol", "blocked"}
        kind = kind if kind in allowed else "protocol"
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code if type(status_code) is int and 100 <= status_code <= 599 else None
        self.provider = provider if provider in {"openai", "gemini"} else None
        super().__init__(self.diagnostic())

    def diagnostic(self) -> str:
        """Only allowlisted categories, provider names and numeric status escape."""
        label = {"openai": "OpenAI", "gemini": "Gemini"}.get(self.provider, "AI provider")
        status = f", HTTP {self.status_code}" if self.status_code is not None else ""
        hints = {
            "configuration": "Set the selected provider's API key and model for cloud questions. Local commands remain available.",
            "auth": "Check the selected provider's API key configuration.",
            "permission": "Check project permissions, API restrictions and regional access.",
            "quota": "Check the project's quota and billing tier, then retry later.",
            "transport": "Check the internet connection, proxy and firewall.",
            "timeout": "The request timed out; check connectivity and try again later.",
            "unavailable": "The service is unavailable; retry later without changing credentials.",
            "not_found": "Check the selected model's availability and project access in the provider console.",
            "request": "Check the adapter request format, tool schemas and installed SDK version.",
            "protocol": "The response format was unexpected; check the adapter and SDK version.",
            "blocked": "The provider did not return a usable answer; rephrase the request.",
        }
        return f"{label} error ({self.kind}{status}). {hints[self.kind]}"


class UnconfiguredProvider:
    """No SDK/network initialization when cloud settings are absent."""
    def start_turn(self, *args: Any) -> Any:
        raise ProviderError("configuration")

    def close(self) -> None:
        pass


def _provider_error(error: Exception, provider: str) -> ProviderError:
    """Classify status and typed causes without exposing SDK text or headers."""
    import httpx
    status = getattr(error, "status_code", None)
    if type(status) is not int:
        status = getattr(error, "code", None)
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    # Gemini commonly reports invalid/restricted keys as HTTP 400. Inspect
    # allowlisted machine-readable ErrorInfo reasons, never the message text.
    payload = getattr(error, "details", None)
    reason = None
    if isinstance(payload, dict):
        body = payload.get("error", payload)
        details = body.get("details", []) if isinstance(body, dict) else []
        if isinstance(details, list):
            for detail in details:
                if isinstance(detail, dict):
                    value = detail.get("reason")
                    if not isinstance(value, str):
                        continue
                    if value in {"API_KEY_INVALID", "API_KEY_EXPIRED"}:
                        reason = "auth"
                    elif value in {"API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED",
                                   "API_KEY_IP_ADDRESS_BLOCKED", "SERVICE_DISABLED", "BILLING_DISABLED"}:
                        reason = "permission"
    categories = {400: "request", 401: "auth", 403: "permission", 404: "not_found",
                  408: "timeout", 429: "quota", 500: "unavailable", 502: "unavailable",
                  503: "unavailable", 504: "timeout"}
    if status is not None:
        kind = reason or categories.get(status, "unavailable" if status >= 500 else "request")
    else:
        kind = "protocol"
        if provider == "openai":
            from openai import APIConnectionError, APITimeoutError
            if isinstance(error, APIConnectionError):
                kind = "timeout" if isinstance(error, APITimeoutError) else "transport"
        cause: BaseException | None = error
        for _ in range(4):
            if isinstance(cause, httpx.TimeoutException):
                kind = "timeout"
                break
            if isinstance(cause, (httpx.TransportError, OSError)):
                kind = "transport"
                break
            cause = cause.__cause__ if cause is not None else None
    return ProviderError(kind, retryable=kind in {"quota", "transport", "timeout", "unavailable"},
                         status_code=status, provider=provider)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments_json: str = field(repr=False)


@dataclass(frozen=True)
class ModelReply:
    text: str
    calls: tuple[ToolCall, ...]
    native_state: list[dict[str, Any]] = field(repr=False)


class ProviderTurn(Protocol):
    def generate(self, allow_tools: bool) -> ModelReply: ...
    def submit_results(self, reply: ModelReply, results: list[tuple[ToolCall, ToolResult]]) -> None: ...


class AIProvider(Protocol):
    def start_turn(self, history: list[dict[str, str]], instructions: str,
                   definitions: list[dict[str, Any]]) -> ProviderTurn: ...
    def close(self) -> None: ...


def _native_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ProviderError("protocol")
    result = []
    for item in items:
        raw = item if isinstance(item, dict) else item.model_dump(exclude_none=True)
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
            raise ProviderError("protocol")
        result.append(deepcopy(raw))
    return result


def _calls(items: list[dict[str, Any]]) -> tuple[ToolCall, ...]:
    calls = []
    for item in items:
        if item["type"] != "function_call":
            continue
        call_id, name = item.get("call_id"), item.get("name")
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            raise ProviderError("protocol")
        arguments = item.get("arguments")
        encoded = arguments if isinstance(arguments, str) else "null"
        calls.append(ToolCall(call_id, name, encoded))
    return tuple(calls)


class OpenAIProvider:
    def __init__(self, client: Any, model: str) -> None:
        self.client, self.model = client, model

    def start_turn(self, history: list[dict[str, str]], instructions: str,
                   definitions: list[dict[str, Any]]) -> ProviderTurn:
        return _OpenAITurn(self.client, self.model, history, instructions, definitions)

    def close(self) -> None:
        self.client.close()


class _OpenAITurn:
    def __init__(self, client: Any, model: str, history: list[dict[str, str]],
                 instructions: str, definitions: list[dict[str, Any]]) -> None:
        self.client, self.model, self.instructions = client, model, instructions
        self.history = deepcopy(history)
        self.tools = [{"type": "function", **d["function"], "strict": False} for d in definitions]

    def generate(self, allow_tools: bool) -> ModelReply:
        from openai import APIError, AuthenticationError
        try:
            response = self.client.responses.create(model=self.model, instructions=self.instructions,
                input=deepcopy(self.history), tools=deepcopy(self.tools),
                tool_choice="auto" if allow_tools else "none", parallel_tool_calls=False, store=False)
        except AuthenticationError as error:
            # Preserve the legacy OpenAI retry policy while improving status reporting.
            normalized = _provider_error(error, "openai")
            normalized.retryable = True
            raise normalized from None
        except APIError as error:
            normalized = _provider_error(error, "openai")
            normalized.retryable = True
            raise normalized from None
        items = _native_items(response.output)
        if getattr(response, "status", "completed") not in {"completed", None}:
            raise ProviderError("protocol")
        text = response.output_text
        if not isinstance(text, str):
            raise ProviderError("protocol")
        return ModelReply(text, _calls(items), items)

    def submit_results(self, reply: ModelReply, results: list[tuple[ToolCall, ToolResult]]) -> None:
        self.history.extend(deepcopy(reply.native_state))
        for call, result in results:
            self.history.append({"type": "function_call_output", "call_id": call.id,
                                 "output": json.dumps(asdict(result))})


class GeminiProvider:
    def __init__(self, client: Any, model: str) -> None:
        self.client, self.model = client, model

    def start_turn(self, history: list[dict[str, str]], instructions: str,
                   definitions: list[dict[str, Any]]) -> ProviderTurn:
        return _GeminiTurn(self.client, self.model, history, instructions, definitions)

    def close(self) -> None:
        self.client.close()


class _GeminiTurn:
    def __init__(self, client: Any, model: str, history: list[dict[str, str]],
                 instructions: str, definitions: list[dict[str, Any]]) -> None:
        self.client, self.model, self.instructions = client, model, instructions
        self.history = [{"role": "user" if m["role"] == "user" else "model",
                         "parts": [{"text": m["content"]}]} for m in history]
        # parameters_json_schema accepts JSON Schema, unlike the SDK's narrower
        # OpenAPI Schema class. Keep every registry constraint unchanged.
        self.tools = [{"name": d["function"]["name"], "description": d["function"]["description"],
                       "parameters_json_schema": deepcopy(d["function"]["parameters"])} for d in definitions]

    def generate(self, allow_tools: bool) -> ModelReply:
        try:
            response = self.client.models.generate_content(model=self.model,
                contents=deepcopy(self.history), config={
                    "system_instruction": self.instructions,
                    "tools": [{"function_declarations": deepcopy(self.tools)}] if self.tools else [],
                    "automatic_function_calling": {"disable": True},
                    "tool_config": {"function_calling_config": {"mode": "AUTO" if allow_tools else "NONE"}},
                })
        except Exception as error:
            raise _provider_error(error, "gemini") from None
        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, list) or not candidates:
            feedback = getattr(response, "prompt_feedback", None)
            blocked = getattr(feedback, "block_reason", None)
            raise ProviderError("blocked" if blocked else "protocol", provider="gemini")
        candidate = candidates[0]
        finish = getattr(candidate, "finish_reason", None)
        if finish is not None and str(finish) not in {"STOP", "FinishReason.STOP"}:
            raise ProviderError("protocol" if str(finish).endswith("MALFORMED_FUNCTION_CALL") else "blocked",
                                provider="gemini")
        content = getattr(candidate, "content", None)
        if content is None or (not isinstance(content, dict) and not callable(getattr(content, "model_dump", None))):
            raise ProviderError("protocol", provider="gemini")
        raw = deepcopy(content) if isinstance(content, dict) else content.model_dump(exclude_none=True)
        if not isinstance(raw, dict) or raw.get("role", "model") != "model" or not isinstance(raw.get("parts"), list):
            raise ProviderError("protocol", provider="gemini")
        text, calls = [], []
        for index, part in enumerate(raw["parts"]):
            if not isinstance(part, dict):
                raise ProviderError("protocol", provider="gemini")
            function = part.get("function_call")
            if function is not None:
                if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
                    raise ProviderError("protocol", provider="gemini")
                native_id = function.get("id")
                if native_id is not None and (not isinstance(native_id, str) or not native_id):
                    raise ProviderError("protocol", provider="gemini")
                # Gemini 2.5 may omit IDs; preserve native parts and use a local
                # correlation ID only for Brain's dispatch and duplicate checks.
                call_id = native_id or f"gemini-{len(self.history)}-{index}"
                args = function.get("args")
                try:
                    encoded = json.dumps(args, allow_nan=False) if isinstance(args, dict) else "null"
                except (TypeError, ValueError):
                    encoded = "null"
                calls.append(ToolCall(call_id, function["name"], encoded))
            elif part.get("text") is not None and not part.get("thought", False):
                if not isinstance(part["text"], str):
                    raise ProviderError("protocol", provider="gemini")
                text.append(part["text"])
        return ModelReply("".join(text), tuple(calls), [raw])

    def submit_results(self, reply: ModelReply, results: list[tuple[ToolCall, ToolResult]]) -> None:
        self.history.extend(deepcopy(reply.native_state))
        native_calls = [p["function_call"] for p in reply.native_state[0]["parts"] if "function_call" in p]
        identities = {call.id: original.get("id") for call, original in zip(reply.calls, native_calls)}
        parts = []
        for call, result in results:
            function = {"name": call.name, "response": asdict(result)}
            if identities[call.id] is not None:
                function["id"] = identities[call.id]
            parts.append({"function_response": function})
        self.history.append({"role": "user", "parts": parts})
