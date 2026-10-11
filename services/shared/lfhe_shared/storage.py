"""Write-once, content-addressed object storage for raw snapshots.

Keys are derived from the SHA-256 of the bytes (``raw/sha256/ab/cd/<hash>``),
so an object can never be replaced by different content under the same key:

* ``put_if_absent`` never overwrites. If the key already exists the stored
  bytes are re-hashed; a mismatch raises ``ObjectIntegrityError``.
* ``get`` re-hashes on read and raises ``ObjectIntegrityError`` on mismatch
  (tamper / corruption detection; storage is tamper-evident, not tamper-proof).

LOCAL is for DEV/TEST only (config refuses LOCAL in PROD). The S3 backend is
implemented against the S3 API (conditional PUT with If-None-Match) but is
NOT exercised by the Phase 1 test-suite — see Control Gate 1 report.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol

from .hashing import sha256_hex


class ObjectIntegrityError(RuntimeError):
    pass


def content_key(sha256: str, prefix: str = "raw") -> str:
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ValueError("not a sha256 hex digest")
    return f"{prefix}/sha256/{sha256[:2]}/{sha256[2:4]}/{sha256}"


class ObjectStore(Protocol):
    def put_if_absent(self, data: bytes, prefix: str = "raw") -> str: ...
    def get(self, key: str) -> bytes: ...


def _expected_hash(key: str) -> str:
    return key.rsplit("/", 1)[-1]


class LocalObjectStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("object key escapes storage root")
        return path

    def put_if_absent(self, data: bytes, prefix: str = "raw") -> str:
        """Write-once and atomic: the bytes go to a private temporary file which is
        then hard-linked into place. link() fails if the key exists, so an object is
        never overwritten, and a concurrent reader can never observe a partially
        written object (fix found by the P2 concurrency test)."""
        digest = sha256_hex(data)
        key = content_key(digest, prefix)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.get(key)  # verifies the existing object
            return key
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o444)
            try:
                os.link(tmp, path)
            except FileExistsError:
                self.get(key)  # a concurrent writer won; verify its complete object
        finally:
            os.unlink(tmp)
        return key

    def iter_keys(self, prefix: str = "raw"):
        base = self.root / prefix
        if not base.exists():
            return
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.startswith(".tmp-"):
                yield path.relative_to(self.root).as_posix()

    def get(self, key: str) -> bytes:
        data = self._path(key).read_bytes()
        if sha256_hex(data) != _expected_hash(key):
            raise ObjectIntegrityError(f"stored object {key} does not match its content hash")
        return data


class S3ObjectStore:  # pragma: no cover - not exercised in Phase 1 tests
    def __init__(self, *, endpoint: str, bucket: str, region: str | None,
                 access_key_id: str, secret_access_key: str):
        import boto3  # optional dependency: pip install .[s3]
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint, region_name=region,
                                   aws_access_key_id=access_key_id,
                                   aws_secret_access_key=secret_access_key)

    def put_if_absent(self, data: bytes, prefix: str = "raw") -> str:
        from botocore.exceptions import ClientError
        key = content_key(sha256_hex(data), prefix)
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, IfNoneMatch="*")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("PreconditionFailed", "412"):
                raise
            self.get(key)
        return key

    def iter_keys(self, prefix: str = "raw"):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix + "/"):
            for obj in page.get("Contents", []):
                yield obj["Key"]

    def get(self, key: str) -> bytes:
        data = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        if sha256_hex(data) != _expected_hash(key):
            raise ObjectIntegrityError(f"stored object {key} does not match its content hash")
        return data


def build_object_store(settings) -> ObjectStore:
    if settings.storage_backend.value == "LOCAL":
        return LocalObjectStore(settings.storage_local_root)
    return S3ObjectStore(
        endpoint=settings.storage_s3_endpoint, bucket=settings.storage_s3_bucket,
        region=settings.storage_s3_region,
        access_key_id=settings.storage_s3_access_key_id.get_secret_value(),
        secret_access_key=settings.storage_s3_secret_access_key.get_secret_value(),
    )


def find_unreferenced_objects(store, conn, prefix: str = "raw") -> list[str]:
    """Objects in the store that no article_snapshot references (report only;
    nothing is deleted — removal is an explicit operator decision)."""
    referenced = {r["raw_storage_key"] for r in conn.execute(
        "SELECT DISTINCT raw_storage_key FROM lfhe.article_snapshots WHERE raw_storage_key IS NOT NULL").fetchall()}
    return [k for k in store.iter_keys(prefix) if k not in referenced]
