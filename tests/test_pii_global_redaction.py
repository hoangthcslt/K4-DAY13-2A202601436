"""CP1 - Security & Compliance: che PII toàn cục trên mọi field của log."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import logging_config
from app.logging_config import configure_logging, get_logger
from app.pii import SAFE_KEYS, scrub_text, scrub_value


@pytest.fixture()
def log_file(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", path)
    configure_logging()
    return path


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- scrub_value: đệ quy và giữ field cấu trúc ---------------------------------


def test_scrub_value_walks_nested_dict_and_list() -> None:
    out = scrub_value(
        {
            "user": {"email": "victim@vinuni.edu.vn", "phone": "0912345678"},
            "cards": ["4111 1111 1111 1111"],
        }
    )

    assert out["user"]["email"] == "[REDACTED_EMAIL]"
    assert out["user"]["phone"] == "[REDACTED_PHONE_VN]"
    assert out["cards"] == ["[REDACTED_CREDIT_CARD]"]


def test_scrub_value_preserves_non_string_types() -> None:
    out = scrub_value({"latency_ms": 1200, "cost_usd": 0.0016, "ok": True, "none": None})

    assert out == {"latency_ms": 1200, "cost_usd": 0.0016, "ok": True, "none": None}


def test_scrub_value_keeps_structural_fields_intact() -> None:
    """user_id_hash 12 số trùng dạng CCCD; xoá nó là mất khả năng truy vết."""
    record = {"user_id_hash": "123456789012", "correlation_id": "req-1a2b3c4d"}

    out = scrub_value(record)

    assert out == record
    assert "user_id_hash" in SAFE_KEYS


def test_client_controlled_fields_are_scrubbed() -> None:
    """session_id/feature/correlation_id đến từ request nên client đặt được PII vào."""
    out = scrub_value(
        {
            "session_id": "0912345678",
            "feature": "lienhe-4111 1111 1111 1111",
            "correlation_id": "req-student@vinuni.edu.vn",
        }
    )

    assert out["session_id"] == "[REDACTED_PHONE_VN]"
    assert out["feature"] == "lienhe-[REDACTED_CREDIT_CARD]"
    # [\w.-]+@ nuốt luôn tiền tố "req-" nên cả chuỗi thành một token redacted.
    assert out["correlation_id"] == "[REDACTED_EMAIL]"
    assert not {"session_id", "feature", "correlation_id"} & SAFE_KEYS


def test_redacted_correlation_id_still_correlates() -> None:
    """Redact là ánh xạ tất định nên hai log của cùng request vẫn nối được."""
    first = scrub_value({"correlation_id": "0912345678", "event": "request_received"})
    second = scrub_value({"correlation_id": "0912345678", "event": "response_sent"})

    assert first["correlation_id"] == second["correlation_id"]


def test_scrub_value_stops_at_max_depth() -> None:
    deep: dict = {"level": None}
    node = deep
    for _ in range(12):
        node["next"] = {"email": "deep@vinuni.edu.vn"}
        node = node["next"]

    scrub_value(deep)  # không được raise RecursionError


# --- processor: chạy sau format_exc_info, trước khi ghi file -------------------


def test_nested_payload_is_redacted_in_log_file(log_file: Path) -> None:
    get_logger().info(
        "nested_payload",
        service="api",
        payload={"user": {"email": "victim@vinuni.edu.vn"}, "cards": ["4111 1111 1111 1111"]},
    )

    raw = log_file.read_text(encoding="utf-8")
    assert "victim@vinuni.edu.vn" not in raw
    assert "4111 1111 1111 1111" not in raw


def test_exception_traceback_is_redacted_in_log_file(log_file: Path) -> None:
    """format_exc_info sinh chuỗi traceback, nên scrub_event phải chạy sau nó."""
    try:
        raise ValueError("DB loi voi email leak@vinuni.edu.vn va the 4111 1111 1111 1111")
    except ValueError:
        get_logger().error("request_failed", service="api", exc_info=True)

    raw = log_file.read_text(encoding="utf-8")
    assert "leak@vinuni.edu.vn" not in raw
    assert "4111 1111 1111 1111" not in raw
    assert "[REDACTED_EMAIL]" in raw
    assert _events(log_file)[0]["event"] == "request_failed"


def test_top_level_custom_field_is_redacted(log_file: Path) -> None:
    get_logger().info("custom_event", service="api", note="lien he 0912345678")

    assert _events(log_file)[0]["note"] == "lien he [REDACTED_PHONE_VN]"


def test_correlation_metadata_survives_redaction(log_file: Path) -> None:
    get_logger().info(
        "response_sent",
        service="api",
        correlation_id="req-1a2b3c4d",
        user_id_hash="23eb0de44cad",
        latency_ms=577,
    )

    record = _events(log_file)[0]
    assert record["correlation_id"] == "req-1a2b3c4d"
    assert record["user_id_hash"] == "23eb0de44cad"
    assert record["latency_ms"] == 577


# --- pattern mới ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "token"),
    [
        ("Passport B1234567 het han", "[REDACTED_PASSPORT]"),
        ("CCCD 012345678901 cua khach", "[REDACTED_CCCD]"),
        ("The 4111-1111-1111-1111 bi tu choi", "[REDACTED_CREDIT_CARD]"),
        ("Client IP 192.168.1.104 gui request", "[REDACTED_IP_ADDRESS]"),
        ("Nha o 123 Nguyen Trai, Phuong 7", "[REDACTED_VN_ADDRESS]"),
        ("Dia chi 45 Le Loi, Phường Bến Nghé", "[REDACTED_VN_ADDRESS]"),
        ("So 12 Hai Ba Trung, Tinh Binh Duong", "[REDACTED_VN_ADDRESS]"),
    ],
)
def test_new_patterns_are_redacted(raw: str, token: str) -> None:
    assert token in scrub_text(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "Latency 3000 ms, quan sat p95 tang manh",
        "Co 500 request, lien quan den incident rag_slow",
        "Threshold 2000 ms, xa hon muc SLO",
        "Ghi nhan 15 loi, tinh trang dang xau di",
        "P95 la 4200 ms, thanh pho khong lien quan",
    ],
)
def test_observability_messages_are_not_over_redacted(raw: str) -> None:
    """Che nhầm log vận hành cũng là hỏng: dashboard và điều tra sẽ mất dữ liệu."""
    assert scrub_text(raw) == raw
