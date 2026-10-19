# Heliox-OS compared with the IRIS vision

> Active implementation sequence: [phase.md](phase.md), roadmap R0–R13 (15 Oct 2026). The former Phase 1–7 plan is [archived](PHASES_LEGACY.md); earlier numbered phases below describe prototype history.

Reviewed 15 Oct 2026. Reference commit: `79af30e810600a62c896487c1a8bd0787a11b6e3`.

## Verdict

**Very similar in purpose, with substantially broader desktop-control implementation than current IRIS. It is a strong architectural reference, but not a ready-made implementation of the exact IRIS experience.**

Both aim to turn natural-language voice requests into real desktop actions, with permissions, cancellation, logs and honest outcomes. Heliox already has source for several of IRIS's largest missing components. Its product is a broad desktop command center with additional gesture/gaze/research features; IRIS is intended to be a focused orb-only voice assistant. No numerical similarity score is warranted without an agreed weighting of features and real workflow tests.

## Scope of this review

The requested GitHub CLI was unavailable. Cloned with `git clone --depth 1` into `Heliox-OS-reference/` after the initial sandbox network failure. Inspected source, selected tests, capability documentation and license. Did not install dependencies, run Heliox, execute its tests, start its daemon, grant permissions or access user accounts. Code existence and test assertions are evidence of implementation intent, not proof of successful operation on this laptop.

## Workflow comparison

| Our IRIS requirement | What Heliox source contains | Assessment |
|---|---|---|
| Orb-only everyday interface | Tauri/Svelte command-center frontend; ordinary decorated window configuration, settings and approval dialogs | Different presentation. A custom orb frontend would still be needed. |
| Always-ready wake phrase | `ContinuousVoiceListener`, default phrases hey heliox/heliox/hey pilot; VAD/transcription-based wake matching | Strong architectural match; custom IRIS phrase and hardware behavior need adaptation/testing. This is not proof of a tiny dedicated low-power keyword detector. |
| Follow-up conversation | Bounded follow-up window and optional continuous conversation; TTS overlap suppression | Much closer to our target than IRIS's per-turn hotkey/Mic flow. |
| Interrupt speech/tasks | Barge-in paths and voice dispatch/correction handling with corresponding tests | Relevant implementation exists; actual microphone/noise/echo reliability remains host-dependent. |
| Open installed apps | Windows installed-application discovery, executable and Start-app registrations, ambiguous-target refusal | Broader than IRIS's fixed six-app catalog. Not a promise that every app is controllable. |
| Notepad dictation/editing | Window targeting, UI Automation text read/set paths and input tools | Good foundation for target-and-verify dictation. Correct control discovery, modern Notepad behavior and spoken editing still need real workflow validation. |
| Operate desktop controls | Accessibility snapshots with element refs, stale-window rejection, focus/window management, screenshots/OCR and bounded autonomous execution | Directly relevant to IRIS's missing observation/control layer. |
| Operate web apps | Playwright browser backend, navigation, element snapshots, typing, extraction, tabs and scrolling | Much more capable than IRIS's URL/search dispatch. Existing signed-in browser sessions and specific websites still need validation. |
| Emails | Email specialist supports IMAP/SMTP with app-password/keyring configuration and confirmed sending | Similar task coverage, different integration from IRIS's Gmail OAuth/API. It is not a drop-in Gmail-service replacement. |
| WhatsApp desktop and Web | General app/browser primitives; planner text mentions `api_whatsapp`, but no corresponding dedicated action/provider was found in the inspected action/catalog/runtime searches | Potential building blocks, not a demonstrated contact-select, compose, edit, review and send workflow. A prompt mention is not implementation. |
| Reels scrolling | Mouse/browser scroll and keyboard actions | General scrolling exists; no dedicated reel-aware end-to-end workflow established in this review. |
| Microsoft Store installs | Windows package operations use WinGet, with Chocolatey fallback | Partial match. Inspected install path does not explicitly select `msstore` or implement listing/publisher/price review in the Store UI. A package tool alone does not establish our Store workflow. |
| Completely voice-only approvals | Explicit server boundary and regression tests deny speech-based approval and direct the user to a visible confirmation dialog | Important mismatch. Spoken refusal/cancellation is distinct from approval. Sending/installing can still require manual interaction. |
| Memory, recovery, packaging | Durable state, memory, background jobs, audit and packaged desktop architecture | Broader implementation surface than current IRIS. Much of the extra gesture/gaze/neural/plugin scope is unnecessary for our immediate goal. |

## Evidence and limits

The repository reports 162 declared actions but only 22 with an independent observed post-condition verifier; the other 140 rely on executor results. These are upstream-reported figures at the inspected commit, not counts verified by running the application. Its proof document explicitly separates software tests from physical microphone, speaker, accessibility and human accuracy evidence.

The strongest conclusion is **ahead of IRIS in implementation breadth**, not proven ahead in end-to-end success on this laptop. Neither a large catalog nor a passing mock test establishes reliable WhatsApp, Store, or full-day hands-free operation.

## What IRIS should learn from it

1. Study continuous voice ownership, follow-up windows, suppression of TTS echoes and cancellation before adding wake activation to IRIS.
2. Study Windows app discovery and unambiguous target resolution rather than expanding a hardcoded app list indefinitely.
3. Add window targeting plus accessible-control snapshots and stale-target rejection before broad desktop typing/clicking.
4. Add a browser adapter with observable page state; opening a URL is not browser automation.
5. Preserve bounded observe-act-check loops, cancellation and outcome evidence rather than relying on model completion claims.
6. Treat trusted voice approval as a separate IRIS engineering task: Heliox's visible-dialog policy does not solve it.

Keep the existing IRIS orb and reusable voice/Brain/gate/Gmail work. Adapt small components behind IRIS's registered tool boundary after reviewing their dependencies and behavior. Wholesale integration would bring a different frontend, daemon/protocol, configuration and permission model; it is not automatically faster or safer than incremental adaptation.

The clone contains an MIT license. Preserve its copyright and license notice if substantial code is reused. No code was copied into IRIS runtime during this review.

## Source map (pinned to the inspected commit)

- [Overview and architecture](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/README.md)
- [Continuous voice, follow-ups and speech coordination](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/system/voice.py)
- [Voice approval rejection regression](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/tests/test_voice_command_dispatch.py)
- [Installed application discovery](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/system/applications.py)
- [Accessibility snapshots and stale-target handling](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/system/accessibility.py)
- [Window targeting and text read/write](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/system/window_mgr.py)
- [Browser implementation](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/system/browser.py)
- [Package manager implementation](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/system/package_mgr.py)
- [Email specialist](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/daemon/pilot/agents/email_agent.py)
- [Desktop window configuration](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/tauri-app/src-tauri/tauri.conf.json)
- [Evidence and known limits](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/proof.md)
- [License](https://github.com/VyomKulshrestha/Heliox-OS/blob/79af30e810600a62c896487c1a8bd0787a11b6e3/LICENSE)
