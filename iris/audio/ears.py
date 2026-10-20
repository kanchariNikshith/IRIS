"""Hotkey-triggered 16 kHz capture and local CPU/int8 transcription."""
from threading import Event, Lock
from time import monotonic
from typing import Any, Callable

from iris.audio.worker import AudioError, StopToken, run_worker
from iris.audio.capture import CaptureOwner, RecordingSettings, WakeCaptureSettings, mono_samples
from iris.audio.wake import WakeModelError, WakeTrigger, wake_command

_capture_lease = Lock()


def record_audio(stop: Any, *, settings: RecordingSettings = RecordingSettings(),
                 device: Any = None, clock: Callable[[], float] = monotonic,
                 on_listening: Callable[[], None] = lambda: None) -> Any:
    return CaptureOwner(settings=settings, device=device, clock=clock).capture_command(
        stop, on_listening=on_listening)


def transcribe_audio(audio: Any, model_name: str, stop: Any, *, factory: Any = None) -> str:
    if stop.is_set():
        return ""
    try:
        if factory is None:
            from faster_whisper import WhisperModel
            factory = WhisperModel
        model = factory(model_name, device="cpu", compute_type="int8", local_files_only=True)
    except Exception:
        raise AudioError("model") from None
    try:
        segments, _ = model.transcribe(audio, language="en", beam_size=1,
                                      vad_filter=True, condition_on_previous_text=False)
        words = []
        for segment in segments:
            if stop.is_set():
                return ""
            words.append(segment.text.strip())
        return " ".join(words).strip()
    except Exception:
        raise AudioError("transcription") from None


def _recognize(sender: Any, cancel: Any, model_name: str) -> None:
    try:
        audio = record_audio(cancel, on_listening=lambda: sender.send(("state", "listening")))
        if audio is None or cancel.is_set():
            sender.send(("empty", ""))
            return
        sender.send(("state", "processing"))
        text = transcribe_audio(audio, model_name, cancel)
        sender.send(("text", text))
    except AudioError as error:
        sender.send(("error", error.kind))
    except Exception:
        sender.send(("error", "audio"))
    finally:
        sender.close()


def _transcribe_captured(sender: Any, cancel: Any, model_name: str, audio: Any) -> None:
    """Owner-supplied command audio: never opens another microphone."""
    try:
        if cancel.is_set():
            sender.send(("empty", ""))
            return
        sender.send(("state", "processing"))
        samples = mono_samples(audio, limit=240000)
        sender.send(("text", transcribe_audio(samples, model_name, cancel)))
    except AudioError as error:
        sender.send(("error", error.kind))
    except Exception:
        sender.send(("error", "audio"))
    finally:
        sender.close()


def _recognize_after_wake(sender: Any, cancel: Any, model_name: str,
                          trigger_factory: Callable[[], WakeTrigger],
                          settings: WakeCaptureSettings) -> None:
    """Development integration entrypoint; the model is loaded before mic open."""
    audio = None
    try:
        if cancel.is_set():
            sender.send(("empty", ""))
            return
        try:
            trigger = trigger_factory()
        except Exception:
            raise WakeModelError() from None
        audio = CaptureOwner().capture_after_wake(cancel, trigger, wake=settings,
            on_standby=lambda: sender.send(("state", "standby")),
            on_listening=lambda: sender.send(("state", "listening")))
        if audio is None or cancel.is_set():
            sender.send(("empty", ""))
            return
        sender.send(("state", "processing"))
        text = wake_command(transcribe_audio(audio, model_name, cancel))
        sender.send(("text", "" if cancel.is_set() else text))
    except WakeModelError:
        sender.send(("error", "wake"))
    except AudioError as error:
        sender.send(("error", error.kind))
    except Exception:
        sender.send(("error", "audio"))
    finally:
        if audio is not None:
            audio.fill(0)
        sender.close()


class Ears:
    def __init__(self, model_name: str, *, runner: Any = run_worker) -> None:
        self.model_name = model_name
        self._runner = runner
        self.closed = Event()

    def listen(self, cancel: Any, on_state: Callable[[str], None]) -> str | None:
        if self.closed.is_set():
            return None
        if not _capture_lease.acquire(blocking=False):
            raise AudioError("audio")
        reaped = True
        try:
            return self._runner(_recognize, (self.model_name,), StopToken(cancel, self.closed), timeout=90.0,
                                on_state=on_state, state_timeouts={"listening": 16.0, "processing": 60.0})
        except AudioError as error:
            if error.kind == "shutdown":
                reaped = False
                self.closed.set()
            raise
        finally:
            if reaped:
                _capture_lease.release()

    def transcribe(self, audio: Any, cancel: Any, on_state: Callable[[str], None]) -> str | None:
        """R2 integration contract for a future wake owner; no recording here."""
        token = StopToken(cancel, self.closed)
        if token.is_set():
            return None
        samples = mono_samples(audio, limit=240000).copy()
        if not _capture_lease.acquire(blocking=False):
            samples.fill(0)
            raise AudioError("audio")
        reaped = True
        try:
            return self._runner(_transcribe_captured, (self.model_name, samples), token,
                                timeout=60.0, on_state=on_state,
                                state_timeouts={"processing": 60.0})
        except AudioError as error:
            if error.kind == "shutdown":
                reaped = False
                self.closed.set()
            raise
        finally:
            samples.fill(0)
            if reaped:
                _capture_lease.release()

    def listen_for_wake(self, trigger_factory: Callable[[], WakeTrigger], cancel: Any,
                        on_state: Callable[[str], None], *,
                        settings: WakeCaptureSettings = WakeCaptureSettings()) -> str | None:
        """One bounded development turn; not wired to GUI/startup or auto-rearm.

        Factory must be spawn-picklable and load pinned local assets in the child.
        Production model selection and acceptance are still required before use.
        Uses the same parent lease as hotkey capture and supplied-audio ASR.
        """
        token = StopToken(cancel, self.closed)
        if token.is_set():
            return None
        if not _capture_lease.acquire(blocking=False):
            raise AudioError("audio")
        reaped = True
        try:
            return self._runner(_recognize_after_wake,
                (self.model_name, trigger_factory, settings), token,
                timeout=settings.standby_seconds + 106.0, on_state=on_state,
                state_timeouts={"standby": settings.standby_seconds + 1.0,
                                "listening": 16.0, "processing": 60.0})
        except AudioError as error:
            if error.kind == "shutdown":
                reaped = False
                self.closed.set()
            raise
        finally:
            if reaped:
                _capture_lease.release()

    def close(self) -> None:
        self.closed.set()
