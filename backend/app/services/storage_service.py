"""MinIO object storage service."""

import uuid
from io import BytesIO

from fastapi import UploadFile

from app.config import settings
from app.utils.minio_client import get_minio_client


class StorageError(Exception):
    """Raised when a storage operation fails."""
    pass


async def upload_file(
    file: UploadFile,
    game_id: str,
    folder: str = "assets",
) -> tuple[str, str]:
    """
    Upload a file to MinIO.
    Returns (oss_key, oss_url).
    """
    client = get_minio_client()
    bucket = settings.minio_bucket

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"
    unique_name = f"{uuid.uuid4()}.{ext}"
    oss_key = f"games/{game_id}/{folder}/{unique_name}"

    content = await file.read()
    file_size = len(content)

    client.put_object(
        bucket_name=bucket,
        object_name=oss_key,
        data=BytesIO(content),
        length=file_size,
        content_type=file.content_type or "application/octet-stream",
    )

    oss_url = f"http://{settings.minio_endpoint}/{bucket}/{oss_key}"
    if settings.minio_secure:
        oss_url = f"https://{settings.minio_endpoint}/{bucket}/{oss_key}"

    return oss_key, oss_url


async def upload_html(game_id: str, html_content: str) -> str:
    """
    Upload a generated HTML game to MinIO.
    Returns the public URL.
    """
    client = get_minio_client()
    bucket = settings.minio_bucket

    oss_key = f"games/{game_id}/index.html"
    data = html_content.encode("utf-8")

    client.put_object(
        bucket_name=bucket,
        object_name=oss_key,
        data=BytesIO(data),
        length=len(data),
        content_type="text/html",
    )

    return f"http://{settings.minio_endpoint}/{bucket}/{oss_key}"


async def delete_file(oss_key: str) -> None:
    """Delete a file from MinIO."""
    client = get_minio_client()
    client.remove_object(settings.minio_bucket, oss_key)


async def get_presigned_url(oss_key: str) -> str:
    """Generate a presigned GET URL for temporary access."""
    client = get_minio_client()
    return client.presigned_get_object(settings.minio_bucket, oss_key)
