"""The /v1 REST API: CVs in, text and scores out, highlights from recruiters."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analysis.analyzers import ANALYZERS, DEFAULT_ANALYZER
from analysis.scoring import final_score, grid_from, manual_score
from analysis.text import locate
from api import schemas
from api.auth import client_id
from core import storage
from core.config import settings
from core.db import get_session
from core.models import Analysis, Document, Grid, Highlight, Offer
from core.queue import enqueue
from worker.main import analyze, latest_grid

app = FastAPI(
    title="CV Analyzer API",
    version="0.1.0",
    description="Reads CVs (PDF, scanned or not), scores each against the offer it was sent for, "
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


def find_offer(db: Session, client: str, ref: str) -> Offer | None:
    return db.scalar(select(Offer).where(Offer.client_id == client, Offer.external_ref == ref))


def own_offer(db: Session, client: str, ref: str) -> Offer:
    offer = find_offer(db, client, ref)
    if offer is None:
        raise api_error(404, "offer_not_found", f"no offer {ref!r}; create it with PUT /v1/offers/{ref}")
    return offer


def document_out(d: Document) -> schemas.DocumentOut:
    return schemas.DocumentOut(
        id=d.id,
        offer_ref=d.offer.external_ref,
        external_ref=d.external_ref,
        filename=d.filename,
        size=d.size,
        status=d.status,
        error=d.error,
        ocr_used=d.ocr_used,
        pages=d.pages,
        created_at=d.created_at,
        processed_at=d.processed_at,
    )


def offer_out(o: Offer, g: Grid) -> schemas.OfferOut:
    return schemas.OfferOut(
        external_ref=o.external_ref,
        title=o.title,
        skills=o.skills,
        grid_version=g.version,
        criteria=g.criteria,
        settings=g.settings,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def analysis_out(a: Analysis, g: Grid) -> schemas.AnalysisOut:
    return schemas.AnalysisOut(
        id=a.id,
        document_id=a.document_id,
        offer_ref=g.offer.external_ref,
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
        author_ref=h.author_ref,
        start=h.start,
        end=h.end,
        quote=h.quote,
        boxes=h.boxes or [],
        points=h.points,
        comment=h.comment,
        created_at=h.created_at,
    )


def line_boxes(d: Document, start: int, end: int) -> list[dict]:
    """The boxes of the lines a passage covers (OCR lines have none)."""
    return [
        {"page": ln.page, "x0": ln.bbox[0], "top": ln.bbox[1], "x1": ln.bbox[2], "bottom": ln.bbox[3]}
        for ln in d.lines
        if ln.bbox and ln.start < end and ln.end > start
    ]


def latest_analyses(db: Session, grid: Grid, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, Analysis]:
    """The newest default-analyzer result per document for this grid version."""
    rows = db.scalars(
        select(Analysis)
        .where(Analysis.grid_id == grid.id, Analysis.document_id.in_(document_ids), Analysis.analyzer == DEFAULT_ANALYZER)
        .order_by(Analysis.created_at)
    )
    return {a.document_id: a for a in rows}


def highlights_of(db: Session, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Highlight]]:
    out: dict[uuid.UUID, list[Highlight]] = {}
    rows = db.scalars(
        select(Highlight)
        .where(Highlight.document_id.in_(document_ids))
        .order_by(Highlight.start, Highlight.created_at)
    )
    for h in rows:
        out.setdefault(h.document_id, []).append(h)
    return out


# --- service ----------------------------------------------------------------


# The web app (web/, built into web/dist): offers, CVs, and scoring passages in the PDF.
WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if WEB_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/app/")


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
    offer_ref: Annotated[str, Form(min_length=1, max_length=200, description="The offer this CV applies to")],
    external_ref: Annotated[str | None, Form(max_length=200, description="Your id for this CV")] = None,
) -> schemas.DocumentOut:
    """Stores a CV sent for an offer and queues it to be read, then scored against that offer.

    Poll GET /v1/documents/{id} or wait for the webhooks.
    """
    offer = own_offer(db, client, offer_ref)
    data = await file.read(settings.max_pdf_bytes + 1)
    if len(data) > settings.max_pdf_bytes:
        raise api_error(413, "file_too_large", f"the PDF must be {settings.max_pdf_bytes // (1024 * 1024)} MB or less")
    if not data.startswith(b"%PDF-"):
        raise api_error(415, "not_a_pdf", "the file must be a PDF")
    document = Document(
        id=uuid.uuid4(),
        client_id=client,
        offer=offer,
        external_ref=external_ref or None,
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
    offer_ref: str | None = None,
    external_ref: str | None = None,
    status_: Annotated[schemas.DocumentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[schemas.DocumentOut]:
    query = select(Document).where(Document.client_id == client).order_by(Document.created_at.desc()).limit(limit)
    if external_ref is not None:
        query = query.where(Document.external_ref == external_ref)
    if offer_ref is not None:
        offer = find_offer(db, client, offer_ref)
        query = query.where(Document.offer_id == (offer.id if offer else None))
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


# --- offers -----------------------------------------------------------------


@app.get("/v1/offers", response_model=list[schemas.OfferSummary], tags=["offers"])
def list_offers(db: Db, client: Client) -> list[schemas.OfferSummary]:
    """The client's offers, last updated first, with how many CVs each has."""
    counts = dict(
        db.execute(
            select(Document.offer_id, func.count()).where(Document.client_id == client).group_by(Document.offer_id)
        ).all()
    )
    offers = db.scalars(select(Offer).where(Offer.client_id == client).order_by(Offer.updated_at.desc()))
    return [
        schemas.OfferSummary(external_ref=o.external_ref, title=o.title, documents=counts.get(o.id, 0), updated_at=o.updated_at)
        for o in offers
    ]


