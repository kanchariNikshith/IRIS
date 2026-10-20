# Architecture: IRIS

## Active R1 runtime update — 15 Oct 2026

R3 handoff (20 Oct): `CaptureOwner.capture_after_wake` now feeds exact detector
frames and transitions to command capture on the same stream, retaining bounded
pre-roll and the triggering chunk's tail. `Ears.listen_for_wake` is a bounded
development entrypoint inside the existing owned worker, with shared capture
lease, standby watchdog and local ASR only after wake and microphone closure.
It returns only the command after an explicit leading wake phrase; unclear/wake-only
transcripts return empty. No GUI/startup activation or continuous rearm is wired;
current models still fail acceptance. Detector factories are explicitly injected
for integration testing; production engine selection/asset loading remains pending.

R3 development (16 Oct): training/pipeline.py owns an isolated CPU synthetic
training/export workflow, and candidate/evaluation modules compare LiveKit
overlapping windows with openWakeWord ONNX streaming on common WAVs. These are
setup tools, disconnected from ordinary runtime listening. Packaged smoke bundles
carry development_only=true and fail normal wake preflight. The current tiny
model has false wakes and no engine is selected for ambient use. Dataset capture
requires explicit per-sample Enter (positives) or declared-duration Enter
(negatives); only these deliberate setup tools save WAVs, never normal IRIS.

R2 adds `iris.audio.capture`: CaptureOwner is the sole stream opener inside the
reapable native worker, with a process-local stream lease and parent Ears lease.
AudioRing bounds/clears pre-roll; PCMFrames preserves tails and saturates int16
conversion. `Ears.transcribe` accepts already-owned command audio without opening
another stream. RMS endpointing remains explicitly EnergyVAD; no trained keyword
model or continuous Whisper inference is enabled. Full R2 offline suite: 405 pass.

The main factory enables `iris.brain.local` before provider dispatch, inside the
existing Brain lock. Exact single actions execute via ToolRegistry with a fresh
turn ID and preserve audit/permission/result handling. Protocol-level Brain
construction keeps the previous model-only default. Missing cloud configuration
uses UnconfiguredProvider without SDK creation, while local tools remain usable.
Fixed-name RAM telemetry tracks local/provider turns, request latency/counts and
owned worker start/reap failures; no user content is retained in metrics.
GUI startup/instance recovery show the orb only; click listens and the menu opens
chat/setup. Requested email review opens its window and retains all invalidation.
See ROADMAP_R0_ACCEPTANCE.md and ROADMAP_R1_ACCEPTANCE.md for evidence and limits.

> The following prototype notes are historical where they conflict with the active update above.

> Active implementation sequence: [phase.md](phase.md), roadmap R0–R13 (15 Oct 2026). The former Phase 1–7 plan is [archived](PHASES_LEGACY.md); earlier numbered phases below describe prototype history.

> Direction updated 15 Oct 2026: [IRIS_VISION.md](IRIS_VISION.md) defines the current target and missing architectural components. This document describes existing implementation and older plans; main-window startup and GUI-only review are current behavior, not the final hands-free experience.

Current Phase 4/5 request (13 Oct 2026) restores main-window startup and orb
click-to-open. The rotating cyan HUD orb retains its existing geometry/controls;
Mic/global push-to-talk uses the same VoiceController and Brain. Gmail is now
official OAuth/REST, replacing the older browser-draft design.

gmail.py owns minimum gmail.compose scope, loopback/PKCE desktop consent in an
owned cancellable subprocess, current-user DPAPI tokens outside the checkout,
bounded refresh and fixed-endpoint REST writes with retries/redirects disabled.
No inbox-reading endpoint is used. tools/email.py owns one serial Gmail worker
and immutable EmailSnapshot objects. Model-visible draft_email creates a local
preview. Registry Tool.exposed=False hides send_email/save_email_draft from model
schemas; both still require Permission.CONFIRM and private GUI-created operations.
No GUI/model path bypasses registry/gate/logging. Only a GUI button creates a write
job; default model confirmation callbacks deny Gmail writes. Original request/turn
IDs and expiry bind approval to the snapshot. Edits/cancel/hide/kill invalidate it;
snapshots are consumed before HTTP dispatch, including ambiguous outcomes.

ui/gmail.py provides an editable review panel and read-only exact-email approval.
UiBridge.email carries queued snapshots/status/results from the worker. GUI widgets
are never updated by backend threads. Manual preview preparation also uses registry
dispatch on the Gmail worker. Writes/connection/cleanup stay off Qt; OAuth subprocess
is reaped on cancellation. Successful Gmail message ID confirms submission only;
no API result proves recipient delivery. Logs omit all private email fields.
GUI close/exit owns Gmail worker/http cleanup alongside existing voice ownership.

