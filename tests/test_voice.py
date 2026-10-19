from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from iris.audio.voice import VoiceController, read_console_line, start_voice_hotkeys, voice_console
from iris.audio.worker import AudioError
from iris.brain.brain import Brain
from iris.brain.providers import GeminiProvider, OpenAIProvider
from iris.config import Config
from iris.logs.action_log import ActionLog
from iris.security.permissions import Permission, PermissionGate
from iris.tools.registry import Tool, ToolRegistry, ToolResult


class FakeSpeaker:
    def __init__(self):
        self.busy = Event()
        self.texts = []
        self.closed = False
        self.mic_open = lambda: False

    def start(self):
        pass

    def enqueue(self, text):
        assert not self.mic_open()
        self.texts.append(text)
        self.on_state("speaking")
        return True

    def close(self):
        self.closed = True
        self.busy.clear()


class FakeEars:
    def __init__(self, text="Open Gmail."):
        self.text = text
        self.calls = 0
        self.open = False
        self.closed = False

    def listen(self, cancel, state):
        self.calls += 1
        self.open = True
        state("listening")
        self.open = False
        state("processing")
        return self.text

    def close(self):
        self.closed = True


def wait_for(predicate, seconds=3):
    deadline = monotonic() + seconds
    while not predicate():
        if monotonic() > deadline:
            pytest.fail("Worker did not reach expected state")
        Event().wait(0.005)


@pytest.fixture
def runtime():
    brain = Mock()
    brain.registry.gate = PermissionGate()
    brain.secrets = ("fixture-secret",)
    brain.run.return_value = "Could not confirm: Browser dispatched."
    ears, speaker, events = FakeEars(), FakeSpeaker(), []
    speaker.mic_open = lambda: ears.open
    controller = VoiceController(brain, "base", ears=ears, speaker=speaker,
                                 emit=lambda label, text: events.append((label, text)))
    controller.start()
    yield controller, brain, ears, speaker, events
    controller.close()
    assert not controller._thread.is_alive()


def test_voice_one_brain_call_and_clear_states(runtime):
    controller, brain, ears, speaker, events = runtime
    assert controller.request_listen()
    wait_for(lambda: not controller.busy.is_set())
    brain.run.assert_called_once_with("Open Gmail.")
    assert ears.calls == 1
    assert speaker.texts == ["Could not confirm: Browser dispatched."]
    states = [text for label, text in events if label == "State"]
    for state in ("listening", "processing", "speaking", "idle"):
        assert state in states
    assert states[-1] == "idle"


def test_hotkey_during_queued_speech_does_not_record(runtime):
    controller, brain, ears, speaker, _ = runtime
    speaker.busy.set()
    assert controller.request_listen() is False
    assert ears.calls == 0
    brain.run.assert_not_called()
    speaker.busy.clear()


def test_busy_hotkeys_are_not_queued_or_replayed(runtime):
    controller, brain, ears, _, _ = runtime
    entered, release = Event(), Event()
    def listen(cancel, state):
        entered.set()
        release.wait(2)
        return "Open Gmail"
    ears.listen = listen
    assert controller.request_listen()
    assert entered.wait(2)
    assert controller.request_listen() is False
    assert controller.submit_text("Open Gmail") is False
    release.set()
    wait_for(lambda: not controller.busy.is_set())
    brain.run.assert_called_once_with("Open Gmail")


def test_kill_discards_late_transcription_and_speech(runtime):
    controller, brain, ears, speaker, _ = runtime
    entered, release = Event(), Event()
    def listen(cancel, state):
        entered.set()
        release.wait(2)
        return "Open Gmail"
    ears.listen = listen
    controller.request_listen()
    assert entered.wait(2)
    controller.stop()
    release.set()
    wait_for(lambda: not controller.busy.is_set())
    brain.run.assert_not_called()
    assert not speaker.texts
    assert controller.request_listen() is False


def test_pause_closes_capture_without_latching_global_kill(runtime):
    controller, brain, ears, _, _ = runtime
    entered = Event()
    def listen(cancel, state):
        entered.set()
        while not cancel.is_set():
            Event().wait(0.005)
        return "Open Gmail"
    ears.listen = listen
    controller.request_listen()
    assert entered.wait(2)
    assert controller.submit_text("stop listening")
    wait_for(lambda: not controller.busy.is_set())
    assert controller.paused.is_set() and not controller.gate.kill_switch.is_set()
    assert controller.request_listen() is False
    brain.run.assert_not_called()
    assert controller.submit_text("start listening")
    wait_for(lambda: not controller.busy.is_set())
    assert not controller.paused.is_set()


def test_spoken_pause_resume_and_stop_are_local_controls(runtime):
    controller, brain, ears, _, _ = runtime
    ears.text = "Iris, stop listening."
    controller.request_listen()
    wait_for(lambda: not controller.busy.is_set())
    assert controller.paused.is_set()
    controller.submit_text("Start listening.")
    wait_for(lambda: not controller.busy.is_set())
    ears.text = "Stop."
    controller.request_listen()
    wait_for(controller.gate.kill_switch.is_set)
    brain.run.assert_not_called()


def test_three_empty_captures_suggest_typing_and_never_run_brain(runtime):
    controller, brain, ears, speaker, _ = runtime
    ears.text = ""
    for _ in range(3):
        assert controller.request_listen()
        wait_for(lambda: not controller.busy.is_set())
    assert "typing" in speaker.texts[-1]
    brain.run.assert_not_called()


