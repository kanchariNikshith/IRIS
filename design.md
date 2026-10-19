# Design: IRIS

## Active R1 behavior — 15 Oct 2026

GUI startup and duplicate-instance recovery expose only the orb. Click invokes
the existing one-turn microphone controller; drag/recovery never record. The
right-click menu opens chat/setup/Gmail on request. Errors/notice tooltips and
compact permission dialogs remain available without opening chat. Requested
email preview deliberately opens review. No decorative orb changes in R0/R1.

> The following prototype notes are historical where they conflict with the active update above.

> Active implementation sequence: [phase.md](phase.md), roadmap R0–R13 (15 Oct 2026). The former Phase 1–7 plan is [archived](PHASES_LEGACY.md); earlier numbered phases below describe prototype history.

> Latest owner direction, 15 Oct 2026: [IRIS_VISION.md](IRIS_VISION.md) supersedes earlier startup preferences below. Everyday IRIS should show only the orb, with wake activation and voice follow-ups. Setup/review panels may be optional. Runtime still opens the main window; this request changed documentation only.

Latest Phase 4/5 request supersedes orb-only mode: show the main window on startup,
orb click opens/focuses it, Mic/hotkey listens. Keep revolving cyan HUD artwork and
gentle idle breathing; reduced motion/paused/hidden stops updates. Gmail connection
status/button belongs to the existing header. A matching dark review dialog contains
recipient/subject/plain body, Prepare locally, Save Draft, Send and Cancel. A separate
read-only full-message confirmation uses the exact snapshot and expiry countdown.

Latest motion override: the user requested a revolving/orbiting AI core. Segmented
HUD rings rotate around stationary glass shading and I.R.I.S. text; two luminous
satellites orbit along tilted elliptical tracks. A 33-ms Qt timer advances rotation
at 12 degrees/sec idle, 20 listening, 38 processing, 18 speaking and 8 error.
Paused, hidden and reduced-motion states stop the timer. This supersedes earlier
idle-still instructions; no voice/permission or provider behavior changes.

Visual override, 13 Oct 2026: the user supplied a cyan futuristic I.R.I.S. HUD
reference and requested a 3D appearance. The 120-pixel orb now has a shaded glass
sphere, beveled segmented concentric rings, radial tick marks, amber instrument
accents, specular lighting and a centered I.R.I.S. wordmark. Idle is cyan #65E3E5
with halo #12383E; remaining state colors and red microphone dot are preserved.
This is lightweight Qt-painted depth, not a true 3D mesh or screen-aware view.
Existing active-state pulses stop when idle, hidden or reduced motion is enabled.

User override, 13 Oct 2026: default GUI is orb only. Clicking the orb starts
listening; the large main window stays hidden. Existing colors/drag/pause/kill/
speech behavior remains. Hover shows recent status/transcript/reply; required
confirmation uses a compact dialog. This overrides window-opening instructions below.

The look of the floating orb and the main window. Calm, dark, and glowing, like a small AI core on the desktop.

## 1. The floating orb

- **Size:** 120 x 120 px, frameless, transparent background, always on top.
- **Start position:** bottom-right of the screen, 32 px from the right edge and about 110 px from the bottom (above the taskbar).
- **Behavior:** drag to move. Click to open or focus the main window; Mic or Ctrl+Alt+Space starts listening (Phase 4 user instruction). Right-click for the menu: Show or hide IRIS, Pause listening, Quit.

### Logo (layers from back to front)
1. **Halo:** soft circle, 112 px, filled with the state's halo color.
2. **Ring:** 96 px circle, dark fill, 3 px outline in the state color.
3. **Iris:** 44 px circle filled with the state color.
4. **Pupil:** 18 px circle in the dark background color.
5. **Label:** the word IRIS under the ring, Segoe UI Bold, 11 px, light text color.

```
      .-""""-.
    /  .---.  \
   |  ( (o) )  |      colored iris + dark pupil
    \  '---'  /       ring in the state color
      '-....-'
        IRIS
```

### States

| State | Ring and iris color | Halo color | Motion |
|---|---|---|---|
| Idle | `#4C7DFF` blue | `#1B2C55` | Still |
| Listening | `#2EC4B6` teal | `#124E4A` | Halo pulses gently (about 1.2 s cycle) |
| Thinking | `#F5B942` amber | `#5A4413` | Halo pulses faster (about 0.8 s cycle) |
| Speaking | `#B983FF` purple | `#3F2A66` | Halo breathes with the speech |
| Error | `#E5484D` red | `#4D1C1E` | One short pulse, then back to idle |
| Paused | `#6B7390` grey | `#1E2336` | Still, ring dashed |

- **Microphone dot:** a small red dot (`#FF4D4F`, 10 px) at the top-right of the orb while the microphone is open. It must be hidden whenever the mic is closed.
- **Color is never the only signal.** The status text in the main window always names the state in words.
- **Reduced motion:** a setting turns pulses into a steady glow.

## 2. Color theme

| Role | Color |
|---|---|
| Background | `#0B1020` |
| Panel | `#141B2E` |
| Panel border | `#222B45` |
| Text | `#EAF0FF` |
| Muted text | `#8A94B0` |
| You (user lines) | `#7FB2FF` |
| IRIS (reply lines) | `#5EE6D0` |
| Primary button | `#4C7DFF` with white text |
| Secondary button | `#1E2A47` with white text |
| Success | `#3DDC97` |
| Warning | `#F5B942` |
| Error | `#E5484D` |

All text on the background has strong contrast (the main text on `#0B1020` is well above the 4.5:1 minimum).

## 3. Main window

- **Size:** 940 x 640 px, minimum 760 x 520, dark background.
- **Top:** large logo on the left (same layers as the orb, about 112 px ring) with the word IRIS in Segoe UI Bold 58 px, and the line "your voice, your laptop" in muted 13 px.
- **Status line** under the logo, Segoe UI 17 px, one of: "Say Iris and a command, or click the orb.", "Listening. Go ahead.", "Thinking...", "Speaking...", "Paused."
- **Conversation log:** panel color, 13 px text, 16 px padding. Each message shows the speaker name (You or IRIS) above the text. Under actions, show a small note: "Verified", "Could not confirm", or "Failed" with the matching color.
- **Bottom bar:** text box (15 px), a **Mic** button (secondary), and a **Send** button (primary).
- **Confirmation card:** when IRIS needs a yes or no (for example sending email), a card appears above the bottom bar with the question, a **Send it** button, and a **Cancel** button.

## 4. Typography

- Font: Segoe UI (falls back to the system sans).
- Sizes: logo word 58, status 17, body 13, small notes 11 to 12, buttons 12 bold.

## 5. Motion

- State change: 150 ms color fade.
- Pulse: sine wave on the halo radius, plus or minus 4 px.
- No other animation. The orb should be calm, not distracting.

## 6. Rules for design changes

- Keep the orb readable at 120 px on a busy desktop.
- Keep the red mic dot visible at all times while recording.
- Keep the colors in `iris/ui/theme.py` so they can be changed in one place.

Phase 4 implementation notes: closing the main window hides it while the orb remains available. Right-click the orb for show/hide, pause/resume, reduced motion or Quit. Positions and reduced-motion choice are retained in this running instance only. The small label uses a translucent dark backing for contrast on bright desktops. Qt logical coordinates and available screen geometries handle scaling/monitor placement; real mixed-DPI acceptance remains pending.
