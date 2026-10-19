"""Wire Phase 2 tools into the existing safety boundary."""
from typing import Any, Callable
from iris.security.permissions import Permission
from iris.tools.apps import APP_CATALOG, AppTools
from iris.tools.browser import open_url, web_search
from iris.tools.input import InputTools, KEY_ALLOWLIST
from iris.tools.registry import Tool, ToolRegistry, ToolResult
from iris.tools.time import get_time


def register_tools(registry: ToolRegistry, *,
                   before_input: Callable[[], bool] | None = None) -> None:
    inputs = InputTools(registry.gate.kill_switch, before_input=before_input)
    apps = AppTools(registry.gate.kill_switch)
    def add(name: str, properties: dict[str, Any], required: list[str],
            function: Callable[..., ToolResult], description: str) -> None:
        registry.register(Tool(name, {"type": "object", "properties": properties,
            "required": required}, Permission.AUTO, function, description))
    add("open_url", {"url": {"type": "string", "maxLength": 2048}}, ["url"], open_url,
        "Open an HTTP/HTTPS website in the default browser. Page loading cannot be verified.")
    add("web_search", {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
        ["query"], web_search, "Open a browser search; does not read search results.")
    add("open_app", {"name": {"type": "string", "enum": list(APP_CATALOG)}}, ["name"],
        apps.open_app, "Open a catalogued app and check for a new matching process within 8 seconds.")
    add("scroll", {"direction": {"type": "string", "enum": ["up", "down", "top", "bottom"]},
        "amount": {"type": "integer", "minimum": 1, "maximum": 20}}, ["direction"],
        inputs.scroll, "Send bounded scroll input to the focused window. Response is unverified.")
    add("press_keys", {"action": {"type": "string", "enum": list(KEY_ALLOWLIST)}}, ["action"],
        inputs.press_keys, "Send an allowlisted key action, never Enter or arbitrary keys.")
    add("type_text", {"text": {"type": "string", "minLength": 1, "maxLength": 500,
        "pattern": "^[ -~]+$"}}, ["text"], inputs.type_text,
        "Type printable English text without Enter, tabs or newlines. Cannot verify the contents.")
    add("get_time", {}, [], get_time, "Read the laptop's current local date and time.")
