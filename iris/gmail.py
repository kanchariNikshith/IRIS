"""Official Gmail REST API and desktop OAuth; credentials never enter diagnostics."""
from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.policy import SMTP
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from iris.tools.registry import ToolResult

SCOPES = ("https://www.googleapis.com/auth/gmail.compose",)
API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailError(Exception):
    """Fixed diagnostics, never SDK exceptions or token/request values."""
    def __init__(self, category="connection"):
        messages = {
            "setup": "Gmail setup is missing. Add a Google Desktop OAuth client JSON outside the project, then Connect Gmail.",
            "auth": "Gmail authorization expired or was revoked. Connect Gmail again.",
            "storage": "Gmail secure token storage is unavailable. Check Windows user-profile access.",
            "cancelled": "Gmail connection cancelled or timed out.",
            "connection": "Gmail connection failed. Check network access and OAuth setup, then try again.",
        }
        super().__init__(messages.get(category, messages["connection"]))


def private_directory() -> Path:
    # LocalAppData is outside the OneDrive/source checkout.
    directory = os.environ.get("LOCALAPPDATA")
    if not directory:
        raise GmailError("storage")
    return Path(directory) / "IRIS" / "gmail"


class TokenVault:
    """DPAPI current-user encryption; fail closed rather than store plaintext."""
    def __init__(self, path=None, *, protect=None, unprotect=None):
        self.path = Path(path) if path is not None else private_directory() / "token.dpapi"
        self._protect, self._unprotect = protect, unprotect

    def save(self, value: str):
        try:
            if self._protect is None:
                import win32crypt
                encrypted = win32crypt.CryptProtectData(value.encode(), "IRIS Gmail", None, None, None, 1)
            else:
                encrypted = self._protect(value.encode())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_bytes(encrypted)
            temporary.replace(self.path)
        except Exception:
            raise GmailError("storage") from None

    def load(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            encrypted = self.path.read_bytes()
            if self._unprotect is None:
                import win32crypt
                value = win32crypt.CryptUnprotectData(encrypted, None, None, None, 1)[1]
            else:
                value = self._unprotect(encrypted)
            return value.decode()
        except Exception:
            raise GmailError("storage") from None

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise GmailError("storage") from None


def oauth_worker(pipe, cancel, client_path):
    """Owned spawned worker for browser consent; parent can terminate/reap on stop."""
    logging.disable(logging.CRITICAL)  # Callback URLs contain authorization codes.
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        with Path(client_path).open(encoding="utf-8") as stream:
            configuration = json.load(stream)
        installed = configuration.get("installed", {})
        if (installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth"
                or installed.get("token_uri") != "https://oauth2.googleapis.com/token"):
            pipe.send(("error", "model"))
            return
        flow = InstalledAppFlow.from_client_config(configuration, scopes=list(SCOPES), autogenerate_code_verifier=True)
        credentials = flow.run_local_server(host="127.0.0.1", port=0,
            authorization_prompt_message="Authorize IRIS in your browser.",
            success_message="IRIS authorization received. You can close this tab.",
            timeout_seconds=180, access_type="offline", prompt="consent")
        if not cancel.is_set():
            pipe.send(("text", credentials.to_json()))
    except Exception:
        pipe.send(("error", "permission"))
    finally:
        pipe.close()


def authorize_desktop(client_path, stop):
    from iris.audio.worker import run_worker, AudioError
    from iris.config import PROJECT_ROOT
    if Path(client_path).resolve().is_relative_to(PROJECT_ROOT):
        raise GmailError("setup")
    if not Path(client_path).is_file():
        raise GmailError("setup")
    try:
        value = run_worker(oauth_worker, (str(client_path),), stop, timeout=190)
    except AudioError as error:
        raise GmailError("cancelled" if error.kind == "timeout" else "connection") from None
    if value is None or stop.is_set():
        raise GmailError("cancelled")
    return value


@dataclass(frozen=True, repr=False)
class EmailSnapshot:
    draft_id: str
    revision: int
    recipients: tuple[str, ...] = field(repr=False)
    subject: str = field(repr=False)
    body: str = field(repr=False)

    def __repr__(self):
        return f"EmailSnapshot(revision={self.revision}, recipients={len(self.recipients)})"


def validate_email(recipients: str, subject: str, body: str) -> tuple[str, ...]:
    if not all(isinstance(v, str) for v in (recipients, subject, body)):
        raise ValueError("Invalid email fields.")
    addresses = tuple(a.strip() for a in recipients.split(","))
    if not 1 <= len(addresses) <= 10 or len(set(addresses)) != len(addresses):
        raise ValueError("Use one to ten distinct email addresses.")
    pattern = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}"
    if any(len(a) > 254 or not re.fullmatch(pattern, a) for a in addresses):
        raise ValueError("Enter complete email addresses, separated by commas.")
    if not subject.strip() or len(subject) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in subject):
        raise ValueError("Enter a subject of 1 to 200 characters without control characters.")
    if not body.strip() or len(body) > 20000 or any(ord(c) < 32 and c not in "\n\r\t" for c in body):
        raise ValueError("Enter an email body of 1 to 20000 characters.")
    return addresses


