# IRIS: step-by-step implementation phases

Version 2, 15 Oct 2026. **Active roadmap. Current implementation: R3 development/evaluation (16 Oct).**

Implementation authorized by the owner's subsequent 15 Oct request. R0 baseline
and R1 runtime changes passed automated checks (359 and 384 tests respectively);
native/account checks remain explicit in their ROADMAP acceptance records. R2
audio foundation passed 405 tests; device acceptance remains pending. R3 requires
a custom wake model and representative held-out audio. Later phases remain planned. Documentation-only
authorization statements below describe the earlier planning request.

This plan combines [the vision](IRIS_VISION.md), [the Heliox comparison](HELIOX_COMPARISON.md),
and [the integration report](IRIS_INTEGRATION_REPORT.md), including the subsequent
Gemini-free-first direction. The former Phase 1–7 plan is preserved in
[PHASES_LEGACY.md](PHASES_LEGACY.md). Use the new **R0–R13** identifiers to avoid
confusing existing prototype work with completion of this expanded roadmap.

This document plans implementation; creating it did not implement any phase.

## Destination and scope

An orb-only Windows assistant that locally monitors for "IRIS, let's start,"
accepts voice follow-ups, answers questions, controls supported desktop/web apps,
dictates and edits text, composes mail/messages, scrolls feeds and installs a
confirmed app from Microsoft Store. Everyday operation should need neither
keyboard nor mouse after setup. Account sign-in, MFA, Windows secure prompts and
unsupported app controls remain explicit user-interaction boundaries.

Keep the existing orb, Brain, registry, permission gate, audit log, local Whisper,
Windows speech output and Gmail OAuth implementation. Use Heliox selectively as
an architectural reference. Evaluate LiveKit WakeWord against openWakeWord and
choose one runtime. Start desktop control with a pywinauto UIA adapter; evaluate
uiautomation only where control inspection justifies an alternative.

Gemini is the planned first cloud reasoning provider within an eligible free-tier
allowance. Paid OpenAI/Claude access is not a project prerequisite. Wake inference,
transcription, speech output and desktop execution should be local. Add deterministic
routes for simple commands so provider outages/quotas do not prevent local work.
Do not silently change current provider/model settings, enable billing, or promise
unlimited free use. The existing runtime still defaults to OpenAI unless configured
otherwise; this roadmap does not itself change that default.

## Current evidence and how to use this plan

The prototype contains the old foundation, tool loop, voice, desktop UI and Gmail
code. The last recorded offline suite was 358 passing tests on 13 Oct 2026; that
is historical evidence, not a new run or end-to-end laptop acceptance. Wake detection,
general app observation/control, voice approval, WhatsApp workflows and Store
installation remain missing. Existing safety/device/provider issues stay open.

Work in numbered order by default. A phase can use completed earlier capabilities,
but cannot claim a later workflow merely because its underlying tools exist.
Before implementation, read memory, this plan, the vision, integration report and
relevant architecture/rules. This request authorizes phase documentation only.
Future implementation requests can authorize one phase or a stated sequence;
ordinary reversible work inside that scope should proceed without repeated approvals.

Use these statuses in each phase record: **planned → implementing → implemented →
automated checks passed → Windows accepted**. Record a blocked item separately
with its precise dependency. Only mark a phase complete when its exit checks pass;
otherwise retain pending acceptance. No new R phase is marked complete here.

For each phase, create `ROADMAP_Rn_ACCEPTANCE.md` when implementation begins. Record
build/revision, environment, changes, test command/result, real-laptop checks,
provider calls used, failures and remaining limits. Update memory and relevant
PRD/architecture/design/rules with the actual resulting behavior. Historical
acceptance records remain available; obsolete startup expectations should be
explicitly mapped to their new replacements rather than blindly rerun.

## Phase overview

