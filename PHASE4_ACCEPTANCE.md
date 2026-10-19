# Phase 4 acceptance — 13 Oct 2026

## Latest combined Phase 4/5 request

Main-window startup and orb click-to-open are restored, superseding the later
historical orb-only notes. Revolving cyan HUD artwork is retained, with gentle
idle breathing and faster processing orbit. Mic/hotkey still activates existing
voice; no extra Brain/controller/listener. IRIS menu and orb provide Exit IRIS.
Gmail connection status opens the matching dark review editor; exact-email dialogs
use the original gate through GUI-owned jobs. One serial Gmail worker and owned
consent subprocess are included in asynchronous cleanup. Phase 4 was integrated
and verified first: **299 passed in 20.97s** before proceeding to Phase 5.
Combined final full suite: **358 passed in 26.43s**. pip check and masked --check
pass. The Gmail subset previously passed 56 tests; no live account or native
hardware acceptance is claimed. Synthetic final editor/confirmation renders were
visually inspected, without accessing Gmail.

Native Phase 4 acceptance remains pending: startup/click/drag/transparent corners,
all monitor/DPI work areas, six states/red dot, idle/reduced-motion CPU/smoothness,
text/voice/model parity, no self-listening or duplicate workers/actions, hide/show/
singleton, errors, kill-at-each-stage and full native cleanup. Follow the existing
Windows steps below plus PHASE5_ACCEPTANCE.md for Gmail. The original Phase 2/3
pending findings remain preserved. Rendered synthetic widgets are not acceptance.

Earlier results/notes below are dated implementation history, not current counts
or new claims that the Windows laptop/account was tested by the agent.

**Status: complete implementation, verified offline; real Windows GUI acceptance pending.** No real GUI/hotkey/audio/tool acceptance is claimed from offscreen rendering/tests. The user explicitly authorized Phase 4 and reported successful core Phase 3 microphone capture, Whisper transcription, AI tool execution, Gmail opening and speech on the laptop. Remaining earlier edge/safety checks stay open.

## Implemented

- PySide6 940x640 desktop window (minimum 760x520), approved dark palette/Segoe UI branding, conversation, command field, Send, Mic, state indicator, recognized speech, visible errors and structured verified/unverified/failed badges.
- 120 logical-pixel frameless, transparent, always-on-top draggable orb, initial bottom-right work-area position, six approved colors, lightweight Qt fades/pulses, microphone dot, in-session position, monitor/work-area reclamping and reduced motion. The label has a small dark backing for bright desktops.
- Orb click opens/focuses the window; Mic and Ctrl+Alt+Space use the existing voice activation. This explicit Phase 4 behavior overrides the earlier click-to-record wording in design/phase documents, which are now aligned.
- Right-click show/hide, pause/resume, reduced motion and Quit. Window close hides; minimize does not end voice/controller/orb. No UI settings system, persistent UI history/position, orb auto-listening or wake word.
- Queued Qt signals bridge one existing VoiceController/Brain/providers/registry. Widgets only update on the GUI thread. Text/Mic requests use the same busy reservation and are never replayed. The GUI retains TTS/mic exclusion, eight-call budget, kill/permissions/logging and truthful tool results.
- Optional registry observers display actual post-log outcomes and route confirmation requests to a non-blocking GUI card. Original request/turn IDs/deadlines are retained; approval/cancel goes only through gate.resolve. Expiry/hide/kill cannot approve. Production remains the same seven auto tools; confirmation tests use a synthetic safe tool.
- Startup/client creation and cleanup run off the event loop. Quit/stop/kill latches the gate immediately, stops one combined hotkey listener, closes the existing voice workers/processes/client, then exits. Cleanup errors produce a fixed warning rather than raw exceptions.
- Per-workspace, user-restricted local Qt IPC prevents a second GUI from starting another controller/listener. The only accepted message is show-window, not commands or approvals. On Windows this uses named pipes. Separate debug console processes should not run concurrently with GUI mode.

## Automated results

Full suite: **297 passed in 28.45s**, Python 3.12.6, PySide6 6.12.0. Previous baseline was 262 tests. Independent GUI/registry subset: **34 passed in 18.18s**. Qt uses the offscreen backend; audio/ASR/TTS, providers, hotkeys and desktop tools are mocked. Test coverage includes six states/mic dot, animation suspension, click/drag, logical multi-monitor geometry, readable plain-text rendering/redaction, command/Mic signals, recognized speech, queued thread affinity, errors, long-history scroll follow/reading position, duplicate prevention, both real provider adapters with mocked Gmail replies, actual permission request/turn approval/cancel/expiry/replay/kill, hide/show, async cleanup, cleanup warnings, singleton startup and IPC.

A separate bounded offscreen QApplication startup/event-loop/shutdown smoke passed outside the filesystem sandbox using a fully mocked runtime. It closed the Brain once and left no live iris-* worker threads. The initial sandboxed local-IPC smoke did not finish and was stopped; it is not counted as a pass. Neither probe started a real microphone, model, TTS engine, hotkey listener or browser/tool.

pip check reported no broken requirements; masked --check passed with the existing Gemini configuration and keys hidden. PySide6 was installed in .venv; no credential/model settings were changed. Actual offscreen QWidget renders with synthetic conversation were visually inspected at data/phase4_window.png and data/phase4_orbs.png. An offscreen Windows font-discovery issue and deferred scroll-layout issue were corrected; these images are not Windows desktop acceptance screenshots.

## Files

Created: iris/ui/app.py, tests/test_ui.py, tests/test_gui_registry.py, PHASE4_ACCEPTANCE.md.

Modified: iris/ui/theme.py, iris/ui/orb.py, iris/ui/window.py, iris/main.py, iris/tools/registry.py, requirements.txt, tests/test_text_console.py, README.md, Architecture.md, design.md, phase.md, memory.md, PHASE3_ACCEPTANCE.md.

