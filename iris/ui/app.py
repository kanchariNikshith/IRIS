"""Qt signals adapt the existing voice/controller safety boundary to widgets."""
from threading import Event, Thread
from time import monotonic
from hashlib import sha256
from typing import Any
from PySide6.QtCore import QObject, Signal, Slot, QTimer, Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QToolTip
from html import escape
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from iris.audio.voice import VoiceController, start_voice_hotkeys
from iris.config import ConfigurationError, PROJECT_ROOT, redact
from iris.ui.orb import FloatingOrb
from iris.ui.window import MainWindow
from iris.ui.theme import ACTION_LABELS, ensure_fonts
from iris.gmail import GmailService
from iris.tools.email import EmailController
from iris.ui.gmail import GmailPanel, EmailConfirmation


class UiBridge(QObject):
    event = Signal(str, str)
    action = Signal(str, str, str)
    confirmation = Signal(object)
    ready = Signal()
    closed = Signal(bool)
    email = Signal(str, object)


class GuiInstance(QObject):
    """A second GUI launch only shows the first; IPC cannot submit commands."""
    show_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
        self._sockets = {}

    def acquire(self, name=None):
        name = name or "iris-gui-" + sha256(str(PROJECT_ROOT).encode()).hexdigest()[:20]
        socket = QLocalSocket(self)
        socket.connectToServer(name)
        if socket.waitForConnected(150):
            socket.write(b"show\n")
            socket.waitForBytesWritten(150)
            socket.disconnectFromServer()
            socket.deleteLater()
            return False
        socket.abort()
        socket.deleteLater()
        if not self.server.listen(name):
            # A simultaneous launcher must not start another listener/controller.
            raise RuntimeError("The IRIS GUI instance endpoint is unavailable.")
        return True

    @Slot()
    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self._sockets[socket] = b""
            socket.readyRead.connect(lambda s=socket: self.read(s))
            socket.disconnected.connect(lambda s=socket: self.discard(s))
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.disconnectFromServer)
            timer.start(1000)
            self.read(socket)

    def read(self, socket):
        data = self._sockets.get(socket, b"") + bytes(socket.readAll())
        self._sockets[socket] = data[:65]
        if len(data) > 64 or b"\n" in data:
            if data == b"show\n":
                self.show_requested.emit()
            socket.disconnectFromServer()

    def discard(self, socket):
        self._sockets.pop(socket, None)
        socket.deleteLater()

    def close(self):
        for socket in list(self._sockets):
            socket.abort()
        self._sockets.clear()
        self.server.close()


