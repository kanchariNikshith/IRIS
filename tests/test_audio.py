from itertools import chain, repeat
import sys
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from iris.audio.ears import Ears, RecordingSettings, _recognize, record_audio, transcribe_audio
from iris.audio.speaker import Speaker, _speak, spoken_text
from iris.audio.worker import AudioError, StopToken, reap, run_worker


def capture_device(values, *, available=1600):
    timer = [0.0]
    stream = Mock(read_available=available)
    samples = iter(chain(values, repeat(0.0)))
    def read(frames):
        timer[0] += frames / 16000
        return np.full((frames, 1), next(samples), dtype=np.float32), False
    stream.read.side_effect = read
    device = Mock()
    device.query_devices.return_value = {"max_input_channels": 1}
    device.InputStream.return_value = stream
    return device, stream, lambda: timer[0], timer


def test_capture_silence_closes_stream_and_bounds_memory():
    device, stream, clock, _ = capture_device([0.1])
    listening = Mock()
    audio = record_audio(Event(), device=device, clock=clock, on_listening=listening)
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert 1600 < len(audio) < 240000
    listening.assert_called_once()
    stream.start.assert_called_once()
    stream.abort.assert_called_once()
    stream.close.assert_called_once()
    assert device.InputStream.call_args.kwargs == {
        "samplerate": 16000, "channels": 1, "dtype": "float32", "blocksize": 1600}


def test_no_speech_and_continuous_speech_timeouts():
    device, stream, clock, _ = capture_device([])
    assert record_audio(Event(), device=device, clock=clock) is None
    assert stream.read.call_count <= 51
    device, stream, clock, _ = capture_device(repeat(0.1))
    audio = record_audio(Event(), device=device, clock=clock)
    assert len(audio) <= 240000
    assert stream.read.call_count <= 150


def test_stalled_microphone_times_out_without_blocking_read():
    device, stream, clock, timer = capture_device([], available=0)
    stop = Mock()
    stop.is_set.return_value = False
    stop.wait.side_effect = lambda seconds: timer.__setitem__(0, timer[0] + seconds)
    assert record_audio(stop, device=device, clock=clock) is None
    stream.read.assert_not_called()
    stream.close.assert_called_once()


def test_recording_cancellation_and_pre_cancelled_no_open():
    stop = Event()
    device, stream, clock, _ = capture_device([0.1])
    stream.read.side_effect = lambda frames: (stop.set() or np.ones((frames, 1), dtype=np.float32), False)
    assert record_audio(stop, device=device, clock=clock) is None
    stream.close.assert_called_once()
    device.reset_mock()
    assert record_audio(stop, device=device) is None
    device.InputStream.assert_not_called()


@pytest.mark.parametrize("problem,kind", [("missing", "microphone"), ("denied", "permission"),
                                         ("open", "audio"), ("read", "audio"), ("overflow", "audio"),
                                         ("close", "audio")])
def test_audio_errors_are_safe_and_resources_close(problem, kind):
    device, stream, clock, _ = capture_device([0.1])
    secret_error = RuntimeError("raw-device-error-fixture-secret")
    if problem == "missing":
        device.query_devices.side_effect = secret_error
    elif problem == "denied":
        device.query_devices.side_effect = PermissionError("fixture-secret")
    elif problem == "open":
        stream.start.side_effect = secret_error
    elif problem == "read":
        stream.read.side_effect = secret_error
    elif problem == "overflow":
        stream.read.return_value = (np.ones((1600, 1)), True)
        stream.read.side_effect = None
    else:
        stream.abort.side_effect = secret_error
    with pytest.raises(AudioError) as caught:
        record_audio(Event(), device=device, clock=clock)
    assert caught.value.kind == kind
    assert "fixture-secret" not in str(caught.value)
    if problem not in {"missing", "denied"}:
        stream.close.assert_called_once()


def test_whisper_is_local_cpu_int8_and_consumes_lazy_segments():
    factory = Mock()
    factory.return_value.transcribe.return_value = (
        iter([SimpleNamespace(text=" Open"), SimpleNamespace(text="Gmail. ")]), None)
    audio = np.ones(1600, dtype=np.float32)
    assert transcribe_audio(audio, "base", Event(), factory=factory) == "Open Gmail."
    factory.assert_called_once_with("base", device="cpu", compute_type="int8", local_files_only=True)
    assert factory.return_value.transcribe.call_args.kwargs["vad_filter"] is True


@pytest.mark.parametrize("stage,kind", [("load", "model"), ("segments", "transcription")])
def test_whisper_failures_do_not_expose_native_details(stage, kind):
    factory = Mock()
    if stage == "load":
        factory.side_effect = RuntimeError("fixture-secret")
    else:
        def segments():
            raise RuntimeError("fixture-secret")
            yield
        factory.return_value.transcribe.return_value = (segments(), None)
    with pytest.raises(AudioError) as caught:
        transcribe_audio(np.ones(5), "base", Event(), factory=factory)
    assert caught.value.kind == kind and "fixture-secret" not in str(caught.value)


