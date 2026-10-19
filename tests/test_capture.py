"""R2 fault injection and audio-to-local-command integration, no real devices."""
from itertools import chain, repeat
from threading import Event, Lock, Thread
from unittest.mock import Mock

import numpy as np
import pytest

from iris.audio.capture import AudioRing, CaptureOwner, EnergyVAD, PCMFrames, RecordingSettings
from iris.audio.ears import Ears, _transcribe_captured
from iris.audio.voice import VoiceController
from iris.audio.worker import AudioError
from iris.config import Config
from iris.logs.action_log import ActionLog
from iris.main import create_brain


def device_fixture(values):
    timer = [0.0]
    samples = iter(chain(values, repeat(0.0)))
    stream = Mock(read_available=1600)
    def read(frames):
        timer[0] += frames / 16000
        return np.full((frames, 1), next(samples), dtype=np.float32), False
    stream.read.side_effect = read
    device = Mock()
    device.query_devices.return_value = {"max_input_channels": 1}
    device.InputStream.return_value = stream
    return device, stream, lambda: timer[0]


def test_ring_wrap_retains_latest_in_order_and_clears_storage():
    ring = AudioRing(5)
    ring.append(np.arange(3, dtype=np.float32))
    ring.append(np.arange(3, 7, dtype=np.float32))
    np.testing.assert_array_equal(ring.snapshot(), [2, 3, 4, 5, 6])
    ring.append(np.arange(20, dtype=np.float32))
    np.testing.assert_array_equal(ring.snapshot(), [15, 16, 17, 18, 19])
    ring.clear()
    assert ring.size == 0 and len(ring.snapshot()) == 0
    assert not ring._data.any()


def test_detector_frames_preserve_chunk_tail_and_saturate_pcm():
    converter = PCMFrames(1280)
    chunks = [np.linspace(-1, 1, 1600, dtype=np.float32) for _ in range(4)]
    output = [frame for chunk in chunks for frame in converter.feed(chunk)]
    assert len(output) == 5 and all(len(frame) == 1280 for frame in output)
    expected = np.clip(np.rint(np.concatenate(chunks) * 32768), -32768, 32767).astype(np.int16)
    np.testing.assert_array_equal(np.concatenate(output), expected)
    assert output[0][0] == -32768 and output[-1][-1] == 32767
    converter.feed(np.ones(20, dtype=np.float32))
    converter.reset()
    assert len(converter._pending) == 0


@pytest.mark.parametrize("audio", [np.zeros((20, 2)), np.full(20, np.nan),
                                   np.zeros(16001), np.zeros(20, dtype=np.int16)])
def test_invalid_detector_audio_is_refused(audio):
    with pytest.raises(AudioError):
        PCMFrames(1280).feed(audio)


@pytest.mark.parametrize("settings", [{"max_seconds": 16}, {"sample_rate": 48000},
                                      {"chunk_frames": 0}, {"rms_threshold": float("nan")}])
def test_settings_cannot_remove_audio_bounds(settings):
    with pytest.raises(ValueError):
        RecordingSettings(**settings)


def test_one_stream_owner_and_release_after_close():
    device, stream, clock = device_fixture([0.1])
    first, second = CaptureOwner(device=device, clock=clock), CaptureOwner(device=device, clock=clock)
    try:
        assert first.open(Event())
        assert first.microphone_active
        with pytest.raises(AudioError):
            second.open(Event())
        device.InputStream.assert_called_once()
        first.close()
        assert not first.microphone_active
        assert second.open(Event())
    finally:
        first.close()
        second.close()
    assert stream.close.call_count == 2


def test_immediate_command_preroll_is_retained_then_erased():
    device, _, clock = device_fixture([])
    owner = CaptureOwner(device=device, clock=clock)
    pre_roll = np.full(1600, 0.2, dtype=np.float32)
    owner.ring.append(pre_roll)
    result = owner.capture_command(Event())
    np.testing.assert_array_equal(result[:1600], pre_roll)
    assert owner.ring.size == 0 and not owner.ring._data.any()
    assert not owner.microphone_active


@pytest.mark.parametrize("failure", ["read", "overflow", "close", "cancel"])
def test_capture_faults_clear_buffer_and_release_ownership(failure):
    device, stream, clock = device_fixture([0.1])
    owner, stop = CaptureOwner(device=device, clock=clock), Event()
    owner.ring.append(np.ones(10, dtype=np.float32))
    if failure == "read":
        stream.read.side_effect = RuntimeError("private-driver-error")
    elif failure == "overflow":
        stream.read.side_effect = None
        stream.read.return_value = (np.ones((1600, 1), dtype=np.float32), True)
    elif failure == "close":
        stream.close.side_effect = RuntimeError("private-driver-error")
    else:
        stream.read.side_effect = lambda _: (stop.set() or np.ones((1600, 1), dtype=np.float32), False)
    if failure == "cancel":
        assert owner.capture_command(stop) is None
    else:
        with pytest.raises(AudioError) as info:
            owner.capture_command(stop)
        assert "private-driver" not in str(info.value)
    assert not owner.microphone_active and owner.ring.size == 0
    assert not owner.ring._data.any()
    assert not owner._leased
    stream.close.assert_called_once()


