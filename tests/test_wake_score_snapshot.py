from hashlib import sha256
import json
import pytest
from training.score_experiment import frozen_corpus


def test_scoring_requires_identical_owner_bytes_and_preserves_labels(tmp_path):
    rows = []
    for name, label in [("one.wav", "positive"), ("two.wav", "negative")]:
        path = tmp_path / name
        path.write_bytes(name.encode())
        rows.append({"path": name, "label": label, "sha256": sha256(path.read_bytes()).hexdigest()})
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"recordings": rows}))
    positive, negative = frozen_corpus(tmp_path, snapshot)
    assert positive == [tmp_path / "one.wav"] and negative == [tmp_path / "two.wav"]
    positive[0].write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        frozen_corpus(tmp_path, snapshot)


def test_scoring_refuses_paths_outside_frozen_corpus(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"recordings": [{"path": "../outside.wav", "label": "positive", "sha256": ""}]}))
    with pytest.raises(ValueError, match="Invalid"):
        frozen_corpus(tmp_path, snapshot)