def test_whisper_discards_cancelled_segments():
    stop, factory = Event(), Mock()
    def segments():
        stop.set()
        yield SimpleNamespace(text="Open Gmail")
    factory.return_value.transcribe.return_value = (segments(), None)
    assert transcribe_audio(np.ones(5), "base", stop, factory=factory) == ""
    factory.reset_mock()
    assert transcribe_audio(np.ones(5), "base", stop, factory=factory) == ""
    factory.assert_not_called()


def test_recognizer_closes_capture_before_transcribing(monkeypatch):
    sender = Mock()
    closed = []
    def record(stop, on_listening):
        on_listening()
        closed.append(True)
        return np.ones(5)
    def transcribe(*args):
        assert closed
        return "Open Gmail"
    monkeypatch.setattr("iris.audio.ears.record_audio", record)
    monkeypatch.setattr("iris.audio.ears.transcribe_audio", transcribe)
    _recognize(sender, Event(), "base")
    assert [c.args[0] for c in sender.send.call_args_list] == [
        ("state", "listening"), ("state", "processing"), ("text", "Open Gmail")]
    sender.close.assert_called_once()


def test_recognizer_no_speech_never_transcribes(monkeypatch):
    sender, transcribe = Mock(), Mock()
    monkeypatch.setattr("iris.audio.ears.record_audio", Mock(return_value=None))
    monkeypatch.setattr("iris.audio.ears.transcribe_audio", transcribe)
    _recognize(sender, Event(), "base")
    transcribe.assert_not_called()
    sender.send.assert_called_once_with(("empty", ""))


def worker_context(messages):
    context, receiver, sender, process = Mock(), Mock(), Mock(), Mock()
    context.Pipe.return_value = (receiver, sender)
    context.Process.return_value = process
    process.is_alive.return_value = False
    receiver.poll.return_value = True
    receiver.recv.side_effect = messages
    return context, receiver, sender, process


def test_worker_messages_and_cleanup_without_native_processes():
    context, receiver, sender, process = worker_context([
        ("state", "listening"), ("state", "processing"), ("text", "Open Gmail")])
    state = Mock()
    assert run_worker(Mock(), (), Event(), timeout=5, context=context, on_state=state) == "Open Gmail"
    assert [c.args[0] for c in state.call_args_list] == ["listening", "processing"]
    process.join.assert_called_once_with(timeout=0.5)
    process.close.assert_called_once()
    receiver.close.assert_called_once()


@pytest.mark.parametrize("message", [("unexpected", "fixture-secret"), ("error", "fixture-secret"),
                                    ("error", ["fixture-secret"])])
def test_worker_protocol_errors_are_sanitized_and_reaped(message):
    context, _, _, process = worker_context([message])
    with pytest.raises(AudioError) as caught:
        run_worker(Mock(), (), Event(), timeout=5, context=context)
    assert "fixture-secret" not in str(caught.value)
    process.close.assert_called_once()


def test_worker_cancellation_discards_late_reply_and_reaps():
    context, receiver, _, process = worker_context([("text", "Open Gmail")])
    stop = Event()
    receiver.poll.side_effect = lambda timeout: (stop.set() or True)
    assert run_worker(Mock(), (), stop, timeout=5, context=context) is None
    process.close.assert_called_once()
    context.reset_mock()
    assert run_worker(Mock(), (), stop, timeout=5, context=context) is None
    context.Process.assert_not_called()


def test_worker_timeout_and_forced_shutdown():
    context, _, _, process = worker_context([])
    with pytest.raises(AudioError) as caught:
        run_worker(Mock(), (), Event(), timeout=1, context=context, clock=Mock(side_effect=[0, 2]))
    assert caught.value.kind == "timeout"
    process.close.assert_called_once()
    process = Mock()
    process.is_alive.side_effect = [True, True, False]
    cancel = Mock()
    reap(process, cancel)
    cancel.set.assert_called_once()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    process.close.assert_called_once()


def test_hung_capture_has_a_shorter_parent_side_timeout():
    context, _, _, process = worker_context([("state", "listening")])
    with pytest.raises(AudioError) as caught:
        run_worker(Mock(), (), Event(), timeout=90, context=context,
                   clock=Mock(side_effect=[0, 0, 0, 17]), state_timeouts={"listening": 16})
    assert caught.value.kind == "timeout"
    process.close.assert_called_once()


