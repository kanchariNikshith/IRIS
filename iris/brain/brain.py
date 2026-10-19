"""Provider-independent bounded tool loop with trusted action reporting."""
from copy import deepcopy
import re
import traceback
from threading import Event, Lock, Thread
from typing import Any, Callable
from uuid import uuid4
from time import monotonic

from iris.brain.prompts import system_prompt
from iris.brain.providers import AIProvider, ModelReply, OpenAIProvider, ProviderError, ProviderTurn, ToolCall
from iris.config import redact
from iris.tools.registry import ToolRegistry, ToolResult
from iris.brain.local import route_local
from iris.telemetry import RuntimeMetrics

MAX_TOOL_CALLS = 8


class Brain:
    def __init__(self, client: Any, model: str, registry: ToolRegistry, *,
                 secrets: tuple[str, ...] = (),
                 provider: AIProvider | None = None,
                 local_commands: bool = False,
                 retry_wait: Callable[[float], bool] | None = None) -> None:
        if not model.strip():
            raise ValueError("OPENAI_MODEL is required for text commands.")
        self.client, self.model, self.registry = client, model, registry
        self.provider = provider if provider is not None else OpenAIProvider(client, model)
        self.secrets = secrets
        self.local_commands = local_commands
        self.metrics = RuntimeMetrics()
        self.history: list[dict[str, str]] = []
        self._lock = Lock()
        self._retry_wait = retry_wait or registry.gate.kill_switch.wait

    def close(self) -> None:
        self.provider.close()

    def _request(self, turn: ProviderTurn, final: bool) -> ModelReply:
        started = monotonic()
        try:
            return turn.generate(allow_tools=not final)
        finally:
            self.metrics.record("provider_requests", elapsed=monotonic() - started)

    def _response(self, turn: ProviderTurn, final: bool) -> ModelReply | None:
        """Let cancellation return immediately while a bounded HTTP call finishes."""
        for attempt in range(2):
            if self.registry.gate.kill_switch.is_set():
                return None
            finished = Event()
            outcome: list[Any] = []
            def request() -> None:
                try:
                    outcome.append(self._request(turn, final))
                except Exception as error:
                    outcome.append(error)
                finally:
                    finished.set()
            Thread(target=request, daemon=True).start()
            while not finished.wait(0.05):
                if self.registry.gate.kill_switch.is_set():
                    return None
            if self.registry.gate.kill_switch.is_set():
                return None
            result = outcome[0]
            if isinstance(result, ProviderError):
                if result.retryable and attempt == 0:
                    interrupted = self._retry_wait(2.0)
                    if self.registry.gate.kill_switch.is_set():
                        return None
                    if not interrupted:
                        continue
                raise result
            if isinstance(result, Exception):
                raise result
            return result
        return None

    @staticmethod
    def _no_tool_reply(request: str, reply: str) -> str:
        """Allow ordinary questions; conservatively refuse unperformed actions.

        English command detection is deliberately broad. Ambiguous commands and
        action language in a model's no-tool reply are not accepted as evidence.
        """
        action = r"\b(open|launch|start|scroll|press|type|write|send|save|remember|forget|delete|click|buy|search|close|mute|volume|tab|run)\b"
        question = r"^(?:iris[, ]+)?(?:who|what|why|how|when|where|which|explain|describe|tell me about|hello|hi|hey|thanks)\b"
        claim = (r"\b(done|opened|launched|started|scrolled|pressed|typed|sent|saved|deleted|closed|completed)\b"
                 r"|\b(?:i|we)\s+(?:have\s+)?(?:open|launch|start|scroll|press|type|send|save|close)\b"
                 r"|\b(?:is|are|has been|have been)\s+(?:now\s+)?(?:open|running|ready|complete|successful)\b")
        information = re.match(r"^(?:what can you do|what are your capabilities|can you (?:explain|describe)|how (?:do|does|can|to)\b|explain\b|describe\b|tell me (?:about|how)\b)", request.strip(), re.IGNORECASE)
        capability = re.fullmatch(
            r"(?:(?:just )?(?:list|tell me) (?:the )?(?:things you can do|your capabilities)"
            r"|(?:what|which) (?:apps|applications|tools) (?:can you|do you) (?:open|use|support))\??",
            request.strip(), re.IGNORECASE)
        information = information or capability
        if ((not re.search(question, request.strip(), re.IGNORECASE) and not information)
                or (re.search(action, request, re.IGNORECASE) and not information)
                or route_local(request) is not None
                or re.search(claim, reply, re.IGNORECASE)):
            return "I couldn't carry out that request because no tool ran."
        return reply or "I couldn't get a reply."

    def _summary(self, results: list[tuple[str, ToolResult]], limit: bool = False) -> str:
        # Model-generated prose is never used for action outcomes, even if it says done.
        known = {t["function"]["name"] for t in self.registry.definitions()}
        visible = [(name, result) for name, result in results if name in known]
        sentences = []
        for status, label in (("verified", "Verified"), ("unverified", "Could not confirm"),
                              ("failed", "Failed")):
            group = [result.message.rstrip(".") for _, result in visible if result.status == status]
            if group:
                sentences.append(label + ": " + "; ".join(group) + ".")
        if limit:
            # Keep the action summaries and limit notice to at most three sentences.
            notice = "Reached the eight-call limit; remaining actions were not attempted."
            if len(sentences) == 3:
                sentences[-1] = sentences[-1].rstrip(".") + "; " + notice[0].lower() + notice[1:]
            else:
                sentences.append(notice)
        return " ".join(sentences) or "I couldn't carry out that request."

    def _error_reply(self, message: str, error: Exception,
                     results: list[tuple[str, ToolResult]], limit: bool) -> str:
        frames = traceback.extract_tb(error.__traceback__)
        trace = "\n".join(f"{f.filename}:{f.lineno} in {f.name}" for f in frames)
        try:
            self.registry.action_log.write("brain", {}, "failed", message, traceback=trace)
        except (OSError, ValueError, TypeError):
            pass  # The safe reply still reaches the user if audit storage is unavailable.
        if results:
            return self._summary(results, limit).rstrip(".") + "; " + message
        return message

    def run(self, text: str) -> str:
        """Run one command at a time; only user/assistant text survives in history."""
        with self._lock:
            stop = self.registry.gate.kill_switch
            if text.strip().casefold() in {"stop", "iris stop", "iris, stop"}:
                self.registry.gate.stop()
                return "Stopped."
            if stop.is_set():
                return "Stopped."
            if not text.strip():
                return "Please type a command."
            safe_text = redact(text, self.secrets)
            items: list[Any] = deepcopy(self.history[-10:]) + [{"role": "user", "content": safe_text}]
            results: list[tuple[str, ToolResult]] = []
            seen_ids: set[str] = set()
            turn_id = uuid4().hex
            count = 0
            limit = False
            try:
                local = route_local(safe_text) if self.local_commands else None
                if local is not None:
                    started = monotonic()
                    result = self.registry.execute(local.tool, local.arguments, turn_id=turn_id)
                    reply = "Stopped." if stop.is_set() else self._summary([(local.tool, result)])
                    reply = redact(reply, self.secrets)
                    self.metrics.record("local_turns", elapsed=monotonic() - started)
                    self.history.extend([{"role": "user", "content": safe_text}, {"role": "assistant", "content": reply}])
                    self.history = self.history[-10:]
                    return reply
                self.metrics.record("provider_turns")
                turn = self.provider.start_turn(items, system_prompt(), self.registry.definitions())
                while True:
                    response = self._response(turn, count >= MAX_TOOL_CALLS)
                    if response is None or stop.is_set():
                        reply = "Stopped."
                        break
                    calls = response.calls
                    if not calls:
                        reply = self._summary(results, limit) if results else self._no_tool_reply(safe_text, response.text)
                        break
                    if count >= MAX_TOOL_CALLS:
                        reply = self._summary(results, True)
                        break
                    feedback: list[tuple[ToolCall, ToolResult]] = []
                    duplicate = False
                    for call in calls:
                        if stop.is_set():
                            break
                        if count >= MAX_TOOL_CALLS:
                            limit = True
                            result = ToolResult("failed", "Step limit reached; this action was not attempted.")
                            self.registry.action_log.write(call.name, {}, result.status, result.message)
                        else:
                            count += 1
                            if call.id in seen_ids:
                                result = ToolResult("failed", "Duplicate tool call refused.")
                                self.registry.action_log.write(call.name, {}, result.status, result.message)
                                results.append((call.name, result))
                                duplicate = True
                                break
                            seen_ids.add(call.id)
                            result = self.registry.execute(call.name, call.arguments_json, turn_id=turn_id)
                            result = ToolResult(result.status, redact(result.message, self.secrets))
                            results.append((call.name, result))
                        feedback.append((call, result))
                    if stop.is_set():
                        reply = "Stopped."
                        break
                    if duplicate:
                        reply = self._summary(results, limit)
                        break
                    turn.submit_results(response, feedback)
                    if count >= MAX_TOOL_CALLS:
                        limit = True
            except ProviderError as error:
                message = {
                    "auth": "My API key looks wrong.",
                    "quota": "I can't reach my brain right now.",
                    "transport": "I can't reach my brain right now.",
                    "request": "The AI provider couldn't accept that request.",
                    "blocked": "The AI provider couldn't answer that request.",
                    "protocol": "Something went wrong with that.",
                }.get(error.kind, "The AI provider couldn't complete that request.")
                # Gemini and HTTP errors retain useful safe category/status hints.
                if error.provider == "gemini" or error.status_code is not None or error.kind == "configuration":
                    message = error.diagnostic()
                reply = self._error_reply(message, error, results, limit)
            except Exception as error:
                # SDK/protocol boundary: never print exception data containing secrets.
                reply = self._error_reply("Something went wrong with that.", error, results, limit)
            reply = redact(reply, self.secrets)
            self.history.extend([{"role": "user", "content": safe_text}, {"role": "assistant", "content": reply}])
            self.history = self.history[-10:]
            return reply