| Phase | Outcome | Entry dependency | Initial status |
|---|---|---|---|
| R0 | Reproducible baseline and carried-forward acceptance | Existing checkout | Automated checks passed |
| R1 | Orb-only UI and local commands without AI calls | R0 | Automated checks passed; Windows pending |
| R2 | One microphone owner and bounded audio lifecycle | R1 | Automated checks passed; device pending |
| R3 | Evaluated custom IRIS wake activation | R2 | Development train/export/compare passed; model accuracy/owner acceptance pending |
| R4 | Follow-ups, interruption and pause semantics | R3 | Planned |
| R5 | Installed-app discovery and observed Windows controls | R4 | Planned |
| R6 | Verified Notepad dictation and corrections | R5 | Planned |
| R7 | Observable browser tasks and grounded questions | R6 | Planned |
| R8 | Trusted voice review/approval and Gmail workflow | R7; existing Gmail acceptance | Planned |
| R9 | WhatsApp desktop and Web workflows | R8 | Planned |
| R10 | Intended-feed scrolling and reels controls | R9 | Planned |
| R11 | Reviewed Microsoft Store installation | R10; R8 approval contract | Planned |
| R12 | Saved preferences and explicit user memory | R11 | Planned |
| R13 | Packaging, recovery and full-day acceptance | R12 | Planned |

### R0 — Establish the baseline

**Goal:** know what works before changing capture, permissions or desktop control.

1. Inventory runtime, dependencies, Python version, selected provider and existing
   tests without exposing credentials or changing configuration.
2. Run the current offline suite and dependency checks; compare new failures with
   the historical result. Record the available Python 3.12 environment separately
   from the Python 3.11 project target.
3. Carry findings from PHASE2_AUDIT, PHASE2_WINDOWS_CHECKLIST and Phase 3/4/5
   acceptance records into one baseline list: focus, routing, shutdown, kill switch,
   logging failures, native UI and Gmail account setup/results.
4. Run safe local checks. Account consent/sign-in needs the owner's interaction;
   a live send must use an explicitly reviewed test message and normal approval.
   Keep unrelated account acceptance pending without blocking independent audio work.
5. Establish non-content telemetry for latency, API request counts and worker
   lifecycle. Check that reference clones are not collected as IRIS tests/packages.

**Deliverables:** baseline acceptance record, dependency/runtime inventory and
prioritized defect list. No decorative UI changes or new app automation.

**Exit checks:** current automated baseline is reproducible; failures are fixed or
explicitly carried with scope; cancellation/secret handling has no unresolved
critical regression. Native/account checks that need owner action are named and
assigned to the phase that depends on them, not silently passed.

### R1 — Orb-only startup and a local command route

**Goal:** see only the orb and perform basic supported actions without model usage.

1. Restore orb-only launch; keep chat, setup and diagnostics available on request.
   Preserve drag, state indicators, reduced motion, singleton and graceful exit.
2. Add a conservative local router for stop/pause, time, supported app names,
   explicit URLs and named bounded scroll/key actions. Ambiguous wording goes to
   clarification or the selected provider, never guessed execution.
3. Route local actions through the same schemas, registry, gate and audit log.
   Do not mark dispatch-only results verified or bypass current input restrictions.
4. Repair known question/capability false refusals without weakening result-based
   success reporting. Add sanitized counts showing local versus provider routing.
5. Allow local startup/actions without requiring a cloud key; cloud requests must
   explain missing configuration. Keep existing `--check` masking behavior safe.

**Files:** `iris/main.py`, `iris/config.py`, `iris/ui/app.py`, `iris/brain/brain.py`;
proposed local command router module. Extend prompts only to reflect real tools.

**Exit checks:** launch without a terminal/main window; open Notepad/read time via
local routing with the provider unavailable and zero provider calls. Existing
scroll/typing remains unverified until target inspection is implemented.

**Demo:** activate by existing Mic/hotkey, then say "open Notepad" with network off.
Wake activation is deliberately not claimed yet.

### R2 — A single owned audio pipeline

**Goal:** prepare ambient audio without competing mic streams or frozen UI.

1. Define a capture adapter that owns one 16 kHz mono microphone stream in a
   cancellable worker, preserving bounded stop/reap behavior.
