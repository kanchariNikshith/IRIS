import json
from training.improve import experiment_config, voice_ids
import numpy as np
from training.harden import negative_windows, config_dict


def test_improved_training_keeps_owner_data_out_and_synthetic_speakers_separate():
    config = experiment_config()
    assert "wake-dataset" not in json.dumps(config)
    assert config["n_samples"] > 32 and config["steps"] > 100
    train = voice_ids(0, 128, 16)
    validation = voice_ids(400000, 32, 904)
    assert train and validation and not train.intersection(validation)


def test_hard_negatives_never_include_complete_positive_source():
    samples = np.ones(16000, dtype=np.float32)
    windows = list(negative_windows(samples, positive_source=True))
    assert len(windows) == 12
    assert all(window.shape == (32000,) for window in windows)
    assert max(np.count_nonzero(window) for window in windows) == 9600
    assert "wake-dataset" not in json.dumps(config_dict())
