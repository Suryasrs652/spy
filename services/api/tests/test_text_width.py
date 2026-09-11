"""Display-width measurement for title/description length rules.

The regression these lock in: counting code points systematically
over-counts abugida scripts, because a syllable is written as a base
consonant plus combining marks that occupy no width of their own.
"""
from __future__ import annotations

from app.core.text_width import display_width


def test_latin_is_measured_exactly_as_before() -> None:
    """The whole fix is worthless if it shifts Latin measurements — the
    configured 15/60 thresholds have to keep meaning what they meant."""
    for text in [
        "AI Studio in India | AI Ads & Films | Spilanth Studio",
        "Privacy notice | Spilanth Studio",
        "",
        "a",
    ]:
        assert display_width(text) == len(text)


def test_combining_marks_do_not_add_width() -> None:
    # Devanagari: "के" is ka + vowel sign e (nonspacing) — one cell, two code points.
    text = "के"
    assert len(text) == 2
    assert display_width(text) == 1


def test_indic_titles_measure_shorter_than_their_code_point_count() -> None:
    tamil = "இந்தியாவில் AI ஸ்டுடியோ | AI விளம்பரங்கள் மற்றும் திரைப்படங்கள்"
    telugu = "భారతదేశంలో AI స్టూడియో | AI ప్రకటనలు మరియు చిత్రాలు"
    for text in (tamil, telugu):
        assert display_width(text) < len(text)


def test_wide_characters_count_double() -> None:
    # CJK ideographs occupy roughly two Latin cells, so a 60-code-point
    # Japanese title really would truncate where a Latin one wouldn't.
    assert display_width("日本語") == 6
    assert display_width("abc") == 3


def test_zero_width_joiners_are_ignored() -> None:
    assert display_width("a\u200db") == 2
