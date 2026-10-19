"""Plain-text email review and exact-message approval, GUI thread only."""
from math import ceil
from time import monotonic
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton

from iris.ui.theme import stylesheet


def plain_label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class GmailPanel(QDialog):
    action = Signal(str)
    edited = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IRIS — Gmail review")
        self.setStyleSheet(stylesheet())
        self.resize(640, 610)
        layout = QVBoxLayout(self)
        self.connection = plain_label("Gmail: Disconnected")
        layout.addWidget(self.connection)
        row = QHBoxLayout()
        self.connect_button = QPushButton("Connect Gmail")
        self.disconnect_button = QPushButton("Disconnect Gmail")
        self.connect_button.clicked.connect(lambda: self.action.emit("connect"))
        self.disconnect_button.clicked.connect(lambda: self.action.emit("disconnect"))
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        layout.addLayout(row)
        layout.addWidget(plain_label("Review the complete email. Preparing a preview never saves or sends it."))
        layout.addWidget(plain_label("Recipients (comma-separated email addresses)"))
        self.recipients = QLineEdit()
        self.recipients.setMaxLength(2600)
        layout.addWidget(self.recipients)
        layout.addWidget(plain_label("Subject"))
        self.subject = QLineEdit()
        self.subject.setMaxLength(200)
        layout.addWidget(self.subject)
        layout.addWidget(plain_label("Body"))
        self.body = QTextEdit()
        self.body.setAcceptRichText(False)
        layout.addWidget(self.body, 1)
        self.feedback = plain_label("")
        layout.addWidget(self.feedback)
        buttons = QHBoxLayout()
        self.prepare = QPushButton("Prepare locally")
        self.prepare.clicked.connect(lambda: self.action.emit("preview"))
        self.save = QPushButton("Save Draft")
        self.send = QPushButton("Send")
        self.cancel = QPushButton("Cancel")
        self.save.clicked.connect(lambda: self.action.emit("save"))
        self.send.clicked.connect(lambda: self.action.emit("send"))
        self.cancel.clicked.connect(self.cancelled.emit)
        for button in (self.prepare, self.save, self.send, self.cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._loading = False
        for field in (self.recipients, self.subject):
            field.textChanged.connect(self._edited)
        self.body.textChanged.connect(self._edited)
        self._connected = False
        self._busy = False
        self.set_busy(False)

    def _edited(self, *args):
        if not self._loading:
            self.edited.emit()
            self.feedback.setText("Changes require a new confirmation.")

    def fields(self):
        return self.recipients.text(), self.subject.text(), self.body.toPlainText()

    def show_draft(self, snapshot):
        self._loading = True
        self.recipients.setText(", ".join(snapshot.recipients) if snapshot else "")
        self.subject.setText(snapshot.subject if snapshot else "")
        self.body.setPlainText(snapshot.body if snapshot else "")
        self._loading = False
        self.feedback.setText("Local preview only. Not saved or sent." if snapshot else "Local preview cancelled.")
        if snapshot:
            self.show()
            self.raise_()
            self.activateWindow()

    def set_connection(self, value):
        self._connected = value == "Connected"
        self.connection.setText("Gmail: " + value)
        self.set_busy(self._busy)

    def set_busy(self, busy):
        self._busy = busy
        self.connect_button.setEnabled(not busy and not self._connected)
        self.disconnect_button.setEnabled(not busy and self._connected)
        self.send.setEnabled(not busy and self._connected)
        self.save.setEnabled(not busy and self._connected)
        self.prepare.setEnabled(not busy)
        if not busy:
            self.freeze(False)

    def freeze(self, frozen):
        for field in (self.recipients, self.subject, self.body):
            field.setReadOnly(frozen)

    def closeEvent(self, event):
        self.cancelled.emit()
        super().closeEvent(event)


class EmailConfirmation(QDialog):
    """Displays an immutable snapshot; close/expiry are denial, never consent."""
    answered = Signal(bool)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self._answered = False
        self.setWindowTitle("Confirm exact email")
        self.setStyleSheet(stylesheet())
        self.resize(620, 520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)
        verb = "Send this exact email?" if operation.kind == "send" else "Save this exact draft to Gmail?"
        layout.addWidget(plain_label(verb))
        snapshot = operation.snapshot
        layout.addWidget(plain_label("To: " + ", ".join(snapshot.recipients)))
        layout.addWidget(plain_label("Subject: " + snapshot.subject))
        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(snapshot.body)
        layout.addWidget(body, 1)
        self.remaining = plain_label("")
        layout.addWidget(self.remaining)
        buttons = QHBoxLayout()
        self.approve = QPushButton("Send this email" if operation.kind == "send" else "Save this draft")
        self.deny = QPushButton("Cancel")
        self.deny.setDefault(True)
        self.approve.setAutoDefault(False)
        self.approve.clicked.connect(lambda: self.answer(True))
        self.deny.clicked.connect(self.reject)
        buttons.addWidget(self.approve)
        buttons.addWidget(self.deny)
        layout.addLayout(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        self.check()

    def check(self):
        request = self.operation.request
        remaining = request.deadline - monotonic()
        if remaining <= 0 or request.event.is_set() or self.operation.state != "pending":
            self.reject()
        else:
            self.remaining.setText(f"Approval expires in {ceil(remaining)} seconds. Editing cancels this request.")

    def answer(self, approved):
        if self._answered:
            return
        self._answered = True
        self.timer.stop()
        self.answered.emit(approved is True)
        super().done(1 if approved else 0)

    def reject(self):
        self.answer(False)

    def closeEvent(self, event):
        self.answer(False)
        event.accept()
