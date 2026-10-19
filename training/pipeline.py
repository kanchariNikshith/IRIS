"""Reproducible local synthetic smoke pipeline, separate from owner acceptance.

Run with .wake-training Python. Never starts a microphone or installs packages.
The small dataset is for validating training/export, not daily wake operation.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from time import monotonic
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "wake-training"
REFERENCE = ROOT / "livekit-wakeword-reference"
REVISION = "fb92cb3641fedceb0bd8442409e14d1224f7fc97"
PHRASE = "IRIS, let's start"
BASE = "https://github.com/livekit/livekit-wakeword/releases/download/v0.1.0/"


def smoke_config() -> dict:
    return {"model_name": "iris_lets_start_smoke", "target_phrases": [PHRASE],
        "n_samples": 32, "n_samples_val": 8, "n_background_samples": 0,
        "n_background_samples_val": 0, "tts_batch_size": 4,
        "data_dir": str(WORK), "output_dir": str(WORK / "output"),
        "tts_backend": "piper_vits", "max_speakers": 16,
        "length_scales": [.75, 1., 1.25], "slerp_weights": [.25, .5, .75],
        "custom_negative_phrases": ["Iris", "let's start", "Iris let's stop", "hi let's start",
            "let's stop", "open notepad", "hello there", "start now"],
        "augmentation": {"clip_duration": 2., "batch_size": 4, "rounds": 1,
                         "background_paths": [], "rir_paths": []},
        "model": {"model_type": "dnn", "model_size": "tiny"},
        "steps": 100, "learning_rate": .001, "max_negative_weight": 10.,
        "target_fp_per_hour": 1., "batch_n_per_class": {"positive": 8,
            "adversarial_negative": 8, "ACAV100M_sample": 0, "background_noise": 0}}


def prepare() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    for folder in ["piper", "cache", "nltk", "output", "reports"]:
        (WORK / folder).mkdir(exist_ok=True)
    for folder in ["held-out-positive", "held-out-negative", "training-positive", "training-negative"]:
        (ROOT / "data" / "wake-dataset" / folder).mkdir(parents=True, exist_ok=True)
    os.environ["NLTK_DATA"] = str(WORK / "nltk")
    os.environ["HF_HOME"] = str(WORK / "cache" / "huggingface")
    os.environ["TORCH_HOME"] = str(WORK / "cache" / "torch")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    espeak = WORK / "tools" / "espeak" / "eSpeak NG"
    os.environ["PATH"] = str(espeak) + os.pathsep + os.environ["PATH"]
    os.environ["ESPEAK_DATA_PATH"] = str(espeak / "espeak-ng-data")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    config_path = WORK / "iris_smoke.json"
    config_path.write_text(json.dumps(smoke_config(), indent=2), encoding="utf-8")
    # JSON is valid YAML and loads through the reference's Pydantic configuration.
    return config_path


def fetch_piper() -> None:
    receipts = []
    for remote, local in [("en-us-libritts-high.state_dict.pt", "en-us-libritts-high.pt"),
                          ("en-us-libritts-high.config.json", "en-us-libritts-high.json")]:
        path = WORK / "piper" / local
        if not path.exists():
            partial = path.with_suffix(path.suffix + ".partial")
            size = 0
            with urlopen(BASE + remote, timeout=60) as response, partial.open("wb") as out:
                while chunk := response.read(1048576):
                    size += len(chunk)
                    if size > 200_000_000:
                        raise ValueError("Training asset exceeds the expected size bound.")
                    out.write(chunk)
            partial.replace(path)
        receipts.append({"path": local, "url": BASE + remote, "bytes": path.stat().st_size,
                         "sha256": sha256(path.read_bytes()).hexdigest(),
                         "purpose": "local synthetic smoke training; release terms review pending"})
    (WORK / "reports" / "piper-assets.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")


def generate(config) -> None:
    from livekit.wakeword.data.tts.piper_backend import PiperVitsBackend
    backend = PiperVitsBackend.from_config(config)
    backend.validate_artifacts()
    for name, phrases, count in [
        ("positive_train", [PHRASE], config.n_samples),
        ("positive_test", [PHRASE], config.n_samples_val),
        ("negative_train", config.custom_negative_phrases, config.n_samples),
        ("negative_test", config.custom_negative_phrases, config.n_samples_val)]:
        folder = config.model_output_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        existing = len(list(folder.glob("clip_??????.wav")))
        if existing < count:
            backend.synthesize_clips(phrases, folder, count, start_index=existing, batch_size=4)
        if len(list(folder.glob("clip_??????.wav"))) < count:
            raise ValueError("Synthetic generation did not produce the requested clip count.")


def run(stage: str) -> None:
    config_path = prepare()
    revision = subprocess.check_output(["git", "-C", str(REFERENCE), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("Training reference revision changed; review before continuing.")
    if stage == "prepare":
        print("Created dataset folders and smoke config. No audio recorded or model trained.")
        return
    if stage == "fetch":
        fetch_piper()
        return
    if not shutil.which("espeak-ng"):
        raise ValueError("The workspace-local eSpeak NG phonemizer is not ready.")
    import torch
    torch.set_num_threads(4)
    from livekit.wakeword.config import load_config
    from livekit.wakeword.data.augment import run_augment
    from livekit.wakeword.data.features import run_extraction
    from livekit.wakeword.training.trainer import run_train
    from livekit.wakeword.export.onnx import run_export
    config = load_config(config_path)
    operations = {"generate": generate, "augment": run_augment, "extract": run_extraction,
                  "train": run_train, "export": run_export}
    for name in (list(operations) if stage == "all" else [stage]):
        started = monotonic()
        print("Starting synthetic smoke stage:", name, flush=True)
        operations[name](config)
        receipt = {"stage": name, "seconds": round(monotonic() - started, 3),
                   "reference_revision": revision, "phrase": PHRASE,
                   "acceptance": "development only; no owner/hardware wake acceptance"}
        (WORK / "reports" / (name + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("Finished synthetic smoke stage:", name, flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "fetch", "generate", "augment", "extract", "train", "export", "all"])
    args = parser.parse_args(argv)
    try:
        run(args.stage)
    except KeyboardInterrupt:
        print("Training interrupted; completed clips/stages are retained for resume.")
        return 1
    except Exception as error:
        # Setup logs may expose the type, never credential-bearing HTTP bodies.
        print("Training stage failed (" + type(error).__name__ + "). Review local prerequisites and stage outputs.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
