"""§108 file security — object storage via a MinIO/S3-compatible client.

Objects are keyed by organization + audit so a presigned URL's key alone
never leaks a guessable path across tenants; the download endpoint (router)
still re-checks organization ownership before issuing that presigned URL —
the key namespace is defense-in-depth, not the authorization boundary.
"""
from __future__ import annotations

import uuid
from functools import lru_cache

import boto3
from botocore.client import Config

from app.core.config import get_settings

PRESIGNED_URL_TTL_SECONDS = 600


@lru_cache
def _client():
    """Internal client — used for actual I/O (put_object, head_bucket),
    talking to MinIO over the Docker-internal endpoint."""
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name=settings.storage_region,
        config=Config(signature_version="s3v4"),
    )


@lru_cache
def _presign_client():
    """A second client configured with the browser-reachable endpoint,
    used only to *generate* presigned URLs (no network I/O happens at
    generation time). SigV4 signs the Host header, so a URL signed against
    the internal `minio:9000` hostname would fail validation the moment a
    browser requests it from `localhost:9000` instead — signing and serving
    host must match.
    """
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_public_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name=settings.storage_region,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    settings = get_settings()
    client = _client()
    try:
        client.head_bucket(Bucket=settings.storage_bucket)
    except Exception:  # noqa: BLE001 - bucket doesn't exist yet
        client.create_bucket(Bucket=settings.storage_bucket)


def object_key(*, organization_id: uuid.UUID, audit_id: uuid.UUID, filename: str) -> str:
    return f"reports/{organization_id}/{audit_id}/{filename}"


def upload_bytes(*, key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    _client().put_object(Bucket=settings.storage_bucket, Key=key, Body=data, ContentType=content_type)


def presigned_download_url(*, key: str, filename: str) -> str:
    settings = get_settings()
    return _presign_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.storage_bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
    )
