from __future__ import annotations

import hashlib
import re
from typing import Any

# Thứ tự quan trọng: pattern cụ thể hơn chạy trước để không bị pattern rộng nuốt mất.
PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "cccd": r"\b\d{12}\b",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    "passport": r"\b[A-Z]\d{7,8}\b",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    # Địa chỉ VN: số nhà + tên đường, theo sau là từ khoá hành chính.
    # [^\n,] chặn match tràn qua dấu phẩy/xuống dòng để không xoá cả câu log.
    # Không dùng cờ (?i) toàn cục: "quan", "xa", "tinh", "thanh pho" không dấu trùng
    # với từ thường gặp trong log ("quan sát p95", "tình trạng"), nên nhánh không dấu
    # phải kèm ràng buộc số hoặc danh từ riêng viết hoa.
    "vn_address": (
        r"\b\d+[^\n,]{0,40},\s*"
        r"(?:"
        r"(?:[Pp]hường|[Xx]ã|[Qq]uận|[Hh]uyện|[Tt]hành phố|[Tt]ỉnh)\s+[^\n,]{1,40}"
        r"|(?i:phuong|xa|quan|huyen|thanh pho|tp|q)\.?\s*\d{1,3}\b"
        r"|(?:Phuong|Xa|Quan|Huyen|Thanh pho|Tinh|TP)\.?\s+[A-ZĐ][^\n,]{1,40}"
        r")"
    ),
}

# Field cấu trúc của log: không scrub để tránh làm hỏng khả năng truy vết.
# user_id_hash là hex 12 ký tự nên có thể trùng dạng CCCD 12 số và bị xoá nhầm.
SAFE_KEYS: frozenset[str] = frozenset(
    {
        "ts",
        "level",
        "service",
        "correlation_id",
        "user_id_hash",
        "session_id",
        "feature",
        "model",
        "env",
    }
)

MAX_SCRUB_DEPTH = 6


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def scrub_value(value: Any, _depth: int = 0) -> Any:
    """Scrub đệ quy mọi chuỗi trong dict/list/tuple, giữ nguyên field cấu trúc."""
    if _depth > MAX_SCRUB_DEPTH:
        return value
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {
            key: value[key] if key in SAFE_KEYS else scrub_value(value[key], _depth + 1)
            for key in value
        }
    if isinstance(value, (list, tuple)):
        return type(value)(scrub_value(item, _depth + 1) for item in value)
    return value


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
