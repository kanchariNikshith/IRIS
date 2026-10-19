"""Real Qt widgets and shared Brain/voice paths, fake Gmail/OAuth services."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from unittest.mock import Mock
from types import SimpleNamespace
from threading import Thread
from time import monotonic

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QThread
from PySide6.QtTest import QTest

from iris.brain.brain import Brain
from iris.brain.providers import GeminiProvider, OpenAIProvider
from iris.tools.registry import ToolRegistry, ToolResult
from iris.security.permissions import PermissionGate
from iris.logs.action_log import ActionLog
from iris.config import Config
from iris.ui.app import DesktopSession
from iris.ui.theme import ensure_fonts
from iris.audio.voice import VoiceController


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    ensure_fonts()
    yield app


def pump(app, predicate):
    deadline = monotonic() + 4
    while not predicate():
        app.processEvents()
        assert monotonic() < deadline
        QTest.qWait(5)
    app.processEvents()


class FakeSpeaker:
    def __init__(self):
        from threading import Event
        self.busy = Event()
        self.texts = []
    def start(self):
        pass
    def enqueue(self, text):
        self.texts.append(text)
        return True
    def close(self):
        pass


def session(app, tmp_path, provider="openai", voice=False):
    args = {"recipients":"test@example.com", "subject":"Tomorrow's meeting", "body":"I'll attend the meeting."}
    registry = ToolRegistry(PermissionGate(timeout=0.5), ActionLog(tmp_path / "actions.log"))
    client = Mock()
    if provider == "openai":
        __import__("openai")
        client.responses.create.side_effect = [
            SimpleNamespace(output=[{"type":"function_call", "call_id":"preview1", "name":"draft_email", "arguments":json.dumps(args)}],output_text=""),
            SimpleNamespace(output=[],output_text="Email sent successfully.")]
        adapter = OpenAIProvider(client,"fixture-model")
    else:
        def response(parts):
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP",content={"role":"model","parts":parts})])
        client.models.generate_content.side_effect = [response([{"function_call":{"name":"draft_email","args":args}}]),
                                                       response([{"text":"Email sent successfully."}])]
        adapter = GeminiProvider(client,"fixture-model")
    brain = Brain(client,"fixture-model",registry,provider=adapter)
    brain.run = Mock(wraps=brain.run)
    api = Mock()
    api.credentials = object()
    api.restore.return_value = True
    api.write.return_value = ToolResult("verified","Gmail confirmed message submission. Recipient delivery is not verified.")
    def factory(brain, model, emit):
        ears = Mock()
        ears.listen.return_value = "Draft an email to test@example.com saying I'll attend the meeting."
        return VoiceController(brain,model,ears=ears,speaker=FakeSpeaker(),emit=emit)
    gui = DesktopSession(config_factory=lambda: Config("fixture-ui-key","fixture-model"),
                         brain_factory=lambda c, **kw: brain, controller_factory=factory,
                         listener_factory=Mock(), gmail_factory=lambda **kw: api)
    gui.start()
    pump(app,lambda: gui._ready and gui.gmail_panel._connected)
    return gui,brain,api


def dispose(app, gui):
    gui.shutdown()
    pump(app,lambda: gui._shutdown_thread is not None and not gui._shutdown_thread.is_alive())
    assert not gui.email_controller._thread.is_alive()
    gui.gmail_panel.deleteLater()
    gui.window.deleteLater()
    gui.orb.deleteLater()
    gui.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("provider",["gemini","openai"])
@pytest.mark.parametrize("voice",[True,False])
def test_shared_brain_text_voice_preview_then_gui_exact_send(app,tmp_path,provider,voice):
    gui,brain,api = session(app,tmp_path,provider)
    try:
        if voice:
            gui.window.mic.click()
        else:
            gui.window.input.setText("Send an email to test@example.com saying I'll attend the meeting.")
            gui.window.send.click()
        pump(app,lambda: gui.email_controller.draft is not None and not gui.controller.busy.is_set())
        brain.run.assert_called_once()
        assert gui.gmail_panel.isVisible()
        assert gui.gmail_panel.body.toPlainText() == "I'll attend the meeting."
        assert "Nothing has been saved" in gui.controller.speaker.texts[-1]
        api.write.assert_not_called()
        gui.gmail_panel.body.setPlainText("I'll attend at 9 AM.")
        gui.gmail_panel.send.click()
        gui.gmail_panel.send.click()
        pump(app,lambda: gui.email_dialog is not None)
        assert gui.email_dialog.operation.snapshot.body == "I'll attend at 9 AM."
        api.write.assert_not_called()
        gui.email_dialog.approve.click()
        gui.email_dialog.approve.click()
        pump(app,lambda: api.write.called and not gui.email_controller.busy.is_set())
        api.write.assert_called_once()
        assert api.write.call_args.args[0].body == "I'll attend at 9 AM."
        log = (tmp_path / "actions.log").read_text()
        assert "9 AM" not in log and "test@example.com" not in log
        if voice:
            assert "test@example.com" in gui.window.transcript.text()
    finally:
        dispose(app,gui)


@pytest.mark.parametrize("event",["edit","expiry","cancel","kill","hide","orb_hide"])
def test_gui_confirmation_invalidated_without_send(app,tmp_path,event):
    gui,brain,api = session(app,tmp_path)
    try:
        gui.email_controller.prepare("test@example.com","Subject","Body")
        pump(app,lambda: gui.gmail_panel.isVisible())
        gui.gmail_panel.send.click()
        pump(app,lambda: gui.email_dialog is not None)
        dialog = gui.email_dialog
        if event == "edit":
            gui.gmail_panel.subject.setText("Changed subject")
        elif event == "cancel":
            dialog.deny.click()
        elif event == "kill":
            gui.controller.stop()
        elif event == "hide":
            gui.window.close()
        elif event == "orb_hide":
            gui.toggle_window()
        else:
            dialog.operation.request.deadline = monotonic() - 1
            dialog.check()
        dialog.approve.click()
        pump(app,lambda: not gui.email_controller.busy.is_set())
        api.write.assert_not_called()
    finally:
        dispose(app,gui)


def test_gui_connection_controls_thread_safety_and_no_duplicate_workers(app,tmp_path):
    gui,brain,api = session(app,tmp_path)
    try:
        api.disconnect.side_effect = lambda: setattr(api,"credentials",None)
        gui.show_gmail()
        gui.gmail_panel.disconnect_button.click()
        pump(app,lambda: not gui.gmail_panel._connected and not gui.email_controller.busy.is_set())
        api.disconnect.assert_called_once()
        def connect(stop):
            assert QThread.currentThread() != app.thread()
            api.credentials = object()
        api.connect.side_effect = connect
        gui.gmail_panel.connect_button.click()
        gui.gmail_panel.connect_button.click()
        pump(app,lambda: gui.gmail_panel._connected and not gui.email_controller.busy.is_set())
        api.connect.assert_called_once()
        assert "Connected" in gui.window.gmail_button.text()
        assert gui.gmail_panel.thread() == app.thread()
    finally:
        dispose(app,gui)


def test_manual_local_preview_works_without_brain_and_save_requires_confirmation(app,tmp_path):
    gui,brain,api = session(app,tmp_path)
    try:
        gui.show_gmail()
        gui.gmail_panel.recipients.setText("test@example.com")
        gui.gmail_panel.subject.setText("Manual subject")
        gui.gmail_panel.body.setPlainText("Manual private body")
        gui.gmail_panel.prepare.click()
        pump(app,lambda: gui.email_controller.draft is not None and not gui.email_controller.busy.is_set())
        brain.run.assert_not_called()
        api.write.assert_not_called()
        gui.gmail_panel.save.click()
        pump(app,lambda: gui.email_dialog is not None)
        api.write.assert_not_called()
        gui.email_dialog.approve.click()
        pump(app,lambda: api.write.called and not gui.email_controller.busy.is_set())
        assert api.write.call_args.args[1] == "save"
        api.write.assert_called_once()
    finally:
        dispose(app,gui)
