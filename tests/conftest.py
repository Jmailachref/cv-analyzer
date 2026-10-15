"""Tests run against a real Postgres and Redis (docker compose, or CI services).

Set TEST_DATABASE_URL to a throwaway database; PDFs go to a temporary folder.
"""
import os
import tempfile

os.environ.setdefault(
    "DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://cva:cva@localhost:5432/cva_test")
)
os.environ.setdefault("QUEUE_NAME", "cva:test-jobs")
os.environ.setdefault("API_KEYS", "recrutehub:rh-key,other:other-key")
os.environ["STORAGE"] = "local"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from fpdf import FPDF  # noqa: E402

from api.main import app  # noqa: E402
from core import webhooks  # noqa: E402
from core.config import settings  # noqa: E402
from core.db import Base, engine  # noqa: E402
from core.queue import dequeue, get_redis  # noqa: E402
from worker.main import process  # noqa: E402

RH = {"Authorization": "Bearer rh-key"}
OTHER = {"Authorization": "Bearer other-key"}


def make_pdf(*lines, size=12) -> bytes:
    """A one-page PDF. A line is a string, or (text, {"color": (r, g, b), "size": n})."""
    pdf = FPDF()
    pdf.add_page()
    for line in lines:
        text, opts = (line, {}) if isinstance(line, str) else line
        pdf.set_font("Helvetica", size=opts.get("size", size))
        pdf.set_text_color(*opts.get("color", (0, 0, 0)))
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def make_scanned_pdf(*lines) -> bytes:
    """A PDF holding only a picture of text, like a scanned CV."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 200 + 90 * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=56)
    for i, text in enumerate(lines):
        draw.text((80, 80 + 90 * i), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    pdf = FPDF()
    pdf.add_page()
    pdf.image(io.BytesIO(buffer.getvalue()), x=0, y=0, w=210)
    return bytes(pdf.output())


@pytest.fixture(autouse=True)
def fresh_state():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    get_redis().delete(settings.queue_name)
    yield


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(webhooks, "send", lambda client, event, data: sent.append((client, event, data)))
    return sent


@pytest.fixture
def client(events):
    return TestClient(app)


def drain() -> int:
    """Runs every queued job, as a worker would."""
    count = 0
    while (job := dequeue(timeout=1)) is not None:
        process(job)
        count += 1
    return count
