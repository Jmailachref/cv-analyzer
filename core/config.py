"""Settings read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _pairs(raw: str, name: str) -> dict[str, str]:
    """Parse "a:x,b:y" into {"a": "x", "b": "y"}. Values may contain ':' (URLs)."""
    pairs = {}
    for item in filter(None, (p.strip() for p in raw.split(","))):
        left, _, right = item.partition(":")
        if not right:
            raise ValueError(f"{name} entry must be name:value, got {item!r}")
        pairs[left] = right
    return pairs


def _api_keys(raw: str) -> dict[str, str]:
    """Parse "client-a:key1,client-b:key2" into {key: client_id}."""
    return {key: client for client, key in _pairs(raw, "API_KEYS").items()}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get("DATABASE_URL", "postgresql+psycopg://cva:cva@localhost:5432/cva")
    )
    redis_url: str = field(default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    queue_name: str = field(default_factory=lambda: os.environ.get("QUEUE_NAME", "cva:jobs"))
    api_keys: dict[str, str] = field(default_factory=lambda: _api_keys(os.environ.get("API_KEYS", "dev:dev-key")))
    # Where each client wants events: "recrutehub:http://candidates:8000/internal/cv-events".
    webhooks: dict[str, str] = field(default_factory=lambda: _pairs(os.environ.get("WEBHOOKS", ""), "WEBHOOKS"))
    # Signs webhook bodies (HMAC-SHA256 in X-CVA-Signature). Empty sends them unsigned.
    # Requests without an API key act as this client: for the bundled web app on a
    # developer's machine. Empty (the default) means every request needs a key.
    open_client: str = field(default_factory=lambda: os.environ.get("OPEN_CLIENT", ""))
    webhook_secret: str = field(default_factory=lambda: os.environ.get("WEBHOOK_SECRET", ""))

    # PDF storage: "s3" (SeaweedFS, MinIO, AWS) or "local" (a folder, for development and tests).
    storage: str = field(default_factory=lambda: os.environ.get("STORAGE", "local"))
    storage_dir: str = field(default_factory=lambda: os.environ.get("STORAGE_DIR", "data/files"))
    s3_url: str = field(default_factory=lambda: os.environ.get("S3_URL", ""))
    s3_access_key: str = field(default_factory=lambda: os.environ.get("S3_ACCESS_KEY", ""))
    s3_secret_key: str = field(default_factory=lambda: os.environ.get("S3_SECRET_KEY", ""))
    s3_bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET", "cv-analyzer"))

    max_pdf_bytes: int = field(default_factory=lambda: int(os.environ.get("MAX_PDF_MB", "10")) * 1024 * 1024)
    # Languages Tesseract reads scanned CVs in.
    ocr_languages: str = field(default_factory=lambda: os.environ.get("OCR_LANGUAGES", "fra+eng"))


settings = Settings()
