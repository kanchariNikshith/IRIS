"""Owned native workers: cancellation can stop blocking audio/ASR drivers."""
import multiprocessing
from time import monotonic
from typing import Any, Callable
from iris.telemetry import runtime_metrics

MESSAGES = {
    "wake": "The local IRIS wake detector isn't ready. You can use the orb or type commands instead.",
    "microphone": "I can't find a microphone. You can type commands instead.",
    "permission": "Microphone access was denied. Check Windows microphone permissions; you can type commands instead.",
    "audio": "I couldn't record from the audio device. Check the default microphone; you can type commands instead.",
    "model": "The local speech model isn't ready. Cache the configured Whisper model; you can type commands instead.",
    "transcription": "I couldn't transcribe that recording. Try again or type the command.",
    "timeout": "Voice processing timed out. Try again or type the command.",
    "speech": "I couldn't speak the response. Please read the text response instead.",
    "shutdown": "An audio worker could not be stopped cleanly.",
}


class AudioError(Exception):
    def __init__(self, kind: str) -> None:
        self.kind = kind if isinstance(kind, str) and kind in MESSAGES else "audio"
        super().__init__(MESSAGES[self.kind])


class StopToken:
    def __init__(self, *events: Any) -> None:
        self.events = events

    def is_set(self) -> bool:
        return any(event.is_set() for event in self.events)

    def wait(self, timeout: float) -> bool:
        deadline = monotonic() + timeout
        while not self.is_set():
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            self.events[0].wait(min(remaining, 0.02))
        return self.is_set()


def reap(process: Any, cancel: Any) -> None:
    cancel.set()
    process.join(timeout=0.5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)
    if process.is_alive():
        raise AudioError("shutdown")
    process.close()


def run_worker(target: Callable[..., None], args: tuple[Any, ...], stop: Any, *,
               timeout: float, on_state: Callable[[str], None] = lambda state: None,
               context: Any = None, clock: Callable[[], float] = monotonic,
               state_timeouts: dict[str, float] | None = None) -> str | None:
    """Only known state/result messages escape, never driver exception text."""
    if stop.is_set():
        return None
    context = context or multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    cancel = context.Event()
    process = context.Process(target=target, args=(sender, cancel, *args), daemon=True)
    started = False
    try:
        process.start()
        started = True
        runtime_metrics.record("workers_started")
        sender.close()
        deadline = clock() + timeout
        phase_deadline = deadline
        while not stop.is_set():
            if clock() >= min(deadline, phase_deadline):
                raise AudioError("timeout")
            if receiver.poll(0.05):
                try:
                    kind, value = receiver.recv()
                except (EOFError, OSError):
                    raise AudioError("audio") from None
                if stop.is_set():
                    return None
                if kind == "state" and value in {"standby", "listening", "processing"}:
                    phase_deadline = min(deadline, clock() + (state_timeouts or {}).get(value, timeout))
                    on_state(value)
                elif kind == "text" and isinstance(value, str):
                    return value
                elif kind in {"done", "empty"}:
                    return ""
                elif kind == "error":
                    raise AudioError(value)
                else:
                    raise AudioError("audio")
            elif not process.is_alive():
                raise AudioError("audio")
        return None
    except AudioError:
        raise
    except Exception:
        raise AudioError("audio") from None
    finally:
        try:
            if started:
                reap(process, cancel)
                runtime_metrics.record("workers_reaped")
            else:
                process.close()
        except AudioError:
            runtime_metrics.record("worker_failures")
            raise
        finally:
            receiver.close()
            sender.close()
