"""The competitor matrix and the advantages derived from it.

Pure functions over two plain profiles, so these tests need neither a
database nor a crawl. What they mostly guard is honesty: that a difference
too small to act on is not reported, that an unmeasured signal is not counted
as a gap, and that two things measured on different terms are never
subtracted from one another.
"""
from __future__ import annotations

from app.modules.competitors.matrix import (
    MATERIAL_GAP,
    MAX_ADVANTAGES,
    SIGNALS,
    build_profile,
    compare_all,
    find_advantages,
    size_comparison,
)


def _profile(name, *, id=None, version="spy-score-v2.0", pages=None, capped=False, **signals):
    """Signals are given as dotted keys with underscores, e.g.
    `geo__fact_density=61`, which reads better in a call than a dict."""
    evidence = {"seo": {"components": {}}, "aeo": {"components": {}}, "geo": {"components": {}}}
    scores = {}
    for key, value in signals.items():
        if "__" in key:
            section, component = key.split("__", 1)
            evidence[section]["components"][component] = value
        else:
            scores[key] = value
    if pages is not None:
        evidence["total_pages_scored"] = pages
    return build_profile(
        id=id or name.lower().replace(" ", "-"), name=name, score_version=version,
        scores=scores, evidence=evidence, pages_scored=pages, crawl_hit_its_limit=capped,
    )


# --------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------


def test_matrix_has_a_row_per_factor_and_a_column_per_competitor() -> None:
    you = _profile("Your site", seo_score=78, aeo_score=62, geo_score=54)
    rivals = [
        _profile("C1", id="c1", seo_score=84, aeo_score=71, geo_score=81),
        _profile("C2", id="c2", seo_score=67, aeo_score=58, geo_score=63),
        _profile("C3", id="c3", seo_score=91, aeo_score=83, geo_score=88),
    ]
    result = compare_all(you, rivals)

    seo = next(f for f in result.factors if f["key"] == "seo_score")
    assert seo["your_score"] == 78
    assert seo["competitor_scores"] == {"c1": 84, "c2": 67, "c3": 91}
    assert seo["best_competitor_id"] == "c3"
    assert seo["gap_to_best"] == -13.0


def test_a_missing_number_is_null_in_the_matrix_not_zero() -> None:
    """A competitor Spy has no ACRS for must not appear to have scored zero
    on it — that is the difference between "not measured" and "bad"."""
    you = _profile("Your site", seo_score=78, acrs_score=40)
    rivals = [_profile("C1", id="c1", seo_score=84)]
    acrs = next(f for f in compare_all(you, rivals).factors if f["key"] == "acrs_score")
    assert acrs["competitor_scores"] == {"c1": None}
    assert acrs["best_competitor_id"] is None
    assert acrs["gap_to_best"] is None


def test_a_competitor_scored_under_another_version_is_excluded_not_mixed_in() -> None:
    """`seo_score` meant the on-page score under v1 and a seven-component
    composite under v2. Putting both in one column produces a table that
    looks comparable and isn't."""
    you = _profile("Your site", seo_score=78)
    current = _profile("Current", id="cur", seo_score=84)
    stale = _profile("Stale", id="old", version="spy-score-v1.0", seo_score=95)

    result = compare_all(you, [current, stale])
    seo = next(f for f in result.factors if f["key"] == "seo_score")
    assert "old" not in seo["competitor_scores"]
    assert [x["competitor_id"] for x in result.not_comparable] == ["old"]
    assert "spy-score-v1.0" in result.not_comparable[0]["reason"]


# --------------------------------------------------------------------------
# Advantages
# --------------------------------------------------------------------------


def test_an_advantage_states_the_numbers_behind_it() -> None:
    you = _profile("Your site", geo__fact_density=10)
    rivals = [_profile("Rival", id="r1", geo__fact_density=61)]
    advantage = find_advantages(you, rivals)[0]

    assert advantage["key"] == "geo.fact_density"
    assert advantage["your_value"] == 10
    assert advantage["gap"] == 51.0
    assert advantage["leaders"] == ["Rival"]
    assert "61%" in advantage["finding"] and "10%" in advantage["finding"]
    assert advantage["what_to_do"]


def test_a_difference_too_small_to_act_on_is_not_reported() -> None:
    you = _profile("Your site", geo__fact_density=60)
    barely = [_profile("Rival", id="r1", geo__fact_density=60 + MATERIAL_GAP - 0.1)]
    clearly = [_profile("Rival", id="r1", geo__fact_density=60 + MATERIAL_GAP)]
    assert find_advantages(you, barely) == []
    assert len(find_advantages(you, clearly)) == 1


def test_a_signal_you_were_not_measured_on_is_not_a_gap() -> None:
    """`faq_implementation` is null when no page asks a question. Treating
    that as zero would manufacture a deficit against a competitor who simply
    writes a different kind of page."""
    you = _profile("Your site")  # no faq_implementation at all
    rivals = [_profile("Rival", id="r1", aeo__faq_implementation=90)]
    assert not any(a["key"] == "aeo.faq_implementation" for a in find_advantages(you, rivals))


