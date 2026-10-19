from support_pilot.config import Settings
from support_pilot.llm.base import LLMError, LLMProvider
from support_pilot.llm.replay import ReplayProvider, record


class RecordingProvider:
    """Wraps a live provider and saves each response for later offline replay."""

    def __init__(self, inner: LLMProvider, settings: Settings):
        self.inner = inner
        self.settings = settings
        self.name = f"{inner.name} (recording)"

    def answer(self, input_text: str):
        result = self.inner.answer(input_text)
        record(self.settings.replay_dir, input_text, result)
        return result

    def review_problem(self, input_text: str):
        result = self.inner.review_problem(input_text)
        record(self.settings.replay_dir, input_text, result, "problems")
        return result

    def draft_article(self, input_text: str):
        result = self.inner.draft_article(input_text)
        record(self.settings.replay_dir, input_text, result, "drafts")
        return result


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "replay":
        return ReplayProvider(settings.replay_dir)
    if settings.llm_provider in ("anthropic", "foundry"):
        if settings.llm_provider == "anthropic":
            from support_pilot.llm.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(settings.model)
        else:
            from support_pilot.llm.foundry import foundry_provider

            provider = foundry_provider(settings.model)
        return RecordingProvider(provider, settings) if settings.record else provider
    raise ValueError(f"Unknown SP_LLM_PROVIDER: {settings.llm_provider!r}")


__all__ = ["LLMError", "LLMProvider", "build_provider"]
