"""Local email preparation and user-owned Gmail writes through the registry."""
from dataclasses import dataclass, field
from queue import Queue, Empty
from threading import Event, RLock, Thread
from uuid import uuid4
from time import monotonic
import json
import re
from pathlib import Path

from iris.gmail import EmailSnapshot, GmailError, validate_email
from iris.security.permissions import Permission
from iris.tools.registry import Tool, ToolResult


def resolve_recipients(value, contacts_path=None):
    """Optional local contacts and spoken at/dot; never guess an address."""
    contacts = {}
    if contacts_path is not None and Path(contacts_path).is_file():
        try:
            path = Path(contacts_path)
            if path.stat().st_size > 64000:
                raise ValueError("Invalid contacts file.")
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in data.items()):
                raise ValueError("Invalid contacts file.")
            contacts = {key.casefold(): address for key,address in data.items()}
        except (OSError, ValueError):
            raise ValueError("The local contacts file is invalid. Use a complete email address.") from None
    result = []
    for item in value.split(","):
        address = contacts.get(item.strip().casefold(), item.strip())
        address = re.sub(r"\s+at\s+", "@", address, flags=re.IGNORECASE)
        address = re.sub(r"\s+dot\s+", ".", address, flags=re.IGNORECASE)
        result.append(address)
    return ",".join(result)


@dataclass(repr=False)
class EmailOperation:
    id: str
    kind: str
    snapshot: EmailSnapshot = field(repr=False)
    state: str = "pending"
    request: object = None