## 1. Flow

```
 You speak ("Iris, open Instagram")
        |
        v
 [Ears]  microphone -> faster-whisper (local) -> text
        |
        v
 [Brain] selected AI provider with tool calling (OpenAI default, Gemini optional)
        |   sees: your sentence, last 10 messages, relevant memories, time
        |   may only call tools from the tool list
        v
 [Permission gate]  auto -> run   |   confirm -> ask you first   |   unknown -> refuse
        |
        v
 [Tools]  browser, apps, scroll/keys, email, memory
        |
        v
 [Verifier]  verified | unverified | failed
        |
        +--> [Action log]  data/actions.log
        |
        v
 [Voice out]  pyttsx3 speaks the reply (microphone muted while speaking)
        |
        v
 [UI]  orb color + main window log
```

The Brain loops: model asks for a tool, the gate and tool run, the result goes back to the model, and this repeats up to 8 times. Then the model writes the final reply.

## 2. Folder structure

```
iris/
  main.py                 start everything
  config.py               load .env, check settings
  audio/
    ears.py               record from the mic, transcribe with faster-whisper
    speaker.py            speak replies with pyttsx3, mute mic while speaking
  brain/
    brain.py              shared provider-independent tool-calling loop
    providers.py          model-only OpenAI/Gemini adapters and native turn history
    prompts.py            system prompt text
  tools/
    registry.py           tool list, argument checks, permission levels
    browser.py            open_url, web_search
    apps.py               open_app
    input.py              scroll, press_keys, type_text
    email.py              draft_email, send_email
    memory_tools.py       remember, search_memory, update_memory, forget
  security/
    permissions.py        auto / confirm rules, confirmation queue, kill switch
  memory/
    store.py              Mem0 + Qdrant wrapper with read-back checks
  logs/
    action_log.py         write the action log
  ui/
    theme.py              colors and fonts (see design.md)
    orb.py                floating orb
    window.py             main window
tests/                    pytest tests (no real key, mic, or browser needed)
data/                     created at runtime: qdrant/, actions.log, contacts.json
PRD.md  Architecture.md  Rules.md  phase.md  design.md  memory.md
AGENTS.md  CODEX_PROMPT.md  requirements.txt  .env.example
```

## 3. Tech stack

| Part | Choice | Why |
|---|---|---|
| Language | Python 3.11 | One language for AI, audio, and automation. |
| AI reasoning and tool calling | OpenAI Responses (`openai`), optional Gemini GenerateContent (`google-genai`) | OpenAI is the default; AI_PROVIDER=gemini selects Gemini explicitly. Both use the same local safety boundary. |
| Embeddings for memory | OpenAI embeddings through Mem0 | Same key, one provider. |
| Speech to text | faster-whisper, local | No audio leaves the laptop, works well for accents. |
| Microphone | sounddevice + numpy | Simple recording with silence detection. |
| Spoken replies | pyttsx3 (Windows SAPI5) | Offline and instant. |
| Floating orb and window | PySide6 | Frameless, transparent, always-on-top windows with smooth drawing. |
| Open sites and apps | `webbrowser`, `os.startfile`, Start menu fallback | Reliable on Windows. |
| Scroll, keys, typing | pyautogui (failsafe on) | Controls the focused window. |
| Global hotkeys | pynput | Push-to-talk and kill switch. |
| Memory | mem0ai + local Qdrant in `data/qdrant` | Persistent and private. |
| Tests | pytest with mocks | No real key or hardware needed. |

## 4. Components

**Ears (Phase 3).** Ctrl+Alt+Space arms one 16 kHz mono sounddevice recording. A worker process stops after 1.2 seconds of silence, five seconds without speech or fifteen seconds total, then closes the microphone before local faster-whisper CPU/int8 English transcription with VAD. Model weights must be cached explicitly; runtime is local-files-only. Audio is not saved or sent to providers. Capture/transcription is bounded to ninety seconds including initialization and cancellation reaps the child. The mic is closed whenever IRIS is not listening. Phase 4 Mic clicks share voice activation; wake words remain a later phase.

**Brain.** Builds each request from the system prompt, the last 10 messages, the top 5 memories that match the request (when Phase 6 is implemented), and the current date and time. Calls the selected provider with tool schemas. Stops after 8 tool-call attempts per command, including invalid and unknown calls. Executes returned batches serially and rejects duplicate call IDs. The final request disables tool calling; any calls still returned are not executed.

