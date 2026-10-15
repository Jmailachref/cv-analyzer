from pathlib import Path

from conftest import OTHER, RH, drain, make_pdf

from core.config import settings

CV_GOOD = make_pdf(
    "Amina Haddad",
    "Expérience",
    "2021 - 2024 : Data scientist chez Acme",
    "Modèles de machine learning en Python, requêtes SQL",
    "Compétences",
    "Docker, Git",
)
CV_WEAK = make_pdf(
    "Karim Ben Ali",
    "Expérience",
    "Stage de développement web en PHP, 6 mois",
    "Compétences",
    "HTML, CSS, JavaScript",
)


def upload(client, pdf=CV_GOOD, headers=RH, **form):
    return client.post("/v1/documents", files={"file": ("cv.pdf", pdf, "application/pdf")}, data=form, headers=headers)


def suggest(client):
    body = {"skills": [{"name": "Python", "priority": 1}, {"name": "SQL", "priority": 2}, {"name": "Docker", "priority": 3}],
            "alerts": ["stage"]}
    r = client.post("/v1/grids/suggest", json=body, headers=RH)
    assert r.status_code == 200, r.text
    return r.json()


def test_every_route_needs_an_api_key(client):
    assert client.get("/v1/analyzers").status_code == 401
    assert client.get("/v1/documents", headers={"Authorization": "Bearer nope"}).json()["error"]["code"] == "unauthorized"
    assert client.get("/health").json() == {"status": "ok"}


def test_suggest_builds_a_grid_from_priorities(client):
    grid = suggest(client)
    assert [(c["id"], c["kind"], c["points_present"], c["points_absent"]) for c in grid["criteria"]] == [
        ("python", "skill", 1.0, -20.0),
        ("sql", "skill", 0.5, 0.0),
        ("docker", "skill", 0.1, 0.0),
        ("stage", "alert", -5.0, 0.0),
    ]
    assert grid["settings"] == {"penalty_cap": 50, "auto_weight": 0.6, "manual_cap": 20}


def test_grid_validation(client):
    bad_alert = {"criteria": [{"id": "stage", "label": "stage", "kind": "alert", "points_present": 2}]}
    assert client.put("/v1/grids/offer-1", json=bad_alert, headers=RH).status_code == 400
    twice = {"criteria": [{"id": "python", "label": "Python"}, {"id": "python", "label": "Py"}]}
    assert client.put("/v1/grids/offer-1", json=twice, headers=RH).status_code == 400
    assert client.get("/v1/grids/offer-1", headers=RH).json()["error"]["code"] == "grid_not_found"


def test_upload_only_takes_pdfs(client):
    r = upload(client, pdf=b"hello")
    assert r.status_code == 415 and r.json()["error"]["code"] == "not_a_pdf"


def test_upload_read_and_score(client, events):
    grid = client.put("/v1/grids/offer-1", json=suggest(client), headers=RH).json()
    assert grid["version"] == 1

    r = upload(client, external_ref="cand-1", grid_ref="offer-1")
    assert r.status_code == 202, r.text
    doc = r.json()
    assert doc["status"] == "queued" and doc["external_ref"] == "cand-1"
    assert drain() == 1

    detail = client.get(f"/v1/documents/{doc['id']}", headers=RH).json()
    assert detail["status"] == "ready" and detail["pages"] == 1
    assert [ln["section"] for ln in detail["lines"]] == ["header", "experience", "experience", "experience", "skills", "skills"]
    assert client.get(f"/v1/documents/{doc['id']}/file", headers=RH).content == CV_GOOD

    score = client.get(f"/v1/documents/{doc['id']}/score", headers=RH).json()
    assert (score["auto"], score["manual"], score["final"], score["grid_version"]) == (100.0, None, 100.0, 1)
    found = {c["id"]: c["lines"] for c in score["analysis"]["details"]["criteria"] if c["found"]}
    assert found == {"python": [3], "sql": [3], "docker": [5]}

    assert [e[1] for e in events] == ["document.processed", "analysis.done"]
    assert events[1][0] == "recrutehub" and events[1][2]["external_ref"] == "cand-1" and events[1][2]["score"] == 100


def test_highlights_add_a_manual_score(client):
    client.put("/v1/grids/offer-1", json=suggest(client), headers=RH)
    doc = upload(client, external_ref="cand-1", grid_ref="offer-1").json()
    drain()
    text = client.get(f"/v1/documents/{doc['id']}", headers=RH).json()["text"]
    start = text.index("Data scientist")

    by_range = client.post(
        f"/v1/documents/{doc['id']}/highlights",
        json={"author_ref": "user-7", "start": start, "end": start + len("Data scientist"), "points": 4, "comment": "le bon poste"},
        headers=RH,
    )
    assert by_range.status_code == 201, by_range.text
    assert by_range.json()["quote"] == "Data scientist"
    by_line = client.post(
        f"/v1/documents/{doc['id']}/highlights", json={"author_ref": "user-7", "line": 3, "points": 2}, headers=RH
    ).json()
    assert by_line["quote"] == "Modèles de machine learning en Python, requêtes SQL"

    score = client.get(f"/v1/documents/{doc['id']}/score", headers=RH).json()
    # 6 points of 20 = 30; final = 0.6 × 100 + 0.4 × 30.
    assert (score["manual_points"], score["manual"], score["final"]) == (6, 30.0, 72.0)

    assert client.delete(f"/v1/highlights/{by_line['id']}", headers=OTHER).status_code == 404
    assert client.delete(f"/v1/highlights/{by_line['id']}", headers=RH).status_code == 204
    assert client.get(f"/v1/documents/{doc['id']}/score", headers=RH).json()["manual_points"] == 4


