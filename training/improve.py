"""R3 v2 experiment: separate synthetic training/validation; never owner fitting."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import shutil
import subprocess
from time import monotonic

from training.pipeline import WORK, REFERENCE, REVISION, PHRASE, prepare

EXPERIMENT = WORK / "experiments/v2"
NEGATIVES = ["Iris", "let's start", "Iris let's stop", "hi let's start", "let us stop",
    "Irish weather", "hey Siri", "hey Iris", "start now", "stop recording", "open notepad",
    "the iris is a flower", "I will start later", "wireless speakers", "please restart",
    "where is the library", "that is interesting", "a fresh start", "turn the lights off",
    "the weather is pleasant", "read the next page", "what time is it", "play some music",
    "I would like a cup of tea", "the meeting starts soon", "this is our last task",
    "we should stop here", "please close the window", "there are stars in the sky",
    "I prefer a quiet room", "can you hear the television", "thank you very much"]


def experiment_config() -> dict:
    return {"model_name": "iris_lets_start_v2", "target_phrases": [PHRASE],
        "data_dir": str(WORK), "output_dir": str(EXPERIMENT / "output"),
        "n_samples": 128, "n_samples_val": 32, "n_background_samples": 32,
        "n_background_samples_val": 16, "tts_backend": "piper_vits", "tts_batch_size": 8,
        "max_speakers": 16, "length_scales": [.7, 1., 1.35],
        "slerp_weights": [.2, .5, .8], "noise_scales": [.667, .98],
        "custom_negative_phrases": NEGATIVES,
        "model": {"model_type": "dnn", "model_size": "small"},
        "augmentation": {"clip_duration": 2., "rounds": 2, "background_paths": [], "rir_paths": []},
        "steps": 1500, "learning_rate": .001, "max_negative_weight": 20.,
        "label_smoothing": .02, "batch_n_per_class": {"positive": 24,
            "adversarial_negative": 24, "ACAV100M_sample": 0, "background_noise": 8}}


def voice_ids(start: int, count: int, speakers: int) -> set[int]:
    return {value for index in range(start, start + count)
            for value in (index // speakers % speakers, index % speakers)}


def make_plan() -> Path:
    prepare()
    EXPERIMENT.mkdir(parents=True, exist_ok=True)
    plan = {"seed": 20261016, "threshold": .5, "config": experiment_config(),
        "train_voice_ids": sorted(voice_ids(0, 128, 16)),
        "validation_voice_ids": sorted(voice_ids(400000, 32, 904)),
        "validation_start": 400000,
        "owner_data_policy": "never used for training, checkpoint selection or threshold tuning",
        "purpose": "development only; no automatic ambient activation"}
    path = EXPERIMENT / "plan.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Experiment plan changed; use a new experiment ID.")
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    config = EXPERIMENT / "config.json"
    config.write_text(json.dumps(plan["config"], indent=2), encoding="utf-8")
    return config


def generate(config) -> None:
    import numpy as np
    from livekit.wakeword.data.tts.piper_backend import PiperVitsBackend
    from training.collect_wake import write_wav
    for split, phrases, count, start, speakers in [
        ("positive_train", [PHRASE], 128, 0, 16),
        ("positive_test", [PHRASE], 32, 400000, 904),
        ("negative_train", NEGATIVES, 128, 0, 16),
        ("negative_test", NEGATIVES, 32, 400000, 904)]:
        folder = config.model_output_dir / split
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted(folder.glob("clip_??????.wav"))
        if len(files) == count:
            continue
        if any(not (folder / f"clip_{index:06d}.wav").is_file() for index in range(start, start + len(files))):
            raise ValueError("Synthetic resume files are not contiguous.")
        local_config = config.model_copy(update={"max_speakers": speakers})
        backend = PiperVitsBackend.from_config(local_config)
        backend.validate_artifacts()
        print(f"Generating {split}: {len(files)}/{count}; separate speaker split", flush=True)
        backend.synthesize_clips(phrases, folder, start + count,
                                 start_index=start + len(files), batch_size=8)
        if len(list(folder.glob("clip_??????.wav"))) != count:
            raise ValueError("Incomplete synthetic split; resume before training.")
    # Independent synthetic noise, not a substitute for real background acceptance.
    for split, count, seed in [("background_train", 32, 1042), ("background_test", 16, 2042)]:
        folder = config.model_output_dir / split
        folder.mkdir(exist_ok=True)
        rng = np.random.default_rng(seed)
        for index in range(count):
            noise = rng.normal(size=32000)
            if index % 2:
                noise = np.convolve(noise, np.ones(12) / 12, mode="same")
            noise = noise / max(1e-8, np.max(np.abs(noise))) * rng.uniform(.003, .08)
            path = folder / f"clip_{index:06d}.wav"
            if not path.exists():
                write_wav(path, noise.astype(np.float32))


def augment(config) -> None:
    from livekit.wakeword.data.augment import AudioAugmentor, _augment_directory
    for split in ["positive_train", "positive_test", "negative_train", "negative_test", "background_train", "background_test"]:
        noise = config.model_output_dir / ("background_train" if split.endswith("train") else "background_test")
        adapter = AudioAugmentor(background_paths=[noise], rir_paths=[])
        for round_index in range(2):
            _augment_directory(config.model_output_dir / split, adapter,
                               is_positive=split.startswith("positive"), round_idx=round_index)


def package(config, *, output_root: Path = EXPERIMENT,
            training_source: str = "local v2 synthetic training") -> None:
    from livekit.wakeword.resources import get_mel_model_path, get_embedding_model_path
    from training.package_smoke import OPENWAKEWORD_REVISION
    classifier = config.model_output_dir / (config.model_name + ".onnx")
    for engine, revision in [("livekit", REVISION), ("openwakeword", OPENWAKEWORD_REVISION)]:
        folder = output_root / "bundles" / engine
        folder.mkdir(parents=True, exist_ok=True)
        assets = []
        for role, source in [("classifier", classifier), ("melspectrogram", get_mel_model_path()), ("embedding", get_embedding_model_path())]:
            target = folder / source.name
            shutil.copyfile(source, target)
            assets.append({"role": role, "path": target.name, "bytes": target.stat().st_size,
                "sha256": sha256(target.read_bytes()).hexdigest(),
                "license": "development only; redistribution terms review pending",
                "source": training_source if role == "classifier" else "pinned reference frontend"})
        (folder / "manifest.json").write_text(json.dumps({"schema_version": 1, "phrase": PHRASE,
            "sample_rate": 16000, "frame_samples": 1280, "engine": engine, "engine_revision": revision,
            "development_only": True, "assets": assets}, indent=2), encoding="utf-8")


def run(stage: str) -> None:
    path = make_plan()
    revision = subprocess.check_output(["git", "-C", str(REFERENCE), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("Reference revision changed.")
    if stage == "prepare":
        print("Frozen v2 plan; owner-held-out recordings excluded.")
        return
    import numpy as np
    import torch
    random.seed(20261016)
    np.random.seed(20261016)
    torch.manual_seed(20261016)
    torch.set_num_threads(4)
    from livekit.wakeword.config import load_config
    from livekit.wakeword.data.features import run_extraction
    from livekit.wakeword.training.trainer import run_train
    from livekit.wakeword.export.onnx import run_export
    config = load_config(path)
    operations = {"generate": generate, "augment": augment, "extract": run_extraction,
                  "train": run_train, "export": run_export, "package": package}
    for name in (list(operations) if stage == "all" else [stage]):
        receipt = EXPERIMENT / (name + "-completed.json")
        if stage == "all" and receipt.exists():
            print("Already completed:", name, flush=True)
            continue
        started = monotonic()
        print("Starting v2 stage:", name, flush=True)
        operations[name](config)
        receipt.write_text(json.dumps({"stage": name, "seconds": monotonic() - started,
            "reference_revision": revision, "plan_sha256": sha256((EXPERIMENT/'plan.json').read_bytes()).hexdigest()}, indent=2))
        print("Completed v2 stage:", name, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "generate", "augment", "extract", "train", "export", "package", "all"])
    run(parser.parse_args().stage)
