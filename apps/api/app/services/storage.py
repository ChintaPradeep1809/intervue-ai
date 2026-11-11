"""Object storage abstraction: local filesystem with HMAC-signed URLs, or S3 with presigned URLs."""

from __future__ import annotations

import abc
import asyncio
import uuid
from pathlib import Path
from urllib.parse import quote

from app.config import get_settings
from intervue_security import sign_path


class Storage(abc.ABC):
    name: str

    @abc.abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abc.abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    def signed_url(self, key: str, ttl_seconds: int = 300) -> str: ...

    async def healthy(self) -> bool:
        return True


def new_key(prefix: str, ext: str) -> str:
    return f"{prefix}/{uuid.uuid4().hex}{ext}"


class LocalStorage(Storage):
    name = "local"

    def __init__(self, root: str, secret: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.secret = secret

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            await asyncio.to_thread(p.unlink)

    def signed_url(self, key: str, ttl_seconds: int = 300) -> str:
        exp, sig = sign_path(self.secret, key, ttl_seconds)
        return f"/api/files/{quote(key)}?exp={exp}&sig={sig}"

    async def healthy(self) -> bool:
        return self.root.exists()


class S3Storage(Storage):
    name = "s3"

    def __init__(self, bucket: str, region: str) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        body: bytes = obj["Body"].read()
        return body

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, ttl_seconds: int = 300) -> str:
        url: str = self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl_seconds)
        return url

    async def healthy(self) -> bool:
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
            return True
        except Exception:
            return False


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage(s.storage_s3_bucket, s.storage_s3_region) if s.storage_backend == "s3" else LocalStorage(s.storage_local_root, s.auth_secret)
    return _storage


def set_storage(storage: Storage) -> None:
    global _storage
    _storage = storage
