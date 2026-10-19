import json
from unittest.mock import Mock

import pytest

from iris.config import ConfigurationError, load_config
from iris.main import main


def test_dotenv_and_environment_precedence(tmp_path):
    env = tmp_path / ".env"
    env.write_text('OPENAI_API_KEY="fixture-secret"\nOPENAI_MODEL=from-file\n', encoding="utf-8")
    config = load_config(env, {"OPENAI_MODEL": "override"})
    assert config.openai_api_key == "fixture-secret"
    assert config.openai_model == "override"
    assert "fixture-secret" not in repr(config)
    assert "fixture-secret" not in json.dumps(config.masked())
    assert "fixture-secret" not in repr(config)


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key_is_safe(tmp_path, key):
    values = {} if key is None else {"OPENAI_API_KEY": key}
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        load_config(tmp_path / "missing", values)


def test_mask_key_repeated_in_other_settings(tmp_path):
    config = load_config(tmp_path / "missing", {
        "OPENAI_API_KEY": "fixture-secret", "OPENAI_MODEL": "fixture-secret"})
    assert "fixture-secret" not in json.dumps(config.masked())


def test_check_command(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-fixture-secret")
    monkeypatch.setenv("OPENAI_MODEL", "offline-test-model")
    assert main(["--check"]) == 0
    output = capsys.readouterr().out
    assert "offline-fixture-secret" not in output
    assert json.loads(output)["OPENAI_API_KEY"] == "[REDACTED]"


def test_main_missing_key(monkeypatch, capsys):
    def missing():
        raise ConfigurationError("OPENAI_API_KEY is required.")
    monkeypatch.setattr("iris.main.load_config", missing)
    assert main(["--check"]) == 1
    assert "required" in capsys.readouterr().out


def test_gemini_only_configuration(tmp_path):
    config = load_config(tmp_path / "missing", {"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "gemini-fixture",
                                               "GEMINI_MODEL": "chosen-gemini"})
    assert config.ai_provider == "gemini" and config.openai_api_key == ""
    assert config.model == "chosen-gemini"
    assert "gemini-fixture" not in repr(config)


def test_legacy_configuration_defaults_to_openai(tmp_path):
    config = load_config(tmp_path / "missing", {"OPENAI_API_KEY": "openai-fixture", "OPENAI_MODEL": "chosen-openai",
                                               "GEMINI_API_KEY": "gemini-fixture"})
    assert config.ai_provider == "openai" and config.model == "chosen-openai"


@pytest.mark.parametrize("values,message", [
    ({"AI_PROVIDER": "unknown-fixture-secret"}, "AI_PROVIDER must"),
    ({"AI_PROVIDER": "gemini", "OPENAI_API_KEY": "openai-fixture"}, "GEMINI_API_KEY is required"),
    ({"GEMINI_API_KEY": "gemini-fixture"}, "OPENAI_API_KEY is required"),
])
def test_invalid_provider_and_selected_key(tmp_path, values, message):
    with pytest.raises(ConfigurationError, match=message) as info:
        load_config(tmp_path / "missing", values)
    assert "fixture" not in str(info.value)


def test_masks_both_keys_across_settings(tmp_path):
    config = load_config(tmp_path / "missing", {"AI_PROVIDER": "gemini", "OPENAI_API_KEY": "openai-fixture",
        "GEMINI_API_KEY": "gemini-fixture", "OPENAI_MODEL": "gemini-fixture", "GEMINI_MODEL": "openai-fixture"})
    text = json.dumps(config.masked()) + repr(config)
    assert "openai-fixture" not in text and "gemini-fixture" not in text


def test_gemini_env_redacted_in_log(tmp_path, monkeypatch):
    from iris.logs.action_log import ActionLog
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-fixture")
    path = tmp_path / "actions.log"
    ActionLog(path).write("tool", {"text": "gemini-fixture"}, "failed", "gemini-fixture")
    assert "gemini-fixture" not in path.read_text()


def test_gemini_check_masks_both_keys_without_sdk(monkeypatch, capsys):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-fixture")
    monkeypatch.setenv("GEMINI_MODEL", "chosen-gemini")
    factory = Mock()
    monkeypatch.setattr("iris.main.create_brain", factory)
    assert main(["--check"]) == 0
    output = capsys.readouterr().out
    assert "gemini-fixture" not in output and "openai-fixture" not in output
    assert json.loads(output)["AI_PROVIDER"] == "gemini"
    factory.assert_not_called()
