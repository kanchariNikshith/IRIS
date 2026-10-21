"""Compare explicit wake candidates on common local WAVs; never records audio."""
import argparse
import json
import math
from pathlib import Path
from time import perf_counter
import wave
from typing import Callable
import numpy as np

from iris.audio.wake import WakeTrigger
from training.candidates import load_candidate
from training.pipeline import WORK


def recall_interval(hits: int, count: int) -> list[float]:
    """Descriptive Wilson 95% interval under an independent-utterance assumption."""
    if not 0 <= hits <= count or count <= 0:
        raise ValueError("Invalid wake outcome counts.")
    z = 1.96
    p = hits / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count)) / denominator
    margin = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count)) / denominator
    return [max(0., center-margin), min(1., center+margin)]


def wav_frames(path: Path, *, positive: bool):
    with wave.open(str(path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Evaluation audio must be 16 kHz mono PCM16 WAV.")
        consumed = 0
        while payload := source.readframes(1280):
            samples = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.
            actual_samples = len(samples)
            # Flush the last positive frame before its detector is reset. Keep
            # negative tails unpadded so successive files remain continuous.
            if positive and len(samples) < 1280:
                samples = np.pad(samples, (0, 1280 - len(samples)))
            consumed += len(samples)
            yield samples, actual_samples
        # Full window for short positives; no truncation of a long wake phrase.
        while positive and consumed < 32000:
            count = min(1280, 32000 - consumed)
            yield np.zeros(count, dtype=np.float32), 0
            consumed += count


def score_corpus(detector, positives: list[Path], negatives: list[Path], *, threshold=.5,
                 progress: Callable[[int, int], None] | None = None) -> dict:
    if not positives or not negatives:
        raise ValueError("Both positive and negative evaluation audio are required.")
    if set(p.resolve() for p in positives) & set(p.resolve() for p in negatives):
        raise ValueError("A clip cannot be both positive and negative.")
    timer = [0.]
    trigger = WakeTrigger(detector, threshold=threshold, clock=lambda: timer[0])
    hits = false_wakes = negative_samples = predictions = 0
    skipped_positive_frames = 0
    first_hit_times = []
    total_inference = maximum_inference = 0.
    started = perf_counter()
    def prime():
        # Emulate an already-running standby detector for isolated utterances.
        # This synthetic context is explicitly excluded from observed negative hours.
        for _ in range(25):
            detector.predict(np.zeros(1280, dtype=np.float32))
        timer[0] += 2.
    try:
        for positive, files in [(True, positives), (False, negatives)]:
            trigger.reset()
            if not positive:
                prime()
            for index, path in enumerate(files):
                # Preserve streaming state across short negative clips; resetting
                # each one could prevent a two-second detector from ever scoring.
                if positive:
                    trigger.reset()
                    prime()
                detected = False
                clip_seconds = 0.
                for frame, actual_samples in wav_frames(path, positive=positive):
                    clip_seconds += len(frame) / 16000
                    timer[0] += len(frame) / 16000
                    if not positive:
                        negative_samples += actual_samples
                    if positive and detected:
                        # A one-hit trigger is disarmed for the rest of this clip;
                        # timing those no-ops understates actual processing cost.
                        skipped_positive_frames += 1
                        continue
                    before = perf_counter()
                    hit = trigger.predict(frame)
                    elapsed = perf_counter() - before
                    total_inference += elapsed
                    maximum_inference = max(maximum_inference, elapsed)
                    predictions += 1
                    if hit:
                        if positive:
                            if not detected:
                                first_hit_times.append(clip_seconds)
                            detected = True
                        else:
                            false_wakes += 1
                            trigger.reset()
                hits += int(positive and detected)
                if positive and progress is not None:
                    progress(index + 1, len(files))
        hours = negative_samples / 16000 / 3600
        return {"positives": len(positives), "positive_hits": hits,
            "positive_misses": len(positives) - hits, "recall": hits / len(positives),
            "recall_wilson95": recall_interval(hits, len(positives)),
            "interval_assumption": "Descriptive independent-utterance binomial interval; same-owner/room repetitions may be correlated.",
            "median_first_hit_seconds_from_clip_start": float(np.median(first_hit_times)) if first_hit_times else None,
            "p95_first_hit_seconds_from_clip_start": float(np.percentile(first_hit_times, 95)) if first_hit_times else None,
            "timing_limit": "File-based first-hit position, not live wake latency measured from phrase end.",
            "negative_hours": hours, "false_wakes": false_wakes,
            "false_wakes_per_hour": false_wakes / hours if hours else None,
            "threshold": threshold, "mean_frame_ms": 1000 * total_inference / max(1, predictions),
            "prediction_frames": predictions,
            "skipped_after_positive_hit_frames": skipped_positive_frames,
            "processing_timing_policy": "armed trigger calls only; excludes synthetic priming and disarmed positive tails; not a device resource benchmark",
            "max_frame_ms": 1000 * maximum_inference, "evaluation_seconds": perf_counter() - started,
            "release_accepted": False,
            "negative_policy": "continuous concatenation with one initial reset; reset/debounce after hits",
            "context_policy": "two seconds synthetic silence before each positive and before the negative stream; excluded from measured corpus duration",
            "positive_padding_policy": "terminal positive frame padded to 1280 samples, then short clips padded to two seconds; padding is synthetic, never measured negative duration",
            "limits": "Corpus provenance, independent owner tests, idle CPU/RAM/battery and Windows acceptance still required."}
    finally:
        trigger.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Compare both development bundles on synthetic test originals.")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--positives", type=Path)
    parser.add_argument("--negatives", type=Path)
    parser.add_argument("--threshold", type=float, default=.5)
    parser.add_argument("--report", type=Path, default=WORK / "reports/candidate-comparison.json")
    args = parser.parse_args(argv)
    try:
        if args.smoke:
            corpus = WORK / "output/iris_lets_start_smoke"
            positives = sorted((corpus / "positive_test").glob("clip_??????.wav"))
            negatives = sorted((corpus / "negative_test").glob("clip_??????.wav"))
            manifests = [WORK / "bundles" / engine / "manifest.json" for engine in ["livekit", "openwakeword"]]
        else:
            if not all([args.manifest, args.positives, args.negatives]):
                raise ValueError("Specify a model bundle and both corpus folders.")
            positives, negatives = sorted(args.positives.glob("*.wav")), sorted(args.negatives.glob("*.wav"))
            manifests = [args.manifest]
        report = {"corpus": "synthetic_smoke" if args.smoke else "provided_local_audio", "candidates": {}}
        for manifest in manifests:
            engine = json.loads(manifest.read_text(encoding="utf-8"))["engine"]
            detector = load_candidate(manifest, development=args.smoke)
            report["candidates"][engine] = score_corpus(detector, positives, negatives, threshold=args.threshold)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except Exception as error:
        print("Wake evaluation failed (" + type(error).__name__ + "). Check bundle, dependencies and audio formats.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
