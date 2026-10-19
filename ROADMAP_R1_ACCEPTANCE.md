# R1 orb and local routing — 15 Oct 2026

Status: **automated checks passed**. Native Windows
acceptance remains pending. Built on the R0 baseline in this workspace.

## Resulting behavior

- `--gui` shows only the orb. Click records one turn using the existing controller;
  drag does not activate. Right-click Show or hide IRIS opens chat/setup/Gmail.
  Singleton recovery restores/clamps the orb without recording/opening chat.
- Exact one-action time/date, six catalog app names, explicit HTTP/HTTPS URLs,
  bounded scroll and named allowlisted key commands bypass the provider. They use
  the same schema validation, gate, cancellation, audit and result callbacks.
  Compound/ambiguous commands stay with the selected provider.
- Startup works without a selected cloud key/model. Cloud questions give fixed
  configuration guidance. `--check` retains the strict selected-key diagnostic
  and masks both keys; no existing `.env` settings are changed.
- Brain factory enables local routing; the low-level Brain constructor retains
  its existing model-only default for backward compatibility/protocol tests.
- Informational capability/how-to questions no longer fail solely because they
  mention an action word. Claimed completion without a tool is still rejected.
- `pause listening` aliases `stop listening`; a closed mic requires local resume.
- Metrics contain only route/request counts and last durations in RAM. Generic
  input/browser dispatch remains unverified. No wake activation is claimed.
- Requested email previews open the review window; existing hide/edit/expiry/
  cancel/kill invalidation and exact-message GUI approval remain mandatory.

## Automated and end-to-end checks

`tests/test_local.py` exercises parsing, refusal boundaries, actual factory with
missing credentials, real clock/registry/audit, unverified results, cancellation
and confirmation denial, plus informational reply regressions. Existing Qt,
provider, voice, safety and Gmail suites remain required. Tests mock native
devices/providers/desktop actions; none sends a live email.

Targeted local/Qt/Gmail/startup checks: **81 passed in 21.62s**. Final full suite:
`.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-r1-final`, outside
the sandbox for the Qt pipe: **384 passed in 27.18s**. No dependency/config/model
changes or live provider calls. First full run caught two Gmail hide-invalidation
regressions from hidden startup; fixed by explicitly opening requested review.

16 Oct follow-up: added the originally reported "Just list the things you can
do" / "Which apps can you open?" question regressions and exact "close the
current tab" local alias. Prompt guidance distinguishes explanations from action
requests. These are included in the final 434-pass suite recorded in R3.

## Windows acceptance still required

1. Start `.venv\Scripts\pythonw.exe -m iris.main --gui`; only the orb appears.
   Drag, click-to-listen, right-click chat/setup and launch a second GUI instance.
2. With the provider unavailable, ask time/open Notepad: one tool/audit record,
   zero provider requests. Check observed Notepad separately from process status.
3. Test pause/resume, Ctrl+Alt+Esc, graceful quit and restart, including speech
   and the three-second focus handoff. Confirm no owned worker remains.
4. Check DPI/monitor transitions and error/permission visibility. Gmail approval
   still needs exact review; real account acceptance is assigned to R8.
