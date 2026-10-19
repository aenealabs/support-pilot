"""Run the suggested demo questions through the live model and save responses for replay.

Usage: python -m support_pilot.record_demos [answers] [problems] [drafts]   (default: all)
Credentials come from the environment (API key, `ant auth login`, or workload identity
federation in CI).
"""

import json
import sys
from dataclasses import replace

from sqlalchemy import create_engine

from support_pilot.assist import answer_input, check
from support_pilot.config import Settings, load_settings
from support_pilot.kb import KnowledgeBase
from support_pilot.llm import LLMError
from support_pilot.llm.anthropic_provider import AnthropicProvider
from support_pilot.llm.replay import record
from support_pilot.problem_ai import check_draft, check_review, problem_input
from support_pilot.tickets import TicketStore


def demo_inputs(settings: Settings) -> list[tuple[str, str, list]]:
    """(question, model input, retrieved passages) for each suggested question."""
    kb = KnowledgeBase(create_engine("sqlite://"), settings.dataset_dir / "kb")
    titles = {a.id: a.title for a in kb.articles.values()}
    questions = json.loads((settings.dataset_dir / "questions.json").read_text())["questions"]
    out = []
    for q in questions:
        found = kb.search(q)
        out.append((q, answer_input(q, found, titles), found))
    return out


def demo_problems(settings: Settings) -> list:
    """The recurring problems in the demo tickets, as the app computes them."""
    from support_pilot.db import make_engine

    store = TicketStore(make_engine(":memory:"))
    store.seed_if_empty(settings.dataset_dir, "seed")
    return store.analysis()[0]


def main() -> int:
    settings = replace(load_settings(), llm_provider="anthropic")
    provider = AnthropicProvider(settings.model)
    kinds = [k for k in sys.argv[1:] if k in ("answers", "problems", "drafts")] or \
        ["answers", "problems", "drafts"]
    failures = 0
    for p in demo_problems(settings) if {"problems", "drafts"} & set(kinds) else []:
        text = problem_input(p)
        for kind in ("problems", "drafts"):
            if kind not in kinds or (kind == "drafts" and p.covered):
                continue
            try:
                out = (provider.review_problem(text) if kind == "problems"
                       else provider.draft_article(text))
            except LLMError as e:
                failures += 1
                print(f"FAIL {kind} {p.key}: {e}", file=sys.stderr)
                continue
            record(settings.replay_dir, text, out, kind)
            checked = check_review(out, text) if kind == "problems" else check_draft(out, text)
            name = out.name if kind == "problems" else out.title
            print(f"ok   {kind:8} {p.key}: {name} ({checked.flagged} flagged)")
    for question, text, found in demo_inputs(settings) if "answers" in kinds else []:
        try:
            answer = provider.answer(text)
        except LLMError as e:
            failures += 1
            print(f"FAIL {question[:60]}: {e}", file=sys.stderr)
            continue
        path = record(settings.replay_dir, text, answer)
        result = check(answer, found)
        print(f"ok   {result.outcome:8} {len(result.shown)} steps, {result.removed} removed: "
              f"{question[:60]} -> {path.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