## Exact launch commands

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\python.exe -m iris.main --gui
```

Without a terminal window:

```powershell
.\.venv\Scripts\pythonw.exe -m iris.main --gui
```

Original console modes remain unchanged:

```powershell
.\.venv\Scripts\python.exe -m iris.main
.\.venv\Scripts\python.exe -m iris.main --text-only
```

Whisper model preparation is in README.md. Do not redownload already-working cached weights or overwrite .env. Run only one mode at a time.

## Real Windows checklist (all GUI rows pending)

For each test record actual behavior, state/mic dot, transcript, spoken response, action-log tool/status/count, and PASS/FAIL.

| Test | Required observation | Status |
|---|---|---|
| Launch python/pythonw GUI | One main window and one orb; no terminal needed with pythonw | Pending |
| Close/hide/minimize/reopen | Runtime/orb remain; click focuses the window and does not record | Pending |
| Drag / monitor placement | Click vs drag separate; position retained for the run; no offscreen orb | Pending |
| Native transparency/topmost | Transparent corners, orb visible above other normal windows | Pending |
| Mixed DPI / screens | Test available 100/125/150/200% displays, negative-coordinate monitors and monitor/work-area changes | Pending |
| State colors / motion / mic | Idle/listening/thinking/speaking/error/paused match; red dot during capture; reduced motion stops pulses | Pending |
| Text and duplicates | What time is it + rapid Send/Enter produces one turn/tool and honest status | Pending |
| Conversation / errors | Recognized speech and readable/selectable messages; long history follows bottom but preserves scrolled-up position; failures remain visible | Pending |
| Mic / hotkey Gmail | Correct transcript, one existing open_url action/log, accurate spoken unverified response | Pending |
| Self-listening / busy | Mic/hotkey during queued speech/tail creates no recording/action; no buffered accidental activation after idle | Pending |
| Pause/resume | Orb menu shares stop/start listening control; paused Mic/hotkey cannot record | Pending |
| Focus handoff | Scroll/type/keys still require selecting the intended target during the three-second notice | Pending |
| Emergency stop | Ctrl+Alt+Esc during mic/ASR/model/input/TTS/idle cancels and cleans up; no late action or speech | Pending |
| Quit / startup cancellation | Responsive while stopping, no owned audio processes/listener left, restart succeeds | Pending |
| Repeated GUI launch | Second launch focuses first window; no second orb/controller/listener | Pending |
| Provider parity | Repeat core text/voice/error/kill checks with each provider where credentials exist | Pending |

Confirmation UI is automated-tested only: none of the seven current tools requests confirmation, so do not add or send real emails to test it. Original gate tests cover safe synthetic requests.

## Known limitations and preserved earlier findings

- Native Windows topmost/focus/transparency, real DPI/monitor changes, long-running resource use and OS session-ending cleanup remain unverified. Headless tests cannot establish these.
- GUI instance protection covers repeated GUI launches for this workspace. An independently running debug console is not detected/replaced; use one mode at a time.
- Position, reduced motion and visible conversation are in-memory for the current run. Startup SDK imports can take time; shutdown waits for owned startup work off the GUI thread. Forceful OS termination cannot be presented as a verified graceful cleanup.
- Phase 2 direct wheel scrolling, real kill/log checks, close-tab no-tool failures, informational requests triggering unwanted actions, capability phrasing and offline-local-command handling remain open. Browser/input results stay unverified; already-dispatched actions cannot be undone.
- The user reports core Phase 3 voice success. Self-listening prevention, error-device/permissions, silence/timeouts, native reaping, kill-every-stage and live provider parity still need explicit confirmation. English CPU/int8 transcription, per-utterance model/engine startup latency and fixed RMS/playback-tail limits are unchanged.
- Existing HTTP work may finish within its bounded timeout after cancellation, with late tool execution blocked. Audio worker/driver cleanup needs real-machine validation despite mock reaping tests.
- No Gmail drafting/sending, Mem0/Qdrant memory, wake word, screen awareness, unrestricted shells/filesystem operations or autonomous desktop control was implemented.

Phase 4 is ready for real-machine review, not marked accepted until the required Windows GUI checks are confirmed.
# Orb-only acceptance update — 13 Oct 2026

Revolving/orbiting update: state-speed HUD rotation and glowing satellites added.
Full offline suite **299 passed in 19.24s** includes frame changes and stopped
timers when paused/hidden/reduced-motion. Windows smoothness/CPU/voice acceptance
still pending; user-requested idle revolution overrides earlier idle-still design.

Latest visual update: reference-inspired cyan HUD/glass depth, segmented rings,
ticks, amber accents and I.R.I.S. wordmark. Six synthetic state renders inspected;
full offline suite **298 passed in 24.43s**. Native Windows readability/DPI and
voice-state checks remain pending. No true 3D mesh engine was added.

Automated verification: **298 passed in 21.93s**. Compact-dialog Yes/No tests use
the real Qt buttons with mocked provider/tools; errors are checked at the orb and
the large window stays hidden. This does not confirm real Windows voice acceptance.

The user superseded the large-window experience with orb-only operation. Verify
--gui shows just the orb; click starts one utterance; speech replies play; dragging
does not listen; busy/speaking clicks do not open a mic; right-click pause/resume and
Quit work; Ctrl+Alt+Space and Ctrl+Alt+Esc retain their behavior. Hover shows latest
sanitized status. Required approvals appear in a small dialog, never the large
window, and expiry/cancel/kill cannot approve. Repeated launches restore only the
orb without another worker. These native checks remain pending; provider 503/504
remains unresolved. Older window-specific instructions below are historical.

