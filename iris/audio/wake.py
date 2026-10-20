"""R3 contracts and local asset preflight; no microphone or model downloads."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from time import monotonic
from typing import Callable, Protocol

import numpy as np

PHRASE = "IRIS, let's start"


class WakeModelError(ValueError):
    def __init__(self) -> None:
        super().__init__("The local IRIS wake model bundle is missing or invalid. Prepare its pinned manifest and assets first.")


class WakeDetector(Protocol):
    """One engine selected after evaluation; float32 16 kHz mono in, score out."""
    def predict(self, frame: np.ndarray) -> float: ...
    def reset(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class WakeBundle:
    engine: str
    revision: str
    frame_samples: int
    assets: tuple[Path, ...]


def validate_bundle(manifest: Path | str, *, allow_development: bool = False) -> WakeBundle:
    """Verify every frontend/classifier file locally before any engine is loaded.

    This checks pinned bytes/provenance, not acoustic compatibility, license
    approval, model quality or installation of a vendor runtime.
    """
    try:
        path = Path(manifest).resolve(strict=True)
        if path.stat().st_size > 65536:
            raise WakeModelError()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise WakeModelError()
        if data.get("development_only", False) and not allow_development:
            raise WakeModelError()
        if (data["schema_version"] != 1 or data["phrase"] != PHRASE
                or data["sample_rate"] != 16000 or data["engine"] not in {"livekit", "openwakeword"}
                or not re.fullmatch(r"[0-9a-f]{40}", data["engine_revision"])
                or type(data["frame_samples"]) is not int or not 1 <= data["frame_samples"] <= 16000
                or not isinstance(data["assets"], list) or len(data["assets"]) != 3):
            raise WakeModelError()
        roles, files, by_role = set(), [], {}
        for asset in data["assets"]:
            if (asset["role"] not in {"classifier", "melspectrogram", "embedding"}
                    or asset["role"] in roles or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
                    or not isinstance(asset["license"], str) or not asset["license"].strip()
                    or not isinstance(asset["source"], str) or not asset["source"].strip()
                    or type(asset["bytes"]) is not int or not 0 < asset["bytes"] <= 67108864):
                raise WakeModelError()
            relative = Path(asset["path"])
            if relative.is_absolute():
                raise WakeModelError()
            file = (path.parent / relative).resolve(strict=True)
            if (not file.is_relative_to(path.parent) or not file.is_file()
                    or file.suffix.lower() != ".onnx" or file in files
                    or file.stat().st_size != asset["bytes"]):
                raise WakeModelError()
            digest = sha256()
            with file.open("rb") as stream:
                while chunk := stream.read(1048576):
                    digest.update(chunk)
            if digest.hexdigest() != asset["sha256"]:
                raise WakeModelError()
            roles.add(asset["role"])
            files.append(file)
            by_role[asset["role"]] = file
        ordered = tuple(by_role[role] for role in ("classifier", "melspectrogram", "embedding"))
        return WakeBundle(data["engine"], data["engine_revision"], data["frame_samples"], ordered)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        raise WakeModelError() from None


class WakeTrigger:
    """One hit arms a command session, never a registered action or approval."""
    def __init__(self, detector: WakeDetector, *, threshold: float,
                 debounce_seconds: float = 2.0, clock: Callable[[], float] = monotonic) -> None:
        if not 0 < threshold <= 1 or not 0 <= debounce_seconds <= 30:
            raise ValueError("Invalid wake threshold/debounce.")
        self.detector, self.threshold = detector, threshold
        self.debounce_seconds, self.clock = debounce_seconds, clock
        self._last_hit = float("-inf")
        self._armed = True
        self._closed = False

    def predict(self, frame: np.ndarray) -> bool:
        if self._closed or not self._armed:
            return False
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.float32
                or frame.ndim != 1 or not 0 < frame.size <= 32000
                or not np.isfinite(frame).all()):
            raise WakeModelError()
        try:
            score = float(self.detector.predict(frame))
        except Exception:
            raise WakeModelError() from None
        if not np.isfinite(score) or not 0 <= score <= 1:
            raise WakeModelError()
        now = self.clock()
        if score >= self.threshold and now - self._last_hit >= self.debounce_seconds:
            self._armed = False
            self._last_hit = now
            return True
        return False

    def reset(self) -> None:
        if not self._closed:
            try:
                self.detector.reset()
            except Exception:
                self._armed = False
                raise WakeModelError() from None
            self._armed = True

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._armed = False
            try:
                self.detector.close()
            except Exception:
                raise WakeModelError() from None


def wake_command(text: str) -> str:
    """Only forward the suffix of an explicit leading requested wake phrase.

    Pre-roll can contain unrelated standby speech. If ASR omits/misrecognizes
    the prefix, fail empty rather than dispatching that speech as a command.
    This is a conservative transcript boundary, not speaker authentication.
    """
    match = re.match(r"^\s*iris\b[\s,.:;!?-]+let['\u2019]s\s+start\b", text, re.IGNORECASE)
    return text[match.end():].lstrip(" \t\r\n,.:;!?-\u2014") if match else ""


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check local wake bundle bytes; does not start listening.")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        bundle = validate_bundle(args.manifest)
    except WakeModelError as error:
        print(str(error))
        return 1
    print(f"Verified {len(bundle.assets)} pinned assets for {bundle.engine}; engine compatibility and wake evaluation still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
