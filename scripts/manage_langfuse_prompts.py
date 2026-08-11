from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.prompt_management import DEFAULT_PROMPT_TEMPLATE
from app.tracing import get_langfuse_client


CANDIDATE_PROMPT_TEMPLATE = (
    DEFAULT_PROMPT_TEMPLATE
    + "\nAnswer concisely, use only the supplied context, and state uncertainty."
)


def _get_by_label(client: Any, name: str, label: str) -> Any | None:
    try:
        return client.get_prompt(
            name,
            label=label,
            type="text",
            cache_ttl_seconds=0,
            max_retries=0,
            fetch_timeout_seconds=5,
        )
    except Exception:
        return None


def bootstrap(client: Any, name: str) -> dict[str, int]:
    """Create the required baseline/candidate versions without duplicating labels."""
    baseline = _get_by_label(client, name, "baseline")
    if baseline is None:
        baseline = client.create_prompt(
            name=name,
            prompt=DEFAULT_PROMPT_TEMPLATE,
            labels=["baseline", "production"],
            type="text",
            tags=["day13", "checkpoint-2"],
            commit_message="Checkpoint 2 baseline prompt",
        )

    candidate = _get_by_label(client, name, "candidate")
    if candidate is None:
        candidate = client.create_prompt(
            name=name,
            prompt=CANDIDATE_PROMPT_TEMPLATE,
            labels=["candidate"],
            type="text",
            tags=["day13", "checkpoint-2"],
            commit_message="Checkpoint 2 candidate prompt",
        )

    return {"baseline": int(baseline.version), "candidate": int(candidate.version)}


def move_production_label(client: Any, name: str, source_label: str) -> int:
    prompt = _get_by_label(client, name, source_label)
    if prompt is None:
        raise RuntimeError(
            f"Không tìm thấy label '{source_label}'. Hãy chạy subcommand bootstrap trước."
        )
    version = int(prompt.version)
    client.update_prompt(
        name=name,
        version=version,
        new_labels=[source_label, "production"],
    )
    return version


def label_status(client: Any, name: str) -> dict[str, int | None]:
    status: dict[str, int | None] = {}
    for label in ("baseline", "candidate", "production"):
        prompt = _get_by_label(client, name, label)
        status[label] = int(prompt.version) if prompt is not None else None
    return status


def main() -> int:
    configure_utf8_stdio()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Tạo prompt v1/v2, đổi production label và rollback trên Langfuse."
    )
    parser.add_argument(
        "action", choices=("bootstrap", "status", "promote", "rollback")
    )
    parser.add_argument(
        "--name",
        default=os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat"),
        help="Tên text prompt trên Langfuse.",
    )
    args = parser.parse_args()

    client = get_langfuse_client()
    try:
        if not client.auth_check():
            raise RuntimeError("Langfuse authentication failed")
        if args.action == "bootstrap":
            versions = bootstrap(client, args.name)
            print(
                f"OK baseline=v{versions['baseline']} candidate=v{versions['candidate']}"
            )
        elif args.action == "promote":
            version = move_production_label(client, args.name, "candidate")
            print(f"OK production -> candidate v{version}")
        elif args.action == "rollback":
            version = move_production_label(client, args.name, "baseline")
            print(f"OK production -> baseline v{version}")
        else:
            print(label_status(client, args.name))
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
