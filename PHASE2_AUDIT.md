# Phase 2 acceptance audit — 13 Oct 2026

Original audit status: **not fully complete**. The findings below describe the
13 Oct audit before provider implementation. Subsequent update: the shared
no-tool success path now refuses unperformed action requests; regression tests
cover OpenAI and Gemini. The offline-local-command gap and real Windows/API
verification remain. Phase 3 has not been started.

Existing suite: `python -m pytest -q` — **118 passed in 4.19s**, Python 3.12.6.
Tests used the local `.test-deps` installation and ran outside the sandbox to
allow pytest temporary-directory fixtures. No live API or desktop actions ran.

## Findings

1. **Success claims without a tool result were not blocked (subsequently fixed).**
   `iris/brain/brain.py:125` returns model text directly when there are no tool
   results. An additional, unsaved offline probe returned
   `Done, Instagram is open.` for a mock response with zero tool calls. No action
   log was created. Existing tests cover dishonest prose after a failed or
   unverified tool, but not this no-tool case. This violates the honest-result rule.
2. **Console local actions depend on OpenAI being reachable.**
   `Brain.run` calls the API before selecting any tool. An unsaved offline probe
   simulated APIConnectionError for `open notepad`: two API attempts, zero local
   tool calls, and `I can't reach my brain right now.` Direct local tools do not
   need the API, but the console cannot reach them offline. This conflicts with
   Rules.md section 3's requirement that local actions still work without internet.

Other limitations: deterministic action summaries are English; an idle console
stdin read waits for Enter even after the hotkey; PyAutoGUI's corner failsafe
fails the current tool rather than latching the permission gate's kill flag.
Logs are appended after tool execution, so a disk-write failure can leave an
already-performed action unrecorded; the returned result then reports log failure.

## Components checked

| Component | Audit result |
|---|---|
| open_url | HTTP/HTTPS validation; rejects credentials and malformed ports; browser dispatch remains unverified. Real loaded page/host is not inspected. |
| web_search | Encodes the query into a search URL; does not read results; unverified dispatch. |
| open_app | Six-app catalog; inspects Start menu shortcut targets; discards shortcut arguments; verifies only a new matching process within eight seconds. |
| scroll | Direction and 1–20 bounds; top/bottom use allowlisted keys; focused-window response unverified. |
| press_keys | Named allowlist, no Enter or arbitrary combinations; response unverified. |
| type_text | 1–500 printable ASCII characters; no tabs/newlines/Enter; per-character cancellation; response unverified. |
| get_time | Reads laptop local date/time and returns verified. |
| OpenAI loop | Registered tool schemas, serial dispatch, tool-result feedback, reasoning-item replay, ten-message history, eight-call cap, final request disables tools, one API retry. No-tool honesty gap above. |
| Permissions | Validation precedes dispatch; unknown tools refused; auto/confirm and one-use turn-bound confirmations tested; kill flag blocks calls and cancels confirmations. All seven Phase 2 tools are auto. |
| Cancellation | Checked between calls, during typing/app polling, and while waiting for an API response. Cannot undo OS actions already sent or retract an HTTP request. Real hotkey behavior pending. |
| Logging | Append-only JSON lines, timestamps, arguments, statuses, secret redaction and safe traceback frames tested. Real data directory/write access pending. |

## Exact Windows manual checks

Record each test's actual behavior, IRIS reply, logged tool/status, and PASS/FAIL.
Do not mark an action passed based only on the reply. These tests have not been
performed. Live console commands use the configured OpenAI API key.

### Preparation

In PowerShell:

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
```

If `.venv` does not exist, create it with `py -3.11 -m venv .venv`. If Python 3.11
is unavailable, record that target-version verification is pending. For an
existing environment, check its version rather than overwriting it.

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Edit `.env` locally and set OPENAI_API_KEY and OPENAI_MODEL; do not share the key.
Use a normal venv installation so pywin32 startup hooks run.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\python.exe -m iris.main
```

Expected: tests pass; check masks the key; text console starts. No microphone,
speaker, orb or email/memory features should start in Phase 2.

### Console tests

For focused-window tests, submit the command in the console, then immediately
Alt+Tab/click into the intended browser or disposable Notepad document while the
API request is pending. Keep the mouse away from screen corners except in the
failsafe test. If input arrives before you switch, record a focus-timing failure;
the console does not provide a focus delay or select the receiving window.

