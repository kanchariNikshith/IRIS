"""Headless Qt tests; no live devices, model services or desktop tools."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer, QThread
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from iris.audio.voice import VoiceController
from iris.brain.brain import Brain
from iris.brain.providers import GeminiProvider, OpenAIProvider
from iris.config import Config
from iris.logs.action_log import ActionLog
from iris.security.permissions import Confirmation, Permission, PermissionGate
from iris.tools.registry import Tool, ToolRegistry, ToolResult
from iris.ui.app import DesktopSession, GuiInstance
from iris.ui.orb import FloatingOrb, OrbFace, constrain_position
from iris.ui.theme import STATES, ensure_fonts
from iris.ui.window import MainWindow


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    ensure_fonts()
    app.setQuitOnLastWindowClosed(False)
    yield app


def test_show_window_restores_hidden_orb_on_screen(app):
    session = DesktopSession(config_factory=Mock(), brain_factory=Mock())
    session.orb.hide()
    session.orb.move(-100000, -100000)
    session.show_window()
    assert session.orb.isVisible()
    assert any(screen.availableGeometry().contains(session.orb.geometry())
               for screen in app.screens())
    assert session.window.isVisible()
    session.orb.hide()
    session.window.hide()


def pump(app, predicate, timeout=4):
    deadline = monotonic() + timeout
    while not predicate():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("Qt/worker condition did not complete")
        QTest.qWait(5)
    app.processEvents()


class SilentSpeaker:
    def __init__(self):
        self.busy = Event()
        self.texts = []
        self.closed = False
    def start(self):
        pass
    def enqueue(self, text):
        self.texts.append(text)
        self.on_state("speaking")
        return True
    def close(self):
        self.closed = True
        self.busy.clear()


class MockEars:
    def __init__(self):
        self.closed = False
        self.calls = 0
    def listen(self, stop, state):
        self.calls += 1
        state("listening")
        state("processing")
        return "Open Gmail."
    def close(self):
        self.closed = True


def controller_factory(brain, model, *, emit):
    return VoiceController(brain, model, ears=MockEars(), speaker=SilentSpeaker(), emit=emit)


def fake_brain(tmp_path):
    brain = Mock()
    brain.registry = ToolRegistry(PermissionGate(), ActionLog(tmp_path / "actions.log"))
    brain.secrets = ("fixture-ui-secret",)
    brain.run.return_value = "Hello from IRIS."
    return brain


def make_session(app, brain, **kwargs):
    gmail = Mock()
    gmail.restore.return_value = False
    gmail.credentials = None
    session = DesktopSession(
        config_factory=kwargs.pop("config_factory", lambda: Config("fixture-ui-secret", "fixture-model")),
        brain_factory=kwargs.pop("brain_factory", lambda config, **kw: brain),
        controller_factory=controller_factory, listener_factory=Mock(),
        gmail_factory=kwargs.pop("gmail_factory", lambda **kw: gmail), **kwargs)
    session.start()
    pump(app, lambda: session._ready or not session.window.error.isHidden())
    return session


def dispose(app, session):
    if not session._stopping.is_set():
        session.shutdown()
    pump(app, lambda: session._shutdown_thread is not None and not session._shutdown_thread.is_alive())
    if hasattr(session, "cleanup_warning"):
        session.cleanup_warning.done(0)
    session.window.deleteLater()
    session.orb.deleteLater()
    session.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("state", list(STATES))
def test_orb_states_microphone_dot_and_reduced_motion(app, state):
    orb = FloatingOrb()
    try:
        orb.show()
        orb.set_reduced_motion(True)
        orb.set_state(state)
        assert orb.state == state
        assert orb.microphone_active == (state == "listening")
        assert orb._accent.name().upper() == STATES[state][0]
        assert orb._motion.state().name == "Stopped"
        assert orb.size().width() == 120
        assert orb.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert orb.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert not orb.grab().isNull()
    finally:
        orb.deleteLater()
        app.processEvents()


def test_orb_breathes_when_idle_and_stops_when_hidden(app):
    orb = FloatingOrb()
    orb.show()
    orb.set_state("listening")
    assert orb._motion.state().name == "Running"
    orb.set_state("idle")
    assert orb._motion.state().name == "Running"
    orb.set_state("processing")
    orb.hide()
    assert orb._motion.state().name == "Stopped"
    orb.deleteLater()


def test_revolving_orb_runs_only_when_visible_and_motion_allowed(app):
    orb = FloatingOrb()
    orb.show()
    assert orb._orbit_timer.isActive()
    start = orb._orbit_angle
    QTest.qWait(100)
    assert orb._orbit_angle > start
    before = orb.grab().toImage()
    orb._orbit_angle = 90
    orb.update()
    assert before != orb.grab().toImage()
    orb.set_state("paused")
    assert not orb._orbit_timer.isActive()
    orb.set_state("processing")
    assert orb._orbit_timer.isActive()
    orb.set_reduced_motion(True)
    assert not orb._orbit_timer.isActive()
    orb.set_reduced_motion(False)
    orb.hide()
    assert not orb._orbit_timer.isActive()
    orb.deleteLater()


def test_orb_click_and_drag_are_distinct_and_position_is_kept(app):
    orb = FloatingOrb()
    orb.show()
    spy = QSignalSpy(orb.clicked)
    QTest.mouseClick(orb, Qt.MouseButton.LeftButton, pos=QPoint(60, 56))
    assert spy.count() == 1
    start = QPoint(150, 180)
    orb.move(start)
    local = QPointF(60, 56)
    global_start = QPointF(orb.mapToGlobal(QPoint(60, 56)))
    def event(kind, global_pos, button, buttons):
        return QMouseEvent(kind, local, global_pos, button, buttons, Qt.KeyboardModifier.NoModifier)
    orb.mousePressEvent(event(QEvent.Type.MouseButtonPress, global_start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    moved = global_start + QPointF(50, 40)
    orb.mouseMoveEvent(event(QEvent.Type.MouseMove, moved, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
    orb.mouseReleaseEvent(event(QEvent.Type.MouseButtonRelease, moved, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
    assert orb.pos() == start + QPoint(50, 40)
    assert spy.count() == 1
    pos = orb.pos()
    orb.set_state("speaking")
    assert orb.pos() == pos
    orb.deleteLater()


@pytest.mark.parametrize("point,areas,expected", [
    (QPoint(-1900, 20), [QRect(-1920, 0, 1920, 1080), QRect(0, 0, 1920, 1080)], QPoint(-1900, 20)),
    (QPoint(-1900, 20), [QRect(0, 0, 1920, 1080)], QPoint(0, 20)),
    (QPoint(1900, 1000), [QRect(0, 0, 1920, 1040)], QPoint(1800, 920)),
    (QPoint(10, 10), [], QPoint(10, 10)),
])
def test_monitor_geometry_clamps_using_logical_coordinates(point, areas, expected):
    assert constrain_position(point, 120, areas) == expected


def test_window_rendering_plain_text_status_and_close_hides(app):
    window = MainWindow()
    window.show()
    window.secrets = ("fixture-ui-secret",)
    card = window.append_message("IRIS", "<img src='remote'> fixture-ui-secret", status="unverified")
    assert card.body.textFormat() == Qt.TextFormat.PlainText
    assert "<img" in card.body.text() and "[REDACTED]" in card.body.text()
    assert card.status.text() == "Could not confirm"
    assert window.size().width() == 940 and window.minimumWidth() == 760
    window.close()
    assert not window.isVisible()
    window.deleteLater()


def test_long_conversation_follows_bottom_but_preserves_reading_position(app):
    window = MainWindow()
    window.show()
    try:
        for index in range(40):
            window.append_message("IRIS", f"Message {index}: " + "Readable conversation text. " * 6)
        app.processEvents()
        app.processEvents()
        bar = window.scroll.verticalScrollBar()
        pump(app, lambda: bar.maximum() > 0)
        assert bar.value() == bar.maximum()
        bar.setValue(0)
        window.append_message("IRIS", "New response while the user reads earlier messages.")
        app.processEvents()
        assert bar.value() == 0
    finally:
        window.deleteLater()


def test_text_input_and_mic_signals_only_submit_once(app):
    window = MainWindow()
    window.show()
    text, mic = QSignalSpy(window.text_submitted), QSignalSpy(window.voice_requested)
    window.input.setText("Hello")
    QTest.keyClick(window.input, Qt.Key.Key_Return)
    assert text.count() == 1 and text.at(0) == ["Hello"]
    QTest.mouseClick(window.mic, Qt.MouseButton.LeftButton)
    assert mic.count() == 1
    window.input.clear()
    window.submit()
    assert text.count() == 1
    window.deleteLater()


def test_session_text_double_click_no_duplicate_brain_and_orb_listens(app, tmp_path):
    brain = fake_brain(tmp_path)
    session = make_session(app, brain)
    try:
        assert not session.window.isVisible()
        session.show_window()
        session.window.input.setText("Hello")
        QTest.mouseClick(session.window.send, Qt.MouseButton.LeftButton)
        QTest.mouseClick(session.window.send, Qt.MouseButton.LeftButton)
        pump(app, lambda: brain.run.called and not session.controller.busy.is_set())
        brain.run.assert_called_once_with("Hello")
        assert len([c for c in session.window.cards if c.role.text() == "You"]) == 1
        session.window.close()
        assert session.orb.isVisible()
        session.orb.clicked.emit()
        pump(app, lambda: session.controller.ears.calls == 1)
        assert not session.window.isVisible()
    finally:
        dispose(app, session)


def test_mic_and_existing_hotkey_share_controller_transcript_and_busy_guard(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    try:
        session.window.voice_requested.emit()
        pump(app, lambda: session.controller.ears.calls == 1 and not session.controller.busy.is_set())
        assert session.window.transcript.text() == "Recognized speech: Open Gmail."
        assert any(c.role.text() == "You (speech)" for c in session.window.cards)
        session.controller.speaker.busy.set()
        session.window.voice_requested.emit()
        assert session.controller.ears.calls == 1
        session.controller.speaker.busy.clear()
        callbacks = session._listener_factory.call_args.args[0]
        callbacks["<ctrl>+<alt>+<space>"]()
        pump(app, lambda: session.controller.ears.calls == 2 and not session.controller.busy.is_set())
        session._listener_factory.assert_called_once()  # No competing listener.
    finally:
        dispose(app, session)


def test_worker_signals_update_widgets_on_qt_thread_only(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    threads = []
    original = session.window.set_state
    def record(state):
        threads.append(QThread.currentThread())
        original(state)
    session.window.set_state = record
    try:
        worker = Thread(target=lambda: session.bridge.event.emit("State", "listening"))
        worker.start()
        worker.join()
        assert not threads
        pump(app, lambda: bool(threads))
        assert threads == [app.thread()]
        assert session.orb.microphone_active
        session.bridge.event.emit("State", "processing")
        pump(app, lambda: session.orb.state == "processing")
        assert not session.orb.microphone_active
    finally:
        dispose(app, session)


def test_errors_and_tool_statuses_are_visible_and_keys_redacted(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    try:
        session.bridge.event.emit("Error", "Device error fixture-ui-secret")
        pump(app, lambda: "Device error" in session.orb.toolTip())
        assert "fixture-ui-secret" not in session.orb.toolTip()
        assert not session.window.isVisible()
        assert "fixture-ui-secret" not in session.window.error.text()
        session.bridge.action.emit("open_url", "failed", "Failed safely")
        pump(app, lambda: any(c.status is not None for c in session.window.cards))
        assert session.window.cards[-1].status.text() == "Failed"
        assert session.orb.state == "error"
    finally:
        dispose(app, session)


def provider_brain(tmp_path, provider, permission=Permission.AUTO, timeout=30):
    registry = ToolRegistry(PermissionGate(timeout), ActionLog(tmp_path / "actions.log"))
    handler = Mock(return_value=ToolResult("unverified", "Browser dispatched; page loading unconfirmed."))
    name = "open_url" if permission == Permission.AUTO else "confirm_test"
    registry.register(Tool(name, {"type": "object", "properties": {"url": {"type": "string"}},
                                  "required": ["url"]}, permission, handler))
    client = Mock()
    if provider == "openai":
        # Real create_brain imports/constructs the SDK before starting workers.
        __import__("openai")
        client.responses.create.side_effect = [
            SimpleNamespace(output=[{"type": "function_call", "call_id": "call-1", "name": name,
                                     "arguments": '{"url":"https://mail.google.com"}'}], output_text=""),
            SimpleNamespace(output=[], output_text="Done, the page loaded.")]
        adapter = OpenAIProvider(client, "fixture-model")
    else:
        def response(parts):
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP", content={"role": "model", "parts": parts})])
        client.models.generate_content.side_effect = [
            response([{"function_call": {"name": name, "args": {"url": "https://mail.google.com"}}}]),
            response([{"text": "Done, the page loaded."}])]
        adapter = GeminiProvider(client, "fixture-model")
    brain = Brain(client, "fixture-model", registry, provider=adapter)
    brain.run = Mock(wraps=brain.run)
    return brain, handler


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_gui_reuses_real_brain_provider_registry_once_and_reports_unverified(app, tmp_path, provider):
    brain, handler = provider_brain(tmp_path, provider)
    session = make_session(app, brain)
    try:
        session.window.input.setText("Open Gmail")
        session.window.send.click()
        session.window.send.click()
        pump(app, lambda: handler.called and not session.controller.busy.is_set())
        brain.run.assert_called_once_with("Open Gmail")
        handler.assert_called_once_with(url="https://mail.google.com")
        action = next(c for c in session.window.cards if c.status is not None)
        assert action.status.text() == "Could not confirm"
        assert "Done" not in session.controller.speaker.texts[-1]
        assert len(brain.registry.action_log.path.read_text().splitlines()) == 1
    finally:
        dispose(app, session)


@pytest.mark.parametrize("approved", [True, False])
def test_confirmation_is_bound_to_real_gate_request_and_turn(app, tmp_path, approved):
    brain, handler = provider_brain(tmp_path, "openai", Permission.CONFIRM)
    session = make_session(app, brain)
    try:
        session.submit("Open Gmail")
        pump(app, lambda: session.window._confirmation is not None)
        request = session.window._confirmation
        assert not session.window.isVisible()
        assert session._confirmation_dialog.isVisible()
        session.resolve(request.id, "wrong-turn", True)
        assert not request.event.is_set()
        button = session._confirmation_dialog.button(
            QMessageBox.StandardButton.Yes if approved else QMessageBox.StandardButton.No)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        session.window.answer_confirmation(True)  # A second click has no request to consume.
        pump(app, lambda: not session.controller.busy.is_set())
        assert handler.call_count == (1 if approved else 0)
        assert brain.registry.gate.resolve(request.id, turn_id=request.turn_id, approved=True) is False
    finally:
        dispose(app, session)


def test_confirmation_expiry_and_hide_never_approve(app, tmp_path):
    brain, handler = provider_brain(tmp_path, "openai", Permission.CONFIRM, timeout=0.2)
    session = make_session(app, brain)
    try:
        session.submit("Open Gmail")
        pump(app, lambda: session.window._confirmation is not None)
        pump(app, lambda: not session.controller.busy.is_set())
        session.window.check_confirmation()
        assert session.window._confirmation is None
        handler.assert_not_called()
        request = Confirmation("fake-id", "fake-tool", "fake-turn", monotonic() + 30)
        answers = QSignalSpy(session.window.confirmation_answered)
        session.window.show_confirmation(request)
        session.window.close()
        assert answers.at(0) == ["fake-id", "fake-turn", False]
    finally:
        dispose(app, session)


def test_kill_cancels_pending_confirmation_and_starts_cleanup_once(app, tmp_path):
    brain, handler = provider_brain(tmp_path, "openai", Permission.CONFIRM)
    session = make_session(app, brain)
    try:
        session.submit("Open Gmail")
        pump(app, lambda: session.window._confirmation is not None)
        callbacks = session._listener_factory.call_args.args[0]
        callbacks["<ctrl>+<alt>+<esc>"]()
        pump(app, lambda: session._shutdown_thread is not None and not session._shutdown_thread.is_alive())
        first = session._shutdown_thread
        session.shutdown()
        assert session._shutdown_thread is first
        handler.assert_not_called()
        assert session.controller.closed.is_set()
        assert session.controller.speaker.closed and session.controller.ears.closed
        session.listener.stop.assert_called_once()
    finally:
        dispose(app, session)


def test_shutdown_remains_responsive_while_worker_cleanup_waits(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    release, entered = Event(), Event()
    original = session.controller.close
    def close():
        entered.set()
        release.wait(3)
        original()
    session.controller.close = close
    try:
        session.shutdown()
        assert entered.wait(1)
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        pump(app, lambda: bool(ticks))
        assert session._shutdown_thread.is_alive()
    finally:
        release.set()
        dispose(app, session)


def test_startup_errors_are_safe_and_no_actions_can_run(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path), brain_factory=Mock(side_effect=RuntimeError("fixture-ui-secret")))
    try:
        assert not session.window.send.isEnabled()
        assert not session.window.error.isHidden()
        assert "couldn't start" in session.orb.toolTip()
        assert not session.window.isVisible()
        assert "fixture-ui-secret" not in session.window.error.text()
        assert session.controller is None
    finally:
        dispose(app, session)


def test_start_called_twice_creates_only_one_listener_and_controller(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    try:
        first = session._startup_thread
        session.start()
        assert session._startup_thread is first
        session._listener_factory.assert_called_once()
    finally:
        dispose(app, session)


def test_pause_menu_uses_voice_controls_and_reduced_motion(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    try:
        session.orb.toggle_pause.emit()
        pump(app, lambda: session.controller.paused.is_set() and not session.controller.busy.is_set())
        assert not session.window.mic.isEnabled()
        session.orb.toggle_pause.emit()
        pump(app, lambda: not session.controller.paused.is_set() and not session.controller.busy.is_set())
        session.orb.motion_changed.emit(True)
        assert session.orb.reduced_motion and session.window.logo.reduced_motion
        session.brain.run.assert_not_called()
    finally:
        dispose(app, session)


def test_second_gui_instance_only_sends_show_request(app):
    first, second = GuiInstance(), GuiInstance()
    name = "iris-test-" + uuid4().hex
    shown = QSignalSpy(first.show_requested)
    try:
        assert first.acquire(name) is True
        assert second.acquire(name) is False
        pump(app, lambda: shown.count() == 1)
        assert not second.server.isListening()
    finally:
        first.close()
        second.close()


def test_cleanup_failure_has_visible_warning_without_raw_exception(app, tmp_path):
    session = make_session(app, fake_brain(tmp_path))
    original = session.controller.close
    def fail():
        original()
        raise RuntimeError("fixture-ui-secret")
    session.controller.close = fail
    try:
        session.shutdown()
        pump(app, lambda: hasattr(session, "cleanup_warning"))
        assert session.cleanup_warning.isVisible()
        assert "fixture-ui-secret" not in session.cleanup_warning.text()
    finally:
        dispose(app, session)
