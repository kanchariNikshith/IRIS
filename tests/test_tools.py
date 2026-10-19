from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from threading import Event
from types import ModuleType
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from iris.logs.action_log import ActionLog
from iris.security.permissions import PermissionGate
from iris.tools.apps import AppTools, matching_processes, resolve_app
from iris.tools.browser import open_url, web_search
from iris.tools.builtins import register_tools
from iris.tools.input import InputTools, KEY_ALLOWLIST
from iris.tools.registry import ToolRegistry
from iris.tools.time import get_time


@pytest.mark.parametrize("url", ["https://www.instagram.com", "http://example.com/path"])
def test_browser_acceptance_is_not_verified(monkeypatch, url):
    browser = Mock(return_value=True)
    monkeypatch.setattr("iris.tools.browser.webbrowser.open", browser)
    assert open_url(url).status == "unverified"
    browser.assert_called_once_with(url, new=2)


@pytest.mark.parametrize("url", ["file:///C:/secret", "javascript:alert(1)", "ftp://example.com",
                                  "https://", "https://user:password@example.com", "https://example.com:bad",
                                  "https://example.com\n", "example.com"])
def test_invalid_urls_do_not_reach_browser(monkeypatch, url):
    browser = Mock()
    monkeypatch.setattr("iris.tools.browser.webbrowser.open", browser)
    assert open_url(url).status == "failed"
    browser.assert_not_called()


def test_browser_failure_and_encoded_search(monkeypatch):
    browser = Mock(return_value=False)
    monkeypatch.setattr("iris.tools.browser.webbrowser.open", browser)
    assert open_url("https://example.com").status == "failed"
    browser.return_value = True
    assert web_search("biryani & tea # Hyderabad").status == "unverified"
    url = browser.call_args.args[0]
    assert parse_qs(urlsplit(url).query)["q"] == ["biryani & tea # Hyderabad"]
    browser.reset_mock()
    assert web_search(" ").status == "failed"
    browser.assert_not_called()


@pytest.fixture
def inputs():
    backend = Mock()
    return InputTools(Event(), backend), backend


@pytest.mark.parametrize("action", list(KEY_ALLOWLIST))
def test_allowlist_keys(inputs, action):
    tools, backend = inputs
    assert tools.press_keys(action).status == "unverified"
    backend.hotkey.assert_called_once_with(*KEY_ALLOWLIST[action])
    assert backend.FAILSAFE is True


@pytest.mark.parametrize("action", ["enter", "win+r", "ctrl+alt+delete", "delete", "unknown"])
def test_arbitrary_keys_refused(inputs, action):
    tools, backend = inputs
    assert tools.press_keys(action).status == "failed"
    backend.hotkey.assert_not_called()


@pytest.mark.parametrize("direction,amount,expected", [("up", 3, 3), ("down", 5, -5)])
def test_scroll_direction(inputs, direction, amount, expected):
    tools, backend = inputs
    assert tools.scroll(direction, amount).status == "unverified"
    backend.scroll.assert_called_once_with(expected)


@pytest.mark.parametrize("direction", ["top", "bottom"])
def test_scroll_extremes(inputs, direction):
    tools, backend = inputs
    assert tools.scroll(direction).status == "unverified"
    backend.hotkey.assert_called_once_with(*KEY_ALLOWLIST[direction])


@pytest.mark.parametrize("direction,amount", [("sideways", 5), ("up", 21), ("down", 0), ("up", True)])
def test_scroll_bounds(inputs, direction, amount):
    tools, backend = inputs
    assert tools.scroll(direction, amount).status == "failed"
    backend.scroll.assert_not_called()


def test_typing_does_not_press_enter(inputs):
    tools, backend = inputs
    assert tools.type_text("Hello!").status == "unverified"
    assert "".join(c.args[0] for c in backend.write.call_args_list) == "Hello!"
    backend.press.assert_not_called()
    backend.hotkey.assert_not_called()


@pytest.mark.parametrize("text", ["", "x" * 501, "hello\n", "hello\r", "hello\t", "hello\x00", "हाय"])
def test_typing_bounds_and_submission_chars(inputs, text):
    tools, backend = inputs
    assert tools.type_text(text).status == "failed"
    backend.write.assert_not_called()