def test_hung_wake_standby_has_a_parent_watchdog_and_is_reaped():
    context, _, _, process = worker_context([("state", "standby")])
    state = Mock()
    with pytest.raises(AudioError) as caught:
        run_worker(Mock(), (), Event(), timeout=166, context=context, on_state=state,
                   clock=Mock(side_effect=[0, 0, 0, 62]), state_timeouts={"standby": 61})
    assert caught.value.kind == "timeout"
    state.assert_called_once_with("standby")
    process.close.assert_called_once()


def test_ears_close_prevents_worker_creation():
    runner = Mock()
    ears = Ears("base", runner=runner)
    ears.close()
    assert ears.listen(Event(), Mock()) is None
    runner.assert_not_called()


def test_speech_short_plain_and_no_code_readout():
    text = spoken_text("- **Could not confirm:** Browser dispatched. Second sentence. Third sentence. Fourth sentence. ```print('x')``` 😀")
    assert text == "Could not confirm: Browser dispatched. Second sentence. Third sentence."
    assert len(spoken_text("x" * 1000)) == 600


def test_native_tts_owned_engine_and_com_cleanup(monkeypatch):
    engine, com, sender = Mock(), Mock(), Mock()
    monkeypatch.setitem(sys.modules, "pyttsx3", SimpleNamespace(init=Mock(return_value=engine)))
    monkeypatch.setitem(sys.modules, "pythoncom", com)
    monkeypatch.setattr("iris.audio.speaker.sys.platform", "win32")
    _speak(sender, Event(), "Could not confirm page loading.")
    engine.say.assert_called_once_with("Could not confirm page loading.")
    engine.runAndWait.assert_called_once()
    engine.stop.assert_called_once()
    com.CoInitialize.assert_called_once()
    com.CoUninitialize.assert_called_once()
    sender.send.assert_called_once_with(("done", ""))


def test_tts_failure_is_safe(monkeypatch):
    engine, sender = Mock(), Mock()
    engine.runAndWait.side_effect = RuntimeError("fixture-secret")
    monkeypatch.setitem(sys.modules, "pyttsx3", SimpleNamespace(init=lambda: engine))
    monkeypatch.setitem(sys.modules, "pythoncom", Mock())
    _speak(sender, Event(), "Hello")
    sender.send.assert_called_once_with(("error", "speech"))
    engine.stop.assert_called_once()


@pytest.mark.parametrize("stage", ["stop", "com"])
def test_tts_cleanup_failures_are_sanitized(monkeypatch, stage):
    engine, com, sender = Mock(), Mock(), Mock()
    if stage == "stop":
        engine.stop.side_effect = RuntimeError("fixture-secret")
    else:
        com.CoUninitialize.side_effect = RuntimeError("fixture-secret")
    monkeypatch.setattr("iris.audio.speaker.sys.platform", "win32")
    monkeypatch.setitem(sys.modules, "pyttsx3", SimpleNamespace(init=lambda: engine))
    monkeypatch.setitem(sys.modules, "pythoncom", com)
    _speak(sender, Event(), "Hello")
    sender.send.assert_called_once_with(("error", "speech"))
    sender.close.assert_called_once()


def test_speaker_error_keeps_queue_worker_alive_and_sanitizes_errors():
    failed = Event()
    errors = []
    def report(message):
        errors.append(message)
        failed.set()
    runner = Mock(side_effect=[RuntimeError("fixture-secret"), ""])
    speaker = Speaker(Event(), runner=runner, on_error=report)
    speaker.start()
    try:
        speaker.enqueue("First reply")
        assert failed.wait(2)
        assert speaker._thread.is_alive()
        assert "fixture-secret" not in errors[0]
        assert speaker.enqueue("Second reply")
        deadline = monotonic() + 2
        while speaker.busy.is_set() and monotonic() < deadline:
            Event().wait(0.01)
        assert not speaker.busy.is_set()
        assert runner.call_count == 2
    finally:
        speaker.close()


def test_nonblocking_speaker_mutes_queue_and_closes_active_worker():
    entered, release = Event(), Event()
    def runner(target, args, stop, **kwargs):
        entered.set()
        while not release.is_set() and not stop.is_set():
            release.wait(0.01)
    speaker = Speaker(Event(), runner=runner)
    speaker.start()
    try:
        assert speaker.enqueue("Hello")
        assert speaker.busy.is_set()
        assert entered.wait(2)
        assert speaker.enqueue("Second reply")
        speaker.close()  # Must cancel even without the global kill event set.
        assert not speaker._thread.is_alive()
        assert not speaker.busy.is_set()
        assert not speaker.enqueue("Late reply")
    finally:
        release.set()
        speaker.close()


def test_stop_token_observes_any_cancel_event():
    first, second = Event(), Event()
    token = StopToken(first, second)
    assert token.wait(0) is False
    second.set()
    assert token.wait(1) is True
