"""File storage abstraction (local disk or S3-compatible), reused as-is from Backend-WH-Retail
and pointed at SeaweedFS's S3 gateway by default (boto3's client only needs a custom
`endpoint_url` to work against any S3-compatible store, SeaweedFS included) — see the
consolidation plan's storage-layer decision.
"""
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import FileTooLargeException, UnsupportedFileTypeException

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".csv", ".docx"}


class UploadedFileOut(BaseModel):
    name: str
    url: str


class StorageClient(ABC):
    @abstractmethod
    def save(self, file: UploadFile, folder: str) -> UploadedFileOut: ...

    @abstractmethod
    def resolve_url(self, stored_value: str, expires_in: int = 900) -> str:
        """Turn whatever `save()` put in the DB back into a URL that's actually viewable right
        now. Local storage's value is already a servable path, so this is a passthrough; S3-
        compatible backends store a bare object key instead, so this mints a short-lived
        presigned GET url on demand — nothing long-lived is ever persisted for those documents."""
        ...

    @abstractmethod
    def read(self, stored_value: str) -> bytes:
        """Reads a file's raw bytes back — used by endpoints that proxy a document through the
        backend's own auth (e.g. vms-sa-react's openAuthedFile(), which needs the Authorization
        header attached, so it can't just follow a redirect straight to the storage backend)."""
        ...


class LocalStorageClient(StorageClient):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)

    def save(self, file: UploadFile, folder: str) -> UploadedFileOut:
        _validate(file)
        target_dir = self.base_dir / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}-{file.filename}"
        target_path = target_dir / safe_name
        with open(target_path, "wb") as out:
            out.write(file.file.read())
        return UploadedFileOut(name=file.filename, url=f"/uploads/{folder}/{safe_name}")

    def resolve_url(self, stored_value: str, expires_in: int = 900) -> str:
        return stored_value

    def read(self, stored_value: str) -> bytes:
        # stored_value is "/uploads/<folder>/<name>" (see save()); base_dir already points at
        # the local uploads root, so strip that one leading path segment back off.
        relative = stored_value.split("/uploads/", 1)[-1]
        with open(self.base_dir / relative, "rb") as f:
            return f.read()


class S3StorageClient(StorageClient):
    """Stores a bare object key rather than a public URL: these are KYC-type documents (GST
    cert, PAN, etc.) and the bucket is never made public-read, so callers must go through
    resolve_url() to view one."""

    def __init__(self, bucket: str, region: str, access_key: str, secret_key: str, endpoint_url: str):
        import boto3

        if not bucket:
            raise NotImplementedError(
                "S3-compatible storage needs AWS_S3_BUCKET set in .env (plus AWS_S3_ENDPOINT_URL "
                "for SeaweedFS or another non-AWS S3-compatible store)."
            )
        self.bucket = bucket
        self.s3 = boto3.client(
            "s3",
            region_name=region or None,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    def save(self, file: UploadFile, folder: str) -> UploadedFileOut:
        _validate(file)
        key = f"{folder}/{uuid.uuid4().hex}-{file.filename}"
        file.file.seek(0)
        self.s3.upload_fileobj(file.file, self.bucket, key)
        return UploadedFileOut(name=file.filename, url=key)

    def resolve_url(self, stored_value: str, expires_in: int = 900) -> str:
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": stored_value}, ExpiresIn=expires_in
        )

    def read(self, stored_value: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=stored_value)["Body"].read()


def _validate(file: UploadFile) -> None:
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeException(extension)
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise FileTooLargeException(MAX_UPLOAD_SIZE_BYTES)


def get_storage_client() -> StorageClient:
    if settings.FILES_STORAGE_BACKEND in ("s3", "seaweedfs"):
        return S3StorageClient(
            settings.AWS_S3_BUCKET, settings.AWS_REGION, settings.AWS_ACCESS_KEY_ID,
            settings.AWS_SECRET_ACCESS_KEY, settings.AWS_S3_ENDPOINT_URL or settings.SEAWEEDFS_FILER_URL,
        )
    return LocalStorageClient(settings.FILES_LOCAL_DIR)
