"""§23-§25 SEO rule engine — pure functions of stored crawl evidence."""
from __future__ import annotations

import uuid

from app.modules.crawler.models import CrawlPage, PageLink
from app.modules.seo.rules import run_all_rules
from tests.test_scoring import _page


def _find(findings, rule_id: str):
    return next((f for f in findings if f.rule_id == rule_id), None)


def test_missing_title_detected() -> None:
    pages = [_page(title=None)]
    findings = run_all_rules(pages, [])
    finding = _find(findings, "SEO_META_001")
    assert finding is not None
    assert finding.affected_count == 1


def test_duplicate_titles_detected() -> None:
    pages = [_page(url=f"https://example.com/{i}", title="Same Title") for i in range(3)]
    findings = run_all_rules(pages, [])
    finding = _find(findings, "SEO_META_002")
    assert finding is not None
    assert finding.affected_count == 3


def test_unique_titles_not_flagged() -> None:
    pages = [_page(url=f"https://example.com/{i}", title=f"Title {i}") for i in range(3)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_META_002") is None


def test_thin_content_threshold() -> None:
    pages = [_page(word_count=50)]  # below default 150-word threshold
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_CONTENT_001") is not None


def test_thin_content_respects_custom_config() -> None:
    pages = [_page(word_count=200)]
    findings_default = run_all_rules(pages, [])
    assert _find(findings_default, "SEO_CONTENT_001") is None

    findings_strict = run_all_rules(pages, [], rule_config={"THIN_CONTENT_WORD_THRESHOLD": 300})
    assert _find(findings_strict, "SEO_CONTENT_001") is not None


def test_broken_pages_detected() -> None:
    pages = [_page(status_code=404, indexable=False)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_CRAWL_001") is not None


def test_server_errors_detected() -> None:
    pages = [_page(status_code=503, indexable=False)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_CRAWL_002") is not None


def test_orphan_page_detected() -> None:
    home = _page(url="https://example.com/", normalized_url="https://example.com/", crawl_depth=0)
    orphan = _page(url="https://example.com/orphan", normalized_url="https://example.com/orphan", crawl_depth=5)
    # No PageLink at all points to `orphan`.
    findings = run_all_rules([home, orphan], [])
    finding = _find(findings, "SEO_LINK_002")
    assert finding is not None
    assert orphan.id in [pid for pid, _ in finding.affected]


def test_linked_page_not_orphan() -> None:
    home = _page(url="https://example.com/", normalized_url="https://example.com/", crawl_depth=0)
    linked = _page(url="https://example.com/linked", normalized_url="https://example.com/linked", crawl_depth=1)
    link = PageLink(
        id=uuid.uuid4(), audit_id=uuid.uuid4(), source_page_id=home.id,
        target_url=linked.normalized_url, target_page_id=linked.id,
        is_internal=True, nofollow=False, ugc=False, sponsored=False,
    )
    findings = run_all_rules([home, linked], [link])
    finding = _find(findings, "SEO_LINK_002")
    linked_is_orphan = finding is not None and linked.id in [pid for pid, _ in finding.affected]
    assert not linked_is_orphan


def test_mixed_content_detected() -> None:
    pages = [_page(mixed_content=True)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_SEC_002") is not None


def test_http_page_detected() -> None:
    pages = [_page(url="http://example.com/", normalized_url="http://example.com/")]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_SEC_001") is not None


def test_clean_site_has_minimal_findings() -> None:
    from tests.test_scoring import _clean_site

    pages = _clean_site()
    findings = run_all_rules(pages, [])
    high_or_critical = [f for f in findings if f.severity.value in ("CRITICAL", "HIGH")]
    assert high_or_critical == [], f"clean site should have no HIGH/CRITICAL findings, got {high_or_critical}"


def test_weakly_linked_sitemap_page_detected() -> None:
    pages = [
        _page(from_sitemap=True, internal_pagerank=3.5),
        _page(url="https://example.com/other", normalized_url="https://example.com/other", from_sitemap=True, internal_pagerank=80.0),
    ]
    findings = run_all_rules(pages, [])
    finding = _find(findings, "SEO_LINK_016")
    assert finding is not None
    assert finding.affected_count == 1


def test_non_sitemap_page_with_low_pagerank_not_flagged() -> None:
    pages = [_page(from_sitemap=False, internal_pagerank=1.0)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_LINK_016") is None


def test_sitemap_page_with_healthy_pagerank_not_flagged() -> None:
    pages = [_page(from_sitemap=True, internal_pagerank=50.0)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_LINK_016") is None


def test_missing_pagerank_data_not_flagged() -> None:
    """internal_pagerank is None until the post-crawl computation runs —
    must never be treated as "zero" and flagged."""
    pages = [_page(from_sitemap=True, internal_pagerank=None)]
    findings = run_all_rules(pages, [])
    assert _find(findings, "SEO_LINK_016") is None
