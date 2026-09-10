"""§23 Images rules."""
from __future__ import annotations

from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule

_EXCESSIVE_IMAGE_COUNT = 100


@rule
def images_missing_alt(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "missing": p.images_missing_alt, "total": p.images_total})
        for p in ctx.crawled() if p.images_missing_alt > 0
    ]
    if not affected:
        return None
    total_missing = sum(a[1]["missing"] for a in affected)
    return RuleFinding(
        "SEO_IMG_001", "Images", Severity.MEDIUM,
        "Images missing alt text",
        "Images without alt text are invisible to screen readers and lose out on image-search relevance.",
        "Add a concise, descriptive alt attribute to every meaningful image.",
        score_impact=-0.5 * total_missing, affected=affected,
    )


@rule
def images_missing_dimensions(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "missing_dimensions": p.images_missing_dimensions})
        for p in ctx.crawled() if p.images_missing_dimensions > 0
    ]
    if not affected:
        return None
    total = sum(a[1]["missing_dimensions"] for a in affected)
    return RuleFinding(
        "SEO_IMG_002", "Images", Severity.MEDIUM,
        "Images missing width/height attributes",
        "Images without explicit width and height attributes cause layout shift as they load — a Core Web "
        "Vitals (CLS) problem that affects both user experience and ranking.",
        "Add explicit width and height attributes (or use aspect-ratio in CSS) to every image.",
        score_impact=-0.25 * total, affected=affected,
    )


@rule
def excessive_image_count(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "images_total": p.images_total})
        for p in ctx.crawled() if p.images_total > _EXCESSIVE_IMAGE_COUNT
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_IMG_004", "Images", Severity.LOW,
        "Excessive number of images on a page",
        f"These pages embed more than {_EXCESSIVE_IMAGE_COUNT} images, which typically means slow load "
        "times and a heavier crawl/render cost for very little added SEO value.",
        "Paginate large galleries, lazy-load below-the-fold images, or split the content across pages.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def images_generic_alt_text(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url, "generic_alt_count": p.images_generic_alt})
        for p in ctx.crawled() if p.images_generic_alt > 0
    ]
    if not affected:
        return None
    total = sum(a[1]["generic_alt_count"] for a in affected)
    return RuleFinding(
        "SEO_IMG_003", "Images", Severity.LOW,
        "Non-descriptive alt text",
        "Some images use alt text that's just a filename or a generic placeholder (e.g. \"image1.jpg\"), "
        "which gives no real information to screen readers or image search.",
        "Replace generic alt text with a short, specific description of each image.",
        score_impact=-0.15 * total, affected=affected,
    )
