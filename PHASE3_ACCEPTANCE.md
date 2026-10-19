# Phase 3 acceptance record — 13 Oct 2026

Status: **core voice pipeline tested on Windows by the user; remaining edge/safety acceptance pending**. The user explicitly authorized Phase 3 while remaining Phase 2 gaps stay recorded. No microphone capture, Whisper weight download, actual SAPI speech, live voice API call, or browser/hardware action was performed by the agent in this implementation session.

## Phase 2 evidence

User confirmed Hello/time/name reversal; Notepad launch/text dispatch; Instagram opening; and combined Instagram/scroll-to-bottom twice with the handoff. These are reported laptop observations. Bottom used the key path; direct wheel down/up remain unconfirmed. Real Ctrl+Alt+Esc/log checks, the close-tab no-tool refusal, informational prompts triggering unnecessary search/app actions, capability-phrasing false refusals and the offline local-command requirement are still open. Phase 2 was not retroactively marked fully accepted.

## Automated verification

Full offline suite: **262 passed in 16.09s**, Python 3.12.6. Previous Phase 2 baseline was 213 tests; 49 additional cases cover mock capture, silence/timeouts/cancellation/errors, stream closure before ASR, local-only CPU/int8 Whisper and lazy segments, IPC/state deadlines, worker reaping, SAPI/COM lifecycle, queue errors/recovery, speech sanitization, mic exclusion, pause/resume, late transcript discard, cancellable console input/hotkeys, and mocked OpenAI/Gemini Gmail tool loops.

Mocked voice Gmail loops call the actual shared Brain/providers and registry once per requested action. A lying model completion cannot turn browser dispatch into verified page loading. Existing validation/gate/logging/eight-call/retry/no-repeat tests remain passing. Process cleanup operations are mocked; they do not prove that the real microphone/SAPI drivers behave correctly.

All new runtime dependencies were installed into .venv and import-tested without initializing devices/models. pip check reported no broken requirements. --check passed with both API keys masked. The configured provider/model remain Gemini/gemini-3.5-flash-lite, and credentials were untouched. The speech model must still be explicitly cached before first voice use.

## Windows checks to record

Follow README.md Phase 3 setup first. For every row record actual Heard text, state sequence, visible action, spoken wording, log tool/status/count and PASS/FAIL. The Phase 4 request explicitly reports successful real-laptop microphone capture, local Whisper transcription, AI tool execution, Gmail opening and spoken replies. This confirms the core pipeline only; unreported edge/safety/count/status checks remain pending.

| Check | Required observation | Status |
|---|---|---|
| Idle microphone | No stream/listening while idle or paused | Pending |
| Ctrl+Alt+Space | Arms only one recording, listening notice follows stream start | Pending |
| Say Open Gmail | Core recognition/tool execution/Gmail opening reported successful; exact count/log check still needed | Core passed (user report); count/log pending |
| Accurate speech | Spoken response reported successful; truthful verification wording still needs explicit confirmation | Speech passed (user report); wording pending |
| Self-listening prevention | During speech and its tail, hotkey does not open mic or generate a new transcript/action | Pending |
| Silence / no-speech / max duration | Stops at roughly 1.2 s silence, 5 s no speech, 15 s recording; silent input executes no action | Pending |
| Pause / resume | Stop listening closes/pauses voice; typed start listening restores activation | Pending |
| Missing/denied microphone | Fixed actionable error and working typed commands | Pending |
| Audio/model/transcription/TTS failure | Error state; no raw exception text; safe retry or text fallback | Pending |
| Kill in each stage and idle | No late tool/speech; recorder and speaker stop | Pending |
| Quit/restart cleanup | No IRIS audio child processes or listener remain; restart succeeds | Pending |
| OpenAI/Gemini parity | Repeat voice/time/cancellation separately where credentials are available | Pending |

## Implementation limits

This is a Windows console, not the orb/UI. Speech is English; mixed Hindi/Telugu is outside v1. Push-to-talk arms one silence-bounded utterance, not an always-open or wake-word microphone. Busy activations are discarded. The 0.015 RMS threshold/0.3-second playback tail need room/device validation. Local model initialization occurs in a new worker per utterance, so CPU startup latency may exceed the PRD goal; no latency target is claimed. The parent watchdog bounds a hung recording stage at sixteen seconds (normal capture limit fifteen), transcription at sixty seconds, and the whole audio operation at ninety seconds. Speech is bounded at sixty seconds. Shutdown gives a native worker 0.5 seconds to cooperate, then uses terminate/kill and bounded joins.

Transcript text goes to the configured Brain provider; audio stays local and is not written to disk. Paused microphones cannot hear start listening; use the typed command. A busy typed stop listening notice is text-only so it cannot play over live capture. Existing API requests may finish in the background within their timeout, with late tool execution blocked. Already-dispatched actions cannot be undone. Original focused-window/verification and offline-command limitations remain; no Phase 2 routing fixes or Phase 4+ features were added.

Update from Phase 4 request: the user authorized proceeding with the desktop UI and deferring noncritical integration tests. No self-listening, kill-every-stage, error-device, timeout, worker-cleanup or provider-parity check is inferred from core voice success. Original implementation-session observations and unresolved Phase 2 findings are retained.
