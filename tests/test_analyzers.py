from analysis.analyzers import CvLine, KeywordAnalyzer, terms_of
from analysis.scoring import total_points
from analysis.text import locate, normalize, term_pattern

SETTINGS: dict = {}


def lines(*texts):
    return [CvLine(i, "experience", t) for i, t in enumerate(texts)]


def skill(id, present, absent=0.0, **extra):
    return {"id": id, "label": extra.pop("label", id), "points_present": present, "points_absent": absent, **extra}


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
    criteria = [skill("python", 1), skill("sql", 0.5), skill("docker", 0.1), skill("data", 0, -20, default_synonyms=False)]
    cv = lines("Développeur Python, 3 ans", "Bases PostgreSQL et Redis")
    result = KeywordAnalyzer().analyze(cv, criteria, SETTINGS)
    # Python +1, SQL (through PostgreSQL) +0.5, no Docker, -20 for the missing "data".
    assert result.score == -18.5
    assert (result.details["possible"], result.details["gained"], result.details["penalties"]) == (1.6, 1.5, 20)
    by_id = {c["id"]: c for c in result.details["criteria"]}
    assert by_id["python"] == {
        "id": "python", "label": "python", "found": True, "points": 1.0,
        "lines": [0], "matched_terms": ["python"],
    }
    assert by_id["sql"]["matched_terms"] == ["postgresql"] and by_id["sql"]["lines"] == [1]
    assert by_id["data"]["found"] is False and by_id["data"]["points"] == -20


def test_points_have_no_bound():
    criteria = [skill("python", 1, -40), skill("java", 1, -40), skill("go", 1, -5)]
    result = KeywordAnalyzer().analyze(lines("Stage de fin d'études"), criteria, SETTINGS)
    assert result.details["penalties"] == 85
    assert result.score == -85


def test_a_word_counts_once_however_often_it_appears():
    once = KeywordAnalyzer().analyze(lines("Python"), [skill("python", 1), skill("go", 1)], SETTINGS)
    many = KeywordAnalyzer().analyze(lines("Python Python", "python"), [skill("python", 1), skill("go", 1)], SETTINGS)
    assert once.score == many.score == 1


def test_only_missing_criteria_cost_points():
    assert KeywordAnalyzer().analyze(lines("Senior engineer"), [skill("java", 0, -20)], SETTINGS).score == -20


def test_total_is_keyword_points_plus_every_recruiter_point():
    assert total_points(1.6, []) == 1.6
    assert total_points(1.6, [30, 50, 40]) == 121.6
    assert total_points(1.6, [10, -100]) == -88.4
    assert total_points(None, [10]) is None


def test_locate_finds_a_quote_whatever_its_spacing():
    text = "Développeur Python\nData   scientist chez Acme\nData scientist junior"
    start, end = locate(text, "data scientist")
    assert text[start:end] == "Data   scientist"
    start, end = locate(text, "DATA SCIENTIST", within=(text.index("Data scientist junior"), len(text)))
    assert text[start:end] == "Data scientist" and start == text.index("Data scientist junior")
    assert locate(text, "developpeur python") == (0, 18)
    assert locate(text, "Java") is None
    assert locate(text, "   ") is None
