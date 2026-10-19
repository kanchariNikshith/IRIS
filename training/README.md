# R3 custom wake preparation

The local training workflow is separate from the IRIS runtime `.venv`. The
isolated `.wake-training` environment has CPU PyTorch/ONNX training/export tools,
the pinned LiveKit and openWakeWord references, and a workspace-local phonemizer.
`requirements-lock.txt` records the installed versions; CPU torch wheels require
the official `https://download.pytorch.org/whl/cpu` index in addition to PyPI.

## Synthetic pipeline smoke test

Larger local experiments are available as `python -m training.improve` (v2)
and `python -m training.harden` (v3), using the isolated Python above. Both
preserve stage receipts and development-only bundles. V3 adds synthetic
incomplete-phrase and shifted wrong-speech negatives. Owner WAVs are excluded.
Score each frozen candidate with `python -m training.score_experiment validation
--version v3`, then `python -m training.score_experiment owner --version v3`.
The scorer rejects changed owner-file hashes and refuses to overwrite an existing
result. Repeated owner evaluation is a development comparison, not a fresh blind
test. `python -m training.scorecard` renders the saved comparisons into
`WAKE_ACCURACY_REPORT.md`. False wakes and recall must be considered together.

The owner does not need to provide an existing model or folder. The setup command
creates separate training/held-out folders. The smoke pipeline synthesizes the
requested phrase and near-miss negatives using the reference Piper backend, then
augments/extracts features/trains a tiny classifier and exports ONNX. It uses
32 synthetic train clips and 8 synthetic test clips per class, no real room
recording, and no cloud AI. This small run does not meet product acceptance.

```powershell
.\.wake-training\Scripts\python.exe -m training.pipeline prepare
.\.wake-training\Scripts\python.exe -m training.pipeline fetch
.\.wake-training\Scripts\python.exe -u -m training.pipeline all
.\.wake-training\Scripts\python.exe -m training.package_smoke
.\.wake-training\Scripts\python.exe -m training.evaluate_wake --smoke
```

The `all` stage can be resumed; individual generate/augment/extract/train/export
stages are available. Outputs, model asset hashes and stage timings live under
`data/wake-training`. Candidate bundles explicitly carry `development_only` and
fail normal runtime preflight. Nothing enables ambient listening automatically.
Held-out owner recordings are excluded from every synthetic training config.
The comparative evaluator streams common 16 kHz mono PCM16 WAVs through both
candidate adapters; reports never automatically grant release acceptance.

The reference is pinned at `fb92cb3641fedceb0bd8442409e14d1224f7fc97`; it is called
as a library and no upstream source is copied into IRIS. Piper assets use its
fixed v0.1.0 release URLs and have local SHA-256 receipts. eSpeak NG 1.52.0 was
extracted to the workspace rather than installed system-wide; its data directory
is supplied through `ESPEAK_DATA_PATH`. Source: [official eSpeak releases](https://github.com/espeak-ng/espeak-ng/releases/tag/1.52.0).
Model/data redistribution terms and natural owner accuracy remain pending.

## Owner-held-out recordings

Requested phrase: **IRIS, let's start**. A tiny synthetic classifier has now been
trained/exported locally for pipeline verification; no accepted owner-tested
classifier exists. Reference example phrases were not relabelled. Normal IRIS
runtime still performs no automatic model download/fallback.

The initial smoke comparison detected 8/8 synthetic positives with each runtime,
but both produced two false wakes over the same 6.25-second negative stream at
threshold 0.5. This is far too little data for a reliable rate estimate and it
does not meet acceptance. No engine is selected/enabled from these results.

The owner confirmed no model/data folder exists. Create held-out voice samples
using the local setup recorder, from the project root:

```powershell
.\.venv\Scripts\python.exe -m training.collect_wake --count 100
```

It creates `data/wake-dataset/held-out-positive` and a local recordings manifest.
Each Enter deliberately starts a bounded microphone recording; wait for LISTENING,
say the phrase once and stop speaking. Enter `q` to finish early; rerun to add
samples without overwriting earlier files. No cloud/Whisper call is made. Audio
is stored only by this explicit setup tool, never normal IRIS operation. These
samples are held out: training requires separate positives/negatives. The recorder
does not train the model or create the eight-hour negative acceptance corpus.

For a deliberate short negative-audio recording (room/media, without the wake
phrase), use the main runtime Python, which has the microphone dependency:

```powershell
.\.venv\Scripts\python.exe -m training.collect_wake --negative-seconds 60
```

It asks for Enter before recording and saves bounded 15-second WAV segments in
`held-out-negative`; Ctrl+C stops it. It never transcribes or uploads them.
The duration is explicit (maximum 28800 seconds); collect representative varied
audio and review that the wake phrase is absent. A one-minute setup check is not
the eight-hour acceptance run. These held-out files stay out of training.

Training data needs its own varied positives/background/general speech negatives;
the smoke intentionally excluded the large ACAV feature set, so its false-wake
behavior is not a production model result. Increase training only with separately
documented data/terms; preserve the owner-held-out corpus for final evaluation.

1. Use the isolated environment and the pinned reference's training
   instructions: `livekit-wakeword-reference/docs/` and `configs/test.yaml` / `configs/prod.yaml`.
   Preserve the phrase; evaluate slow pronunciation against its inference window.
2. Record provenance/license terms separately for generated training audio,
   natural training audio, background/negative audio, classifier and frontend
   assets. Do not use held-out owner test recordings for training or threshold tuning.
3. Export compatible ONNX classifiers/frontends for both candidate runtimes;
   do not assume the same classifier works unchanged with both frontends.
4. Keep a manifest JSON beside each bundle, schema version 1, phrase exactly
   `IRIS, let's start`, sample_rate 16000, engine `livekit` or `openwakeword`,
   engine_revision a pinned forty-character Git SHA, frame_samples the actual
   input contract. The assets array must contain one each of classifier,
   melspectrogram, embedding; each has role, relative path, bytes, sha256,
   license and source. Preflight with
   `.venv\Scripts\python.exe -m iris.audio.wake path\to\manifest.json`.
   Hash validation alone does not establish acoustic compatibility or license approval.
5. Compare both engines on the same held-out natural owner recordings (minimum
   100 positives, target >=90% recall) and representative eight-hour negative
   audio (initial target: no observed false wakes). Count wake sessions, not
   every above-threshold overlapping frame. Measure latency, CPU/RAM and battery,
   and choose budgets before acceptance. Reset/debounce between sessions.
6. Record the selected engine, precise dependencies, artifacts and results in
   ROADMAP_R3_ACCEPTANCE.md before connecting ambient capture/session transitions.

Required external input: trained custom phrase bundle plus representative held-out
owner recordings/negative audio, or a prepared training-data location and an
explicit recording session to create missing owner samples. No room recording
was started by this implementation run.
