# GitHub phase workflow

## Initial import

The checkout had no commits or remote on 19 October 2026. The first commits
organize the existing source by component; they do not reconstruct historical
versions. Files contain their current implementation, including later changes.
Intermediate import commits are not independently runnable releases. Validate
the final import together. See `phase.md` for the active R0–R13 roadmap and
`PHASES_LEGACY.md` for the prototype history.

| Import commit | Contents |
| --- | --- |
| Foundation | Configuration, permission gate, audit log, dependency setup, memory placeholders and tests |
| Command engine | Provider adapters, Brain, tool registry and desktop/browser tools with tests |
| Voice | Cancellable audio workers, transcription, speech output and tests |
| Desktop | Orb, chat window, theme and UI integration tests |
| Gmail | OAuth, secure storage, local review, approved draft/send tools and tests |
| R0–R1 | Telemetry, deterministic local routes and tests |
| R2–R3 development | Single-owner capture, disabled wake runtime, training/evaluation tools and tests |
| Documentation and integration | Entrypoint, setup, roadmap, acceptance records and current audit reports |

R3 wake candidates fail acceptance and remain disabled. Later planned phases
must not be reported as implemented merely because this source is on GitHub.

## Future phase delivery

1. Begin each authorized phase in `phase.md` order on `codex/rN-short-description`.
2. Implement only its agreed scope; update its acceptance record and `memory.md`.
3. Run the relevant checks and the full offline suite before marking a phase done:
   `.venv\Scripts\python.exe -m pytest -q`.
4. Review `git diff --check`, the staged diff and candidate files for secrets.
5. Commit with a phase-specific message, then push that branch to `origin`.
6. Report the commit/branch URL, automated results and remaining manual acceptance.

The owner has requested phase-by-phase GitHub delivery. Push completed authorized
work when credentials and the remote are available; this does not authorize
implementing every planned phase or silently merging branches.

## Local-only files

`.env`, OAuth credentials/tokens, recordings, runtime data, generated models,
virtual environments, test caches and upstream reference clones are excluded.
Keep `.env.example` blank. Reference revisions and sources are documented in
`IRIS_INTEGRATION_REPORT.md` and the training README; clones are not vendored.

## First connection

If no remote exists, create an empty GitHub repository without generated files.
Set `origin` to its HTTPS URL, authenticate Git locally, then push `main` with
`git push -u origin main`. Never put a token in a remote URL or tracked file.
