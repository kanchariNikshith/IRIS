"""Bounded keyboard input to the focused window, never arbitrary keys."""
from threading import Event
from typing import Any, Callable

from iris.tools.registry import ToolResult

KEY_ALLOWLIST = {
    "new_tab": ("ctrl", "t"), "close_tab": ("ctrl", "w"),
    "go_back": ("alt", "left"), "go_forward": ("alt", "right"),
    "top": ("ctrl", "home"), "bottom": ("ctrl", "end"),
    "volume_up": ("volumeup",), "volume_down": ("volumedown",),
    "mute": ("volumemute",),
}


class InputTools:
    def __init__(self, stop: Event, backend: Any = None, *,
                 before_input: Callable[[], bool] | None = None) -> None:
        self.stop = stop
        self._backend = backend
        self._before_input = before_input

    def _ready(self) -> bool:
        if self.stop.is_set():
            return False
        if self._before_input is not None and not self._before_input():
            return False
        return not self.stop.is_set()

    def _device(self) -> Any:
        if self._backend is None:
            import pyautogui
            self._backend = pyautogui
        self._backend.FAILSAFE = True
        return self._backend

    def press_keys(self, action: str) -> ToolResult:
        if action not in KEY_ALLOWLIST:
            return ToolResult("failed", "That key action is not allowed.")
        if not self._ready():
            return ToolResult("failed", "Stopped.")
        keys = KEY_ALLOWLIST[action]
        self._device().hotkey(*keys)
        return ToolResult("unverified", "Keys sent to the focused window; I couldn't confirm its response.")

    def scroll(self, direction: str, amount: int = 5) -> ToolResult:
        if direction not in {"up", "down", "top", "bottom"} or type(amount) is not int or not 1 <= amount <= 20:
            return ToolResult("failed", "The scroll request is invalid.")
        if self.stop.is_set():
            return ToolResult("failed", "Stopped.")
        if direction in {"top", "bottom"}:
            return self.press_keys(direction)
        if not self._ready():
            return ToolResult("failed", "Stopped.")
        self._device().scroll(amount if direction == "up" else -amount)
        return ToolResult("unverified", "Scroll sent to the focused window; I couldn't confirm its response.")

    def type_text(self, text: str) -> ToolResult:
        # PyAutoGUI cannot reliably type Unicode; control characters can submit forms.
        if not isinstance(text, str) or not 1 <= len(text) <= 500 or any(not 32 <= ord(c) <= 126 for c in text):
            return ToolResult("failed", "Use at most 500 printable English characters without newlines or tabs.")
        if not self._ready():
            return ToolResult("failed", "Stopped.")
        device = self._device()
        for character in text:
            if self.stop.is_set():
                return ToolResult("failed", "Stopped; some text may already have been typed.")
            device.write(character)
        return ToolResult("unverified", "Text sent to the focused window without Enter; I couldn't confirm its contents.")