def test_missing_mic_error_keeps_text_commands_working(runtime):
    controller, brain, ears, _, events = runtime
    ears.listen = Mock(side_effect=AudioError("microphone"))
    controller.request_listen()
    wait_for(lambda: not controller.busy.is_set())
    assert ("State", "error") in events
    assert any("can't find a microphone" in text for _, text in events)
    controller.submit_text("Hello")
    wait_for(lambda: not controller.busy.is_set())
    brain.run.assert_called_once_with("Hello")


def test_voice_secrets_are_masked_before_output_and_brain(runtime):
    controller, brain, ears, speaker, events = runtime
    ears.text = "Hello fixture-secret"
    brain.run.return_value = "Response fixture-secret"
    controller.request_listen()
    wait_for(lambda: not controller.busy.is_set())
    brain.run.assert_called_once_with("Hello [REDACTED]")
    assert all("fixture-secret" not in text for _, text in events)
    assert speaker.texts == ["Response [REDACTED]"]


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_voice_gmail_uses_existing_provider_gate_validation_and_truthful_log(tmp_path, provider):
    registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    handler = Mock(return_value=ToolResult("unverified", "Browser dispatched; page loading unconfirmed."))
    registry.register(Tool("open_url", {"type": "object", "properties": {"url": {"type": "string"}},
                                       "required": ["url"]}, Permission.AUTO, handler))
    client = Mock()
    if provider == "openai":
        client.responses.create.side_effect = [
            SimpleNamespace(output=[{"type": "function_call", "call_id": "gmail-1", "name": "open_url",
                                     "arguments": '{"url":"https://mail.google.com"}'}], output_text=""),
            SimpleNamespace(output=[], output_text="Done, Gmail loaded.")]
        adapter = OpenAIProvider(client, "fixture-model")
    else:
        def response(parts):
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP", content={"role": "model", "parts": parts})])
        client.models.generate_content.side_effect = [
            response([{"function_call": {"name": "open_url", "args": {"url": "https://mail.google.com"}}}]),
            response([{"text": "Done, Gmail loaded."}])]
        adapter = GeminiProvider(client, "fixture-model")
    brain = Brain(client, "fixture-model", registry, provider=adapter)
    speaker = FakeSpeaker()
    controller = VoiceController(brain, "base", ears=FakeEars(), speaker=speaker, emit=Mock())
    controller.start()
    try:
        assert controller.request_listen()
        wait_for(lambda: not controller.busy.is_set())
        handler.assert_called_once_with(url="https://mail.google.com")
        assert "Could not confirm" in speaker.texts[-1]
        assert "Done" not in speaker.texts[-1]
        assert '"status": "unverified"' in registry.action_log.path.read_text()
    finally:
        controller.close()


def test_hotkey_callbacks_only_enqueue_and_listener_start_cleanup():
    controller, factory = Mock(), Mock()
    listener = start_voice_hotkeys(controller, "<ctrl>+<alt>+<space>", "<ctrl>+<alt>+<esc>", factory)
    callbacks = factory.call_args.args[0]
    controller.request_listen.assert_not_called()
    callbacks["<ctrl>+<alt>+<space>"]()
    controller.request_listen.assert_called_once()
    callbacks["<ctrl>+<alt>+<esc>"]()
    controller.stop.assert_called_once()
    listener.start.assert_called_once()
    with pytest.raises(ValueError):
        start_voice_hotkeys(controller, "same", "same", factory)
    listener.start.side_effect = RuntimeError("fixture")
    with pytest.raises(RuntimeError):
        start_voice_hotkeys(controller, "ptt", "kill", factory)
    listener.stop.assert_called_once()


def test_console_keyboard_polling_editing_and_kill():
    keyboard, stop, writes = Mock(), Event(), []
    keyboard.kbhit.return_value = True
    keyboard.getwch.side_effect = ["h", "x", "\b", "i", "\r"]
    assert read_console_line(stop, keyboard=keyboard, write=writes.append) == "hi"
    keyboard.kbhit.return_value = False
    keyboard.kbhit.side_effect = lambda: (stop.set() or False)
    assert read_console_line(stop, keyboard=keyboard, write=writes.append) is None


def test_voice_console_hotkey_failure_keeps_typed_fallback_and_closes():
    brain, controller, factory, listener_factory = Mock(), Mock(), Mock(), Mock()
    brain.registry.gate = PermissionGate()
    factory.return_value = controller
    listener_factory.side_effect = RuntimeError("fixture-secret")
    voice_console(brain, Config("fixture-secret"), controller_factory=factory,
                  listener_factory=listener_factory, line_reader=Mock(side_effect=["Hello", None]))
    controller.submit_text.assert_called_once_with("Hello")
    controller.stop.assert_called_once()
    controller.close.assert_called_once()
    assert "fixture-secret" not in str(controller.emit.call_args_list)


def test_console_listener_cleanup_failure_still_closes_controller():
    brain, controller, factory, listeners = Mock(), Mock(), Mock(), Mock()
    brain.registry.gate = PermissionGate()
    factory.return_value = controller
    listeners.return_value.stop.side_effect = RuntimeError("fixture-error")
    with pytest.raises(RuntimeError):
        voice_console(brain, Config("fixture-secret"), controller_factory=factory,
                      listener_factory=listeners, line_reader=Mock(return_value=None))
    controller.close.assert_called_once()


def test_close_cancels_active_recording_and_closes_brain_once(runtime):
    controller, brain, ears, speaker, _ = runtime
    entered = Event()
    def listen(cancel, state):
        entered.set()
        while not cancel.is_set():
            Event().wait(0.005)
        return "Open Gmail"
    ears.listen = listen
    controller.request_listen()
    assert entered.wait(2)
    controller.close()
    controller.close()
    assert ears.closed and speaker.closed
    assert not controller._thread.is_alive()
    brain.run.assert_not_called()
    brain.close.assert_called_once()
