"""S3-compatible object storage client — works with Alibaba OSS, AWS S3, MinIO, Cloudflare R2."""

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings


def get_s3_endpoint_url() -> str:
    """Build the full S3 endpoint URL from config."""
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_endpoint}"


def get_s3_client():
    """Return a boto3 S3 client configured for the given endpoint."""
    endpoint_url = get_s3_endpoint_url()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},  # path-style for MinIO/OSS compatibility
        ),
        region_name="us-east-1",  # Required but ignored by most S3-compatible services
    )


def ensure_bucket() -> None:
    """Create the configured bucket if it does not already exist."""
    client = get_s3_client()
    bucket = settings.minio_bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        # Set public-read for game files
        client.put_bucket_policy(
            Bucket=bucket,
            Policy='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":["s3:GetObject"],"Resource":["arn:aws:s3:::' + bucket + '/games/*"]}]}',
        )
