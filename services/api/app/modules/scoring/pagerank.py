"""§144/M5 — internal PageRank: how much internal link equity each page in
one audit's crawl holds.

Computed purely from that audit's own internal link graph (§3 — no
external data, no guessing, no LLM). Standard power-iteration PageRank;
external links never contribute here — a different, external signal
covered by app/modules/backlinks. Dangling pages (no outbound internal
links) redistribute their mass evenly across the whole graph each
iteration rather than leaking it, so the scores always sum to ~1.0
regardless of how many dead-end pages the site has.
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from app.modules.crawler.models import CrawlPage, PageLink

DAMPING_FACTOR = 0.85
MAX_ITERATIONS = 100
CONVERGENCE_THRESHOLD = 1e-6


def compute_internal_pagerank(pages: list[CrawlPage], links: list[PageLink]) -> dict[uuid.UUID, float]:
    """Returns {page_id: raw_pagerank}, summing to ~1.0 across all pages."""
    page_ids = [p.id for p in pages]
    n = len(page_ids)
    if n == 0:
        return {}
    if n == 1:
        return {page_ids[0]: 1.0}

    valid_ids = set(page_ids)
    outbound: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in links:
        if (
            link.is_internal
            and link.target_page_id
            and link.source_page_id in valid_ids
            and link.target_page_id in valid_ids
        ):
            outbound[link.source_page_id].append(link.target_page_id)

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

    return scores


def normalize_to_100(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Rescales so the highest-ranked page (usually the homepage) reads as
    100 — raw PageRank values are tiny fractions (~1/n) that mean nothing
    to a reader without this context.
    """
    if not scores:
        return {}
    peak = max(scores.values()) or 1.0
    return {pid: round(100 * score / peak, 2) for pid, score in scores.items()}
