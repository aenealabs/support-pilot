"""Offline provider: serves recorded responses so demos never depend on the network."""

import json
from pathlib import Path

from pydantic import BaseModel

from support_pilot.llm.base import LLMError, input_key
from support_pilot.models import Answer, ArticleDraft, ProblemReview


class ReplayProvider:
    name = "replay"

    def __init__(self, replay_dir: Path):
        self.replay_dir = replay_dir

    def answer(self, input_text: str) -> Answer:
        return self._load("answers", input_text, Answer,
                          "Offline demo mode has recorded answers for the suggested questions "
                          "only. Pick one of them, or switch to live AI mode.")

    def review_problem(self, input_text: str) -> ProblemReview:
        return self._load("problems", input_text, ProblemReview,
                          "Offline demo mode has recorded reviews for the demo tickets only. "
                          "Switch to live AI mode for imported tickets.")

    def draft_article(self, input_text: str) -> ArticleDraft:
        return self._load("drafts", input_text, ArticleDraft,
                          "Offline demo mode has recorded drafts for the demo knowledge gaps "
                          "only. Switch to live AI mode for imported tickets.")

    def _load(self, kind: str, input_text: str, model: type[BaseModel], missing: str):
        path = replay_path(self.replay_dir, input_text, kind)
        if not path.exists():
            raise LLMError(missing)
        return model.model_validate(json.loads(path.read_text())["output"])


def replay_path(replay_dir: Path, input_text: str, kind: str = "answers") -> Path:
    return replay_dir / kind / f"{input_key(input_text)}.json"


def record(replay_dir: Path, input_text: str, output: BaseModel, kind: str = "answers") -> Path:
    path = replay_path(replay_dir, input_text, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"input": input_text, "output": output.model_dump()},
                               indent=2) + "\n")
    return path
