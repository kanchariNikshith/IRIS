# R0 baseline — 15 Oct 2026

Status: **automated checks passed**. Native/account acceptance is carried below.
Source base: initial checkout at this workspace; source files were untracked on
entry, so no committed source revision is asserted. See the dated memory entry.

Environment: Windows, Python 3.12.6 in `.venv`; project target Python 3.11 has
not been tested. Existing selected provider Gemini, selected model
`gemini-3.5-flash-lite`, local Whisper `base`; settings/credentials unchanged.
No live provider calls, microphone recordings, email writes or model downloads.

Installed inventory: python-dotenv 1.2.4, jsonschema 4.26.0, openai 3.29.0,
google-genai 2.29.0, numpy 2.5.4, sounddevice 0.5.6, faster-whisper 1.2.1,
pyttsx3 2.99, PySide6 6.12.0, psutil 7.2.2, pywin32 312, google-auth 2.62.0,
google-auth-oauthlib 1.5.0, requests 2.34.2. No dependency installation performed.

## Reproduction and results

- `python -m pip check`: no broken requirements.
- `python -m iris.main --check`: passes, both provider keys masked.
- Initial plain pytest encountered sandbox temporary-directory errors. A local
  `--basetemp` fixed those; Qt's local singleton pipe still required unsandboxed
  execution. These are environment restrictions, not application regressions.
- `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-r0-native`
  outside the sandbox: **359 passed in 33.28s** (358 historical tests plus the
  new telemetry test). Telemetry/audio subset: **33 passed in 1.01s**.
- `pytest.ini` restricts discovery to `tests` and Python path to this project;
  reference clones are not collected or installed as IRIS packages.
- `iris.telemetry` provides bounded thread-safe in-memory counts and most recent
  latency, fixed event names only. Worker start/reap/failure counts are connected;
  R1 connects local/provider turns and actual provider request durations. It
  records no commands, transcripts, email fields, recordings or credentials.

## Carried-forward defects and acceptance ownership

| Finding | Disposition / next owner |
|---|---|
| Cloud-dependent simple commands; question/capability false refusals | R1 implementation/regressions |
| Focus/pointer dependent input, missing content observation | R5–R7/R10; keep `unverified` |
| Orb/drag/DPI/native transparency/global hotkeys | R1/Windows acceptance; synthetic Qt tests alone insufficient |
| Stop at each audio/provider/input/speech stage; device loss; orphan workers | R2/R4/R13 hardware checks; existing offline guards pass |
| Post-action logging can fail after OS dispatch | Keep failed audit result; no rollback promise; R13 reliability |
| PyAutoGUI corner failsafe does not latch the global kill gate | Explicit Ctrl+Alt+Esc remains kill; native check pending |
| Gmail OAuth consent/DPAPI/account refresh/draft/send | R8 account setup and exact-message reviewed test; never inferred from mocks |
| Gemini availability/quota; Python 3.11 runtime | R13/setup verification; no provider/model change |

No unresolved critical cancellation/secret-handling regression was found by the
offline suite. Real account sign-in and independently reviewed live sends remain
owner-dependent; they do not block independent local/audio development.