def test_energy_endpoint_detector_is_independent_of_keyword_detection():
    vad = EnergyVAD()
    assert not vad.voiced(np.zeros(1600))
    assert vad.voiced(np.full(1600, 0.1))


def test_ears_rejects_overlapping_native_capture_workers():
    entered, release = Event(), Event()
    def runner(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return "time"
    first, second = Ears("base", runner=runner), Ears("base", runner=Mock())
    thread = Thread(target=lambda: first.listen(Event(), Mock()))
    thread.start()
    try:
        assert entered.wait(2)
        with pytest.raises(AudioError):
            second.listen(Event(), Mock())
        second._runner.assert_not_called()
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()
    second.listen(Event(), Mock())
    second._runner.assert_called_once()


def test_supplied_command_audio_transcribes_without_opening_microphone(monkeypatch):
    audio, sender, transcriber = np.ones(1600, dtype=np.float32), Mock(), Mock(return_value="time")
    monkeypatch.setattr("iris.audio.ears.transcribe_audio", transcriber)
    recorder = Mock(side_effect=AssertionError("must not record"))
    monkeypatch.setattr("iris.audio.ears.record_audio", recorder)
    _transcribe_captured(sender, Event(), "base", audio)
    recorder.assert_not_called()
    transcriber.assert_called_once()
    assert sender.send.call_args.args[0] == ("text", "time")
    sender.close.assert_called_once()


def test_ears_supplied_audio_is_bounded_copied_cleared_and_cancelled():
    captured = []
    def runner(target, args, stop, **kwargs):
        captured.append(args[1])
        assert target is _transcribe_captured
        assert kwargs["timeout"] == 60
        return "time"
    ears = Ears("base", runner=runner)
    audio = np.ones(100, dtype=np.float32)
    assert ears.transcribe(audio, Event(), Mock()) == "time"
    assert not captured[0].any() and audio.all()
    with pytest.raises(AudioError):
        ears.transcribe(np.zeros(240001, dtype=np.float32), Event(), Mock())
    ears.close()
    assert ears.transcribe(audio, Event(), Mock()) is None


def test_unreapable_worker_prevents_another_capture_until_runtime_restart(monkeypatch):
    # Keep this intentionally latched lease separate from the rest of the suite.
    monkeypatch.setattr("iris.audio.ears._capture_lease", Lock())
    ears = Ears("base", runner=Mock(side_effect=AudioError("shutdown")))
    with pytest.raises(AudioError, match="could not be stopped"):
        ears.listen(Event(), Mock())
    assert ears.closed.is_set()
    other = Ears("base", runner=Mock())
    with pytest.raises(AudioError):
        other.listen(Event(), Mock())
    other._runner.assert_not_called()


def test_audio_to_local_brain_reply_and_shutdown_end_to_end(tmp_path, monkeypatch):
    device, stream, clock = device_fixture([0.1])
    owners = []
    def record(stop, **kwargs):
        owner = CaptureOwner(device=device, clock=clock)
        owners.append(owner)
        return owner.capture_command(stop, **kwargs)
    def transcribe(*args):
        assert not owners[-1].microphone_active
        return "what time is it"
    monkeypatch.setattr("iris.audio.ears.record_audio", record)
    monkeypatch.setattr("iris.audio.ears.transcribe_audio", transcribe)
    def runner(target, args, stop, *, on_state, **kwargs):
        messages = []
        sender = Mock()
        sender.send.side_effect = lambda value: messages.append(value)
        target(sender, stop, *args)
        result = ""
        for kind, value in messages:
            if kind == "state":
                on_state(value)
            elif kind == "text":
                result = value
        return result
    brain = create_brain(Config(""))
    brain.registry.action_log = ActionLog(tmp_path / "actions.log")
    speaker = Mock()
    speaker.busy = Event()
    replied = Event()
    events = []
    def emit(label, text):
        events.append((label, text))
        if label == "IRIS":
            replied.set()
    controller = VoiceController(brain, "base", ears=Ears("base", runner=runner), speaker=speaker, emit=emit)
    controller.start()
    try:
        assert controller.request_listen()
        assert replied.wait(3)
        assert any(label == "IRIS" and "Verified" in text for label, text in events)
        assert brain.metrics.snapshot()["counts"] == {"local_turns": 1}
        assert ('Heard', 'what time is it') in events
        assert stream.start.call_count == 1 and stream.close.call_count == 1
    finally:
        controller.close()
    assert not controller._thread.is_alive()
    assert controller.ears.closed.is_set() and brain.registry.gate.kill_switch.is_set()
