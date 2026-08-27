from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModelProvider(Protocol):
    name: str

    def grounded_answer(self, question: str, evidence: str) -> str: ...


@dataclass
class DemoProvider:
    name: str = "demo"

    def grounded_answer(self, question: str, evidence: str) -> str:
        return f"Based on the approved evidence: {evidence}"


@dataclass
class OpenAIProvider:
    """Deployment seam; the demo never requires a remote model credential."""

    name: str = "openai"

    def grounded_answer(self, question: str, evidence: str) -> str:
        return DemoProvider().grounded_answer(question, evidence)
