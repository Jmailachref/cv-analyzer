"""Analyzers turn a CV's lines and a grid into points, with their reasons.

Every analyzer returns the same shape, so a better one (embeddings, an LLM)
can replace or run beside the keyword analyzer without any client change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from analysis.synonyms import synonyms_for
from analysis.text import normalize, term_pattern


@dataclass(frozen=True)
class CvLine:
    n: int
    section: str
    text: str


@dataclass
class Result:
    score: float
    details: dict


class Analyzer(Protocol):
    name: str
    version: str
    description: str

    def analyze(self, lines: list[CvLine], criteria: list[dict], settings: dict) -> Result: ...


def terms_of(criterion: dict) -> list[str]:
    terms = list(criterion.get("terms") or [])
    if criterion.get("default_synonyms", True):
        terms += synonyms_for(criterion["label"])
    terms.append(criterion["label"])
    seen, out = set(), []
    for t in terms:
        key = normalize(t).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


class KeywordAnalyzer:
    """Finds each criterion (a group of synonyms) in the CV; each counts once,
    however often it appears.

    score = the sum of the points: points_present for each criterion found,
    points_absent (0 or negative) for each one missing. No cap, no scale.
    """

    name = "keywords"
    version = "2.0"
    description = "Keywords and synonyms, matched as whole words in the CV text."

    def analyze(self, lines: list[CvLine], criteria: list[dict], settings: dict) -> Result:
        normalized = [(line, normalize(line.text)) for line in lines]
        results, possible, gained, penalties = [], 0.0, 0.0, 0.0
        for c in criteria:
            patterns = [(t, term_pattern(t)) for t in terms_of(c)]
            hits: dict[int, set[str]] = {}
            for line, text in normalized:
                for term, pattern in patterns:
                    if pattern.search(text):
                        hits.setdefault(line.n, set()).add(term)
            found = bool(hits)
            present, absent = float(c.get("points_present", 0)), float(c.get("points_absent", 0))
            if present > 0:
                possible += present
            points = present if found else absent
            if points > 0:
                gained += points
            else:
                penalties += -points
            results.append(
                {
                    "id": c["id"],
                    "label": c["label"],
                    "found": found,
                    "points": points,
                    "lines": sorted(hits),
                    "matched_terms": sorted({t for ts in hits.values() for t in ts}),
                }
            )

        return Result(
            score=round(gained - penalties, 2),
            details={
                "possible": round(possible, 2),
                "gained": round(gained, 2),
                "penalties": round(penalties, 2),
                "criteria": results,
            },
        )


ANALYZERS: dict[str, Analyzer] = {a.name: a for a in (KeywordAnalyzer(),)}
DEFAULT_ANALYZER = "keywords"
