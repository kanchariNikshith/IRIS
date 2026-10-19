from unittest.mock import Mock
import numpy as np
from training.collect_wake import write_wav
from training.evaluate_wake import recall_interval, score_corpus


def test_evaluation_counts_utterances_and_never_claims_release_acceptance(tmp_path):
    positive, negative = tmp_path / "positive.wav", tmp_path / "negative.wav"
    write_wav(positive, np.full(16000, .1, dtype=np.float32))
    write_wav(negative, np.zeros(16000, dtype=np.float32))
    detector = Mock()
    detector.predict.side_effect = lambda frame: .9 if frame.max() > .05 else .1
    report = score_corpus(detector, [positive], [negative])
    assert report["positive_hits"] == 1 and report["recall"] == 1
    assert report["false_wakes"] == 0 and report["negative_hours"] == 1/3600
    assert report["positive_misses"] == 0
    assert report["median_first_hit_seconds_from_clip_start"] == .08
    assert report["recall_wilson95"][0] < 1
    assert report["release_accepted"] is False
    detector.close.assert_called_once()


def test_negative_clips_are_continuous_instead_of_restarting_detector_each_file(tmp_path):
    positive, first, second = [tmp_path / name for name in ['positive.wav', 'first.wav', 'second.wav']]
    for path in [positive, first, second]:
        write_wav(path, np.zeros(16000, dtype=np.float32))
    detector = Mock()
    detector.predict.return_value = 0.
    score_corpus(detector, [positive], [first, second])
    # One phase reset, one positive-utterance reset, one negative-phase reset.
    assert detector.reset.call_count == 3


def test_recall_interval_does_not_turn_perfect_small_sample_into_certainty():
    low, high = recall_interval(8, 8)
    assert .67 < low < .68 and high <= 1
    low, high = recall_interval(0, 8)
    assert low >= 0 and .32 < high < .33
