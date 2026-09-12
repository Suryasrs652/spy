"""§144/M5 — internal PageRank: how much internal link equity each page in
one audit's crawl holds.

Computed purely from that audit's own internal link graph (§3 — no
external data, no guessing, no LLM). Standard power-iteration PageRank;
external links never contribute here — a different, external signal
covered by app/modules/backlinks. Dangling pages (no outbound internal
links) redistribute their mass evenly across the whole graph each
iteration rather than leaking it, so the scores always sum to ~1.0
regardless of how many dead-end pages the site has.

**Canonical duplicates are collapsed before the graph is built.** A site
whose navigation links `index.html` relatively while its sitemap declares
`/` has one page reachable at two URLs, and a search engine consolidates
them. Ranking them as two nodes does not: on the site this was found on,
`/index.html` held 94 of 100 points of internal equity while the canonical
`/` it points at held 12, and the real homepage read as one of the most
weakly-linked pages on the site. Every rule downstream inherited that —
"sitemap pages with weak internal linking" flagged the homepage.

So a page whose `canonical_url` resolves to another crawled page is
treated as that page for ranking, and afterwards is reported with its
canonical's score rather than its own. It is the same page; it should not
read as an orphan.
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from app.modules.crawler.models import CrawlPage, PageLink

DAMPING_FACTOR = 0.85
MAX_ITERATIONS = 100
CONVERGENCE_THRESHOLD = 1e-6


def resolve_canonical_duplicates(pages: list[CrawlPage]) -> dict[uuid.UUID, uuid.UUID]:
    """{page_id: the id of the page it canonicalises to}, for every page.

    A page pointing at itself, at nothing, or at a URL outside this crawl
    maps to itself. Chains (A -> B -> C) resolve to their end.

    A *cycle* (A canonicalises to B, B canonicalises to A — a real mistake a
    site can ship) needs a representative every member agrees on. Walking
    from A stops one step before walking from B would, so each independently
    "resolves" to the *other* node rather than a shared one — silently
    reintroducing the duplicate-node bug this function exists to remove.
    The fix is to walk the whole path per page, and when it revisits a node
    (the cycle), resolve every page that reaches it to the same member of
    that cycle (the lowest id, an arbitrary but shared choice) rather than
    wherever each individual walk happened to stop.
    """
    by_url: dict[str, uuid.UUID] = {}
    for page in pages:
        for url in (page.normalized_url, page.url):
            if url:
                by_url.setdefault(url, page.id)

    direct: dict[uuid.UUID, uuid.UUID] = {}
    for page in pages:
        target = by_url.get(page.canonical_url) if page.canonical_url else None
        direct[page.id] = target if target and target != page.id else page.id

    resolved: dict[uuid.UUID, uuid.UUID] = {}
    for page in pages:
        path = [page.id]
        current = direct[page.id]
        while current != direct[current] and current not in path:
            path.append(current)
            current = direct[current]
        if current in path:
            # `current` is the first repeated node, so everything from its
            # first occurrence onward is the cycle; the whole path up to
            # there is a tail leading into it, not part of it.
            cycle = path[path.index(current):]
            current = min(cycle, key=str)
        resolved[page.id] = current
    return resolved


def compute_internal_pagerank(pages: list[CrawlPage], links: list[PageLink]) -> dict[uuid.UUID, float]:
    """Returns {page_id: raw_pagerank}. Canonical duplicates share their
    canonical's score, so the total exceeds 1.0 by whatever those duplicates
    add back; the canonical set itself sums to ~1.0."""
    if not pages:
        return {}
    if len(pages) == 1:
        return {pages[0].id: 1.0}

    canonical_of = resolve_canonical_duplicates(pages)
    page_ids = sorted({canonical_of[p.id] for p in pages}, key=str)
    n = len(page_ids)
    if n == 1:
        return {p.id: 1.0 for p in pages}

    valid_ids = set(page_ids)
    outbound: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in links:
        if not link.is_internal or not link.target_page_id:
            continue
        source = canonical_of.get(link.source_page_id)
        target = canonical_of.get(link.target_page_id)
        # A link from a duplicate to its own canonical is the page linking to
        # itself once they are the same node, and a self-link passes no equity.
        if source in valid_ids and target in valid_ids and source != target:
            outbound[source].append(target)

    out_degree = {pid: len(outbound.get(pid, [])) for pid in page_ids}
    scores = {pid: 1.0 / n for pid in page_ids}

    for _ in range(MAX_ITERATIONS):
        dangling_mass = sum(scores[pid] for pid in page_ids if out_degree[pid] == 0)
        base = (1 - DAMPING_FACTOR) / n + DAMPING_FACTOR * dangling_mass / n

        inbound_sum: dict[uuid.UUID, float] = defaultdict(float)
        for source_id, targets in outbound.items():
            share = scores[source_id] / len(targets)
            for target_id in targets:
                inbound_sum[target_id] += share

        new_scores = {pid: base + DAMPING_FACTOR * inbound_sum.get(pid, 0.0) for pid in page_ids}
        max_delta = max(abs(new_scores[pid] - scores[pid]) for pid in page_ids)
        scores = new_scores
        if max_delta < CONVERGENCE_THRESHOLD:
            break

    # Report each duplicate with its canonical's score. Zero would read as
    # "nothing links here", which is the opposite of what consolidation means.
    return {p.id: scores[canonical_of[p.id]] for p in pages}


def normalize_to_100(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Rescales so the highest-ranked page (usually the homepage) reads as
    100 — raw PageRank values are tiny fractions (~1/n) that mean nothing
    to a reader without this context.
    """
    if not scores:
        return {}
    peak = max(scores.values()) or 1.0
    return {pid: round(100 * score / peak, 2) for pid, score in scores.items()}
