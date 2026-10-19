"""V3: learn to reject partial phrases and shifted streaming speech windows."""
from hashlib import sha256
import json
from pathlib import Path
import random
import shutil
from time import monotonic

import numpy as np
from training.improve import EXPERIMENT as V2, experiment_config, package
from training.pipeline import WORK, prepare

EXPERIMENT = WORK / "experiments/v3"


def negative_windows(audio: np.ndarray, *, positive_source: bool):
    """Every returned window is negative: wrong speech, or an incomplete prefix."""
    if positive_source:
        pieces = [audio[:max(1, int(len(audio) * fraction))] for fraction in [.25, .45, .60]]
    else:
        pieces = [audio]
    for piece in pieces:
        # Different positions avoid learning that only centered negatives are negative.
        for position in [0, 6400, 12800, 19200]:
            output = np.zeros(32000, dtype=np.float32)
            take = min(len(piece), 32000-position)
            output[position:position+take] = piece[:take]
            yield output


def config_dict() -> dict:
    config = experiment_config()
    config.update(model_name="iris_lets_start_v3", output_dir=str(EXPERIMENT / "output"))
    config["model"] = {"model_type": "dnn", "model_size": "medium"}
    config["steps"] = 1500
    return config


def extract_hard_negatives(config) -> None:
    import soundfile as sf
    from onnxruntime import SessionOptions
    from livekit.wakeword.models.feature_extractor import MelSpectrogramFrontend, SpeechEmbedding
    from livekit.wakeword.resources import get_mel_model_path, get_embedding_model_path
    options = SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    mel = MelSpectrogramFrontend(get_mel_model_path(), sess_options=options)
    embedding = SpeechEmbedding(get_embedding_model_path(), sess_options=options)
    source_root = V2 / "output/iris_lets_start_v2"
    target = config.model_output_dir
    target.mkdir(parents=True, exist_ok=True)
    for split in ["train", "test"]:
        for stem in ["positive", "background_noise"]:
            name = f"{stem}_features_{split}.npy"
            shutil.copyfile(source_root / name, target / name)
        output = [np.load(source_root / f"negative_features_{split}.npy")]
        for positive_source, label in [(False, "negative"), (True, "positive")]:
            files = sorted((source_root / f"{label}_{split}").glob("clip_??????.wav"))
            features = []
            for index, file in enumerate(files):
                audio, _ = sf.read(file, dtype="float32")
                for window in negative_windows(audio, positive_source=positive_source):
                    values = embedding.extract_embeddings(mel(window))[0]
                    if values.shape[0] < 16:
                        raise ValueError("Incomplete frozen feature window.")
                    features.append(values[-16:])
                if (index+1) % 32 == 0:
                    print("Hard negatives", split, label, index+1, "/", len(files), flush=True)
            output.append(np.stack(features).astype(np.float32))
        np.save(target / f"negative_features_{split}.npy", np.concatenate(output))
        # Keep raw validation originals available to the same evaluator, not training.
        if split == "test":
            for label in ["positive", "negative", "background"]:
                destination = target / f"{label}_test"
                destination.mkdir(exist_ok=True)
                for source in (source_root / f"{label}_test").glob("clip_??????.wav"):
                    if not (destination/source.name).exists():
                        shutil.copyfile(source, destination/source.name)


def run() -> None:
    prepare()
    EXPERIMENT.mkdir(parents=True, exist_ok=True)
    plan = {"config": config_dict(), "seed": 20261017, "threshold": .5,
            "negative_positions": [0, 6400, 12800, 19200], "incomplete_prefix_fractions": [.25, .45, .6],
            "selection_basis": "v2 synthetic validation false wakes; owner data excluded from fitting/calibration"}
    plan_path = EXPERIMENT / "plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError("V3 plan changed; preserve the existing experiment.")
    plan_path.write_text(json.dumps(plan, indent=2))
    import torch
    random.seed(20261017)
    np.random.seed(20261017)
    torch.manual_seed(20261017)
    torch.set_num_threads(4)
    from livekit.wakeword.config import WakeWordConfig
    from livekit.wakeword.training.trainer import run_train
    from livekit.wakeword.export.onnx import run_export
    config = WakeWordConfig(**config_dict())
    for name, operation in [("features", extract_hard_negatives), ("train", run_train), ("export", run_export),
                            ("package", lambda c: package(c, output_root=EXPERIMENT, training_source="local v3 streaming-hard-negative training"))]:
        receipt = EXPERIMENT / (name + "-completed.json")
        if receipt.exists():
            continue
        print("Starting v3:", name, flush=True)
        started = monotonic()
        operation(config)
        receipt.write_text(json.dumps({"stage": name, "seconds": monotonic()-started,
            "plan_sha256": sha256(plan_path.read_bytes()).hexdigest()}, indent=2))
        print("Completed v3:", name, flush=True)


if __name__ == "__main__":
    run()
