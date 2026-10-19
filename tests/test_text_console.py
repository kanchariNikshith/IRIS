from unittest.mock import Mock

from iris.config import Config
from iris.main import create_brain, main, prepare_console_input, text_console
from iris.security.permissions import PermissionGate


def test_console_handoff_notice_and_cancellable_wait(capsys):
    stop = Mock()
    stop.is_set.return_value = False
    stop.wait.return_value = False
    assert prepare_console_input(stop) is True
    stop.wait.assert_called_once_with(3.0)
    notice = capsys.readouterr().out
    assert "target window" in notice and "mouse" in notice and "3 seconds" in notice
    stop.wait.return_value = True
    assert prepare_console_input(stop) is False


def test_stopped_console_handoff_skips_notice_and_wait(capsys):
    stop = Mock()
    stop.is_set.return_value = True
    assert prepare_console_input(stop) is False
    stop.wait.assert_not_called()
    assert not capsys.readouterr().out


def test_text_console_wires_commands_and_cleans_listener(monkeypatch, capsys):
    gate = PermissionGate()
    brain = Mock()
    brain.registry.gate = gate
    brain.run.return_value = "Verified: time checked."
    listener = Mock()
    monkeypatch.setattr("iris.security.permissions.start_kill_switch", Mock(return_value=listener))
    commands = iter(["what time is it", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(commands))
    text_console(brain, "<ctrl>+<alt>+<esc>")
    brain.run.assert_called_once_with("what time is it")
    assert "Verified" in capsys.readouterr().out
    assert gate.kill_switch.is_set()
    listener.stop.assert_called_once()
    listener.join.assert_called_once_with(timeout=1)


def test_missing_model_starts_local_runtime(monkeypatch):
    config = Config("")
    monkeypatch.setattr("iris.main.load_config", lambda **kw: config)
    factory, console = Mock(), Mock()
    monkeypatch.setattr("iris.main.create_brain", factory)
    monkeypatch.setattr("iris.main.text_console", console)
    assert main(["--text-only"]) == 0
    factory.assert_called_once_with(config)
    console.assert_called_once()


def test_main_text_mode_mock_runtime(monkeypatch):
    config = Config("fixture-secret", "selected-model")
    brain = Mock()
    monkeypatch.setattr("iris.main.load_config", lambda **kw: config)
    monkeypatch.setattr("iris.main.create_brain", Mock(return_value=brain))
    console = Mock()
    monkeypatch.setattr("iris.main.text_console", console)
    assert main(["--text-only"]) == 0
    console.assert_called_once_with(brain, config.kill_switch_hotkey)


def test_main_defaults_to_voice_console_without_changing_brain(monkeypatch):
    config = Config("fixture-secret", "selected-model")
    brain, console = Mock(), Mock()
    monkeypatch.setattr("iris.main.load_config", lambda **kw: config)
    monkeypatch.setattr("iris.main.create_brain", Mock(return_value=brain))
    monkeypatch.setattr("iris.audio.voice.voice_console", console)
    assert main([]) == 0
    console.assert_called_once_with(brain, config)


def test_gui_flag_uses_qt_entry_without_starting_console(monkeypatch):
    run = Mock(return_value=0)
    monkeypatch.setattr("iris.ui.app.run_gui", run)
    assert main(["--gui"]) == 0
    assert run.call_args.kwargs["config_factory"] is not None
    assert run.call_args.kwargs["brain_factory"] is not None


def test_gemini_missing_model_starts_local_runtime(monkeypatch):
    config = Config("", ai_provider="gemini", gemini_api_key="gemini-fixture")
    monkeypatch.setattr("iris.main.load_config", lambda **kw: config)
    factory, console = Mock(), Mock()
    monkeypatch.setattr("iris.main.create_brain", factory)
    monkeypatch.setattr("iris.audio.voice.voice_console", console)
    assert main([]) == 0
    factory.assert_called_once_with(config)
    console.assert_called_once()


def test_gemini_factory_uses_selected_credentials_and_safety(monkeypatch):
    from google import genai
    factory = Mock()
    monkeypatch.setattr(genai, "Client", factory)
    config = Config("openai-fixture", "openai-model", ai_provider="gemini",
                    gemini_api_key="gemini-fixture", gemini_model="gemini-model")
    brain = create_brain(config)
    assert brain.model == "gemini-model"
    assert factory.call_args.kwargs["api_key"] == "gemini-fixture"
    assert factory.call_args.kwargs["vertexai"] is False
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 20000 and options.retry_options.attempts == 1
    assert brain.registry.action_log.secrets == config.secrets
    assert len(brain.registry.definitions()) == 7
    brain.close()
    factory.return_value.close.assert_called_once()


def test_default_startup_does_not_import_gemini(monkeypatch):
    import builtins
    import openai
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == "google" or name.startswith("google.genai"):
            raise AssertionError("Gemini should not be imported by OpenAI startup.")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(openai, "OpenAI", Mock())
    brain = create_brain(Config("openai-fixture", "chosen-openai"))
    brain.close()


def test_openai_factory_remains_default(monkeypatch):
    import openai
    factory = Mock()
    monkeypatch.setattr(openai, "OpenAI", factory)
    brain = create_brain(Config("openai-fixture", "chosen-openai"))
    assert brain.model == "chosen-openai"
    factory.assert_called_once_with(api_key="openai-fixture", max_retries=0, timeout=20.0)
    brain.close()
