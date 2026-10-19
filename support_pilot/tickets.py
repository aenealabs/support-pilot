"""Tickets and recurring problems: clustering, volume, trend, time to resolve, and whether
the knowledge base covers each problem. All computed; the AI is not involved."""

import json
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

from support_pilot.clustering import cluster
from support_pilot.db import audit, utcnow

COVERED_SHARE = 0.2  # an article linked on at least this share of a problem's tickets covers it
RISING_RATIO, RISING_MIN = 1.5, 15  # rising: last 3 months at least 1.5x the 3 before, +15


class ProblemError(ValueError):
    """Invalid import; the message is user-facing."""


class TicketSet(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    as_of: datetime
    tickets: int
    loaded_by: str
    loaded_at: datetime = Field(default_factory=utcnow)


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    set_id: int = Field(foreign_key="ticketset.id", index=True)
    ticket: str = Field(index=True)
    created: datetime
    business_unit: str
    requester: str
    short_description: str
    description: str
    kb_article: str = ""
    resolved: datetime | None = None
    resolution: str = ""


class Handoff(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    set_id: int = Field(index=True)
    problem: str  # the problem's label
    remote_id: int
    sent_by: str
    at: datetime = Field(default_factory=utcnow)


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass
class Problem:
    key: str  # PRB-n, by size
    label: str  # the most common ticket title in the group
    tickets: list[Ticket]
    terms: list[str]
    monthly: list[tuple[str, int]]  # last 12 months
    recent: int  # last 3 months
    before: int  # the 3 months before that
    units: list[tuple[str, int]]
    median_hours: float
    article: str  # most-linked KB article, or ""
    article_share: float

    @property
    def covered(self) -> bool:
        return bool(self.article) and self.article_share >= COVERED_SHARE

    @property
    def rising(self) -> bool:
        return self.recent >= RISING_RATIO * self.before and self.recent - self.before >= \
            RISING_MIN

    @property
    def trend(self) -> float | None:
        return round(100 * (self.recent - self.before) / self.before) if self.before else None


def months_back(as_of: datetime, n: int = 12) -> list[str]:
    y, m = as_of.year, as_of.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}-{m:02d}")
    return list(reversed(out))


def problems(tickets: list[Ticket], as_of: datetime) -> tuple[list[Problem], list[Ticket]]:
    groups, left = cluster([f"{t.short_description}. {t.description}" for t in tickets])
    months = months_back(as_of)
    out = []
    for n, g in enumerate(groups, start=1):
        mine = [tickets[i] for i in g.members]
        per = Counter(f"{t.created.year}-{t.created.month:02d}" for t in mine)
        monthly = [(m, per.get(m, 0)) for m in months]
        hours = [(t.resolved - t.created).total_seconds() / 3600 for t in mine if t.resolved]
        links = Counter(t.kb_article for t in mine if t.kb_article)
        article, count = links.most_common(1)[0] if links else ("", 0)
        out.append(Problem(
            f"PRB-{n}", Counter(t.short_description for t in mine).most_common(1)[0][0], mine,
            g.top_terms(), monthly, sum(c for _, c in monthly[-3:]),
            sum(c for _, c in monthly[-6:-3]),
            Counter(t.business_unit for t in mine).most_common(),
            round(statistics.median(hours), 1) if hours else 0.0, article,
            round(count / len(mine), 2)))
    return out, [tickets[i] for i in left]


class TicketStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._cache: tuple[int, tuple] | None = None

    def seed_if_empty(self, dataset_dir: Path, actor: str) -> None:
        if self.current() is not None or not (dataset_dir / "tickets.csv").exists():
            return
        meta = json.loads((dataset_dir / "tickets_planted.json").read_text())
        self.load((dataset_dir / "tickets.csv").read_text(), "Fictional tickets (demo)",
                  as_utc(datetime.fromisoformat(meta["as_of"])), actor)

    def load(self, csv_text: str, name: str, as_of: datetime | None, actor: str) -> TicketSet:
        import csv
        import io

        reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
        need = {"ticket", "created", "short_description", "description"}
        if not need <= set(reader.fieldnames or []):
            raise ProblemError("The ticket file needs the columns ticket, created, "
                               "short_description, description.")
        rows = []
        try:
            for r in reader:
                rows.append(Ticket(set_id=0, ticket=r["ticket"],
                                   created=as_utc(datetime.fromisoformat(r["created"])),
                                   business_unit=r.get("business_unit", ""),
                                   requester=r.get("requester", ""),
                                   short_description=r["short_description"],
                                   description=r["description"],
                                   kb_article=r.get("kb_article", "") or "",
                                   resolved=as_utc(datetime.fromisoformat(r["resolved"]))
                                   if r.get("resolved") else None,
                                   resolution=r.get("resolution", "")))
        except ValueError as e:
            raise ProblemError("Dates must look like 2026-03-04T09:30.") from e
        if not rows:
            raise ProblemError("The ticket file has no rows.")
        as_of = as_of or max(t.created for t in rows)
        with Session(self.engine) as s:
            ts = TicketSet(name=name, as_of=as_of, tickets=len(rows), loaded_by=actor)
            s.add(ts)
            s.flush()
            for t in rows:
                t.set_id = ts.id
            s.add_all(rows)
            audit(s, actor, "tickets_loaded", f"{name}: {len(rows)} tickets")
            s.commit()
            s.refresh(ts)
        return ts

    def current(self) -> TicketSet | None:
        with Session(self.engine) as s:
            return s.exec(select(TicketSet).order_by(TicketSet.id.desc())).first()

    def analysis(self) -> tuple[list[Problem], list[Ticket]]:
        ts = self.current()
        if ts is None:
            return [], []
        if self._cache and self._cache[0] == ts.id:
            return self._cache[1]
        with Session(self.engine) as s:
            rows = list(s.exec(select(Ticket).where(Ticket.set_id == ts.id)
                               .order_by(Ticket.created, Ticket.id)))
        result = problems(rows, ts.as_of)
        self._cache = (ts.id, result)
        return result

    def record_handoff(self, problem: str, remote_id: int, actor: str) -> None:
        ts = self.current()
        with Session(self.engine) as s:
            s.add(Handoff(set_id=ts.id, problem=problem, remote_id=remote_id, sent_by=actor))
            audit(s, actor, "problem_sent_to_backlog", f"{problem}: inbox item {remote_id}")
            s.commit()

    def handoffs(self) -> dict[str, Handoff]:
        ts = self.current()
        if ts is None:
            return {}
        with Session(self.engine) as s:
            rows = s.exec(select(Handoff).where(Handoff.set_id == ts.id)).all()
        return {h.problem: h for h in rows}
