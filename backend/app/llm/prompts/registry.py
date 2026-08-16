"""Versioned prompt registry (LEGAL-ARCHITECTURE.md §5, brief §40).

Prompts are records, not ad hoc f-strings inlined in agent code. Populated
with real prompt content in Phase 2 — the scaffold only defines the shape
so agents can already depend on `PromptRegistry.get(...)` instead of a
hardcoded string.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptRecord:
    id: str
    version: str
    description: str
    model_hint: str
    temperature: float
    template: str


class PromptRegistry:
    _prompts: dict[str, PromptRecord] = {}

    @classmethod
    def register(cls, record: PromptRecord) -> None:
        cls._prompts[f"{record.id}@{record.version}"] = record

    @classmethod
    def get(cls, prompt_id: str, version: str = "latest") -> PromptRecord:
        if version == "latest":
            candidates = [r for k, r in cls._prompts.items() if k.startswith(f"{prompt_id}@")]
            if not candidates:
                raise KeyError(f"No prompt registered for id={prompt_id!r}")
            return sorted(candidates, key=lambda r: r.version)[-1]
        return cls._prompts[f"{prompt_id}@{version}"]
