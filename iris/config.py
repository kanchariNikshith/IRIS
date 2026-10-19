"""Settings loading without exposing credentials."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MASK = "[REDACTED]"


class ConfigurationError(ValueError):
    """A required setting is missing or unreadable."""


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove supplied secrets and the process API key from text."""
    values = (*secrets, os.environ.get("OPENAI_API_KEY", ""), os.environ.get("GEMINI_API_KEY", ""))
    for secret in sorted(set(values), key=len, reverse=True):
        if secret:
            text = text.replace(secret, MASK)
    return text


@dataclass(frozen=True, repr=False)
class Config:
    openai_api_key: str = field(repr=False)
    openai_model: str = ""
    kill_switch_hotkey: str = "<ctrl>+<alt>+<esc>"
    push_to_talk_hotkey: str = "<ctrl>+<alt>+<space>"
    whisper_model: str = "base"
    ai_provider: str = "openai"
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = ""
    gmail_client_file: str = ""

    @property
    def secrets(self) -> tuple[str, ...]:
        return tuple(key for key in (self.openai_api_key, self.gemini_api_key) if key)

    @property
    def model(self) -> str:
        return self.gemini_model if self.ai_provider == "gemini" else self.openai_model

    def __repr__(self) -> str:
        return f"Config({self.masked()!r})"

    def masked(self) -> dict[str, str]:
        return {
            "OPENAI_API_KEY": MASK,
            "GEMINI_API_KEY": MASK,
            "AI_PROVIDER": redact(self.ai_provider, self.secrets),
            "OPENAI_MODEL": redact(self.openai_model, self.secrets),
            "GEMINI_MODEL": redact(self.gemini_model, self.secrets),
            "KILL_SWITCH_HOTKEY": redact(self.kill_switch_hotkey, self.secrets),
            "PUSH_TO_TALK_HOTKEY": redact(self.push_to_talk_hotkey, self.secrets),
            "WHISPER_MODEL": redact(self.whisper_model, self.secrets),
            "GMAIL_OAUTH_CLIENT_FILE": redact(self.gmail_client_file, self.secrets),
        }


def load_config(
    env_path: Path | str = PROJECT_ROOT / ".env",
    environ: Mapping[str, str] | None = None,
    *, require_cloud: bool = True,
) -> Config:
    """Load .env; process settings take precedence without mutating them."""
    try:
        values = dict(dotenv_values(env_path, interpolate=False))
    except (OSError, UnicodeError):
        raise ConfigurationError("Could not read .env settings.") from None
    values.update(os.environ if environ is None else environ)
    provider = (values.get("AI_PROVIDER") or "openai").strip().lower()
    if provider not in {"openai", "gemini"}:
        raise ConfigurationError("AI_PROVIDER must be openai or gemini.")
    key = (values.get("OPENAI_API_KEY") or "").strip()
    gemini_key = (values.get("GEMINI_API_KEY") or "").strip()
    key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    if require_cloud and not (gemini_key if provider == "gemini" else key):
        raise ConfigurationError(f"{key_name} is required. Set it in .env or the environment.")
    return Config(
        openai_api_key=key,
        openai_model=(values.get("OPENAI_MODEL") or "").strip(),
        kill_switch_hotkey=values.get("KILL_SWITCH_HOTKEY") or "<ctrl>+<alt>+<esc>",
        push_to_talk_hotkey=values.get("PUSH_TO_TALK_HOTKEY") or "<ctrl>+<alt>+<space>",
        whisper_model=values.get("WHISPER_MODEL") or "base",
        ai_provider=provider,
        gemini_api_key=gemini_key,
        gemini_model=(values.get("GEMINI_MODEL") or "").strip(),
        gmail_client_file=(values.get("GMAIL_OAUTH_CLIENT_FILE") or "").strip(),
    )
