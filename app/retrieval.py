"""Dependency-free TF-IDF selector for dynamic few-shot examples."""
from __future__ import annotations

import math
import re
from collections import Counter

_STOP = {"the", "a", "an", "of", "in", "is", "are", "was", "were", "to", "and", "or", "for", "with", "by", "on", "at",
         "that", "have", "has", "each", "which", "what", "how", "many", "return", "list", "their", "than", "per", "all", "any"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


class ExampleSelector:
    def __init__(self, pool: list[tuple[str, str]], k: int = 4):
        self.pool, self.k = pool, k
        docs = [Counter(_tokens(q)) for q, _ in pool]
        n = len(docs)
        df = Counter(t for d in docs for t in d)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, counts: Counter) -> dict[str, float]:
        v = {t: c * self.idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def select(self, question: str) -> list[tuple[str, str]]:
        q = self._vec(Counter(_tokens(question)))
        scores = [(sum(w * v.get(t, 0.0) for t, w in q.items()), -i) for i, v in enumerate(self.vecs)]
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: self.k]
        return [self.pool[i] for i in top]
