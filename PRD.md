# PRD: IRIS

## Active implementation update — 15 Oct 2026

R1 restores orb-only GUI startup/click-to-listen, with chat/setup on the orb menu.
Simple exact local time/app/URL/scroll/key commands do not require cloud access;
other requests use the explicitly selected provider. Missing cloud configuration
does not prevent startup. Generic browser/input actions remain unverified, and
email approval remains GUI-only. Wake/session/app observation milestones are
still pending; see the R-roadmap acceptance records for measured results.

> The following prototype notes are historical where they conflict with the active update above.

> Active implementation sequence: [phase.md](phase.md), roadmap R0–R13 (15 Oct 2026). The former Phase 1–7 plan is [archived](PHASES_LEGACY.md); earlier numbered phases below describe prototype history.

> Product direction updated 15 Oct 2026: [IRIS_VISION.md](IRIS_VISION.md) defines the current orb-only, wake-activated desktop-assistant goal, including voice workflows, WhatsApp and Microsoft Store. Conflicting scope/UI statements below describe the earlier version. The missing features are planned, not implemented.

Product requirements for IRIS, a Jarvis-style voice assistant for the desktop.
Version 1.0, written 13 Oct 2026.

Latest explicit Phase 4/5 request overrides the original browser-email flow below:
use official Gmail desktop OAuth and minimum gmail.compose scope. Prepare editable
local previews; save or send only after an exact-message GUI approval through the
existing gate. Spoken send it cannot approve. Never request Google passwords.
Gmail message ID confirms submission, not delivery. Inbox scraping, automatic
replies, bulk sending and Phase 6/7 features remain outside this implementation.

## 1. Summary

IRIS is a voice assistant that lives on a Windows laptop as a small floating orb. The user speaks, IRIS listens, does the task (open a site, open an app, scroll, write an email), and answers out loud. It remembers what the user asks it to remember. The user should not need the keyboard for everyday tasks.

## 2. Target users

**Primary**
- Students and working professionals who spend most of their day in a browser and email and want to do routine tasks hands-free.
- Multitaskers and creators whose hands are busy (typing, drawing, cooking, presenting).

**Secondary**
- People who want to reduce keyboard and mouse use, for example because of wrist strain.

**First user:** the project owner, on a Windows 10/11 laptop with a microphone and internet access.

## 3. Problems IRIS solves

- Everyday tasks (open Gmail, scroll a page, write a short email) need many small clicks and keystrokes.
- Existing voice tools answer questions but do not control the laptop.
- Assistants often say "done" when nothing happened. IRIS must check first.

## 4. Goals and non-goals

**Goals (v1)**
- Speak to the laptop and get things done without touching the keyboard.
- Spoken answers, not just text.
- A floating orb that is always visible and shows what IRIS is doing.
- Emails written by dictation, sent only after the user confirms.
- Honest results: IRIS says "done" only when it has checked.

**Non-goals (v1)**
- Controlling any app by clicking arbitrary screen positions.
- Reading the screen or screenshots.
- Deleting files, buying things, filling forms, or changing system settings.
- Mac, Linux, phone, or multi-user versions.
- Training or fine-tuning models.

## 5. Features

Priority: **Must** is needed for v1. **Should** is v1 if time allows. **Later** is after v1.

