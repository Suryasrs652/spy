"""§23-§25 SEO rule engine — public entry point.

Rules live one file per §23 category; each category module registers its
rules into the shared registry (app.modules.seo.rules.base) purely via
import side-effect, so importing this package is what makes `run_all_rules`
actually see every rule. `RuleFinding`/`run_all_rules` are the only names
other modules should import from here.
"""
from __future__ import annotations

from app.modules.seo.rules.base import (
    DEFAULT_THRESHOLDS,
    RuleContext,
    RuleFinding,
    run_all_rules,
)

# Import order doesn't matter for correctness (registration is additive),
# but keeping it in §23's own category order makes the registry's iteration
# order predictable for anyone reading findings output.
from app.modules.seo.rules import (  # noqa: E402,F401 - import-for-registration
    crawlability,
    indexability,
    metadata,
    content,
    links,
    images,
    structured_data,
    security,
    international,
)

__all__ = ["RuleFinding", "RuleContext", "DEFAULT_THRESHOLDS", "run_all_rules"]