def test_typing_kill_switch_between_characters(inputs):
    tools, backend = inputs
    backend.write.side_effect = lambda character: tools.stop.set()
    assert tools.type_text("Hello").status == "failed"
    assert backend.write.call_count == 1


def test_stopped_input_never_dispatches(inputs):
    tools, backend = inputs
    tools.stop.set()
    for result in (tools.scroll("up"), tools.press_keys("new_tab"), tools.type_text("text")):
        assert result.status == "failed"
    assert backend.mock_calls == []


@pytest.mark.parametrize("method,args", [
    ("scroll", ("down",)), ("scroll", ("top",)), ("scroll", ("bottom",)),
    ("press_keys", ("close_tab",)), ("type_text", ("Hello",)),
])
def test_input_handoff_precedes_dispatch_and_runs_once(method, args):
    backend = Mock()
    def handoff():
        assert backend.mock_calls == []
        return True
    prepare = Mock(side_effect=handoff)
    tools = InputTools(Event(), backend, before_input=prepare)
    assert getattr(tools, method)(*args).status == "unverified"
    prepare.assert_called_once_with()
    assert backend.mock_calls


@pytest.mark.parametrize("method,args", [
    ("scroll", ("down",)), ("press_keys", ("new_tab",)), ("type_text", ("Hello",)),
])
@pytest.mark.parametrize("set_stop", [False, True])
def test_cancelled_handoff_never_sends_input(method, args, set_stop):
    stop, backend = Event(), Mock()
    def handoff():
        if set_stop:
            stop.set()
            return True  # Even an approving callback cannot override cancellation.
        return False
    tools = InputTools(stop, backend, before_input=handoff)
    assert getattr(tools, method)(*args).status == "failed"
    assert backend.mock_calls == []


def test_invalid_or_stopped_input_skips_handoff():
    stop, prepare, backend = Event(), Mock(), Mock()
    tools = InputTools(stop, backend, before_input=prepare)
    tools.scroll("sideways")
    tools.press_keys("enter")
    tools.type_text("invalid\n")
    stop.set()
    tools.scroll("down")
    tools.press_keys("new_tab")
    tools.type_text("Hello")
    prepare.assert_not_called()
    assert backend.mock_calls == []


def test_registered_scroll_uses_handoff_and_logs_cancellation(tmp_path, monkeypatch):
    backend, prepare = Mock(), Mock(return_value=False)
    monkeypatch.setattr(InputTools, "_device", lambda self: backend)
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    register_tools(registry, before_input=prepare)
    result = registry.execute("scroll", {"direction": "down"})
    assert result.status == "failed"
    prepare.assert_called_once_with()
    assert backend.mock_calls == []
    record = json.loads(registry.action_log.path.read_text().strip())
    assert record["tool"] == "scroll"
    assert record["result"]["status"] == "failed"


def test_app_verifies_new_process():
    launch = Mock()
    processes = Mock(side_effect=[{(1, 1.0)}, {(1, 1.0), (2, 2.0)}])
    tools = AppTools(Event(), resolver=Mock(return_value=Path("C:/Windows/System32/notepad.exe")),
                     launcher=launch, processes=processes)
    assert tools.open_app("Notepad").status == "verified"
    launch.assert_called_once_with(str(Path("C:/Windows/System32/notepad.exe")))


def test_existing_process_alone_not_verified():
    tools = AppTools(Event(), resolver=lambda name: Path("C:/apps/spotify.exe"), launcher=Mock(),
                     processes=Mock(return_value={(1, 1.0)}), clock=Mock(side_effect=[0, 8]), wait=Mock())
    assert tools.open_app("spotify").status == "unverified"
    tools.wait.assert_not_called()


@pytest.mark.parametrize("name", ["cmd", "powershell", "C:/script.py", "notepad.exe & unsafe", "unknown"])
def test_arbitrary_apps_rejected(name):
    resolver, launch = Mock(), Mock()
    tools = AppTools(Event(), resolver=resolver, launcher=launch)
    assert tools.open_app(name).status == "failed"
    resolver.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("path", [None, Path("C:/apps/cmd.exe"), Path("C:/apps/spotify.py")])
