"""Display width for title/description length checks.

Google truncates titles and descriptions by rendered pixel width, not by
code points. We can't measure pixels without font metrics, but counting
code points is wrong in a way that is both large and systematically
biased against non-Latin scripts, so this approximates rendered width
instead.

Two adjustments, both of which are no-ops for Latin text:

  - Zero-advance marks don't count. Abugidas (Devanagari, Tamil, Telugu,
    Bengali…) write a syllable as a base consonant plus combining vowel
    signs and viramas. Those marks attach to the base glyph and occupy no
    horizontal cell of their own, so counting them inflated every Indic
    title by 12-20%. On one real four-language site that mis-flagged 69%
    of Tamil pages and 44% of Telugu pages as over-long while flagging
    only 9% of the English ones — the titles were fine; the ruler wasn't.

  - Wide characters count double. CJK ideographs and fullwidth forms
    occupy roughly two Latin character cells, so counting them as one
    under-flags Japanese and Chinese titles that really would truncate.

Latin text contains neither, so its measurement is unchanged — the
existing thresholds keep meaning exactly what they meant before.
"""
from __future__ import annotations

import unicodedata

# Nonspacing marks, enclosing marks, and format characters (ZWJ/ZWNJ,
# directional marks) all render with no advance width of their own.
_ZERO_WIDTH_CATEGORIES = frozenset({"Mn", "Me", "Cf"})

# East Asian Wide and Fullwidth occupy about two Latin cells.
_DOUBLE_WIDTH = frozenset({"W", "F"})


def display_width(text: str) -> int:
    """Approximate rendered width of `text` in Latin character cells."""
    width = 0
    for char in text:
        if unicodedata.category(char) in _ZERO_WIDTH_CATEGORIES:
            continue
        width += 2 if unicodedata.east_asian_width(char) in _DOUBLE_WIDTH else 1
    return width


# Below this many cased letters there isn't enough evidence to call a string
# shouting. "AI" alone is two.
_MIN_CASED_FOR_CAPS_CHECK = 10


def is_shouting(text: str) -> bool:
    """True when `text` is written in all capitals, for scripts that have
    capitals at all.

    The obvious test — `text == text.upper()` — silently misfires on every
    caseless script. Devanagari, Tamil, Telugu, Arabic, Hebrew, CJK and the
    rest are unchanged by `upper()`, so a perfectly normal sentence in one
    of them containing a single Latin acronym ("AI", "UGC") satisfies both
    `text == text.upper()` and `text != text.lower()` and gets reported as
    shouting. On one real four-language site that flagged 12 descriptions,
    every one of them ordinary sentence case.

    So: look only at characters that actually carry case, and require
    enough of them to be saying something.
    """
    cased = [char for char in text if char.upper() != char.lower()]
    if len(cased) < _MIN_CASED_FOR_CAPS_CHECK:
        return False
    return all(char.isupper() for char in cased)
