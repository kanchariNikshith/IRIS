# IRIS functionality test report — 19 October 2026

**Verdict: all 439 automated tests passed. The implemented prototype passes its
offline regression suite, but full hands-free operation is not accepted.**
Wake false activations, live device checks, provider availability and Gmail
account acceptance remain open. Test pass rate is not product accuracy or code
coverage.

## Checks executed for this report

| Check | Result | Evidence / limitation |
|---|---|---|
| Full pytest suite | 439 passed, 0 failed, 0 errors, 0 skipped; 76.69 s | `data/test-reports/functional-audit-19oct.xml` |
| Main environment dependencies | PASS | `python -m pip check`: no broken requirements |
| Training environment dependencies | PASS | uv checked 86 packages; all compatible |
| Source compilation | PASS | `python -m compileall -q iris training` |
| Runtime configuration preflight | PASS | `python -m iris.main --check`; keys masked; no service connection established |
| Supported app discovery | 6/6 found | Notepad, Chrome, Edge, Spotify, Word, Excel; paths resolved without launching |
| Audio device inventory | Available | 5 input-capable and 8 output-capable device entries; default input/output assigned; no capture or playback |

Runtime: Windows, Python 3.12.6. Python 3.11 compatibility was not tested.
The training dependency check initially failed to persist its sandbox cache;
rerunning with a workspace-local cache passed. This was an execution-environment
issue, not a dependency incompatibility. No runtime code or settings were changed.

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-audit-19oct --junitxml=data/test-reports/functional-audit-19oct.xml
```

## Functionality coverage

Counts below partition all 439 tests, including parameterized cases. They describe
executed tests, not a claim that every possible behavior is covered.

| Implemented area | Tests passed | Behaviors exercised | Remaining real-world check |
|---|---:|---|---|
| Configuration | 15 | Loading, validation, missing-provider handling, secret masking | Provider/model entitlement and availability |
| Permissions, registry, audit | 30 | Argument validation, unknown-tool rejection, one-use turn-bound approval, expiry, stop, safe errors and log failures | Native emergency hotkey; audit failure after an actual OS action |
| Brain and provider adapters | 84 | OpenAI/Gemini protocol handling, SDK serialization with mocked transport, tool results, eight-call limit, cancellation, retries, duplicate prevention, truthful completion | Actual successful cloud conversation/tool loop; historical Gemini errors remain unconfirmed as resolved |
| Local command routing | 28 | Exact time/app/URL/scroll/key commands, no-provider execution, ambiguity rejection, same gate/audit path | Native app/window results for each command |
| Desktop/browser tools | 75 | URL checks, search encoding, six-app allowlist, new-process verification, bounded scrolling, allowed keys, typing without Enter, cancellation | Actual launch/navigation/focus and typed contents; generic browser/input results remain unverified |
| Capture, ASR/TTS adapters and voice controller | 70 | One microphone owner, ring/frame conversion, endpoint limits, device fault cleanup, local Whisper options, worker cancellation/timeouts, speech queue, busy/pause/stop handling | Real recognition/playback, mic unplug/stall, noise, soft speech and orphan-process checks |
| Orb/UI, GUI registry and text console | 47 | Headless Qt rendering/signals, click versus drag, orb-only startup behavior, duplicate-instance endpoint, thread handoff, confirmation expiry, responsive cleanup, text fallback | Visible Windows rendering, DPI/multiple monitors, focus, transparency, global hotkeys |
| Gmail and Gmail UI | 59 | MIME/address validation, mocked OAuth/storage/HTTP, exact-message GUI review, one-use draft/send, invalidation, ambiguous-send no-retry behavior, threaded UI integration | OAuth client file is currently unset; real consent, DPAPI, refresh, draft/send acceptance pending |
| Telemetry | 1 | Bounded fixed-name counters and no user-content metrics | Idle CPU/RAM/battery measurements |
| Wake preparation/training/evaluation | 30 | Bundle hashes/contracts, development-model rejection, reset/debounce, collectors with mocked capture, dataset separation, synthetic split safeguards, frozen-owner hashes, scoring | Acoustic accuracy and false wakes, independent long-negative test, ambient runtime integration |

## Integration tests versus live end-to-end tests

The suite exercises audio → Ears → VoiceController → real local Brain/registry/
clock/audit → reply → shutdown using a synthetic input device and mocked ASR/TTS.
It also exercises GUI/text/voice → Brain → Gmail preview → exact GUI approval →
mocked HTTP dispatch. Real Qt objects and local IPC are exercised in an offscreen
session. These are integration tests with controlled dependencies, not proof of
live microphone-to-desktop or account-to-email completion.

No live API requests, email sends, desktop typing, new room recording or audio
uploads/transcription were performed for this audit. Device enumeration did not
open a recording stream. Native inventory is saved in
`data/test-reports/native-inventory-19oct.json`.

## Wake model results

The local models were actually trained/exported earlier; unit tests alone do not
measure their accuracy. The frozen owner corpus contains 104 wake utterances and
60 seconds of negative audio. Threshold is fixed at 0.5; owner recordings are
excluded from training and threshold tuning. Repeated evaluation is development
evidence, not a new blind test. See [wake scorecard](WAKE_ACCURACY_REPORT.md).

V2 detected 92/104 (88.5%) with LiveKit and 104/104 (100%) with openWakeWord,
but caused 2 and 8 false wakes respectively in 60 seconds. V3 synthetic validation
detected 32/32 with each engine but caused 8 and 11 false wakes in 78.6 seconds.
These results fail false-activation acceptance. One minute cannot establish an
all-day false-wake rate. Wake remains disabled.

The interrupted v3 owner evaluation was restarted and completed on 19 October:

| Model | Engine | Detected / 104 | Detection score | False wakes / 60 s |
|---|---|---:|---:|---:|
| Original smoke | LiveKit | 71 | 68.3% | 0 |
| Original smoke | openWakeWord | 73 | 70.2% | 2 |
| V2 larger training | LiveKit | 92 | 88.5% | 2 |
| V2 larger training | openWakeWord | 104 | 100% | 8 |
| V3 partial-phrase negatives | LiveKit | 66 | 63.5% | 2 |
| V3 partial-phrase negatives | openWakeWord | 68 | 65.4% | 4 |

V3 regressed on natural owner recall despite detecting all synthetic validation
positives. It is not promoted. V2's 100% detection result is also not acceptable
because of false wakes. No candidate establishes reliable hands-free operation.
The first two runs above are preserved earlier measurements; v3 owner testing
was completed during this audit. Wall-clock timings are not controlled resource
benchmarks. Model/data files and JSON reports stay local under `data/wake-training`.

## Unimplemented and pending work

- Persistent memory storage and memory tools are placeholders, not functional
  features. Permission tests mentioning memory do not implement storage.
- R3 ambient wake-to-command integration and R4 follow-up sessions remain pending.
- R5–R13 general app observation, verified dictation/correction, richer browser
  tasks, trusted voice approval, WhatsApp, reels/feed workflows, reviewed Store
  installs and later reliability work remain planned. Existing limited tools
  must not be treated as completing those milestones.
- Gmail implementation exists, but live account acceptance is incomplete;
  spoken approval does not authorize sending under the current implementation.

## Next acceptance steps

1. Improve wake rejection using separate training/validation data; retain the
   owner corpus for evaluation. Do not enable the current development bundles.
2. Run controlled Windows checks for orb/hotkeys, one-turn capture/transcription/
   playback, pause/kill/device loss and supported desktop actions. Check the actual
   target window and resulting content, not just dispatch success.
3. Verify a live selected-provider response and tool round trip; separately set up
   Gmail OAuth and review the exact recipient/message before any live send.
4. Once a wake candidate passes initial quality checks, run independent positives,
   representative eight-hour negatives and idle CPU/RAM/battery/latency acceptance.

No phase is marked Windows accepted by this report.
