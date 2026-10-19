# Phase 5 Gmail API acceptance — 13 Oct 2026

**Status: implemented and verified offline; real OAuth/Gmail acceptance pending.**
No real account consent, token persistence, draft API write or send was performed
by the agent. All Gmail tests use fixture credentials, mock HTTP/OAuth and synthetic
email text. User authorization to proceed across Phases 4/5 does not imply live
authorization or acceptance. Phase 2/3 findings remain preserved in their records.

## Implemented

- Official installed-app OAuth consent in browser via loopback/PKCE, user-initiated
  Connect Gmail, restored cached grants and Disconnect Gmail. Single gmail.compose
  scope supports both draft creation and sending; no inbox endpoint or password input.
- External OAuth client JSON and current-user DPAPI encrypted token file under
  LocalAppData/IRIS/gmail. No plaintext storage fallback; extra OAuth scopes are
  refused when credentials load. Refresh failures/401 disconnect safely.
- Existing Brain draft_email tool creates a local immutable preview and displays
  it in the editor through queued Qt signals. Explicit initial send requests also
  only prepare. Optional existing local contacts/spoken at/dot resolve addresses;
  unknown names never cause guessed addresses. Complete UTF-8/plain-text emails,
  1–10 recipient addresses, subject/body bounds and header-injection checks.
- Manual Prepare locally action uses the same registry/gate/log on a Gmail worker,
  without invoking AI. Editable recipient, subject and body; Save Draft/Send/Cancel,
  visible connection state and actual outcome feedback.
- Private GUI jobs for send/save, both Permission.CONFIRM. They are hidden from the
  provider's tool schema list, and default model confirmation callbacks deny them.
  Full exact snapshot is displayed, original request/turn IDs/deadline enforced,
  affirmative GUI button required. Edits, invalid edits, close/hide, cancel, expiry
  and emergency stop cannot approve. Fields freeze after approval until result.
- Consume operations before dispatch. Double-click/callback/replayed/attempted
  identical snapshots cannot write again. No automatic HTTP send/save retry or
  redirect replay. Timeout/5xx/missing ID is uncertain, never claimed successful.
- Gmail ID confirms draft creation or message submission; not recipient delivery.
  Fixed errors expose useful categories/status without raw bodies/tokens/headers.
  Email audit entries omit recipient/subject/body/MIME and keep safe metadata/results.
- One owned serial Gmail worker, bounded HTTP/refresh, cancellable/reaped consent
  subprocess and asynchronous app cleanup. No extra mic/hotkey/Brain loop.

## Automated results

Phase 4 restoration baseline: **299 passed in 20.97s** before Gmail implementation.
Gmail-specific security/API/headless UI subset: **56 passed in 6.12s**.
Final combined full suite: **358 passed in 26.43s**. Final regressions verify
orb-menu hiding cancels exact-email approval and worker restore/cleanup errors
cannot escape as raw thread exceptions or leak credentials.
pip check reports no broken requirements; actual --check masks both API keys and
does not initialize hardware/OAuth. No live account or provider test in this run.

Covered: local preview privacy/schema/headers, MIME encoding, DPAPI mock failure,
minimum scopes, credential restore/refresh/revocation, consent settings/timeout/
cancel, fixed diagnostics, actual draft/send REST payloads and request counts,
uncertain results, replay refusal, exact snapshot/gate request and turn binding,
invalid edits/cancel/expiry/kill, real Qt approval buttons, manual save workflow,
background connection calls and UI affinity, shutdown, text/voice preview with
both actual provider adapters using mocked model replies, and old safety tests.
DPAPI native usability, network/OAuth/browser/Windows/hardware are not established
by these mocked results. Tested Python 3.12.6; target Python 3.11 remains unchecked.

## Windows setup and acceptance

