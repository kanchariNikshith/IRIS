import json
import wave
from unittest.mock import Mock
import numpy as np
import pytest

from training.collect_wake import collect, collect_negatives, write_wav


def test_collection_requires_explicit_recording_step_and_q_stops(tmp_path):
    runner = Mock()
    assert collect(tmp_path, 100, prompt=lambda _: "q", runner=runner, announce=Mock()) == 0
    runner.assert_not_called()
    assert not (tmp_path / "recordings.jsonl").exists()


def test_collection_writes_wav_and_separate_held_out_manifest(tmp_path):
    def runner(target, args, stop, **kwargs):
        from pathlib import Path
        write_wav(Path(args[0]), np.ones(1600, dtype=np.float32))
        return "recorded"
    assert collect(tmp_path, 2, prompt=lambda _: "", runner=runner, announce=Mock()) == 2
    lines = (tmp_path / "recordings.jsonl").read_text().splitlines()
    assert len(lines) == 2
    data = json.loads(lines[0])
    assert data["split"] == "held-out" and data["phrase"] == "IRIS, let's start"
    with wave.open(str(tmp_path / data["path"]), "rb") as wav:
        assert (wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getnframes()) == (1, 16000, 2, 1600)


def test_existing_recording_cannot_be_overwritten(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        write_wav(path, np.ones(10, dtype=np.float32))
    assert path.read_bytes() == b"existing"


def test_negative_collection_cancels_before_microphone_on_nonempty_answer(tmp_path):
    runner = Mock()
    assert collect_negatives(tmp_path, 60, prompt=lambda _: "cancel", runner=runner, announce=Mock()) == 0
    runner.assert_not_called()


def test_negative_collection_is_segmented_bounded_and_kept_out_of_training(tmp_path):
    durations = []
    def runner(target, args, stop, **kwargs):
        from pathlib import Path
        duration = args[1]
        durations.append(duration)
        write_wav(Path(args[0]), np.zeros(duration * 16000, dtype=np.float32))
        return "recorded"
    assert collect_negatives(tmp_path, 31, prompt=lambda _: "", runner=runner, announce=Mock()) == 31
    assert durations == [15, 15, 1]
    assert len((tmp_path / "negative-recordings.jsonl").read_text().splitlines()) == 3
    assert not (tmp_path / "training-negative").exists()
