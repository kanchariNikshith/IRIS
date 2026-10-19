# Gemini connection investigation — Phase 2

Latest configuration: **gemini-3.5-flash-lite**, selected after the subsequent 3.6 Flash HTTP 503 report and limited recheck. Restart an already-running console to load the setting.
Live greeting and clock function checks passed; see [model results](GEMINI_MODEL_RESULTS.md).
The full IRIS prompt/seven-tool payload and Windows actions still require local acceptance.

Earlier gemini-2.5-flash investigation on 13 Oct 2026, with the configured key kept private:

| Probe | Result |
|---|---|
| Interactions, minimal Hello, no tools | HTTP 404 |
| Interactions, Hello with IRIS schemas | HTTP 404 |
| GenerateContent, minimal Hello, v1beta | HTTP 404 |
| GenerateContent, minimal Hello, v1 | HTTP 404 |
| Model catalog with the same credentials | Succeeded; included gemini-2.5-flash and generateContent support |
| Post-fix Brain Hello, desktop tools disabled | Safe not_found / HTTP 404 diagnostic; no successful greeting |

The observed root cause is service-side model/endpoint availability for the
configured account/model, rather than a demonstrated invalid key or a schema
failure: even the minimal requests without tool declarations fail, and catalog
authentication works. The original adapter erased the 404 status and collapsed
it into a generic request rejection, obscuring this distinction.

Google's [Interactions model list](https://ai.google.dev/gemini-api/docs/interactions-overview)
includes Gemini 2.5 Flash, so universal Interactions incompatibility is not
established. Google's [model-access note](https://ai.google.dev/gemini-api/docs/deprecations)
says 2.5 access is limited to users who previously used those models. This is
consistent with the observed 404; the project's precise eligibility was not
confirmed. Catalog presence is not proof that generation is available.

## Adapter changes

- Gemini uses the fully supported GenerateContent endpoint for this text/tool
  integration. Switching endpoints cannot grant missing model access.
- system_instruction is passed in GenerateContentConfig; messages use Content
  roles/parts, and outputs come from candidate content, not Interaction steps.
- Tools use parameters_json_schema (the full registry schema), rather than the
  SDK's narrower OpenAPI Schema type. Local validation remains authoritative.
- Automatic SDK function execution is explicitly disabled. All actions go
  through the existing Brain, registry, permission gate and action log.
- Whole model parts, including thought signatures, are preserved. Missing Gemini
  2.5 function-call IDs get local correlation IDs; native result IDs are preserved
  only when supplied by the model.
- SDK HTTP retries are disabled. One Brain-controlled retry applies to transient
  quota/service/network failures; 400/401/403/404 stop without repeated requests.
- Error diagnostics contain only safe fixed categories, numeric HTTP status and
  actionable guidance. API keys, headers, raw SDK error bodies, user commands and
  private request content are never included in provider diagnostics.

## Exact local verification

Keep your key private. Do not paste .env or raw SDK tracebacks into chat.
Do not overwrite .env; credentials are unchanged and GEMINI_MODEL is now gemini-3.5-flash-lite.

```powershell
Set-Location 'C:\Users\NIKSHITH\OneDrive\Desktop\IRIS'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iris.main --check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m iris.main
```

At the IRIS prompt, enter each separately:

1. `Hello`: expect a brief greeting. With continued model access failure, expect
   `Gemini error (not_found, HTTP 404)` and model/project-access guidance.
2. `What time is it?`: expect a verified local time from get_time, with a matching
   data/actions.log entry. A successful greeting alone does not verify tool calling.
3. Close disposable Notepad windows; enter `Open Notepad`: expect a new window
   and a verified result only when a new matching process is observed.
4. Enter `Open Instagram`: expect the default browser to open it; the app must
   report unverified page loading, even if you see the page open.
5. Submit a command and press Ctrl+Alt+Esc during model processing: expect Stopped
   and no tools from a late response. An already-dispatched action is not undone.

If 404 persists, check generation access for the selected model in Google AI
Studio. For projects without legacy 2.5 access, choose an available model there
and edit only GEMINI_MODEL locally. Google currently recommends 3.5 Flash-Lite or
3.8 Flash for new projects; availability/quota for this account still needs
checking. IRIS does not silently substitute a model or provider.

IRIS already retries a transient API error once after two seconds; repeated 503 can still occur. A successful probe does not guarantee service availability. Do not repeatedly resubmit a desktop action without checking its reported result; an action may have run before a later provider failure.

Safe failure meanings:

| Category | Guidance |
|---|---|
| auth / 401 (or allowlisted invalid-key reason) | Check key configuration locally. |
| permission / 403 | Check project restrictions, API permissions and region. |
| not_found / 404 | Check model generation access and endpoint availability; do not assume a bad key. |
| request / 400 | Check SDK/request/schema compatibility. |
| quota / 429 | Check project quota/billing tier and retry later. |
| unavailable / 503 | Service capacity/availability issue; retry later. |
| transport or timeout | Check network/proxy/firewall and retry later. |

Review `Get-Content .\data\actions.log -Tail 20` locally for statuses and safe
provider diagnostics. Windows action checks and the full console payload remain pending; selected-model
generation and read-only clock function checks now pass. Phase 3 has not been started.
