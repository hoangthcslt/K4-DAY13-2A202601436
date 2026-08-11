from collections import Counter

import pytest

from app import metrics


@pytest.fixture(autouse=True)
def isolated_metrics_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "REQUEST_LATENCIES", [])
    monkeypatch.setattr(metrics, "REQUEST_COSTS", [])
    monkeypatch.setattr(metrics, "REQUEST_TOKENS_IN", [])
    monkeypatch.setattr(metrics, "REQUEST_TOKENS_OUT", [])
    monkeypatch.setattr(metrics, "ERRORS", Counter())
    monkeypatch.setattr(metrics, "TRAFFIC", 0)
    monkeypatch.setattr(metrics, "QUALITY_SCORES", [])


def test_percentile_basic() -> None:
    assert metrics.percentile([100, 200, 300, 400], 50) >= 100


def test_snapshot_error_rate_is_zero_safe() -> None:
    result = metrics.snapshot()

    assert result["traffic"] == 0
    assert result["successful_requests_total"] == 0
    assert result["errors_total"] == 0
    assert result["error_rate_pct"] == 0.0


def test_error_rate_uses_all_completed_requests_and_rounds_to_two_decimals() -> None:
    for _ in range(2):
        metrics.record_request(
            latency_ms=100,
            cost_usd=0.01,
            tokens_in=10,
            tokens_out=20,
            quality_score=0.8,
        )
    metrics.record_error("RuntimeError")

    result = metrics.snapshot()

    assert result["traffic"] == 3
    assert result["successful_requests_total"] == 2
    assert result["errors_total"] == 1
    assert result["error_rate_pct"] == 33.33
    assert result["error_breakdown"] == {"RuntimeError": 1}


def test_failed_requests_count_as_completed_traffic() -> None:
    metrics.record_error("TimeoutError")
    metrics.record_error("RuntimeError")

    result = metrics.snapshot()

    assert result["traffic"] == 2
    assert result["successful_requests_total"] == 0
    assert result["errors_total"] == 2
    assert result["error_rate_pct"] == 100.0
