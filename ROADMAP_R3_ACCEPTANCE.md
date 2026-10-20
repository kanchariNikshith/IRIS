# R3 custom wake — 15 Oct 2026

Status: **implementing; development candidates fail false-activation acceptance**.
Model improvement and long-run/device measurements remain required. Not Windows accepted.

## Single-stream wake handoff — 20 Oct 2026

Implemented a bounded development integration path: `CaptureOwner.capture_after_wake`
feeds exact float32 detector frames from the existing 100 ms capture chunks, retains
two seconds of pre-roll including the triggering chunk's unconsumed tail, then
continues command endpointing on the same stream. One trigger permits one capture;
it has no Brain, tool or approval callback. Timeout, cancellation, overflow, driver
and detector failures close the stream and detector and clear retained buffers.

`Ears.listen_for_wake` runs this path inside the existing reapable worker and shares
the parent microphone lease with hotkey capture and supplied-audio transcription.
Its explicit factory constructs the detector before microphone opening. Standby is
bounded to 60 seconds by default (maximum 300), with parent watchdogs for standby,
command capture and transcription. An unreapable worker prevents another capture.
This is an internal development API: no GUI/startup setting, continuous rearming,
production engine selection or R4 session behavior is enabled.

Whisper runs once after a hit and after microphone/detector closure. Only the suffix
after a recognized leading `IRIS, let's start` reaches the caller; wake-only or
unclear-prefix transcripts return empty. This conservative boundary can reject
commands when pre-roll clips the phrase or ASR changes it. Natural one-utterance,
slow-phrase and device acceptance must measure this before activation. Recognized
text still needs the ordinary Brain/registry/gate; the keyword is no authorization.

Offline tests cover exact frame/tail preservation, bounded pre-roll, wake/no-wake,
stalled capture, cancellation at each handoff, sanitized detector/driver failures,
cleanup, parent lease exclusion, watchdog/reaping and a mocked wake-to-local-clock
command through the existing audited Brain. Focused audio checks: **107 passed**.
Full working-tree suite: **490 passed in 34.27s**, with Qt local-pipe access;
the restricted run had 489 passes and one GUI singleton pipe failure. Compileall,
pip check and CRLF-aware diff whitespace checks passed. Existing greeting edits
were present before this work and are preserved separately from the R3 commit;
the working-tree test total includes their ten tests. No microphone, provider or
owner recording was used.

The exact staged R3 source was also exported to an isolated local directory,
excluding the earlier greeting edits: **480 passed in 97.56s**. The local JUnit
receipt is `data/r3-staged-results.xml`. After a repeated implementation request
arrived with working files reverted, the R3 files were restored from the index
only after confirming each matched its pre-change baseline; both test copies'
R3 Python files were checked against the index.

All previously measured models remain development-only and fail acceptance.
Next: improve false-wake rejection with independent training/validation data;
then choose a qualifying engine and measure the integrated path on Windows,
including >=100 natural positives, eight hours of negatives and resource budgets.

## Larger training experiments — 17 Oct 2026

V2 trained with 128 synthetic training/32 validation speech clips per class,
disjoint synthetic speaker identities, separate noise splits and 1,800 steps.
V3 added shifted negative speech and truncated synthetic wake prefixes with a
medium DNN, motivated by v2 synthetic-validation false activations. Threshold
stayed 0.5. Waveform-prefix negative labels are heuristic, not word-aligned.

On the reused 32-positive/78.6-second-negative synthetic validation corpus,
both models detected all positives. V2 had 20 false wakes per engine; v3 had
8 (LiveKit) and 11 (openWakeWord). Neither passes acceptance. Owner audio is
excluded from fitting/calibration and checked against its original SHA256
snapshot. Repeated evaluation is development evidence, not blind acceptance.
See [accuracy report](WAKE_ACCURACY_REPORT.md) for owner comparisons.

