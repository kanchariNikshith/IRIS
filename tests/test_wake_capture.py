"""Offline R3 wake-to-command tests; no real detector, microphone or provider."""
from itertools import chain, repeat
from threading import Event, Lock, Thread
from unittest.mock import Mock

import numpy as np
import pytest

from iris.audio.capture import CaptureOwner, WakeCaptureSettings
from iris.audio.ears import Ears, _recognize_after_wake
from iris.audio.wake import WakeModelError, WakeTrigger, wake_command
from iris.audio.worker import AudioError


def device_fixture(chunks):
    timer = [0.0]
    chunks = iter(chain(chunks, repeat(np.zeros((1600, 1), dtype=np.float32))))
    stream = Mock(read_available=1600)
    def read(frames):
        timer[0] += frames / 16000
        return next(chunks), False
    stream.read.side_effect = read
    device = Mock()
    device.query_devices.return_value = {"max_input_channels": 1}
    device.InputStream.return_value = stream
    owner = CaptureOwner(device=device, clock=lambda: timer[0])
    return owner, device, stream, timer


def detector_fixture(scores):
    detector = Mock()
    scores = iter(chain(scores, repeat(0.0)))
    frames = []
    def predict(frame):
        frames.append(frame.copy())
        return next(scores)
    detector.predict.side_effect = predict
    return WakeTrigger(detector, threshold=0.5), detector, frames


def test_wake_reframes_without_losing_or_duplicating_immediate_command():
    original = np.linspace(.02, .3, 4800, dtype=np.float32)
    owner, device, stream, _ = device_fixture(np.split(original, 3))
    trigger, detector, frames = detector_fixture([0, 1])
    states = []
    def state(value):
        assert owner.microphone_active
        states.append(value)
    audio = owner.capture_after_wake(Event(), trigger,
        on_standby=lambda: state("standby"), on_listening=lambda: state("listening"))
    # Detection at sample 2560 within the second 1600-sample read: its 640-sample
    # tail plus the next command chunk must occur exactly once in captured audio.
    np.testing.assert_array_equal(np.concatenate(frames), original[:2560])
    np.testing.assert_array_equal(audio[:4800], original)
    assert all(frame.dtype == np.float32 and len(frame) == 1280 for frame in frames)
    assert states == ["standby", "listening"]
    device.InputStream.assert_called_once()
    stream.start.assert_called_once()
    stream.close.assert_called_once()
    detector.reset.assert_called_once()
    detector.close.assert_called_once()
    assert not owner.microphone_active and not owner._leased
    assert owner.ring.size == 0 and not owner.ring._data.any()


def test_standby_preroll_is_bounded_and_old_audio_is_not_forwarded():
    original = np.linspace(.02, .3, 48000, dtype=np.float32)
    owner, _, _, _ = device_fixture(np.split(original, 30))
    trigger, _, _ = detector_fixture([0] * 36 + [1])
    audio = owner.capture_after_wake(Event(), trigger)
    # Hit at sample 47360; entire read through 48000 retained, latest two seconds.
    np.testing.assert_array_equal(audio[:32000], original[-32000:])
    assert len(audio) <= 240000


def test_no_wake_times_out_without_command_capture():
    owner, _, stream, _ = device_fixture([])
    trigger, detector, _ = detector_fixture([])
    listening = Mock()
    assert owner.capture_after_wake(Event(), trigger,
        wake=WakeCaptureSettings(standby_seconds=.3), on_listening=listening) is None
    listening.assert_not_called()
    assert stream.read.call_count == 3
    assert owner.ring.size == 0
    detector.close.assert_called_once()
    stream.close.assert_called_once()


def test_stalled_standby_times_out_and_never_reads():
    owner, _, stream, timer = device_fixture([])
    stream.read_available = 0
    stop = Mock()
    stop.is_set.return_value = False
    stop.wait.side_effect = lambda seconds: timer.__setitem__(0, timer[0] + seconds)
    trigger, detector, _ = detector_fixture([])
    assert owner.capture_after_wake(stop, trigger,
        wake=WakeCaptureSettings(standby_seconds=.1)) is None
    stream.read.assert_not_called()
    detector.predict.assert_not_called()
    stream.close.assert_called_once()


