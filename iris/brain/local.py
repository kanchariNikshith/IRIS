"""Exact, single-action local grammar; ambiguous language stays with Brain."""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from iris.tools.apps import APP_CATALOG


@dataclass(frozen=True)
class LocalCommand:
    tool: str
    arguments: dict[str, str | int]


def route_local(text: str) -> LocalCommand | None:
    text = re.sub(r"^iris[, ]+", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^please\s+", "", text, flags=re.IGNORECASE)
    command = text.casefold().rstrip(".!?")
    if command in {"what time is it", "what is the time", "time", "get time",
                   "what is today's date", "what day is it", "what is the date"}:
        return LocalCommand("get_time", {})
    match = re.fullmatch(r"(?:open|launch|start) (.+)", command)
    if match and match[1] in APP_CATALOG:
        return LocalCommand("open_app", {"name": match[1]})
    # Preserve the complete URL including its path, query and case.
    match = re.fullmatch(r"(?:open|visit) (https?://\S+)", text, re.IGNORECASE)
    if match:
        try:
            url = urlsplit(match[1])
            if (url.hostname and not url.username and not url.password
                    and not any(c in match[1] for c in '<>"\\')):
                return LocalCommand("open_url", {"url": match[1]})
        except ValueError:
            return None
    match = re.fullmatch(r"scroll (up|down)(?: (\d{1,2}))?", command)
    if match and 1 <= int(match[2] or 5) <= 20:
        return LocalCommand("scroll", {"direction": match[1], "amount": int(match[2] or 5)})
    if command in {"scroll to top", "scroll to bottom", "scroll top", "scroll bottom"}:
        return LocalCommand("scroll", {"direction": command.split()[-1]})
    keys = {"new tab": "new_tab", "close tab": "close_tab", "close current tab": "close_tab",
            "close the current tab": "close_tab", "go back": "go_back",
            "go forward": "go_forward", "volume up": "volume_up",
            "volume down": "volume_down", "mute": "mute"}
    if command in keys:
        return LocalCommand("press_keys", {"action": keys[command]})
    return None