2. Add a bounded RAM ring buffer/pre-roll, overflow handling and frame conversion:
   existing float32/100 ms capture must support detector-specific frame contracts.
3. Refactor `Ears` to accept command audio from that owner rather than opening a
   second stream; keep Whisper local and only transcribe explicit command turns.
4. Add VAD endpointing and bounded no-speech/max-utterance handling. Test the VAD
   choice separately from keyword detection; neither is a command interpreter.
5. Connect actual mic-open state to the orb. Privacy pause closes capture and
   clears buffered audio; stop/device failure releases resources.

**Files:** proposed `iris/audio/capture.py`; existing `ears.py`, `worker.py`,
`voice.py`, `speaker.py` and queued UI signals. No separate PyAudio listener.

**Exit checks:** one active mic owner across activations; bounded memory; immediate
post-activation speech retained; pause/kill closes the mic; unplugged/hung devices
produce controlled failure and no orphan worker. Tests inject audio/driver faults;
real device behavior also needs recorded Windows checks.

### R3 — Custom wake phrase and engine selection

**Goal:** wake locally on "IRIS, let's start" without continuous Whisper inference.

1. Define a swappable wake detector interface with predict/reset/close and pinned
   model metadata. Inspect model/data terms, sizes and hashes before packaging.
2. In a separate training environment, prepare the requested phrase, representative
   positive/negative data and a held-out owner test set. Use LiveKit's training/export
   pipeline as a candidate; do not install all training extras into IRIS runtime.
3. Compare LiveKit ONNX inference with openWakeWord's streaming path on common
   audio. Verify classifier/front-end compatibility; do not assume every export
   or a default existing model detects the custom phrase.
4. Measure recall, false wakes/hour, latency, idle CPU/RAM and battery impact.
   Check long/slow pronunciations against the chosen inference window.
5. Select one engine, tune threshold/debounce/reset and connect wake events to R2
   capture. Retain pre-roll for "IRIS, let's start, open Notepad" in one utterance.
6. Keep missing-model errors local and clear; runtime must not silently download
   assets or switch models/providers. A different phrase requires an explicit choice.

**Files:** proposed `iris/audio/wake.py`, training configs/artifact manifest outside
runtime dependencies, wake settings in `iris/config.py`.

**Exit checks:** use a proposed minimum 100 held-out natural utterances with at
least 90% recall and an initial eight-hour representative negative-audio run with
no observed false wake. These are project targets, not prior results or a proof
of zero false-wake probability. Record measured latency/resources and choose
budgets before accepting. No wake hit itself executes a consequential action.

### R4 — Conversation, interruption and privacy modes

**Goal:** have a short conversation and stop IRIS without another click.

1. Implement standby, capture, processing, speaking, follow-up, privacy-paused and
   stopped transitions under one session coordinator and existing Brain ownership.
2. Arm a bounded wake-free follow-up after responses; expire on silence or "that's
   all." Discard stale audio/jobs after cancellation or a session change.
3. Implement spoken stop with priority during capture, reasoning, tools and speech.
   Revise the current busy/speaking rejection deliberately, not by bypassing its lock.
4. Add barge-in and TTS/media rejection. Distinguish interrupting narration from
   granting any new tool permission; speech output cannot approve actions.
5. Keep "go to standby" distinct from "pause listening." Privacy pause needs a
   deliberate local resume control because a closed mic cannot hear a wake phrase.

**Files:** proposed `iris/audio/session.py`; existing voice/speaker/worker and orb
state integration. Update actual microphone/permission rules when implemented.

**Exit checks:** wake → command → follow-up → interruption → standby works without
hotkeys. Playback/TV does not execute unintended tasks; privacy pause opens no mic;
kill remains usable independently. Measure stop latency rather than promising a
hard cancellation of an OS/network effect already dispatched.

### R5 — App discovery, targeting and control observation

**Goal:** identify the intended app/window/control before interacting.

1. Add bounded discovery of installed desktop and packaged Windows apps, learning
   from Heliox's registration resolution. Refuse missing/ambiguous names.