@pytest.mark.parametrize("when", ["before", "read", "predict", "listening"])
def test_cancel_at_each_handoff_boundary_discards_audio(when):
    owner, device, stream, _ = device_fixture([np.ones(1600, dtype=np.float32)])
    trigger, detector, _ = detector_fixture([1])
    stop, listening = Event(), Mock()
    if when == "before":
        stop.set()
    elif when == "read":
        stream.read.side_effect = lambda _: (stop.set() or np.ones(1600, dtype=np.float32), False)
    elif when == "predict":
        detector.predict.side_effect = lambda _: stop.set() or 1.0
    else:
        listening.side_effect = stop.set
    assert owner.capture_after_wake(stop, trigger, on_listening=listening) is None
    assert not owner._leased and not owner.microphone_active and owner.ring.size == 0
    detector.close.assert_called_once()
    if when == "before":
        device.InputStream.assert_not_called()
    else:
        stream.close.assert_called_once()
    if when != "listening":
        listening.assert_not_called()


@pytest.mark.parametrize("failure", ["reset", "predict", "detector_close", "read",
                                     "overflow", "short_read", "stream_close", "callback"])
def test_faults_clear_buffers_close_both_resources_and_sanitize_errors(failure):
    owner, _, stream, _ = device_fixture([])
    trigger, detector, _ = detector_fixture([1])
    callback = Mock()
    error = RuntimeError("private-device-or-model-details")
    if failure in {"reset", "predict"}:
        getattr(detector, failure).side_effect = error
    elif failure == "detector_close":
        detector.close.side_effect = error
    elif failure == "read":
        stream.read.side_effect = error
    elif failure in {"overflow", "short_read"}:
        stream.read.side_effect = None
        stream.read.return_value = (np.zeros(10 if failure == "short_read" else 1600,
                                            dtype=np.float32), failure == "overflow")
    elif failure == "stream_close":
        stream.close.side_effect = error
    else:
        callback.side_effect = error
    with pytest.raises((AudioError, WakeModelError)) as caught:
        owner.capture_after_wake(Event(), trigger, on_standby=callback)
    assert "private-" not in str(caught.value)
    assert not owner._leased and not owner.microphone_active
    assert owner.ring.size == 0 and not owner.ring._data.any()
    detector.close.assert_called_once()
    if failure != "reset":
        stream.close.assert_called_once()


@pytest.mark.parametrize("settings", [{"frame_samples": 0}, {"frame_samples": 16001},
    {"frame_samples": True}, {"standby_seconds": 0}, {"standby_seconds": 301},
    {"standby_seconds": float("nan")}, {"standby_seconds": float("inf")}])
def test_wake_settings_are_bounded(settings):
    with pytest.raises(ValueError):
        WakeCaptureSettings(**settings)


@pytest.mark.parametrize("text,expected", [
    ("IRIS, let's start, open Notepad", "open Notepad"),
    (" Iris. Let’s start! What time is it?", "What time is it?"),
    ("IRIS let's start", ""), ("Iris, let's start.", ""),
    ("open Notepad", ""), ("TV says IRIS let's start, open Notepad", ""),
    ("Iris let's restart open Notepad", ""), ("Iris let's starter", ""),
    ("Iris let us start open Notepad", ""),
])
def test_only_exact_leading_phrase_suffix_can_become_command(text, expected):
    assert wake_command(text) == expected


def test_worker_transcribes_once_only_after_capture_and_detector_close(monkeypatch):
    owner, _, stream, _ = device_fixture([np.ones(1600, dtype=np.float32)])
    trigger, detector, _ = detector_fixture([1])
    monkeypatch.setattr("iris.audio.ears.CaptureOwner", lambda: owner)
    retained = []
    def transcribe(audio, model, stop):
        assert not owner.microphone_active
        stream.close.assert_called_once()
        detector.close.assert_called_once()
        retained.append(audio)
        return "IRIS, let's start, what time is it"
    transcriber = Mock(side_effect=transcribe)
    monkeypatch.setattr("iris.audio.ears.transcribe_audio", transcriber)
    sender = Mock()
    _recognize_after_wake(sender, Event(), "base", lambda: trigger, WakeCaptureSettings())
    assert [c.args[0] for c in sender.send.call_args_list] == [
        ("state", "standby"), ("state", "listening"),
        ("state", "processing"), ("text", "what time is it")]
    transcriber.assert_called_once()
    assert not retained[0].any()
    sender.close.assert_called_once()


