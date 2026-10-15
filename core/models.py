"""Tables. Offers and candidates live in the caller (RecruteHub); here they are references."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base, Json

DOCUMENT_STATUSES = ("queued", "processing", "ready", "unreadable", "failed")


class Document(Base):
    """One CV a client sent."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(f"status IN {DOCUMENT_STATUSES}", name="ck_documents_status"),
        # Full-text search over CVs, for a later search endpoint.
        Index(
            "ix_documents_text_search",
            sql_text("to_tsvector('simple', coalesce(text, ''))"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    # Every CV is sent for one offer, and scored with that offer's grid.
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), index=True)
    # The caller's id for this CV (RecruteHub: the candidate).
    external_ref: Mapped[str | None] = mapped_column(String(200), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    pages: Mapped[int | None] = mapped_column(Integer)
    # The whole extracted text; lines and highlights point into it by character offset.
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    offer: Mapped[Offer] = relationship(back_populates="documents")
    lines: Mapped[list[DocumentLine]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentLine.n", passive_deletes=True
    )


class DocumentLine(Base):
    __tablename__ = "document_lines"
    __table_args__ = (UniqueConstraint("document_id", "n", name="uq_document_lines_n"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    n: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    # header, summary, experience, education, skills, projects, languages, certifications, interests
    section: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    # [x0, top, x1, bottom] in PDF points on its page; None for OCR lines.
    bbox: Mapped[list | None] = mapped_column(Json)

    document: Mapped[Document] = relationship(back_populates="lines")


class Offer(Base):
    """A job offer, as the caller defines it (RecruteHub: job_offers). Its grid is versioned apart."""

    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("client_id", "external_ref", name="uq_offers_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    # The caller's id for the offer (RecruteHub: job_offers.id).
    external_ref: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(255))
    # As the caller ranks them: [{"name": "python", "priority": 1}, ...]; the grid is built from them.
    skills: Mapped[list] = mapped_column(Json)
    alerts: Mapped[list] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    documents: Mapped[list[Document]] = relationship(back_populates="offer", passive_deletes=True)


class Grid(Base):
    """One version of an offer's scoring grid. A change adds a version; old analyses keep theirs."""

    __tablename__ = "grids"
    __table_args__ = (UniqueConstraint("offer_id", "version", name="uq_grids_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(Json)
    settings: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    offer: Mapped[Offer] = relationship()


class Analysis(Base):
    """An automatic score of one document against one grid version."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    grid_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grids.id", ondelete="CASCADE"), index=True)
    analyzer: Mapped[str] = mapped_column(String(40))
    analyzer_version: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Highlight(Base):
    """A passage a recruiter marked as worth points, for the CV's offer whatever the grid version."""

    __tablename__ = "highlights"
    __table_args__ = (
        CheckConstraint("points BETWEEN 1 AND 5", name="ck_highlights_points"),
        CheckConstraint('start >= 0 AND "end" > start', name="ck_highlights_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    author_ref: Mapped[str] = mapped_column(String(200))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
