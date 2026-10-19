"""Single native microphone owner and bounded local audio primitives.

This module runs inside the existing reapable audio worker. It does not start
ambient listening or load a keyword model. Samples are 16 kHz mono float32.
"""
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any, Callable

import numpy as np

from iris.audio.worker import AudioError

_stream_lease = Lock()


@dataclass(frozen=True)
class RecordingSettings:
    sample_rate: int = 16000
    chunk_frames: int = 1600
    silence_seconds: float = 1.2
    start_timeout: float = 5.0
    max_seconds: float = 15.0
    rms_threshold: float = 0.015

    def __post_init__(self) -> None:
        if (self.sample_rate != 16000 or type(self.chunk_frames) is not int
                or not 1 <= self.chunk_frames <= 1600
                or not 0 < self.silence_seconds <= 5
                or not 0 < self.start_timeout <= 15
                or not 0 < self.max_seconds <= 15
                or not 0 < self.rms_threshold <= 1):
            raise ValueError("Invalid bounded recording settings.")


def mono_samples(audio: Any, *, limit: int) -> np.ndarray:
    """Validate before copying; reject multichannel or unbounded external audio."""
    samples = np.asarray(audio)
    if (samples.ndim not in {1, 2} or (samples.ndim == 2 and samples.shape[1] != 1)
            or samples.size > limit or not samples.size
            or samples.dtype.kind != "f" or not np.isfinite(samples).all()):
        raise AudioError("audio")
    return samples.astype(np.float32, copy=False).reshape(-1)


class AudioRing:
    """Fixed allocation, chronological pre-roll; clear overwrites retained audio."""
    def __init__(self, capacity: int = 32000) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 240000:
            raise ValueError("Invalid audio buffer capacity.")
        self._data = np.zeros(capacity, dtype=np.float32)
        self._position = 0
        self.size = 0

    def append(self, audio: Any) -> None:
        samples = mono_samples(audio, limit=240000)[-len(self._data):]
        first = min(len(samples), len(self._data) - self._position)
        self._data[self._position:self._position + first] = samples[:first]
        self._data[:len(samples) - first] = samples[first:]
        self._position = (self._position + len(samples)) % len(self._data)
        self.size = min(len(self._data), self.size + len(samples))

    def snapshot(self) -> np.ndarray:
        start = (self._position - self.size) % len(self._data)
        if start + self.size <= len(self._data):
            return self._data[start:start + self.size].copy()
        return np.concatenate((self._data[start:], self._data[:self._position]))

    def clear(self) -> None:
        self._data.fill(0)
        self._position = self.size = 0


class PCMFrames:
    """Convert arbitrary capture chunks to exact detector frames, no lost tail."""
    def __init__(self, frame_samples: int) -> None:
        if type(frame_samples) is not int or not 1 <= frame_samples <= 16000:
            raise ValueError("Invalid detector frame size.")
        self.frame_samples = frame_samples
        self._pending = np.empty(0, dtype=np.int16)

    def feed(self, audio: Any) -> list[np.ndarray]:
        samples = mono_samples(audio, limit=16000)
        # +1 saturates at 32767 and -1 at -32768, with no integer wraparound.
        pcm = np.clip(np.rint(np.clip(samples, -1, 1) * 32768), -32768, 32767).astype(np.int16)
        combined = np.concatenate((self._pending, pcm))
        count = len(combined) // self.frame_samples
        frames = [combined[i*self.frame_samples:(i+1)*self.frame_samples].copy() for i in range(count)]
        self._pending = combined[count*self.frame_samples:].copy()
        return frames

    def reset(self) -> None:
        self._pending.fill(0)
        self._pending = np.empty(0, dtype=np.int16)


class EnergyVAD:
    """Existing RMS endpoint detector, separate from keyword inference.

    This is a conservative energy detector, not a trained speech/noise model.
    Real-room noise/soft-voice acceptance remains required.
    """
    def __init__(self, threshold: float = 0.015) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("Invalid voice threshold.")
        self.threshold = threshold

    def voiced(self, samples: np.ndarray) -> bool:
        return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) >= self.threshold


class CaptureOwner:
    """Own exactly one stream; all close/error/cancel paths clear pre-roll.

    A parent Ears lease also prevents overlapping capture subprocesses. Native
    calls remain inside run_worker so its watchdog can terminate/reap a hang.
    """
    def __init__(self, *, settings: RecordingSettings = RecordingSettings(),
                 device: Any = None, clock: Callable[[], float] = monotonic,
                 vad: Any = None) -> None:
        self.settings, self.device, self.clock = settings, device, clock
        self.vad = vad or EnergyVAD(settings.rms_threshold)
        self.ring = AudioRing()
        self.stream = None
        self.microphone_active = False
        self._leased = False

    def open(self, stop: Any) -> bool:
        if stop.is_set():
            return False
        if self.stream is not None or not _stream_lease.acquire(blocking=False):
            raise AudioError("audio")
        self._leased = True
        try:
            if self.device is None:
                import sounddevice
                self.device = sounddevice
            try:
                info = self.device.query_devices(kind="input")
            except PermissionError:
                raise AudioError("permission") from None
            except Exception:
                raise AudioError("microphone") from None
            if info.get("max_input_channels", 0) < 1:
                raise AudioError("microphone")
            self.stream = self.device.InputStream(samplerate=16000, channels=1,
                dtype="float32", blocksize=self.settings.chunk_frames)
            self.stream.start()
            self.microphone_active = True
            return True
        except Exception:
            self.close()
            raise

    def capture_command(self, stop: Any, *,
                        on_listening: Callable[[], None] = lambda: None) -> Any:
        s = self.settings
        try:
            if self.stream is None and not self.open(stop):
                return None
            if stop.is_set():
                return None
            on_listening()  # Only after InputStream.start succeeded.
            started = last_voice = self.clock()
            chunks = []
            frames = 0
            voiced = False
            max_frames = int(s.max_seconds * s.sample_rate)
            pre_roll = self.ring.snapshot()[-max_frames:]
            if len(pre_roll):
                chunks.append(pre_roll)
                frames = len(pre_roll)
                voiced = self.vad.voiced(pre_roll)
            while not stop.is_set() and frames < max_frames:
                now = self.clock()
                if (now - started >= s.max_seconds
                        or (not voiced and now - started >= s.start_timeout)
                        or (voiced and now - last_voice >= s.silence_seconds)):
                    break
                if self.stream.read_available < s.chunk_frames:
                    stop.wait(0.02)
                    continue
                data, overflow = self.stream.read(s.chunk_frames)
                if overflow:
                    raise AudioError("audio")
                data = mono_samples(data, limit=s.chunk_frames)[:max_frames - frames]
                frames += len(data)
                chunks.append(data.copy())
                self.ring.append(data)
                if self.vad.voiced(data):
                    voiced = True
                    last_voice = self.clock()
            return np.concatenate(chunks) if voiced and not stop.is_set() else None
        except AudioError:
            raise
        except PermissionError:
            raise AudioError("permission") from None
        except Exception:
            raise AudioError("audio") from None
        finally:
            self.close()

    def close(self) -> None:
        stream, self.stream = self.stream, None
        try:
            if stream is not None:
                try:
                    stream.abort()
                finally:
                    stream.close()
        except Exception:
            raise AudioError("audio") from None
        finally:
            self.microphone_active = False
            self.ring.clear()
            if self._leased:
                self._leased = False
                _stream_lease.release()
