"""Clause retrieval over a parsed policy: small BM25-style keyword scoring, no embeddings or external services."""

import math
import re
from collections import Counter

from ..schemas.claim import PolicyClause

STOPWORDS = set("""the and for are any all per with this that from shall will such under policy insured person
than into been being have has its not our out their there these they which who whom your item items amount rs inr
clause section""".split())


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words if w not in STOPWORDS]


def search_clauses(clauses: list[PolicyClause], query: str, k: int = 3) -> list[tuple[PolicyClause, float]]:
    docs = [Counter(tokens(f"{c.title} {c.title} {c.text}")) for c in clauses]  # title counted twice
    if not docs:
        return []
    df = Counter(t for d in docs for t in d)
    n = len(docs)
    scored = []
    for c, d in zip(clauses, docs):
        score = sum(math.log(1 + n / df[t]) * d[t] / (d[t] + 1.2) for t in set(tokens(query)) if t in d)
        if score > 0:
            scored.append((c, round(score, 3)))
    return sorted(scored, key=lambda x: -x[1])[:k]


def token_overlap(needle: str, haystack: str) -> float:
    """Share of the needle's words that appear in the haystack."""
    n = set(tokens(needle))
    return len(n & set(tokens(haystack))) / len(n) if n else 0.0