@pytest.mark.parametrize("reason", ["no_hit", "bad_model", "cancel"])
def test_worker_never_transcribes_standby_or_opens_for_bad_model(monkeypatch, reason):
    owner, device, _, _ = device_fixture([])
    trigger, _, _ = detector_fixture([])
    monkeypatch.setattr("iris.audio.ears.CaptureOwner", lambda: owner)
    transcriber = Mock()
    monkeypatch.setattr("iris.audio.ears.transcribe_audio", transcriber)
    factory, sender, stop = Mock(return_value=trigger), Mock(), Event()
    if reason == "bad_model":
        factory.side_effect = WakeModelError()
    elif reason == "cancel":
        stop.set()
    _recognize_after_wake(sender, stop, "base", factory, WakeCaptureSettings(standby_seconds=.1))
    transcriber.assert_not_called()
    if reason != "no_hit":
        device.InputStream.assert_not_called()
    if reason == "cancel":
        factory.assert_not_called()
    assert sender.send.call_args.args[0] == (("error", "wake") if reason == "bad_model" else ("empty", ""))
    sender.close.assert_called_once()


def test_wake_and_hotkey_workers_share_parent_lease_and_deadlines():
    entered, release = Event(), Event()
    def runner(target, args, token, **kwargs):
        assert target is _recognize_after_wake
        assert kwargs["state_timeouts"] == {"standby": 11, "listening": 16, "processing": 60}
        assert kwargs["timeout"] == 116
        entered.set()
        assert release.wait(3)
    first, other = Ears("base", runner=runner), Ears("base", runner=Mock())
    thread = Thread(target=lambda: first.listen_for_wake(Mock(), Event(), Mock(),
        settings=WakeCaptureSettings(standby_seconds=10)))
    thread.start()
    try:
        assert entered.wait(2)
        with pytest.raises(AudioError):
            other.listen(Event(), Mock())
        with pytest.raises(AudioError):
            other.listen_for_wake(Mock(), Event(), Mock())
        with pytest.raises(AudioError):
            other.transcribe(np.ones(100, dtype=np.float32), Event(), Mock())
        other._runner.assert_not_called()
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()
    other.listen(Event(), Mock())
    other._runner.assert_called_once()


def test_unreapable_wake_worker_latches_parent_lease(monkeypatch):
    monkeypatch.setattr("iris.audio.ears._capture_lease", Lock())
    ears = Ears("base", runner=Mock(side_effect=AudioError("shutdown")))
    with pytest.raises(AudioError):
        ears.listen_for_wake(Mock(), Event(), Mock())
    assert ears.closed.is_set()
    other = Ears("base", runner=Mock())
    with pytest.raises(AudioError):
        other.listen(Event(), Mock())
    other._runner.assert_not_called()


def test_closed_wake_ears_do_not_launch_worker():
    ears = Ears("base", runner=Mock())
    ears.close()
    assert ears.listen_for_wake(Mock(), Event(), Mock()) is None
    ears._runner.assert_not_called()


def test_wake_command_uses_existing_local_brain_gate_and_audit(tmp_path, monkeypatch):
    from iris.config import Config
    from iris.logs.action_log import ActionLog
    from iris.main import create_brain

    owner, _, stream, _ = device_fixture([np.ones(1600, dtype=np.float32)])
    trigger, _, _ = detector_fixture([1])
    monkeypatch.setattr("iris.audio.ears.CaptureOwner", lambda: owner)
    monkeypatch.setattr("iris.audio.ears.transcribe_audio",
                        Mock(return_value="IRIS, let's start, what time is it"))
    def runner(target, args, token, *, on_state, **kwargs):
        messages, sender = [], Mock()
        sender.send.side_effect = messages.append
        target(sender, token, *args)
        for kind, value in messages:
            if kind == "state":
                on_state(value)
            elif kind == "text":
                return value
        raise AssertionError("Expected a command transcript")
    brain = create_brain(Config(""))
    log = tmp_path / "actions.log"
    brain.registry.action_log = ActionLog(log)
    ears = Ears("base", runner=runner)
    command = ears.listen_for_wake(lambda: trigger, Event(), Mock())
    # A wake hit has no reference to Brain, registry or approvals; the caller
    # explicitly submits the returned command through the existing gated route.
    assert not log.exists()
    assert command == "what time is it"
    assert "Verified" in brain.run(command)
    assert brain.metrics.snapshot()["counts"] == {"local_turns": 1}
    assert 'get_time' in log.read_text(encoding="utf-8")
    stream.close.assert_called_once()
