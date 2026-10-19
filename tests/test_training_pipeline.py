import json
import os
from training.pipeline import PHRASE, prepare, smoke_config


def test_smoke_training_cannot_consume_owner_held_out_data():
    data = smoke_config()
    assert data["target_phrases"] == [PHRASE]
    assert data["n_samples"] == 32 and data["steps"] == 100
    assert "wake-dataset" not in json.dumps(data)
    assert data["augmentation"]["background_paths"] == []


def test_prepare_creates_separate_folders_without_recording(tmp_path, monkeypatch):
    monkeypatch.setattr("training.pipeline.os.environ", dict(os.environ))
    monkeypatch.setattr("training.pipeline.ROOT", tmp_path)
    monkeypatch.setattr("training.pipeline.WORK", tmp_path / "data/wake-training")
    config = prepare()
    assert config.exists()
    assert json.loads(config.read_text())["model_name"].endswith("_smoke")
    assert (tmp_path / "data/wake-dataset/held-out-positive").is_dir()
    assert not list(tmp_path.rglob("*.wav"))
