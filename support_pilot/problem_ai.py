"""AI on recurring problems, checked by code: a problem review (name, likely root cause, fix)
and, for knowledge gaps, a draft article built from how agents resolved the tickets.

Every claim quotes a ticket the model was given; code checks the ticket id and the quote word
for word. A draft becomes a knowledge-base article only when a support lead approves it, and
only its checked steps are published.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

from support_pilot.db import audit, utcnow
from support_pilot.llm.prompts import tickets_message
from support_pilot.models import ArticleDraft, Finding, ProblemReview, TicketQuote
from support_pilot.tickets import Problem, Ticket

SAMPLE = 40  # most recent tickets given to the model
DRAFT, APPROVED, REJECTED = "draft", "approved", "rejected"


def problem_input(p: Problem) -> str:
    stats = (f"{p.key}: {len(p.tickets)} tickets in 12 months; "
             f"{p.recent} in the last 3 months, {p.before} in the 3 before; median "
             f"{p.median_hours} hours to resolve; units: "
             + ", ".join(f"{u} {n}" for u, n in p.units)
             + (f"; article {p.article} linked on {round(100 * p.article_share)}%" if p.covered
                else "; no knowledge-base article covers it"))
    recent = sorted(p.tickets, key=lambda t: (t.created, t.ticket))[-SAMPLE:]
    lines = "\n".join(f"{t.ticket} | {t.short_description} | {t.description} | "
                      f"{t.resolution}" for t in recent)
    return tickets_message(stats, lines)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def ticket_texts(input_text: str) -> dict[str, str]:
    body = input_text.split("<tickets>\n", 1)[1].split("\n</tickets>", 1)[0]
    out = {}
    for line in body.splitlines():
        tid, _, rest = line.partition(" | ")
        out[tid] = _norm(rest)
    return out


def check_quotes(quotes: list[TicketQuote], texts: dict[str, str]) -> list[str]:
    problems = []
    if not quotes:
        problems.append("Quotes no ticket.")
    for q in quotes:
        if q.ticket not in texts:
            problems.append(f"{q.ticket} was not among the tickets given.")
        elif _norm(q.quote) not in texts[q.ticket] or len(_norm(q.quote)) < 6:
            problems.append(f"Quote not found in {q.ticket}.")
    return problems


@dataclass
class CheckedFinding:
    finding: Finding
    problems: list[str] = field(default_factory=list)


@dataclass
class CheckedReview:
    review: ProblemReview
    root: CheckedFinding
    evidence: list[CheckedFinding]

    @property
    def flagged(self) -> int:
        return sum(bool(f.problems) for f in [self.root, *self.evidence])


def check_review(review: ProblemReview, input_text: str) -> CheckedReview:
    texts = ticket_texts(input_text)
    return CheckedReview(
        review, CheckedFinding(review.root_cause, check_quotes(review.root_cause.quotes, texts)),
        [CheckedFinding(f, check_quotes(f.quotes, texts)) for f in review.evidence])


@dataclass
class CheckedDraft:
    draft: ArticleDraft
    steps: list[tuple]  # (step, problems)

    @property
    def flagged(self) -> int:
        return sum(bool(p) for _, p in self.steps)

    def markdown(self) -> str:
        """The article as published: checked steps only, plus what is still unknown."""
        ok = [s for s, p in self.steps if not p]
        body = [self.draft.applies_when, "", "## What to do"]
        body += [f"{n}. {s.text}" for n, s in enumerate(ok, start=1)]
        if self.draft.unknowns:
            body += ["", "## Not yet documented"] + [f"- {u}" for u in self.draft.unknowns]
        return "\n".join(body)


def check_draft(draft: ArticleDraft, input_text: str) -> CheckedDraft:
    texts = ticket_texts(input_text)
    return CheckedDraft(draft, [(s, check_quotes(s.quotes, texts)) for s in draft.steps])


# ---------- storage ----------

class ProblemAi(SQLModel, table=True):
    """A problem review or an article draft. Keyed by ticket set and problem label."""
    id: int | None = Field(default=None, primary_key=True)
    set_id: int = Field(index=True)
    problem: str = Field(index=True)  # the problem's label
    kind: str  # review | draft
    input_text: str
    output: str
    drafted_by: str
    requested_by: str
    status: str = DRAFT  # drafts: draft | approved | rejected
    article_id: str = ""  # set when a draft is approved
    decided_by: str = ""
    reason: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ProblemAiStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save(self, set_id: int, problem: str, kind: str, input_text: str, output, actor: str,
             drafted_by: str) -> ProblemAi:
        rec = ProblemAi(set_id=set_id, problem=problem, kind=kind, input_text=input_text,
                        output=output.model_dump_json(), drafted_by=drafted_by,
                        requested_by=actor)
        with Session(self.engine) as s:
            s.add(rec)
            audit(s, actor, f"problem_ai_{kind}", f"{problem} ({drafted_by})")
            s.commit()
            s.refresh(rec)
        return rec

    def latest(self, set_id: int, problem: str, kind: str) -> ProblemAi | None:
        with Session(self.engine) as s:
            return s.exec(select(ProblemAi).where(ProblemAi.set_id == set_id,
                                                  ProblemAi.problem == problem,
                                                  ProblemAi.kind == kind)
                          .order_by(ProblemAi.id.desc())).first()

    def names(self, set_id: int) -> dict[str, str]:
        """Problem label -> AI name, from the latest review of each problem."""
        with Session(self.engine) as s:
            rows = s.exec(select(ProblemAi).where(ProblemAi.set_id == set_id,
                                                  ProblemAi.kind == "review")
                          .order_by(ProblemAi.id)).all()
        return {r.problem: ProblemReview.model_validate_json(r.output).name for r in rows}

    def approved(self) -> list[ProblemAi]:
        with Session(self.engine) as s:
            return list(s.exec(select(ProblemAi).where(ProblemAi.kind == "draft",
                                                       ProblemAi.status == APPROVED)
                               .order_by(ProblemAi.id)))

    def decide(self, rec_id: int, approve: bool, actor: str, reason: str) -> ProblemAi:
        with Session(self.engine) as s:
            rec = s.get(ProblemAi, rec_id)
            if rec is None or rec.kind != "draft" or rec.status != DRAFT:
                raise ValueError("That draft is not waiting for a decision.")
            if not approve and not reason.strip():
                raise ValueError("Say why the draft is rejected.")
            rec.status = APPROVED if approve else REJECTED
            rec.decided_by, rec.reason = actor, reason.strip()
            if approve:
                count = len(s.exec(select(ProblemAi).where(ProblemAi.status == APPROVED,
                                                           ProblemAi.id != rec.id)).all())
                rec.article_id = f"KB-9{count + 1:02d}"
            s.add(rec)
            audit(s, actor, f"problem_draft_{rec.status}",
                  f"{rec.problem}" + (f" as {rec.article_id}" if approve else f": {reason}"))
            s.commit()
            s.refresh(rec)
        return rec


def sample_tickets(p: Problem) -> list[Ticket]:
    return sorted(p.tickets, key=lambda t: (t.created, t.ticket))[-SAMPLE:]
