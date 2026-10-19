"""Live provider backed by the Claude API (or Microsoft Foundry, same SDK surface)."""

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from support_pilot.llm.base import LLMError
from support_pilot.llm.prompts import ANSWER_SYSTEM, DRAFT_SYSTEM, PROBLEM_SYSTEM
from support_pilot.models import Answer, ArticleDraft, ProblemReview

# Server-side fallback: if a safety classifier declines, the API retries on Anthropic's
# recommended fallback model within the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    """`server_fallbacks` sends the server-side refusal fallback; platforms without it
    (such as Foundry) use the SDK's client-side fallback middleware instead."""

    def __init__(self, model: str, client: anthropic.Anthropic | None = None,
                 name: str = "anthropic", server_fallbacks: bool = True):
        self.model = model
        self.client = client or anthropic.Anthropic()
        self.name = name
        self.server_fallbacks = server_fallbacks

    def answer(self, input_text: str) -> Answer:
        return self._parse(ANSWER_SYSTEM, input_text, Answer, effort="medium", what="answer")

    def review_problem(self, input_text: str) -> ProblemReview:
        return self._parse(PROBLEM_SYSTEM, input_text, ProblemReview, effort="medium",
                           what="problem review")

    def draft_article(self, input_text: str) -> ArticleDraft:
        return self._parse(DRAFT_SYSTEM, input_text, ArticleDraft, effort="medium",
                           what="article draft")

    def _parse(self, system: str, message: str, output_format: type[T], *,
               effort: str, what: str) -> T:
        try:
            fallback = ({"betas": [FALLBACK_BETA], "fallbacks": "default"}
                        if self.server_fallbacks else {})
            # Streamed so a long response never hits an HTTP timeout; the helper still
            # parses and validates the final message against the schema.
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                system=system,
                messages=[{"role": "user", "content": message}],
                output_format=output_format,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                **fallback,
            ) as stream:
                response = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("The Anthropic API key is missing or invalid.") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Rate limited by the Anthropic API. Try again shortly.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API. Check the network.") from e

        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request. Rephrase the input and retry.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The response was cut off. Try a shorter input.")
        if response.parsed_output is None:
            raise LLMError(f"The model did not return a valid {what}.")
        return response.parsed_output
