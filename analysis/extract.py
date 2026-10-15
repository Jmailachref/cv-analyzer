"""PDF to text lines: pdfplumber for real text, Tesseract OCR for scanned pages.

Each line keeps its page, its section (experience, education, ...), its
position in the document's full text and, when read from the PDF itself,
its box on the page so a viewer can highlight it.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

import pdfplumber

from analysis.text import normalize
from core.config import settings

log = logging.getLogger("cva.extract")

# Below this many letters a page is treated as a scan and read with OCR.
MIN_TEXT_CHARS = 40
# Characters smaller than this are not meant to be read (hidden keyword stuffing).
MIN_FONT_SIZE = 4
OCR_DPI = 300

SECTIONS: dict[str, list[str]] = {
    "summary": ["profil", "profile", "resume", "summary", "a propos", "about me", "objectif", "objective"],
    "experience": [
        "experience", "experiences", "experience professionnelle", "experiences professionnelles",
        "parcours professionnel", "work experience", "professional experience", "employment", "work history",
    ],
    "education": ["formation", "formations", "education", "etudes", "diplomes", "academic background", "cursus"],
    "skills": [
        "competences", "competences techniques", "skills", "technical skills", "hard skills",
        "technologies", "outils", "stack technique", "savoir-faire",
    ],
    "projects": ["projets", "projects", "projets personnels", "personal projects", "realisations"],
    "languages": ["langues", "languages"],
    "certifications": ["certifications", "certificats", "certificates"],
    "interests": ["centres d'interet", "loisirs", "interests", "hobbies", "activites"],
}
_HEADING = {h: section for section, headings in SECTIONS.items() for h in headings}


@dataclass
class Line:
    page: int
    text: str
    section: str = "header"
    bbox: list[float] | None = None
    start: int = 0
    end: int = 0


@dataclass
class Extraction:
    lines: list[Line] = field(default_factory=list)
    text: str = ""
    pages: int = 0
    ocr_used: bool = False

    @property
    def readable(self) -> bool:
        return sum(ch.isalnum() for ch in self.text) >= MIN_TEXT_CHARS


def heading_section(text: str) -> str | None:
    """The section a line opens, if it is a heading such as "EXPÉRIENCES PROFESSIONNELLES :"."""
    words = re.sub(r"[^a-z' -]", " ", normalize(text)).split()
    if not words or len(words) > 4:
        return None
    return _HEADING.get(" ".join(words))


def _visible(obj: dict) -> bool:
    if obj.get("object_type") != "char":
        return True
    if obj.get("size", 10) < MIN_FONT_SIZE:
        return False
    color = obj.get("non_stroking_color")
    if isinstance(color, (int, float)):
        color = (color,)
    if isinstance(color, (list, tuple)) and color:
        if len(color) in (1, 3) and all(c >= 0.95 for c in color):  # white text on a white page
            return False
        if len(color) == 4 and all(c <= 0.05 for c in color):  # CMYK white
            return False
    return True


def _ocr(page) -> list[str]:
    import pytesseract

    image = page.to_image(resolution=OCR_DPI).original
    text = pytesseract.image_to_string(image, lang=settings.ocr_languages)
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract(pdf: bytes) -> Extraction:
    result = Extraction()
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        result.pages = len(doc.pages)
        for number, page in enumerate(doc.pages, start=1):
            visible = page.filter(_visible)
            lines = [
                Line(number, " ".join(row["text"].split()), bbox=[round(row[k], 1) for k in ("x0", "top", "x1", "bottom")])
                for row in visible.extract_text_lines(return_chars=False)
                if row["text"].strip()
            ]
            if sum(ch.isalnum() for ln in lines for ch in ln.text) < MIN_TEXT_CHARS:
                try:
                    ocr_lines = _ocr(page)
                except Exception:  # Tesseract missing or failing: keep what the PDF gave
                    log.exception("OCR failed on page %s", number)
                    ocr_lines = []
                if ocr_lines:
                    result.ocr_used = True
                    lines = [Line(number, " ".join(t.split())) for t in ocr_lines]
            result.lines.extend(lines)

    section, offset, parts = "header", 0, []
    for line in result.lines:
        section = heading_section(line.text) or section
        line.section = section
        line.start, line.end = offset, offset + len(line.text)
        parts.append(line.text)
        offset = line.end + 1
    result.text = "\n".join(parts)
    return result