def test_wrong_app_target_rejected(path):
    launch = Mock()
    assert AppTools(Event(), resolver=lambda name: path, launcher=launch).open_app("spotify").status == "failed"
    launch.assert_not_called()


def test_app_wait_is_cancellable():
    stop = Event()
    def wait(duration):
        assert duration <= 0.2
        stop.set()
        return True
    tools = AppTools(stop, resolver=lambda name: Path("C:/apps/spotify.exe"), launcher=Mock(),
                     processes=Mock(return_value=set()), clock=Mock(return_value=0), wait=wait)
    assert tools.open_app("spotify").status == "failed"


def test_process_matching_mock_os(monkeypatch):
    processes = [Mock(info={"name": "NOTEPAD.EXE", "pid": 1, "create_time": 2.0}),
                 Mock(info={"name": "other.exe", "pid": 2, "create_time": 3.0})]
    monkeypatch.setattr("iris.tools.apps.psutil.process_iter", Mock(return_value=processes))
    assert matching_processes("notepad.exe") == {(1, 2.0)}


def test_time_uses_local_clock(monkeypatch):
    clock = Mock()
    clock.now.return_value = datetime(2026, 10, 13, 9, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("iris.tools.time.datetime", clock)
    result = get_time()
    assert result.status == "verified" and "2026-10-13" in result.message


def test_builtin_registration_and_registry_error_handling(tmp_path, monkeypatch):
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    register_tools(registry)
    assert {t["function"]["name"] for t in registry.definitions()} == {
        "open_url", "web_search", "open_app", "scroll", "press_keys", "type_text", "get_time"}
    assert registry.execute("type_text", {"text": "x" * 501}).status == "failed"
    assert registry.execute("press_keys", {"action": "enter"}).status == "failed"
    monkeypatch.setattr("iris.tools.browser.webbrowser.open", Mock(side_effect=OSError("private error")))
    assert registry.execute("open_url", {"url": "https://example.com"}).status == "failed"
    records = [json.loads(line) for line in registry.action_log.path.read_text().splitlines()]
    assert len(records) == 3 and "private error" not in str(records)


@pytest.mark.parametrize("target_name,expected", [("chrome.exe", True), ("cmd.exe", False),
                                                   ("script.py", False)])
def test_start_menu_only_accepts_catalogued_executable(tmp_path, monkeypatch, target_name, expected):
    root = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    root.mkdir(parents=True)
    (root / "Google Chrome.lnk").touch()
    target = tmp_path / target_name
    target.touch()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    com = ModuleType("pythoncom")
    com.CoInitialize, com.CoUninitialize = Mock(), Mock()
    client = ModuleType("win32com.client")
    shell = Mock()
    shell.CreateShortCut.return_value.TargetPath = str(target)
    client.Dispatch = Mock(return_value=shell)
    package = ModuleType("win32com")
    package.client = client
    monkeypatch.setitem(sys.modules, "pythoncom", com)
    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    assert resolve_app("chrome") == (target if expected else None)
    com.CoInitialize.assert_called_once()
    com.CoUninitialize.assert_called_once()


def test_system_app_resolves_from_system_directory(tmp_path, monkeypatch):
    system = tmp_path / "System32"
    system.mkdir()
    target = system / "notepad.exe"
    target.touch()
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    assert resolve_app("notepad") == target


def test_app_polling_never_exceeds_eight_seconds():
    elapsed = [0.0]
    waits = []
    def wait(duration):
        waits.append(duration)
        elapsed[0] += duration
        return False
    tools = AppTools(Event(), resolver=lambda name: Path("C:/apps/spotify.exe"), launcher=Mock(),
                     processes=lambda name: set(), clock=lambda: elapsed[0], wait=wait)
    assert tools.open_app("spotify").status == "unverified"
    assert elapsed[0] == pytest.approx(8.0)
    assert all(0 < duration <= 0.2 for duration in waits)
