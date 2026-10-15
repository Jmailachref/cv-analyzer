"""Job queue between the API and workers: a Redis list of JSON jobs.

Jobs: {"type": "extract", "document_id": ...} reads a PDF;
{"type": "analyze", "document_id": ..., "grid_id": ...} scores a read CV.
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache

import redis

from core.config import settings


@lru_cache
def get_redis() -> redis.Redis:
    # redis-py 8 times reads out after 5 s by default, as long as dequeue blocks:
    # leave room for the blocking pop.
    return redis.Redis.from_url(settings.redis_url, socket_timeout=30, socket_connect_timeout=5)


def enqueue(job_type: str, **payload: uuid.UUID | str) -> None:
    job = {"type": job_type, **{k: str(v) for k, v in payload.items()}}
    get_redis().lpush(settings.queue_name, json.dumps(job))


def dequeue(timeout: int = 5) -> dict | None:
    """Block up to timeout seconds (well under the socket timeout) for the next job."""
    item = get_redis().brpop([settings.queue_name], timeout=timeout)
    return json.loads(item[1]) if item else None
