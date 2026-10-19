# Phases: IRIS

> Updated destination and milestones, 15 Oct 2026: [IRIS_VISION.md](IRIS_VISION.md). Numbered phases below are the historical plan, not a completion measure for the expanded goal. Prioritize orb-only startup and wake/follow-up interaction, then reliable app targeting/dictation. Existing acceptance gaps remain; no new runtime phase ran in this audit.

Latest explicit request authorizes Phases 4 and 5 in one run despite earlier
pending acceptance checks. Restore main-window startup and orb click-to-open;
use official Gmail OAuth/API rather than browser email automation. Earlier
orb-only instructions are superseded. Neither phase is accepted from mocks.

Build in this order. Finish each phase, run `pytest`, update `memory.md`, then move on. Each phase ends with something that can be tried on the laptop.

## Phase 1: Foundation
**Goal:** a project that starts, reads its settings, and has the safety layer ready.
- Create the folder structure from `Architecture.md`.
- `config.py`: load `.env`, require the selected provider's key (OPENAI_API_KEY by default), mask both provider keys when printed.
- Tool registry with argument checks and permission levels.
- Permission gate (`auto`, `confirm`) and the kill-switch hotkey.
- Action log writer.
- **Done when:** `python -m iris.main --check` shows the settings with the key masked, and tests for the registry, the gate, and the log pass.

## Phase 2: Brain and actions (text only)
**Goal:** type a command and IRIS does it.
- Shared provider tool-calling loop (OpenAI default, optional Gemini; max 8 tool calls) and the system prompt.
- Tools: `open_url`, `web_search`, `open_app`, `scroll`, `press_keys`, `type_text`, `get_time`.
- Verification for each tool and honest wording of results.
- Errors handled as in `Rules.md`.
- **Done when:** typing "open Instagram", "scroll down", "open notepad", and "what time is it" works, and a fake OpenAI client in tests shows that a failed tool is reported honestly.

## Phase 3: Voice
**Goal:** speak to IRIS and hear it answer.
- Hotkey-activated recording, faster-whisper transcription, silence detection.
- pyttsx3 speaker with a queue; the mic is muted while speaking.
- "Stop listening" and "start listening".
- **Done when:** pressing the hotkey, saying "open Gmail", and hearing IRIS reply works, and IRIS does not react to its own voice.

## Phase 4: Orb and main window
**Goal:** the visible IRIS.
- Floating orb as described in `design.md`: always on top, draggable, state colors, red mic dot, right-click menu.
- Main window: big logo, status line, conversation log, text box, Mic and Send buttons.
- Click the orb to open/focus the window; use Mic or Ctrl+Alt+Space to speak (explicit Phase 4 user request).
- **Done when:** the orb changes color as IRIS listens, thinks, and speaks, and the window shows the conversation.

## Phase 5: Email by dictation
**Goal:** write emails by voice, safely.
- Contacts file and spoken address parsing ("john at gmail dot com").
- Prepare subject/body with the existing model, without inventing details; draft_email creates a local editable preview only.
- Official desktop OAuth, secure external token storage, Connect/Disconnect UI, minimum gmail.compose scope.
- Gmail draft/save and send require exact-message GUI approval through the existing gate; edits invalidate approvals. Sending is not exposed to the model, and ambiguous writes are never retried automatically.
- **Done when:** a reviewed draft is saved/sent only after explicit GUI approval, real OAuth/API results are confirmed, and required Windows/security tests pass. Spoken send it cannot authorize sending.

## Phase 6: Memory
**Goal:** IRIS remembers what you ask it to.
- Mem0 with OpenAI provider and local Qdrant.
- `remember`, `search_memory`, `update_memory`, `forget` with read-back checks.
- Recall in answers, and history for updated memories.
- **Done when:** "remember that I prefer Chrome" is saved and read back, survives a restart, and "forget" asks for confirmation.

## Phase 7: Hands-free and polish
**Goal:** use IRIS without touching anything.
- Wake word: say "Iris" and a command. Can be turned off in settings.
- Tune silence detection, speaking speed, and orb animation.
- Handle the error table in `Rules.md` end to end.
- Write a short manual test list for a real laptop.
- **Done when:** the example commands in `PRD.md` section 6 work by voice alone, and a full day of use needs no restart.

## After v1 (not part of the build)
Reminders, screen awareness, routines, Hindi and Telugu commands, calendar.
