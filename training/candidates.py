"""R3 candidate adapters; optional libraries are loaded only for explicit evaluation."""
from hashlib import sha256
import numpy as np
from iris.audio.capture import AudioRing, PCMFrames
from iris.audio.wake import WakeModelError, validate_bundle


class LivekitCandidate:
    def __init__(self, backend, key: str):
        self.backend, self.key = backend, key
        self.ring = AudioRing(32000)

    def predict(self, frame: np.ndarray) -> float:
        self.ring.append(frame)
        if self.ring.size < 32000:
            return 0.
        return float(self.backend.predict(self.ring.snapshot())[self.key])

    def reset(self) -> None:
        self.ring.clear()

    def close(self) -> None:
        self.reset()
        self.backend = None


class OpenWakeWordCandidate:
    def __init__(self, backend, key: str):
        self.backend, self.key = backend, key
        self.converter = PCMFrames(1280)

    def predict(self, frame: np.ndarray) -> float:
        score = 0.
        for pcm in self.converter.feed(frame):
            current = float(self.backend.predict(pcm)[self.key])
            if not np.isfinite(current) or not 0 <= current <= 1:
                raise WakeModelError()
            score = max(score, current)
        return score

    def reset(self) -> None:
        self.converter.reset()
        self.backend.reset()

    def close(self) -> None:
        self.reset()
        self.backend = None


def load_candidate(manifest, *, development=False):
    bundle = validate_bundle(manifest, allow_development=development)
    classifier, mel, embedding = bundle.assets
    try:
        if bundle.engine == "livekit":
            from livekit.wakeword import WakeWordModel
            from livekit.wakeword.resources import get_mel_model_path, get_embedding_model_path
            # LiveKit loads bundled frontends; require exact identity with this bundle.
            for installed, pinned in [(get_mel_model_path(), mel), (get_embedding_model_path(), embedding)]:
                if sha256(installed.read_bytes()).digest() != sha256(pinned.read_bytes()).digest():
                    raise WakeModelError()
            from onnxruntime import SessionOptions
            options = SessionOptions()
            options.intra_op_num_threads = options.inter_op_num_threads = 1
            return LivekitCandidate(WakeWordModel(models=[classifier], sess_options=options), classifier.stem)
        from openwakeword.model import Model
        backend = Model(wakeword_models=[str(classifier)], inference_framework="onnx",
                        melspec_model_path=str(mel), embedding_model_path=str(embedding), ncpu=1)
        return OpenWakeWordCandidate(backend, classifier.stem)
    except Exception:
        raise WakeModelError() from None
