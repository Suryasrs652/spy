"""§23 International rules (hreflang) — previously untested, which is very
likely why the canonical-blindness bug below shipped and stayed unnoticed
until an audit agent flagged it on a real four-language site.
"""
from __future__ import annotations

from app.modules.seo.rules import run_all_rules
from tests.test_scoring import _page


def _find(findings, rule_id: str):
    return next((f for f in findings if f.rule_id == rule_id), None)


def _tag(lang: str, url: str) -> dict:
    return {"lang": lang, "url": url}


# --------------------------------------------------------------------------
# SEO_INTL_001 — missing self-reference
# --------------------------------------------------------------------------


def test_missing_self_reference_is_detected() -> None:
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[_tag("fr", "https://x.com/fr/")],  # no self entry at all
    )
    findings = run_all_rules([page], [])
    assert _find(findings, "SEO_INTL_001") is not None


def test_a_genuine_self_reference_is_not_flagged() -> None:
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[
            _tag("en", "https://x.com/en/"), _tag("fr", "https://x.com/fr/"),
        ],
    )
    findings = run_all_rules([page], [])
    assert _find(findings, "SEO_INTL_001") is None


def test_an_hreflang_entry_pointing_at_the_canonical_counts_as_self_reference() -> None:
    """The bug this guards: spilanthstudio.com's homepage is reachable at
    both "/" and "/index.html" (a relative nav link, not a mistake) with
    "/index.html" correctly canonicalizing to "/". "/index.html"'s hreflang
    block points its own en-IN entry at the canonical "/" rather than at
    itself — which is the *correct* shape, since search engines evaluate
    the canonical's signals, not the duplicate's. Before this fix, that
    correct implementation was reported as a missing self-reference.
    """
    duplicate = _page(
        url="https://x.com/index.html", normalized_url="https://x.com/index.html",
        canonical_url="https://x.com/",
        hreflang_tags=[
            _tag("en-IN", "https://x.com/"),  # points at the canonical, not self
            _tag("fr-FR", "https://x.com/fr/"),
        ],
    )
    findings = run_all_rules([duplicate], [])
    assert _find(findings, "SEO_INTL_001") is None


def test_canonical_awareness_does_not_excuse_a_genuinely_missing_reference() -> None:
    """The fix only accepts an hreflang entry aimed at the canonical — a page
    that canonicalizes somewhere and still omits any matching hreflang entry
    at all is still a real violation."""
    duplicate = _page(
        url="https://x.com/index.html", normalized_url="https://x.com/index.html",
        canonical_url="https://x.com/",
        hreflang_tags=[_tag("fr-FR", "https://x.com/fr/")],  # neither self nor canonical
    )
    findings = run_all_rules([duplicate], [])
    assert _find(findings, "SEO_INTL_001") is not None


# --------------------------------------------------------------------------
# SEO_INTL_002 — invalid language code
# --------------------------------------------------------------------------


def test_invalid_language_code_is_detected() -> None:
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[_tag("english", "https://x.com/en/")],
    )
    findings = run_all_rules([page], [])
    finding = _find(findings, "SEO_INTL_002")
    assert finding is not None
    assert finding.affected[0][1]["invalid_codes"] == ["english"]


def test_x_default_is_a_valid_code() -> None:
    page = _page(
        url="https://x.com/", normalized_url="https://x.com/",
        hreflang_tags=[_tag("x-default", "https://x.com/")],
    )
    findings = run_all_rules([page], [])
    assert _find(findings, "SEO_INTL_002") is None


# --------------------------------------------------------------------------
# SEO_INTL_003 — points to a broken or non-indexable page
# --------------------------------------------------------------------------


def test_hreflang_pointing_at_a_broken_page_is_detected() -> None:
    broken = _page(url="https://x.com/fr/", normalized_url="https://x.com/fr/", status_code=404)
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[_tag("en", "https://x.com/en/"), _tag("fr", "https://x.com/fr/")],
    )
    findings = run_all_rules([page, broken], [])
    assert _find(findings, "SEO_INTL_003") is not None


def test_hreflang_pointing_at_a_healthy_page_is_not_flagged() -> None:
    fr = _page(url="https://x.com/fr/", normalized_url="https://x.com/fr/")
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[_tag("en", "https://x.com/en/"), _tag("fr", "https://x.com/fr/")],
    )
    findings = run_all_rules([page, fr], [])
    assert _find(findings, "SEO_INTL_003") is None


