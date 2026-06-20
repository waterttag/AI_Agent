"""S3-compatible object storage service — OSS / S3 / MinIO / R2."""

import uuid
from io import BytesIO

from fastapi import UploadFile

from app.config import settings
from app.utils.s3_client import get_s3_client


def _build_public_url(oss_key: str) -> str:
    """Build a public URL for the given object key."""
    bucket = settings.minio_bucket
    endpoint = settings.minio_endpoint
    scheme = "https" if settings.minio_secure else "http"
    # Alibaba OSS / AWS S3: virtual-hosted style
    if "aliyuncs.com" in endpoint or "amazonaws.com" in endpoint:
        return f"{scheme}://{bucket}.{endpoint}/{oss_key}"
    # MinIO / local / others: path style
    return f"{scheme}://{endpoint}/{bucket}/{oss_key}"


async def upload_file(file: UploadFile, game_id: str, folder: str = "assets") -> tuple[str, str]:
    """Upload a file to object storage. Returns (oss_key, oss_url)."""
    client = get_s3_client()
    bucket = settings.minio_bucket

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"
    unique_name = f"{uuid.uuid4()}.{ext}"
    oss_key = f"games/{game_id}/{folder}/{unique_name}"

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    client.put_object(
        Bucket=bucket,
        Key=oss_key,
        Body=BytesIO(content),
        ContentType=content_type,
        ACL="public-read",
    )

    endpoint = settings.minio_endpoint
    scheme = "https" if settings.minio_secure else "http"
    oss_url = _build_public_url(oss_key)

    return oss_key, oss_url


async def upload_html(game_id: str, html_content: str) -> str:
    """Upload a generated HTML game to object storage. Returns the public URL."""
    client = get_s3_client()
    bucket = settings.minio_bucket

    oss_key = f"games/{game_id}/index.html"
    data = html_content.encode("utf-8")

    client.put_object(
        Bucket=bucket,
        Key=oss_key,
        Body=BytesIO(data),
        ContentType="text/html",
        ACL="public-read",
    )

    return _build_public_url(oss_key)


async def delete_file(oss_key: str) -> None:
    """Delete a file from object storage."""
    client = get_s3_client()
    client.delete_object(Bucket=settings.minio_bucket, Key=oss_key)