class EmailController:
    """One Gmail worker. The model prepares previews, never creates write jobs."""
    def __init__(self, registry, service, *, emit=lambda kind, value: None, secrets=(), contacts_path=None):
        self.registry, self.gate, self.service = registry, registry.gate, service
        self.emit, self.secrets = emit, secrets
        self.contacts_path = contacts_path
        self.draft = None
        self._operations = {}
        self._lock = RLock()
        self.busy = Event()
        self.closed = Event()
        self._cleanup_failed = Event()
        self._cancel = Event()
        self._jobs = Queue(maxsize=1)
        self._thread = Thread(target=self._work, name="iris-gmail")
        self._started = False
        registry.register(Tool("draft_email", {
            "type": "object", "properties": {
                "recipients": {"type": "string", "minLength": 3, "maxLength": 2600},
                "subject": {"type": "string", "minLength": 1, "maxLength": 200},
                "body": {"type": "string", "minLength": 1, "maxLength": 20000}},
            "required": ["recipients", "subject", "body"]}, Permission.AUTO,
            self.prepare, "Prepare a local editable email preview only. Does not save or send; sending needs GUI review."))
        for name, kind in (("send_email", "send"), ("save_email_draft", "save")):
            registry.register(Tool(name, {"type": "object", "properties": {
                "operation_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"}},
                "required": ["operation_id"]}, Permission.CONFIRM,
                lambda operation_id, k=kind: self._dispatch(operation_id, k),
                "GUI-owned Gmail write; never exposed to the model.", exposed=False))

    def start(self):
        if not self._started:
            self._started = True
            self._thread.start()

    def _fields(self, recipients, subject, body):
        if any(secret in value for secret in self.secrets if secret
               for value in (recipients, subject, body)):
            raise ValueError("Email fields contain configured credentials and cannot be used.")
        return validate_email(recipients, subject, body)

    def _invalidate(self):
        for operation in self._operations.values():
            if operation.state == "pending":
                operation.state = "cancelled"
                if operation.request is not None:
                    self.gate.resolve(operation.request.id, turn_id=operation.request.turn_id, approved=False)

    def prepare(self, recipients, subject, body):
        recipients = resolve_recipients(recipients, self.contacts_path)
        addresses = self._fields(recipients, subject, body)
        with self._lock:
            if self.gate.kill_switch.is_set() or self.closed.is_set():
                return ToolResult("failed", "Stopped.")
            if any(op.state == "running" for op in self._operations.values()):
                return ToolResult("failed", "Wait for the current Gmail operation to finish.")
            self._invalidate()
            self.draft = EmailSnapshot(uuid4().hex, 1, addresses, subject, body)
            snapshot = self.draft
        self.emit("draft", snapshot)
        return ToolResult("verified", "Prepared a local email preview for review. Nothing has been saved to Gmail or sent.")

    def edit(self, recipients, subject, body):
        addresses = self._fields(recipients, subject, body)
        with self._lock:
            if self.draft is None:
                raise ValueError("Prepare an email first.")
            if any(op.state == "running" for op in self._operations.values()):
                raise ValueError("Wait for the current Gmail operation to finish.")
            if (addresses, subject, body) == (self.draft.recipients, self.draft.subject, self.draft.body):
                return self.draft
            self._invalidate()
            self.draft = EmailSnapshot(self.draft.draft_id, self.draft.revision + 1, addresses, subject, body)
            return self.draft

    def invalidate_edits(self):
        # Every keystroke invalidates pending approval, including temporarily invalid text.
        with self._lock:
            self._invalidate()

    def cancel(self):
        self._cancel.set()
        with self._lock:
            self._invalidate()
            if not any(op.state == "running" for op in self._operations.values()):
                self.draft = None
        self.emit("draft", None)

    def submit(self, kind):
        with self._lock:
            if self.busy.is_set() or self.closed.is_set() or self.gate.kill_switch.is_set():
                return False
            if kind not in {"connect", "disconnect", "send", "save"}:
                return False
            operation = None
            if kind in {"send", "save"}:
                if self.draft is None:
                    return False
                if any(op.kind == kind and op.snapshot == self.draft and op.state == "attempted"
                       for op in self._operations.values()):
                    return False
                operation = EmailOperation(uuid4().hex, kind, self.draft)
                self._operations[operation.id] = operation
            self.busy.set()
            self._cancel.clear()
            self._jobs.put_nowait((kind, operation))
        self.emit("busy", True)
        return True

    def _bind(self, operation, request):
        with self._lock:
            if operation.state != "pending" or self.draft != operation.snapshot:
                self.gate.resolve(request.id, turn_id=request.turn_id, approved=False)
                return
            operation.request = request
        self.emit("confirmation", operation)

    def prepare_from_editor(self, fields):
        self._fields(*fields)
        with self._lock:
            if self.busy.is_set() or self.closed.is_set() or self.gate.kill_switch.is_set():
                return False
            self.busy.set()
            self._cancel.clear()
            self._jobs.put_nowait(("preview", tuple(fields)))
        self.emit("busy", True)
        return True

    def resolve(self, operation, approved):
        with self._lock:
            if (self._operations.get(operation.id) is not operation or operation.state != "pending"
                    or self.draft != operation.snapshot or operation.request is None):
                return False
            return self.gate.resolve(operation.request.id, turn_id=operation.request.turn_id, approved=approved is True)

    def _dispatch(self, operation_id, kind):
        with self._lock:
            operation = self._operations.get(operation_id)
            if (operation is None or operation.kind != kind or operation.state != "pending"
                    or operation.request is None or not operation.request.approved
                    or not operation.request.event.is_set() or monotonic() >= operation.request.deadline
                    or self.draft != operation.snapshot or self.gate.kill_switch.is_set()):
                return ToolResult("failed", "Gmail operation cancelled, changed or already attempted.")
            operation.state = "running"
        try:
            from iris.audio.worker import StopToken
            return self.service.write(operation.snapshot, kind,
                                      StopToken(self.gate.kill_switch, self.closed, self._cancel))
        finally:
            with self._lock:
                operation.state = "attempted"  # No replay, even after an ambiguous result.

    def _work(self):
        try:
            try:
                connected = self.service.restore(self.gate.kill_switch)
                self.emit("connection", "Connected" if connected else "Disconnected")
            except GmailError as error:
                self.emit("connection", "Disconnected")
                self.emit("error", str(error))
            while not self.closed.is_set() and not self.gate.kill_switch.is_set():
                try:
                    kind, operation = self._jobs.get(timeout=0.05)
                except Empty:
                    continue
                try:
                    if self.gate.kill_switch.is_set():
                        continue
                    if kind == "preview":
                        fields = dict(zip(("recipients", "subject", "body"), operation))
                        result = self.registry.execute("draft_email", fields, turn_id=uuid4().hex)
                        self.emit("result", result)
                    elif operation is not None:
                        name = "send_email" if kind == "send" else "save_email_draft"
                        result = self.registry.execute(name, {"operation_id": operation.id},
                            turn_id=operation.id, on_confirmation=lambda request: self._bind(operation, request))
                        self.emit("result", result)
                        self.emit("connection", "Connected" if self.service.credentials is not None else "Disconnected")
                    else:
                        if kind == "connect":
                            self.emit("connection", "Connecting — authorize in your browser")
                            from iris.audio.worker import StopToken
                            self.service.connect(StopToken(self.gate.kill_switch, self.closed, self._cancel))
                        else:
                            self.service.disconnect()
                        self.emit("connection", "Connected" if self.service.credentials is not None else "Disconnected")
                        self.registry.action_log.write("gmail_" + kind, {}, "verified", "Gmail connection state updated.")
                except GmailError as error:
                    self.emit("connection", "Connected" if self.service.credentials is not None else "Disconnected")
                    self.emit("error", str(error))
                    try:
                        self.registry.action_log.write("gmail_" + kind, {}, "failed", str(error))
                    except OSError:
                        pass
                except Exception:
                    self.emit("error", "Gmail operation failed safely. Check setup and connection.")
                finally:
                    if isinstance(operation, EmailOperation):
                        with self._lock:
                            if operation.state == "pending":
                                operation.state = "cancelled"
                    self.busy.clear()
                    self.emit("busy", False)
                    self._jobs.task_done()
        except Exception:
            self.closed.set()
            self.emit("error", "Gmail worker stopped safely. Check the connection and restart IRIS.")
        finally:
            try:
                self.service.close()
            except Exception:
                self._cleanup_failed.set()
                self.emit("error", "Gmail connection cleanup failed. Restart IRIS after checking its owned workers.")

    def close(self):
        self.closed.set()
        self.invalidate_edits()
        if self._started:
            self._thread.join()  # Only the off-Qt lifecycle owner calls close.
            if self._cleanup_failed.is_set():
                raise GmailError("connection")
        else:
            self.service.close()
