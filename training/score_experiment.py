"""Score frozen development candidates without fitting or changing owner recordings."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from training.candidates import load_candidate
from training.evaluate_wake import score_corpus
from training.improve import EXPERIMENT
from training.pipeline import WORK, ROOT


def frozen_corpus(root: Path, snapshot: Path) -> tuple[list[Path], list[Path]]:
    """Keep comparison paired to the original test data and reject changed bytes."""
    root = root.resolve()
    groups: dict[str, list[Path]] = {"positive": [], "negative": []}
    seen = set()
    for row in json.loads(snapshot.read_text(encoding="utf-8"))["recordings"]:
        relative = Path(row["path"])
        if relative.is_absolute():
            raise ValueError("Corpus paths must be relative.")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path in seen or row["label"] not in groups:
            raise ValueError("Invalid frozen corpus entry.")
        if sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Held-out recording changed since the first evaluation.")
        seen.add(path)
        groups[row["label"]].append(path)
    if not all(groups.values()):
        raise ValueError("Both frozen corpus groups are required.")
    return groups["positive"], groups["negative"]


def run(corpus: str, *, experiment_root: Path = EXPERIMENT,
        model_name: str = "iris_lets_start_v2") -> dict:
    report_path = experiment_root / (corpus + "-evaluation.json")
    if report_path.exists():
        raise ValueError("This experiment/corpus was already scored; preserve its first result.")
    if corpus == "owner":
        snapshot = WORK / "reports/owner-first-corpus.json"
        positives, negatives = frozen_corpus(ROOT / "data/wake-dataset", snapshot)
        fingerprint = sha256(snapshot.read_bytes()).hexdigest()
    else:
        folder = experiment_root / "output" / model_name
        positives = sorted((folder / "positive_test").glob("clip_??????.wav"))
        negatives = (sorted((folder / "negative_test").glob("clip_??????.wav"))
                     + sorted((folder / "background_test").glob("clip_??????.wav")))
        fingerprint = None
    report = {"experiment": experiment_root.name, "corpus": corpus, "owner_snapshot_sha256": fingerprint,
        "threshold_policy": "fixed at 0.5 before training; no owner tuning",
        "repeat_evaluation_limit": "Owner test set was evaluated before; this is a paired development comparison, not new blind acceptance.",
        "candidates": {}}
    for engine in ["livekit", "openwakeword"]:
        manifest = experiment_root / "bundles" / engine / "manifest.json"
        print("Evaluating", engine, "on", corpus, flush=True)
        detector = load_candidate(manifest, development=True)
        def progress(count, total):
            if count % 20 == 0 or count == total:
                print(engine, "positive progress:", count, "/", total, flush=True)
        outcome = score_corpus(detector, positives, negatives, threshold=.5, progress=progress)
        outcome["bundle_manifest_sha256"] = sha256(manifest.read_bytes()).hexdigest()
        report["candidates"][engine] = outcome
        partial = report_path.with_suffix(".partial.json")
        partial.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({engine: outcome}), flush=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", choices=["validation", "owner"])
    parser.add_argument("--version", choices=["v2", "v3"], default="v2")
    args = parser.parse_args()
    run(args.corpus, experiment_root=WORK / "experiments" / args.version,
        model_name="iris_lets_start_" + args.version)
