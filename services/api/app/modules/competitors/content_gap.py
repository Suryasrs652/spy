"""§144/M5 content-gap analysis — a coverage approximation, not a
search-volume-weighted keyword gap. A real keyword-volume gap analysis
needs a third-party keyword database (search volume, difficulty) this app
has no access to; rather than fabricate volume numbers (§3), this compares
what it actually has real evidence for: significant terms appearing in
crawled page titles/H1s. "Terms your competitor's pages mention that yours
don't" is a genuine, if rougher, content-coverage signal — clearly labeled
as that, never presented as a keyword-opportunity report with volumes.
"""
from __future__ import annotations

import re
from collections import Counter

_STOPWORDS = {
    "the", "and", "for", "with", "your", "you", "our", "are", "this", "that",
    "from", "have", "has", "not", "but", "all", "can", "how", "what", "why",
    "who", "will", "was", "were", "been", "being", "into", "about", "more",
    "than", "then", "them", "they", "their", "its", "his", "her", "she",
    "him", "get", "one", "out", "new", "top", "best", "home", "page", "here",
}
_WORD_RE = re.compile(r"[a-z]{4,}")


def extract_top_terms(texts: list[str | None], *, limit: int = 25) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        if not text:
            continue
        for word in _WORD_RE.findall(text.lower()):
            if word not in _STOPWORDS:
                counts[word] += 1
    return [term for term, _count in counts.most_common(limit)]


def compute_gap_terms(*, your_terms: list[str], competitor_terms: list[str]) -> list[str]:
    your_set = set(your_terms)
    return [t for t in competitor_terms if t not in your_set]