Follow README Phase 5 setup: enable Gmail API; configure Google Auth Platform
Branding/Audience/Data Access; personal account uses External/Testing plus test
user; add gmail.compose; create Desktop app client. Store downloaded JSON at
`%LOCALAPPDATA%\IRIS\gmail\client.json`, outside the source checkout. Do not share
the JSON, token file, private email text or keys.

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\pythonw.exe -m iris.main --gui
```

Use your own receiving address for send testing; sample example.com addresses
in automated tests are not intended for actual mail. Record PASS/FAIL and visible
outcome without sharing private contents.

1. **Connection:** Gmail button > Connect Gmail. Complete browser consent.
   Confirm Connected, external encrypted token.dpapi creation, no token.json in
   source, and no authorization codes/tokens/passwords in console or actions.log.
   Restart and confirm cached restoration. All pending until real authorization.
2. **Local preview:** Type Draft an email to YOUR_ADDRESS about tomorrow's meeting.
   Review the exact address/subject/body. Confirm no Gmail draft or mail exists
   until approval. Repeat by Mic/Ctrl+Alt+Space. Initial Send an email must also
   prepare only. Say send it: no Gmail write can occur through speech.
3. **Manual preview:** Open Gmail review, enter fields, Prepare locally. Verify it
   works even if the AI provider is unavailable. This still executes through registry.
4. **Save:** Save Draft, inspect the full confirmation, approve Save this draft.
   Confirm actual Gmail Drafts entry and not Sent. One API result/log action only.
5. **Send:** Use a new reviewed preview addressed to yourself. Send > inspect exact
   immutable fields > Send this email. Confirm one Sent entry, appropriate Gmail
   submission result and independently check receipt. Do not infer delivery from ID.
6. **Invalidation:** Before approving repeat with subject/body/recipient edits,
   temporarily invalid address, Cancel, Escape/close, hide main window and >30-second
   expiry. Previous dialog approval must never dispatch. A fresh Send opens a new
   snapshot; after approval fields remain frozen until result.
7. **Duplicates:** Rapidly click Send/approve twice; confirm exactly one message.
   Try the same completed/uncertain preview again: it is refused until a new or
   edited preview and fresh approval. Do not intentionally resend an uncertain
   live message until manually checking Gmail.
8. **Errors:** Deny consent, omit/misconfigure client JSON, remove API access, revoke
   the app's Google Account grant, expire credentials and interrupt connectivity.
   Expect fixed errors/disconnection, no secret leakage and no automatic write
   retries. Mock tests cover ambiguous sends; do not send extra live messages just
   to provoke a timeout.
9. **Cancellation/cleanup:** Press Ctrl+Alt+Esc during OAuth wait, pending approval,
   and a write. Pending/unstarted work must stop; an in-flight request cannot be
   retracted. Exit and confirm this instance's consent/audio processes and worker
   threads are gone, then restart. Preserve unrelated Python processes.
10. **Disconnect:** Disconnect Gmail removes local token and shows Disconnected;
    saving/sending disabled. Google's remote consent is separate: revoke it in
    Account > third-party connections if required. Reconnect explicitly.

## Known limitations and remaining issues

All live steps above are pending. Google Cloud setup/account consent are user-owned.
gmail.compose is restricted; public distribution requires Google's verification
process. This local testing implementation is not a verified public OAuth app.
Local Disconnect does not revoke the remote grant. Cached valid tokens may not
reveal revocation until refresh/write. No inbox/profile verification endpoint is
requested. Already-dispatched writes cannot be cancelled or unsent. One HTTP
write/refresh has a 20-second bound; consent subprocess has a 190-second parent
bound and is cancellable/reaped. Native shutdown needs Windows validation.

No attachments, CC/BCC, HTML, bulk mail, inbox scraping, campaigns or automatic
replies. Local previews are in-process only; approved Gmail drafts persist at Google.
Save Draft always creates a new Gmail draft rather than editing a remote draft.
Prepared email text/user commands still use the selected Brain provider; OAuth
credentials are never passed to it. Gemini 503/504 remain unresolved and can stop
AI preparation, but manual preview/Gmail operations do not call Gemini.

Remaining Phase 2 focus/scroll/routing/offline/failsafe/logging findings and Phase 3
self-listening/device/timeouts/hotkey/native-cleanup/provider checks are not erased.
See PHASE2_AUDIT.md, PHASE2_WINDOWS_CHECKLIST.md and PHASE3_ACCEPTANCE.md.

## Files in this combined implementation

Created: iris/gmail.py, iris/ui/gmail.py, tests/test_gmail.py,
tests/test_gmail_ui.py, PHASE5_ACCEPTANCE.md.
Modified: iris/tools/email.py, iris/tools/registry.py, iris/brain/prompts.py,
iris/logs/action_log.py, iris/config.py, iris/ui/app.py, iris/ui/window.py,
iris/ui/orb.py, iris/ui/theme.py, tests/test_ui.py, tests/test_action_log.py,
requirements.txt, .env.example, .gitignore, README.md, PRD.md, Architecture.md,
Rules.md, phase.md, design.md, memory.md, PHASE4_ACCEPTANCE.md.
Synthetic visual QA artifacts in ignored data/: phase45_window.png,
phase5_gmail.png, phase5_confirmation.png. They are not live account evidence.

Official references: [OAuth desktop flow](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[drafts.create](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create),
[messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send),
[Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).
