import dataclasses
from pathlib import Path

from conftest import OTHER, RH, drain, make_pdf

from api import auth
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


# An offer as RecruteHub sends it: its skills use "language".
OFFER = {
    "title": "Data scientist",
    "skills": [{"language": "Python", "priority": 1}, {"language": "SQL", "priority": 2}, {"language": "Docker", "priority": 3}],
}


def upload(client, pdf=CV_GOOD, headers=RH, offer_ref="offer-1", **form):
    if offer_ref is not None:
        form["offer_ref"] = offer_ref
    return client.post("/v1/documents", files={"file": ("cv.pdf", pdf, "application/pdf")}, data=form, headers=headers)


def create_offer(client, ref="offer-1", body=OFFER):
    r = client.put(f"/v1/offers/{ref}", json=body, headers=RH)
    assert r.status_code == 200, r.text
    return r.json()


def test_every_route_needs_an_api_key(client):
    assert client.get("/v1/analyzers").status_code == 401
    assert client.get("/v1/documents", headers={"Authorization": "Bearer nope"}).json()["error"]["code"] == "unauthorized"
    assert client.get("/health").json() == {"status": "ok"}


def test_an_offer_gets_a_grid_built_from_its_skills(client):
    grid = create_offer(client)
    assert (grid["external_ref"], grid["title"], grid["grid_version"]) == ("offer-1", "Data scientist", 1)
    assert grid["skills"][0] == {"name": "Python", "priority": 1}
    # Only a missing core skill costs points.
    assert [(c["id"], c["points_present"], c["points_absent"]) for c in grid["criteria"]] == [
        ("python", 1.0, -20.0),
        ("sql", 0.5, 0.0),
        ("docker", 0.1, 0.0),
    ]


def test_changing_skills_keeps_the_grid_a_recruiter_edited(client):
    grid = create_offer(client)["criteria"]
    grid[0]["terms"] = ["pandas"]
    grid.append({"id": "airflow", "label": "Airflow", "points_present": 3})
    create_offer(client, body={**OFFER, "criteria": grid})
    skills = [{"name": "Python", "priority": 2}, {"name": "SQL", "priority": 1}, {"name": "Go", "priority": 3}]
    out = create_offer(client, body={"title": "Data scientist", "skills": skills})
    by_id = {c["id"]: c for c in out["criteria"]}
    # Python was edited: it keeps its edits. SQL follows its new priority, Docker is gone, Airflow stays.
    assert by_id["python"]["terms"] == ["pandas"] and by_id["python"]["points_absent"] == -20
    assert (by_id["sql"]["points_present"], by_id["sql"]["points_absent"]) == (1.0, -20.0)
    assert "docker" not in by_id and by_id["go"]["points_present"] == 0.1
    assert by_id["airflow"]["points_present"] == 3
    rebuilt = create_offer(client, body={"title": "Data scientist", "skills": skills, "rebuild": True})
    assert [c["id"] for c in rebuilt["criteria"]] == ["sql", "python", "go"]
    assert rebuilt["criteria"][1]["terms"] == []


def test_offer_validation(client):
    costs_when_found = {"title": "x", "criteria": [{"id": "stage", "label": "stage", "points_present": -5}]}
    assert client.put("/v1/offers/offer-1", json=costs_when_found, headers=RH).status_code == 400
    twice = {"title": "x", "criteria": [{"id": "python", "label": "Python"}, {"id": "python", "label": "Py"}]}
    assert client.put("/v1/offers/offer-1", json=twice, headers=RH).status_code == 400
    same_skill = {"title": "x", "skills": [{"name": "Python", "priority": 1}, {"name": "python", "priority": 2}]}
    assert client.put("/v1/offers/offer-1", json=same_skill, headers=RH).status_code == 400
    assert client.put("/v1/offers/offer-1", json={"skills": []}, headers=RH).status_code == 400
    assert client.get("/v1/offers/offer-1", headers=RH).json()["error"]["code"] == "offer_not_found"


def test_a_cv_is_always_sent_for_an_existing_offer(client):
    assert upload(client, offer_ref=None).status_code == 400
    r = upload(client, offer_ref="offer-404")
    assert r.status_code == 404 and r.json()["error"]["code"] == "offer_not_found"
    create_offer(client)
    r = upload(client, pdf=b"hello")
    assert r.status_code == 415 and r.json()["error"]["code"] == "not_a_pdf"
    assert upload(client).json()["offer_ref"] == "offer-1"


def test_upload_read_and_score(client, events):
    create_offer(client)

    r = upload(client, external_ref="cand-1")
    assert r.status_code == 202, r.text
    doc = r.json()
    assert doc["status"] == "queued" and doc["external_ref"] == "cand-1"
    assert drain() == 1

    detail = client.get(f"/v1/documents/{doc['id']}", headers=RH).json()
    assert detail["status"] == "ready" and detail["pages"] == 1
    assert [ln["section"] for ln in detail["lines"]] == ["header", "experience", "experience", "experience", "skills", "skills"]
    assert client.get(f"/v1/documents/{doc['id']}/file", headers=RH).content == CV_GOOD

    score = client.get(f"/v1/documents/{doc['id']}/score", headers=RH).json()
    # Python +1, SQL +0.5, Docker +0.1; no recruiter points yet.
    assert (score["auto"], score["manual"], score["total"], score["grid_version"]) == (1.6, 0, 1.6, 1)
    found = {c["id"]: c["lines"] for c in score["analysis"]["details"]["criteria"] if c["found"]}
    assert found == {"python": [3], "sql": [3], "docker": [5]}

    assert [e[1] for e in events] == ["document.processed", "analysis.done"]
    assert events[0][2]["offer_ref"] == "offer-1"
    assert events[1][0] == "recrutehub" and events[1][2]["external_ref"] == "cand-1" and events[1][2]["score"] == 1.6
    assert events[1][2]["offer_ref"] == "offer-1" and events[1][2]["grid_version"] == 1


def test_highlights_add_a_manual_score(client):
    create_offer(client)
    doc = upload(client, external_ref="cand-1").json()
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
    assert (score["auto"], score["manual"], score["total"]) == (1.6, 6, 7.6)

    assert client.delete(f"/v1/highlights/{by_line['id']}", headers=OTHER).status_code == 404
    assert client.delete(f"/v1/highlights/{by_line['id']}", headers=RH).status_code == 204
    assert client.get(f"/v1/documents/{doc['id']}/score", headers=RH).json()["manual"] == 4


def test_highlight_validation(client):
    create_offer(client)
    doc = upload(client).json()
    early = client.post(f"/v1/documents/{doc['id']}/highlights", json={"author_ref": "u", "line": 0, "points": 3}, headers=RH)
    assert early.status_code == 409
    drain()
    url = f"/v1/documents/{doc['id']}/highlights"
    assert client.post(url, json={"author_ref": "u", "line": 99, "points": 3}, headers=RH).json()["error"]["code"] == "invalid_range"
    assert client.post(url, json={"author_ref": "u", "start": 0, "end": 99999, "points": 3}, headers=RH).status_code == 400
    assert client.post(url, json={"author_ref": "u", "line": 0, "points": 101}, headers=RH).status_code == 400
    assert client.post(url, json={"author_ref": "u", "line": 0, "points": 0}, headers=RH).status_code == 400
    assert client.post(url, json={"author_ref": "u", "line": 0, "points": 100}, headers=RH).json()["points"] == 100
    assert client.post(url, json={"author_ref": "u", "start": 0, "end": 4, "line": 0, "points": 1}, headers=RH).status_code == 400


def test_ranking_and_rescoring_when_the_grid_changes(client):
    create_offer(client)
    good = upload(client, external_ref="good").json()
    weak = upload(client, pdf=CV_WEAK, external_ref="weak").json()
    pending = upload(client, external_ref="pending").json()
    assert drain() == 3
    client.delete(f"/v1/documents/{pending['id']}", headers=RH)

    ranking = client.get("/v1/offers/offer-1/ranking", headers=RH).json()
    assert [(r["rank"], r["external_ref"], r["total"]) for r in ranking] == [(1, "good", 1.6), (2, "weak", -20.0)]
    # Weak: no Python (-20), nothing gained.
    assert ranking[1]["missing"] == ["Python"]

    # A new title alone leaves the grid, and the scores, as they are.
    assert create_offer(client, body={**OFFER, "title": "Data scientist senior"})["grid_version"] == 1
    assert drain() == 0

    # A recruiter edits the grid: a new version, and every read CV is scored again.
    edited = create_offer(client)
    edited["criteria"].append({"id": "php", "label": "PHP", "points_present": 1})
    assert create_offer(client, body={**OFFER, "criteria": edited["criteria"]})["grid_version"] == 2
    assert drain() == 2
    weak_score = client.get(f"/v1/documents/{weak['id']}/score", headers=RH).json()
    assert weak_score["grid_version"] == 2
    # PHP +1, minus 20 for the missing Python.
    assert weak_score["auto"] == -19
    history = client.get(f"/v1/documents/{good['id']}/analyses", headers=RH).json()
    assert [a["grid_version"] for a in history] == [2, 1]


def test_analyze_on_demand(client):
    create_offer(client)
    doc = upload(client).json()
    url = f"/v1/documents/{doc['id']}/analyses"
    assert client.post(url, json={}, headers=RH).status_code == 409
    drain()
    assert client.post(url, json={"analyzer": "magic"}, headers=RH).status_code == 400
    r = client.post(url, json={}, headers=RH)
    assert r.status_code == 201 and r.json()["score"] == 1.6 and r.json()["analyzer"] == "keywords"
    assert r.json()["offer_ref"] == "offer-1"


def test_clients_only_see_their_own_data(client):
    create_offer(client)
    doc = upload(client).json()
    drain()
    assert client.get(f"/v1/documents/{doc['id']}", headers=OTHER).status_code == 404
    assert client.get(f"/v1/documents/{doc['id']}/file", headers=OTHER).status_code == 404
    assert client.delete(f"/v1/documents/{doc['id']}", headers=OTHER).status_code == 404
    assert client.get("/v1/offers/offer-1", headers=OTHER).status_code == 404
    assert upload(client, headers=OTHER).status_code == 404
    assert client.get("/v1/documents", headers=OTHER).json() == []
    assert len(client.get("/v1/documents?offer_ref=offer-1", headers=RH).json()) == 1
    assert client.get("/v1/documents?offer_ref=offer-2", headers=RH).json() == []


def test_delete_erases_everything(client):
    create_offer(client)
    doc = upload(client).json()
    drain()
    client.post(f"/v1/documents/{doc['id']}/highlights", json={"author_ref": "u", "line": 0, "points": 3}, headers=RH)
    stored = Path(settings.storage_dir) / "recrutehub" / f"{doc['id']}.pdf"
    assert stored.exists()
    assert client.delete(f"/v1/documents/{doc['id']}", headers=RH).status_code == 204
    assert not stored.exists()
    assert client.get(f"/v1/documents/{doc['id']}", headers=RH).status_code == 404
    assert client.get("/v1/offers/offer-1/ranking", headers=RH).json() == []


def test_deleting_an_offer_erases_its_cvs(client):
    create_offer(client)
    create_offer(client, ref="offer-2")
    doc = upload(client).json()
    kept = upload(client, offer_ref="offer-2").json()
    drain()
    stored = Path(settings.storage_dir) / "recrutehub" / f"{doc['id']}.pdf"
    assert client.delete("/v1/offers/offer-1", headers=OTHER).status_code == 404
    assert client.delete("/v1/offers/offer-1", headers=RH).status_code == 204
    assert not stored.exists()
    assert client.get(f"/v1/documents/{doc['id']}", headers=RH).status_code == 404
    assert client.get(f"/v1/documents/{kept['id']}/score", headers=RH).json()["auto"] == 1.6


def test_unreadable_and_broken_pdfs(client, events):
    create_offer(client)
    blank = upload(client, pdf=make_pdf("")).json()
    broken = upload(client, pdf=b"%PDF-1.7 this is not really a pdf").json()
    drain()
    assert client.get(f"/v1/documents/{blank['id']}", headers=RH).json()["status"] == "unreadable"
    failed = client.get(f"/v1/documents/{broken['id']}", headers=RH).json()
    assert failed["status"] == "failed" and failed["error"]
    assert [e[2]["status"] for e in events] == ["unreadable", "failed"]


def test_highlight_the_text_selected_in_the_pdf(client):
    create_offer(client)
    doc = upload(client).json()
    drain()
    url = f"/v1/documents/{doc['id']}/highlights"
    # A PDF viewer spaces and cases words its own way; accents may be lost too.
    picked = client.post(
        url, json={"author_ref": "u", "quote": "data  SCIENTIST chez acme", "page": 1, "points": 5, "comment": "top"}, headers=RH
    )
    assert picked.status_code == 201, picked.text
    h = picked.json()
    assert h["quote"] == "Data scientist chez Acme"
    # Without boxes from the viewer, the boxes are the lines the passage covers.
    assert len(h["boxes"]) == 1 and h["boxes"][0]["page"] == 1 and h["boxes"][0]["x0"] < h["boxes"][0]["x1"]

    drawn = [{"page": 1, "x0": 10, "top": 20, "x1": 60, "bottom": 30}]
    exact = client.post(url, json={"author_ref": "u", "quote": "Docker", "page": 1, "boxes": drawn, "points": 1}, headers=RH)
    assert exact.json()["boxes"] == [{"page": 1, "x0": 10.0, "top": 20.0, "x1": 60.0, "bottom": 30.0}]

    missing = client.post(url, json={"author_ref": "u", "quote": "Kubernetes", "page": 1, "points": 1}, headers=RH)
    assert missing.json()["error"]["code"] == "quote_not_found"
    assert client.post(url, json={"author_ref": "u", "quote": "Docker", "line": 1, "points": 1}, headers=RH).status_code == 400
    # A passage counts once: the same text again, or a passage overlapping a scored one, is refused.
    again = client.post(url, json={"author_ref": "u", "quote": "Data scientist chez Acme", "page": 1, "points": 5}, headers=RH)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_scored"
    overlap = client.post(url, json={"author_ref": "u", "quote": "scientist chez", "page": 1, "points": 5}, headers=RH)
    assert overlap.status_code == 409

    # A red flag costs points; nothing bounds the total.
    flag = client.post(url, json={"author_ref": "u", "quote": "Git", "page": 1, "points": -50, "comment": "red flag"}, headers=RH)
    assert flag.status_code == 201, flag.text
    score = client.get(f"/v1/documents/{doc['id']}/score", headers=RH).json()
    assert (score["auto"], score["manual"], score["total"]) == (1.6, -44, -42.4)


def test_list_offers(client):
    create_offer(client)
    create_offer(client, ref="offer-2", body={**OFFER, "title": "Backend"})
    upload(client)
    rows = client.get("/v1/offers", headers=RH).json()
    assert [(r["external_ref"], r["title"], r["documents"]) for r in rows] == [("offer-2", "Backend", 0), ("offer-1", "Data scientist", 1)]
    assert client.get("/v1/offers", headers=OTHER).json() == []


def test_an_open_client_needs_no_api_key(client, monkeypatch):
    assert client.get("/v1/offers").status_code == 401
    monkeypatch.setattr(auth, "settings", dataclasses.replace(settings, open_client="recrutehub"))
    create_offer(client)
    assert [r["external_ref"] for r in client.get("/v1/offers").json()] == ["offer-1"]
    assert client.get("/v1/offers", headers={"Authorization": "Bearer nope"}).status_code == 401
