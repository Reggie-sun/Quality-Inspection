from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath


class HashMismatch(ValueError):
    pass


@dataclass(frozen=True)
class StoredWrite:
    resource_ref: str
    path: Path
    sha256: str
    size_bytes: int


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()

    @staticmethod
    def _relative_parts(relative_path: str) -> tuple[str, ...]:
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("resource path must be one non-empty relative path")
        path = PurePosixPath(relative_path)
        raw_parts = relative_path.split("/")
        if (
            path.is_absolute()
            or "\\" in relative_path
            or any(part in {"", ".", ".."} for part in raw_parts)
        ):
            raise ValueError("resource path escapes storage root")
        return tuple(raw_parts)

    def _resolve_relative_path(self, relative_path: str) -> Path:
        parts = self._relative_parts(relative_path)
        current = self.root
        for part in parts:
            current /= part
            if current.is_symlink():
                raise ValueError("resource path contains a symlink")
        resolved = current.resolve(strict=False)
        if self.root not in resolved.parents:
            raise ValueError("resource path escapes storage root")
        return resolved

    def write_verified(
        self,
        relative_path: str,
        content: bytes,
        expected_sha256: str,
    ) -> StoredWrite:
        target = self._resolve_relative_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_sha256:
            raise HashMismatch(f"expected {expected_sha256}, got {digest}")

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if temp.stat().st_size != len(content):
                raise HashMismatch("stored byte count changed")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

        return StoredWrite(
            resource_ref=f"asset://{relative_path}",
            path=target,
            sha256=digest,
            size_bytes=len(content),
        )

    def resolve_resource_ref(self, resource_ref: str) -> Path:
        if not isinstance(resource_ref, str) or not resource_ref.startswith("asset://"):
            raise ValueError("resource_ref must use the asset scheme")
        target = self._resolve_relative_path(resource_ref.removeprefix("asset://"))
        if not target.is_file():
            raise ValueError("resource_ref does not resolve to a stored file")
        return target

    def read_bytes(self, resource_ref: str) -> bytes:
        return self.resolve_resource_ref(resource_ref).read_bytes()

    def delete(self, resource_ref: str) -> None:
        self.resolve_resource_ref(resource_ref).unlink()

    def probe(self) -> None:
        payload = secrets.token_bytes(32)
        relative_path = f".capability-probe-{uuid.uuid4().hex}"
        stored: StoredWrite | None = None
        try:
            stored = self.write_verified(
                relative_path,
                payload,
                hashlib.sha256(payload).hexdigest(),
            )
            if self.read_bytes(stored.resource_ref) != payload:
                raise HashMismatch("storage probe bytes changed")
        finally:
            if stored is not None and stored.path.exists():
                self.delete(stored.resource_ref)
