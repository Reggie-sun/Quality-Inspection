from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_hash(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("content_sha256", None)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _with_hash(document: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    payload = dict(document)
    payload["content_sha256"] = _canonical_hash(payload)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload, content


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_private_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
        ):
            raise ValueError("usage ledger directory is invalid")
        return
    try:
        os.mkdir(path, 0o700)
    except OSError as exc:
        raise ValueError("usage ledger directory is invalid") from exc
    os.chmod(path, 0o700)
    fsync_directory(path.parent)


def read_fact(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("usage ledger journal fact is invalid") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or metadata.st_size > 64 * 1024
        ):
            raise ValueError("usage ledger journal fact is invalid")
        content = b""
        while len(content) <= metadata.st_size:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            content += chunk
    finally:
        os.close(fd)
    try:
        document = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("usage ledger journal fact is invalid") from exc
    if not isinstance(document, Mapping):
        raise ValueError("usage ledger journal fact is invalid")
    payload = dict(document)
    digest = payload.get("content_sha256")
    if (
        not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or digest != _canonical_hash(payload)
    ):
        raise ValueError("usage ledger journal fact hash is invalid")
    return payload


def append_fact_exclusive(
    path: Path,
    document: dict[str, Any],
) -> dict[str, Any]:
    payload, content = _with_hash(document)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError("usage ledger journal append failed") from exc
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short usage ledger write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_directory(path.parent)
    return payload
