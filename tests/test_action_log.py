import json

import pytest

from iris.logs.action_log import ActionLog


def test_append_redaction_and_email_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")
    path = tmp_path / "data" / "actions.log"
    log = ActionLog(path, ("fixture-secret",))
    log.write("draft_email", {"body": "a" * 120, "nested": {"password": "private"},
              "api_key": "fixture-secret", "text": "environment-secret"},
              "unverified", "fixture-secret")
    first = path.read_bytes()
    log.write("get_time", {}, "verified", "Checked.")
    assert path.read_bytes().startswith(first)
    text = path.read_text()
    assert "fixture-secret" not in text and "environment-secret" not in text
    assert "private" not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert len(records) == 2
    assert records[0]["arguments"] == {"field_count": 4}
    assert records[0]["time"].endswith("+00:00")


def test_reject_bad_status_without_writing(tmp_path):
    path = tmp_path / "actions.log"
    with pytest.raises(ValueError):
        ActionLog(path).write("tool", {}, "done", "Checked.")
    assert not path.exists()


@pytest.mark.parametrize("length", [80, 600])
def test_email_body_echo_in_result_is_shortened(tmp_path, length):
    path = tmp_path / "actions.log"
    body = "a" * length + "private tail"
    ActionLog(path).write("draft_email", {"body": body}, "unverified", "Draft: " + body)
    assert "private tail" not in path.read_text()