def test_a_shared_advantage_outranks_one_rivals_quirk() -> None:
    """If every competitor does something and you don't, that is a pattern.
    One competitor doing it is that competitor."""
    you = _profile("Your site", geo__author_transparency=0, geo__source_attribution=0)
    rivals = [
        _profile("C1", id="c1", geo__author_transparency=60, geo__source_attribution=62),
        _profile("C2", id="c2", geo__author_transparency=60, geo__source_attribution=0),
        _profile("C3", id="c3", geo__author_transparency=60, geo__source_attribution=0),
    ]
    advantages = find_advantages(you, rivals)
    by_key = {a["key"]: a for a in advantages}
    assert by_key["geo.author_transparency"]["competitors_ahead"] == 3
    assert by_key["geo.source_attribution"]["competitors_ahead"] == 1
    assert advantages.index(by_key["geo.author_transparency"]) < advantages.index(
        by_key["geo.source_attribution"]
    )


def test_advantages_are_capped_so_the_list_stays_a_plan() -> None:
    you = _profile("Your site", **{s.key.replace(".", "__"): 0.0 for s in SIGNALS})
    rivals = [_profile("Rival", id="r1", **{s.key.replace(".", "__"): 90.0 for s in SIGNALS})]
    advantages = find_advantages(you, rivals)
    assert len(SIGNALS) > MAX_ADVANTAGES, "fixture no longer exercises the cap"
    assert len(advantages) == MAX_ADVANTAGES


def test_findings_state_a_difference_and_never_a_cause() -> None:
    """Spy has no ranking data for a competitor's site. A finding that claims
    one thing causes another is a claim this tool cannot support."""
    forbidden = ("outrank", "rank higher", "beats you in search", "because they")
    you = _profile("Your site", **{s.key.replace(".", "__"): 0.0 for s in SIGNALS})
    rivals = [_profile("Rival", id="r1", **{s.key.replace(".", "__"): 90.0 for s in SIGNALS})]
    for advantage in find_advantages(you, rivals):
        lowered = advantage["finding"].lower()
        for phrase in forbidden:
            assert phrase not in lowered, f"{advantage['key']} claims causation: {advantage['finding']}"


def test_leading_on_a_signal_produces_no_advantage() -> None:
    you = _profile("Your site", geo__fact_density=90)
    rivals = [_profile("Rival", id="r1", geo__fact_density=10)]
    assert find_advantages(you, rivals) == []


# --------------------------------------------------------------------------
# Size, and the crawl-ceiling trap
# --------------------------------------------------------------------------


def test_size_comparison_reports_a_real_difference() -> None:
    you = _profile("Your site", pages=40)
    rivals = [_profile("Rival", id="r1", pages=83)]
    size = size_comparison(you, rivals)
    assert size["your_pages"] == 40
    assert "43 more indexable pages" in size["finding"]


def test_a_capped_competitor_crawl_gives_a_floor_not_a_difference() -> None:
    """A benchmark that stopped at its own ceiling cannot say how much bigger
    the site is — subtracting would describe the crawl settings. It can say
    the site has at least that many pages, which is true and still useful.
    """
    you = _profile("Your site", pages=40)
    size = size_comparison(you, [_profile("Rival", id="r1", pages=100, capped=True)])
    assert "at least 100" in size["finding"]
    assert "60 more" not in size["finding"]


def test_size_is_silent_when_your_own_crawl_hit_its_ceiling() -> None:
    """Then your page count is a floor too, and neither side of the
    comparison is solid."""
    capped_you = _profile("Your site", pages=80, capped=True)
    assert size_comparison(capped_you, [_profile("Rival", id="r1", pages=100)]) is None


def test_size_is_silent_when_no_competitor_is_larger() -> None:
    you = _profile("Your site", pages=120)
    assert size_comparison(you, [_profile("Rival", id="r1", pages=30)]) is None


def test_findings_read_correctly_with_one_leader_and_with_several() -> None:
    """The leaders phrase is one name or a list, so every statement has to
    carry subject-verb agreement — "Superside phrase headings" is not a
    sentence. Any placeholder left unfilled shows up as a literal brace.
    """
    behind = {s.key.replace(".", "__"): 0.0 for s in SIGNALS}
    ahead = {s.key.replace(".", "__"): 90.0 for s in SIGNALS}
    you = _profile("Your site", **behind)

    solo = find_advantages(you, [_profile("Superside", id="c1", **ahead)])
    duo = find_advantages(
        you, [_profile("Superside", id="c1", **ahead), _profile("Vidsy", id="c2", **ahead)]
    )
    assert solo and duo

    for advantage in solo + duo:
        assert "{" not in advantage["finding"], advantage["finding"]
        assert "}" not in advantage["finding"], advantage["finding"]

    # The same signal, conjugated both ways.
    by_key_solo = {a["key"]: a["finding"] for a in solo}
    by_key_duo = {a["key"]: a["finding"] for a in duo}
    shared = set(by_key_solo) & set(by_key_duo)
    assert shared, "expected the same signals to surface in both runs"
    for key in shared:
        assert by_key_solo[key] != by_key_duo[key]