Owner evaluation completed 19 Oct after the prior run was interrupted: v3
LiveKit 66/104 (63.5%) with 2 false wakes/60 s; openWakeWord 68/104 (65.4%)
with 4 false wakes/60 s. V2 had 92/104 (88.5%) with 2 and 104/104 (100%)
with 8 respectively. V3 regressed on owner recall; neither version is promoted.
The 19 Oct functionality audit reran all 439 tests: passed in 76.69s.

Final full offline regressions: **439 passed in 121.23s**. Training compilation
passed. An earlier concurrent test run was interrupted after a Windows WMI
resource warning; a subsequent 438-test run and the final 439-test run passed.
Wall-clock evaluation timings are not controlled device/resource benchmarks.
No ambient wake integration, microphone capture, audio upload/transcription or
cloud model calls occurred. All models remain development-only and disabled.

Latest owner corpus update, 16 Oct: the additional run saved 17 positives, bringing
the total to **104 positive WAVs**, with **four 15-second negative WAVs (60 s)**.
Header checks and manifest counts match. A hashed first-test corpus snapshot was
saved locally; both development engines are being evaluated at the unchanged
threshold 0.5. No training/threshold tuning used these files. This supersedes the
earlier 87-sample/no-negatives inventory below; phrase labels are owner-provided.

## First owner-held-out result — 16 Oct 2026

Both candidate evaluations completed locally against the same frozen corpus:
104 positive files (307.1 s total) and four negative files (60 s total). The
threshold stayed at 0.5, identical to the earlier synthetic comparison. No
recording was transcribed/uploaded, relabelled, trimmed, deleted or used for
training/tuning. File hashes are in owner-first-corpus.json and aggregate results
in owner-first-evaluation.json under data/wake-training/reports.

| Candidate | Positive hits | Recall | False wakes in 60 s |
|---|---:|---:|---:|
| LiveKit | 71/104 | 68.27% | 0 |
| openWakeWord ONNX | 73/104 | 70.19% | 2 |

**Both fail the proposed >=90% recall target. Neither is enabled or selected.**
Zero observed false wakes in one minute does not establish long-run reliability.
The same documented synthetic context/continuous-negative policy was used;
this is file-based owner evaluation, not live wake→command session acceptance.

No more owner positives are required now; the proposed >=100 count is met.
Next development step: improve training using separate varied positives/general
negatives and separate validation, keeping this held-out corpus out of training
and threshold tuning. Defer the eight-hour negative/resource/native acceptance
until a stronger candidate passes the initial check. Runtime code, model/provider
configuration and recordings are unchanged; no unit suite rerun was needed for
this read-only inference/documentation step (last full suite: 434 passed).

Owner update, 16 Oct: collector transcript and local metadata confirm **87 saved
positive WAVs** (3 first run + 84 second run), all nonempty 16 kHz mono PCM16 with
87 matching manifest rows. No negative recordings exist yet. Header inspection
does not confirm phrase correctness or classifier accuracy. At least 13 further
saved positives remain for the proposed 100-sample target, followed by initial
negative capture and eventual long-duration acceptance. Earlier "owner recordings
unperformed" statements below describe the implementation run, before this update.

Implemented a swappable predict/reset/close protocol, threshold/debounce/one-hit
trigger, and local pinned-bundle preflight with exact requested phrase, runtime
revision, frontend/classifier roles, sizes, hashes, provenance/license fields and
bundle-relative paths. Missing/changed assets fail locally; no model download,
provider fallback, microphone opening or tool/approval dispatch is implemented.
`training/README.md` records setup and evaluation separately from runtime
dependencies. No engine has been selected for normal ambient runtime operation.

16 Oct continuation: owner asked to resume after interruption and confirmed no
existing model/inputs. Prepared `.wake-training` with CPU-only Torch 2.8.0,
Torchaudio 2.8.0, ONNX training/export dependencies and pinned reference libraries.
IRIS `.venv` dependencies/provider/model/credentials remain unchanged. Downloaded
the reference's Piper state_dict/config with hash receipts, and extracted official
eSpeak NG locally. Initial phonemizer crash was resolved with its explicit data
directory. Synthetic smoke generation/training/export is running; no final model
accuracy is asserted from setup alone.