def raw_message(snapshot: EmailSnapshot) -> str:
    validate_email(",".join(snapshot.recipients), snapshot.subject, snapshot.body)
    message = EmailMessage(policy=SMTP)
    message["To"] = ", ".join(snapshot.recipients)
    message["Subject"] = snapshot.subject
    message.set_content(snapshot.body)
    return urlsafe_b64encode(message.as_bytes()).decode("ascii")


class GmailService:
    def __init__(self, *, client_path=None, vault=None, http=None, oauth=authorize_desktop):
        self.client_path = Path(client_path) if client_path else private_directory() / "client.json"
        self.vault = vault or TokenVault()
        if http is None:
            import requests
            http = requests.Session()  # default retries=0; no AuthorizedSession send replays
        self.http, self.oauth = http, oauth
        self.credentials = None

    def _credentials(self, text):
        from google.oauth2.credentials import Credentials
        info = json.loads(text)
        if (info.get("token_uri") != "https://oauth2.googleapis.com/token"
                or set(info.get("scopes", ())) != set(SCOPES)):
            raise GmailError("auth")
        return Credentials.from_authorized_user_info(info, scopes=list(SCOPES))

    def restore(self, stop):
        try:
            value = self.vault.load()
            if value:
                self.credentials = self._credentials(value)
                self._ensure_token(stop)
        except Exception:
            self.credentials = None
            raise GmailError("auth") from None
        return self.credentials is not None

    def connect(self, stop):
        self.credentials = None
        try:
            value = self.oauth(self.client_path, stop)
            credentials = self._credentials(value)
            if stop.is_set():
                raise GmailError("cancelled")
            self.vault.save(credentials.to_json())
            self.credentials = credentials
            self._ensure_token(stop)
        except GmailError:
            self.credentials = None
            raise
        except Exception:
            self.credentials = None
            raise GmailError("connection") from None

    def disconnect(self):
        self.credentials = None
        self.vault.clear()  # local disconnection; revoke Google's grant in account settings

    def _ensure_token(self, stop):
        if stop.is_set():
            raise GmailError("cancelled")
        if self.credentials is None:
            raise GmailError("auth")
        if not self.credentials.valid:
            try:
                from google.auth.transport.requests import Request
                transport = Request(session=self.http)
                attempts = 0
                def bounded_request(*args, **kwargs):
                    nonlocal attempts
                    if attempts or stop.is_set():
                        raise GmailError("connection")
                    attempts += 1
                    kwargs["timeout"] = 20
                    return transport(*args, **kwargs)
                self.credentials.refresh(bounded_request)
                if not self.credentials.valid:
                    raise GmailError("auth")
                if stop.is_set():
                    raise GmailError("cancelled")
                self.vault.save(self.credentials.to_json())
            except Exception:
                self.credentials = None
                raise GmailError("auth") from None

    def write(self, snapshot: EmailSnapshot, kind: str, stop) -> ToolResult:
        if kind not in {"send", "save"}:
            return ToolResult("failed", "Unknown Gmail operation.")
        try:
            self._ensure_token(stop)
            raw = raw_message(snapshot)
        except GmailError as error:
            return ToolResult("failed", str(error))
        except ValueError:
            return ToolResult("failed", "Email fields are invalid.")
        if stop.is_set():
            return ToolResult("failed", "Stopped before Gmail dispatch.")
        payload = {"raw": raw} if kind == "send" else {"message": {"raw": raw}}
        endpoint = "/messages/send" if kind == "send" else "/drafts"
        try:
            response = self.http.post(API_ROOT + endpoint,
                headers={"Authorization": "Bearer " + self.credentials.token},
                json=payload, timeout=20, allow_redirects=False)
            status = response.status_code
            if 200 <= status < 300:
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"]:
                    if kind == "save":
                        return ToolResult("verified", "Gmail confirmed draft creation. It has not been sent.")
                    return ToolResult("verified", "Gmail confirmed message submission. Recipient delivery is not verified.")
            if status == 401:
                self.credentials = None
                try:
                    self.vault.clear()
                except GmailError:
                    pass
                return ToolResult("failed", "Gmail error (authorization, HTTP 401). Connect Gmail again.")
            if status in {400, 403, 404, 429}:
                guidance = {400: "Check the email fields.", 403: "Check Gmail API access and OAuth scopes.",
                            404: "Check Gmail API configuration.", 429: "Check Gmail quota; no automatic retry occurred."}
                return ToolResult("failed", f"Gmail error (request, HTTP {status}). {guidance[status]}")
        except Exception:
            pass  # Outcome after HTTP dispatch can be ambiguous; never replay a write.
        operation = "send" if kind == "send" else "draft creation"
        return ToolResult("unverified", f"Gmail {operation} outcome is uncertain. Check Gmail before trying again; no automatic retry occurred.")

    def close(self):
        self.http.close()
