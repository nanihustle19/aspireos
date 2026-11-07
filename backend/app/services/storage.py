"""S3-compatible object storage service using aioboto3 (MinIO for local dev)."""
import logging
from contextlib import asynccontextmanager

import aioboto3
from botocore.config import Config

from app.config import get_settings

logger = logging.getLogger("benchos.storage")

# Module-level session (lazy-init)
_session: aioboto3.Session | None = None

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!H+H*"
SAFE_EXTENSIONS = {"pdf", "doc", "docx", "txt", "rtf", "png", "jpg", "jpeg"}


def _get_session() -> aioboto3.Session:
    global _session
    if _session is None:
        _session = aioboto3.Session()
    return _session


def _client_kwargs() -> dict:
    """Build kwargs for the S3 client from settings."""
    settings = get_settings()
    kwargs: dict = {
        "service_name": "s3",
        "region_name": settings.S3_REGION,
        "config": Config(signature_version="s3v4"),
    }
    if settings.S3_ENDPOINT:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT
    if settings.S3_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY
    if settings.S3_SECRET_KEY:
        kwargs["aws_secret_access_key"] = settings.S3_SECRET_KEY
    return kwargs


@asynccontextmanager
async def _s3_client():
    """Async context manager yielding an S3 client."""
    session = _get_session()
    async with session.client(**_client_kwargs()) as client:
        yield client


async def init_storage():
    """Ensure the storage bucket exists. Call once at startup."""
    settings = get_settings()
    bucket = settings.S3_BUCKET
    try:
        async with _s3_client() as s3:
            try:
                await s3.head_bucket(Bucket=bucket)
                logger.info(f"Storage bucket '{bucket}' exists")
            except s3.exceptions.ClientError:
                await s3.create_bucket(Bucket=bucket)
                logger.info(f"Storage bucket '{bucket}' created")
    except Exception as e:
        logger.warning(f"Storage init failed (non-fatal if no S3 configured): {e}")


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload an object to S3-compatible storage.

    Args:
        path: Object key (e.g. 'org123/documents/abc.pdf')
        data: File bytes
        content_type: MIME type

    Returns:
        Dict with storage_path and size.
    """
    settings = get_settings()
    async with _s3_client() as s3:
        await s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=path,
            Body=data,
            ContentType=content_type,
        )
    logger.info(f"Uploaded {path} ({len(data)} bytes)")
    return {"storage_path": path, "size": len(data), "content_type": content_type}


async def get_object(path: str) -> tuple[bytes, str]:
    """Download an object from S3-compatible storage.

    Returns:
        Tuple of (data_bytes, content_type)
    """
    settings = get_settings()
    async with _s3_client() as s3:
        resp = await s3.get_object(Bucket=settings.S3_BUCKET, Key=path)
        data = await resp["Body"].read()
        ct = resp.get("ContentType", "application/octet-stream")
    return data, ct


async def delete_object(path: str) -> None:
    """Delete an object from storage."""
    settings = get_settings()
    async with _s3_client() as s3:
        await s3.delete_object(Bucket=settings.S3_BUCKET, Key=path)
    logger.info(f"Deleted {path}")


async def get_signed_url(path: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed download URL.

    Only call this for documents that passed scan.
    Signed URLs expire after `expires_in` seconds (default 1 hour).
    """
    settings = get_settings()
    async with _s3_client() as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": path},
            ExpiresIn=expires_in,
        )
    return url


async def object_exists(path: str) -> bool:
    """Check whether an object exists in storage."""
    settings = get_settings()
    try:
        async with _s3_client() as s3:
            await s3.head_object(Bucket=settings.S3_BUCKET, Key=path)
        return True
    except Exception:
        return False


def check_eicar(data: bytes) -> str | None:
    """Check for EICAR test signature. Returns reason string or None."""
    if EICAR in data:
        return "Malware signature detected (EICAR test)"
    if data[:2] == b"MZ":
        return "Executable content detected"
    return None


def check_extension(filename: str) -> str | None:
    """Validate file extension against allowlist. Returns reason or None."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SAFE_EXTENSIONS:
        return f"File type .{ext} not allowed"
    return None

