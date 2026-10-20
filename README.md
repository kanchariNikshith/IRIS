# IRIS — Orb and local commands (R0–R3 progress)

GitHub delivery: [phase commit groups and future push workflow](GITHUB_WORKFLOW.md).
The initial import groups current source by component; intermediate import commits
are not independently runnable historical releases.

19 Oct functionality audit: **439 passed in 76.69s**, with no failures or skips.
Dependency, compilation and masked configuration checks passed. See the
[full functionality report](FUNCTIONAL_TEST_REPORT_2026-10-19.md) for feature
coverage, measured wake results and outstanding live acceptance checks.

## Active R-roadmap runtime update — 15 Oct 2026

20 Oct: R3 now includes a tested development path from wake detection to command
capture on one microphone stream, preserving immediate speech and bounded pre-roll.
Cancellation, worker watchdogs and local transcription share the existing audio
ownership. Normal GUI/startup wake listening remains disabled: every current model
still fails acceptance. See [R3 acceptance](ROADMAP_R3_ACCEPTANCE.md) for scope,
verification and remaining model/device checks.

19 Oct: larger v2/v3 models have been trained locally and compared on the frozen
owner corpus. V3 regressed on recall; all candidates fail acceptance. Wake remains disabled; improved phrase
recall alone does not pass false-activation acceptance. The latest full offline
regression suite passed **439 tests in 121.23s**. See
[measured accuracy report](WAKE_ACCURACY_REPORT.md) for the completed comparison.

16 Oct continuation: the isolated R3 synthetic training/export pipeline now runs
end to end and produces development-only ONNX bundles. Both candidate runtimes
were compared on the same synthetic audio; each detected 8/8 positives but also
produced two false wakes in only 6.25 seconds of negative audio. These tiny smoke
results fail wake acceptance; neither engine is enabled in IRIS. See
[R3 acceptance](ROADMAP_R3_ACCEPTANCE.md) and [training setup](training/README.md).
The setup tools create dataset folders; no pre-existing model/data is needed.
Final offline regression suite: **434 passed in 62.55s**. Native Windows/device,
account, natural-voice and all-day acceptance remain pending.

R2 capture now uses one stream owner with bounded pre-roll/frame conversion and
an owner-supplied transcription path; the full offline suite passed 405 tests.
See [ROADMAP_R2_ACCEPTANCE.md](ROADMAP_R2_ACCEPTANCE.md). Ambient wake listening
still requires R3's evaluated custom model. Hardware checks remain pending.

R0 baseline: see [ROADMAP_R0_ACCEPTANCE.md](ROADMAP_R0_ACCEPTANCE.md).
R1 implementation: see [ROADMAP_R1_ACCEPTANCE.md](ROADMAP_R1_ACCEPTANCE.md).
These entries supersede historical main-window startup and cloud-required local
command instructions below. `--gui` starts only the orb; click to speak,
right-click **Show or hide IRIS** for chat/setup. Launch without a console using
`.venv\Scripts\pythonw.exe -m iris.main --gui`. Reopening restores the orb.

Time/date, `open Notepad` (and the other five catalog apps), explicit HTTP/HTTPS
URLs, `scroll down 5` (1–20), `scroll to top/bottom`, `new tab`, `close tab`,
`go back/forward`, `volume up/down` and `mute` use the normal gated/logged local
tools with zero provider calls. Input still needs the three-second focus handoff
and is unverified. Compound/ambiguous requests use the selected provider.
`pause listening`/`stop listening` closes the current voice capture; resume from
the orb menu or typed `start listening`. Wake listening is not implemented.

Cloud credentials/model are optional for startup/local commands; cloud questions
explain missing configuration. `--check` still strictly diagnoses a missing
selected key and masks credentials. Provider/model settings are preserved. Email
previews explicitly open GUI review; saving/sending retains exact-message approval.
No native Windows or real account acceptance is inferred from automated tests.

> The following prototype notes are historical where they conflict with the active update above.

> Active implementation sequence: [phase.md](phase.md), roadmap R0–R13 (15 Oct 2026). The former Phase 1–7 plan is [archived](PHASES_LEGACY.md); earlier numbered phases below describe prototype history.

> Current product direction (15 Oct 2026): see [IRIS_VISION.md](IRIS_VISION.md) for the orb-only, wake-activated desktop goal, source-based gap assessment and next milestones. Setup/runtime behavior below describes the existing prototype; the new hands-free/app-control features are not yet implemented.

