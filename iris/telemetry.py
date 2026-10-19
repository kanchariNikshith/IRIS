"""Bounded in-memory counters: never retain commands, audio or credentials."""
from collections import Counter
from threading import Lock


class RuntimeMetrics:
    EVENTS = frozenset({"local_turns", "provider_turns", "provider_requests",
                        "workers_started", "workers_reaped", "worker_failures"})

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[str] = Counter()
        self._elapsed: dict[str, float] = {}

    def record(self, event: str, *, elapsed: float | None = None) -> None:
        if event not in self.EVENTS:
            raise ValueError("Unknown telemetry event.")
        with self._lock:
            self._counts[event] += 1
            if elapsed is not None:
                self._elapsed[event] = max(0.0, float(elapsed))

    def snapshot(self) -> dict[str, dict[str, int | float]]:
        with self._lock:
            return {"counts": dict(self._counts), "last_seconds": dict(self._elapsed)}


runtime_metrics = RuntimeMetrics()
