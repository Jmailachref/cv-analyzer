"""Text normalisation shared by extraction and matching."""
from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", " ": " ", "–": "-", "—": "-"})


def normalize(text: str) -> str:
    """Lowercase, no accents, plain apostrophes and dashes, single spaces.

    Accents are dropped one character at a time, so the result has the same
    length as the input as long as it holds no ligatures: offsets stay valid.
    """
    out = []
    for ch in text.translate(_APOSTROPHES).lower():
        base = unicodedata.normalize("NFKD", ch)
        stripped = "".join(c for c in base if not unicodedata.combining(c))
        out.append(stripped if len(stripped) == 1 else ch)
    return "".join(out)


def locate(text: str, quote: str, within: tuple[int, int] | None = None) -> tuple[int, int] | None:
    """Where a quote copied from the PDF sits in the extracted text, as (start, end).

    Spaces, case and accents are ignored on both sides, because a PDF viewer and
    the extractor rarely space words the same way. The first match inside
    `within` wins, else the first match anywhere.
    """
    norm = normalize(text)
    kept = [i for i, ch in enumerate(norm) if not ch.isspace()]
    compact = "".join(norm[i] for i in kept)
    needle = "".join(ch for ch in normalize(quote) if not ch.isspace())
    if not needle:
        return None
    first, pos = None, compact.find(needle)
    while pos != -1:
        start, end = kept[pos], kept[pos + len(needle) - 1] + 1
        if within is None or within[0] <= start < within[1]:
            return start, end
        first = first or (start, end)
        pos = compact.find(needle, pos + 1)
    return first


def term_pattern(term: str) -> re.Pattern:
    """A term as a whole word: "go" does not match "google", "c++" matches "C++,"."""
    words = normalize(term).split()
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")
