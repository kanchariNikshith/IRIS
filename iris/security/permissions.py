"""A code-enforced gate and one-use confirmation queue."""
from dataclasses import dataclass, field
from enum import Enum
from threading import Event, Lock
from time import monotonic
from typing import Any, Callable
from uuid import uuid4


class Permission(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"


@dataclass
class Confirmation:
    id: str
    tool: str
    turn_id: str
    deadline: float
    event: Event = field(default_factory=Event, repr=False)
    approved: bool = False


class PermissionGate:
    def __init__(self, timeout: float = 30.0) -> None:
        if not 0 <= timeout <= 30:
            raise ValueError("Confirmation timeout must be between 0 and 30 seconds.")
        self.timeout = timeout
        self.kill_switch = Event()
        self._lock = Lock()
        self._pending: dict[str, Confirmation] = {}

    def stop(self) -> None:
        """Latch cancellation and wake every pending confirmation."""
        with self._lock:
            self.kill_switch.set()
            for request in self._pending.values():
                request.approved = False
                request.event.set()
            self._pending.clear()

    def authorize(
        self, tool: str, permission: Permission, *, turn_id: str = "",
        explicit_memory_request: bool = False,
        on_confirmation: Callable[[Confirmation], None] | None = None,
    ) -> bool:
        if self.kill_switch.is_set():
            return False
        if tool in {"remember", "update_memory"} and not explicit_memory_request:
            return False
        if tool in {"send_email", "forget"}:
            permission = Permission.CONFIRM
        if permission == Permission.AUTO:
            return True
        if permission != Permission.CONFIRM or not turn_id or on_confirmation is None:
            return False
        request = Confirmation(uuid4().hex, tool, turn_id, monotonic() + self.timeout)
        with self._lock:
            if self.kill_switch.is_set():
                return False
            self._pending[request.id] = request
        try:
            on_confirmation(request)
            request.event.wait(max(0, request.deadline - monotonic()))
            return request.approved and not self.kill_switch.is_set()
        finally:
            with self._lock:
                self._pending.pop(request.id, None)

    def resolve(self, request_id: str, *, turn_id: str, approved: bool) -> bool:
        """Consume a response only for this request and conversation turn."""
        with self._lock:
            request = self._pending.get(request_id)
            if (request is None or request.event.is_set() or request.turn_id != turn_id
                    or monotonic() >= request.deadline or self.kill_switch.is_set()):
                return False
            request.approved = approved is True
            request.event.set()
            return True


def start_kill_switch(
    gate: PermissionGate, hotkey: str = "<ctrl>+<alt>+<esc>",
    listener_factory: Callable[..., Any] | None = None,
) -> Any:
    """Start the Windows hotkey listener; caller owns stop/join on shutdown.

    The lazy import keeps config checks and offline tests hardware-free.
    """
    if listener_factory is None:
        from pynput.keyboard import GlobalHotKeys
        listener_factory = GlobalHotKeys
    listener = listener_factory({hotkey: gate.stop})
    listener.start()
    return listener
