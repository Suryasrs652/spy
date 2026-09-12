"""Top-5 blockers and the severity counts beside them.

Pure functions over an audit-shaped object and a list of issue-shaped objects,
so none of this needs a database. What it mostly guards is that the list stays
honest: that an unmeasured component is never a blocker, that one problem is
never reported twice, and that "points recoverable" means the same thing
whether it came from a rule or from a score component.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.modules.audits.blockers import (
    HEALTHY_SIGNAL,
    SIGNAL_BLOCKERS,
    TOP_N,
    count_issues,
    find_blockers,
)


def _issue(rule_id, *, category="Metadata", severity="MEDIUM", affected=10, title="Something wrong"):
    return SimpleNamespace(
        rule_id=rule_id, category=category, severity=severity, affected_count=affected,
        title=title, description="Because of reasons.", recommendation="Fix it.",
    )


def _audit(*, seo_components=None, aeo=None, geo=None, pages=100):
    return SimpleNamespace(
        evidence={
            "total_pages_scored": pages,
            "seo": {"components": seo_components or {}},
            "aeo": {"components": aeo or {}} if aeo is not None else {},
            "geo": {"components": geo or {}} if geo is not None else {},
        }
    )


# --------------------------------------------------------------------------
# Severity counts
# --------------------------------------------------------------------------


def test_counts_both_issues_and_the_pages_behind_them() -> None:
    """One issue affecting 70 pages and 70 issues affecting one page each look
    identical with only one of these numbers, and they are not the same site."""
    counts = count_issues([
        _issue("A", severity="HIGH", affected=2),
        _issue("B", severity="HIGH", affected=40),
        _issue("C", severity="LOW", affected=5),
        _issue("D", severity="INFO", affected=70),
    ])
    assert counts["high"] == {"issues": 2, "pages": 42}
    assert counts["critical"] == {"issues": 0, "pages": 0}
    # LOW and INFO are the tail: real findings, none of them urgent.
    assert counts["opportunities"] == {"issues": 2, "pages": 75}


# --------------------------------------------------------------------------
# Blockers from score components
# --------------------------------------------------------------------------


def test_a_weakness_no_rule_watches_still_becomes_a_blocker() -> None:
    """The reason this engine exists: roughly a hundred rules cover markup and
    crawling, and none of them fire on "no page carries a byline". Without
    this, that never reaches a list of things to do."""
    audit = _audit(geo={"author_transparency": 0.0})
    blockers = find_blockers(audit=audit, issues=[])
    assert [b["key"] for b in blockers] == ["geo.author_transparency"]
    assert blockers[0]["source"] == "SIGNAL"
    assert "100%" in blockers[0]["title"]


def test_an_unmeasured_component_is_never_a_blocker() -> None:
    """`null` means nobody could measure it, which is not a deficit. Scoring
    it as one invents work against a site that did nothing wrong."""
    audit = _audit(aeo={"faq_implementation": None, "answerability": None})
    assert find_blockers(audit=audit, issues=[]) == []


def test_a_healthy_component_is_not_a_blocker() -> None:
    audit = _audit(geo={"author_transparency": HEALTHY_SIGNAL})
    assert find_blockers(audit=audit, issues=[]) == []


def test_a_component_a_rule_already_covers_defers_to_the_rule() -> None:
    """No Organization schema is both SEO_SCHEMA_003 and a low
    `entity_recognition`. Reporting both is one problem shown twice — and the
    rule is the better version, because it can name pages."""
    audit = _audit(geo={"entity_recognition": 10.0})

    alone = find_blockers(audit=audit, issues=[])
    assert [b["key"] for b in alone] == ["geo.entity_recognition"]

    with_rule = find_blockers(
        audit=audit,
        issues=[_issue("SEO_SCHEMA_003", category="Structured Data", severity="HIGH", affected=100)],
    )
    assert "geo.entity_recognition" not in [b["key"] for b in with_rule]
    assert with_rule[0]["source"] == "RULE"


def test_no_two_signal_blockers_read_the_same_measurement() -> None:
    """`passage_extractability` is measured once and shared by AEO and GEO.
    Listing it under both names would report one problem twice."""
    pairs = {(s.section, s.component) for s in SIGNAL_BLOCKERS}
    assert len(pairs) == len(SIGNAL_BLOCKERS)
    assert ("geo", "citation_readiness") not in pairs, (
        "geo.citation_readiness is the same number as aeo.passage_extraction"
    )


# --------------------------------------------------------------------------
# Blockers from rule findings, and the shared currency
# --------------------------------------------------------------------------


def test_a_rule_finding_is_costed_at_what_it_took_off_the_score() -> None:
    audit = _audit(seo_components={"onpage": 90.0}, pages=100)
    blockers = find_blockers(
        audit=audit, issues=[_issue("SEO_META_004", severity="MEDIUM", affected=100)]
    )
    # The one finding in `onpage` absorbs the whole 10-point deduction, worth
    # 10 * 0.20 (onpage within SEO) * 0.60 (SEO within overall) = 1.2.
    assert blockers[0]["points_recoverable"] == 1.2
    assert blockers[0]["rule_id"] == "SEO_META_004"
    assert blockers[0]["affected_pages"] == 100


def test_findings_never_claim_more_points_than_the_category_lost() -> None:
    """A category score floors at zero, so past 100 the extra deductions cost
    nothing. Attributing each finding its raw deduction would promise back
    points that were never taken."""
    audit = _audit(seo_components={"onpage": 0.0}, pages=100)
    issues = [
        _issue(f"SEO_META_{i:03d}", severity="CRITICAL", affected=100) for i in range(10)
    ]
    blockers = find_blockers(audit=audit, issues=issues, top_n=99)
    ceiling = 100.0 * 0.20 * 0.60  # the whole onpage component, at most
    assert sum(b["points_recoverable"] for b in blockers) <= ceiling + 0.01


def test_rule_and_signal_blockers_are_ranked_on_one_scale() -> None:
    """The point of a shared currency: a metadata issue and a fact-density gap
    have to be genuinely comparable, not merely adjacent in a list."""
    audit = _audit(
        seo_components={"onpage": 94.0},   # costing a little
        geo={"author_transparency": 0.0},  # costing a lot
        pages=100,
    )
    blockers = find_blockers(
        audit=audit, issues=[_issue("SEO_META_004", severity="LOW", affected=100)]
    )
    assert [b["key"] for b in blockers] == ["geo.author_transparency", "SEO_META_004"]
    assert blockers[0]["points_recoverable"] > blockers[1]["points_recoverable"]


def test_a_difference_too_small_to_matter_is_dropped_entirely() -> None:
    """A finding worth a tenth of a point is not blocking anything, and
    listing it crowds out something that is."""
    audit = _audit(seo_components={"onpage": 99.0}, pages=100)
    assert find_blockers(
        audit=audit, issues=[_issue("SEO_META_004", severity="LOW", affected=10)]
    ) == []


def test_the_list_is_capped_and_ordered_by_magnitude() -> None:
    audit = _audit(
        geo={"author_transparency": 0.0, "fact_density": 0.0, "source_attribution": 0.0},
        aeo={"answerability": 0.0, "question_coverage": 0.0, "structured_answers": 0.0,
             "passage_extraction": 0.0, "faq_implementation": 0.0},
    )
    blockers = find_blockers(audit=audit, issues=[])
    assert len(blockers) == TOP_N
    points = [b["points_recoverable"] for b in blockers]
    assert points == sorted(points, reverse=True)


def test_every_blocker_says_what_to_do_about_it() -> None:
    audit = _audit(
        seo_components={"onpage": 70.0},
        geo={"author_transparency": 0.0, "fact_density": 0.0},
        aeo={"answerability": 0.0},
        pages=100,
    )
    blockers = find_blockers(
        audit=audit, issues=[_issue("SEO_META_004", severity="HIGH", affected=100)]
    )
    assert blockers
    for blocker in blockers:
        assert blocker["what_to_do"].strip()
        assert blocker["detail"].strip()
        assert blocker["effort_label"] in ("Low", "Medium", "High")


def test_an_audit_with_no_evidence_produces_no_blockers() -> None:
    assert find_blockers(audit=SimpleNamespace(evidence={}), issues=[]) == []
    assert find_blockers(audit=SimpleNamespace(evidence=None), issues=[]) == []
