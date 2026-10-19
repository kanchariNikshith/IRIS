"""Offline Gmail safety/API/OAuth tests. No real account or password access."""
from base64 import urlsafe_b64decode
from email import message_from_bytes
import json
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from iris.gmail import (EmailSnapshot, GmailError, GmailService, TokenVault,
                        SCOPES, raw_message, validate_email, authorize_desktop, oauth_worker)
from iris.logs.action_log import ActionLog
from iris.security.permissions import PermissionGate
from iris.tools.registry import ToolRegistry, ToolResult
from iris.tools.email import EmailController
from iris.tools.email import resolve_recipients


def wait(predicate):
    deadline = monotonic() + 3
    while not predicate():
        assert monotonic() < deadline
        sleep(0.005)


def snapshot():
    return EmailSnapshot("id", 1, ("test@example.com",), "Tomorrow's meeting", "I'll attend.\nThank you.")


def service():
    http = Mock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {"id": "confirmed-id"}
    result = GmailService(client_path="fixture-client.json", vault=Mock(), http=http, oauth=Mock())
    result.credentials = Mock(valid=True, token="fixture-oauth-secret")
    return result


def controller(tmp_path, emit=lambda kind, value: None, timeout=1):
    api = service()
    api.restore = Mock(return_value=False)
    registry = ToolRegistry(PermissionGate(timeout), ActionLog(tmp_path / "actions.log"))
    return EmailController(registry, api, emit=emit), api


def finish(manager):
    manager.gate.stop()
    manager.close()
    assert not manager._thread.is_alive()


def test_raw_email_encodes_unicode_without_header_injection():
    email = EmailSnapshot("id", 1, ("test@example.com",), "Résumé", "Hello\nWorld — thanks.")
    parsed = message_from_bytes(urlsafe_b64decode(raw_message(email)))
    assert parsed["To"] == "test@example.com"
    assert "World" in parsed.get_payload(decode=True).decode("utf-8")


def test_local_contact_and_spoken_address_resolution_never_guesses(tmp_path):
    contacts = tmp_path / "contacts.json"
    contacts.write_text(json.dumps({"Priya":"priya@example.com"}))
    assert resolve_recipients("priya, john at gmail dot com", contacts) == "priya@example.com,john@gmail.com"
    with pytest.raises(ValueError):
        validate_email(resolve_recipients("unknown name", contacts), "Subject", "Body")


def test_invalid_contacts_are_sanitized(tmp_path):
    path = tmp_path / "contacts.json"
    path.write_text("private invalid data")
    with pytest.raises(ValueError) as error:
        resolve_recipients("Priya", path)
    assert "private invalid data" not in str(error.value)


@pytest.mark.parametrize("to,subject,body", [
    ("x@example.com\r\nBcc:victim@example.com", "Hi", "Body"),
    ("not an address", "Hi", "Body"), ("test@example.com", "Hi\nBcc: victim", "Body"),
    ("test@example.com", "Hi", "\x00Body"), ("test@example.com", "", "Body"),
    ("test@example.com", "Hi", ""), ("test@example.com", "Hi", "a" * 20001),
    ("test@example.com,test@example.com", "Hi", "Body"),
])
def test_invalid_email_fields_refused(to, subject, body):
    with pytest.raises(ValueError):
        validate_email(to, subject, body)


def test_vault_never_writes_plaintext_and_clear_is_local(tmp_path):
    # Cipher functions mocked; real DPAPI is a separate Windows manual check.
    vault = TokenVault(tmp_path / "token.dpapi", protect=lambda value: b"encrypted",
                       unprotect=lambda value: b"fixture-oauth-secret")
    vault.save("fixture-oauth-secret")
    assert vault.path.read_bytes() == b"encrypted"
    assert vault.load() == "fixture-oauth-secret"
    vault.clear()
    assert vault.load() is None


def test_vault_failure_does_not_fall_back_to_plaintext(tmp_path):
    vault = TokenVault(tmp_path / "token.dpapi", protect=Mock(side_effect=OSError("fixture-oauth-secret")))
    with pytest.raises(GmailError) as error:
        vault.save("fixture-oauth-secret")
    assert "secret" not in str(error.value)
    assert not vault.path.exists()


