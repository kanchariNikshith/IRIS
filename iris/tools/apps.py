"""Launch catalogued Windows applications without a shell or arguments."""
from dataclasses import dataclass
import os
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable

import psutil

from iris.tools.registry import ToolResult


@dataclass(frozen=True)
class App:
    executable: str
    shortcuts: tuple[str, ...]
    system: bool = False


APP_CATALOG = {
    "notepad": App("notepad.exe", ("notepad",), True),
    "chrome": App("chrome.exe", ("google chrome", "chrome")),
    "edge": App("msedge.exe", ("microsoft edge",)),
    "spotify": App("spotify.exe", ("spotify",)),
    "word": App("winword.exe", ("word",)),
    "excel": App("excel.exe", ("excel",)),
}


def resolve_app(name: str) -> Path | None:
    """Resolve trusted installation paths, then inspect matching .lnk targets.

    Only the catalogued executable basename is accepted; shortcut arguments
    are discarded, and shortcuts to scripts/interpreters are never launched.
    """
    app = APP_CATALOG[name]
    if os.name != "nt":
        return None
    if app.system:
        target = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / app.executable
        if target.is_file():
            return target
    roots = []
    for variable in ("APPDATA", "PROGRAMDATA"):
        base = os.environ.get(variable)
        if base:
            roots.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    # COM is initialized on the calling tool thread and always released.
    import pythoncom
    from win32com.client import Dispatch
    pythoncom.CoInitialize()
    try:
        shell = Dispatch("WScript.Shell")
        for root in roots:
            for shortcut in root.rglob("*.lnk"):
                if shortcut.stem.casefold() not in app.shortcuts:
                    continue
                target = Path(shell.CreateShortCut(str(shortcut)).TargetPath)
                if target.name.casefold() == app.executable and target.is_absolute() and target.is_file():
                    return target
    finally:
        pythoncom.CoUninitialize()
    return None


def matching_processes(executable: str) -> set[tuple[int, float]]:
    found = set()
    for process in psutil.process_iter(["name", "pid", "create_time"]):
        try:
            info = process.info
            if (info["name"] or "").casefold() == executable:
                found.add((info["pid"], info["create_time"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


class AppTools:
    def __init__(self, stop: Event, *, resolver: Callable[[str], Path | None] = resolve_app,
                 launcher: Callable[[str], None] | None = None,
                 processes: Callable[[str], set] = matching_processes,
                 clock: Callable[[], float] = monotonic,
                 wait: Callable[[float], bool] | None = None) -> None:
        self.stop = stop
        self.resolver, self.launcher, self.processes = resolver, launcher, processes
        self.clock, self.wait = clock, wait or stop.wait

    def open_app(self, name: str) -> ToolResult:
        normalized = name.strip().casefold()
        if normalized not in APP_CATALOG:
            return ToolResult("failed", "That app is not in the allowed app catalog.")
        if self.stop.is_set():
            return ToolResult("failed", "Stopped.")
        target = self.resolver(normalized)
        app = APP_CATALOG[normalized]
        if target is None or target.name.casefold() != app.executable:
            return ToolResult("failed", "I couldn't find that app installed.")
        before = self.processes(app.executable)
        if self.stop.is_set():
            return ToolResult("failed", "Stopped.")
        launcher = self.launcher or os.startfile
        launcher(str(target))
        deadline = self.clock() + 8.0
        while not self.stop.is_set():
            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            appeared = self.processes(app.executable) - before
            if self.stop.is_set():
                break
            if appeared and self.clock() <= deadline:
                return ToolResult("verified", f"Opened {normalized}; a new matching process appeared.")
            remaining = deadline - self.clock()
            if remaining <= 0 or self.wait(min(0.2, remaining)):
                break
        if self.stop.is_set():
            return ToolResult("failed", "Stopped; the app may already have opened.")
        return ToolResult("unverified", "I tried to open the app but couldn't confirm a new process appeared.")
