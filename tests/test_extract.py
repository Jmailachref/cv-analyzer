import shutil

import pytest
from conftest import make_pdf, make_scanned_pdf

from analysis.extract import extract, heading_section


def test_lines_get_sections_and_offsets_into_the_text():
    result = extract(
        make_pdf(
            "Amina Haddad",
            "Data engineer",
            "EXPÉRIENCES PROFESSIONNELLES",
            "2021 - 2024 : Data engineer chez Acme, Python et SQL",
            "Formation :",
            "Master Informatique, 2020",
            "Compétences",
            "Docker, Kubernetes",
        )
    )
    assert result.readable and not result.ocr_used and result.pages == 1
    assert [(ln.section, ln.text) for ln in result.lines] == [
        ("header", "Amina Haddad"),
        ("header", "Data engineer"),
        ("experience", "EXPÉRIENCES PROFESSIONNELLES"),
        ("experience", "2021 - 2024 : Data engineer chez Acme, Python et SQL"),
        ("education", "Formation :"),
        ("education", "Master Informatique, 2020"),
        ("skills", "Compétences"),
        ("skills", "Docker, Kubernetes"),
    ]
    for ln in result.lines:
        assert result.text[ln.start : ln.end] == ln.text
        assert ln.bbox and ln.bbox[0] < ln.bbox[2]


def test_hidden_text_is_ignored():
    result = extract(
        make_pdf(
            "Développeur Java depuis 2015, applications bancaires",
            ("python kubernetes terraform rust", {"color": (255, 255, 255)}),
            ("golang scala spark", {"size": 2}),
        )
    )
    assert "python" not in result.text and "golang" not in result.text
    assert "Java" in result.text


def test_a_page_without_text_is_unreadable():
    result = extract(make_pdf(""))
    assert not result.readable and result.lines == []


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_scanned_cvs_are_read_with_ocr():
    result = extract(make_scanned_pdf("Experience", "Data engineer Python SQL", "Formation Master 2020"))
    assert result.ocr_used and result.readable
    assert "Python" in result.text
    assert result.lines[0].bbox is None


def test_headings_are_recognised_in_french_and_english():
    assert heading_section("Expériences professionnelles :") == "experience"
    assert heading_section("WORK EXPERIENCE") == "experience"
    assert heading_section("Centres d’intérêt") == "interests"
    assert heading_section("Développeur Python chez Acme depuis 2020") is None
