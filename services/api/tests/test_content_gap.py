"""§144/M5 content-gap term extraction — pure functions."""
from __future__ import annotations

from app.modules.competitors.content_gap import compute_gap_terms, extract_top_terms


def test_extracts_significant_terms_ignoring_stopwords() -> None:
    terms = extract_top_terms(["The Best Widget Reviews", "Widget Pricing Guide"])
    assert "widget" in terms
    assert "reviews" in terms
    assert "pricing" in terms
    assert "best" not in terms  # stopword
    assert "the" not in terms  # too short after filtering / stopword


def test_ignores_none_and_empty_strings() -> None:
    terms = extract_top_terms([None, "", "Widget Reviews"])
    assert "widget" in terms


def test_orders_by_frequency() -> None:
    terms = extract_top_terms(["widget widget widget gadget"])
    assert terms[0] == "widget"


def test_gap_terms_only_include_competitor_exclusive_terms() -> None:
    gap = compute_gap_terms(your_terms=["widget", "pricing"], competitor_terms=["widget", "reviews", "comparison"])
    assert gap == ["reviews", "comparison"]


def test_no_gap_when_full_overlap() -> None:
    gap = compute_gap_terms(your_terms=["widget", "reviews"], competitor_terms=["widget", "reviews"])
    assert gap == []
