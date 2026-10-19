# IRIS wake detection: measured training/test scorecard

The owner test contains 104 wake recordings and 60 seconds of background audio.
Scores below measure detection on those recordings, not overall live-assistant reliability.

| Candidate | Test | Detected | Missed | Detection score /100 | False wakes in 60 s |
|---|---|---:|---:|---:|---:|
| LiveKit | Before (smoke) | 71/104 | 33 | 68.3 | 0 |
| LiveKit | Larger model (v2) | 92/104 | 12 | 88.5 | 2 |
| LiveKit | Partial-phrase rejection (v3) | 66/104 | 38 | 63.5 | 2 |
| openWakeWord ONNX | Before (smoke) | 73/104 | 31 | 70.2 | 2 |
| openWakeWord ONNX | Larger model (v2) | 104/104 | 0 | 100.0 | 8 |
| openWakeWord ONNX | Partial-phrase rejection (v3) | 68/104 | 36 | 65.4 | 4 |

## What the scores mean

A detection score of 90 means the model detected 90 of every 100 test utterances on this corpus.
False wakes are reported separately. Combining wake utterances and seconds of background into
one overall accuracy percentage would be misleading.

## Uncertainty and timing

- LiveKit: descriptive 95% detection interval 53.9–72.1%.
  Median first-hit position in saved clips: 2.080 s.
- openWakeWord ONNX: descriptive 95% detection interval 55.8–73.8%.
  Median first-hit position in saved clips: 2.160 s.

Intervals assume independent utterances; repeated same-owner/room recordings can be correlated.
First-hit position starts at the saved clip's beginning, not at phrase end, and is not a live latency benchmark.
A one-minute negative test is too short to establish an all-day false-wake rate.

## Training and evaluation separation

V2 uses 128 synthetic training and 32 validation speech clips per class, separate train/validation
speaker identities and noise, a larger small DNN and 1,800 optimizer steps. The threshold remained 0.5.
V3 uses a medium DNN and adds shifted wrong-speech windows and truncated synthetic wake prefixes
as negatives. This experiment was motivated by v2 synthetic-validation false activations.
Prefix labels use waveform fractions, not manually annotated word boundaries; their correctness
has not been independently reviewed. Synthetic validation was reused for development decisions.
The owner's recordings were neither trained on nor used for threshold tuning. They were hash-checked
against the original frozen corpus. This is a repeat development comparison on the same test set,
not fresh blind acceptance. Original smoke artifacts/results and owner files are preserved.

## Activation decision

Neither development bundle is enabled in normal IRIS. The roadmap requires at least 90% recall,
a representative eight-hour negative test, resource/latency budgets and real Windows session acceptance.
These file-based tests alone cannot establish reliable hands-free wake→command operation.

Machine-readable results: data/wake-training/experiments/{v2,v3}/owner-evaluation.json.
Wall-clock inference timings were affected by concurrent work/interruption and are not resource benchmarks.