@app.put("/v1/offers/{ref}", response_model=schemas.OfferOut, tags=["offers"])
def save_offer(ref: str, body: schemas.OfferIn, db: Db, client: Client) -> schemas.OfferOut:
    """Creates or updates the offer ref (RecruteHub: the job offer's id).

    Without criteria, the grid is built from the skills and their priorities. When the grid
    changes it gets a new version and every CV read for the offer is scored again.
    """
    if len(ref) > 200:
        raise api_error(400, "invalid_request", "ref is longer than 200 characters")
    data = body.model_dump()
    offer = find_offer(db, client, ref)
    if offer is None:
        offer = Offer(client_id=client, external_ref=ref)
        db.add(offer)
    offer.title, offer.skills = data["title"], data["skills"]
    criteria = data["criteria"] if body.criteria is not None else grid_from(data["skills"])
    db.flush()
    grid = latest_grid(db, offer.id)
    changed = grid is None or (grid.criteria, grid.settings) != (criteria, data["settings"])
    if changed:
        grid = Grid(offer=offer, version=grid.version + 1 if grid else 1, criteria=criteria, settings=data["settings"])
        db.add(grid)
    db.commit()
    db.refresh(offer)
    if changed:
        ready = db.scalars(select(Document.id).where(Document.offer_id == offer.id, Document.status == "ready"))
        for document_id in ready:
            enqueue("analyze", document_id=document_id, grid_id=grid.id)
    return offer_out(offer, grid)


@app.get("/v1/offers/{ref}", response_model=schemas.OfferOut, tags=["offers"])
def read_offer(ref: str, db: Db, client: Client) -> schemas.OfferOut:
    offer = own_offer(db, client, ref)
    return offer_out(offer, latest_grid(db, offer.id))


@app.delete("/v1/offers/{ref}", status_code=204, tags=["offers"])
def delete_offer(ref: str, db: Db, client: Client) -> Response:
    """Erases the offer and every CV sent for it, with their scores and highlights."""
    offer = own_offer(db, client, ref)
    for key in db.scalars(select(Document.storage_key).where(Document.offer_id == offer.id)):
        storage.delete(key)
    db.delete(offer)
    db.commit()
    return Response(status_code=204)


