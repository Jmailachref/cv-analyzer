"""An offer's grid, and a CV's points: the keyword points plus the recruiters' points."""
from __future__ import annotations

import re

from analysis.text import normalize

# Points a skill earns by priority (1 core ... 5 bonus) when present, and costs when missing.
PRIORITY_POINTS = {1: (1.0, -20.0), 2: (0.5, 0.0), 3: (0.1, 0.0), 4: (0.5, 0.0), 5: (0.1, 0.0)}


def grid_from(skills: list[dict]) -> list[dict]:
    """An offer's grid built from its ranked skills.

    Priority 1 (core): +1 when present, -20 when missing. 2: +0.5. 3: +0.1.
    4 (CV only): +0.5. 5 (bonus): +0.1. Only a missing core skill costs points.
    """
    criteria, used = [], set()

    def slug(name: str) -> str:
        # The id a grid accepts back: lowercase letters, digits and _ . + # / -
        base = re.sub(r"[^a-z0-9_.+#/]+", "-", normalize(name)).strip("-")[:50] or "criterion"
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
             "points_present": present, "points_absent": absent, "level": skill["priority"]}
        )
    return criteria


def regrid(old_skills: list[dict], old_criteria: list[dict], skills: list[dict]) -> list[dict]:
    """The grid built from new skills, keeping what a recruiter changed in the old grid.

    A criterion the recruiter edited keeps its edits while its skill stays in the offer,
    and one the recruiter added stays. The others follow the new skills and priorities.
    """
    defaults = {c["id"]: c for c in grid_from(old_skills)}
    criteria = grid_from(skills)
    position = {c["id"]: i for i, c in enumerate(criteria)}
    for old in old_criteria:
        default = defaults.get(old["id"])
        if default is None:
            if old["id"] not in position:
                position[old["id"]] = len(criteria)
                criteria.append(old)
        elif {**default, **old} != default and old["id"] in position:  # grids saved before levels have none
            criteria[position[old["id"]]] = old
    return criteria


def total_points(auto: float | None, highlights: list[int]) -> float | None:
    """The CV's points: the keyword points plus every recruiter's points. No bound."""
    if auto is None:
        return None
    return round(auto + sum(highlights), 2)
