"""An offer's grid, and the final CV score: the automatic score weighed with the recruiters' highlights."""
from __future__ import annotations

from analysis.text import normalize

DEFAULT_SETTINGS = {"penalty_cap": 50, "auto_weight": 0.6, "manual_cap": 20}

# Points a skill earns by priority (1 core ... 5 bonus) when present, and costs when missing.
PRIORITY_POINTS = {1: (1.0, -20.0), 2: (0.5, 0.0), 3: (0.1, 0.0), 4: (0.5, 0.0), 5: (0.1, 0.0)}


def grid_from(skills: list[dict]) -> list[dict]:
    """An offer's grid built from its ranked skills.

    Priority 1 (core): +1 when present, -20 when missing. 2: +0.5. 3: +0.1.
    4 (CV only): +0.5. 5 (bonus): +0.1. Only a missing core skill costs points.
    """
    criteria, used = [], set()

    def slug(name: str) -> str:
        base = "-".join(normalize(name).split())[:50] or "criterion"
        base = base if base[0].isalnum() else f"c{base}"
        out, i = base, 2
        while out in used:
            out, i = f"{base}-{i}", i + 1
        used.add(out)
        return out

    for skill in sorted(skills, key=lambda s: s["priority"]):
        present, absent = PRIORITY_POINTS[skill["priority"]]
        criteria.append(
            {"id": slug(skill["name"]), "label": skill["name"], "terms": [], "default_synonyms": True,
             "points_present": present, "points_absent": absent}
        )
    return criteria


def manual_score(points: list[int], settings: dict) -> float | None:
    """Highlight points out of 100: manual_cap points (20 by default) make 100."""
    if not points:
        return None
    cap = float(settings.get("manual_cap", DEFAULT_SETTINGS["manual_cap"]))
    return round(min(sum(points), cap) / cap * 100, 1)


def final_score(auto: float | None, manual: float | None, settings: dict) -> float | None:
    """auto_weight × auto + the rest × manual; the automatic score alone until someone highlights."""
    if auto is None:
        return None
    if manual is None:
        return auto
    weight = float(settings.get("auto_weight", DEFAULT_SETTINGS["auto_weight"]))
    return round(weight * auto + (1 - weight) * manual, 1)
