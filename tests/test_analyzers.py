from analysis.analyzers import CvLine, KeywordAnalyzer, terms_of
from analysis.scoring import final_score, manual_score
from analysis.text import normalize, term_pattern

SETTINGS = {"penalty_cap": 50, "auto_weight": 0.6, "manual_cap": 20}


def lines(*texts):
    return [CvLine(i, "experience", t) for i, t in enumerate(texts)]


def skill(id, present, absent=0.0, **extra):
    return {"id": id, "label": extra.pop("label", id), "kind": "skill", "points_present": present, "points_absent": absent, **extra}


def alert(id, points=-5.0):
    return {"id": id, "label": id, "kind": "alert", "default_synonyms": False, "points_present": points, "points_absent": 0}


def test_normalize_drops_accents_and_keeps_offsets():
    text = "Expérience à Montréal – Développeur"
    assert normalize(text) == "experience a montreal - developpeur"
    assert len(normalize(text)) == len(text)


def test_terms_match_whole_words_only():
    assert term_pattern("go").search(normalize("Go, Rust"))
    assert not term_pattern("go").search(normalize("Google Cloud"))
    assert term_pattern("c++").search(normalize("C++, Java"))
    assert term_pattern("node.js").search(normalize("APIs en Node.js."))
    assert term_pattern("machine learning").search(normalize("Machine   Learning"))
    assert not term_pattern("java").search(normalize("JavaScript"))


def test_default_synonyms_are_added_unless_turned_off():
    assert "postgresql" in terms_of(skill("sql", 1))
    assert terms_of(skill("sql", 1, default_synonyms=False, terms=["t-sql"])) == ["t-sql", "sql"]


def test_the_data_scientist_example():
    criteria = [skill("python", 1), skill("sql", 0.5), skill("docker", 0.1), skill("data", 0, -20, default_synonyms=False), alert("stage")]
    cv = lines("Développeur Python, 3 ans", "Bases PostgreSQL et Redis")
    result = KeywordAnalyzer().analyze(cv, criteria, SETTINGS)
    # 1.5 of 1.6 possible points = 93.75, minus 20 for the missing "data".
    assert result.score == 73.8
    by_id = {c["id"]: c for c in result.details["criteria"]}
    assert by_id["python"] == {
        "id": "python", "label": "python", "kind": "skill", "found": True, "points": 1.0,
        "lines": [0], "matched_terms": ["python"],
    }
    assert by_id["sql"]["matched_terms"] == ["postgresql"] and by_id["sql"]["lines"] == [1]
    assert by_id["data"]["found"] is False and by_id["data"]["points"] == -20
    assert by_id["stage"]["found"] is False and by_id["stage"]["points"] == 0


def test_warning_words_cost_points_and_penalties_are_capped():
    criteria = [skill("python", 1, -40), skill("java", 1, -40), alert("stage")]
    result = KeywordAnalyzer().analyze(lines("Stage de fin d'études"), criteria, SETTINGS)
    assert result.details["penalties"] == 85
    assert result.details["penalties_applied"] == 50
    assert result.score == 0


def test_a_word_counts_once_however_often_it_appears():
    once = KeywordAnalyzer().analyze(lines("Python"), [skill("python", 1), skill("go", 1)], SETTINGS)
    many = KeywordAnalyzer().analyze(lines("Python Python", "python"), [skill("python", 1), skill("go", 1)], SETTINGS)
    assert once.score == many.score == 50


def test_a_grid_of_warnings_only_starts_from_100():
    assert KeywordAnalyzer().analyze(lines("Senior engineer"), [alert("stage")], SETTINGS).score == 100


def test_final_score_weighs_auto_and_highlights():
    assert manual_score([], SETTINGS) is None
    assert manual_score([5, 5], SETTINGS) == 50
    assert manual_score([5, 5, 5, 5, 5], SETTINGS) == 100  # capped at 20 points
    assert final_score(70, None, SETTINGS) == 70
    assert final_score(70, 50, SETTINGS) == 62
    assert final_score(None, 50, SETTINGS) is None
