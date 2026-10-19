"""Phase 3 orchestration: one command, one existing Brain invocation."""
from queue import Empty, Queue
import re
from threading import Event, Lock, Thread
from typing import Any, Callable

from iris.audio.ears import Ears
from iris.audio.speaker import Speaker
from iris.audio.worker import AudioError, StopToken
from iris.config import redact

STATES = {"idle", "listening", "processing", "speaking", "error", "paused"}


class VoiceController:
    def __init__(self, brain: Any, model_name: str, *, ears: Any = None, speaker: Any = None,
                 emit: Callable[[str, str], None] = lambda label, text: print(f"{label}: {text}", flush=True)) -> None:
        self.brain = brain
        self.gate = brain.registry.gate
        self.closed = Event()
        self.paused = Event()
        self.busy = Event()
        self._listen_cancel = Event()
        self._lock = Lock()
        self._jobs: Queue[tuple[str, str]] = Queue(maxsize=1)
        self._thread = Thread(target=self._work, name="iris-commands")
        self.emit = emit
        self.state = "idle"
        self.misses = 0
        self.ears = ears or Ears(model_name)
        self.speaker = speaker or Speaker(self.gate.kill_switch)
        self.speaker.on_state = self._state
        self.speaker.on_error = self._error

    def _state(self, state: str) -> None:
        if state in STATES and not self.gate.kill_switch.is_set():
            self.state = state
            self.emit("State", state)

    def start(self) -> None:
        self.speaker.start()
        self._thread.start()
        self._state("idle")

    def _reserve(self, kind: str, text: str = "") -> bool:
        with self._lock:
            if (self.closed.is_set() or self.gate.kill_switch.is_set()
                    or self.busy.is_set() or self.speaker.busy.is_set()
                    or (kind == "listen" and self.paused.is_set())):
                return False
            self._listen_cancel.clear()
            self.busy.set()
            self._jobs.put_nowait((kind, text))
            return True

    def request_listen(self) -> bool:
        # Called on the hotkey thread: no audio, provider or TTS work here.
        return self._reserve("listen")

    @staticmethod
    def _control(text: str) -> str:
        return re.sub(r"^iris[, ]+", "", text.strip().casefold()).strip(" .!?")

    def submit_text(self, text: str) -> bool:
        command = self._control(text)
        if command in {"stop", "quit", "exit"}:
            self.stop()
            self.emit("IRIS", "Stopped.")
            return True
        if command in {"stop listening", "pause listening"} and self.busy.is_set():
            self.paused.set()
            self._listen_cancel.set()
            self.emit("IRIS", "Listening paused. Type start listening to resume.")
            return True
        if not text.strip():
            self.emit("IRIS", "Please type a command.")
            return False
        if not self._reserve("text", text):
            self.emit("IRIS", "I'm busy. Wait until idle before another command.")
            return False
        return True

    def _reply(self, text: str) -> None:
        safe = redact(text, self.brain.secrets)
        self.emit("IRIS", safe)
        if not self.gate.kill_switch.is_set():
            self.speaker.enqueue(safe)

    def _error(self, message: str) -> None:
        self._state("error")
        # Audio messages are fixed; no device/SDK exceptions or raw recordings.
        self.emit("IRIS", message)
        try:
            self.brain.registry.action_log.write("voice", {}, "failed", message)
        except (OSError, ValueError, TypeError):
            pass

    def _work(self) -> None:
        stop = self.gate.kill_switch
        while not stop.is_set() and not self.closed.is_set():
            try:
                kind, text = self._jobs.get(timeout=0.05)
            except Empty:
                continue
            try:
                if stop.is_set():
                    continue
                if kind == "listen":
                    token = StopToken(stop, self.closed, self._listen_cancel)
                    self._state("processing")
                    text = self.ears.listen(token, self._state)
                    if token.is_set() or text is None:
                        continue
                    if not text.strip():
                        self.misses += 1
                        message = "Sorry, I didn't catch that. Please say it again."
                        if self.misses >= 3:
                            message += " Try typing the command instead."
                        self._state("error")
                        self._reply(message)
                        continue
                    self.misses = 0
                    text = redact(text, self.brain.secrets)
                    self.emit("Heard", text)
                command = self._control(text)
                if command in {"stop", "quit", "exit"}:
                    self.stop()
                    self.emit("IRIS", "Stopped.")
                elif command in {"stop listening", "pause listening"}:
                    self.paused.set()
                    self._reply("Listening paused. Type start listening to resume.")
                elif command == "start listening":
                    self.paused.clear()
                    self._reply("Listening enabled. Press the push-to-talk hotkey when ready.")
                else:
                    self._state("processing")
                    reply = self.brain.run(text)
                    if not stop.is_set():
                        self._reply(reply)
            except AudioError as error:
                self._error(str(error))
            except Exception:
                self._error("Voice processing failed. You can type the command instead.")
            finally:
                # Reserve stays latched throughout queued speech and its audio tail.
                while self.speaker.busy.is_set() and not stop.is_set():
                    stop.wait(0.05)
                self._jobs.task_done()
                with self._lock:
                    self.busy.clear()
                self._state("paused" if self.paused.is_set() else "idle")

    def stop(self) -> None:
        self.gate.stop()
        self._listen_cancel.set()

    def close(self) -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        self.stop()
        self.ears.close()
        try:
            self.speaker.close()
        finally:
            try:
                if self._thread.ident is not None:
                    self._thread.join(timeout=6)
                    if self._thread.is_alive():
                        raise AudioError("shutdown")
            finally:
                self.brain.close()


