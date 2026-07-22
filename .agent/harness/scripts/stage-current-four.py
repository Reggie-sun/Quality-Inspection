#!/usr/bin/env python3
"""Register the frozen current-four PDF identity without copying source bytes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Sequence

import pymupdf


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
SCHEMA_PATH = HARNESS / "schemas/current-four-manifest.schema.json"
CURRENT_FOUR_ARTIFACT = "artifacts/current-four-manifest.json"
POINT_TOLERANCE = 2.0
PHYSICAL_PAGE_POINTS = {
    "A3 landscape": (1190.55, 841.89),
    "A4 portrait": (595.28, 841.89),
}


@dataclass(frozen=True)
class FrozenDocument:
    order: int
    basename: str
    sha256: str
    opaque_ref: str
    page_count: int
    physical_page: str


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen_documents() -> tuple[FrozenDocument, ...]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    documents: list[FrozenDocument] = []
    for item in schema["properties"]["entries"]["prefixItems"]:
        properties = item["allOf"][1]["properties"]
        page_metadata = properties["page_metadata"]["const"]
        documents.append(
            FrozenDocument(
                order=properties["order"]["const"],
                basename=properties["basename"]["const"],
                sha256=properties["sha256"]["const"],
                opaque_ref=properties["opaque_ref"]["const"],
                page_count=page_metadata["page_count"],
                physical_page=page_metadata["physical_page"],
            )
        )
    return tuple(documents)


FROZEN_DOCUMENTS = _frozen_documents()


def manifest_from_documents(
    documents: Sequence[FrozenDocument],
) -> dict[str, Any]:
    entries = [
        {
            "order": document.order,
            "basename": document.basename,
            "sha256": document.sha256,
            "opaque_ref": document.opaque_ref,
            "page_metadata": {
                "page_count": document.page_count,
                "physical_page": document.physical_page,
            },
        }
        for document in documents
    ]
    if not entries:
        raise ValueError("current-four manifest requires frozen documents")
    return {
        "schema_version": "current-four-manifest/1",
        "input_set": "current-four",
        "first_checkpoint": {
            key: entries[0][key]
            for key in ("order", "basename", "sha256", "opaque_ref")
        },
        "entries": entries,
    }


def _resolve_sources(
    source_args: Sequence[str] | None,
    source_root: str | None,
) -> dict[str, Path]:
    if source_root is not None:
        root = Path(source_root)
        try:
            root_stat = root.lstat()
        except OSError as exc:
            raise ValueError("source root is unavailable") from exc
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("source root must be one real directory")
        candidates = tuple(root.rglob("*.pdf"))
    else:
        candidates = tuple(Path(value) for value in source_args or ())

    expected = {document.basename for document in FROZEN_DOCUMENTS}
    resolved: dict[str, Path] = {}
    for path in candidates:
        if path.name not in expected:
            raise ValueError("source selection contains a non-current-four PDF")
        if path.name in resolved:
            raise ValueError(f"duplicate current-four basename: {path.name}")
        resolved[path.name] = path
    if set(resolved) != expected:
        raise ValueError("source selection must contain exactly the frozen current-four PDFs")
    return resolved


def _stream_sha256(path: Path, basename: str) -> str:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError(f"source is unavailable: {basename}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"source must be one real regular file: {basename}")
    if before.st_size <= 0:
        raise ValueError(f"source is empty: {basename}")

    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as stream:
            header = stream.read(5)
            if header != b"%PDF-":
                raise ValueError(f"source is not a PDF: {basename}")
            digest.update(header)
            byte_count += len(header)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                byte_count += len(chunk)
        after = path.lstat()
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"source could not be read: {basename}") from exc
    if (
        byte_count != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise ValueError(f"source changed during identity verification: {basename}")
    return digest.hexdigest()


def _matches_physical_page(page: pymupdf.Page, physical_page: str) -> bool:
    expected_width, expected_height = PHYSICAL_PAGE_POINTS[physical_page]
    return (
        abs(page.rect.width - expected_width) <= POINT_TOLERANCE
        and abs(page.rect.height - expected_height) <= POINT_TOLERANCE
    )


def _verify_document(path: Path, expected: FrozenDocument) -> None:
    if _stream_sha256(path, expected.basename) != expected.sha256:
        raise ValueError(f"SHA-256 mismatch: {expected.basename}")
    try:
        with pymupdf.open(path) as document:
            if document.page_count != expected.page_count:
                raise ValueError(f"page count mismatch: {expected.basename}")
            if not all(
                _matches_physical_page(page, expected.physical_page)
                for page in document
            ):
                raise ValueError(f"physical page mismatch: {expected.basename}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF metadata could not be read: {expected.basename}") from exc


def _verify_sources(sources: dict[str, Path]) -> None:
    for document in FROZEN_DOCUMENTS:
        _verify_document(sources[document.basename], document)


def _manifest_bytes(documents: Iterable[FrozenDocument]) -> bytes:
    manifest = manifest_from_documents(tuple(documents))
    receipt_module = _load_module(
        "qi_generate_receipt_for_staging",
        HARNESS / "scripts/generate-receipt.py",
    )
    receipt_module.validate_schema(
        manifest,
        "current-four-manifest.schema.json",
        ROOT,
    )
    return json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("live",))
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", action="append")
    source_group.add_argument("--source-root")
    args = parser.parse_args(argv)
    try:
        sources = _resolve_sources(args.source, args.source_root)
        _verify_sources(sources)
        artifact = _manifest_bytes(FROZEN_DOCUMENTS)
        runner = _load_module(
            "qi_run_p0_for_staging",
            HARNESS / "scripts/run-p0.py",
        )
        run_id, verdict = runner.run_task(
            "live",
            "task",
            "D2-T1",
            input_artifacts={CURRENT_FOUR_ARTIFACT: artifact},
        )
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"stage-current-four: {exc}", file=sys.stderr)
        return 2

    page_count = sum(document.page_count for document in FROZEN_DOCUMENTS)
    print(
        f"registered={len(FROZEN_DOCUMENTS)} pages={page_count} hashes=verified "
        f"first_checkpoint={FROZEN_DOCUMENTS[0].sha256[:10]}... "
        f"run_id={run_id} overall_verdict={verdict}"
    )
    return 0 if verdict == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
