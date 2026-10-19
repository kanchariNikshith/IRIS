# Phase 2 Windows checks — 13 Oct 2026

The user reported successful full-console greetings, current time, name reversal, Notepad launching/text dispatch, and Instagram browser opening with gemini-3.5-flash-lite. These are user-reported observations, not new agent-run tests. Generated programs have not been compiled or validated.

IRIS can confirm a new app process and read the local clock. It does not read Notepad contents or inspect browser pages. Text, scroll, keys and browser dispatch therefore remain unverified even when you see them succeed. Text input is limited to 500 printable ASCII characters, with no newlines, tabs or Enter.

Desktop app catalog: Notepad, Chrome, Edge, Spotify, Word, Excel, subject to installation/resolution. WhatsApp desktop is not included. The generic website tool can attempt Open https://web.whatsapp.com; page loading remains unverified. The shorter Open WhatsApp phrase currently lacks an explicit website mapping and failed in the supplied transcript.

For scroll/key/typing tests, submit the command in the IRIS console. When IRIS prints its input notice, click the intended disposable browser tab or Notepad during the three-second pause. For scrolling, keep the mouse over the page content. The pause is cancellable with Ctrl+Alt+Esc; there is still no automatic target selection or readback. Avoid using a terminal or form as the typing target. If the wrong window receives input, record a failure.

| Exact command / test | Expected result |
|---|---|
| Hello | Brief greeting; no desktop action. |
| What is the reverse of your name? | SIRI; no app or keyboard tool needed. |
| Explain the Fibonacci sequence. | Explanation; no desktop action. |
| What time is it now? | Verified local date/time agreeing with Windows clock. |
| What can you do? | Should explain supported capabilities; record any false refusal. |
| Just list the things you can do. | Should answer without actions; currently a known false refusal in the no-tool guard. |
| Open Notepad | App opens; verified only if a new matching process is observed. |
| Open Chrome / Open Edge / Open Spotify / Open Word / Open Excel (one at a time) | Installed catalog app opens; missing/unresolvable apps fail honestly. Existing single-instance apps may be unverified. |
| Open Instagram | Default browser opens the site; report remains unverified. |
| Open https://web.whatsapp.com | Browser attempts WhatsApp Web; may require login/QR; no claim that loading or login was verified. |
| Search the web for Python Fibonacci examples | Browser search results open; no claim that IRIS read the results. |
| Scroll down / Scroll up / Scroll to bottom / Scroll to top (one at a time) | Focused long page moves appropriately; unverified input result. |
| Open a new tab / Close the current tab (one at a time) | Focused browser disposable tab opens/closes; unverified. |
| Go back / Go forward (one at a time) | Focused browser history changes; unverified. |
| Type exactly Hello from IRIS | Exact one-line text appears in focused disposable Notepad; no Enter; unverified contents. |
| Increase volume / Decrease volume / Mute (one at a time, optional) | Windows audio indicator changes; unverified input result. |
| Press Enter | Refused; no Enter dispatched. |
| Open PowerShell | Refused; not a catalogued app. |
| Open file:///C:/Windows/win.ini | Refused; browser accepts only HTTP/HTTPS. |
| Stop | Stopped and console exits; restart to resume. |
| Press Ctrl+Alt+Esc during a pending command | Stops the turn, no tools from late API replies. Already-dispatched actions cannot be undone. At an idle input prompt, Enter may be needed to exit. |

After tests inspect the log locally in another PowerShell window:

```powershell
Get-Content .\data\actions.log -Tail 20
```

Record command, visible outcome, reply, logged tool/status, and PASS/FAIL. Tool attempts should append entries; plain answers need no action log entry. Do not share keys or private text from logs.

The rejected capability-list questions are a known response-guard bug, not proof that IRIS has no capabilities. Offline local commands still depend on an API connection. Scroll/key/focus/cancellation/log acceptance remains pending. No Phase 3 features or new tools were implemented for this checklist.

## Follow-up scroll failure and handoff fix

The user reported no visible browser movement after scroll dispatch and was unsure which window had focus. Root cause is not confirmed; input may have targeted PowerShell or the mouse may have been outside the page. The console previously offered no predictable handoff. It now prints a notice and waits three seconds before each scroll/key/typing action. All 213 offline tests pass, including handoff order and cancellation without hardware dispatch. Real scrolling still needs this check:

1. Restart IRIS to load the code change.
2. Open a long browser page that scrolls when you manually turn the wheel, starting near its top.
3. Enter Scroll down in browser in IRIS.
4. At the input notice, click the page and leave the pointer over its content during the three-second pause.
5. Check visible movement. Repeat Scroll up and Scroll to bottom, switching back to the page at each notice.
6. In a fresh turn, press Ctrl+Alt+Esc during the pause and confirm no input is sent afterward.

The follow-up transcript reports What can you do answered, search/new-tab/text dispatch returned unverified, Stop exited, Explain the Fibonacci sequence opened a search instead of answering directly, and Close the current tab yielded no tool call. These dispatch replies alone do not prove the target window changed; the latter two behaviors still need a separate scope correction. Phase 3 remains unstarted.

## Latest user acceptance result

The user confirmed Open Instagram and Scroll to bottom worked twice after the handoff change. This covers the combined browser dispatch/bottom-key path in those attempts. Direct wheel scroll down/up, real Ctrl+Alt+Esc during the pause and append-only log review remain pending. Prior close-tab and informational-request routing failures, plus the offline local-command requirement, still prevent full Phase 2 sign-off. No Phase 3 work was started.
