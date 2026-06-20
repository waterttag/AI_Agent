"""MinIO/S3 client singleton."""

import json

from minio import Minio

from app.config import settings

_minio_client: Minio | None = None


def get_minio_client() -> Minio:
    """Return a singleton MinIO client instance."""
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _minio_client


def ensure_bucket() -> None:
    """Create the configured bucket if it does not already exist."""
    client = get_minio_client()
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        # Set public read policy for game files
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/games/*"],
                }
            ],
        }
        client.set_bucket_policy(bucket, json.dumps(policy))
