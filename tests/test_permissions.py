from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest

from iris.security.permissions import Permission, PermissionGate, start_kill_switch


def test_auto_and_unknown_permissions():
    gate = PermissionGate()
    assert gate.authorize("open_url", Permission.AUTO)
    assert not gate.authorize("open_url", "unknown")
    gate.stop()
    assert not gate.authorize("open_url", Permission.AUTO)


@pytest.mark.parametrize("tool", ["remember", "update_memory"])
def test_memory_requires_explicit_user_request(tool):
    gate = PermissionGate()
    assert not gate.authorize(tool, Permission.AUTO)
    assert gate.authorize(tool, Permission.AUTO, explicit_memory_request=True)


@pytest.mark.parametrize("tool", ["send_email", "forget"])
def test_sensitive_tools_force_confirmation(tool):
    assert not PermissionGate().authorize(tool, Permission.AUTO)


def test_confirmation_is_bound_to_turn_and_one_use():
    gate = PermissionGate()
    ids = []
    def confirm(request):
        ids.append(request.id)
        assert not gate.resolve(request.id, turn_id="old", approved=True)
        assert gate.resolve(request.id, turn_id="current", approved=True)
        assert not gate.resolve(request.id, turn_id="current", approved=True)
    for _ in range(2):
        assert gate.authorize("send_email", Permission.CONFIRM,
                              turn_id="current", on_confirmation=confirm)
    assert ids[0] != ids[1]
    assert not gate.resolve(ids[0], turn_id="current", approved=True)


def test_timeout_and_rejection():
    gate = PermissionGate(timeout=0)
    assert not gate.authorize("forget", Permission.CONFIRM, turn_id="turn",
                              on_confirmation=lambda request: None)
    gate = PermissionGate()
    def decline(request):
        gate.resolve(request.id, turn_id="turn", approved=False)
    assert not gate.authorize("forget", Permission.CONFIRM,
                              turn_id="turn", on_confirmation=decline)


def test_kill_switch_wakes_confirmation():
    gate = PermissionGate()
    ready = Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(gate.authorize, "send_email", Permission.CONFIRM,
                                 turn_id="turn", on_confirmation=lambda request: ready.set())
        assert ready.wait(2)
        gate.stop()
        assert future.result(timeout=2) is False
    assert gate.kill_switch.is_set()


def test_hotkey_adapter_uses_mock_hardware():
    factory = Mock()
    gate = PermissionGate()
    listener = start_kill_switch(gate, listener_factory=factory)
    listener.start.assert_called_once()
    factory.call_args.args[0]["<ctrl>+<alt>+<esc>"]()
    assert gate.kill_switch.is_set()


@pytest.mark.parametrize("timeout", [-1, 31])
def test_timeout_bounds(timeout):
    with pytest.raises(ValueError):
        PermissionGate(timeout)
