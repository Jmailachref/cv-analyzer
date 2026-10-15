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


def term_pattern(term: str) -> re.Pattern:
    """A term as a whole word: "go" does not match "google", "c++" matches "C++,"."""
    words = normalize(term).split()
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")
