"""Group support tickets into recurring problems by their words. Pure functions, no AI.

TF-IDF over the ticket title and description (ids, part numbers, file names, and numbers
removed), then single-pass clustering: each ticket joins the most similar existing group if
it is similar enough, else starts a new one. Deterministic: the same tickets always give the
same groups. Groups worded differently but about the same problem (similar centroids) are
merged. Small groups are left unclustered rather than forced into a problem.
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

STOP = set("""a an the and or of to in on for is it my i we our me can cannot not no
with from at by be been has have had this that what who how do does did when after before
since still need needs some someone any all every keeps keep get gets getting says said shows
show see there here into out up about only also just one two three new please""".split())
TOKEN = re.compile(r"[a-z][a-z'-]+")
NOISE = re.compile(r"\b\d{3}-\d+\b|\b[\w-]+\.(prt|asm|drw)\b|\b\d+\b|inc\d+", re.IGNORECASE)
THRESHOLD = 0.32  # a ticket joins a group at this similarity to its centroid
MERGE = 0.25  # groups whose centroids are this similar describe the same problem
MIN_SIZE = 12  # smaller groups stay unclustered
# Tuned on the generated demo tickets; real ticket text will need its own tuning.


def singular(w: str) -> str:
    """Rough English singular, enough to merge 'crashes'/'crash' and keep 'access'."""
    if len(w) <= 4 or w.endswith(("ss", "us", "is")):
        return w
    if w.endswith(("ches", "shes", "xes", "sses")):
        return w[:-2]
    if w.endswith("ies"):
        return w[:-3] + "y"
    return w[:-1] if w.endswith("s") else w


def tokens(text: str) -> list[str]:
    text = NOISE.sub(" ", text.lower())
    out = []
    for w in TOKEN.findall(text):
        w = w.strip("'-")
        if len(w) > 2 and w not in STOP:
            out.append(singular(w))
    return out


def vectors(texts: list[str]) -> list[dict[str, float]]:
    docs = [Counter(tokens(t)) for t in texts]
    df = Counter(w for d in docs for w in d)
    n = len(docs)
    out = []
    for d in docs:
        v = {w: (1 + math.log(c)) * math.log((1 + n) / (1 + df[w])) for w, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out.append({w: x / norm for w, x in v.items()})
    return out


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


@dataclass
class Group:
    members: list[int] = field(default_factory=list)
    total: dict[str, float] = field(default_factory=dict)

    def centroid(self) -> dict[str, float]:
        norm = math.sqrt(sum(x * x for x in self.total.values())) or 1.0
        return {w: x / norm for w, x in self.total.items()}

    def add(self, i: int, v: dict[str, float]) -> None:
        self.members.append(i)
        for w, x in v.items():
            self.total[w] = self.total.get(w, 0.0) + x

    def top_terms(self, k: int = 4) -> list[str]:
        return [w for w, _ in sorted(self.total.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def cluster(texts: list[str], threshold: float = THRESHOLD, min_size: int = MIN_SIZE,
            merge_at: float = MERGE) -> tuple[list[Group], list[int]]:
    """Returns the groups (largest first) and the indexes left unclustered."""
    vs = vectors(texts)
    groups: list[Group] = []
    centroids: list[dict[str, float]] = []
    for i, v in enumerate(vs):
        best, score = -1, 0.0
        for g, c in enumerate(centroids):
            s = cosine(v, c)
            if s > score:
                best, score = g, s
        if best >= 0 and score >= threshold:
            groups[best].add(i, v)
            centroids[best] = groups[best].centroid()
        else:
            g = Group()
            g.add(i, v)
            groups.append(g)
            centroids.append(g.centroid())
    # second pass: re-assign every ticket to its nearest final centroid (stabilizes groups)
    final = [g.centroid() for g in groups]
    regrouped: dict[int, Group] = defaultdict(Group)
    for i, v in enumerate(vs):
        best = max(range(len(final)), key=lambda g: (cosine(v, final[g]), -g))
        regrouped[best].add(i, v)
    big = [g for g in regrouped.values() if len(g.members) >= min_size]
    left = sorted(i for g in regrouped.values() if len(g.members) < min_size for i in g.members)
    merged = merge(big, vs, merge_at)
    return sorted(merged, key=lambda g: (-len(g.members), g.members[0])), left


def merge(groups: list[Group], vs: list[dict[str, float]], at: float) -> list[Group]:
    """Join groups whose centroids are similar (same problem, different wording)."""
    cents = [g.centroid() for g in groups]
    parent = list(range(len(groups)))

    def root(x: int) -> int:
        while parent[x] != x:
            x = parent[x]
        return x

    for a in range(len(groups)):
        for b in range(a + 1, len(groups)):
            if cosine(cents[a], cents[b]) >= at:
                parent[root(b)] = root(a)
    joined: dict[int, Group] = {}
    for i, g in enumerate(groups):
        target = joined.setdefault(root(i), Group())
        for m in g.members:
            target.add(m, vs[m])
    for g in joined.values():
        g.members.sort()
    return list(joined.values())
