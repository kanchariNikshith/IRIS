"""Non-blocking speech queue with cancellable owned SAPI workers."""
from queue import Empty, Full, Queue
import re
import sys
import unicodedata
from threading import Event, Lock, Thread
from typing import Any, Callable

from iris.audio.worker import AudioError, StopToken, run_worker


def spoken_text(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:[-*#]+|\d+\.)\s+", "", text)
    text = re.sub(r"[`*_]", "", text)
    text = "".join(c for c in text if unicodedata.category(c) not in {"So", "Cs"})
    text = " ".join(text.split())
    return " ".join(re.split(r"(?<=[.!?])\s+", text)[:3])[:600] or "The response is available as text."


def _speak(sender: Any, cancel: Any, text: str) -> None:
    engine = None
    com = None
    failed = False
    try:
        if sys.platform == "win32":
            import pythoncom
            com = pythoncom
            com.CoInitialize()
        import pyttsx3
        if not cancel.is_set():
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
    except Exception:
        failed = True
    finally:
        try:
            if engine is not None:
                engine.stop()
        except Exception:
            failed = True
        finally:
            try:
                if com is not None:
                    com.CoUninitialize()
            except Exception:
                failed = True
            try:
                sender.send(("error", "speech") if failed else ("done", ""))
            finally:
                sender.close()


class Speaker:
    def __init__(self, stop: Event, *, runner: Any = run_worker,
                 on_state: Callable[[str], None] = lambda state: None,
                 on_error: Callable[[str], None] = lambda message: None) -> None:
        self.stop = stop
        self.closed = Event()
        self.busy = Event()
        self._queue: Queue[str] = Queue(maxsize=4)
        self._lock = Lock()
        self._runner = runner
        self.on_state, self.on_error = on_state, on_error
        self._thread = Thread(target=self._work, name="iris-speaker")

    def start(self) -> None:
        self._thread.start()

    def enqueue(self, text: str) -> bool:
        with self._lock:
            if self.stop.is_set() or self.closed.is_set():
                return False
            try:
                self._queue.put_nowait(spoken_text(text))
            except Full:
                return False
            self.busy.set()
            return True

    def _work(self) -> None:
        while not self.stop.is_set() and not self.closed.is_set():
            try:
                text = self._queue.get(timeout=0.05)
            except Empty:
                continue
            try:
                self.on_state("speaking")
                token = StopToken(self.stop, self.closed)
                self._runner(_speak, (text,), token, timeout=60.0)
                token.wait(0.3)
            except Exception:
                self.on_error(str(AudioError("speech")))
            finally:
                self._queue.task_done()
                with self._lock:
                    if self._queue.empty():
                        self.busy.clear()
        with self._lock:
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Empty:
                    break
            self.busy.clear()

    def close(self) -> None:
        self.closed.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=6)
            if self._thread.is_alive():
                raise AudioError("shutdown")