2. Add window listing, attachment and activation with process/window identity;
   handle existing single-instance apps rather than expecting a new process.
3. Implement a pywinauto UIA adapter with bounded searches and waits; inspect
   Win32 or uiautomation only for demonstrated coverage gaps.
4. Create limited snapshots of control identity, role/name and supported patterns.
   Bind references to window/process/generation and reject stale/password targets.
5. Register narrow observation/focus/control tools through the gate. Isolate native
   UIA/COM work from Qt and terminate/recover from hung providers safely.
6. Add a bounded observe → choose registered action → act → inspect-result loop
   with no-progress/step/time limits. Do not enable arbitrary model-written code.

**Files:** proposed `iris/desktop/adapter.py`, `iris/tools/desktop.py`; existing
`tools/apps.py`, registry and action log. Preserve notices for reused upstream code.

**Exit checks:** resolve Notepad from another active app, identify the intended
editor among two windows/tabs, refuse stale/ambiguous controls and explain unsupported
apps. No coordinate guessing or unbounded full-desktop content dumping.

### R6 — Verified Notepad dictation and corrections

**Goal:** reliably write and edit real text using voice.

1. Build a Notepad adapter for the installed version using supported patterns;
   do not assume old Win32 examples fit modern Windows 11 tabbed Notepad.
2. Support multiline Unicode and punctuation with target-bound insertion. Read
   back contents independently; preserve `unverified` if inspection is unavailable.
3. Add selection, replace sentence/word, append, newline and undo. Keep session
   context tied to the active document; ask when "change that" is ambiguous.
4. Add short clarification for writing versus replacing existing text. Keep text
   insertion separate from Enter/submission and intentional file-save workflows.
5. Stage long dictation/jobs with bounded actions and progress. Preserve the current
   eight-tool-call turn cap unless a separately bounded job contract replaces it.

**Exit checks:** from another foreground app, dictate a paragraph, add a newline,
replace a sentence, undo and verify the final buffer without mouse/keyboard input.
Test two documents, unsupported patterns, existing text, focus changes and stopping
mid-edit. Word requires its own adapter/acceptance before claiming equivalent support.

### R7 — Observable browser workflows and useful questions

**Goal:** control pages and answer questions without pretending a search page is evidence.

1. Add a browser adapter with an explicit supported browser/profile attachment
   policy. Preserve sign-in boundaries; do not expose unrestricted scripting tools.
2. Observe tabs/pages and elements; perform navigation, field insertion, selection,
   extraction and scroll through fresh scoped references and the registry.
3. Add before/after evidence, timeout/stale-reference handling and no-progress
   termination. Never replay an ambiguous external write just because the DOM
   did not visibly change.
4. Keep ordinary questions with Gemini; use bounded retrieval with source/time
   evidence for current questions. If retrieval is unavailable, state the limit.
5. Measure provider request/token use per workflow, keep context bounded and return
   quota/service failures clearly. Do not auto-enable billing or change providers.

**Exit checks:** choose the intended tab, fill a non-submitting test field and read
it back, navigate/scroll without affecting another tab, and answer a current-information
test only from retrieved evidence. Local R1 commands still work during quota outage.

### R8 — Trusted voice approval and complete Gmail flow

**Goal:** review, correct, save or send an email entirely by voice after account setup.

1. Complete pending real Gmail OAuth/storage/draft acceptance before voice writes;
   preserve minimum scope, DPAPI storage and the existing API service.
2. Define a reviewed immutable operation snapshot containing exact account,
   recipients, subject/body and action. Read it back in manageable spoken portions
   on request; concise summaries cannot silently hide changed recipients/content.
3. Add a trusted approval state separate from model conversation. Accept only a
   deliberate response to the active reviewed operation, after narration finishes,
   tied to session/turn/request/snapshot, one-use and at most 30 seconds old.
4. Implement cancellation, corrections and expiry; any edit invalidates review
   and approval. Replayed, model-generated, page-sourced or overlapping TTS input
   cannot authorize. Evaluate background speech/replay; keyword matching alone
   is insufficient. If rejection is not reliable, keep GUI approval and phase pending.