@pytest.mark.parametrize("kind", ["send", "save"])
def test_gmail_api_write_is_once_and_reports_real_result(kind):
    api = service()
    result = api.write(snapshot(), kind, Event())
    assert result.status == "verified"
    assert "delivery is not verified" in result.message if kind == "send" else "not been sent" in result.message
    api.http.post.assert_called_once()
    arguments = api.http.post.call_args
    assert arguments.kwargs["allow_redirects"] is False and arguments.kwargs["timeout"] == 20
    raw = arguments.kwargs["json"]["raw"] if kind == "send" else arguments.kwargs["json"]["message"]["raw"]
    assert "test@example.com" in urlsafe_b64decode(raw).decode()


@pytest.mark.parametrize("status,expected", [(400,"failed"),(401,"failed"),(403,"failed"),(429,"failed"),
                                             (503,"unverified"),(504,"unverified"),(302,"unverified")])
def test_http_errors_safe_without_retries(status, expected):
    api = service()
    api.http.post.return_value.status_code = status
    api.http.post.return_value.text = "fixture-oauth-secret private email body"
    result = api.write(snapshot(), "send", Event())
    assert result.status == expected and "secret" not in result.message
    api.http.post.assert_called_once()
    if status == 401:
        assert api.credentials is None


@pytest.mark.parametrize("outcome", [TimeoutError("fixture-oauth-secret"), {"message": "missing id"}])
def test_ambiguous_send_never_claims_success_or_retries(outcome):
    api = service()
    if isinstance(outcome, Exception):
        api.http.post.side_effect = outcome
    else:
        api.http.post.return_value.json.return_value = outcome
    result = api.write(snapshot(), "send", Event())
    assert result.status == "unverified" and "uncertain" in result.message
    assert "secret" not in result.message
    api.http.post.assert_called_once()


def test_expired_credentials_refresh_before_write_and_revocation_blocks_dispatch():
    api = service()
    api.credentials.valid = False
    api.credentials.refresh.side_effect = RuntimeError("fixture-oauth-secret")
    result = api.write(snapshot(), "send", Event())
    assert result.status == "failed" and "revoked" in result.message
    assert api.credentials is None
    api.http.post.assert_not_called()


def test_stop_before_dispatch_never_calls_http():
    api = service()
    stop = Event()
    stop.set()
    assert api.write(snapshot(), "send", stop).status == "failed"
    api.http.post.assert_not_called()


def test_oauth_requires_explicit_connect_and_storage_success():
    api = service()
    api.credentials = None
    api._credentials = Mock(return_value=Mock(valid=True, to_json=Mock(return_value="encrypted fixture")))
    api.oauth.return_value = "fixture credentials"
    api.vault.save.side_effect = OSError("fixture-oauth-secret")
    with pytest.raises(GmailError):
        api.connect(Event())
    assert api.credentials is None
    api.http.post.assert_not_called()


def test_restore_and_disconnect_do_not_prompt_for_consent():
    api = service()
    api.vault.load.return_value = None
    api.credentials = None
    assert not api.restore(Event())
    api.oauth.assert_not_called()
    api.disconnect()
    api.vault.clear.assert_called_once()
    api.http.post.assert_not_called()


def test_connect_and_restore_google_credential_json_are_local_and_scope_limited(tmp_path):
    value = json.dumps({"token":"fixture-oauth-secret", "refresh_token":"fixture-refresh-secret",
        "token_uri":"https://oauth2.googleapis.com/token", "client_id":"fixture-client",
        "client_secret":"fixture-client-secret", "scopes":list(SCOPES), "expiry":"2050-01-01T00:00:00Z"})
    vault = Mock()
    api = GmailService(client_path=tmp_path / "client.json", vault=vault, http=Mock(), oauth=Mock(return_value=value))
    api.connect(Event())
    assert api.credentials.valid
    assert set(api.credentials.scopes) == set(SCOPES)
    vault.save.assert_called_once()
    vault.load.return_value = vault.save.call_args.args[0]
    api.credentials = None
    assert api.restore(Event())
    api.oauth.assert_called_once()
    api.http.post.assert_not_called()


