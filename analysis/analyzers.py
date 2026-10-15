"""Analyzers turn a CV's lines and a grid into a score out of 100 with its reasons.

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
    """Finds each criterion (a group of synonyms) in the CV; each counts once.

    score = max(0, gained / possible * 100 - min(penalty_cap, penalties))
    where possible is the sum of the positive criteria's points, gained the
    part of it found, and penalties the points lost to missing criteria and
    to warning words that are present.
    """

    name = "keywords"
    version = "1.0"
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

        cap = float(settings.get("penalty_cap", 50))
        base = gained / possible * 100 if possible else 100.0
        applied = min(cap, penalties)
        score = round(max(0.0, base - applied), 1)
        return Result(
            score=score,
            details={
                "base": round(base, 1),
                "penalties": round(penalties, 2),
                "penalties_applied": round(applied, 2),
                "criteria": results,
            },
        )


ANALYZERS: dict[str, Analyzer] = {a.name: a for a in (KeywordAnalyzer(),)}
DEFAULT_ANALYZER = "keywords"
