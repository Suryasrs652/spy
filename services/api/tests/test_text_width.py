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


# ── is_shouting ──────────────────────────────────────────────────────────

from app.core.text_width import is_shouting  # noqa: E402


def test_genuine_all_caps_is_detected() -> None:
    assert is_shouting("BUY NOW WHILE STOCKS LAST")


def test_normal_sentence_case_is_not_shouting() -> None:
    assert not is_shouting("A perfectly ordinary meta description about a studio.")


def test_caseless_script_with_a_latin_acronym_is_not_shouting() -> None:
    """The regression: upper() is a no-op on Devanagari/Tamil/Telugu, so a
    normal sentence carrying one uppercase Latin acronym satisfied both
    `s == s.upper()` and `s != s.lower()`. These are real descriptions from
    a site that had 12 of them reported as shouting.
    """
    for text in [
        "चेन्नई, तमिलनाडु में AI विज्ञापन और वीडियो स्टूडियो",
        "சென்னை, தமிழ்நாட்டில் உள்ள AI விளம்பர மற்றும் வீடியோ ஸ்டுடியோ",
        "చెన్నై, తమిళనాడులోని AI ప్రకటన మరియు వీడియో స్టూడియో",
    ]:
        assert not is_shouting(text), text


def test_too_few_cased_letters_is_never_shouting() -> None:
    # "AI" alone proves nothing either way.
    assert not is_shouting("AI")
    assert not is_shouting("日本語 AI")


def test_mixed_case_is_not_shouting() -> None:
    assert not is_shouting("THIS IS MOSTLY CAPS but not entirely")
