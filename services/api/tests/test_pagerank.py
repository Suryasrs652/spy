"""§144/M5 internal PageRank — pure function of the internal link graph."""
from __future__ import annotations

import uuid

import pytest

from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.scoring.pagerank import (
    compute_internal_pagerank,
    normalize_to_100,
    resolve_canonical_duplicates,
)


def _page(**kwargs) -> CrawlPage:
    url = kwargs.pop("url", None) or f"https://x/{uuid.uuid4()}"
    defaults = dict(
        id=uuid.uuid4(), audit_id=uuid.uuid4(), project_id=uuid.uuid4(),
        url=url, normalized_url=url, canonical_url=None,
    )
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


# --------------------------------------------------------------------------
# Canonical duplicates — the exact defect found auditing a real site
# --------------------------------------------------------------------------
#
# spilanthstudio.com's navigation links the homepage as the relative
# "index.html" on every page; its sitemap declares the canonical homepage as
# "/". Google consolidates the two. Spy's own graph did not: `/index.html`
# held 94 of 100 points of internal equity while the `/` it canonicalises to
# held 12 — the real homepage read as one of the most weakly-linked pages on
# the site, and every rule reading PageRank inherited the error.


def test_a_page_and_its_canonical_duplicate_resolve_to_one_node() -> None:
    real = _page(url="https://x/")
    duplicate = _page(url="https://x/index.html", canonical_url="https://x/")
    resolved = resolve_canonical_duplicates([real, duplicate])
    assert resolved[duplicate.id] == real.id
    assert resolved[real.id] == real.id


def test_the_real_world_case_both_urls_report_the_combined_rank() -> None:
    """Mirrors the found defect: everything links to the relative duplicate,
    almost nothing links to the canonical URL directly. Both must end up
    reporting the *same*, high score — not the duplicate high and the
    canonical low.
    """
    home = _page(url="https://x/")
    home_dup = _page(url="https://x/index.html", canonical_url="https://x/")
    leaves = [_page() for _ in range(10)]
    # Every leaf's nav links the duplicate URL, the way a real template does.
    links = [_link(leaf, home_dup) for leaf in leaves]

    scores = compute_internal_pagerank([home, home_dup, *leaves], links)

    assert scores[home.id] == scores[home_dup.id]
    assert scores[home.id] > max(scores[leaf.id] for leaf in leaves)


def test_a_link_to_the_duplicate_counts_as_a_link_to_the_canonical() -> None:
    """The equity a duplicate receives has to actually reach the canonical
    node — collapsing the two into one score with no equity flowing between
    them would just be a display fix, not a graph fix."""
    canonical = _page()
    duplicate = _page(canonical_url=canonical.normalized_url)
    isolated = _page()  # gets no links at all — the baseline for "unranked"

    scores = compute_internal_pagerank(
        [canonical, duplicate, isolated], [_link(isolated, duplicate)]
    )
    assert scores[canonical.id] > scores[isolated.id]


def test_self_canonical_and_no_canonical_are_both_no_ops() -> None:
    page = _page()
    self_canonical = _page(canonical_url=page.normalized_url)
    # Give self_canonical its own canonical pointing at itself.
    self_canonical.canonical_url = self_canonical.normalized_url
    no_canonical = _page(canonical_url=None)

    resolved = resolve_canonical_duplicates([page, self_canonical, no_canonical])
    assert resolved[self_canonical.id] == self_canonical.id
    assert resolved[no_canonical.id] == no_canonical.id


def test_canonical_chains_resolve_to_their_end() -> None:
    c = _page()
    b = _page(canonical_url=c.normalized_url)
    a = _page(canonical_url=b.normalized_url)
    resolved = resolve_canonical_duplicates([a, b, c])
    assert resolved[a.id] == c.id
    assert resolved[b.id] == c.id
    assert resolved[c.id] == c.id


def test_a_canonical_cycle_does_not_infinite_loop() -> None:
    a, b = _page(), _page()
    a.canonical_url, b.canonical_url = b.normalized_url, a.normalized_url
    resolved = resolve_canonical_duplicates([a, b])
    # Whichever node the cycle resolves to, both agree on the same one and
    # the call returns rather than hanging.
    assert resolved[a.id] == resolved[b.id]


def test_a_longer_cycle_and_a_tail_into_it_share_one_representative() -> None:
    """A -> B -> C -> B: B and C form a cycle, A is a tail leading into it.
    Every page that reaches the cycle — including the tail — must resolve to
    the same member of it."""
    a, b, c = _page(), _page(), _page()
    a.canonical_url = b.normalized_url
    b.canonical_url = c.normalized_url
    c.canonical_url = b.normalized_url
    resolved = resolve_canonical_duplicates([a, b, c])
    assert resolved[a.id] == resolved[b.id] == resolved[c.id]
    assert resolved[b.id] in (b.id, c.id)  # the representative is a cycle member


def test_a_canonical_pointing_outside_the_crawl_is_a_no_op() -> None:
    """A canonical URL the crawler never fetched (blocked, off-site, beyond
    the crawl limit) has nothing to resolve to — the page ranks as itself
    rather than vanishing from the graph."""
    page = _page(canonical_url="https://elsewhere.example/never-crawled")
    resolved = resolve_canonical_duplicates([page])
    assert resolved[page.id] == page.id


def test_duplicates_still_sum_to_the_canonical_sets_one_point_oh() -> None:
    """Collapsing nodes changes what compute_internal_pagerank reports per
    page (a duplicate now equals its canonical) but not the total mass in
    the graph — that still belongs to the deduplicated set of real pages."""
    canonical = _page()
    duplicate = _page(canonical_url=canonical.normalized_url)
    other = _page()
    scores = compute_internal_pagerank(
        [canonical, duplicate, other], [_link(other, canonical)]
    )
    # Sum over the *distinct* nodes, not the raw per-row values (which
    # double-count the duplicate against its canonical by design).
    distinct = {resolve_canonical_duplicates([canonical, duplicate, other])[p]: s
                for p, s in ((canonical.id, scores[canonical.id]), (other.id, scores[other.id]))}
    assert sum(distinct.values()) == pytest.approx(1.0, abs=1e-4)
