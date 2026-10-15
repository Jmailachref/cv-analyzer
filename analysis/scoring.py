"""The final CV score: the automatic score weighed with the recruiters' highlights."""
from __future__ import annotations

DEFAULT_SETTINGS = {"penalty_cap": 50, "auto_weight": 0.6, "manual_cap": 20}

# Points a skill earns by priority (1 core ... 5 bonus) when present, and costs when missing.
PRIORITY_POINTS = {1: (1.0, -20.0), 2: (0.5, 0.0), 3: (0.1, 0.0), 4: (0.5, 0.0), 5: (0.1, 0.0)}
ALERT_POINTS = -5.0


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
