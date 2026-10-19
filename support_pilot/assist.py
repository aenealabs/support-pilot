"""Ask: retrieve passages, let the model answer from them, check every quote, log the outcome.

A step is shown only if every quote it cites appears word for word in the cited passage.
If no step survives, or the model says the passages do not answer the question, the answer
is withheld and the engineer gets a ready-to-paste ticket instead. Each question is logged
with its outcome, and the engineer can say whether it solved the problem (deflection).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

from support_pilot.db import audit, utcnow
from support_pilot.kb import Passage
from support_pilot.llm.prompts import answer_message
from support_pilot.models import Answer, Step

ANSWERED, WITHHELD = "answered", "withheld"


def passages_text(found: list[Passage], titles: dict[str, str]) -> str:
    return "\n\n".join(f"[{p.ref}] {titles[p.article]} - {p.heading}\n{p.text}" for p in found)


def answer_input(question: str, found: list[Passage], titles: dict[str, str]) -> str:
    return answer_message(question.strip(), passages_text(found, titles))


MIN_QUOTE = 8  # characters; shorter quotes prove nothing


def _norm(s: str) -> str:
    return " ".join(s.replace("**", "").replace("`", "").lower().split())


@dataclass
class Checked:
    answer: Answer
    shown: list[Step]  # steps whose every quote checked out
    removed: int  # steps dropped because a quote did not match its passage
    outcome: str
    sources: list[str]  # passage refs actually used by shown steps


def check(answer: Answer, found: list[Passage]) -> Checked:
    texts = {p.ref: _norm(p.text) for p in found}
    shown, removed = [], 0
    for step in answer.steps:
        ok = bool(step.cites) and all(c.passage in texts and _norm(c.quote) in texts[c.passage]
                                      and len(_norm(c.quote)) >= MIN_QUOTE for c in step.cites)
        if ok:
            shown.append(step)
        else:
            removed += 1
    outcome = ANSWERED if answer.answerable and shown else WITHHELD
    sources = list(dict.fromkeys(c.passage for s in shown for c in s.cites))
    return Checked(answer, shown, removed, outcome, sources)


class AskLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    question: str
    asked_by: str
    outcome: str  # answered | withheld
    sources: str = ""  # passage refs shown, comma separated
    removed: int = 0
    drafted_by: str = ""
    solved: bool | None = None  # the engineer's feedback
    at: datetime = Field(default_factory=utcnow)


class AskStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def log(self, question: str, actor: str, checked: Checked, drafted_by: str) -> AskLog:
        entry = AskLog(question=question.strip(), asked_by=actor, outcome=checked.outcome,
                       sources=", ".join(checked.sources), removed=checked.removed,
                       drafted_by=drafted_by)
        with Session(self.engine) as s:
            s.add(entry)
            audit(s, actor, f"ask_{checked.outcome}",
                  f"{question.strip()[:120]}"
                  + (f" (sources {entry.sources})" if entry.sources else "")
                  + (f"; {checked.removed} unsupported step(s) removed" if checked.removed
                     else ""))
            s.commit()
            s.refresh(entry)
        return entry

    def feedback(self, ask_id: int, solved: bool, actor: str) -> None:
        with Session(self.engine) as s:
            entry = s.get(AskLog, ask_id)
            if entry is None or entry.solved is not None:
                return
            entry.solved = solved
            s.add(entry)
            audit(s, actor, "ask_feedback", f"#{ask_id}: {'solved' if solved else 'not solved'}")
            s.commit()

    def recent(self, limit: int = 20) -> list[AskLog]:
        with Session(self.engine) as s:
            return list(s.exec(select(AskLog).order_by(AskLog.id.desc()).limit(limit)))

    def stats(self) -> dict:
        with Session(self.engine) as s:
            rows = list(s.exec(select(AskLog)))
        answered = [r for r in rows if r.outcome == ANSWERED]
        rated = [r for r in answered if r.solved is not None]
        return {"asked": len(rows), "answered": len(answered),
                "withheld": len(rows) - len(answered),
                "solved": sum(bool(r.solved) for r in rated), "rated": len(rated)}
