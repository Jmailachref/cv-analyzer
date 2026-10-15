from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Ref = Annotated[str, Field(min_length=1, max_length=200)]
Slug = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9_.+#/-]*$")]
Term = Annotated[str, Field(min_length=1, max_length=80)]


# --- grids ------------------------------------------------------------------


class Criterion(BaseModel):
    id: Slug
    label: Term = Field(description="What the recruiter reads, e.g. Python. Also searched for.")
    kind: Literal["skill", "alert"] = Field(
        default="skill", description="skill: wanted in the CV. alert: a warning word that costs points when present."
    )
    terms: list[Term] = Field(default=[], max_length=40, description="Extra words that count as this criterion")
    default_synonyms: bool = Field(default=True, description="Also search the engine's synonyms for the label")
    points_present: float = Field(default=1.0, ge=-50, le=50)
    points_absent: float = Field(default=0.0, ge=-50, le=0)

    @model_validator(mode="after")
    def coherent(self) -> Criterion:
        if self.kind == "alert" and (self.points_present > 0 or self.points_absent != 0):
            raise ValueError(f"{self.id}: an alert costs points when present and nothing when absent")
        if self.kind == "skill" and self.points_present < 0:
            raise ValueError(f"{self.id}: a skill cannot cost points when present; use an alert")
        return self


class GridSettings(BaseModel):
    penalty_cap: float = Field(default=50, ge=0, le=100, description="Most points penalties can take off the score")
    auto_weight: float = Field(default=0.6, ge=0, le=1, description="Weight of the automatic score in the final one")
    manual_cap: float = Field(default=20, gt=0, le=100, description="Highlight points that make a manual score of 100")


class GridIn(BaseModel):
    criteria: list[Criterion] = Field(max_length=100)
    settings: GridSettings = GridSettings()

    @model_validator(mode="after")
    def distinct_ids(self) -> GridIn:
        ids = [c.id for c in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("each criterion id appears once in a grid")
        return self


class GridOut(GridIn):
    external_ref: str
    version: int
    created_at: datetime


class SkillIn(BaseModel):
    name: Term
    priority: int = Field(ge=1, le=5, description="1 core, 2 important, 3 secondary, 4 CV only, 5 bonus")


class SuggestIn(BaseModel):
    skills: list[SkillIn] = Field(default=[], max_length=60)
    alerts: list[Term] = Field(default=[], max_length=40, description="Warning words, e.g. stage for a senior role")


# --- documents --------------------------------------------------------------

DocumentStatus = Literal["queued", "processing", "ready", "unreadable", "failed"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    external_ref: str | None
    grid_ref: str | None
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
    grid_ref: Ref | None = Field(default=None, description="Defaults to the document's grid_ref")
    analyzer: str = "keywords"


class AnalysisOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    grid_ref: str
    grid_version: int
    analyzer: str
    analyzer_version: str
    score: float
    details: dict
    created_at: datetime


class HighlightIn(BaseModel):
    grid_ref: Ref | None = Field(default=None, description="Defaults to the document's grid_ref")
    author_ref: Ref = Field(description="Who highlighted, in the caller's terms (RecruteHub: the user id)")
    start: int | None = Field(default=None, ge=0, description="Character offset in the document text")
    end: int | None = Field(default=None, ge=1)
    line: int | None = Field(default=None, ge=0, description="Or a whole line, by its number")
    points: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def one_target(self) -> HighlightIn:
        has_range = self.start is not None and self.end is not None
        if has_range == (self.line is not None):
            raise ValueError("give either start and end, or line")
        if has_range and self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class HighlightOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    grid_ref: str
    author_ref: str
    start: int
    end: int
    quote: str
    points: int
    comment: str | None
    created_at: datetime


class ScoreOut(BaseModel):
    document_id: uuid.UUID
    external_ref: str | None
    grid_ref: str
    grid_version: int | None = Field(description="The grid version the automatic score used")
    auto: float | None = Field(description="Keyword score out of 100; null until the CV is read and scored")
    manual: float | None = Field(description="Highlight points out of 100; null until someone highlights")
    final: float | None
    manual_points: int
    analysis: AnalysisOut | None
    highlights: list[HighlightOut]


class RankingRow(BaseModel):
    rank: int | None
    document_id: uuid.UUID
    external_ref: str | None
    status: DocumentStatus
    auto: float | None
    manual: float | None
    final: float | None
    missing: list[str] = Field(description="Labels of criteria that cost points by being absent")


class AnalyzerOut(BaseModel):
    name: str
    version: str
    description: str