5. Integrate the tested voice path with the existing gate/jobs. Only then revise
   GUI-only constraints across rules/prompts/UI; preserve GUI fallback.
6. Execute once, never automatically retry uncertain writes. Distinguish draft
   creation/message submission from recipient delivery; keep email fields out of logs.

**Exit checks:** dictate to an owner-approved test recipient, correct address/body,
review and explicitly save/send by voice. Expiry, changed snapshot, double approval,
background audio, stop and uncertain results never cause an extra send. Account
consent remains an explicit setup interaction, not a keyboard-free guarantee.

### R9 — WhatsApp desktop and WhatsApp Web

**Goal:** open the chosen WhatsApp surface and compose/edit/send a reviewed message.

1. Add explicit desktop-versus-web choice and preference; do not silently switch
   accounts/surfaces on failure. Detect signed-out/unavailable states.
2. Inspect actual desktop UIA controls and web elements; implement each surface
   separately, including unsupported-version errors.
3. Select a contact using visible identity evidence and clarify duplicates. Draft
   text in the identified composer, support corrections and read back the result.
4. Use R8's operation-bound approval contract for exact contact/account/content;
   do not send by generic Enter or expose an unrestricted messaging tool.
5. Inspect submission evidence and handle uncertain results without retrying.
   Avoid claims about delivery/read receipts unless actually observed.

**Exit checks:** owner-controlled desktop and web test conversations each complete
open → select → dictate → correct → review → confirm → submit. Signed-out, duplicate
contacts, changed chats, duplicate requests and cancellation produce no wrong send.

### R10 — Voice scrolling and reels navigation

**Goal:** scroll the intended feed and stop promptly.

1. Target the intended app/tab/feed using R5/R7; route basic unambiguous scrolling
   locally once target context is valid.
2. Add bounded up/down and next/previous reel actions for explicitly supported
   surfaces. Do not assume mouse wheel equals next reel everywhere.
3. Add continuous scrolling only when requested, with finite duration/step caps,
   progress checks and spoken stop priority. Stop when the target changes/disappears.
4. Verify visible movement/reel identity where possible; otherwise report input
   dispatch as unverified. Do not depend on the owner hovering the pointer manually.

**Exit checks:** select a test feed, move through content by voice, reverse direction
and stop without mouse use. Other foreground windows, media playback and closed
feeds must not receive unintended repeated input.

### R11 — Microsoft Store discovery and confirmed installation

**Goal:** install the exact reviewed app through a supported Store-specific path.

1. Discover/open Microsoft Store and inspect search/listing capabilities. Choose
   UIA/Store-specific integration based on tested evidence; Heliox's generic
   WinGet/Chocolatey install is not acceptance of this workflow.
2. Resolve exact app identity, publisher, source and displayed price. Clarify
   similar names; unsupported/unknown listings must not auto-install.
3. Review the immutable install operation and request R8-style explicit approval.
   Initial scope is free apps; paid purchases stay outside this roadmap.
4. Start a fixed supported installation action through the registry. Add progress,
   timeout, error and permission/sign-in boundaries; never expose arbitrary shell code.
5. Verify installed registration and launchability. On ambiguous completion,
   inspect state before a deliberate retry; cancellation cannot undo an already
   submitted installation or bypass Windows secure prompts.

**Exit checks:** install an owner-approved free test app, verify its identity and
launch it. Wrong-name, cancelled/expired approval, existing installation, source
ambiguity, unavailable app and network failure do not install an unintended app.

### R12 — Persistent preferences and requested memory

**Goal:** preserve deliberate choices and facts without introducing a paid dependency.

1. Persist explicit settings: wake/model choice, microphone, orb position/reduced
   motion, app/web preference and opt-in login startup choice. Exclude secrets and
   do not persist transient approvals or room audio.
2. Implement explicit remember/search/update/forget with read-back and confirmed
   forgetting; never silently turn transcripts/emails into permanent memory.