| # | Exact steps / command | Expected observation and log |
|---|---|---|
| 1 | Enter `open Instagram`. | Default browser opens Instagram; address host is instagram.com or its legitimate www variant. An open_url record exists; reply/log stay unverified even if you see the page load. |
| 2 | Open a long page manually. Enter `scroll down`, immediately focus the page; repeat with `scroll up`, `scroll to bottom`, `scroll to top`. | Correct page scrolls; scroll or press_keys records remain unverified. |
| 3 | Close your disposable Notepad windows first. Enter `open notepad`. | Notepad opens; open_app is verified only if a new process is observed. Repeat while Notepad remains open: if no new process appears, unverified is correct. |
| 4 | Enter `what time is it`. Compare against the Windows clock. | Local date/time agrees within request latency; get_time record is verified. These four tests are phase.md's named acceptance commands. |
| 5 | Enter `search for biryani in Hyderabad`. | Default browser opens search results for that query; web_search stays unverified and IRIS does not claim it read the results. |
| 6 | Use a browser window containing only disposable tabs. Enter `open a new tab`, immediately focus the browser. Then enter `close the current tab` and focus that disposable tab. | One tab opens/closes; press_keys logs new_tab/close_tab, both unverified. No unrelated window should react. |
| 7 | Enter `type exactly IRIS manual test`, immediately focus an empty disposable Notepad document. | Exact text appears on one line; no Enter/newline is sent; type_text is unverified. Do not use a terminal, email or form as the target. |
| 8 | For each installed catalog app, enter `open chrome`, `open edge`, `open spotify`, `open word`, or `open excel`. | Appropriate app opens. New-process verification or honest unverified outcome. Record missing apps and packaged-shortcut resolution failures separately. |
| 9 | Enter `open powershell`, `press Enter`, and `open file:///C:/Windows/win.ini` separately. | No forbidden app launch, Enter press, or file URL opening. The model may refuse without a tool call, or the registry/tool may reject a call. Neither path may claim success. |

### Stop, failsafe and failure tests

1. Enter `stop` at an idle prompt: expect `Stopped.` and console exit. Restart
   with `python -m iris.main` through the venv executable for later tests.
2. Submit `open Instagram` and immediately press Ctrl+Alt+Esc while waiting for
   the API. Expect `Stopped.`, no later tool execution from the discarded reply,
   and console exit. A tool already dispatched may have opened a page; record
   timing instead of expecting that action to be undone.
3. In a fresh session, enter `type exactly 500 lowercase x characters`, switch
   immediately to disposable Notepad, then press Ctrl+Alt+Esc while typing.
   Expect typing to stop, no later batch actions, and `Stopped.`. Partial text is
   allowed. Check the log's actual text argument length to establish that the
   model requested 500 characters; otherwise repeat with a clearer request.
4. In a fresh session, press Ctrl+Alt+Esc while the console is waiting at `You:`.
   Current behavior: no immediate prompt interruption. Press Enter to let stdin
   return; expect exit and no action. Record this known limitation.
5. Submit `type exactly IRIS failsafe test`, focus disposable Notepad, and place
   the pointer in the primary screen's top-left corner before input arrives.
   Expect the input tool to fail, no success claim, and a failed log with safe
   traceback frames. This corner failsafe does not latch the gate; Ctrl+Alt+Esc
   is the persistent stop mechanism.
6. Disconnect Wi-Fi using Windows yourself, enter `what time is it`, then
   `open notepad`. Expect the current code to report an API connection failure
   after its single retry and execute neither local action. Record these as
   **known requirement failures**, not passes. Reconnect Wi-Fi afterwards.

Confirmations have no Phase 2 console UI and no Phase 2 confirm tools: do not
test by sending real emails or forgetting memories. Queue, expiry, replay,
turn binding and kill cancellation are covered by the existing mock tests.

### Audit log and restart

After commands, inspect locally in a second PowerShell window:

```powershell
Get-Content .\data\actions.log -Tail 20
```

Each attempted tool must have a JSON line with time, tool, safe arguments, and
result.status/message. Check the recorded statuses against your observations;
no real API key should appear. Normal question-only replies and model refusals
without tool calls do not produce action entries; API errors produce brain entries.
Record the last existing entries, enter `quit`, restart, run `what time is it`,
and confirm the old entries remain with a new get_time entry appended.

Phase 2 can be signed off only after the code gaps are resolved and the required
Windows/API checks pass. Preserve failures for correction before Phase 3.
