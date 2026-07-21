from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


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
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_verified(
        self,
        relative_path: str,
        content: bytes,
        expected_sha256: str,
    ) -> StoredWrite:
        target = (self.root / relative_path).resolve()
        if self.root not in target.parents:
            raise ValueError("resource path escapes storage root")
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
