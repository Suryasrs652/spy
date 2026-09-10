"""§23 Security rules."""
from __future__ import annotations

import re

from app.modules.seo.models import Severity
from app.modules.seo.rules.base import RuleContext, RuleFinding, rule

_VERSION_NUMBER_RE = re.compile(r"/\d+\.\d+")


@rule
def http_pages(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.crawled() if p.url.lower().startswith("http://")]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_001", "Security", Severity.HIGH,
        "Pages served over HTTP",
        "These pages are served without TLS, which browsers flag as insecure and which Google treats as a ranking negative.",
        "Serve the entire site over HTTPS and redirect all HTTP requests.",
        score_impact=-2 * len(affected), affected=affected,
    )


@rule
def mixed_content(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.crawled() if p.mixed_content]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_002", "Security", Severity.MEDIUM,
        "Mixed content",
        "These HTTPS pages load at least one resource over plain HTTP, which browsers may block or flag as insecure.",
        "Update all sub-resource URLs (images, scripts, stylesheets) to HTTPS.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def missing_hsts_header(ctx: RuleContext) -> RuleFinding | None:
    https_pages = [p for p in ctx.crawled() if p.url.lower().startswith("https://")]
    affected = [
        (p.id, {"url": p.url}) for p in https_pages
        if "strict-transport-security" not in (p.security_headers or {})
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_003", "Security", Severity.HIGH,
        "Missing HSTS header",
        "These HTTPS pages don't send a Strict-Transport-Security header, leaving a brief window where a "
        "visitor's first request could be intercepted over plain HTTP.",
        "Add a Strict-Transport-Security header (e.g. max-age=31536000; includeSubDomains) to all responses.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def missing_x_content_type_options(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url}) for p in ctx.crawled()
        if "x-content-type-options" not in (p.security_headers or {})
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_004", "Security", Severity.MEDIUM,
        "Missing X-Content-Type-Options header",
        "These pages don't send X-Content-Type-Options: nosniff, allowing browsers to MIME-sniff responses "
        "in a way that can enable certain content-injection attacks.",
        "Add the header \"X-Content-Type-Options: nosniff\" to all responses.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def missing_csp_header(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url}) for p in ctx.crawled()
        if "content-security-policy" not in (p.security_headers or {})
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_005", "Security", Severity.LOW,
        "Missing Content-Security-Policy header",
        "These pages don't send a Content-Security-Policy header, which is a meaningful layer of defense "
        "against cross-site scripting and data-injection attacks.",
        "Add a Content-Security-Policy header appropriate to the site's resources.",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def server_header_exposes_version(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        server = (p.security_headers or {}).get("server", "")
        if server and _VERSION_NUMBER_RE.search(server):
            affected.append((p.id, {"url": p.url, "server_header": server}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_007", "Security", Severity.LOW,
        "Server header exposes software version",
        "The Server response header reveals a specific software version, which can help an attacker target "
        "known vulnerabilities for that exact version.",
        "Configure the web server to omit or generalize the Server header (don't expose the version number).",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def insecure_cookie_flags(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        cookie = (p.security_headers or {}).get("set-cookie", "")
        if not cookie:
            continue
        lowered = cookie.lower()
        if "secure" not in lowered or "httponly" not in lowered:
            affected.append((p.id, {"url": p.url, "has_secure": "secure" in lowered, "has_httponly": "httponly" in lowered}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_008", "Security", Severity.MEDIUM,
        "Cookies missing Secure/HttpOnly flags",
        "These pages set cookies without both the Secure and HttpOnly flags, increasing the risk of cookie "
        "theft via network interception or cross-site scripting.",
        "Set the Secure and HttpOnly flags on all cookies that don't need JavaScript access.",
        score_impact=-1 * len(affected), affected=affected,
    )


@rule
def missing_x_frame_options(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url}) for p in ctx.crawled()
        if "x-frame-options" not in (p.security_headers or {})
        and "frame-ancestors" not in (p.security_headers or {}).get("content-security-policy", "")
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_009", "Security", Severity.MEDIUM,
        "Missing X-Frame-Options header",
        "These pages send no X-Frame-Options header (and no CSP frame-ancestors directive), leaving them "
        "embeddable in an iframe on another site — a clickjacking risk.",
        "Add \"X-Frame-Options: DENY\" or \"SAMEORIGIN\" (or a CSP frame-ancestors directive).",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def missing_referrer_policy(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url}) for p in ctx.crawled()
        if "referrer-policy" not in (p.security_headers or {})
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_010", "Security", Severity.LOW,
        "Missing Referrer-Policy header",
        "These pages don't send a Referrer-Policy header, leaving the browser's default behavior in place — "
        "which can leak the full URL (including any sensitive query parameters) to external sites.",
        "Add a Referrer-Policy header (e.g. \"strict-origin-when-cross-origin\").",
        score_impact=-0.25 * len(affected), affected=affected,
    )


@rule
def missing_permissions_policy(ctx: RuleContext) -> RuleFinding | None:
    affected = [
        (p.id, {"url": p.url}) for p in ctx.crawled()
        if "permissions-policy" not in (p.security_headers or {})
    ]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_011", "Security", Severity.INFO,
        "Missing Permissions-Policy header",
        "These pages don't send a Permissions-Policy header, missing a chance to explicitly restrict which "
        "browser features (camera, microphone, geolocation, etc.) the page and any embedded content can use.",
        "Add a Permissions-Policy header restricting unused browser features.",
        score_impact=-0.1 * len(affected), affected=affected,
    )


@rule
def cookie_missing_samesite(ctx: RuleContext) -> RuleFinding | None:
    affected = []
    for p in ctx.crawled():
        cookie = (p.security_headers or {}).get("set-cookie", "")
        if cookie and "samesite" not in cookie.lower():
            affected.append((p.id, {"url": p.url}))
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_012", "Security", Severity.LOW,
        "Cookies missing SameSite attribute",
        "These pages set cookies with no SameSite attribute, leaving the browser's default (increasingly "
        "restrictive, but inconsistent across browsers) rather than an explicit cross-site request forgery defense.",
        "Set an explicit SameSite attribute (Lax or Strict) on cookies.",
        score_impact=-0.5 * len(affected), affected=affected,
    )


@rule
def insecure_form_submission(ctx: RuleContext) -> RuleFinding | None:
    affected = [(p.id, {"url": p.url}) for p in ctx.crawled() if p.has_insecure_form_action]
    if not affected:
        return None
    return RuleFinding(
        "SEO_SEC_006", "Security", Severity.HIGH,
        "Form submits over plain HTTP",
        "These HTTPS pages contain a form whose action submits data over plain HTTP, which browsers flag as "
        "insecure and which can expose submitted data (including credentials) in transit.",
        "Update the form's action URL to use https://.",
        score_impact=-2 * len(affected), affected=affected,
    )
