from unittest.mock import Mock
import numpy as np
from training.candidates import LivekitCandidate, OpenWakeWordCandidate


def test_livekit_uses_complete_overlapping_window_and_clears_preroll():
    backend = Mock()
    backend.predict.return_value = {"iris": .8}
    detector = LivekitCandidate(backend, "iris")
    frame = np.ones(1280, dtype=np.float32)
    for _ in range(24):
        assert detector.predict(frame) == 0
    backend.predict.assert_not_called()
    assert detector.predict(frame) == .8
    assert backend.predict.call_args.args[0].shape == (32000,)
    detector.reset()
    assert detector.ring.size == 0
    detector.close()
    assert detector.backend is None


def test_openwakeword_gets_exact_pcm16_frames_and_resets_state():
    backend = Mock()
    backend.predict.return_value = {"iris": .7}
    detector = OpenWakeWordCandidate(backend, "iris")
    assert detector.predict(np.ones(1600, dtype=np.float32)) == .7
    received = backend.predict.call_args.args[0]
    assert received.dtype == np.int16 and len(received) == 1280
    detector.reset()
    backend.reset.assert_called_once()
    assert not detector.converter._pending.size