@app.get("/v1/offers/{ref}/ranking", response_model=list[schemas.RankingRow], tags=["offers"])
def ranking(ref: str, db: Db, client: Client) -> list[schemas.RankingRow]:
    """Every CV sent for this offer, best final score first; CVs not scored yet come last."""
    offer = own_offer(db, client, ref)
    grid = latest_grid(db, offer.id)
    documents = list(db.scalars(select(Document).where(Document.offer_id == offer.id)))
    ids = [d.id for d in documents]
    analyses, highlights = latest_analyses(db, grid, ids), highlights_of(db, ids)
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
                filename=d.filename,
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
    """Scores a read CV now against the latest grid of its offer, e.g. with another analyzer."""
    body = body or schemas.AnalyzeIn()
    d = own_document(db, client, document_id)
    if d.status != "ready":
        raise api_error(409, "not_ready", f"the document is {d.status}, not ready")
    if body.analyzer not in ANALYZERS:
        raise api_error(400, "unknown_analyzer", f"analyzers: {', '.join(ANALYZERS)}")
    grid = latest_grid(db, d.offer_id)
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
    """A recruiter marks a passage as worth 1 to 5 points.

    The passage is the text selected in the PDF (`quote`, with its `page`), a character
    range, or a whole line. Pass the selection's `boxes` to draw it back exactly.
    """
    d = own_document(db, client, document_id)
    if d.status != "ready" or not d.text:
        raise api_error(409, "not_ready", f"the document is {d.status}, not ready")
    if body.line is not None:
        line = next((ln for ln in d.lines if ln.n == body.line), None)
        if line is None:
            raise api_error(400, "invalid_range", f"the document has no line {body.line}")
        start, end = line.start, line.end
    elif body.quote is not None:
        on_page = [ln for ln in d.lines if ln.page == body.page]
        within = (on_page[0].start, on_page[-1].end + 1) if on_page else None
        found = locate(d.text, body.quote, within)
        if found is None:
            raise api_error(400, "quote_not_found", "the selected text was not found in the CV's text")
        start, end = found
    else:
        start, end = body.start, body.end
    if end > len(d.text):
        raise api_error(400, "invalid_range", f"end is past the text, which has {len(d.text)} characters")
    quote = d.text[start:end]
    if not quote.strip():
        raise api_error(400, "invalid_range", "the passage is empty")
    h = Highlight(
        document_id=d.id,
        author_ref=body.author_ref,
        start=start,
        end=end,
        quote=quote,
        boxes=[b.model_dump() for b in body.boxes] if body.boxes else line_boxes(d, start, end),
        points=body.points,
        comment=body.comment,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return highlight_out(h)


@app.get("/v1/documents/{document_id}/highlights", response_model=list[schemas.HighlightOut], tags=["highlights"])
def list_highlights(document_id: uuid.UUID, db: Db, client: Client) -> list[schemas.HighlightOut]:
    d = own_document(db, client, document_id)
    return [highlight_out(h) for h in highlights_of(db, [d.id]).get(d.id, [])]


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
def document_score(document_id: uuid.UUID, db: Db, client: Client) -> schemas.ScoreOut:
    """The automatic, manual and final scores of one CV for its offer, with every point explained."""
    d = own_document(db, client, document_id)
    grid = latest_grid(db, d.offer_id)
    a = latest_analyses(db, grid, [d.id]).get(d.id)
    marks = highlights_of(db, [d.id]).get(d.id, [])
    auto = a.score if a else None
    manual = manual_score([h.points for h in marks], grid.settings)
    return schemas.ScoreOut(
        document_id=d.id,
        offer_ref=d.offer.external_ref,
        external_ref=d.external_ref,
        grid_version=grid.version if a else None,
        auto=auto,
        manual=manual,
        final=final_score(auto, manual, grid.settings),
        manual_points=sum(h.points for h in marks),
        settings=grid.settings,
        analysis=analysis_out(a, grid) if a else None,
        highlights=[highlight_out(h) for h in marks],
    )