def test_expired_token_refresh_is_bounded_and_persists_before_send():
    api = service()
    api.credentials.valid = False
    credentials = api.credentials
    def refreshed(request):
        credentials.valid = True
    credentials.refresh.side_effect = refreshed
    credentials.to_json.return_value = "fixture refreshed credentials"
    assert api.write(snapshot(), "send", Event()).status == "verified"
    credentials.refresh.assert_called_once()
    api.vault.save.assert_called_once_with("fixture refreshed credentials")
    api.http.post.assert_called_once()


def test_oauth_cancel_discards_credentials_before_storage():
    api = service()
    stop = Event()
    stop.set()
    api.oauth.return_value = "fixture credentials"
    api._credentials = Mock(return_value=Mock())
    with pytest.raises(GmailError, match="cancelled"):
        api.connect(stop)
    api.vault.save.assert_not_called()
    assert api.credentials is None


def test_default_http_transport_disables_retries():
    api = GmailService(client_path="fixture-client.json", vault=Mock())
    assert api.http.get_adapter("https://gmail.googleapis.com").max_retries.total == 0
    api.close()


def test_malformed_or_overscoped_token_is_not_loaded():
    api = service()
    for scopes in (["https://mail.google.com/"], []):
        with pytest.raises(GmailError):
            api._credentials(json.dumps({"token_uri":"https://oauth2.googleapis.com/token", "scopes":scopes}))


def test_oauth_setup_failure_is_fixed_and_no_browser(tmp_path):
    with pytest.raises(GmailError, match="setup is missing"):
        authorize_desktop(tmp_path / "missing.json", Event())


def test_owned_oauth_uses_loopback_pkce_bounded_consent_no_url_output(tmp_path, monkeypatch, capsys):
    import google_auth_oauthlib.flow
    import logging
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"installed": {"auth_uri":"https://accounts.google.com/o/oauth2/auth",
                                             "token_uri":"https://oauth2.googleapis.com/token"}}))
    factory = Mock()
    factory.return_value.run_local_server.return_value.to_json.return_value = "fixture credentials"
    monkeypatch.setattr(google_auth_oauthlib.flow.InstalledAppFlow, "from_client_config", factory)
    pipe = Mock()
    old_disable = logging.root.manager.disable
    try:
        oauth_worker(pipe, Event(), str(path))
    finally:
        logging.disable(old_disable)
    assert factory.call_args.kwargs["scopes"] == list(SCOPES)
    assert factory.call_args.kwargs["autogenerate_code_verifier"] is True
    options = factory.return_value.run_local_server.call_args.kwargs
    assert options["host"] == "127.0.0.1" and options["port"] == 0
    assert options["timeout_seconds"] == 180 and "{url}" not in options["authorization_prompt_message"]
    assert capsys.readouterr().out == ""
    pipe.send.assert_called_once_with(("text", "fixture credentials"))


def test_prepare_is_local_and_private_and_write_tools_hidden(tmp_path):
    manager, api = controller(tmp_path)
    result = manager.registry.execute("draft_email", {"recipients":"test@example.com", "subject":"Private subject", "body":"Private body"})
    assert result.status == "verified"
    assert [d["function"]["name"] for d in manager.registry.definitions()] == ["draft_email"]
    api.http.post.assert_not_called()
    log = manager.registry.action_log.path.read_text()
    assert "Private body" not in log and "Private subject" not in log and "test@example.com" not in log
    assert "Private body" not in repr(manager.draft)
    manager.close()


