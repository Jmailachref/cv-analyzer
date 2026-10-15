"""PDF files: an S3 bucket in production, a local folder in development and tests."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.config import settings


@lru_cache
def _s3():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@lru_cache
def _bucket() -> str:
    """The bucket, created on first use if it does not exist yet."""
    from botocore.exceptions import ClientError

    try:
        _s3().head_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
            raise
        _s3().create_bucket(Bucket=settings.s3_bucket)
    return settings.s3_bucket


def _local(key: str) -> Path:
    path = Path(settings.storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def put(key: str, data: bytes) -> None:
    if settings.storage == "s3":
        _s3().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType="application/pdf")
    else:
        _local(key).write_bytes(data)


def get(key: str) -> bytes:
    if settings.storage == "s3":
        return _s3().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
    return _local(key).read_bytes()


def delete(key: str) -> None:
    if settings.storage == "s3":
        _s3().delete_object(Bucket=settings.s3_bucket, Key=key)
    else:
        _local(key).unlink(missing_ok=True)