def start_voice_hotkeys(controller: VoiceController, push_to_talk: str, kill: str,
                       listener_factory: Any = None) -> Any:
    if push_to_talk == kill:
        raise ValueError("Push-to-talk and kill hotkeys must differ.")
    if listener_factory is None:
        from pynput.keyboard import GlobalHotKeys
        listener_factory = GlobalHotKeys
    listener = listener_factory({push_to_talk: controller.request_listen, kill: controller.stop})
    try:
        listener.start()
    except Exception:
        listener.stop()
        if listener.ident is not None:
            listener.join(timeout=1)
        raise
    return listener


def read_console_line(stop: Event, *, keyboard: Any = None, write: Any = None) -> str | None:
    """Windows console polling: kill can exit even while waiting for text."""
    if keyboard is None:
        import msvcrt as keyboard
    if write is None:
        import sys
        write = lambda text: (sys.stdout.write(text), sys.stdout.flush())
    write("You: ")
    characters = []
    extended = False
    while not stop.is_set():
        if not keyboard.kbhit():
            stop.wait(0.03)
            continue
        char = keyboard.getwch()
        if extended:
            extended = False
            continue
        if char in {"\x00", "\xe0"}:
            extended = True
        elif char == "\x03":
            raise KeyboardInterrupt
        elif char in {"\x04", "\x1a"}:
            return None
        elif char in {"\r", "\n"}:
            write("\n")
            return "".join(characters)
        elif char == "\b":
            if characters:
                characters.pop()
                write("\b \b")
        elif char.isprintable():
            characters.append(char)
            write(char)
    return None


def voice_console(brain: Any, config: Any, *, controller_factory: Any = VoiceController,
                  listener_factory: Any = None, line_reader: Any = read_console_line) -> None:
    controller = controller_factory(brain, config.whisper_model)
    listener = None
    try:
        controller.start()
        try:
            listener = start_voice_hotkeys(controller, config.push_to_talk_hotkey,
                                           config.kill_switch_hotkey, listener_factory)
        except Exception:
            controller.emit("State", "error")
            controller.emit("IRIS", "Global voice hotkeys are unavailable. You can type commands or quit.")
        print(f"IRIS voice mode. Press {config.push_to_talk_hotkey}, wait for listening, then speak. "
              "Type commands, stop listening, start listening, or quit.", flush=True)
        while not brain.registry.gate.kill_switch.is_set():
            text = line_reader(brain.registry.gate.kill_switch)
            if text is None:
                break
            controller.submit_text(text)
    finally:
        controller.stop()
        try:
            if listener is not None:
                listener.stop()
                listener.join(timeout=1)
        finally:
            controller.close()
