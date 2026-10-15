from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from analysis.text import normalize

Ref = Annotated[str, Field(min_length=1, max_length=200)]
Slug = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9_.+#/-]*$")]
Term = Annotated[str, Field(min_length=1, max_length=80)]


# --- offers and their grids ------------------------------------------------------------------


class Criterion(BaseModel):
    id: Slug
    label: Term = Field(description="What the recruiter reads, e.g. Python. Also searched for.")
    terms: list[Term] = Field(default=[], max_length=40, description="Extra words that count as this criterion")
    default_synonyms: bool = Field(default=True, description="Also search the engine's synonyms for the label")
    points_present: float = Field(default=1.0, ge=0, le=50, description="Points when found")
    points_absent: float = Field(default=0.0, ge=-50, le=0, description="Points lost when missing (core skills)")


class SkillIn(BaseModel):
    name: Term = Field(validation_alias=AliasChoices("name", "language"), description="RecruteHub's language works too")
    priority: int = Field(ge=1, le=5, description="1 core, 2 important, 3 secondary, 4 CV only, 5 bonus")


def check_distinct(criteria: list[Criterion]) -> None:
    ids = [c.id for c in criteria]
    if len(ids) != len(set(ids)):
        raise ValueError("each criterion id appears once in a grid")


class OfferIn(BaseModel):
    """An offer as RecruteHub defines it. Without criteria, the grid is built from the skills."""

    title: Annotated[str, Field(min_length=1, max_length=255)]
    skills: list[SkillIn] = Field(default=[], max_length=60)
    criteria: list[Criterion] | None = Field(
        default=None, max_length=100, description="The grid, edited by a recruiter; built from skills when left out"
    )

    @model_validator(mode="after")
    def coherent(self) -> OfferIn:
        names = [normalize(s.name) for s in self.skills]
        if len(names) != len(set(names)):
            raise ValueError("each skill appears once in an offer")
        if self.criteria is not None:
            check_distinct(self.criteria)
        return self


class OfferSummary(BaseModel):
    external_ref: str
    title: str
    documents: int
    updated_at: datetime


class OfferOut(BaseModel):
    external_ref: str
    title: str
    skills: list[SkillIn]
    grid_version: int
    criteria: list[Criterion]
    created_at: datetime
    updated_at: datetime


# --- documents --------------------------------------------------------------

DocumentStatus = Literal["queued", "processing", "ready", "unreadable", "failed"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    offer_ref: str
    external_ref: str | None
    filename: str
    size: int
    status: DocumentStatus
    error: str | None
    ocr_used: bool
    pages: int | None
    created_at: datetime
    processed_at: datetime | None


class LineOut(BaseModel):
    n: int
    page: int
    section: str
    text: str
    start: int
    end: int
    bbox: list[float] | None


class DocumentDetail(DocumentOut):
    text: str | None
    lines: list[LineOut]


# --- analyses, highlights, scores ------------------------------------------


class AnalyzeIn(BaseModel):
    analyzer: str = "keywords"


class AnalysisOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    offer_ref: str
    grid_version: int
    analyzer: str
    analyzer_version: str
    score: float
    details: dict
    created_at: datetime


class Box(BaseModel):
    """A rectangle on a page, in PDF points from the page's top left corner."""

    page: int = Field(ge=1)
    x0: float
    top: float
    x1: float
    bottom: float


class HighlightIn(BaseModel):
    author_ref: Ref = Field(description="Who highlighted, in the caller's terms (RecruteHub: the user id)")
    quote: str | None = Field(
        default=None, max_length=5000, description="The text selected in the PDF; the engine finds it in the CV"
    )
    page: int | None = Field(default=None, ge=1, description="The page the quote was selected on")
    start: int | None = Field(default=None, ge=0, description="Or a character range in the document text")
    end: int | None = Field(default=None, ge=1)
    line: int | None = Field(default=None, ge=0, description="Or a whole line, by its number")
    boxes: list[Box] | None = Field(
        default=None, max_length=100, description="Where the selection is drawn on the PDF; from the lines if left out"
    )
    points: int = Field(ge=-100, le=100, description="What the passage is worth, -100 to 100; negative for a red flag")
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def one_target(self) -> HighlightIn:
        if self.points == 0:
            raise ValueError("points cannot be 0")
        has_range = self.start is not None and self.end is not None
        targets = [has_range, self.line is not None, self.quote is not None]
        if sum(targets) != 1:
            raise ValueError("give one of quote, start and end, or line")
        if has_range and self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class HighlightOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    author_ref: str
    start: int
    end: int
    quote: str
    boxes: list[Box]
    points: int
    comment: str | None
    created_at: datetime


class ScoreOut(BaseModel):
    document_id: uuid.UUID
    offer_ref: str
    external_ref: str | None
    grid_version: int | None = Field(description="The grid version the keyword points used")
    auto: float | None = Field(description="Keyword points; null until the CV is read and scored")
    manual: int = Field(description="The sum of the recruiters' points, negative for red flags")
    total: float | None = Field(description="auto + manual, unbounded; null until the CV is scored")
    analysis: AnalysisOut | None
    highlights: list[HighlightOut]


class RankingRow(BaseModel):
    rank: int | None
    document_id: uuid.UUID
    external_ref: str | None
    filename: str
    status: DocumentStatus
    auto: float | None
    manual: int
    total: float | None
    missing: list[str] = Field(description="Labels of criteria that cost points by being absent")


class AnalyzerOut(BaseModel):
    name: str
    version: str
    description: str
