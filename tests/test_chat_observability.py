from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import logging_config
from app import main as main_module
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={
                "user_id": "student-01",
                "session_id": "session-01",
                "feature": "qa",
                "message": "Explain observability",
            },
        )

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert "trace_id" in response.json()
    assert response_event["trace_id"] == response.json()["trace_id"]


def test_failed_chat_log_keeps_langfuse_trace_id(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    error = RuntimeError("synthetic dependency failure")
    error.observability_trace_id = "trace-failed-request"  # type: ignore[attr-defined]

    def fail_with_trace(**kwargs):
        raise error

    monkeypatch.setattr(main_module.agent, "run", fail_with_trace)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={
                "user_id": "student-01",
                "session_id": "session-failed",
                "feature": "qa",
                "message": "Trigger a synthetic failure",
            },
        )

    assert response.status_code == 500
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    failed_event = next(event for event in events if event["event"] == "request_failed")
    assert failed_event["trace_id"] == "trace-failed-request"
