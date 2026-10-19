# IRIS: the assistant we are building

> Active implementation sequence: [phase.md](phase.md), roadmap R0–R13 (15 Oct 2026). The former Phase 1–7 plan is [archived](PHASES_LEGACY.md); earlier numbered phases below describe prototype history.

Updated 15 Oct 2026 from the owner's explicit direction and a source-code audit.

## Read this before planning or changing IRIS

IRIS is a Windows desktop assistant whose everyday interface is only a floating
orb. The owner should be able to operate the laptop by voice: wake IRIS, ask
questions, open apps, dictate and edit text, write messages and emails, navigate
websites, scroll reels, and install requested apps through Microsoft Store.

This is the current product direction. It supersedes older requirements for a
main window at startup, click/hotkey-only listening, wake words as optional polish,
and deferring the app awareness needed for these workflows. Older phase documents
describe the implementation history; they do not define the full destination.
This request establishes the direction and roadmap, not implementation of the
missing features. Existing runtime safeguards remain in force until deliberately
revised and tested as part of the relevant feature.

## What the owner should experience

- Launch IRIS and see the orb, without a required chat window or terminal.
- While enabled, IRIS locally monitors for a configurable wake phrase such as
  "IRIS, let's start." It then listens for the task and answers aloud.
- Continue a short conversation without reaching for a hotkey for each sentence;
  end it with "that's all" or a timeout and return to wake monitoring.
- Say "open Notepad and write ..." and have IRIS select Notepad, put the text in
  its editor, and confirm the result it can actually inspect.
- Say "open WhatsApp" and use either the installed Windows app or WhatsApp Web,
  according to the owner's preference and what is available. Select a contact,
  dictate, correct, review, and explicitly confirm sending by voice.
- Compose, correct, review, and confirm emails without mandatory button clicks.
- Say "scroll down," "next reel," or "stop scrolling" and affect the intended
  app or browser view, even if another window previously had focus.
- Say "install [app] from Microsoft Store" and have IRIS find the intended
  listing, read back its identity/publisher and any price, request confirmation,
  start the supported installation flow, and report its actual outcome.
- Ask ordinary questions and receive useful spoken answers. Questions requiring
  current information need retrieval with evidence, not merely a search page.
- Say "stop" to interrupt activity and "pause listening" to close the mic.

"Always listening" means wake monitoring while enabled, not continuously sending
room audio to a cloud model. Define separate visible orb states for wake monitoring,
command recording, processing, speaking, and microphone-off. Full privacy pause
closes the microphone and therefore needs a deliberate local control to resume;
ordinary standby keeps wake monitoring available. These are different modes.

The aim is keyboard-free everyday work after setup. Account sign-in, MFA,
Windows secure prompts, and apps without accessible controls can require user
interaction. IRIS must explain a boundary rather than claim universal access or
bypass authentication. Optional setup/review panels may exist on request; they
must not become the required everyday interface.

## Where the project actually stands

**Assessment: a functional voice-assistant prototype with a substantial reusable
foundation, not yet a hands-free desktop operator.** Phases 1–5 have implementation
code, but that does not mean five sevenths of this expanded goal is finished.
Wake activation and reliable control inside applications are major missing pieces.
A precise completion percentage would be misleading without measured workflows.

| Capability | Evidence in this checkout | Gap to the owner's goal |
|---|---|---|
| Floating orb | Animated, draggable, always-on-top Qt orb in `iris/ui/orb.py` | `iris/ui/app.py` still shows the main window at startup; orb-only default must return. |
| Voice input | Local faster-whisper capture/transcription and managed workers in `iris/audio/` | `VoiceController.request_listen()` requires Mic/hotkey activation; no wake detector or always-ready session. |
| Spoken answers | pyttsx3 output with capture/playback exclusion | No interruption listener during speech; busy turns reject new listening requests. |
| Reasoning and questions | Shared Brain with OpenAI/Gemini adapters and bounded tool calls | Recorded question/intent false refusals remain; provider availability still affects commands. |
| App launching | `APP_CATALOG` contains Notepad, Chrome, Edge, Spotify, Word and Excel | No general installed-app discovery, WhatsApp desktop entry, Store launcher, or reliable window targeting. |
| Notepad dictation | Open-app and focused-window typing tools exist; earlier user-reported successes are recorded | Generic typing is limited to 500 printable ASCII characters, without newlines, tabs, Enter, field selection, or content verification. |
| Browser navigation | HTTP/HTTPS opening and search-page dispatch | No page reading, element selection, tab/content inspection, or reliable in-page workflow execution. |
| WhatsApp | Generic `open_url` can request `https://web.whatsapp.com` | No dedicated app/web routing, contact selection, composer control, review/send workflow, or message verification. Opening a URL alone is not WhatsApp automation. |
| Reels and scrolling | Bounded wheel and top/bottom key dispatch | Input is unverified and depends on window focus/pointer position; no reel-aware navigation or continuous scrolling controller. |
| Email | Official Gmail OAuth, secure token storage, local previews, gated draft/save/send code | Real account/API acceptance pending; save/send requires GUI-created approval, so it is not voice-only. Other mail apps/providers lack workflows. |
| Microsoft Store | No registered install workflow | Need app search/identity checks, confirmed install, progress/error handling and installed-app verification. |
| Safety and outcomes | Registry, schemas, permission gate, cancellation, action logs and result statuses | Need those protections across new app workflows; current process/input checks cannot verify document/message contents. |
| Persistent memory | `iris/memory/store.py` and `iris/tools/memory_tools.py` are placeholders | Preferences and explicitly requested memories do not yet survive restart. This is separate from basic desktop control. |
| Daily desktop operation | GUI singleton and owned worker cleanup exist | Startup packaging, saved settings, sleep/resume/device recovery and a full-day reliability run remain to be completed/accepted. |

