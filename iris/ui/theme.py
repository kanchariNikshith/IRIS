"""Approved design.md palette shared by the orb and desktop window."""
import os
from pathlib import Path
COLORS = {
    "background": "#0B1020", "panel": "#141B2E", "border": "#222B45",
    "text": "#EAF0FF", "muted": "#8A94B0", "user": "#7FB2FF",
    "assistant": "#5EE6D0", "primary": "#4C7DFF", "secondary": "#1E2A47",
    "success": "#3DDC97", "warning": "#F5B942", "error": "#E5484D", "mic": "#FF4D4F",
}
STATES = {
    "idle": ("#65E3E5", "#12383E", "Idle. Type a command, press Mic, or use Ctrl+Alt+Space."),
    "listening": ("#2EC4B6", "#124E4A", "Listening. Go ahead."),
    "processing": ("#F5B942", "#5A4413", "Thinking..."),
    "speaking": ("#B983FF", "#3F2A66", "Speaking..."),
    "error": ("#E5484D", "#4D1C1E", "Something needs attention. See the message below."),
    "paused": ("#6B7390", "#1E2336", "Paused. Resume listening from the orb menu."),
}
STATUS = {"verified": ("Verified", "success"), "unverified": ("Could not confirm", "warning"),
          "failed": ("Failed", "error")}
ACTION_LABELS = {"open_url": "Website", "web_search": "Web search", "open_app": "App",
                "scroll": "Scroll", "press_keys": "Keyboard", "type_text": "Typing", "get_time": "Local time",
                "draft_email": "Email preview", "save_email_draft": "Gmail draft", "send_email": "Gmail send"}


def ensure_fonts():
    """Offscreen Qt on Windows may not enumerate any system fonts."""
    from PySide6.QtGui import QFontDatabase
    if not QFontDatabase.families() and os.name == "nt":
        directory = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf", "arial.ttf"):
            path = directory / filename
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))


def stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
    QMainWindow, QDialog, QWidget#root {{ background: {c['background']}; }}
    QMenuBar, QMenu {{ background: {c['background']}; color: {c['text']}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {c['panel']}; }}
    QFrame#message, QFrame#confirmation, QScrollArea {{ background: {c['panel']};
        border: 1px solid {c['border']}; border-radius: 12px; }}
    QWidget#conversation {{ background: transparent; }}
    QLabel {{ background: transparent; border: none; }}
    QLineEdit, QTextEdit {{ background: {c['panel']}; border: 1px solid {c['border']};
        border-radius: 10px; padding: 13px; font-size: 15px; selection-background-color: {c['primary']}; }}
    QLineEdit:focus {{ border: 1px solid {c['primary']}; }}
    QPushButton {{ background: {c['secondary']}; border: 1px solid {c['border']};
        border-radius: 10px; padding: 12px 18px; font-size: 15px; }}
    QPushButton:hover {{ border-color: {c['primary']}; }}
    QPushButton:pressed {{ background: {c['border']}; }}
    QPushButton#primary {{ background: {c['primary']}; border-color: {c['primary']}; }}
    QPushButton:disabled {{ color: {c['muted']}; background: {c['secondary']}; }}
    QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 6px; }}
    QMenu::item {{ padding: 8px 20px; }}
    QMenu::item:selected {{ background: {c['secondary']}; }}
    QScrollBar:vertical {{ background: {c['panel']}; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