3. Start with a simple local store and local search; the old mandatory Mem0/OpenAI
   embedding plan is superseded for this milestone. Add vector memory only if
   measured needs justify it without making paid API access a requirement.
4. Add schema migration, corrupt-store recovery, bounded retention and user-visible
   review/reset controls. Treat recalled content as data rather than authority.

**Exit checks:** remembered preference survives restart and is recalled accurately;
update is read back, forgetting requires confirmation, declined/cancelled writes
leave no memory, and no cloud key is needed for persistence.

### R13 — Desktop packaging and full-day release acceptance

**Goal:** use the complete supported workflows routinely after setup.

1. Package a convenient terminal-free Windows launch with pinned runtime dependencies
   and a separately managed licensed model bundle. Exclude reference clones,
   training tools, private data and credentials from the application distribution.
2. Provide setup for microphone/model availability, Gemini configuration, Gmail
   consent and optional login startup. Keep normal interaction orb-only.
3. Handle sleep/resume, device unplug/replug, network/quota failures, worker crashes,
   duplicate instances, interrupted jobs and safe shutdown/restart.
4. Run the acceptance matrix below, including at least 10 repetitions of basic
   supported actions with at least 9 successful outcomes; count unverified actions
   separately from independently observed successes.
5. Run a full-day soak (at least eight hours) with real routine use, record CPU/RAM,
   battery and latency against budgets established in R0/R3, and check for leaked
   workers/mic ownership. Record provider usage instead of assuming free-tier fit.
6. Publish the supported-app/version list, setup exceptions, known limits and
   measured results. Retain GUI/manual fallback for genuinely unsupported boundaries.

**Exit checks:** all required phases have relevant automated and Windows evidence;
no critical unresolved send/install/cancellation/secret-handling defect; supported
routine flows complete by voice after setup; no restart required during the soak.
Never claim universal control of every installed application.

## End-to-end release matrix

| User request | Required observed result | Owning phases |
|---|---|---|
| "IRIS, let's start" | One wake/session; no continuous Whisper/model calls | R2–R4 |
| "Open Notepad and write ..." | Correct editor contains read-back-matching multiline text | R5–R6 |
| "Replace the last sentence ..." | Correct document edited and verified | R6 |
| "What time is it?" / "Scroll down" | Eligible simple command uses zero provider calls | R1, R10 |
| "Explain ..." / current-information question | Useful answer or sourced current evidence; no invented live facts | R1, R7 |
| "Write an email ... send it" | Exact reviewed snapshot submitted once after trusted confirmation | R8 |
| "Open WhatsApp ... message ..." | Chosen surface and intended contact; reviewed message submitted once | R9 |
| "Next reel ... stop scrolling" | Intended feed changes; stop prevents further dispatch | R10 |
| "Install [app] from Microsoft Store" | Correct free listing approved, installed and launchable | R11 |
| "Remember I prefer WhatsApp desktop" | Explicit fact persists; forgetting is confirmed | R12 |
| "Pause listening" | Mic closed, buffer cleared; deliberate local resume required | R2, R4 |
| Provider outage / sleep / mic unplug | Local commands retained where possible; recovery or clear limit | R1, R13 |

## Phase completion checklist

- [ ] Implement the listed outcome without unrelated feature expansion.
- [ ] Add meaningful logic/security/regression tests for changed behavior; keep
      provider/hardware mocks offline. Do not add tests that only mirror code.
- [ ] Run affected checks and the required IRIS suite; record exact results.
- [ ] Run and record the relevant native Windows/app/account checks, or leave
      acceptance explicitly pending. Never label mock success as hardware success.
- [ ] Reconcile affected rules/prompts/docs with the new behavior before activating it.
- [ ] Record references, dependency/model versions, notices, budgets and limitations.
- [ ] Update `memory.md` and the phase acceptance record; identify the next dependency.

The next implementation request should start with **R0**, then **R1–R4** for the
first wake-activated orb milestone and **R5–R6** for verified Notepad work.
