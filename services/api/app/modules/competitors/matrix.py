"""Your site against every competitor at once, and what the differences are.

Two things come out of here. The **matrix** is the side-by-side table: a row
per factor, a column per site. The **advantages** are the interesting half —
the specific, measured signals where competitors are ahead, each with the
numbers behind it, ordered by how much of a gap it is and how many rivals
share it.

The point of the second half is that "create better content" is not advice.
"Two of your three competitors state checkable figures on more than half their
pages; you do on 10%" is, because someone can act on it tomorrow and check
afterwards whether it moved.

## What this deliberately does not say

It does not say these differences are *why* anyone outranks anyone. Spy reads
markup and prose; it has no ranking data for a competitor's site and no way to
attribute a position to a cause. What it can say is where two sites measurably
differ on signals that search and generative systems are documented to use,
which is a different and honest claim. Every phrase in here is written to
survive that distinction.

Two more traps this guards:

  - **Different crawl depths.** A competitor benchmark stops at
    MAX_COMPETITOR_URLS; your own audit can go far deeper. Raw page counts
    across two different ceilings are an artifact of the ceilings, so a
    size comparison is only reported when neither crawl hit one.
  - **Different score versions.** A competitor benchmarked under an older
    scoring version is not comparable to a current audit, for the same reason
    two audits under different versions are not (§22). It is listed as
    not-comparable rather than silently placed in the table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

# Below this, a difference is noise rather than a finding. Both sides are
# percentages of pages or 0-100 scores, so one threshold covers both.
MATERIAL_GAP = 5.0

# How many advantages to report. Past this the list stops being a plan.
MAX_ADVANTAGES = 8

# When two competitors are further apart than this, no single number is true
# of both, so the finding reports their range instead of a midpoint. Without
# it, Superside at 77% and Vidsy at 17% produced "Superside and Vidsy link out
# to a source on 47% of pages" — a figure neither of them hits, asserted about
# both by name.
SPREAD_TOLERANCE = 10.0


@dataclass(frozen=True)
class SiteProfile:
    """One site's numbers, flattened so the matrix can read any of them by a
    single dotted key regardless of whether it came from a column or from the
    evidence blob."""

    id: str | None
    name: str
    score_version: str | None
    values: dict[str, float | None]
    pages_scored: int | None = None
    crawl_hit_its_limit: bool = False

    def get(self, key: str) -> float | None:
        return self.values.get(key)


def _section(evidence: dict, name: str) -> dict:
    section = evidence.get(name) or {}
    return section if isinstance(section, dict) else {}


def _components(evidence: dict, name: str) -> dict:
    components = _section(evidence, name).get("components") or {}
    return components if isinstance(components, dict) else {}


def _as_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_profile(
    *,
    id: str | None,
    name: str,
    score_version: str | None,
    scores: dict,
    evidence: dict,
    pages_scored: int | None = None,
    crawl_hit_its_limit: bool = False,
) -> SiteProfile:
    """`scores` is the stored columns; `evidence` the JSONB blob. Everything
    lands in one flat namespace: `seo_score`, `aeo.fact_density`, and so on.
    """
    evidence = evidence or {}
    values: dict[str, float | None] = {k: _as_float(v) for k, v in scores.items()}
    for section in ("seo", "aeo", "geo"):
        for component, value in _components(evidence, section).items():
            values[f"{section}.{component}"] = _as_float(value)
    for component, value in _section(evidence, "acrs").items():
        values[f"acrs.{component}"] = _as_float(value)
    return SiteProfile(
        id=id, name=name, score_version=score_version, values=values,
        pages_scored=pages_scored, crawl_hit_its_limit=crawl_hit_its_limit,
    )


# --------------------------------------------------------------------------
# The matrix itself
# --------------------------------------------------------------------------

# Kept short on purpose. This is the table someone reads first; the detailed
# signal-by-signal differences belong in the advantages below it.
MATRIX_FACTORS: list[tuple[str, str]] = [
    ("spy_score", "Overall"),
    ("seo_score", "SEO"),
    ("aeo_score", "AEO"),
    ("geo_score", "GEO"),
    ("acrs_score", "AI citation readiness"),
    ("aeo.schema_support", "Schema"),
    ("geo.topical_authority", "Topical authority"),
    ("geo.entity_recognition", "Entity strength"),
]


def build_matrix(you: SiteProfile, competitors: list[SiteProfile]) -> list[dict]:
    rows = []
    for key, label in MATRIX_FACTORS:
        your_value = you.get(key)
        competitor_values = {c.id: c.get(key) for c in competitors}
        scored = [(cid, v) for cid, v in competitor_values.items() if v is not None]
        best_id, best_value = max(scored, key=lambda kv: kv[1]) if scored else (None, None)
        rows.append(
            {
                "key": key,
                "label": label,
                "your_score": your_value,
                "competitor_scores": competitor_values,
                "best_competitor_id": best_id,
                "gap_to_best": (
                    round(your_value - best_value, 2)
                    if your_value is not None and best_value is not None
                    else None
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Where they are ahead
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    # One sentence, with {leaders}, {theirs} and {yours} filled in. Written so
    # it states a measured difference and never a cause.
    #
    # `{s}` goes on the verb and carries subject-verb agreement: the leaders
    # phrase is one name or several, so "Superside phrase headings" has to
    # become "phrases" without writing the sentence twice. Keep the verbs
    # regular — `{s}` cannot turn "carry" into "carries". `{possessive}` is
    # the same phrase with an apostrophe, for statements with no verb on it.
    statement: str
    remedy: str
    # Multiplies the gap when ranking. Signals that are cheap to act on and
    # unambiguous outrank ones that need a content programme.
    leverage: float = 1.0


# Read in this order when gaps tie; the order itself carries no other meaning.
SIGNALS: list[Signal] = [
    Signal(
        "aeo.schema_support", "Schema coverage",
        "Structured data appears on {theirs} of {possessive} pages, against your {yours}.",
        "Add JSON-LD to the templates that lack it — Article, Service or Product as the page warrants. "
        "It is a template change, not a content programme.",
        leverage=1.3,
    ),
    Signal(
        "geo.knowledge_graph_signals", "Knowledge-graph signals",
        "{leaders} give{s} a knowledge graph {theirs} of the fields it needs to resolve their entity "
        "(@id, sameAs, url, logo); you give {yours}.",
        "Add @id and sameAs to the Organization block on the homepage, pointing sameAs at profiles "
        "the business actually controls.",
        leverage=1.3,
    ),
    Signal(
        "aeo.faq_implementation", "FAQ and Q&A markup",
        "Of the pages that pose questions, {leaders} mark{s} up {theirs} with FAQPage or QAPage schema; "
        "you mark up {yours}.",
        "Mark up the Q&A blocks that already exist. The content is written; only the markup is missing.",
        leverage=1.3,
    ),
    Signal(
        "geo.entity_recognition", "Entity strength",
        "{leaders} score{s} {theirs} on declaring what their pages are about; you score {yours}.",
        "Declare the organization on the homepage and the subject of each page — Service, Product "
        "or Person — rather than leaving the page type implicit.",
        leverage=1.2,
    ),
    Signal(
        "geo.author_transparency", "Named authorship",
        "{leaders} attribute{s} {theirs} of pages to a named author; you attribute {yours}.",
        "Put a real byline and a short bio on anything that makes a claim. Generative systems weigh "
        "attributable content more heavily, and this is a content decision rather than an engineering one.",
        leverage=1.1,
    ),
    Signal(
        "geo.fact_density", "Citeable statistics",
        "{leaders} state{s} checkable figures on {theirs} of pages; you do on {yours}.",
        "Add concrete numbers — sample sizes, timings, prices, measured results — to the pages that "
        "currently only describe capabilities.",
        leverage=1.1,
    ),
    Signal(
        "aeo.answerability", "Direct answers",
        "{leaders} answer{s} a posed question in a passage that stands on its own on {theirs} of pages; "
        "you do on {yours}.",
        "Under each question heading, put one paragraph that answers it without depending on the "
        "sentences around it. Adding headings alone does not move this.",
        leverage=1.1,
    ),
    Signal(
        "geo.source_attribution", "Cited outside sources",
        "{leaders} link{s} out to a source on {theirs} of pages; you do on {yours}.",
        "Link to the studies, standards or data you are drawing on. Sitewide footer links do not count "
        "and are excluded from this measurement.",
    ),
    Signal(
        "aeo.question_coverage", "Question coverage",
        "{leaders} phrase{s} headings as questions on {theirs} of pages; you do on {yours}.",
        "Use the questions people actually ask as headings, in their words rather than yours.",
    ),
    Signal(
        "aeo.structured_answers", "Lists, tables and definitions",
        "{leaders} break{s} content into lists, tables or definition lists on {theirs} of pages; "
        "you do on {yours}.",
        "Convert dense prose into the shapes a machine lifts cleanly — comparison tables, step lists, "
        "short definitions.",
    ),
    Signal(
        "geo.citation_readiness", "Quotable passages",
        "{leaders} write{s} paragraphs that survive being quoted out of context {theirs} of the time; "
        "yours do {yours} of the time.",
        "Open paragraphs with the subject rather than with 'This means that' or 'As a result'.",
    ),
    Signal(
        "geo.topical_authority", "Content depth",
        "{leaders} cover{s} their subject across substantially more long-form pages ({theirs} against "
        "your {yours} on Spy's depth-and-breadth measure).",
        "Fewer, longer pages on the subjects that matter, rather than more pages.",
        leverage=0.9,
    ),
    Signal(
        "geo.brand_consistency", "Brand name consistency",
        "{leaders} use{s} one name consistently across their markup ({theirs}); yours agree {yours} "
        "of the time.",
        "Pick one name and use it in every schema block, even where the visible branding varies.",
    ),
    Signal(
        "seo.technical", "Technical foundations",
        "{leaders} score{s} {theirs} on crawlability, indexability and security headers; you score {yours}.",
        "Work the technical issues list — sitewide header and canonical fixes are usually a handful of "
        "lines in the host config.",
        leverage=1.2,
    ),
    Signal(
        "seo.internal_links", "Internal linking",
        "{leaders} score{s} {theirs} on internal link health; you score {yours}.",
        "Link supporting pages from the pages that already have authority, and fix orphans and dead ends.",
    ),
    Signal(
        "seo.performance", "Response speed",
        "{leaders} respond{s} faster ({theirs} against your {yours} on Spy's response-time measure).",
        "Investigate server response times before optimising assets; this measures time to first byte, "
        "not render.",
    ),
]


def _fmt(value: float) -> str:
    return f"{value:.0f}%"


def _fmt_theirs(values: list[float]) -> str:
    """One competitor's figure, or a range when several disagree.

    The midpoint of two distant values describes neither of them. A reader who
    acts on "both do 47%" and then looks at the two sites finds 77% and 17%,
    and stops trusting the rest of the report — correctly.
    """
    low, high = min(values), max(values)
    if high - low <= SPREAD_TOLERANCE:
        return _fmt(median(values))
    return f"{low:.0f}–{high:.0f}%"


def _possessive(names: list[str]) -> str:
    """Superside -> Superside's; Superside and Vidsy -> Superside and Vidsy's.
    The apostrophe attaches to the last name either way."""
    joined = _join(names)
    return joined + ("'" if joined.endswith("s") else "'s")


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])} and {names[-1]}"


def find_advantages(you: SiteProfile, competitors: list[SiteProfile]) -> list[dict]:
    """The signals where competitors measurably lead, worst gap first.

    A gap counts only when it clears MATERIAL_GAP — two sites within a few
    points of each other are the same site as far as this is concerned, and
    padding the list with noise is how a report stops being read.
    """
    advantages = []

    for signal in SIGNALS:
        your_value = you.get(signal.key)
        if your_value is None:
            # Not measured on your site: there is no gap to state, and
            # treating it as zero would invent one.
            continue

        ahead = [
            (c, value)
            for c in competitors
            if (value := c.get(signal.key)) is not None and value - your_value >= MATERIAL_GAP
        ]
        if not ahead:
            continue

        their_values = [value for _c, value in ahead]
        typical = median(their_values)
        gap = typical - your_value

        leaders = [c.name for c, _v in ahead]
        advantages.append(
            {
                "key": signal.key,
                "label": signal.label,
                "your_value": round(your_value, 1),
                "competitor_values": {c.id: round(v, 1) for c, v in ahead},
                "leaders": leaders,
                "competitors_ahead": len(ahead),
                "gap": round(gap, 1),
                "finding": signal.statement.format(
                    leaders=_join(leaders), theirs=_fmt_theirs(their_values), yours=_fmt(your_value),
                    s="s" if len(leaders) == 1 else "",
                    possessive=_possessive(leaders),
                ),
                "what_to_do": signal.remedy,
                # Shared advantages matter more than one rival's quirk, and a
                # bigger gap matters more than a smaller one.
                "_rank": gap * signal.leverage * (1 + 0.5 * (len(ahead) - 1)),
            }
        )

    advantages.sort(key=lambda a: a["_rank"], reverse=True)
    for advantage in advantages:
        del advantage["_rank"]
    return advantages[:MAX_ADVANTAGES]


def size_comparison(you: SiteProfile, competitors: list[SiteProfile]) -> dict | None:
    """How much more of their site there is than of yours.

    The trap: a competitor benchmark stops at a lower ceiling than a full
    audit. Subtracting two page counts when either crawl hit its limit gives
    a number that describes the crawl settings, not the sites.

    But silence throws away something real. A crawl that stopped at its limit
    still proves the site has *at least* that many pages, so a capped
    competitor gets a floor ("at least 100") rather than a difference, and an
    uncapped one gets the exact gap. Either way the sentence is true.
    """
    if you.pages_scored is None or you.crawl_hit_its_limit:
        # Your own crawl was truncated, so your page count is a floor too and
        # there is no side of this comparison that is solid.
        return None

    bigger = [
        c for c in competitors
        if c.pages_scored is not None and c.pages_scored > you.pages_scored
    ]
    if not bigger:
        return None

    largest = max(bigger, key=lambda c: c.pages_scored)
    if largest.crawl_hit_its_limit:
        finding = (
            f"{largest.name} has at least {largest.pages_scored} indexable pages against your "
            f"{you.pages_scored} — the benchmark crawl stopped at its own limit, so the real "
            f"number is higher than that."
        )
    else:
        finding = (
            f"{largest.name} publishes {largest.pages_scored - you.pages_scored} more indexable "
            f"pages than you ({largest.pages_scored} against {you.pages_scored})."
        )

    return {
        "your_pages": you.pages_scored,
        "competitor_pages": {
            c.id: c.pages_scored for c in competitors if c.pages_scored is not None
        },
        "finding": finding,
        "what_to_do": (
            "Look at what those pages cover before adding any. Breadth only helps where it is depth on "
            "subjects you want to be known for."
        ),
    }


@dataclass
class MatrixResult:
    factors: list[dict] = field(default_factory=list)
    advantages: list[dict] = field(default_factory=list)
    size: dict | None = None
    not_comparable: list[dict] = field(default_factory=list)


def compare_all(you: SiteProfile, competitors: list[SiteProfile]) -> MatrixResult:
    comparable, excluded = [], []
    for competitor in competitors:
        if competitor.score_version and you.score_version and competitor.score_version != you.score_version:
            excluded.append(
                {
                    "competitor_id": competitor.id,
                    "name": competitor.name,
                    "reason": (
                        f"benchmarked under {competitor.score_version} while your audit is "
                        f"{you.score_version} — the same field means different things across "
                        f"versions. Refresh this competitor to compare."
                    ),
                }
            )
        else:
            comparable.append(competitor)

    return MatrixResult(
        factors=build_matrix(you, comparable),
        advantages=find_advantages(you, comparable),
        size=size_comparison(you, comparable),
        not_comparable=excluded,
    )