@pytest.mark.parametrize("kind", ["send", "save"])
def test_gui_confirmation_one_use_exact_snapshot_no_double_click(tmp_path, kind):
    events = []
    manager, api = controller(tmp_path, lambda label, value: events.append((label,value)))
    manager.prepare("test@example.com", "Subject", "Private body")
    manager.start()
    try:
        assert manager.submit(kind)
        assert manager.submit(kind) is False
        wait(lambda: any(e[0] == "confirmation" for e in events))
        operation = next(v for k,v in events if k == "confirmation")
        api.http.post.assert_not_called()
        assert manager.gate.resolve(operation.request.id, turn_id="wrong", approved=True) is False
        assert manager.resolve(operation, True)
        assert not manager.resolve(operation, True)
        wait(lambda: not manager.busy.is_set())
        api.http.post.assert_called_once()
        assert operation.snapshot.body == "Private body"
        assert not manager.submit(kind)  # same exact attempted snapshot cannot be resent
        assert manager._dispatch(operation.id, kind).status == "failed"
    finally:
        finish(manager)


@pytest.mark.parametrize("reason", ["edit", "invalid_edit", "cancel", "expiry", "kill"])
def test_confirmation_invalidation_prevents_gmail_dispatch(tmp_path, reason):
    events=[]
    manager, api = controller(tmp_path, lambda k,v: events.append((k,v)), timeout=0.15 if reason == "expiry" else 1)
    manager.prepare("test@example.com", "Subject", "Body")
    manager.start()
    try:
        manager.submit("send")
        wait(lambda: any(k == "confirmation" for k,v in events))
        op = next(v for k,v in events if k == "confirmation")
        if reason == "edit":
            manager.edit("other@example.com", "Edited", "Other body")
        elif reason == "invalid_edit":
            manager.invalidate_edits()
        elif reason == "cancel":
            manager.cancel()
        elif reason == "kill":
            manager.gate.stop()
        else:
            wait(lambda: not manager.busy.is_set())
        assert not manager.resolve(op, True)
        wait(lambda: not manager.busy.is_set())
        api.http.post.assert_not_called()
    finally:
        finish(manager)


def test_model_cannot_create_or_approve_send_jobs(tmp_path):
    manager, api = controller(tmp_path)
    manager.prepare("test@example.com", "Subject", "Body")
    result = manager.registry.execute("send_email", {"operation_id": "a"*32}, turn_id="model-turn",
        on_confirmation=lambda r: manager.gate.resolve(r.id, turn_id=r.turn_id, approved=True))
    assert result.status == "failed"
    api.http.post.assert_not_called()
    manager.close()


def test_uncertain_snapshot_cannot_be_replayed_by_new_button_callback(tmp_path):
    events=[]
    manager,api = controller(tmp_path,lambda k,v: events.append((k,v)))
    api.http.post.side_effect = TimeoutError("fixture-oauth-secret")
    manager.prepare("test@example.com","Subject","Body")
    manager.start()
    try:
        manager.submit("send")
        wait(lambda: any(k == "confirmation" for k,v in events))
        operation = next(v for k,v in events if k == "confirmation")
        manager.resolve(operation,True)
        wait(lambda: not manager.busy.is_set())
        assert next(v for k,v in events if k == "result").status == "unverified"
        assert not manager.submit("send")
        api.http.post.assert_called_once()
    finally:
        finish(manager)


def test_worker_cleanup_error_cannot_escape_as_raw_thread_exception(tmp_path, capsys):
    events=[]
    manager,api = controller(tmp_path,lambda k,v: events.append((k,v)))
    api.close = Mock(side_effect=RuntimeError("fixture-oauth-secret"))
    manager.start()
    manager.gate.stop()
    with pytest.raises(GmailError) as error:
        manager.close()
    assert "fixture-oauth-secret" not in str(error.value)
    assert "fixture-oauth-secret" not in repr(events)
    assert "fixture-oauth-secret" not in capsys.readouterr().err
    assert not manager._thread.is_alive()


def test_unexpected_restore_failure_has_fixed_error_not_raw_exception(tmp_path, capsys):
    events=[]
    manager,api = controller(tmp_path,lambda k,v: events.append((k,v)))
    api.restore.side_effect = RuntimeError("fixture-oauth-secret")
    manager.start()
    wait(lambda: not manager._thread.is_alive())
    assert manager.closed.is_set()
    assert "fixture-oauth-secret" not in repr(events) + capsys.readouterr().err
    assert any(k == "error" for k,v in events)
    manager.close()
