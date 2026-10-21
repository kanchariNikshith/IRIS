from unittest.mock import Mock
import numpy as np
from training.collect_wake import write_wav
from training.evaluate_wake import recall_interval, score_corpus, wav_frames
from training.candidates import OpenWakeWordCandidate


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


def test_positive_terminal_partial_frame_is_scored_and_negative_duration_is_exact(tmp_path):
    positive, negative = tmp_path / "positive.wav", tmp_path / "negative.wav"
    audio = np.zeros(32001, dtype=np.float32)
    audio[-1] = .8
    write_wav(positive, audio)
    write_wav(negative, np.zeros(32001, dtype=np.float32))
    backend = Mock()
    backend.predict.side_effect = lambda pcm: {"iris": .9 if pcm.max() > 1000 else 0.}
    report = score_corpus(OpenWakeWordCandidate(backend, "iris"), [positive], [negative])
    assert report["positive_hits"] == 1
    assert report["negative_hours"] == 32001 / 16000 / 3600
    positives = list(wav_frames(positive, positive=True))
    negatives = list(wav_frames(negative, positive=False))
    assert len(positives[-1][0]) == 1280 and positives[-1][1] == 1
    assert len(negatives[-1][0]) == 1 and negatives[-1][1] == 1


def test_processing_metrics_exclude_disarmed_positive_frames(tmp_path):
    positive, negative = tmp_path / "positive.wav", tmp_path / "negative.wav"
    write_wav(positive, np.ones(32000, dtype=np.float32))
    write_wav(negative, np.zeros(32000, dtype=np.float32))
    detector = Mock()
    detector.predict.side_effect = lambda frame: .9 if frame.max() > .5 else 0.
    report = score_corpus(detector, [positive], [negative])
    assert report["prediction_frames"] == 26  # One positive hit, 25 negative frames.
    assert report["skipped_after_positive_hit_frames"] == 24