# --------------------------------------------------------------------------
# SEO_INTL_004 — missing reciprocal (return) tag
# --------------------------------------------------------------------------


def test_a_non_reciprocal_alternate_is_detected() -> None:
    fr = _page(
        url="https://x.com/fr/", normalized_url="https://x.com/fr/",
        hreflang_tags=[_tag("fr", "https://x.com/fr/")],  # does not point back to en
    )
    en = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[_tag("en", "https://x.com/en/"), _tag("fr", "https://x.com/fr/")],
    )
    findings = run_all_rules([en, fr], [])
    assert _find(findings, "SEO_INTL_004") is not None


def test_reciprocal_alternates_are_not_flagged() -> None:
    fr = _page(
        url="https://x.com/fr/", normalized_url="https://x.com/fr/",
        hreflang_tags=[_tag("fr", "https://x.com/fr/"), _tag("en", "https://x.com/en/")],
    )
    en = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        hreflang_tags=[_tag("en", "https://x.com/en/"), _tag("fr", "https://x.com/fr/")],
    )
    findings = run_all_rules([en, fr], [])
    assert _find(findings, "SEO_INTL_004") is None


def test_a_return_tag_aimed_at_the_canonical_satisfies_reciprocity() -> None:
    """Mirrors the SEO_INTL_001 fix: the alternate (fr) reciprocates to the
    *canonical* homepage ("/"), not to the literal duplicate URL
    ("/index.html") that happened to link to it. That is the correct shape —
    fr has no way to know the duplicate URL exists, only the canonical one.
    """
    duplicate = _page(
        url="https://x.com/index.html", normalized_url="https://x.com/index.html",
        canonical_url="https://x.com/",
        hreflang_tags=[_tag("fr", "https://x.com/fr/")],
    )
    fr = _page(
        url="https://x.com/fr/", normalized_url="https://x.com/fr/",
        hreflang_tags=[_tag("fr", "https://x.com/fr/"), _tag("en", "https://x.com/")],  # points at canonical
    )
    findings = run_all_rules([duplicate, fr], [])
    assert _find(findings, "SEO_INTL_004") is None


def test_canonical_awareness_does_not_excuse_a_genuinely_broken_reciprocal_link() -> None:
    duplicate = _page(
        url="https://x.com/index.html", normalized_url="https://x.com/index.html",
        canonical_url="https://x.com/",
        hreflang_tags=[_tag("fr", "https://x.com/fr/")],
    )
    fr = _page(
        url="https://x.com/fr/", normalized_url="https://x.com/fr/",
        # Points back at neither the duplicate nor its canonical.
        hreflang_tags=[_tag("fr", "https://x.com/fr/"), _tag("de", "https://x.com/de/")],
    )
    findings = run_all_rules([duplicate, fr], [])
    assert _find(findings, "SEO_INTL_004") is not None


# --------------------------------------------------------------------------
# SEO_INTL_005 — html lang vs hreflang self-entry disagreement
# --------------------------------------------------------------------------


def test_conflicting_lang_declaration_is_detected() -> None:
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        html_lang="fr", hreflang_tags=[_tag("en", "https://x.com/en/")],
    )
    findings = run_all_rules([page], [])
    assert _find(findings, "SEO_INTL_005") is not None


def test_x_default_self_entry_is_exempt_from_the_conflict_check() -> None:
    page = _page(
        url="https://x.com/", normalized_url="https://x.com/",
        html_lang="en", hreflang_tags=[_tag("x-default", "https://x.com/")],
    )
    findings = run_all_rules([page], [])
    assert _find(findings, "SEO_INTL_005") is None


def test_agreeing_lang_declarations_are_not_flagged() -> None:
    page = _page(
        url="https://x.com/en/", normalized_url="https://x.com/en/",
        html_lang="en-US", hreflang_tags=[_tag("en", "https://x.com/en/")],
    )
    findings = run_all_rules([page], [])
    assert _find(findings, "SEO_INTL_005") is None


# --------------------------------------------------------------------------
# A site that doesn't use hreflang at all triggers none of these
# --------------------------------------------------------------------------


def test_no_hreflang_findings_when_the_site_does_not_use_hreflang() -> None:
    pages = [_page(url=f"https://x.com/{i}", normalized_url=f"https://x.com/{i}") for i in range(3)]
    findings = run_all_rules(pages, [])
    for rule_id in ("SEO_INTL_001", "SEO_INTL_002", "SEO_INTL_003", "SEO_INTL_004", "SEO_INTL_005"):
        assert _find(findings, rule_id) is None
