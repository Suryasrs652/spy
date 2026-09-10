"""§144/M5 internal PageRank — pure function of the internal link graph."""
from __future__ import annotations

import uuid

import pytest

from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.scoring.pagerank import compute_internal_pagerank, normalize_to_100


def _page(**kwargs) -> CrawlPage:
    defaults = dict(id=uuid.uuid4(), audit_id=uuid.uuid4(), project_id=uuid.uuid4(), url="https://x/", normalized_url="https://x/")
    defaults.update(kwargs)
    return CrawlPage(**defaults)


def _link(source: CrawlPage, target: CrawlPage) -> PageLink:
    return PageLink(
        id=uuid.uuid4(), audit_id=source.audit_id, source_page_id=source.id, target_url=target.url,
        target_page_id=target.id, is_internal=True,
    )


def test_single_page_gets_full_rank() -> None:
    page = _page()
    scores = compute_internal_pagerank([page], [])
    assert scores == {page.id: 1.0}


def test_empty_graph_returns_empty() -> None:
    assert compute_internal_pagerank([], []) == {}


def test_scores_sum_to_approximately_one() -> None:
    pages = [_page() for _ in range(5)]
    links = [_link(pages[i], pages[(i + 1) % 5]) for i in range(5)]  # a ring
    scores = compute_internal_pagerank(pages, links)
    assert sum(scores.values()) == pytest.approx(1.0, abs=1e-4)


def test_hub_page_outranks_leaf_pages() -> None:
    """A star topology: every other page links only to the hub."""
    hub = _page()
    leaves = [_page() for _ in range(4)]
    links = [_link(leaf, hub) for leaf in leaves]
    scores = compute_internal_pagerank([hub, *leaves], links)
    assert scores[hub.id] > max(scores[leaf.id] for leaf in leaves)


def test_more_inbound_links_means_higher_rank() -> None:
    a, b, c = _page(), _page(), _page()
    # a and c both link to b; only a links to c.
    links = [_link(a, b), _link(c, b), _link(a, c)]
    scores = compute_internal_pagerank([a, b, c], links)
    assert scores[b.id] > scores[c.id] > scores[a.id]


def test_dangling_pages_do_not_leak_rank_mass() -> None:
    """A page with no outbound internal links (a dead end) must still have
    its rank redistributed, not silently discarded — total mass stays ~1.0
    even with dangling nodes present.
    """
    a, b = _page(), _page()  # b has no outbound links at all
    links = [_link(a, b)]
    scores = compute_internal_pagerank([a, b], links)
    assert sum(scores.values()) == pytest.approx(1.0, abs=1e-4)


def test_normalize_to_100_scales_top_page_to_100() -> None:
    hub = _page()
    leaves = [_page() for _ in range(3)]
    links = [_link(leaf, hub) for leaf in leaves]
    raw = compute_internal_pagerank([hub, *leaves], links)
    normalized = normalize_to_100(raw)
    assert normalized[hub.id] == 100.0
    assert all(0 <= v <= 100 for v in normalized.values())


def test_disconnected_pages_still_get_a_score() -> None:
    """Two separate islands with no links between them at all — every page
    still gets a nonzero score from the damping-factor base term.
    """
    a, b = _page(), _page()
    scores = compute_internal_pagerank([a, b], [])
    assert scores[a.id] > 0
    assert scores[b.id] > 0
