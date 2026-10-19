"""Render measured before/after wake results; never invent an overall score."""
import json
from pathlib import Path
from training.evaluate_wake import recall_interval
from training.improve import EXPERIMENT
from training.pipeline import WORK, ROOT


def build() -> Path:
    before = json.loads((WORK / "reports/owner-first-evaluation.json").read_text())
    v2 = json.loads((EXPERIMENT / "owner-evaluation.json").read_text())
    after = json.loads((WORK / "experiments/v3/owner-evaluation.json").read_text())
    lines = ["# IRIS wake detection: measured training/test scorecard", "",
        "The owner test contains 104 wake recordings and 60 seconds of background audio.",
        "Scores below measure detection on those recordings, not overall live-assistant reliability.", "",
        "| Candidate | Test | Detected | Missed | Detection score /100 | False wakes in 60 s |",
        "|---|---|---:|---:|---:|---:|"]
    for engine, label in [("livekit", "LiveKit"), ("openwakeword", "openWakeWord ONNX")]:
        for run, source in [("Before (smoke)", before), ("Larger model (v2)", v2), ("Partial-phrase rejection (v3)", after)]:
            row = source["candidates"][engine]
            hits, count = row["positive_hits"], row["positives"]
            lines.append(f"| {label} | {run} | {hits}/{count} | {count-hits} | {100*hits/count:.1f} | {row['false_wakes']} |")
    lines += ["", "## What the scores mean", "",
        "A detection score of 90 means the model detected 90 of every 100 test utterances on this corpus.",
        "False wakes are reported separately. Combining wake utterances and seconds of background into",
        "one overall accuracy percentage would be misleading.", "",
        "## Uncertainty and timing", ""]
    for engine, label in [("livekit", "LiveKit"), ("openwakeword", "openWakeWord ONNX")]:
        row = after["candidates"][engine]
        low, high = recall_interval(row["positive_hits"], row["positives"])
        median = row.get("median_first_hit_seconds_from_clip_start")
        lines += [f"- {label}: descriptive 95% detection interval {100*low:.1f}–{100*high:.1f}%.",
            f"  Median first-hit position in saved clips: {median:.3f} s." if median is not None else "  No detected utterances for a first-hit timing estimate."]
    lines += ["", "Intervals assume independent utterances; repeated same-owner/room recordings can be correlated.",
        "First-hit position starts at the saved clip's beginning, not at phrase end, and is not a live latency benchmark.",
        "A one-minute negative test is too short to establish an all-day false-wake rate.", "",
        "## Training and evaluation separation", "",
        "V2 uses 128 synthetic training and 32 validation speech clips per class, separate train/validation",
        "speaker identities and noise, a larger small DNN and 1,800 optimizer steps. The threshold remained 0.5.",
        "V3 uses a medium DNN and adds shifted wrong-speech windows and truncated synthetic wake prefixes",
        "as negatives. This experiment was motivated by v2 synthetic-validation false activations.",
        "Prefix labels use waveform fractions, not manually annotated word boundaries; their correctness",
        "has not been independently reviewed. Synthetic validation was reused for development decisions.",
        "The owner's recordings were neither trained on nor used for threshold tuning. They were hash-checked",
        "against the original frozen corpus. This is a repeat development comparison on the same test set,",
        "not fresh blind acceptance. Original smoke artifacts/results and owner files are preserved.", "",
        "## Activation decision", "",
        "Neither development bundle is enabled in normal IRIS. The roadmap requires at least 90% recall,",
        "a representative eight-hour negative test, resource/latency budgets and real Windows session acceptance.",
        "These file-based tests alone cannot establish reliable hands-free wake→command operation.", "",
        "Machine-readable results: data/wake-training/experiments/{v2,v3}/owner-evaluation.json.",
        "Wall-clock inference timings were affected by concurrent work/interruption and are not resource benchmarks."]
    target = ROOT / "WAKE_ACCURACY_REPORT.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build())
