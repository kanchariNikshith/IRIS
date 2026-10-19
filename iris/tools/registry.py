"""Validated tool dispatch through the permission gate."""
from copy import deepcopy
from dataclasses import dataclass
import json
import re
import traceback
from typing import Any, Callable, Literal

from jsonschema import Draft202012Validator, ValidationError

from iris.logs.action_log import ActionLog
from iris.security.permissions import Confirmation, Permission, PermissionGate


@dataclass(frozen=True)
class ToolResult:
    status: Literal["verified", "unverified", "failed"]
    message: str

    def __post_init__(self) -> None:
        if self.status not in {"verified", "unverified", "failed"} or not isinstance(self.message, str):
            raise ValueError("Invalid tool result.")


@dataclass(frozen=True)
class Tool:
    name: str
    schema: dict[str, Any]
    permission: Permission
    function: Callable[..., ToolResult]
    description: str = ""
    exposed: bool = True


class ToolRegistry:
    def __init__(self, gate: PermissionGate, action_log: ActionLog) -> None:
        self.gate = gate
        self.action_log = action_log
        self._tools: dict[str, Tool] = {}
        self.on_confirmation: Callable[[Confirmation], None] | None = None
        self.on_result: Callable[[str, ToolResult], None] | None = None

    def register(self, tool: Tool) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", tool.name) or tool.name in self._tools:
            raise ValueError("Tool name invalid or already registered.")
        permission = Permission(tool.permission)
        if tool.name in {"send_email", "forget"} and permission != Permission.CONFIRM:
            raise ValueError("This tool always requires confirmation.")
        schema = deepcopy(tool.schema)
        if schema.get("type") != "object":
            raise ValueError("Tool arguments must have an object schema.")
        schema["additionalProperties"] = False
        # External schemas are never fetched during validation.
        def check_refs(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"$ref", "$dynamicRef"} and not str(item).startswith("#"):
                        raise ValueError("External schema references are forbidden.")
                    check_refs(item)
            elif isinstance(value, list):
                for item in value:
                    check_refs(item)
        check_refs(schema)
        Draft202012Validator.check_schema(schema)
        if not callable(tool.function):
            raise ValueError("Tool function must be callable.")
        self._tools[tool.name] = Tool(tool.name, schema, permission, tool.function, tool.description, tool.exposed)

    def definitions(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": deepcopy(t.schema)}}
            for t in self._tools.values() if t.exposed]

    def execute(self, name: str, arguments: dict[str, Any] | str, *, turn_id: str = "",
                explicit_memory_request: bool = False,
                on_confirmation: Callable[[Confirmation], None] | None = None) -> ToolResult:
        safe_arguments: dict[str, Any] = {}
        error_trace = None
        dispatching = False
        try:
            if name not in self._tools:
                result = ToolResult("failed", "The tool does not exist.")
            else:
                tool = self._tools[name]
                parsed = json.loads(arguments) if isinstance(arguments, str) else deepcopy(arguments)
                if not isinstance(parsed, dict):
                    raise ValueError("Arguments must be an object.")
                safe_arguments = parsed
                Draft202012Validator(tool.schema).validate(parsed)
                if not self.gate.authorize(name, tool.permission, turn_id=turn_id,
                        explicit_memory_request=explicit_memory_request,
                        on_confirmation=on_confirmation or self.on_confirmation):
                    result = ToolResult("failed", "Action cancelled or permission denied.")
                elif self.gate.kill_switch.is_set():
                    result = ToolResult("failed", "Stopped.")
                else:
                    dispatching = True
                    result = tool.function(**parsed)
                    if not isinstance(result, ToolResult):
                        raise TypeError("Tools must return ToolResult.")
        except Exception as error:
            if not dispatching and isinstance(error, (ValidationError, ValueError)):
                result = ToolResult("failed", "I couldn't do that because the request was unclear.")
            else:
                # Tool boundary: catch runtime errors, never expose their contents.
                frames = traceback.extract_tb(error.__traceback__)
                error_trace = "\n".join(f"{f.filename}:{f.lineno} in {f.name}" for f in frames)
                result = ToolResult("failed", "Something went wrong with that.")
        try:
            self.action_log.write(name, safe_arguments, result.status, result.message, traceback=error_trace)
        except (OSError, ValueError, TypeError):
            result = ToolResult("failed", "Could not record the action result.")
        if self.on_result is not None:
            try:
                self.on_result(name, result)
            except Exception:
                pass  # A UI observer must never change dispatch or its outcome.
        return result
