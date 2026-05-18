import asyncio
import io
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


class LocalStorage:
    def __init__(self, uploads_path: Path, base_url: str):
        self.uploads_path = uploads_path
        # base_url must be scheme+host only, e.g. https://example.com (no path suffix)
        self.base_url = base_url.rstrip("/") if base_url else ""

    async def save(self, content: bytes, filename: str) -> str:
        (self.uploads_path / filename).write_bytes(content)
        return f"{self.base_url}/api/files/{filename}"


class S3Storage:
    def __init__(self, bucket: str, endpoint_url: str, access_key: str,
                 secret_key: str, region: str, public_url: str):
        self.bucket = bucket
        self.endpoint_url = endpoint_url or None
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.public_url = public_url.rstrip("/") if public_url else ""

    async def save(self, content: bytes, filename: str) -> str:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._upload_sync, content, filename)
        if self.public_url:
            return f"{self.public_url}/{filename}"
        base = (self.endpoint_url or "https://s3.amazonaws.com").rstrip("/")
        return f"{base}/{self.bucket}/{filename}"

    def _upload_sync(self, content: bytes, filename: str) -> None:
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        client.upload_fileobj(
            io.BytesIO(content), self.bucket, filename,
            ExtraArgs={"ACL": "public-read"},
        )


def make_storage(settings: "Settings") -> "LocalStorage | S3Storage":
    if settings.S3_BUCKET and settings.S3_ACCESS_KEY:
        return S3Storage(
            bucket=settings.S3_BUCKET,
            endpoint_url=settings.S3_ENDPOINT_URL,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
            region=settings.S3_REGION,
            public_url=settings.S3_PUBLIC_URL,
        )
    return LocalStorage(settings.uploads_path(), settings.BASE_URL)
