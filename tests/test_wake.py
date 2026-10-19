from hashlib import sha256
import json
from unittest.mock import Mock
import numpy as np
import pytest

from iris.audio.wake import PHRASE, WakeModelError, WakeTrigger, validate_bundle


def bundle_fixture(tmp_path):
    assets = []
    for role in ["classifier", "melspectrogram", "embedding"]:
        payload = ("synthetic-" + role).encode()
        (tmp_path / (role + ".onnx")).write_bytes(payload)
        assets.append({"role": role, "path": role + ".onnx", "bytes": len(payload),
                       "sha256": sha256(payload).hexdigest(), "license": "test only", "source": "synthetic"})
    data = {"schema_version": 1, "phrase": PHRASE, "sample_rate": 16000, "engine": "livekit",
            "engine_revision": "a" * 40, "frame_samples": 1280, "assets": assets}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path, data


def test_bundle_preflight_requires_all_pinned_frontends_and_classifier(tmp_path):
    path, _ = bundle_fixture(tmp_path)
    bundle = validate_bundle(path)
    assert bundle.engine == "livekit" and len(bundle.assets) == 3
    (tmp_path / "classifier.onnx").write_bytes(b"changed")
    with pytest.raises(WakeModelError):
        validate_bundle(path)


def test_development_models_cannot_pass_normal_runtime_preflight(tmp_path):
    path, data = bundle_fixture(tmp_path)
    data["development_only"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(WakeModelError):
        validate_bundle(path)
    assert validate_bundle(path, allow_development=True).engine == "livekit"


@pytest.mark.parametrize("change", ["phrase", "path", "hash", "license", "missing", "role", "version"])
def test_bundle_refuses_wrong_phrase_unpinned_or_missing_assets(tmp_path, change):
    path, data = bundle_fixture(tmp_path)
    if change == "phrase":
        data["phrase"] = "hey livekit"
    elif change == "path":
        data["assets"][0]["path"] = "../classifier.onnx"
    elif change == "hash":
        data["assets"][0]["sha256"] = "0" * 64
    elif change == "license":
        data["assets"][0]["license"] = ""
    elif change == "missing":
        (tmp_path / "classifier.onnx").unlink()
    elif change == "role":
        data["assets"][0]["role"] = "embedding"
    else:
        data["engine_revision"] = "latest"
    path.write_text(json.dumps(data))
    with pytest.raises(WakeModelError) as info:
        validate_bundle(path)
    assert str(tmp_path) not in str(info.value)


def test_wake_hit_requires_explicit_reset_and_debounce_and_never_dispatches():
    detector = Mock()
    detector.predict.return_value = .95
    timer = [0.0]
    trigger = WakeTrigger(detector, threshold=.8, clock=lambda: timer[0])
    frame = np.zeros(1280, dtype=np.float32)
    assert trigger.predict(frame)
    assert not trigger.predict(frame)
    detector.predict.assert_called_once()
    trigger.reset()
    assert not trigger.predict(frame)
    timer[0] = 3
    assert trigger.predict(frame)
    trigger.close()
    trigger.close()
    assert not trigger.predict(frame)
    detector.close.assert_called_once()


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -1, 2])
def test_invalid_detector_scores_fail_closed(score):
    detector = Mock()
    detector.predict.return_value = score
    with pytest.raises(WakeModelError):
        WakeTrigger(detector, threshold=.8).predict(np.zeros(1280, dtype=np.float32))