**Provider adapters.** providers.py supplies normalized ToolCall/ModelReply/ProviderError types and a per-command native turn. OpenAI uses Responses with store=False; Gemini uses client.models.generate_content with client-owned Content/Part history. Gemini's automatic function calling is disabled: adapters receive schemas, never tool functions. Declarations use parameters_json_schema to preserve registry constraints. The shared Brain owns validation/dispatch, permissions, cancellation, action logging and honest summaries. Complete native model content (including thought signatures) and matched function responses are replayed within a turn; native history is never transferred across providers. Gemini 2.5 may omit function IDs: local IDs correlate Brain calls, while responses preserve provided native IDs or omit absent ones. The legacy Brain(client, model, registry, ...) constructor still wraps OpenAI by default. SDK retries are disabled; Brain retries transient provider failures at most once after two seconds. Fatal Gemini request/authentication/permission/not-found failures are not retried. HTTP requests have a 20-second timeout; cancellation discards late responses without executing tools. No automatic provider or model fallback.

**Provider diagnostics.** Errors expose only an allowlisted category/provider and numeric HTTP status plus fixed actionable guidance. Distinguish request (400), authentication (401 or allowlisted API_KEY_INVALID ErrorInfo), permission (403), model/endpoint not found (404), quota (429), service unavailable (5xx), transport and timeout. SDK message bodies, headers, credential fields and sensitive request contents are not printed or logged. Gemini SDK 2.29.0 GenerateContent honors HttpRetryOptions(attempts=1), with no Interactions-internal retry override required.

**Tool registry.** Each tool has a name, a schema for its arguments, a permission level, and a function that returns a result. Arguments are validated before anything runs.

| Tool | Permission | Check |
|---|---|---|
| `open_url` | auto | Page opens; URL host matches when possible. |
| `web_search` | auto | Results page opens. |
| `open_app` | auto | A matching process appears within 8 seconds. |
| `scroll` | auto | Reported as "sent to the focused window" (cannot be checked further). |
| `press_keys` (allowlist only) | auto | Same as scroll. |
| `type_text` (max 500 characters, never presses Enter) | auto | Same as scroll. |
| `draft_email` | auto | Gmail compose page opened with the fields. |
| `send_email` | **confirm, every time** | Reported as unverified. User is told to check Sent. |
| `remember` | auto, only when the user asked | Read back from memory. |
| `update_memory` | auto, only when the user asked | Read back, old value kept in history. |
| `forget` | **confirm** | Read back shows it is gone. |
| `search_memory` | auto | Read-only. |
| `get_time` | auto | Read-only. |

**Permission gate.** Runs before every tool, in code, not in the prompt. `auto` runs. `confirm` speaks and shows a question and waits up to 30 seconds. No answer means cancel. A tool that is not in the registry is refused.

**Verifier.** Every tool returns `verified`, `unverified`, or `failed` plus a plain message. The Brain may only say "done" for `verified`.

**No-tool replies.** Action requests with no tool results receive a fixed refusal. A conservative English guard permits ordinary question/greeting replies and rejects completion claims without evidence. Ambiguous requests fail safely; this may refuse some legitimate phrasing. Neither provider's prose can upgrade an actual tool result. Browser and focused-window actions remain unverified because this phase cannot inspect their effects.

**Memory.** Mem0 with the OpenAI provider and local Qdrant. Writes happen only on an explicit request. Every write is read back before IRIS says it saved anything. Updates keep the previous text in history.

**Voice out (Phase 3).** A non-blocking bounded queue and speaker thread run pyttsx3/SAPI in an owned spawned subprocess. A busy flag covers queued playback and its 0.3-second tail. The controller reserves the whole capture/transcription/Brain/speech turn so no microphone stream opens during speech. Driver hangs can be terminated and reaped without blocking the control thread.

**UI.** PySide6. The orb and window run on the main thread. Audio, brain, and tools run on worker threads and talk to the UI through signals.

## 5. Threads

- GUI main thread in Phase 4: QApplication event loop and all widgets. The existing voice console still uses Windows keyboard polling when --gui is omitted.
- Command worker: one queued voice or typed command, managed audio/ASR subprocess, then the existing Brain.run.
- Speaker thread: non-blocking queue, managed SAPI subprocess and playback tail.
- Hotkey listener thread: pynput callbacks only reserve a voice turn or latch cancellation.
- Owned native subprocesses are cooperatively closed or terminated/killed/joined on cancellation; none are intentionally left running.

## 6. Data and files

