"""Worker: reads PDFs and scores them, off the request path.

    python -m worker.main
"""
from __future__ import annotations

import logging
import signal
import time
import uuid
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import select, update

from analysis import extract as extracting
from analysis.analyzers import ANALYZERS, DEFAULT_ANALYZER, CvLine
from core import storage, webhooks
from core.db import SessionLocal
from core.models import Analysis, Document, DocumentLine, Grid
from core.queue import dequeue, enqueue

log = logging.getLogger("cva.worker")
SWEEP_EVERY_S = 60
# A document still processing after this was lost with its worker.
STALE_PROCESSING = timedelta(minutes=10)


def latest_grid(session, offer_id: uuid.UUID) -> Grid | None:
    return session.scalar(select(Grid).where(Grid.offer_id == offer_id).order_by(Grid.version.desc()).limit(1))


def analyze(session, document: Document, grid: Grid, analyzer: str = DEFAULT_ANALYZER) -> Analysis:
    """Scores a read document against a grid version and stores the result."""
    lines = [CvLine(line.n, line.section, line.text) for line in document.lines]
    engine = ANALYZERS[analyzer]
    result = engine.analyze(lines, grid.criteria, grid.settings)
    row = Analysis(
        document_id=document.id,
        grid_id=grid.id,
        analyzer=engine.name,
        analyzer_version=engine.version,
        score=result.score,
        details=result.details,
    )
    session.add(row)
    session.commit()
    webhooks.send(
        document.client_id,
        "analysis.done",
        {
            "document_id": str(document.id),
            "external_ref": document.external_ref,
            "offer_ref": grid.offer.external_ref,
            "grid_version": grid.version,
            "analyzer": engine.name,
            "score": result.score,
        },
    )
    return row


def process_extract(document_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        claimed = session.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "queued")
            .values(status="processing", started_at=datetime.now(timezone.utc))
        )
        session.commit()
        if claimed.rowcount != 1:
            return
        document = session.get(Document, document_id)
        try:
            result = extracting.extract(storage.get(document.storage_key))
        except Exception as exc:  # a broken PDF, or storage unreachable
            log.exception("document %s failed", document_id)
            document.status, document.error = "failed", str(exc)[:2000]
        else:
            document.pages, document.ocr_used, document.text = result.pages, result.ocr_used, result.text
            document.lines = [
                DocumentLine(
                    n=i, page=ln.page, section=ln.section, text=ln.text, start=ln.start, end=ln.end, bbox=ln.bbox
                )
                for i, ln in enumerate(result.lines)
            ]
            document.status = "ready" if result.readable else "unreadable"
        document.processed_at = datetime.now(timezone.utc)
        session.commit()
        log.info("document %s: %s", document_id, document.status)
        webhooks.send(
            document.client_id,
            "document.processed",
            {
                "document_id": str(document.id),
                "external_ref": document.external_ref,
                "offer_ref": document.offer.external_ref,
                "status": document.status,
            },
        )
        if document.status == "ready":
            analyze(session, document, latest_grid(session, document.offer_id))


def process_analyze(document_id: uuid.UUID, grid_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        document, grid = session.get(Document, document_id), session.get(Grid, grid_id)
        if document is None or grid is None or document.status != "ready" or grid.offer_id != document.offer_id:
            return
        analyze(session, document, grid)


def process(job: dict) -> None:
    if job["type"] == "extract":
        process_extract(uuid.UUID(job["document_id"]))
    elif job["type"] == "analyze":
        process_analyze(uuid.UUID(job["document_id"]), uuid.UUID(job["grid_id"]))
    else:
        log.warning("unknown job %s", job)


def recover_lost_jobs() -> int:
    """Put back documents a dead worker left half read."""
    cutoff = datetime.now(timezone.utc) - STALE_PROCESSING
    with SessionLocal() as session:
        stale = session.scalars(
            select(Document).where(Document.status == "processing", Document.started_at < cutoff)
        ).all()
        for document in stale:
            document.status = "queued"
            session.commit()
            enqueue("extract", document_id=document.id)
        return len(stale)


def rescore_outdated(limit: int = 200) -> int:
    """Score again the read CVs the current analyzer version has not scored yet, e.g. after an upgrade."""
    engine = ANALYZERS[DEFAULT_ANALYZER]
    current = select(Analysis.id).where(
        Analysis.document_id == Document.id,
        Analysis.analyzer == engine.name,
        Analysis.analyzer_version == engine.version,
    )
    with SessionLocal() as session:
        outdated = session.scalars(
            select(Document).where(Document.status == "ready", ~current.exists()).limit(limit)
        ).all()
        for document in outdated:
            analyze(session, document, latest_grid(session, document.offer_id))
        return len(outdated)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker started")
    last_sweep = datetime.min.replace(tzinfo=timezone.utc)
    while not stopping:
        now = datetime.now(timezone.utc)
        if (now - last_sweep).total_seconds() >= SWEEP_EVERY_S:
            if count := recover_lost_jobs():
                log.warning("requeued %s lost documents", count)
            if count := rescore_outdated():
                log.info("scored %s CVs again with %s %s", count, DEFAULT_ANALYZER, ANALYZERS[DEFAULT_ANALYZER].version)
            last_sweep = now
        try:
            job = dequeue(timeout=5)
        except redis.RedisError:
            log.exception("queue unreachable, retrying")
            time.sleep(2)
            continue
        if job is None:
            continue
        try:
            process(job)
        except Exception:
            log.exception("job failed: %s", job)


if __name__ == "__main__":
    main()