class DesktopSession(QObject):
    finished = Signal(bool)

    def __init__(self, *, config_factory, brain_factory, controller_factory=VoiceController,
                 listener_factory=None, gmail_factory=GmailService, parent=None):
        super().__init__(parent)
        self.bridge = UiBridge(self)
        self.window = MainWindow()
        self.orb = FloatingOrb()
        self.controller = None
        self.brain = None
        self.listener = None
        self.email_controller = None
        self._gmail_factory = gmail_factory
        self.gmail_panel = GmailPanel(self.window)
        self.email_dialog = None
        self.secrets = ()
        self._config_factory, self._brain_factory = config_factory, brain_factory
        self._controller_factory, self._listener_factory = controller_factory, listener_factory
        self._stopping = Event()
        self._ready = False
        self._shutdown_thread = None
        self._startup_thread = None
        self._last_state = "idle"
        self._confirmation_dialog = None
        self._error_until = 0.0
        self.bridge.event.connect(self.receive, Qt.ConnectionType.QueuedConnection)
        self.bridge.action.connect(self.action_result, Qt.ConnectionType.QueuedConnection)
        self.bridge.confirmation.connect(self.confirmation_request, Qt.ConnectionType.QueuedConnection)
        self.bridge.ready.connect(self.ready, Qt.ConnectionType.QueuedConnection)
        self.bridge.closed.connect(self.shutdown_done, Qt.ConnectionType.QueuedConnection)
        self.bridge.email.connect(self.email_event, Qt.ConnectionType.QueuedConnection)
        self.window.gmail_requested.connect(self.show_gmail)
        self.window.exit_requested.connect(self.shutdown)
        self.window.hidden.connect(self.cancel_email_approval)
        self.gmail_panel.action.connect(self.email_action)
        self.gmail_panel.edited.connect(self.email_edited)
        self.gmail_panel.cancelled.connect(self.cancel_email)
        self.window.text_submitted.connect(self.submit)
        self.window.voice_requested.connect(self.listen)
        self.window.confirmation_answered.connect(self.resolve)
        self.orb.clicked.connect(self.listen)
        self.orb.toggle_window.connect(self.toggle_window)
        self.orb.toggle_pause.connect(self.toggle_pause)
        self.orb.quit_requested.connect(self.shutdown)
        self.orb.motion_changed.connect(self.reduce_motion)
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self.poll)
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self.release_error)
        self.window.set_busy(False, ready=False)
        pixmap = QPixmap(120, 120)
        pixmap.fill(Qt.GlobalColor.transparent)
        self.orb.render(pixmap)
        icon = QIcon(pixmap)
        self.window.setWindowIcon(icon)
        self.orb.setWindowIcon(icon)

    def start(self):
        if self._startup_thread is not None:
            return
        self.orb.show()
        self.orb.last_message = "Starting IRIS..."
        self.window.show_notice("Starting IRIS...")
        self._poll.start()
        self._startup_thread = Thread(target=self._startup, name="iris-ui-startup")
        self._startup_thread.start()

    def _startup(self):
        try:
            config = self._config_factory()
            self.secrets = config.secrets
            self.brain = self._brain_factory(config, before_input=self.prepare_input)
            def confirmation(request):
                if request.tool in {"send_email", "save_email_draft"}:
                    self.brain.registry.gate.resolve(request.id, turn_id=request.turn_id, approved=False)
                else:
                    self.bridge.confirmation.emit(request)
            self.brain.registry.on_confirmation = confirmation
            def observe(name, result):
                self.bridge.action.emit(redact(name, self.secrets), result.status,
                                        redact(result.message, self.secrets))
            self.brain.registry.on_result = observe
            self.email_controller = EmailController(self.brain.registry,
                self._gmail_factory(client_path=config.gmail_client_file or None),
                emit=self.bridge.email.emit, secrets=self.secrets, contacts_path=PROJECT_ROOT / "data" / "contacts.json")
            self.email_controller.start()
            self.controller = self._controller_factory(self.brain, config.whisper_model,
                                                       emit=self.bridge.event.emit)
            if self._stopping.is_set():
                return
            self.controller.start()
            try:
                self.listener = start_voice_hotkeys(self.controller, config.push_to_talk_hotkey,
                                                    config.kill_switch_hotkey, self._listener_factory)
            except Exception:
                self.bridge.event.emit("State", "error")
                self.bridge.event.emit("Error", "Global hotkeys are unavailable. Use Mic and type stop or quit.")
            self.bridge.ready.emit()
        except ConfigurationError as error:
            self.bridge.event.emit("State", "error")
            self.bridge.event.emit("Error", redact(str(error), self.secrets))
        except Exception:
            self.bridge.event.emit("State", "error")
            self.bridge.event.emit("Error", "IRIS couldn't start. Check installed dependencies and masked configuration with --check.")

    def prepare_input(self, stop):
        if stop.is_set() or self._stopping.is_set():
            return False
        self.bridge.event.emit("Notice", "Click the target window and keep the mouse over its content. Input starts in 3 seconds; Ctrl+Alt+Esc cancels.")
        return not stop.wait(3.0)

    @Slot()
    def ready(self):
        if self._stopping.is_set():
            return
        self.window.secrets = self.secrets
        self._ready = True
        self.orb.last_message = "Click to listen. Right-click to open chat/setup. Ctrl+Alt+Space also listens."
        self.orb.setToolTip(self.orb.last_message)
        self.orb.set_state(self._last_state)
        self.window.notice.hide()
        self.poll()

    @Slot(str)
    def submit(self, text):
        if self._stopping.is_set() or self.controller is None or not self._ready:
            return
        command = self.controller._control(text)
        if command in {"quit", "exit", "stop"}:
            self.window.append_message("You", redact(text, self.secrets))
            self.shutdown()
            return
        if self.controller.submit_text(text):
            self.window.append_message("You", redact(text, self.secrets))
            self.window.input.clear()
            self.window.error.hide()
            self.window.notice.hide()
            self.poll()

    @Slot()
    def listen(self):
        if self.controller is not None and self._ready and not self._stopping.is_set():
            if self.controller.request_listen():
                self.window.error.hide()
                self.poll()

    @Slot()
    def toggle_pause(self):
        if self.controller is not None and self._ready and not self._stopping.is_set():
            command = "start listening" if self.controller.paused.is_set() else "stop listening"
            self.controller.submit_text(command)
            self.poll()

    @Slot()
    def restore_orb(self):
        self.orb.reclamp()
        self.orb.show()
        self.orb.raise_()

    @Slot()
    def show_window(self):
        self.orb.reclamp()
        self.orb.show()
        self.orb.raise_()
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        self.window.input.setFocus()

    @Slot()
    def show_gmail(self):
        self.show_window()
        self.gmail_panel.show()
        self.gmail_panel.raise_()

    @Slot(str, object)
    def email_event(self, kind, value):
        if self._stopping.is_set():
            return
        if kind == "draft":
            self.show_window()
            self.gmail_panel.show_draft(value)
        elif kind == "connection":
            self.gmail_panel.set_connection(value)
            status = "Connecting" if value.startswith("Connecting") else value
            self.window.gmail_button.setText("Gmail: " + status)
        elif kind == "busy":
            self.gmail_panel.set_busy(bool(value))
        elif kind == "confirmation":
            if value.request.event.is_set() or value.state != "pending":
                return
            if self.email_dialog is not None:
                self.email_dialog.reject()
            self.email_dialog = EmailConfirmation(value, self.gmail_panel)
            def answer(approved):
                accepted = self.email_controller.resolve(value, approved)
                if accepted and approved:
                    self.gmail_panel.freeze(True)
            self.email_dialog.answered.connect(answer)
            self.email_dialog.show()
        elif kind == "result":
            self.gmail_panel.feedback.setText(value.status.capitalize() + ": " + value.message)
        else:
            text = redact(str(value), self.secrets)
            self.gmail_panel.feedback.setText(text)
            self.receive("Error", text)

    @Slot(str)
    def email_action(self, kind):
        if self.email_controller is None or self._stopping.is_set():
            return
        try:
            if kind == "preview":
                if not self.email_controller.prepare_from_editor(self.gmail_panel.fields()):
                    self.gmail_panel.feedback.setText("Wait for the current Gmail operation.")
                return
            if kind in {"send", "save"}:
                self.email_controller.edit(*self.gmail_panel.fields())
            if not self.email_controller.submit(kind):
                self.gmail_panel.feedback.setText("Wait for the current Gmail operation or prepare a preview first.")
        except ValueError as error:
            self.gmail_panel.feedback.setText(redact(str(error), self.secrets))

    @Slot()
    def email_edited(self):
        self.cancel_email_approval()

    @Slot()
    def cancel_email_approval(self):
        if self.email_controller is not None:
            self.email_controller.invalidate_edits()
        if self.email_dialog is not None:
            self.email_dialog.reject()

    @Slot()
    def cancel_email(self):
        self.cancel_email_approval()
        if self.email_controller is not None:
            self.email_controller.cancel()

    @Slot()
    def toggle_window(self):
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.answer_confirmation(False)
            self.window.hide()
        else:
            self.show_window()

    @Slot(bool)
    def reduce_motion(self, enabled):
        self.orb.set_reduced_motion(enabled)
        self.window.logo.set_reduced_motion(enabled)

    @Slot(str, str)
    def receive(self, label, text):
        if self._stopping.is_set():
            return
        text = redact(text, self.secrets)
        if label != "State":
            self.orb.last_message = text
            self.orb.setToolTip("IRIS — " + self._last_state + "\n" + text)
            if label in {"Notice", "Error"} or text.startswith(("Gemini error (", "OpenAI error (")):
                QToolTip.showText(self.orb.mapToGlobal(self.orb.rect().topLeft()),
                                 escape(text), self.orb, self.orb.rect(), 8000)
        if label == "State":
            self._last_state = text
            if text == "error":
                self._error_until = monotonic() + 0.6
            if text == "idle" and monotonic() < self._error_until:
                self._error_timer.start(max(1, int((self._error_until - monotonic()) * 1000)))
            else:
                self.orb.set_state(text)
                self.window.set_state(text)
        elif label == "Heard":
            self.window.show_transcript(text)
        elif label == "Notice":
            self.window.show_notice(text)
        else:
            self.window.append_message("IRIS", text)
            failed_reply = text.startswith(("Gemini error (", "OpenAI error (", "I couldn't carry out", "Something went wrong"))
            if label == "Error" or failed_reply or self._last_state == "error":
                if failed_reply:
                    self.receive("State", "error")
                self.window.show_error(text)
        self.poll()

    @Slot()
    def release_error(self):
        if self._last_state == "idle" and not self._stopping.is_set():
            self.orb.set_state("idle")
            self.window.set_state("idle")

    @Slot(str, str, str)
    def action_result(self, name, status, message):
        if not self._stopping.is_set():
            self.window.append_message(ACTION_LABELS.get(name, "Tool request"),
                                       redact(message, self.secrets), status=status)
            if status == "failed":
                self.receive("State", "error")
                self.window.show_error(message)

    @Slot(object)
    def confirmation_request(self, request):
        if self._stopping.is_set() or self.brain is None:
            return
        if request.event.is_set() or request.deadline <= monotonic() or self.brain.registry.gate.kill_switch.is_set():
            return
        self.window.show_confirmation(request)
        dialog = QMessageBox(QMessageBox.Icon.Question, "IRIS confirmation",
                             redact("Allow " + ACTION_LABELS.get(request.tool, "this action") + "?", self.secrets),
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self._confirmation_dialog = dialog
        def answer(result):
            self.resolve(request.id, request.turn_id, result == QMessageBox.StandardButton.Yes)
            if self.window._confirmation is request:
                self.window.clear_confirmation()
        dialog.finished.connect(answer)
        dialog.open()

    @Slot(str, str, bool)
    def resolve(self, request_id, turn_id, approved):
        if self.brain is not None:
            self.brain.registry.gate.resolve(request_id, turn_id=turn_id, approved=approved)

    @Slot()
    def poll(self):
        if self._stopping.is_set():
            return
        if self._confirmation_dialog is not None and self.window._confirmation is None:
            self._confirmation_dialog.reject()
            self._confirmation_dialog.deleteLater()
            self._confirmation_dialog = None
        if self.controller is not None:
            if self.controller.gate.kill_switch.is_set():
                self.shutdown()
                return
            self.window.set_busy(self.controller.busy.is_set() or self.controller.speaker.busy.is_set(),
                                 ready=self._ready, paused=self.controller.paused.is_set())

    @Slot()
    def shutdown(self):
        if self._stopping.is_set():
            return
        self._stopping.set()
        self._poll.stop()
        self._error_timer.stop()
        self.cancel_email_approval()
        self.gmail_panel.hide()
        self.window.answer_confirmation(False)
        if self._confirmation_dialog is not None:
            self._confirmation_dialog.reject()
            self._confirmation_dialog.deleteLater()
            self._confirmation_dialog = None
        self.window.set_busy(True, ready=False)
        self.window.state_label.setText("Stopping IRIS...")
        if not self.orb.microphone_active:
            self.orb.set_state("paused")
        if self.controller is not None:
            self.controller.stop()  # Immediate gate latch, never wait on the GUI thread.
        self._shutdown_thread = Thread(target=self._cleanup, name="iris-ui-shutdown")
        self._shutdown_thread.start()

    def _cleanup(self):
        ok = True
        try:
            if self._startup_thread is not None:
                self._startup_thread.join()  # Off the event loop; startup owns configuration/client creation.
            if self.controller is not None:
                self.controller.stop()
            try:
                if self.listener is not None:
                    self.listener.stop()
                    self.listener.join(timeout=1)
            finally:
                try:
                    if self.email_controller is not None:
                        self.email_controller.close()
                finally:
                    if self.controller is not None:
                        self.controller.close()
                    elif self.brain is not None:
                        self.brain.close()
        except Exception:
            ok = False
        self.bridge.closed.emit(ok)

    @Slot(bool)
    def shutdown_done(self, ok):
        self.orb.hide()
        self.window.hide()
        if not ok:
            self.cleanup_warning = QMessageBox(QMessageBox.Icon.Warning, "IRIS shutdown",
                "IRIS reported a cleanup error. Check this instance's owned processes before restarting.",
                QMessageBox.StandardButton.Close, self.window)
            self.cleanup_warning.finished.connect(lambda result: self.finished.emit(False))
            self.cleanup_warning.open()
        else:
            self.finished.emit(True)


def run_gui(*, config_factory, brain_factory) -> int:
    app = QApplication.instance() or QApplication([])
    ensure_fonts()
    app.setApplicationName("IRIS")
    app.setFont(QFont("Segoe UI", 10))
    app.setQuitOnLastWindowClosed(False)
    instance = GuiInstance(app)
    try:
        if not instance.acquire():
            return 0
    except Exception:
        QMessageBox.warning(None, "IRIS", "Another IRIS GUI may be starting. Try again after it finishes.")
        return 1
    session = DesktopSession(config_factory=config_factory, brain_factory=brain_factory)
    instance.show_requested.connect(session.restore_orb)
    status = [0]
    def finished(ok):
        status[0] = 0 if ok else 1
        app.quit()
    session.finished.connect(finished)
    session.start()
    # App close requests (including Windows session end) use the same owned cleanup.
    app.aboutToQuit.connect(session.shutdown)
    app.exec()
    if session._shutdown_thread is not None:
        session._shutdown_thread.join()
    instance.close()
    return status[0]