- `.env`: `AI_PROVIDER` (defaults to openai), `OPENAI_API_KEY`/`OPENAI_MODEL`, `GEMINI_API_KEY`/`GEMINI_MODEL`, optional hotkeys and speech model size. Require only the selected provider's key; text mode also requires its model. --check masks both keys without importing either SDK or initializing hardware.
- `data/qdrant/`: memory vectors.
- `data/actions.log`: one line per action (time, tool, safe summary of arguments, result).
- `data/contacts.json`: optional `{"priya": "priya@gmail.com"}`.

## 7. Security boundaries

- The model can only reach the laptop through the tool registry.
- No tool runs shell commands or scripts.
- Web pages, emails, and files are information only and never grant permission.
- API keys never appear in logs, the UI, or error messages; configured and process-environment keys for both providers are redacted.
- Gemini uses the Developer API and a user-selected model; generation access, free-tier eligibility and quotas require an account check. Client-owned GenerateContent history does not change Google's data-use terms. Model catalog presence does not establish generation access. Memory embeddings remain the planned OpenAI/Mem0 provider and are outside this Phase 2 adapter change.
- Email bodies are not stored in the action log (first 80 characters only).

**Phase 2 console input handoff.** The console factory supplies an optional before_input callback to InputTools through register_tools. Valid scroll/key/typing calls print a target-window/mouse notice and wait three seconds using the kill event. InputTools checks cancellation before and after handoff; top/bottom scroll delegates to the key path so it waits only once. Invalid arguments and killed turns never reach handoff or hardware. Standalone tools without a callback preserve their existing behavior. Outcomes remain unverified; no window activation or screen reading was added.

**Phase 3 controls/states.** Default main starts the voice console; --text-only preserves the previous console and --check remains hardware-free. Ctrl+Alt+Space begins one silence-bounded utterance; Ctrl+Alt+Esc and stop/quit stop the instance. Stop listening pauses activation; typed start listening resumes. Console state notifications are idle/listening/processing/speaking/error/paused. Busy activations are ignored, not replayed. Only recognized text goes to the existing provider-neutral Brain; no registry dispatch or provider loop is duplicated. Phase 2 outstanding acceptance/routing/offline gaps remain documented despite explicit user authorization to proceed. Real Phase 3 acceptance remains pending.


## Phase 4 desktop integration

--gui starts a PySide6 DesktopSession; default python -m iris.main remains the Phase 3 console and --text-only remains the Phase 2 fallback. pythonw.exe -m iris.main --gui runs without a terminal. The main window is 940x640 (minimum 760x520); the always-on-top transparent frameless orb is 120 logical pixels, user-draggable, clamped to available monitor rectangles, and remains after the main window is hidden. Orb click opens/focuses the window, per the explicit Phase 4 request; Mic/global push-to-talk activates voice. Palette/state motion lives in theme.py and orb.py; idle/paused/hidden motion stops. Reduced motion and position are in-session only.

ui/app.py owns one VoiceController and one existing start_voice_hotkeys listener. Startup/client creation and shutdown/join run off the Qt thread. UiBridge uses explicit queued signals for states, recognized text, replies, tool outcomes and confirmation metadata. Widgets are never touched by backend threads. Text and Mic requests use VoiceController.submit_text/request_listen, preserving the same Brain.run/registry/providers and busy-turn reservation. GUI input handoff emits a notice and observes the same three-second kill-event wait, without selecting a window. Error states are briefly held so a fast transition back to idle is visible; error text remains visible. Conversation is plain text with selectable bodies, structured result badges and scroll following only when the user stays at the bottom.

ToolRegistry has optional on_confirmation and on_result observers. Explicit per-call confirmations override the default callback; the default still calls PermissionGate.authorize. GUI confirmation cards keep request/turn IDs, use original deadlines, and resolve only through gate.resolve; hide, cancel, expiry and kill cannot approve. Result observers run after the original log attempt, cannot alter an outcome, and never dispatch anything. Storage failure is observed as failed. All production tools remain the existing seven auto tools; no email/memory actions were added. Request IDs/turn IDs stay internal rather than appearing as product instructions.

A per-workspace local Qt server prevents a second GUI launch from starting another controller/listener. Its user-restricted local IPC accepts only show-window, never commands or approvals; Windows uses named pipes. Do not run a debug console and GUI concurrently. Main-window close/minimize does not terminate IRIS; Quit or emergency stop latches the gate and begins asynchronous cleanup. The GUI remains responsive until owned voice workers/listener/client are closed. Cleanup errors show a fixed warning rather than raw exceptions. Earlier Phase 2/3 safety and hardware findings remain open where not explicitly confirmed by the user.
