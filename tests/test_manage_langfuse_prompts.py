from __future__ import annotations

from dataclasses import dataclass

from scripts.manage_langfuse_prompts import bootstrap, move_production_label


@dataclass
class Prompt:
    version: int


class FakePromptClient:
    def __init__(self) -> None:
        self.by_label: dict[str, Prompt] = {}
        self.created: list[dict] = []
        self.updated: list[dict] = []

    def get_prompt(self, name: str, *, label: str, **kwargs) -> Prompt:
        if label not in self.by_label:
            raise LookupError(label)
        return self.by_label[label]

    def create_prompt(self, **kwargs) -> Prompt:
        prompt = Prompt(version=len(self.created) + 1)
        self.created.append(kwargs)
        for label in kwargs["labels"]:
            self.by_label[label] = prompt
        return prompt

    def update_prompt(self, **kwargs) -> None:
        self.updated.append(kwargs)


def test_bootstrap_creates_baseline_and_candidate_once() -> None:
    client = FakePromptClient()

    first = bootstrap(client, "day13-chat")
    second = bootstrap(client, "day13-chat")

    assert first == second == {"baseline": 1, "candidate": 2}
    assert len(client.created) == 2
    assert client.created[0]["labels"] == ["baseline", "production"]
    assert client.created[1]["labels"] == ["candidate"]


def test_promote_and_rollback_move_production_to_selected_version() -> None:
    client = FakePromptClient()
    bootstrap(client, "day13-chat")

    candidate_version = move_production_label(client, "day13-chat", "candidate")
    baseline_version = move_production_label(client, "day13-chat", "baseline")

    assert candidate_version == 2
    assert baseline_version == 1
    assert client.updated == [
        {
            "name": "day13-chat",
            "version": 2,
            "new_labels": ["candidate", "production"],
        },
        {
            "name": "day13-chat",
            "version": 1,
            "new_labels": ["baseline", "production"],
        },
    ]