Evidence levels must stay separate:

- The last recorded offline suite passed **358 tests** on 13 Oct 2026. This audit
  did not rerun tests or exercise the laptop, microphone, accounts, or external APIs.
- Earlier owner reports establish some real voice, Notepad, browser, speech and
  combined Instagram/top-bottom-command successes. They do not prove every app flow.
- Native GUI acceptance, Gmail OAuth/draft/send acceptance, and earlier edge/safety
  checks remain pending in `PHASE2_WINDOWS_CHECKLIST.md`, `PHASE3_ACCEPTANCE.md`,
  `PHASE4_ACCEPTANCE.md` and `PHASE5_ACCEPTANCE.md`.
- Browser and generic input tools correctly report `unverified`; dispatch is not
  proof that the intended window, text field, recipient or page changed.

## What needs to be built next

### 1. Align the experience and establish a baseline

Restore orb-only startup, keep diagnostic/setup panels optional, and record the
existing Windows acceptance results. Fix known intent-routing false refusals and
the missing local route for simple commands when the AI provider is unreachable.
Retain the current gate, logs, cancellation and honest result reporting.

**Exit check:** launch without a terminal/chat window; use the existing basic
commands successfully, with failures and unverified results stated accurately.

### 2. Make activation and conversation hands-free

Add local wake-phrase detection, microphone ownership shared with capture/TTS,
standby versus privacy pause, a short follow-up session, inactivity timeout and
false-trigger handling. Design interruption during speech/long tasks explicitly:
the existing busy-turn exclusion does not provide spoken emergency interruption.
Avoid treating IRIS's own voice or media playback as user approval.

**Exit check:** from another active app, say "IRIS, let's start," issue a command,
ask a follow-up, interrupt speech, and return to standby without clicking. Test
background audio, missed phrases, false wakes, pause and device failures.

### 3. Build app discovery, targeting and observation

Discover supported installed desktop and packaged apps; distinguish installed
apps from websites. Add window enumeration, activation and control inspection.
Use Windows accessibility/UI Automation for semantic controls and browser element
inspection for web flows; use supported app APIs where suitable. These are new
components, not capabilities already supplied by PyAutoGUI or either AI model.

Introduce a bounded observe → choose registered action → act → inspect result loop.
Start with accessible controls; evaluate an explicit screen-reading fallback only
where needed. Screen/email content remains untrusted data, never instructions.
Allow general app launching to expand incrementally; reliable operation inside
every app needs capability detection and supported workflows, not one allowlist edit.

**Exit check:** target Notepad while another app is focused, identify its editor,
write and read back text, and refuse an ambiguous target without typing elsewhere.

### 4. Add useful dictation and task continuation

Support multiline/Unicode text through an appropriate input method, punctuation,
selection, replacement, undo and spoken corrections. Keep text insertion separate
from submission. Track the active task/app and resolve "write this there" or ask a
short clarification. Split longer jobs into bounded stages beyond the current
eight-tool-call turn limit without dropping cancellation or approval boundaries.

**Exit check:** dictate a paragraph in Notepad, add a newline, replace a sentence,
read back the edited result and stop midway without further input being dispatched.

### 5. Complete email and WhatsApp end to end

First validate the existing Gmail account flow. Add trusted voice approval tied
to the exact reviewed recipient/content and operation, with timeout, edit
invalidation, one-use consumption and no automatic retry after uncertain sends.
The model saying "send it" must never count as user approval. Preserve the current
GUI path until a tested replacement exists. Add WhatsApp desktop/web routing,
contact disambiguation, draft editing and equivalent review/confirmation behavior.

**Exit check:** compose, correct, review and explicitly approve a test email/message
entirely by voice. Cancellation, background speech, changed recipients and replayed
approval must not send. Report submission separately from delivery.

### 6. Add browser/media and Microsoft Store workflows

Implement intended-window/page selection, per-command scrolling, next/previous
reel actions and bounded continuous scrolling with spoken stop if requested.
Add a Store-specific workflow for finding, confirming and installing the intended
app, handling unavailable apps, failures, permissions and progress. Do not add
generic arbitrary-shell execution as a shortcut to desktop control.

**Exit check:** voice-scroll the chosen feed and stop promptly; install a confirmed
free test app from Store and verify it can be launched. No unintended purchase or
installation may occur from a misheard name or webpage instruction.

### 7. Harden daily use and add optional memory

Package a convenient desktop launch and opt-in login startup; persist explicit
preferences such as wake phrase and desktop/web app choice. Implement user-requested
memory separately. Add evidence-backed retrieval for current questions. Test
microphone unplugging, sleep/resume, network/provider failures, duplicate requests,
resource usage, worker cleanup and recovery through a full day of use.

**Exit check:** complete the routine workflows without touching the keyboard or
mouse after setup, with documented exceptions and no restart during a full-day run.

## Working agreement for future changes

1. Read `memory.md`, this file, and the existing architecture/rules before work.
2. Prioritize the owner's complete voice workflows over decorative UI additions.
3. Do not describe a mocked test, a registered tool, or an opened app as proof of
   a completed real-world workflow. Keep implemented, tested and accepted separate.
4. Keep confirmations for sending, installing and other consequential actions,
   while making the ordinary review/approval interaction usable by voice.
5. Update the older PRD, design, phase plan and runtime instructions as each new
   feature is implemented. Their historical restrictions must be reconciled with
   this direction explicitly, not silently removed from the running assistant.

The next implementation milestone is **orb-only startup plus wake activation and
hands-free follow-up**, followed by **reliable Notepad targeting/dictation**. Those
milestones establish the interaction and control foundation for mail, WhatsApp,
reels and Store; cosmetic changes alone do not close those gaps.
