"""Append-only JSON lines, with bounded argument previews and redaction."""
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from iris.config import MASK, PROJECT_ROOT, redact


class ActionLog:
    def __init__(self, path: Path | str = PROJECT_ROOT / "data" / "actions.log",
                 secrets: tuple[str, ...] = ()) -> None:
        self.path = Path(path)
        self.secrets = secrets
        self._lock = Lock()

    def _safe(self, value: Any, name: str = "") -> Any:
        normalized = name.lower()
        if any(word in normalized for word in ("key", "password", "secret", "token")):
            return MASK
        if isinstance(value, Mapping):
            return {str(k): self._safe(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._safe(item, name) for item in value]
        if isinstance(value, str):
            safe = redact(value, self.secrets)
            return safe[:80] if "body" in normalized else safe[:500]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return "[unsupported value]"

    def write(self, tool: str, arguments: Mapping[str, Any], status: str,
              message: str, *, traceback: str | None = None) -> None:
        if status not in {"verified", "unverified", "failed"}:
            raise ValueError("Invalid action status.")
        if tool in {"draft_email", "send_email", "save_email_draft"}:
            for name, value in arguments.items():
                if name in {"body", "subject", "recipients"} and isinstance(value, str) and value:
                    message = message.replace(value, "[email content omitted]")
            arguments = {"field_count": len(arguments)}
        # A tool may echo the email body in its result; shorten that too.
        bodies: list[str] = []
        def collect_bodies(value: Any) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if "body" in str(key).lower() and isinstance(item, str) and len(item) > 80:
                        bodies.append(redact(item, self.secrets))
                    collect_bodies(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect_bodies(item)
        collect_bodies(arguments)
        def shorten_bodies(value: str) -> str:
            value = redact(value, self.secrets)
            for body in bodies:
                value = value.replace(body, body[:80])
            return value
        record = {"time": datetime.now(timezone.utc).isoformat(),
                  "tool": self._safe(tool), "arguments": self._safe(arguments),
                  "result": {"status": status, "message": self._safe(shorten_bodies(message))}}
        if traceback is not None:
            # Registry tracebacks omit exception values and source lines.
            record["traceback"] = self._safe(shorten_bodies(traceback))
        line = redact(json.dumps(record, ensure_ascii=False, allow_nan=False), self.secrets)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
