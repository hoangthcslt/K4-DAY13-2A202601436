from __future__ import annotations

import os
from typing import Any

try:
    from langfuse import get_client, observe

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_trace(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

        def get_current_trace_id(self) -> None:
            return None

        def flush(self) -> None:
            return None

    def get_client():
        return _DummyClient()


def get_langfuse_client():
    return get_client()


def get_current_trace_id(client: Any) -> str | None:
    """Return the active Langfuse trace ID without making tracing a hard dependency."""
    getter = getattr(client, "get_current_trace_id", None)
    if not callable(getter):
        return None
    try:
        trace_id = getter()
    except Exception:  # Langfuse must never make the API request fail
        return None
    return str(trace_id) if trace_id else None


def flush_langfuse() -> None:
    """Flush queued spans during a graceful API shutdown."""
    if not tracing_enabled():
        return
    try:
        get_langfuse_client().flush()
    except Exception:
        return


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )
