"""The /v1 REST API: CVs in, text and scores out, highlights from recruiters."""
from __future__ import annotations

import hashlib
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.analyzers import ANALYZERS, DEFAULT_ANALYZER
from analysis.scoring import ALERT_POINTS, PRIORITY_POINTS, final_score, manual_score
from analysis.text import normalize
from api import schemas
from api.auth import client_id
from core import storage
from core.config import settings
from core.db import get_session
from core.models import Analysis, Document, Grid, Highlight
from core.queue import enqueue
from worker.main import analyze, latest_grid

app = FastAPI(
    title="CV Analyzer API",
    version="0.1.0",
    description="Reads CVs (PDF, scanned or not), scores them against a grid of keywords, "
    "and keeps the passages recruiters highlight.",
)

Db = Annotated[Session, Depends(get_session)]
Client = Annotated[str, Depends(client_id)]


# --- errors -----------------------------------------------------------------


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message})


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        error = exc.detail
    else:
        codes = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed", 413: "too_large"}
        error = {"code": codes.get(exc.status_code, "error"), "message": str(exc.detail)}
    return JSONResponse({"error": error}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    error = {"code": "invalid_request", "message": "request is invalid", "details": exc.errors()}
    return JSONResponse({"error": jsonable_encoder(error)}, status_code=400)


# --- helpers ----------------------------------------------------------------


def own_document(db: Session, client: str, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.client_id != client:
        raise api_error(404, "not_found", "document not found")
    return document


def own_grid(db: Session, client: str, ref: str) -> Grid:
    grid = latest_grid(db, client, ref)
    if grid is None:
        raise api_error(404, "grid_not_found", f"no grid for {ref!r}")
    return grid


def grid_ref_of(document: Document, given: str | None) -> str:
    ref = given or document.grid_ref
    if not ref:
        raise api_error(400, "grid_ref_required", "this document has no grid_ref; pass one")
    return ref


def document_out(d: Document) -> schemas.DocumentOut:
    return schemas.DocumentOut(
        id=d.id,
        external_ref=d.external_ref,
        grid_ref=d.grid_ref,
        filename=d.filename,
        size=d.size,
        status=d.status,
        error=d.error,
        ocr_used=d.ocr_used,
        pages=d.pages,
        created_at=d.created_at,
        processed_at=d.processed_at,
    )


def grid_out(g: Grid) -> schemas.GridOut:
    return schemas.GridOut(
        external_ref=g.external_ref, version=g.version, criteria=g.criteria, settings=g.settings, created_at=g.created_at
    )


def analysis_out(a: Analysis, g: Grid) -> schemas.AnalysisOut:
    return schemas.AnalysisOut(
        id=a.id,
        document_id=a.document_id,
        grid_ref=g.external_ref,
        grid_version=g.version,
        analyzer=a.analyzer,
        analyzer_version=a.analyzer_version,
        score=a.score,
        details=a.details,
        created_at=a.created_at,
    )


def highlight_out(h: Highlight) -> schemas.HighlightOut:
    return schemas.HighlightOut(
        id=h.id,
        document_id=h.document_id,
        grid_ref=h.grid_ref,
        author_ref=h.author_ref,
        start=h.start,
        end=h.end,
        quote=h.quote,
        points=h.points,
        comment=h.comment,
        created_at=h.created_at,
    )


def latest_analyses(db: Session, grid: Grid, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, Analysis]:
    """The newest default-analyzer result per document for this grid version."""
    rows = db.scalars(
        select(Analysis)
        .where(Analysis.grid_id == grid.id, Analysis.document_id.in_(document_ids), Analysis.analyzer == DEFAULT_ANALYZER)
        .order_by(Analysis.created_at)
    )
    return {a.document_id: a for a in rows}


def highlights_of(db: Session, ref: str, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Highlight]]:
    out: dict[uuid.UUID, list[Highlight]] = {}
    rows = db.scalars(
        select(Highlight)
        .where(Highlight.grid_ref == ref, Highlight.document_id.in_(document_ids))
        .order_by(Highlight.start, Highlight.created_at)
    )
    for h in rows:
        out.setdefault(h.document_id, []).append(h)
    return out


# --- service ----------------------------------------------------------------


@app.get("/health", tags=["service"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/analyzers", response_model=list[schemas.AnalyzerOut], tags=["service"])
def list_analyzers(_: Client) -> list[schemas.AnalyzerOut]:
    return [schemas.AnalyzerOut(name=a.name, version=a.version, description=a.description) for a in ANALYZERS.values()]


# --- documents --------------------------------------------------------------


@app.post("/v1/documents", response_model=schemas.DocumentOut, status_code=202, tags=["documents"])
async def upload_document(
    db: Db,
    client: Client,
    file: Annotated[UploadFile, File(description="The CV, a PDF")],
    external_ref: Annotated[str | None, Form(max_length=200, description="Your id for this CV")] = None,
    grid_ref: Annotated[str | None, Form(max_length=200, description="Score with this grid once read")] = None,
) -> schemas.DocumentOut:
    """Stores a CV and queues it to be read. Poll GET /v1/documents/{id} or wait for the webhook."""
    data = await file.read(settings.max_pdf_bytes + 1)
    if len(data) > settings.max_pdf_bytes:
        raise api_error(413, "file_too_large", f"the PDF must be {settings.max_pdf_bytes // (1024 * 1024)} MB or less")
    if not data.startswith(b"%PDF-"):
        raise api_error(415, "not_a_pdf", "the file must be a PDF")
    document = Document(
        id=uuid.uuid4(),
        client_id=client,
        external_ref=external_ref or None,
        grid_ref=grid_ref or None,
        filename=(file.filename or "cv.pdf")[:255],
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    document.storage_key = f"{client}/{document.id}.pdf"
    storage.put(document.storage_key, data)
    db.add(document)
    db.commit()
    db.refresh(document)
    enqueue("extract", document_id=document.id)
    return document_out(document)


@app.get("/v1/documents", response_model=list[schemas.DocumentOut], tags=["documents"])
def list_documents(
    db: Db,
    client: Client,
    external_ref: str | None = None,
    grid_ref: str | None = None,
    status_: Annotated[schemas.DocumentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[schemas.DocumentOut]:
    query = select(Document).where(Document.client_id == client).order_by(Document.created_at.desc()).limit(limit)
    if external_ref is not None:
        query = query.where(Document.external_ref == external_ref)
    if grid_ref is not None:
        query = query.where(Document.grid_ref == grid_ref)
    if status_ is not None:
        query = query.where(Document.status == status_)
    return [document_out(d) for d in db.scalars(query)]


@app.get("/v1/documents/{document_id}", response_model=schemas.DocumentDetail, tags=["documents"])
def read_document(document_id: uuid.UUID, db: Db, client: Client) -> schemas.DocumentDetail:
    """The CV's status, then its text line by line, each line with its section and position."""
    d = own_document(db, client, document_id)
    return schemas.DocumentDetail(
        **document_out(d).model_dump(),
        text=d.text,
        lines=[
            schemas.LineOut(n=ln.n, page=ln.page, section=ln.section, text=ln.text, start=ln.start, end=ln.end, bbox=ln.bbox)
            for ln in d.lines
        ],
    )


@app.get(
    "/v1/documents/{document_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    tags=["documents"],
)
def download_document(document_id: uuid.UUID, db: Db, client: Client) -> Response:
    d = own_document(db, client, document_id)
    return Response(
        storage.get(d.storage_key),
        media_type="application/pdf",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@app.delete("/v1/documents/{document_id}", status_code=204, tags=["documents"])
def delete_document(document_id: uuid.UUID, db: Db, client: Client) -> Response:
    """Erases the CV for good: the PDF, its text, its scores and its highlights (GDPR)."""
    d = own_document(db, client, document_id)
    storage.delete(d.storage_key)
    db.delete(d)
    db.commit()
    return Response(status_code=204)


# --- grids ------------------------------------------------------------------


@app.post("/v1/grids/suggest", response_model=schemas.GridIn, tags=["grids"])
def suggest_grid(body: schemas.SuggestIn, _: Client) -> schemas.GridIn:
    """A starting grid from skills ranked by priority, plus warning words. Nothing is saved.

    Priority 1 (core): +1 when present, -20 when missing. 2: +0.5. 3: +0.1.
    4 (CV only): +0.5. 5 (bonus): +0.1. Each warning word: -5 when present.
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

    for skill in sorted(body.skills, key=lambda s: s.priority):
        present, absent = PRIORITY_POINTS[skill.priority]
        criteria.append(
            schemas.Criterion(id=slug(skill.name), label=skill.name, points_present=present, points_absent=absent)
        )
    for word in body.alerts:
        criteria.append(
            schemas.Criterion(
                id=slug(word), label=word, kind="alert", default_synonyms=False, points_present=ALERT_POINTS
            )
        )
    return schemas.GridIn(criteria=criteria)


@app.put("/v1/grids/{ref}", response_model=schemas.GridOut, tags=["grids"])
def save_grid(ref: str, body: schemas.GridIn, db: Db, client: Client) -> schemas.GridOut:
    """Saves a new version of the grid for ref (RecruteHub: an offer) and rescores its CVs."""
    if len(ref) > 200:
        raise api_error(400, "invalid_request", "ref is longer than 200 characters")
    previous = latest_grid(db, client, ref)
    data = body.model_dump()
    grid = Grid(
        client_id=client,
        external_ref=ref,
        version=(previous.version + 1) if previous else 1,
        criteria=data["criteria"],
        settings=data["settings"],
    )
    db.add(grid)
    db.commit()
    db.refresh(grid)
    ready = db.scalars(
        select(Document.id).where(Document.client_id == client, Document.grid_ref == ref, Document.status == "ready")
    )
    for document_id in ready:
        enqueue("analyze", document_id=document_id, grid_id=grid.id)
    return grid_out(grid)


@app.get("/v1/grids/{ref}", response_model=schemas.GridOut, tags=["grids"])
def read_grid(ref: str, db: Db, client: Client) -> schemas.GridOut:
    return grid_out(own_grid(db, client, ref))


@app.get("/v1/grids/{ref}/ranking", response_model=list[schemas.RankingRow], tags=["grids"])
def ranking(ref: str, db: Db, client: Client) -> list[schemas.RankingRow]:
    """Every CV sent with this grid_ref, best final score first; CVs not scored yet come last."""
    grid = own_grid(db, client, ref)
    documents = list(db.scalars(select(Document).where(Document.client_id == client, Document.grid_ref == ref)))
    ids = [d.id for d in documents]
    analyses, highlights = latest_analyses(db, grid, ids), highlights_of(db, ref, ids)
    rows = []
    for d in documents:
        a = analyses.get(d.id)
        auto = a.score if a else None
        manual = manual_score([h.points for h in highlights.get(d.id, [])], grid.settings)
        missing = [
            c["label"]
            for c in (a.details.get("criteria", []) if a else [])
            if not c["found"] and c["points"] < 0
        ]
        rows.append(
            schemas.RankingRow(
                rank=None,
                document_id=d.id,
                external_ref=d.external_ref,
                status=d.status,
                auto=auto,
                manual=manual,
                final=final_score(auto, manual, grid.settings),
                missing=missing,
            )
        )
    rows.sort(key=lambda r: (r.final is None, -(r.final or 0)))
    for i, r in enumerate(rows):
        r.rank = i + 1 if r.final is not None else None
    return rows


# --- analyses ---------------------------------------------------------------


@app.post(
    "/v1/documents/{document_id}/analyses", response_model=schemas.AnalysisOut, status_code=201, tags=["scores"]
)
def analyze_document(
    document_id: uuid.UUID, db: Db, client: Client, body: schemas.AnalyzeIn | None = None
) -> schemas.AnalysisOut:
    """Scores a read CV now with the latest version of a grid."""
    body = body or schemas.AnalyzeIn()
    d = own_document(db, client, document_id)
    if d.status != "ready":
        raise api_error(409, "not_ready", f"the document is {d.status}, not ready")
    if body.analyzer not in ANALYZERS:
        raise api_error(400, "unknown_analyzer", f"analyzers: {', '.join(ANALYZERS)}")
    grid = own_grid(db, client, grid_ref_of(d, body.grid_ref))
    return analysis_out(analyze(db, d, grid, body.analyzer), grid)


@app.get("/v1/documents/{document_id}/analyses", response_model=list[schemas.AnalysisOut], tags=["scores"])
def list_analyses(document_id: uuid.UUID, db: Db, client: Client) -> list[schemas.AnalysisOut]:
    """Every score this CV got, newest first, across grid versions and analyzers."""
    own_document(db, client, document_id)
    rows = db.execute(
        select(Analysis, Grid)
        .join(Grid, Grid.id == Analysis.grid_id)
        .where(Analysis.document_id == document_id)
        .order_by(Analysis.created_at.desc())
    )
    return [analysis_out(a, g) for a, g in rows]


# --- highlights -------------------------------------------------------------


@app.post(
    "/v1/documents/{document_id}/highlights", response_model=schemas.HighlightOut, status_code=201, tags=["highlights"]
)
def add_highlight(document_id: uuid.UUID, body: schemas.HighlightIn, db: Db, client: Client) -> schemas.HighlightOut:
    """A recruiter marks a passage (a character range, or a whole line) as worth 1 to 5 points."""
    d = own_document(db, client, document_id)
    if d.status != "ready" or not d.text:
        raise api_error(409, "not_ready", f"the document is {d.status}, not ready")
    if body.line is not None:
        line = next((ln for ln in d.lines if ln.n == body.line), None)
        if line is None:
            raise api_error(400, "invalid_range", f"the document has no line {body.line}")
        start, end = line.start, line.end
    else:
        start, end = body.start, body.end
    if end > len(d.text):
        raise api_error(400, "invalid_range", f"end is past the text, which has {len(d.text)} characters")
    quote = d.text[start:end]
    if not quote.strip():
        raise api_error(400, "invalid_range", "the passage is empty")
    h = Highlight(
        document_id=d.id,
        grid_ref=grid_ref_of(d, body.grid_ref),
        author_ref=body.author_ref,
        start=start,
        end=end,
        quote=quote,
        points=body.points,
        comment=body.comment,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return highlight_out(h)


@app.get("/v1/documents/{document_id}/highlights", response_model=list[schemas.HighlightOut], tags=["highlights"])
def list_highlights(
    document_id: uuid.UUID, db: Db, client: Client, grid_ref: str | None = None
) -> list[schemas.HighlightOut]:
    d = own_document(db, client, document_id)
    return [highlight_out(h) for h in highlights_of(db, grid_ref_of(d, grid_ref), [d.id]).get(d.id, [])]


@app.delete("/v1/highlights/{highlight_id}", status_code=204, tags=["highlights"])
def delete_highlight(highlight_id: uuid.UUID, db: Db, client: Client) -> Response:
    h = db.get(Highlight, highlight_id)
    if h is None or db.get(Document, h.document_id).client_id != client:
        raise api_error(404, "not_found", "highlight not found")
    db.delete(h)
    db.commit()
    return Response(status_code=204)


# --- scores -----------------------------------------------------------------


@app.get("/v1/documents/{document_id}/score", response_model=schemas.ScoreOut, tags=["scores"])
def document_score(document_id: uuid.UUID, db: Db, client: Client, grid_ref: str | None = None) -> schemas.ScoreOut:
    """The automatic, manual and final scores for one CV, with every point explained."""
    d = own_document(db, client, document_id)
    ref = grid_ref_of(d, grid_ref)
    grid = own_grid(db, client, ref)
    a = latest_analyses(db, grid, [d.id]).get(d.id)
    marks = highlights_of(db, ref, [d.id]).get(d.id, [])
    auto = a.score if a else None
    manual = manual_score([h.points for h in marks], grid.settings)
    return schemas.ScoreOut(
        document_id=d.id,
        external_ref=d.external_ref,
        grid_ref=ref,
        grid_version=grid.version if a else None,
        auto=auto,
        manual=manual,
        final=final_score(auto, manual, grid.settings),
        manual_points=sum(h.points for h in marks),
        analysis=analysis_out(a, grid) if a else None,
        highlights=[highlight_out(h) for h in marks],
    )