def test_highlight_validation(client):
    doc = upload(client, grid_ref="offer-1").json()
    early = client.post(f"/v1/documents/{doc['id']}/highlights", json={"author_ref": "u", "line": 0, "points": 3}, headers=RH)
    assert early.status_code == 409
    drain()
    url = f"/v1/documents/{doc['id']}/highlights"
    assert client.post(url, json={"author_ref": "u", "line": 99, "points": 3}, headers=RH).json()["error"]["code"] == "invalid_range"
    assert client.post(url, json={"author_ref": "u", "start": 0, "end": 99999, "points": 3}, headers=RH).status_code == 400
    assert client.post(url, json={"author_ref": "u", "line": 0, "points": 6}, headers=RH).status_code == 400
    assert client.post(url, json={"author_ref": "u", "start": 0, "end": 4, "line": 0, "points": 1}, headers=RH).status_code == 400


def test_ranking_and_rescoring_when_the_grid_changes(client):
    client.put("/v1/grids/offer-1", json=suggest(client), headers=RH)
    good = upload(client, external_ref="good", grid_ref="offer-1").json()
    weak = upload(client, pdf=CV_WEAK, external_ref="weak", grid_ref="offer-1").json()
    pending = upload(client, external_ref="pending", grid_ref="offer-1").json()
    assert drain() == 3
    client.delete(f"/v1/documents/{pending['id']}", headers=RH)

    ranking = client.get("/v1/grids/offer-1/ranking", headers=RH).json()
    assert [(r["rank"], r["external_ref"], r["final"]) for r in ranking] == [(1, "good", 100.0), (2, "weak", 0.0)]
    # Weak: no Python (-20), a "stage" (-5), nothing gained.
    assert ranking[1]["missing"] == ["Python"]

    grid = suggest(client)
    grid["criteria"].append({"id": "php", "label": "PHP", "points_present": 1})
    assert client.put("/v1/grids/offer-1", json=grid, headers=RH).json()["version"] == 2
    assert drain() == 2
    weak_score = client.get(f"/v1/documents/{weak['id']}/score", headers=RH).json()
    assert weak_score["grid_version"] == 2
    # 1 of 2.6 points = 38.5, minus 20 and 5.
    assert weak_score["auto"] == 13.5
    history = client.get(f"/v1/documents/{good['id']}/analyses", headers=RH).json()
    assert [a["grid_version"] for a in history] == [2, 1]


def test_analyze_on_demand(client):
    doc = upload(client).json()
    drain()
    url = f"/v1/documents/{doc['id']}/analyses"
    assert client.post(url, json={}, headers=RH).json()["error"]["code"] == "grid_ref_required"
    assert client.post(url, json={"grid_ref": "offer-9"}, headers=RH).json()["error"]["code"] == "grid_not_found"
    client.put("/v1/grids/offer-9", json=suggest(client), headers=RH)
    assert client.post(url, json={"grid_ref": "offer-9", "analyzer": "magic"}, headers=RH).status_code == 400
    r = client.post(url, json={"grid_ref": "offer-9"}, headers=RH)
    assert r.status_code == 201 and r.json()["score"] == 100 and r.json()["analyzer"] == "keywords"


def test_clients_only_see_their_own_data(client):
    client.put("/v1/grids/offer-1", json=suggest(client), headers=RH)
    doc = upload(client, grid_ref="offer-1").json()
    drain()
    assert client.get(f"/v1/documents/{doc['id']}", headers=OTHER).status_code == 404
    assert client.get(f"/v1/documents/{doc['id']}/file", headers=OTHER).status_code == 404
    assert client.delete(f"/v1/documents/{doc['id']}", headers=OTHER).status_code == 404
    assert client.get("/v1/grids/offer-1", headers=OTHER).status_code == 404
    assert client.get("/v1/documents", headers=OTHER).json() == []
    assert len(client.get("/v1/documents?grid_ref=offer-1", headers=RH).json()) == 1


def test_delete_erases_everything(client):
    client.put("/v1/grids/offer-1", json=suggest(client), headers=RH)
    doc = upload(client, grid_ref="offer-1").json()
    drain()
    client.post(f"/v1/documents/{doc['id']}/highlights", json={"author_ref": "u", "line": 0, "points": 3}, headers=RH)
    stored = Path(settings.storage_dir) / "recrutehub" / f"{doc['id']}.pdf"
    assert stored.exists()
    assert client.delete(f"/v1/documents/{doc['id']}", headers=RH).status_code == 204
    assert not stored.exists()
    assert client.get(f"/v1/documents/{doc['id']}", headers=RH).status_code == 404
    assert client.get("/v1/grids/offer-1/ranking", headers=RH).json() == []


def test_unreadable_and_broken_pdfs(client, events):
    blank = upload(client, pdf=make_pdf("")).json()
    broken = upload(client, pdf=b"%PDF-1.7 this is not really a pdf").json()
    drain()
    assert client.get(f"/v1/documents/{blank['id']}", headers=RH).json()["status"] == "unreadable"
    failed = client.get(f"/v1/documents/{broken['id']}", headers=RH).json()
    assert failed["status"] == "failed" and failed["error"]
    assert [e[2]["status"] for e in events] == ["unreadable", "failed"]
