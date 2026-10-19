# Gemini model checks — 13 Oct 2026

Latest configuration: **gemini-3.5-flash-lite** after the later 503 recheck below.

All 15 supplied model IDs were tried sequentially using the configured credentials.
Requests contained generic test prompts only. No keys, headers, raw SDK errors, IRIS internal prompts, or desktop tool schemas appear in this report.

| Model | Live Hello | Function round trip |
|---|---|---|
| `gemini-3.8-flash-tts` | request, HTTP 400 | not tested because greeting failed |
| `gemini-3.8-flash-lite-tts` | request, HTTP 400 | not tested because greeting failed |
| `gemini-3.8-live` | request, HTTP 400 | not tested because greeting failed |
| `gemini-3.8-live-extended-thinking` | request, HTTP 400 | not tested because greeting failed |
| `gemini-3.8-flash` | timeout, HTTP 504 | not tested because greeting failed |
| `gemini-3.7-flash` | unavailable, HTTP 503 | not tested because greeting failed |
| `gemini-3.6-flash` | passed | Passed (synthetic clock) |
| `gemini-3.5-flash-lite` | passed | Passed (synthetic clock) |
| `gemini-3.5-flash` | passed | Passed (synthetic clock) |
| `gemini-3.1-flash-lite` | passed | Passed (synthetic clock) |
| `gemini-3.1-flash-tts-preview` | request, HTTP 400 | not tested because greeting failed |
| `gemini-3.1-pro-preview` | quota, HTTP 429 | not tested because greeting failed |
| `gemini-3-flash-preview` | passed | Passed (synthetic clock) |
| `gemini-3-pro-preview` | not_found, HTTP 404 | not tested because greeting failed |
| `gemini-3.1-flash-lite-preview` | passed | Passed (synthetic clock) |

Selected **gemini-3.6-flash**, the first candidate in the supplied order to pass both checks. Only GEMINI_MODEL in .env changed; credentials were preserved. IRIS has no runtime automatic model/provider fallback.

Each successful function probe required exactly one get_time call with empty arguments, replayed a fixed synthetic result, then required a text answer containing that result with tools disabled. SDK retries were disabled for this sweep. A single transient failure does not prove permanent model unavailability.

Additional selected-model check through the shared Brain used a generic test prompt and a registry containing only the real read-only get_time tool. Hello returned a greeting. What time is it returned a verified local timestamp through the permission gate and action logger. The full IRIS internal prompt/seven-tool payload was not live-tested in this session.

Configuration check passed with both keys masked. Offline full suite: **198 passed in 11.96s**. No runtime source changes or Phase 3 features were added.

TTS/Live HTTP 400 results apply to the Phase 2 GenerateContent text requests, not a claim that their intended audio/Live APIs are broken. Shutdown/alias guidance: [Google deprecations](https://ai.google.dev/gemini-api/docs/deprecations).

Run the full console locally:

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\python.exe -m iris.main
```

Enter Hello, What time is it?, Open Notepad, and Open Instagram one at a time. Expect a greeting, verified current local time, a Notepad result verified only if a new matching process appears, and an unverified browser dispatch for Instagram. Test Ctrl+Alt+Esc during a request. Full prompt/seven-tool and real Windows acceptance remain manual; see GEMINI_TROUBLESHOOTING.md.

Automatic approval review rejected the initial sweep that would export IRIS internal prompts and all tool schemas. That probe did not run. The permitted alternative used generic test prompts and a small public clock schema only.

## Later full-console 503 report and recheck

The user reported HTTP 503 for Hello on gemini-3.6-flash. The earlier matrix is a point-in-time result, not an availability guarantee. A later shared-Brain check used generic prompts and only the real read-only clock tool:

| Model | Three greetings | Actual clock tool and final feedback |
|---|---|---|
| gemini-3.6-flash | HTTP 504, 503, 499 | HTTP 503 |
| gemini-3.5-flash-lite | One failed reply check, two passed | Passed, verified local time |

The first Flash-Lite greeting did not pass the probe's reply check; its precise cause was not recorded. These results do not guarantee model availability or full-console behavior.

**Current configuration: GEMINI_MODEL=gemini-3.5-flash-lite.** Restart any existing console to load it. Credentials are unchanged; runtime retries/fallback behavior is unchanged. The configuration check passes with keys masked. Focused offline error/retry/no-repeat/cancellation tests: **8 passed, 45 deselected in 0.65s**. Full normal-prompt/seven-tool and Windows acceptance still require local checks.
