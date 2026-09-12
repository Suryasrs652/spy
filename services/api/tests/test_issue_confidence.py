"""Per-rule confidence — how much of a finding is observation, how much is
inference — and how it reaches the prioritised list.

The point of the field is that a reader can tell the two apart. These tests
guard the two ways that breaks: a rule quietly claiming certainty it doesn't
have, and the priority formula ignoring the distinction.
"""
from __future__ import annotations

from app.modules.recommendations.engine import build_recommendations
from app.modules.seo.models import Severity
from app.modules.seo.rules import run_all_rules
from app.modules.seo.rules.base import CERTAIN, RuleFinding
from tests.test_scoring import _page


def _find(findings, rule_id: str):
    return next((f for f in findings if f.rule_id == rule_id), None)


def _finding(rule_id: str, *, confidence: float, severity=Severity.MEDIUM, affected=3) -> RuleFinding:
    return RuleFinding(
        rule_id, "Metadata", severity, "Title", "Description", "Recommendation",
        score_impact=-1.0, confidence=confidence,
        affected=[(_page().id, {"url": f"https://example.com/{i}"}) for i in range(affected)],
    )


def test_every_rule_declares_a_usable_confidence() -> None:
    """A confidence of 0 would mean "this rule reports nothing real", and
    anything above 1 would break the 0-1 contract the priority formula and
    the API schema both assume."""
    pages = [
        _page(url="https://example.com/", title=None, meta_description=None, word_count=10),
        _page(url="https://example.com/b", title="x", word_count=0, crawl_depth=9),
    ]
    findings = run_all_rules(pages, [])
    assert findings, "expected the deliberately broken fixture to trip some rules"
    for f in findings:
        assert 0 < f.confidence <= CERTAIN, f"{f.rule_id} has confidence {f.confidence}"


def test_directly_observed_finding_is_certain() -> None:
    # There is no title tag. Nothing about that is a judgement call.
    findings = run_all_rules([_page(title=None)], [])
    assert _find(findings, "SEO_META_001").confidence == CERTAIN


def test_inferred_finding_is_not_certain() -> None:
    # A word-frequency ratio cannot distinguish stuffing from a page that
    # legitimately repeats its own product name, and says so.
    findings = run_all_rules([_page(word_frequency_top_ratio=0.5)], [])
    stuffing = _find(findings, "SEO_CONTENT_008")
    assert stuffing is not None
    assert stuffing.confidence < CERTAIN


def test_title_length_is_heuristic_but_missing_title_is_not() -> None:
    """Both are Metadata rules about the same tag; only one is a judgement.
    Search engines truncate titles by pixel width, so the character range is
    a convention — the absence of the tag is a fact."""
    too_long = run_all_rules([_page(title="x" * 200)], [])
    assert _find(too_long, "SEO_META_003").confidence < CERTAIN
    assert _find(run_all_rules([_page(title=None)], []), "SEO_META_001").confidence == CERTAIN


def test_confidence_reaches_the_recommendation() -> None:
    recs = build_recommendations([_finding("SEO_TEST_001", confidence=0.5)], total_pages=3)
    assert recs[0]["confidence"] == 5

    certain = build_recommendations([_finding("SEO_TEST_002", confidence=CERTAIN)], total_pages=3)
    assert certain[0]["confidence"] == 10


def test_low_confidence_ranks_below_an_otherwise_identical_certainty() -> None:
    """Same severity, same category, same reach — the only difference is how
    sure the rule is. Before confidence was per-rule these tied."""
    recs = build_recommendations(
        [
            _finding("SEO_GUESS_001", confidence=0.5),
            _finding("SEO_FACT_001", confidence=CERTAIN),
        ],
        total_pages=3,
    )
    assert [r["evidence"]["rule_id"] for r in recs] == ["SEO_FACT_001", "SEO_GUESS_001"]
    assert recs[0]["priority_score"] > recs[1]["priority_score"]


def test_a_guess_does_not_land_in_do_now() -> None:
    """The Action Center's top bucket is what a reader works through first.
    A CRITICAL-severity inference should have to be verified before it can
    displace a certainty there."""
    certain, guess = build_recommendations(
        [
            _finding("SEO_FACT_002", confidence=CERTAIN, severity=Severity.CRITICAL, affected=10),
            _finding("SEO_GUESS_002", confidence=0.5, severity=Severity.CRITICAL, affected=10),
        ],
        total_pages=10,
    )
    assert certain["group"] == "DO_NOW"
    assert guess["group"] != "DO_NOW"
