"""The knowledge base: Markdown articles split into passages, searched with SQLite FTS5.

Retrieval is code: the question's words are matched against passages (BM25 ranking), and
only the top passages are given to the model. Nothing else can be cited.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from support_pilot.clustering import STOP

WORD = re.compile(r"[A-Za-z][A-Za-z-]+")
PASSAGES = 6  # passages given to the model for each question; nothing else can be cited


@dataclass(frozen=True)
class Article:
    id: str
    category: str
    title: str
    body: str


@dataclass(frozen=True)
class Passage:
    article: str
    section: int
    heading: str
    text: str

    @property
    def ref(self) -> str:
        return f"{self.article} §{self.section}"


def load_articles(kb_dir: Path) -> list[Article]:
    out = []
    for path in sorted(kb_dir.glob("*.md")):
        raw = path.read_text()
        meta, body = raw.split("---", 2)[1:]
        fields = dict(line.split(": ", 1) for line in meta.strip().splitlines())
        out.append(Article(fields["id"], fields["category"], fields["title"], body.strip()))
    return out


def passages(article: Article) -> list[Passage]:
    """One passage per section; the text before the first '## ' is section 1."""
    body = re.sub(r"^# .*\n+", "", article.body)
    parts = re.split(r"\n(?=## )", body)
    out = []
    for n, part in enumerate(parts, start=1):
        lines = part.strip().splitlines()
        heading = lines[0][3:].strip() if lines and lines[0].startswith("## ") else article.title
        content = "\n".join(lines[1:] if lines and lines[0].startswith("## ") else lines).strip()
        out.append(Passage(article.id, n, heading, content))
    return out


class KnowledgeBase:
    def __init__(self, engine: Engine, kb_dir: Path):
        self.engine = engine
        self.articles = {a.id: a for a in load_articles(kb_dir)}
        self.passages = [p for a in self.articles.values() for p in passages(a)]
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS kb_fts"))
            conn.execute(text("CREATE VIRTUAL TABLE kb_fts USING fts5(ref UNINDEXED, title, "
                              "heading, body)"))
            for p in self.passages:
                conn.execute(text("INSERT INTO kb_fts(ref, title, heading, body) "
                                  "VALUES (:r, :t, :h, :b)"),
                             {"r": p.ref, "t": self.articles[p.article].title,
                              "h": p.heading, "b": p.text})

    def add(self, article: Article) -> None:
        """Publish an article (an approved draft) so Ask can use it."""
        self.articles[article.id] = article
        new = passages(article)
        self.passages += new
        with self.engine.begin() as conn:
            for p in new:
                conn.execute(text("INSERT INTO kb_fts(ref, title, heading, body) "
                                  "VALUES (:r, :t, :h, :b)"),
                             {"r": p.ref, "t": article.title, "h": p.heading, "b": p.text})

    def search(self, question: str, k: int = PASSAGES) -> list[Passage]:
        words = [w.lower() for w in WORD.findall(question) if w.lower() not in STOP
                 and len(w) > 2]
        if not words:
            return []
        query = " OR ".join(f'"{w}"*' for w in dict.fromkeys(words))
        by_ref = {p.ref: p for p in self.passages}
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT ref FROM kb_fts WHERE kb_fts MATCH :q "
                                     "ORDER BY bm25(kb_fts, 0, 4.0, 2.0, 1.0) LIMIT :k"),
                                {"q": query, "k": k}).all()
        return [by_ref[r[0]] for r in rows]