## Actual synthetic end-to-end result — 16 Oct 2026

All five stages completed: generation → augmentation → feature extraction →
CPU training → ONNX export. Generated 32 train and 8 test originals per class,
80 total; augmented training features remain separate from held-out owner audio.
Natural owner audio was not recorded. Synthetic positive originals lasted
0.785–1.445 seconds (40 clips), all shorter than the two-second candidate window.
Training took 54.360 seconds and ONNX export 0.313 seconds, excluding synthesis,
installation and model loading; stage receipts live in data/wake-training/reports.

The explicit common-audio comparison used 8 positive test originals, a continuous
concatenation of 8 negative originals totaling **6.25 seconds**, threshold 0.5,
and two seconds of synthetic silence context before each positive and the
negative stream. Context padding is excluded from observed negative duration.

| Candidate | Positive hits | False wakes in 6.25 s | Mean trigger-frame processing |
|---|---:|---:|---:|
| LiveKit | 8/8 | 2 | 35.67 ms |
| openWakeWord ONNX | 8/8 | 2 | 3.08 ms |

These are development smoke results with a tiny, related synthetic corpus;
frame timing is not end-to-end wake latency or an idle battery/CPU benchmark.
**Both fail acceptance; neither engine is enabled or selected.** The false-wake
sample is too short for a useful generalized hourly estimate. The report marks
release_accepted=false. Development bundles fail normal IRIS preflight as expected.
No compatibility/accuracy equivalence is inferred from using the same frontend
weights. A first evaluator attempt exposed missing positive pre-roll and resets
on short negative files; corrected to emulate standby context and continuous
negative audio, then reran comparison. Frozen source models were not changed.

The isolated uv dependency check passes (86 installed packages); the main IRIS
pip check and compileall also pass. An intermediate full offline run passed
431 tests in 113.49s while evaluation was running. A final run covers the latest
negative collector and evaluation corrections; its result is recorded below.

Final `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-r3-final-16oct`
with Qt local-pipe access: **434 passed in 62.55s**. Main pip check, compileall,
masked --check and training environment dependency check pass. The development
bundle CLI preflight returns a fixed local rejection as intended. No cloud AI
requests, live account actions, natural room recording or everyday ambient mic
monitoring were used. The synthetic classifier is 101,960 bytes; pinned frontend
files are 1,087,958 and 1,326,578 bytes. Model bundles and exact comparison JSON
are stored locally under data/wake-training, excluded from tracked source.

Implemented callable training stages, resumable generation, separate dataset
folders, two candidate adapters, common-WAV evaluation, and development-only
bundle packaging. Normal runtime preflight rejects development bundles. The
new preparation/adapter/evaluator/preflight subset passed **19 tests in 7.69s**.

The explicit setup recorder now supports bounded environmental negatives with a
deliberate Enter before capture, a declared duration and Ctrl+C cancellation.
Both positive and negative owner recordings remain unperformed. No existing
model/folder is required from the owner; setup creates folders and the synthetic
pipeline creates a development model, while independent natural data remains a
human participation requirement.

Inventory found only reference phrase models (`hey_livekit`, `nihao_livekit`) and
reference test WAVs; no custom IRIS classifier or held-out owner corpus. An async
question requested existing local artifact/data paths; the owner confirmed they
have none. Added `training.collect_wake` to create the folder and collect local
held-out positives only on deliberate per-sample Enter. It was tested with
synthetic samples; no real recording started. Do not select another phrase silently.

Required before advancing: custom phrase training/export and frontend compatibility;
common-audio candidate comparison; model/data terms; >=100 held-out owner positives
and eight hours representative negatives; measured latency/resources/battery;
threshold/debounce/reset tuning; capture/session integration and real-device checks.
R4–R13 remain planned in the ordered roadmap. Account boundaries remain pending
in their own acceptance records and Gmail approval remains GUI-only.