The latest combined Phase 4/5 request restores the main window: the revolving HUD
orb opens/focuses it, and Mic or Ctrl+Alt+Space listens. Phase 5 adds official Gmail
OAuth, a local editable preview, and gate-confirmed draft/save actions. Earlier
orb-only startup/click-to-listen notes below are historical, superseded instructions.

## Phase 5 Gmail setup

1. Open [Google Cloud Console](https://console.cloud.google.com/), select/create
   your project, and enable **Gmail API** in APIs & Services > Library.
2. In Google Auth Platform > Branding, configure IRIS and your support/contact
   email. For a personal Gmail account choose **External**, keep the app in
   **Testing**, and add your Gmail address under Audience > Test users. Internal
   is only appropriate for an eligible Workspace organization.
3. Under Data Access add only `https://www.googleapis.com/auth/gmail.compose`.
   It manages drafts and sends mail; `gmail.send` alone cannot create drafts.
   This is a restricted scope. Public distribution has additional verification
   requirements; do not request full mailbox/read/modify scopes for IRIS.
4. Under Clients choose Create Client > **Desktop app**. Download its JSON.
5. Create the external directory below and save the downloaded file there as
   **client.json**. Never put it in the source checkout or paste it into chat.

```powershell
New-Item -ItemType Directory -Force -Path "$env:LOCALAPPDATA\IRIS\gmail"
```

Default client location: `%LOCALAPPDATA%\IRIS\gmail\client.json`. If using
another directory, set `GMAIL_OAUTH_CLIENT_FILE` in `.env` to its full absolute
path outside this project. Leaving that setting blank uses the default. This is
a Gmail OAuth client, separate from GEMINI_API_KEY; changing a Gemini key cannot
connect Gmail. No password is requested by IRIS.

6. Install and launch:

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\pythonw.exe -m iris.main --gui
```

7. Click **Gmail: Disconnected**, then **Connect Gmail**. Complete Google's
   consent in the browser. Only after consent/token validation succeeds does
   IRIS show Connected. Consent waits at most 180 seconds; Cancel or emergency
   stop closes the owned OAuth worker. IRIS uses loopback redirect and PKCE.
   Tokens are stored as DPAPI-encrypted bytes in the same external directory,
   tied to the Windows user; there is no plaintext token fallback. A previously
   authorized cached token can restore the connection on startup. Revocation may
   only be detected on refresh or the next Gmail write; errors require reconnecting.

Disconnect Gmail clears the local credential/token. To revoke Google's grant as
well, remove IRIS under your Google Account's third-party connections. OAuth
testing grants may require renewed consent. See Google's [desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail setup guide](https://developers.google.com/workspace/gmail/api/quickstart/python)
and [scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes).

## Preparing, reviewing and writing email

Type, or use Mic to say, `Draft an email to your-address@gmail.com saying I'll
attend tomorrow's meeting.` An initial Send an email request also creates only a
local preview. Review every recipient, subject and body in the Gmail editor.
The model is not allowed to invent missing addresses or facts. Optional local
`data/contacts.json` maps names to addresses; spoken `john at gmail dot com` is
normalized. Unknown names require a complete address; no contacts are written.

You can also enter the fields yourself and click **Prepare locally**, without
calling either AI provider. This works even when Gemini returns 503/504.
Local previews are held in this process only; nothing is sent or saved automatically.

**Save Draft** asks approval for the exact snapshot, then calls Gmail drafts.create.
**Send** opens the full immutable message and asks **Send this email**. It expires
within 30 seconds. Cancel, edit any field, close/hide, expiry or emergency stop
cannot approve it. Spoken send it and model-generated tool calls cannot approve.
Fields freeze after approval until the write finishes; edits before approval
invalidate it. Each attempted snapshot is consumed and cannot be replayed by
repeated clicks, callbacks or AI retries. Prepare a new preview or edit it for a
deliberate new attempt after checking Gmail.

Gmail confirmation of a message ID means submission, not proof of recipient
delivery. A timeout/5xx/missing response is **uncertain**: check Gmail before any
new attempt. Sends and draft writes have no automatic retry. Stop prevents new
dispatch, but cannot retract an already in-flight Gmail request. Audit logs keep
safe counts/results, never recipients, subject, body, MIME, tokens or OAuth codes.
Email text supplied to the Brain still goes to the chosen AI provider as ordinary
command/model content; OAuth credentials never do.

Both acceptance records have exact Windows checks:
[Phase 4](PHASE4_ACCEPTANCE.md), [Phase 5](PHASE5_ACCEPTANCE.md).
Neither live OAuth nor sending has been performed by the agent. Earlier Phase
2/3 safety, device, routing and offline-command gaps remain in memory.md.

Final combined offline verification: **358 passed in 26.43s** (Python 3.12.6).
Phase 4 was verified first with 299 tests; the Gmail-focused subset passed 56
tests before the last hide-path and worker-error cases were added. All external APIs, consent,
hardware and native secure-storage calls are mocked. pip check and --check pass.

Install the dependencies in a virtual environment (Python 3.11 is the project
target; the offline suite has been run on Python 3.12.6):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

OpenAI remains the default. Set `OPENAI_API_KEY` and your chosen `OPENAI_MODEL`
in `.env`. To use Gemini instead, set `AI_PROVIDER=gemini`, `GEMINI_API_KEY` and
`GEMINI_MODEL`; an OpenAI key is not required for Gemini mode. Model names
are user-configured; there is no automatic provider fallback. Then run:

```powershell
python -m iris.main --check
python -m iris.main --gui
python -m pytest -q
```

The check prints masked settings without contacting OpenAI or initializing
hardware. The selected provider's model is required before commands make API calls. The console
accepts commands such as "open Instagram", "scroll down", "open notepad", and
"what time is it". Type `quit` to exit or `stop` to latch the kill switch and exit.

Phases 1–5 are implemented for acceptance testing. The user reports successful real-Windows core voice capture/transcription/tool/Gmail-browser-opening/speech tests. Earlier edge/safety/routing/offline gaps remain recorded. Phases 4/5 real GUI/OAuth/Gmail acceptance is pending; wake word and persistent memory remain unimplemented.
`data/` is created lazily when the logger first appends to `data/actions.log`.

Tools must return `ToolResult`, use JSON object argument schemas, and execute
through `ToolRegistry`. Construct `ActionLog(secrets=config.secrets)`
so credentials loaded from `.env` are redacted as well as process environment
credentials. Invalid, unknown, denied, and completed calls are logged.

Confirmation callbacks receive a request ID and turn ID, and the UI must resolve
that request through `PermissionGate.resolve`. Responses expire after at most
30 seconds and cannot be reused. Only trusted user input should set
`explicit_memory_request` or resolve a confirmation.

`start_kill_switch(gate, config.kill_switch_hotkey)` provides the Ctrl+Alt+Esc
listener adapter. The runtime caller owns listener shutdown. The stop flag is
latched for the lifetime of the gate, cancels pending confirmations, and blocks
later calls. App process polling and character-by-character typing observe this
flag; cancellation discards an in-flight API response without executing its tools.
The HTTP request may finish in the background within its 20-second timeout.
Already-dispatched OS input cannot be undone. The default voice console polls Windows keyboard input, so Ctrl+Alt+Esc can close it even while idle. The legacy --text-only console may still need Enter to unblock stdin. Audio workers are cancelled and reaped on shutdown.
Real Windows hotkey behavior needs a manual check; tests inject a mock listener.

Older Phase 1/2 dependencies exist in `.test-deps`; they are not a complete voice installation. Use the normal .venv installation above for Phase 3. The older offline-test path is:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) '.test-deps'
python -m iris.main --check
python -m pytest -q
```

Use a normal virtual-environment installation for Windows runtime use; pywin32's
startup hooks are needed to resolve Start menu shortcuts.

The adapters use OpenAI Responses or Gemini GenerateContent, pass matched tool
results and native reasoning/thought items back within the turn, and let the
shared Brain make at most eight tool-call attempts. After the
limit it disables tool calling for the final request. SDK retries are disabled;
IRIS retries an API error once after two seconds. Only the last ten user/assistant
messages are retained between commands, in process memory. Action replies are
constructed from actual tool results rather than model success claims. The
shared no-tool guard refuses unperformed action requests and unsupported
completion claims. It conservatively accepts English questions/greetings;
ambiguous requests may be refused even when an alternative phrasing would work.
See the [official OpenAI function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling).
Gemini uses the [GenerateContent function-calling protocol](https://ai.google.dev/gemini-api/docs/generate-content/function-calling).
The google-genai import is lazy so an existing OpenAI installation can still run
without it. The full requirements install includes both SDKs for the full tests.
Gemini automatic SDK tool execution is disabled. The adapter submits registry
schemas through parameters_json_schema and preserves complete model parts,
including thought signatures. Gemini 2.5 calls without native IDs use local
correlation IDs; synthetic IDs are not sent back as invented native IDs.
SDK attempts=1 disables automatic HTTP retries; the shared Brain controls at most
one retry of transient failures. Mock HTTP tests verify request counts and
prevent tool re-execution after a retry.

Choose a model available to your Gemini project and check its free-tier quotas.
Google's [pricing page](https://ai.google.dev/gemini-api/docs/pricing) states that
free-tier content is used to improve its products. OpenAI store=False and local
Gemini turn history do not change either provider's data-use terms. The adapter adds no built-in
search, code execution, memory or other provider tools. Local console commands
still need model connectivity; the previously audited offline-local-command
fallback remains unresolved.

For Gemini connection problems, see GEMINI_TROUBLESHOOTING.md. The configured
gemini-2.5-flash returned HTTP 404 in live minimal requests through both Gemini
APIs, despite successful model listing. Google restricts access to 2.5 models
to prior users; listing a model does not prove generation access. The application
does not change GEMINI_MODEL automatically. Errors now give a sanitized category
and HTTP status; 403/404 are not reported as proof of an invalid API key.

Browser dispatch and focused-window input return `unverified` because this phase
cannot inspect the loaded page or the receiving window. `open_app` uses a catalog
of Notepad, Chrome, Edge, Spotify, Word and Excel. It checks for a new matching
process within eight seconds; an already-running process alone is insufficient.
Start menu fallback inspects matching shortcuts and launches only the expected
executable, discarding shortcut arguments. Packaged apps with non-executable
shortcuts may not resolve and will be reported as unavailable.

Keyboard actions are limited to new/close tab, back/forward, top/bottom and volume.
Typing is limited to 500 printable ASCII characters and rejects tabs, newlines,
control characters and Unicode that PyAutoGUI cannot reliably type. It never
presses Enter. Before each console scroll/key/typing action, IRIS prints a notice
and waits three seconds. During this pause click the intended window; for wheel
scrolling keep the mouse over the page content. Ctrl+Alt+Esc cancels the pause.
IRIS still cannot verify which window receives input or whether it responded.

Manual Windows checks (not performed by the offline tests): start text mode with
your chosen model, try the four example commands, inspect `data/actions.log`,
confirm focused-window input, move the mouse to a corner to check PyAutoGUI's
failsafe, and press Ctrl+Alt+Esc during typing or app polling. Real OpenAI access,
default-browser behavior, installed-app shortcuts and global hotkeys require
these checks. Do not treat browser acceptance as proof that a page loaded.


## Phase 3 setup

Use the existing virtual environment; do not overwrite your .env or keys. The full requirements now include sounddevice, NumPy, faster-whisper and pyttsx3. Windows wheels provide PortAudio and PyAV; this implementation uses CPU/int8 Whisper and Windows SAPI5, without requiring CUDA or an external FFmpeg executable. Dependency import checks do not start a microphone, model or speaker.

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m iris.main --check
```

