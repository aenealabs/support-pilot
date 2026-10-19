"""Provider interface shared by the live and replay LLM backends."""

import hashlib
from typing import Protocol

from support_pilot.models import Answer, ArticleDraft, ProblemReview


class LLMError(Exception):
    """A provider could not produce a usable result; the message is user-facing."""


class LLMProvider(Protocol):
    name: str

    def answer(self, input_text: str) -> Answer: ...

    def review_problem(self, input_text: str) -> ProblemReview: ...

    def draft_article(self, input_text: str) -> ArticleDraft: ...


def input_key(text: str) -> str:
    """Stable key for an input, insensitive to whitespace and case differences."""
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
