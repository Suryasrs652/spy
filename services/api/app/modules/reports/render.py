"""§54 report HTML rendering — the same evidence shown in the web UI,
rendered server-side for the PDF pipeline (app/modules/reports/pdf.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)

_SCORE_BANDS = [
    (90, "band-excellent"), (75, "band-good"), (60, "band-needs"), (40, "band-poor"), (0, "band-critical"),
]


def _band_class(score: float | None) -> str:
    if score is None:
        return ""
    for threshold, css_class in _SCORE_BANDS:
        if score >= threshold:
            return css_class
    return "band-critical"


def render_audit_report_html(*, audit, project, issues, recommendations) -> str:
    template = _env.get_template("audit_report.html.j2")
    evidence = audit.evidence or {}
    return template.render(
        audit=audit,
        project=project,
        issues=issues,
        recommendations=recommendations,
        evidence=evidence,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        band_class=_band_class(float(audit.spy_score) if audit.spy_score is not None else None),
    )
