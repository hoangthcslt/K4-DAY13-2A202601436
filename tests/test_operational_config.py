from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str) -> dict:
    return yaml.safe_load(
        (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    )


def test_slo_defines_measurable_thresholds_and_error_budgets() -> None:
    payload = _load_yaml("config/slo.yaml")

    assert payload["window"] == "28d"
    assert payload["data_source"] == "data/logs.jsonl"
    assert set(payload["slis"]) == {
        "latency_p95_ms",
        "error_rate_pct",
        "daily_cost_usd",
        "quality_score_avg",
    }
    for sli in payload["slis"].values():
        assert sli["comparison"] in {"lte", "gte"}
        assert isinstance(sli["objective"], (int, float))
        assert 0 <= sli["target"] <= 100
        assert "formula" in sli
        assert "error_budget_percent" in sli


def test_alert_rules_are_actionable_and_link_to_existing_runbook_sections() -> None:
    payload = _load_yaml("config/alert_rules.yaml")
    alerts = payload["alerts"]
    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")

    assert len(alerts) == 3
    assert {alert["sli"] for alert in alerts} == {
        "error_rate_pct",
        "latency_p95_ms",
        "quality_score_avg",
    }
    for alert in alerts:
        assert alert["severity"] in {"critical", "warning"}
        assert alert["type"] == "symptom-based"
        assert alert["condition"]
        assert alert["window"]
        assert alert["for"]
        assert alert["owner"]
        anchor = alert["runbook"].split("#", maxsplit=1)[1]
        heading = "## " + " ".join(word.title() for word in anchor.split("-"))
        assert heading in runbook


def test_slo_and_dashboard_thresholds_stay_aligned() -> None:
    slo = _load_yaml("config/slo.yaml")["slis"]
    panels = {
        panel["id"]: panel
        for panel in _load_yaml("config/dashboard.yaml")["dashboard"]["panels"]
    }

    assert panels["latency"]["threshold"]["value"] == slo["latency_p95_ms"]["objective"]
    assert panels["errors"]["threshold"]["value"] == slo["error_rate_pct"]["objective"]
    assert panels["cost"]["threshold"]["value"] == slo["daily_cost_usd"]["objective"]
    assert panels["quality"]["threshold"]["value"] == slo["quality_score_avg"]["objective"]
