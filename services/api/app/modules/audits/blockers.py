"""The five things most holding this site's score down.

Not the same list as `/recommendations`, and the difference matters. The
recommendation engine ranks rule findings by `impact x confidence x reach /
effort` — what to *do first*, cheapest-useful-thing-first. This ranks by
magnitude alone: what is costing the most, regardless of how hard it is to
fix. A site can have a tidy Action Center and still be held down by one thing
nobody has a rule for.

Which is the other reason this exists. Roughly a hundred rules cover
crawlability, metadata, links and markup, and **none of them fire on the
reasons a generative system ignores a site**. Nothing produces a finding for
"10% of your pages state a checkable figure" or "no page carries a byline" —
those live only in the AEO and GEO score components, where they move a number
and never reach the list of things to do. So blockers are drawn from both:

  - **rule findings**, which name specific pages, and
  - **score components**, which name the gaps no rule watches.

Both are converted to one honest currency: **points of the Overall Digital
Search Score this is costing you right now**. A rule finding's cost is the
deduction it actually contributed to its category, scaled by that category's
weight within SEO and SEO's weight within the overall. A score component's is
how far below 100 it sits, scaled the same way through its own section. That
makes a metadata issue and a fact-density gap genuinely comparable instead of
merely adjacent in a list.

Two things it refuses to do:

  - **Report an unmeasured component as a blocker.** `faq_implementation` is
    null when no page asks a question; original information gain is always
    null. Neither is a deficit, and neither is something to fix.
  - **Report the same problem twice.** Several components overlap a rule that
    already covers the same ground — no Organization schema is both
    `SEO_SCHEMA_003` and a low `entity_recognition`. When the rule fired, the
    rule wins: it can name the pages.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.scoring.spy_score import (
    AEO_COMPONENT_WEIGHTS,
    CATEGORY_TO_SEO_COMPONENT,
    GEO_COMPONENT_WEIGHTS,
    SEARCH_SCORE_WEIGHTS,
    SEO_COMPONENT_WEIGHTS,
    SEVERITY_DEDUCTION,
)

# A component at or above this is working well enough that the next point is
# not where anyone's afternoon should go.
HEALTHY_SIGNAL = 70.0

# Below this many points of the overall score, a blocker is not blocking.
MATERIAL_POINTS = 0.25

TOP_N = 5

# Effort per rule category, matching the recommendation engine's estimates so
# one report does not call the same fix cheap in one place and dear in another.
_CATEGORY_EFFORT = {
    "Crawlability": 6, "Indexability": 4, "Metadata": 2, "Content": 7,
    "Links": 4, "Images": 2, "Structured Data": 5, "Security": 6,
    "International": 5,
}

EFFORT_LABELS = {1: "Low", 2: "Low", 3: "Low", 4: "Medium", 5: "Medium", 6: "Medium"}


def effort_label(effort: int) -> str:
    return EFFORT_LABELS.get(effort, "High")


@dataclass
class Blocker:
    key: str
    title: str
    detail: str
    what_to_do: str
    # RULE — a specific finding naming specific pages.
    # SIGNAL — a score component no rule watches.
    source: str
    points_recoverable: float
    effort: int
    effort_label: str
    affected_pages: int | None = None
    rule_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "detail": self.detail,
            "what_to_do": self.what_to_do, "source": self.source,
            "points_recoverable": round(self.points_recoverable, 2),
            "effort": self.effort, "effort_label": self.effort_label,
            "affected_pages": self.affected_pages, "rule_id": self.rule_id,
        }


@dataclass(frozen=True)
class SignalBlocker:
    """A weakness that lives only in a score component.

    `title` takes `{short}` — the share of pages *not* doing the thing, which
    is what a reader wants ("61% of pages lack…" rather than "answerability is
    39"). `covered_by` names the rule ids that already describe the same
    problem; if one of them fired, this is dropped so the reader sees the
    version that can name pages.
    """

    section: str
    component: str
    title: str
    detail: str
    what_to_do: str
    effort: int
    covered_by: tuple[str, ...] = ()


SIGNAL_BLOCKERS: list[SignalBlocker] = [
    SignalBlocker(
        "geo", "fact_density",
        "{short} of pages state fewer than two checkable figures",
        "Pages that describe capabilities without a single figure give a generative system nothing "
        "to quote and nothing to attribute. This is the most common reason a technically clean site "
        "is never cited.",
        "Add concrete numbers to the pages that matter — sample sizes, turnaround times, prices, "
        "measured results — and say where each came from.",
        effort=7,
    ),
    SignalBlocker(
        "geo", "author_transparency",
        "{short} of pages have no named author",
        "Unattributed content is a weaker citation candidate than identical content with a real "
        "person behind it. Nothing in the rule engine flags this, so it tends to go unnoticed "
        "indefinitely.",
        "Put a byline and a two-line bio on anything that makes a claim.",
        effort=4,
    ),
    SignalBlocker(
        "aeo", "answerability",
        "{short} of pages carry no extractable answer",
        "This counts a page only when it both poses something — a question heading, a definition "
        "list, a table — and carries a paragraph that survives being lifted away from its "
        "neighbours. Either half alone is not an answer, which is why adding headings without "
        "rewriting the prose beneath them does not move it.",
        "Under each question heading, write one paragraph that answers it without depending on the "
        "sentences around it. Adding headings alone does not move this.",
        effort=6,
    ),
    SignalBlocker(
        "aeo", "question_coverage",
        "{short} of pages phrase nothing as a question",
        "Questions are the literal unit an answer engine matches against. Prose organised around "
        "topics rather than questions is harder to match, whatever it says.",
        "Use the questions people actually ask as headings, in their words.",
        effort=5,
    ),
    SignalBlocker(
        "aeo", "passage_extraction",
        "{short} of prose does not survive being quoted out of context",
        "A paragraph opening with \"This means that\" or \"As a result\" cannot be lifted — it "
        "depends on the sentence before it, which the quoting system will not carry.",
        "Open paragraphs with the subject rather than with a connective.",
        effort=6,
    ),
    SignalBlocker(
        "aeo", "structured_answers",
        "{short} of pages use no list, table or definition",
        "These are the shapes a machine extracts most reliably. Dense prose is the shape it "
        "extracts least reliably.",
        "Convert comparisons into tables, processes into numbered lists, and terms into short "
        "definitions.",
        effort=4,
    ),
    SignalBlocker(
        "aeo", "faq_implementation",
        "{short} of the pages that ask questions do not mark them up",
        "The content is already written. Without FAQPage or QAPage schema a machine has to infer "
        "that a heading is a question and the text beneath it is the answer.",
        "Add FAQPage or QAPage schema to the Q&A blocks that already exist — markup only, no "
        "writing.",
        effort=3,
    ),
    SignalBlocker(
        "geo", "source_attribution",
        "{short} of pages cite no outside source",
        "Linking to what you drew on is the only citation signal that survives a crawl. Sitewide "
        "footer links are excluded from this and do not help.",
        "Link to the studies, standards, datasets or documentation behind each claim.",
        effort=4,
    ),
    # geo.citation_readiness is deliberately absent: it is the same
    # measurement as aeo.passage_extraction above, shared between the two
    # sections. Listing both would report one problem twice under two names.
    SignalBlocker(
        "geo", "topical_authority",
        "The site covers its subject thinly ({value} on depth and breadth)",
        "Depth without breadth is one good essay; breadth without depth is a sitemap of stubs. "
        "This measures the on-site half only — whether the wider web treats the site as an "
        "authority is not measured.",
        "Fewer, longer pages on the subjects you want to be known for, rather than more pages.",
        effort=8,
        covered_by=("SEO_CONTENT_001",),
    ),
    SignalBlocker(
        "geo", "entity_recognition",
        "The site does not clearly declare what it is ({value})",
        "Without a declared entity a generative system has to guess who it is citing, and mostly "
        "declines to.",
        "Add Organization schema to the homepage and declare the subject of each page — Service, "
        "Product or Person.",
        effort=3,
        covered_by=("SEO_SCHEMA_002", "SEO_SCHEMA_003"),
    ),
    SignalBlocker(
        "geo", "knowledge_graph_signals",
        "The declared entity is missing {short} of what a knowledge graph needs",
        "@id, sameAs, url and logo are what let an engine resolve this entity to a real one rather "
        "than a name on a page.",
        "Add @id and sameAs to the Organization block, pointing sameAs at profiles the business "
        "actually controls.",
        effort=3,
        covered_by=("SEO_SCHEMA_004",),
    ),
    SignalBlocker(
        "geo", "brand_consistency",
        "The site calls itself different things in different places ({value} agree)",
        "A brand that names itself inconsistently is an ambiguous entity, and ambiguity costs more "
        "than a missing optional field.",
        "Pick one name and use it in every markup block, even where the visible branding varies.",
        effort=2,
        covered_by=("SEO_SCHEMA_007",),
    ),
    SignalBlocker(
        "aeo", "schema_support",
        "{short} of pages carry no structured data",
        "Schema is how a page tells a machine what it is rather than leaving it to be inferred.",
        "Add JSON-LD to the templates that lack it — a template change, not a content programme.",
        effort=3,
        covered_by=("SEO_SCHEMA_002",),
    ),
    SignalBlocker(
        "aeo", "entity_clarity",
        "{short} of pages do not say what they are about",
        "A page whose subject is only implied has to be classified by guesswork.",
        "Declare a type per page — Article, Service, Product — alongside the organization.",
        effort=3,
        covered_by=("SEO_SCHEMA_002", "SEO_SCHEMA_003"),
    ),
]

_SECTION_WEIGHTS = {"aeo": AEO_COMPONENT_WEIGHTS, "geo": GEO_COMPONENT_WEIGHTS}


def _pct(value: float) -> str:
    return f"{value:.0f}%"


def _rule_blockers(issues, *, total_pages: int, seo_components: dict) -> list[Blocker]:
    """One blocker per finding, costed at what it actually took off the score.

    A category score floors at 0, so once deductions pass 100 the extra ones
    cost nothing. Attributing each finding its raw deduction would then claim
    more points are recoverable than exist. Each finding gets its share of the
    deduction the category *realised* instead.
    """
    by_component: dict[str, list] = {}
    for issue in issues:
        component = CATEGORY_TO_SEO_COMPONENT.get(issue.category)
        if component:
            by_component.setdefault(component, []).append(issue)

    blockers = []
    for component, component_issues in by_component.items():
        raw = {
            issue.rule_id: SEVERITY_DEDUCTION.get(issue.severity, 0)
            * (issue.affected_count / max(total_pages, 1))
            for issue in component_issues
        }
        raw_total = sum(raw.values())
        if raw_total <= 0:
            continue

        score = seo_components.get(component)
        realised = (100.0 - score) if score is not None else min(raw_total, 100.0)
        scale = realised / raw_total if raw_total else 0.0

        for issue in component_issues:
            points = (
                raw[issue.rule_id] * scale
                * SEO_COMPONENT_WEIGHTS[component]
                * SEARCH_SCORE_WEIGHTS["seo"]
            )
            if points < MATERIAL_POINTS:
                continue
            effort = _CATEGORY_EFFORT.get(issue.category, 5)
            blockers.append(
                Blocker(
                    key=issue.rule_id,
                    title=f"{issue.affected_count} page{'s' if issue.affected_count != 1 else ''}: "
                          f"{issue.title[0].lower()}{issue.title[1:]}",
                    detail=issue.description,
                    what_to_do=issue.recommendation,
                    source="RULE",
                    points_recoverable=points,
                    effort=effort,
                    effort_label=effort_label(effort),
                    affected_pages=issue.affected_count,
                    rule_id=issue.rule_id,
                )
            )
    return blockers


def _signal_blockers(evidence: dict, fired_rule_ids: set[str]) -> list[Blocker]:
    blockers = []
    for spec in SIGNAL_BLOCKERS:
        if any(rule_id in fired_rule_ids for rule_id in spec.covered_by):
            # A rule already describes this, and it can name the pages.
            continue

        section = evidence.get(spec.section) or {}
        components = section.get("components") or {}
        value = components.get(spec.component)
        if value is None or value >= HEALTHY_SIGNAL:
            # None means not measured, which is not a deficit.
            continue

        weights = section.get("weights_used") or _SECTION_WEIGHTS[spec.section]
        weight = weights.get(spec.component)
        if not weight:
            continue

        points = (100.0 - value) * weight * SEARCH_SCORE_WEIGHTS[spec.section]
        if points < MATERIAL_POINTS:
            continue

        blockers.append(
            Blocker(
                key=f"{spec.section}.{spec.component}",
                title=spec.title.format(short=_pct(100.0 - value), value=_pct(value)),
                detail=spec.detail,
                what_to_do=spec.what_to_do,
                source="SIGNAL",
                points_recoverable=points,
                effort=spec.effort,
                effort_label=effort_label(spec.effort),
            )
        )
    return blockers


def find_blockers(*, audit, issues, top_n: int = TOP_N) -> list[dict]:
    """The `top_n` things costing this site the most score, from both the rule
    findings and the score components no rule watches."""
    evidence = audit.evidence or {}
    seo_components = (evidence.get("seo") or {}).get("components") or {}
    total_pages = evidence.get("total_pages_scored") or 1
    fired = {issue.rule_id for issue in issues}

    blockers = _rule_blockers(issues, total_pages=total_pages, seo_components=seo_components)
    blockers += _signal_blockers(evidence, fired)
    blockers.sort(key=lambda b: b.points_recoverable, reverse=True)
    return [b.as_dict() for b in blockers[:top_n]]


# --------------------------------------------------------------------------


# "Opportunities" is the spec's name for the tail: real findings, none of them
# urgent. Kept distinct from Medium so the top three counts stay the ones a
# reader acts on.
OPPORTUNITY_SEVERITIES = ("LOW", "INFO")


def count_issues(issues) -> dict:
    """Issues by severity, with the pages behind each.

    Both numbers are reported because one issue affecting 70 pages and 70
    issues affecting one page each look identical otherwise, and they are not
    the same site.
    """
    counts = {
        "critical": {"issues": 0, "pages": 0},
        "high": {"issues": 0, "pages": 0},
        "medium": {"issues": 0, "pages": 0},
        "opportunities": {"issues": 0, "pages": 0},
    }
    for issue in issues:
        severity = (issue.severity or "").upper()
        if severity in OPPORTUNITY_SEVERITIES:
            bucket = "opportunities"
        elif severity in ("CRITICAL", "HIGH", "MEDIUM"):
            bucket = severity.lower()
        else:
            continue
        counts[bucket]["issues"] += 1
        counts[bucket]["pages"] += issue.affected_count or 0
    return counts