| ID | Feature | Priority | Acceptance check |
|---|---|---|---|
| F1 | Floating IRIS orb (always on top, draggable, color shows state) | Must | Orb stays above other windows, can be dragged, and changes color for idle, listening, thinking, speaking. |
| F2 | Voice input (click the orb or press a hotkey, then speak) | Must | A spoken phrase becomes text and runs as a command. |
| F3 | Spoken replies | Must | Every reply is spoken aloud and shown in the log. IRIS does not hear itself. |
| F4 | Open websites ("open Instagram", "go to github.com") | Must | The site opens in the default browser. |
| F5 | Open apps ("open Notepad", "open Spotify") | Must | The app starts. IRIS confirms by checking that it is running. |
| F6 | Scroll and basic keys (scroll up/down/top/bottom, new tab, close tab, go back, volume) | Must | The focused window scrolls or reacts. Only allowlisted keys are used. |
| F7 | Email by dictation | Must | IRIS asks who and what, opens a Gmail draft, reads the subject back, and sends only after "send it". |
| F8 | Questions and web search | Must | IRIS answers in one to three spoken sentences. "Search for X" opens results. |
| F9 | Memory ("remember that I prefer Chrome", "what do you remember about me?") | Must | The fact is saved only when asked, read back to confirm, and recalled after a restart. |
| F10 | Main window (big IRIS logo, status, conversation log, text box) | Must | Shows the log and lets the user type commands. |
| F11 | Pause and kill switch ("stop listening", Ctrl+Alt+Esc) | Must | The microphone closes and the current task stops. |
| F12 | Action log (every action and result saved) | Must | `data/actions.log` lists what ran and whether it was verified. |
| F13 | Wake word: say "Iris" with no click | Should | Saying "Iris, open Gmail" works hands-free. Can be turned off. |
| F14 | Forget and update memories by voice | Should | Forget asks for confirmation first. Updates keep the old value in memory history. |
| F15 | Reminders ("remind me at 5pm to call Priya") | Later | |
| F16 | Screen awareness ("what am I looking at?", opt-in) | Later | |
| F17 | Custom routines ("start my coding session") | Later | |
| F18 | Hindi, Telugu, and mixed-language commands | Later | |

## 6. Example commands

- "Iris, open Instagram."
- "Iris, scroll down a lot."
- "Iris, open Gmail."
- "Iris, write an email to Priya saying the meeting moved to Monday."
- "Iris, search for biryani near me."
- "Iris, what is the weather in Hyderabad?"
- "Iris, remember that I prefer Chrome for work."
- "Iris, stop listening."

## 7. Key user flows

**Open something:** user speaks, IRIS opens it, checks it opened, and says so. If it cannot confirm, IRIS says "I tried to open it but could not confirm."

**Email:**
1. User: "Write an email to Priya saying I'll be late."
2. IRIS finds the address in contacts. If unknown, it asks and the user says it ("priya at gmail dot com").
3. IRIS writes a clean subject and body from what the user said, without inventing details.
4. IRIS opens the Gmail draft and reads the subject back.
5. IRIS asks: "Say send it to send, or cancel." Only "send it" sends.
6. IRIS says it pressed send and tells the user to check the Sent folder, because it cannot verify delivery.

**Memory:** user says "remember ...". IRIS saves it, reads it back to confirm, and replies "Saved." Without a spoken or typed "remember", nothing is saved.

## 8. Success metrics

- Basic commands (open site, open app, scroll) succeed on at least 9 of 10 attempts in a quiet room.
- No email is ever sent without a confirmation.
- IRIS never reports success for an action it could not check.
- Time from the end of the user's sentence to the start of IRIS acting is under 4 seconds for simple commands.
- IRIS runs for a full day without needing a restart.

## 9. Assumptions and constraints

- Windows 10/11, Python 3.11, a working microphone and speakers.
- Internet is needed for the selected AI provider and for opening web pages.
- OpenAI is the default brain; the user may explicitly select Gemini. Provider keys are the user's own and are loaded from `.env` or process settings, never printed or logged.
- Speech recognition runs locally on the laptop.
- Gmail is used through the browser. The user must already be signed in.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Mishearing names and email addresses | Read back the subject, repeat the address, and ask for confirmation before sending. |
| Scroll or keys hit the wrong window | Act only on the focused window and say what was done. |
| Prompt injection from web pages or emails | Outside text is treated as information only and never changes the rules. |
| Microphone always open feels invasive | Visible red dot on the orb, a pause command, and nothing recorded to disk. |
| API cost | Short prompts, short replies, and a step limit per command. |