Keep WHISPER_MODEL=base (already the default), or use a supported cached model/local model directory. Before first voice use, explicitly download/cache the selected model once while online:

```powershell
.\.venv\Scripts\python.exe -c "from iris.config import load_config; from faster_whisper import WhisperModel; WhisperModel(load_config().whisper_model, device='cpu', compute_type='int8'); print('Whisper model cached.')"
```

This preparation downloads model weights, not microphone audio. Runtime transcription uses local_files_only=True and never downloads weights while listening. If preparation fails or the cache is missing, IRIS reports a fixed model error and keeps typed commands available. Using the local CPU model can add startup latency; no four-second latency target is claimed.

In Windows choose a working default input device in Settings > System > Sound and test it there. Enable microphone access for desktop apps under Settings > Privacy & security > Microphone. See [Microsoft microphone permissions](https://support.microsoft.com/en-us/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows).

Start voice mode (the default) or retain the Phase 2 fallback:

```powershell
.\.venv\Scripts\python.exe -m iris.main
# Without audio workers or push-to-talk:
.\.venv\Scripts\python.exe -m iris.main --text-only
```

## Using voice

Press and release Ctrl+Alt+Space, wait for State: listening, then speak one command. This arms one recording; it does not continuously monitor speech and does not require holding the keys. A busy/paused/speaking controller ignores further activation rather than queuing accidental recordings. Existing PUSH_TO_TALK_HOTKEY and KILL_SWITCH_HOTKEY settings are respected.

The microphone captures 16 kHz mono float32 only during listening. It stops after about 1.2 seconds below the RMS silence threshold, five seconds without speech, or fifteen seconds total. Silence/no-speech captures do not invoke Brain. Three misses suggest typing. Transcription is English, local faster-whisper with VAD. The recognized text is shown as Heard: and is handed to the existing Brain once; audio is neither saved nor sent to either AI provider. Recognized command text still goes to the selected provider as ordinary Brain input.

Console states are idle, listening, processing, speaking, error and paused. The stream is closed before transcription. New microphone capture is blocked throughout transcription, Brain work, all queued speech and a 0.3-second playback tail. Replies use the same truthful verified/unverified/failed summaries as typed commands. pyttsx3 speaks at most three short sentences, without code blocks, Markdown or emojis; the full reply stays in the console.

Type or say stop listening to pause voice activation. While paused, type start listening to enable it again (a closed microphone cannot hear a resume command). Typed commands remain available while paused. If you type stop listening during capture/transcription, cancellation closes that voice operation and discards its command; the pause notice is text-only in that case to avoid overlapping microphone capture. Type stop/quit or press Ctrl+Alt+Esc to stop the entire assistant. A kill remains latched; restart IRIS to resume.

The hotkey callback only submits work. One command worker owns capture/transcription and calls Brain.run; a separate speech queue worker owns playback. Native capture/Whisper and SAPI run in owned spawned subprocesses, so a hung native call can be terminated and reaped. Recording/transcription has a 90-second overall bound including local model initialization, with a sixteen-second parent watchdog for a hung recording stage (normal capture ends by fifteen seconds) and sixty seconds for transcription; speech has a 60-second bound. Shutdown uses cooperative cancellation, then bounded terminate/kill/join as needed. No audio child should remain after exit. Each utterance gets a new native worker; model reloading has a latency cost. Existing API requests may finish within their bounded timeout, but cancellation prevents late tool execution.

Missing microphones, denied access, stream errors, missing model files, transcription errors and speech failures produce fixed sanitized diagnostics and an error state; driver exception bodies are not printed. A speech failure leaves the text reply usable. Audio errors append a safe voice error record, without recordings/transcripts. The three-second focused-window handoff from Phase 2 still applies to scroll/key/typing tools; voice activation itself does not move or select a window.

## Remaining Phase 3 Windows acceptance

The [Phase 3 acceptance record](PHASE3_ACCEPTANCE.md) records user-confirmed core voice success and remaining checks. Perform these on the real laptop; mocked tests are not hardware acceptance:

1. Start default voice mode. At idle, confirm the microphone is closed.
2. Press Ctrl+Alt+Space, wait for listening, say Open Gmail, then stop speaking. Check listening -> processing -> Heard: Open Gmail -> speaking -> idle.
3. Confirm Gmail opens once via the existing open_url tool and data/actions.log gets one unverified entry. Expect spoken wording that browser dispatch/page loading could not be confirmed, even if you see the page load.
4. While the reply is spoken, press Ctrl+Alt+Space and speak near the speakers. Confirm no listening state, no new Heard line and no additional action. Repeat without pressing the hotkey; nothing should listen. After idle, the next hotkey should work.
5. Say What time is it: expect one verified time result and matching speech. Say Stop listening: microphone stays closed and hotkey no longer arms it. Type start listening, wait for idle, and retest.
6. Test five-second no-speech timeout, a phrase followed by silence, and continuous speech exceeding fifteen seconds. No-speech must not execute tools. Noise/soft voices may require microphone gain adjustments; the fixed threshold is not validated for your room yet.
7. Test Ctrl+Alt+Esc during listening, transcription, provider processing, the input handoff, speaking and idle. No late tools or queued speech should run. Already-dispatched actions cannot be undone.
8. Disconnect/disable the default microphone or deny desktop microphone permission yourself. Confirm a clear error, microphone closure and working typed Hello/get_time commands; restore the setting afterward. Audio capture itself is local, but typed/voice Brain commands still require network access.
9. Exit with quit and with the kill hotkey. In Task Manager or a local process listing confirm this IRIS instance's child Python workers and hotkey listener are gone; restart successfully. Preserve unrelated Python processes.
10. If configured credentials are available for both providers, repeat the Gmail/time/cancellation checks separately with AI_PROVIDER=openai and AI_PROVIDER=gemini. Never share keys. Live voice OpenAI/Gemini parity is not claimed from mocks.

Inspect logs locally in a separate PowerShell window:

```powershell
Get-Content .\data\actions.log -Tail 20
```

Record visible action, Heard text, spoken wording, state sequence, tool count and log status for each test. Do not share private transcripts or keys. Phase 3 is implemented for testing, not marked complete until the required real-machine checks pass. Phase 2 direct wheel scroll, kill/log checks and routing/offline defects remain recorded; no Phase 4+ work was added.

Implementation references: [sounddevice streams](https://python-sounddevice.readthedocs.io/en/0.5.3/api/streams.html), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [pyttsx3 engine](https://pyttsx3.readthedocs.io/en/latest/engine.html), [pynput hotkeys](https://pynput.readthedocs.io/en/latest/keyboard.html#global-hotkeys).

Latest full offline test result: **262 passed in 16.09s** on Python 3.12.6. Audio/ASR/TTS, hotkeys, process ownership and provider responses are mocked. Core Windows voice success is now user-reported; remaining Phase 3 edge/safety checks are pending.


## Phase 4 GUI launch

The recommended desktop entry point is --gui. Default python -m iris.main still opens the existing voice console; --text-only remains the debugging fallback. Credentials/model settings are unchanged. GUI mode creates one existing Brain and VoiceController, with a single combined global-hotkey listener.

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\python.exe -m iris.main --gui
```

To run the desktop interface without a terminal window:

```powershell
.\.venv\Scripts\pythonw.exe -m iris.main --gui
```

Debugging modes are still available:

```powershell
.\.venv\Scripts\python.exe -m iris.main
.\.venv\Scripts\python.exe -m iris.main --text-only
```

Run only one mode at a time; a separately launched console is not automatically replaced by the GUI. Reopening --gui for this workspace shows its existing GUI, rather than starting another microphone/controller/hotkey listener. Local IPC can only request window display and cannot run commands or approve actions. No network-facing control service was added.

PySide6>=6.8,<7 is the new UI dependency (tested with 6.12.0). Qt 6 handles display scaling in logical pixels; orb placement uses available monitor geometry. The approved Segoe UI palette/typography and six states are shared by the window and orb. Reduced-motion choice and dragged position persist for this run only; no new settings/history files are written. The offscreen backend may need explicitly loaded system fonts; the UI has a fallback for that case.

## Using the desktop interface

- The orb is frameless, transparent and always on top. Drag it to move; a click opens/focuses the main window and does not start recording. The red dot indicates listening/microphone activity. Right-click for show/hide, pause/resume, reduced motion and Quit.
- The main window shows IRIS branding, state text, recognized speech, selectable plain-text conversation, actual tool status badges, visible errors, command input, Mic and Send. Enter or Send submits once through the existing voice-controller queue and Brain. Busy attempts are not replayed. Replies still use the existing TTS queue and microphone exclusion.
- Mic and Ctrl+Alt+Space share the same voice activation. Cached Whisper setup remains as above; if your model is already cached and working, preparation need not be repeated. Pause/resume uses the same Phase 3 controls. The main-window close button hides it; minimize keeps the orb/voice available. Quit is in the orb menu; typing stop/quit or Ctrl+Alt+Esc latches emergency cancellation and exits after cleanup.
- GUI/backend communication uses queued Qt signals; no worker updates widgets directly. AI/audio/tools/startup/cleanup remain off the Qt event loop. Conversation follows new messages at the bottom, while scrolling up preserves your reading position.
- Before keyboard/scroll/type tools, a visible three-second handoff tells you to focus the intended target. No automatic target selection was added. Browser/input outcomes remain unverified; a visible page does not change its programmatic verification status.
- Confirmation dialogs use the existing gate request/turn IDs and expiry. Approve/Cancel is one-use; hiding the window, expiry and kill cannot grant approval. The seven desktop tools plus local draft preparation are model-visible; Gmail save/send tools require confirmation and are hidden from the model schema list. Memory remains unimplemented.
- Startup/provider/audio/tool errors use visible sanitized messages. Keys are masked in conversation/actions/errors. Cleanup is asynchronous; if it reports failure, a fixed warning asks you to inspect this IRIS instance's processes before restarting. Avoid force-killing unrelated Python processes.

## Phase 4 Windows testing

Follow [PHASE4_ACCEPTANCE.md](PHASE4_ACCEPTANCE.md) and record observations; offscreen tests do not verify native Windows behavior.

1. Launch --gui, drag the orb, click it to focus the window, then close/hide and reopen the window. Verify the orb position remains unchanged.
2. Test each monitor and 100/125/150/200% Windows scaling where available; verify visibility, transparent corners, legible text, dragging and no offscreen orb after monitor removal/work-area changes.
3. Type What time is it, rapidly press Send twice, and verify one user turn/tool/log entry and honest verified status. Check long-history scrolling and error display.
4. Click Mic, say Open Gmail, and confirm recognized speech, one browser action, accurate unverified speech, orb state transitions and red microphone dot only during listening. Repeat with Ctrl+Alt+Space while the browser is focused.
5. Press Mic/hotkey while speech is playing; confirm no extra recording/transcript/action. Check pause/resume, error devices and silence/timeouts from the earlier acceptance record.
6. Test Ctrl+Alt+Esc during capture, ASR, model work, focus handoff, speech and idle. Quit and restart; confirm owned audio subprocesses/worker threads/listener are cleaned up. Closing/minimizing only the main window should not exit.
7. Launch --gui twice: the second launch should show the first window, not create a second orb/controller/listener. With both provider credentials available, repeat key tests separately in OpenAI and Gemini mode.

Headless automated checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Qt tests select the offscreen backend automatically and mock AI/audio/hotkeys/desktop tools. Current full suite: **297 passed in 28.45s**. The independent UI/registry subset: **34 passed in 18.18s**. An offscreen QApplication startup/event-loop/shutdown smoke check uses a fully mocked runtime; it is not real Windows GUI acceptance. Phase 4 remains implemented and awaiting real Windows acceptance. No Phase 5–7 features were added; unresolved Phase 2/3 findings are preserved.
# Troubleshooting an absent orb or Gemini 503

The HUD orb now revolves with glowing lights on tilted orbit paths. Thinking
rotates faster; center text stays readable. Right-click Reduce motion for a still
orb. Pausing or hiding stops orbital updates; click-to-listen and hotkeys are unchanged.

The orb now uses the requested futuristic cyan I.R.I.S. HUD design with shaded
glass depth, segmented rings, radial ticks and amber accents. It remains 120
logical pixels, draggable, and click-to-listen. This is a Qt-painted 3D appearance;
no new graphics dependency or continuously spinning idle animation is required.

**Historical interface: orb only (superseded by the combined Phase 4/5 request).** Launch with
`.\.venv\Scripts\python.exe -m iris.main --gui` or use `pythonw.exe` instead
to avoid a terminal. The large conversation window stays hidden. Click the orb
or press Ctrl+Alt+Space, wait for teal/listening, then speak. IRIS replies through
the existing speech queue. Drag to move; right-click for Listen, Pause/resume,
Reduce motion or Quit. Hover for the latest transcript/reply/status; important
notices and errors also appear briefly beside the orb. Required permissions use
a small Yes/No dialog with the original expiry and cancellation rules. No wake
word or continuous recording is enabled. Gemini 503/504 can still prevent answers.
Older main-window testing instructions below describe the retained internal/debug
window; they no longer describe the default GUI experience.

The console launch does not create an orb. Exit any running console first, then run
`.\.venv\Scripts\python.exe -m iris.main --gui` from the project folder.
Look near the bottom-right of the primary display, above the taskbar. Repeating the
GUI command shows the existing window and restores/reclamps its orb without starting
another voice controller. Closing the main window hides it; right-click the orb and
choose Quit to exit IRIS.

Gemini HTTP 503 means temporary service unavailability. IRIS already retries once
after two seconds, without repeating completed tool executions. A minimal generic
greeting probe on 13 Oct returned HTTP 504 on the configured gemini-3.5-flash-lite;
this did not establish an authentication or tool-schema fault. Retry Hello later,
then What time is it. Credentials and model were preserved; availability cannot
be repaired by changing the desktop UI. Native orb visibility still needs a Windows check.
