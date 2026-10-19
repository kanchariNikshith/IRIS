"""Package a trained smoke classifier with pinned frontends; never enable it."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

from training.pipeline import WORK, PHRASE, REVISION, ROOT

OPENWAKEWORD_REVISION = "368c03716d1e92591906a84949bc477f3a834455"


def package() -> None:
    from livekit.wakeword.resources import get_mel_model_path, get_embedding_model_path
    classifier = WORK / "output/iris_lets_start_smoke/iris_lets_start_smoke.onnx"
    if not classifier.is_file():
        raise ValueError("Run the synthetic train/export stages first.")
    for engine, revision in [("livekit", REVISION), ("openwakeword", OPENWAKEWORD_REVISION)]:
        folder = WORK / "bundles" / engine
        folder.mkdir(parents=True, exist_ok=True)
        assets = []
        for role, source in [("classifier", classifier), ("melspectrogram", get_mel_model_path()),
                             ("embedding", get_embedding_model_path())]:
            target = folder / source.name
            shutil.copyfile(source, target)
            assets.append({"role": role, "path": target.name, "bytes": target.stat().st_size,
                "sha256": sha256(target.read_bytes()).hexdigest(),
                "license": "development only; model/data redistribution terms pending review",
                "source": "local synthetic training" if role == "classifier" else "pinned livekit-wakeword reference resources"})
        manifest = {"schema_version": 1, "phrase": PHRASE, "sample_rate": 16000,
                    "frame_samples": 1280, "engine": engine, "engine_revision": revision,
                    "development_only": True, "assets": assets}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Packaged two development-only candidate bundles. Neither is enabled in IRIS.")


if __name__ == "__main__":
    package()
