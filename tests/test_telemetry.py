from concurrent.futures import ThreadPoolExecutor
import pytest
from iris.telemetry import RuntimeMetrics


def test_metrics_are_bounded_content_free_and_thread_safe():
    metrics = RuntimeMetrics()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: metrics.record("provider_requests", elapsed=0.5), range(100)))
    snapshot = metrics.snapshot()
    assert snapshot == {"counts": {"provider_requests": 100},
                        "last_seconds": {"provider_requests": 0.5}}
    snapshot["counts"].clear()
    assert metrics.snapshot()["counts"]["provider_requests"] == 100
    with pytest.raises(ValueError):
        metrics.record("private command content")
