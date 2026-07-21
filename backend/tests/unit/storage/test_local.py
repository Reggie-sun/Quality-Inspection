from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.storage.local as storage_module
from app.storage.local import HashMismatch, LocalFileStorage


def test_atomic_write_publishes_verified_bytes(tmp_path: Path) -> None:
    """P0-RUN-002C and P0-RUN-002D publish verified bytes atomically."""
    storage = LocalFileStorage(tmp_path)
    payload = b"engineering-pdf"

    stored = storage.write_verified(
        "projects/p1/source.pdf",
        payload,
        sha256(payload).hexdigest(),
    )

    assert stored.path.read_bytes() == payload
    assert stored.size_bytes == len(payload)
    assert not list(tmp_path.rglob("*.tmp"))


def test_write_starts_in_same_filesystem_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-RUN-002B starts writes beside the final target."""
    created_temp_paths: list[Path] = []
    real_mkstemp = storage_module.tempfile.mkstemp

    def recording_mkstemp(*args, **kwargs):
        fd, temp_name = real_mkstemp(*args, **kwargs)
        created_temp_paths.append(Path(temp_name))
        return fd, temp_name

    monkeypatch.setattr(storage_module.tempfile, "mkstemp", recording_mkstemp)
    storage = LocalFileStorage(tmp_path)
    payload = b"same-filesystem"
    target = tmp_path / "projects/p1/source.pdf"

    storage.write_verified(
        "projects/p1/source.pdf",
        payload,
        sha256(payload).hexdigest(),
    )

    assert len(created_temp_paths) == 1
    assert created_temp_paths[0].parent == target.parent


def test_hash_or_size_mismatch_rejects_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-RUN-002C rejects hash or persisted byte-count mismatch."""
    storage = LocalFileStorage(tmp_path)
    hash_target = tmp_path / "projects/p1/hash-mismatch.pdf"

    with pytest.raises(HashMismatch):
        storage.write_verified(
            "projects/p1/hash-mismatch.pdf",
            b"bad",
            "0" * 64,
        )

    assert not hash_target.exists()

    real_stat = Path.stat

    def mismatched_temp_size(path: Path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if path.suffix == ".tmp":
            return SimpleNamespace(st_size=result.st_size + 1)
        return result

    monkeypatch.setattr(Path, "stat", mismatched_temp_size)
    payload = b"size-mismatch"
    size_target = tmp_path / "projects/p1/size-mismatch.pdf"

    with pytest.raises(HashMismatch):
        storage.write_verified(
            "projects/p1/size-mismatch.pdf",
            payload,
            sha256(payload).hexdigest(),
        )

    assert not size_target.exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_atomic_replace_is_the_only_publish_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-RUN-002D leaves no formal reference when atomic replace stops."""
    storage = LocalFileStorage(tmp_path)
    payload = b"interrupted-publish"
    target = tmp_path / "projects/p1/source.pdf"
    replace_calls: list[tuple[Path, Path]] = []

    def interrupt_replace(source, destination) -> None:
        replace_calls.append((Path(source), Path(destination)))
        raise RuntimeError("publish interrupted")

    monkeypatch.setattr(storage_module.os, "replace", interrupt_replace)

    with pytest.raises(RuntimeError, match="publish interrupted"):
        storage.write_verified(
            "projects/p1/source.pdf",
            payload,
            sha256(payload).hexdigest(),
        )

    assert len(replace_calls) == 1
    assert replace_calls[0][0].parent == replace_calls[0][1].parent
    assert replace_calls[0][1] == target
    assert not target.exists()
    assert not list(tmp_path.rglob("*.tmp"))
