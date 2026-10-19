"""Collect owner-held-out positives on deliberate Enter; never starts with IRIS."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event
from uuid import uuid4
import wave

import numpy as np

from iris.audio.capture import CaptureOwner, mono_samples
from iris.audio.ears import record_audio
from iris.audio.worker import AudioError, run_worker
from iris.audio.wake import PHRASE


def write_wav(path: Path, audio: np.ndarray) -> None:
    samples = mono_samples(audio, limit=240000)
    pcm = np.clip(np.rint(np.clip(samples, -1, 1) * 32768), -32768, 32767).astype("<i2")
    # Exclusive creation protects existing recordings from replacement.
    with path.open("xb") as output:
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm.tobytes())


def _record_sample(sender, cancel, target: str) -> None:
    try:
        audio = record_audio(cancel, on_listening=lambda: sender.send(("state", "listening")))
        if audio is None or cancel.is_set():
            sender.send(("empty", ""))
            return
        write_wav(Path(target), audio)
        audio.fill(0)
        sender.send(("text", "recorded"))
    except AudioError as error:
        sender.send(("error", error.kind))
    except Exception:
        sender.send(("error", "audio"))
    finally:
        sender.close()


def collect(output: Path, count: int, *, prompt=input, runner=run_worker, announce=print) -> int:
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("Choose between 1 and 1000 recordings.")
    output = output.resolve()
    folder = output / "held-out-positive"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = output / "recordings.jsonl"
    stop = Event()
    saved = 0
    conditions = ["normal pace", "slow pace", "soft voice", "normal voice from farther away"]
    announce("Local setup only. WAV audio is saved here for wake evaluation; no upload or transcription.")
    announce("Keep these held-out samples out of training and threshold tuning. Enter q to stop.")
    try:
        for index in range(count):
            condition = conditions[index % len(conditions)]
            answer = prompt(f'{index + 1}/{count}: {condition}. Press Enter, wait for LISTENING, then say "{PHRASE}"; q quits: ')
            if answer.strip().casefold() == "q":
                break
            if answer:
                announce("Skipped; press Enter with no text to record, or q to quit.")
                continue
            path = folder / (uuid4().hex + ".wav")
            try:
                def state(value):
                    if value == "listening":
                        announce("LISTENING — say the phrase now.")
                result = runner(_record_sample, (str(path),), stop, timeout=25,
                                on_state=state, state_timeouts={"listening": 16})
                if result != "recorded" or not path.is_file():
                    announce("No sample saved; rerun to add more recordings.")
                    continue
                with manifest.open("a", encoding="utf-8") as log:
                    log.write(json.dumps({"path": path.relative_to(output).as_posix(),
                        "phrase": PHRASE, "split": "held-out", "condition": condition,
                        "sample_rate": 16000, "recorded_at": datetime.now(timezone.utc).isoformat()}) + "\n")
                saved += 1
                announce("Saved one local held-out sample.")
            except AudioError as error:
                announce(str(error))
                break
    except (KeyboardInterrupt, EOFError):
        stop.set()
    return saved


def _record_negative(sender, cancel, target: str, seconds: int) -> None:
    """Fixed-duration room/background sample, with no VAD dropping silence."""
    owner = CaptureOwner()
    audio = None
    try:
        if not 1 <= seconds <= 15:
            raise AudioError("audio")
        chunks, remaining = [], seconds * 16000
        if not owner.open(cancel):
            sender.send(("empty", ""))
            return
        sender.send(("state", "listening"))
        while remaining and not cancel.is_set():
            count = min(1600, remaining)
            if owner.stream.read_available < count:
                cancel.wait(.02)
                continue
            samples, overflow = owner.stream.read(count)
            samples = mono_samples(samples, limit=count)
            if overflow:
                raise AudioError("audio")
            chunks.append(samples.copy())
            remaining -= len(samples)
        owner.close()
        if cancel.is_set():
            sender.send(("empty", ""))
            return
        audio = np.concatenate(chunks)
        write_wav(Path(target), audio)
        sender.send(("text", "recorded"))
    except AudioError as error:
        sender.send(("error", error.kind))
    except Exception:
        sender.send(("error", "audio"))
    finally:
        if audio is not None:
            audio.fill(0)
        try:
            owner.close()
        finally:
            sender.close()


def collect_negatives(output: Path, seconds: int, *, prompt=input, runner=run_worker, announce=print) -> int:
    if type(seconds) is not int or not 1 <= seconds <= 28800:
        raise ValueError("Choose 1 to 28800 seconds of explicit local negative recording.")
    output = output.resolve()
    folder = output / "held-out-negative"
    folder.mkdir(parents=True, exist_ok=True)
    announce(f"This deliberately records and saves {seconds} seconds of room/media audio locally; no upload/transcription.")
    announce("Avoid the wake phrase. Use representative background sounds. Ctrl+C stops recording.")
    if prompt("Press Enter with no text to start; anything else cancels: "):
        return 0
    remaining, saved, stop = seconds, 0, Event()
    try:
        while remaining:
            duration = min(15, remaining)
            path = folder / (uuid4().hex + ".wav")
            result = runner(_record_negative, (str(path), duration), stop,
                            timeout=duration + 10, state_timeouts={"listening": duration + 3})
            if result != "recorded" or not path.is_file():
                break
            with (output / "negative-recordings.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"path": path.relative_to(output).as_posix(),
                    "split": "held-out-negative", "seconds": duration, "sample_rate": 16000,
                    "label": "owner-specified negative; content not independently validated"}) + "\n")
            remaining -= duration
            saved += duration
            announce(f"Saved {saved}/{seconds} seconds locally.")
    except (KeyboardInterrupt, EOFError):
        stop.set()
    except AudioError as error:
        announce(str(error))
    return saved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Deliberately record local held-out IRIS wake samples.")
    parser.add_argument("--output", type=Path, default=Path("data/wake-dataset"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--negative-seconds", type=int, help="Explicitly record this duration of local negative audio instead of wake positives.")
    args = parser.parse_args(argv)
    try:
        if args.negative_seconds is not None:
            saved = collect_negatives(args.output, args.negative_seconds)
            print(f"Saved {saved} seconds of local negative audio. Independent review/evaluation remains required.")
            return 0
        saved = collect(args.output, args.count)
    except (OSError, ValueError):
        print("Could not prepare the recording folder. Check the output path/count and available disk space.")
        return 1
    print(f"Saved {saved} samples this run. Model training/evaluation and negative audio are still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
