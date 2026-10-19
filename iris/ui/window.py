"""Approved Phase 4 layout, with plain-text conversation and confirmation card."""
from math import ceil
from time import monotonic
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                              QPushButton, QScrollArea, QVBoxLayout, QWidget)

from iris.config import redact
from iris.ui.orb import OrbFace
from iris.ui.theme import COLORS, STATES, STATUS, stylesheet


def label(text, *, color=None, size=13, bold=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setStyleSheet(f"color: {color or COLORS['text']}; font-size: {size}px; "
                        f"font-weight: {600 if bold else 400};")
    return widget


class MessageCard(QFrame):
    def __init__(self, role, text, *, status=None):
        super().__init__()
        self.setObjectName("message")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(7)
        color = COLORS["user"] if role.startswith("You") else COLORS["assistant"] if role == "IRIS" else COLORS["muted"]
        self.role = label(role, color=color, bold=True)
        self.body = label(text)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.role)
        layout.addWidget(self.body)
        self.status = None
        if status in STATUS:
            title, key = STATUS[status]
            self.status = label(title, color=COLORS[key], size=12)
            layout.addWidget(self.status)


class MainWindow(QMainWindow):
    text_submitted = Signal(str)
    voice_requested = Signal()
    confirmation_answered = Signal(str, str, bool)
    hidden = Signal()
    gmail_requested = Signal()
    exit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.secrets = ()
        self.setWindowTitle("IRIS — your voice, your laptop")
        self.resize(940, 640)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(stylesheet())
        self.cards = []
        self._confirmation = None
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 18, 28, 24)
        layout.setSpacing(14)
        header = QHBoxLayout()
        self.logo = OrbFace(diameter=140, label=False)
        header.addWidget(self.logo)
        branding = QVBoxLayout()
        branding.setSpacing(0)
        branding.addWidget(label("IRIS", size=58, bold=True))
        branding.addWidget(label("your voice, your laptop", color=COLORS["muted"], size=13))
        header.addLayout(branding)
        header.addStretch()
        self.state_badge = label("IDLE", color=STATES["idle"][0], bold=True)
        header.addWidget(self.state_badge, alignment=Qt.AlignmentFlag.AlignTop)
        self.gmail_button = QPushButton("Gmail: Disconnected")
        self.gmail_button.clicked.connect(self.gmail_requested.emit)
        header.addWidget(self.gmail_button)
        layout.addLayout(header)
        self.state_label = label(STATES["idle"][2], size=17)
        layout.addWidget(self.state_label)
        self.notice = label("", color=COLORS["warning"])
        self.notice.hide()
        layout.addWidget(self.notice)
        self.error = label("", color=COLORS["error"])
        self.error.hide()
        layout.addWidget(self.error)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.conversation = QWidget()
        self.conversation.setObjectName("conversation")
        self.messages = QVBoxLayout(self.conversation)
        self.messages.setContentsMargins(16, 16, 16, 16)
        self.messages.setSpacing(12)
        self.messages.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.conversation)
        self._follow_conversation = True
        self._follow_pending = False
        self._scrolling_programmatically = False
        bar = self.scroll.verticalScrollBar()
        bar.rangeChanged.connect(self.schedule_follow)
        bar.valueChanged.connect(self.scroll_position_changed)
        bar.sliderPressed.connect(lambda: setattr(self, "_follow_conversation", False))
        layout.addWidget(self.scroll, stretch=1)
        self.confirmation = QFrame()
        self.confirmation.setObjectName("confirmation")
        confirm_layout = QVBoxLayout(self.confirmation)
        confirm_layout.setContentsMargins(16, 12, 16, 12)
        self.confirmation_text = label("", size=15)
        self.confirmation_time = label("", color=COLORS["muted"], size=12)
        confirm_layout.addWidget(self.confirmation_text)
        confirm_layout.addWidget(self.confirmation_time)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.allow = QPushButton("Allow action")
        self.allow.setObjectName("primary")
        self.cancel = QPushButton("Cancel")
        self.allow.clicked.connect(lambda: self.answer_confirmation(True))
        self.cancel.clicked.connect(lambda: self.answer_confirmation(False))
        buttons.addWidget(self.allow)
        buttons.addWidget(self.cancel)
        confirm_layout.addLayout(buttons)
        self.confirmation.hide()
        layout.addWidget(self.confirmation)
        self.transcript = label("", color=COLORS["user"], size=12)
        self.transcript.hide()
        layout.addWidget(self.transcript)
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.input = QLineEdit()
        self.input.setMaxLength(4096)
        self.input.setPlaceholderText("Type a command...")
        self.input.setAccessibleName("Command")
        self.input.returnPressed.connect(self.submit)
        bottom.addWidget(self.input, stretch=1)
        self.mic = QPushButton("Mic")
        self.mic.setAccessibleName("Activate microphone")
        self.mic.setToolTip("Push to talk — Ctrl+Alt+Space")
        self.mic.clicked.connect(self.voice_requested.emit)
        bottom.addWidget(self.mic)
        self.send = QPushButton("Send")
        self.send.setObjectName("primary")
        self.send.clicked.connect(self.submit)
        bottom.addWidget(self.send)
        layout.addLayout(bottom)
        self._confirm_timer = QTimer(self)
        self._confirm_timer.setInterval(100)
        self._confirm_timer.timeout.connect(self.check_confirmation)
        menu = self.menuBar().addMenu("IRIS")
        menu.addAction("Gmail", self.gmail_requested.emit)
        menu.addAction("Exit IRIS", self.exit_requested.emit)

    def submit(self):
        text = self.input.text().strip()
        if text:
            self.text_submitted.emit(text)

    def append_message(self, role, text, *, status=None):
        card = MessageCard(role, redact(text, self.secrets), status=status)
        self.cards.append(card)
        self.messages.addWidget(card)
        self.schedule_follow()
        return card

    def scroll_position_changed(self, value):
        if not self._scrolling_programmatically and not self._follow_pending:
            self._follow_conversation = self.scroll.verticalScrollBar().maximum() - value <= 24

    def schedule_follow(self, *args):
        if self._follow_conversation:
            self._follow_pending = True
            QTimer.singleShot(0, self.follow_conversation)

    def follow_conversation(self):
        if self._follow_conversation:
            self._scrolling_programmatically = True
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
            self._scrolling_programmatically = False
        self._follow_pending = False

    def show_transcript(self, text):
        text = redact(text, self.secrets)
        self.transcript.setText("Recognized speech: " + text)
        self.transcript.show()
        self.append_message("You (speech)", text)

    def set_state(self, state):
        if state not in STATES:
            return
        self.state_badge.setText(state.upper())
        self.state_badge.setStyleSheet(f"color: {STATES[state][0]}; font-weight: 600;")
        self.state_label.setText(STATES[state][2])
        self.logo.set_state(state)

    def set_busy(self, busy, *, ready=True, paused=False):
        self.send.setEnabled(ready and not busy)
        self.mic.setEnabled(ready and not busy and not paused)
        self.input.setEnabled(ready)

    def show_error(self, text):
        self.error.setText(redact(text, self.secrets))
        self.error.show()

    def show_notice(self, text):
        self.notice.setText(redact(text, self.secrets))
        self.notice.show()

    def show_confirmation(self, request):
        if self._confirmation is not None:
            self.answer_confirmation(False)
        self._confirmation = request
        self.confirmation_text.setText("Allow " + redact(request.tool.replace("_", " "), self.secrets) + "?")
        self.confirmation.show()
        self._confirm_timer.start()
        self.check_confirmation()

    def answer_confirmation(self, approved):
        request = self._confirmation
        self.clear_confirmation()
        if request is not None:
            self.confirmation_answered.emit(request.id, request.turn_id, bool(approved))

    def clear_confirmation(self):
        self._confirmation = None
        self._confirm_timer.stop()
        self.confirmation.hide()

    def check_confirmation(self):
        request = self._confirmation
        if request is None:
            return
        remaining = request.deadline - monotonic()
        if request.event.is_set():
            self.clear_confirmation()
        elif remaining <= 0:
            self.answer_confirmation(False)
            self.show_notice("Confirmation expired. The action was not approved.")
        else:
            self.confirmation_time.setText(f"Expires in {ceil(remaining)} seconds.")

    def closeEvent(self, event):
        event.ignore()
        self.answer_confirmation(False)
        self.hide()

    def hideEvent(self, event):
        self.answer_confirmation(False)
        self.hidden.emit()
        super().hideEvent(event)
