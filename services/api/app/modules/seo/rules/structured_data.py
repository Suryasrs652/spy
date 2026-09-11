"""§23 Structured Data rules."""
from __future__ import annotations

from app.core.schema_org import ORGANIZATION_TYPES
from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule


@rule
def invalid_structured_data(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.crawled() if p.schema_invalid]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SCHEMA_001", "Structured Data", Severity.MEDIUM,
        "Invalid structured data",
        "These pages contain JSON-LD that fails to parse, so search engines can't read the structured data at all.",
        "Fix the JSON-LD syntax (validate with Google's Rich Results Test or Schema.org's validator).",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def no_structured_data(ctx: RuleContext) -> RuleFinding | None:
    crawled = ctx.crawled()
    affected = [(p.id, {"url": p.url}) for p in crawled if p.indexable and not p.has_schema]
    # Only flag this site-wide if *no* page anywhere has schema — a single
    # missing block on one page of a well-structured site isn't worth a
    # separate line item.
    if not affected or any(p.has_schema for p in crawled):
        return None
    return RuleFinding(
        "SEO_SCHEMA_002", "Structured Data", Severity.INFO,
        "No structured data found",
        "No JSON-LD structured data was found anywhere on the site, missing an opportunity for rich results and better AI/answer-engine readability.",
        "Add Organization, WebSite, and content-type-appropriate (Article/Product/FAQ) schema.",
        score_impact=-1, affected=affected,
    )


@rule
def missing_organization_schema(ctx: RuleContext) -> RuleFinding | None:
    crawled = ctx.crawled()
    has_org = any(ORGANIZATION_TYPES.intersection(p.schema_types or []) for p in crawled)
    if has_org or not crawled:
        return None
    homepage = min(crawled, key=lambda p: p.crawl_depth)
    return RuleFinding(
        "SEO_SCHEMA_003", "Structured Data", Severity.MEDIUM,
        "No Organization schema found",
        "No page declares Organization structured data, which helps search engines (and AI answer engines) "
        "understand who runs the site — important for both SEO and GEO/AEO.",
        "Add Organization schema (name, url, logo, sameAs social links) to the homepage.",
        score_impact=-1, affected=[(homepage.id, {"url": homepage.url})],
    )


@rule
def organization_schema_missing_fields(ctx: RuleContext) -> RuleFinding | None:
    required = ("name", "url")
    affected = []
    for p in ctx.crawled():
        for block in p.schema_blocks or []:
            block_type = block.get("@type")
            types = block_type if isinstance(block_type, list) else [block_type]
            if ORGANIZATION_TYPES.intersection(types):
                missing = [f for f in required if not block.get(f)]
                if missing:
                    affected.append((p.id, {"url": p.url, "missing_fields": missing}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_SCHEMA_004", "Structured Data", Severity.LOW,
        "Organization schema missing required fields",
        "The Organization structured data found is missing key fields (name and/or url), reducing how "
        "usefully search engines and AI systems can identify the business.",
        "Add the missing fields to the Organization schema block.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def missing_website_schema(ctx: RuleContext) -> RuleFinding | None:
    crawled = ctx.crawled()
    if not crawled or any("WebSite" in (p.schema_types or []) for p in crawled):
        return None
    homepage = min(crawled, key=lambda p: p.crawl_depth)
    return RuleFinding(
        "SEO_SCHEMA_008", "Structured Data", Severity.INFO,
        "No WebSite schema found",
        "No page declares WebSite structured data, missing an opportunity for a sitelinks search box and "
        "clearer site-identity signals in search results.",
        "Add WebSite schema (name, url, and optionally a SearchAction) to the homepage.",
        score_impact=-0.5, affected=[(homepage.id, {"url": homepage.url})],
    )


@rule
def missing_breadcrumb_schema(ctx: RuleContext) -> RuleFinding | None:
    crawled = ctx.crawled()
    deep_pages = [p for p in crawled if p.indexable and p.crawl_depth >= 2]
    if not deep_pages:
        return None
    has_breadcrumb = any("BreadcrumbList" in (p.schema_types or []) for p in crawled)
    if has_breadcrumb:
        return None
    return RuleFinding(
        "SEO_SCHEMA_005", "Structured Data", Severity.INFO,
        "No BreadcrumbList schema found",
        "This site has multi-level pages but no BreadcrumbList structured data, missing an opportunity for "
        "breadcrumb rich results in search.",
        "Add BreadcrumbList schema reflecting each page's position in the site hierarchy.",
        score_impact=-0.5, affected=[(p.id, {"url": p.url}) for p in deep_pages[:5]],
    )


@rule
def conflicting_organization_names(ctx: RuleContext) -> RuleFinding | None:
    names_seen: dict[str, list] = {}
    for p in ctx.crawled():
        for block in p.schema_blocks or []:
            block_type = block.get("@type")
            types = block_type if isinstance(block_type, list) else [block_type]
            if ORGANIZATION_TYPES.intersection(types) and block.get("name"):
                names_seen.setdefault(block["name"], []).append(p)
    distinct_names = list(names_seen.keys())
    if len(distinct_names) < 2:
        return None
    affected = [(p.id, {"url": p.url, "org_names": distinct_names}) for pages in names_seen.values() for p in pages]
    return RuleFinding(
        "SEO_SCHEMA_007", "Structured Data", Severity.MEDIUM,
        "Conflicting Organization names in structured data",
        f"Different pages declare Organization schema with different names ({', '.join(distinct_names[:5])}), "
        "an inconsistent entity signal that can confuse search engines and AI systems about who the site "
        "actually represents.",
        "Use the exact same Organization name consistently across every page's structured data.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def duplicate_schema_ids(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        ids_seen = []
        for block in p.schema_blocks or []:
            block_id = block.get("@id")
            if block_id:
                ids_seen.append(block_id)
        duplicates = {i for i in ids_seen if ids_seen.count(i) > 1}
        if duplicates:
            affected.append((p.id, {"url": p.url, "duplicate_ids": list(duplicates)}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_SCHEMA_006", "Structured Data", Severity.LOW,
        "Duplicate structured data @id values",
        "These pages declare the same @id on more than one structured-data block, which can confuse how "
        "search engines link related entities together.",
        "Give each structured-data block a unique @id.",
        score_impact=-0.25 * len(affected), affected=affected,
    )
