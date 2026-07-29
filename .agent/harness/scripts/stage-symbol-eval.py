#!/usr/bin/env python3
"""Validate and seal the approved current-source visual symbol labels."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import stat
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

import pymupdf
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
SOURCE_SHA256 = (
    "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec"
)
EXPECTED_PAGE_SIZE = (1190.55, 841.89)
PAGE_SIZE_TOLERANCE = 0.05
CURRENT_PAGE_BOXES = (
    (0.0, 0.0, EXPECTED_PAGE_SIZE[0], EXPECTED_PAGE_SIZE[1]),
) * 2
EVAL_ARTIFACT = "artifacts/visual-symbol-eval.json"
VERDICT_ARTIFACT = "artifacts/visual-symbol-annotation-verdict.json"
POSITIVE_SYMBOL_KINDS = (
    "diameter",
    "depth",
    "counterbore",
    "surface_roughness",
    "gdt_parallelism",
    "gdt_perpendicularity",
    "gdt_flatness",
    "datum_reference",
    "revision_marker",
)
ALL_SYMBOL_KINDS = (*POSITIVE_SYMBOL_KINDS, "frozen_negative")
NEGATIVE_FAMILIES = (
    "part_or_hole_geometry",
    "hatch_center_or_cross",
    "dimension_leader_or_section_line",
    "view_or_section_label",
    "revision_table_or_invalid_marker",
    "datum_like_letter_or_table_cell",
    "watermark_logo_title_or_signoff",
    "isometric_hole_slot_or_edge",
    "ordinary_text_number_material_or_requirement",
)
FORBIDDEN_FIELD_PARTS = (
    "base64",
    "credential",
    "password",
    "pdf_bytes",
    "screenshot",
    "secret",
    "source_path",
)
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9._~+\-/])/(?!/)[^/\s]+(?:/[^/\s]*)*"),
    re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)"),
    re.compile(r"(?<![A-Za-z0-9._~+\-])[a-z]:[\\/]", re.IGNORECASE),
    re.compile(r"\\\\[^\\\s]+\\[^\\\s]+"),
    re.compile(r"file://", re.IGNORECASE),
    re.compile(r"data:application/pdf", re.IGNORECASE),
    re.compile(r"base64,", re.IGNORECASE),
    re.compile(r"%PDF-"),
)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid arguments\n")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_json_document(
    content: bytes,
    *,
    kind: str,
    require_canonical: bool,
) -> dict[str, Any]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{kind} must be strict UTF-8 JSON") from exc

    def reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"{kind} contains a duplicate JSON key")
            document[key] = value
        return document

    def reject_nonfinite(_value: str) -> Any:
        raise ValueError(f"{kind} contains a non-finite JSON number")

    try:
        document = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{kind} must be valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{kind} root must be one JSON object")
    if require_canonical and content != _canonical_bytes(document):
        raise ValueError(f"{kind} bytes must use canonical JSON serialization")
    return document


def _stable_read(path: Path, *, kind: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError(f"{kind} input is unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{kind} input must be one real regular file")
    if before.st_size <= 0:
        raise ValueError(f"{kind} input must not be empty")
    try:
        content = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise ValueError(f"{kind} input could not be read") from exc
    if (
        len(content) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
        or stat.S_ISLNK(after.st_mode)
        or not stat.S_ISREG(after.st_mode)
    ):
        raise ValueError(f"{kind} input changed during verification")
    return content


def verify_source(path: Path) -> tuple[tuple[float, float, float, float], ...]:
    content = _stable_read(path, kind="source PDF")
    if not content.startswith(b"%PDF-"):
        raise ValueError("source input does not have a PDF header")
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise ValueError("source PDF SHA-256 mismatch")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.page_count != 2:
                raise ValueError("source PDF must contain exactly two pages")
            boxes = tuple(
                (
                    float(page.rect.x0),
                    float(page.rect.y0),
                    float(page.rect.x1),
                    float(page.rect.y1),
                )
                for page in document
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("source PDF metadata could not be read") from exc
    expected_width, expected_height = EXPECTED_PAGE_SIZE
    if any(
        abs((x1 - x0) - expected_width) > PAGE_SIZE_TOLERANCE
        or abs((y1 - y0) - expected_height) > PAGE_SIZE_TOLERANCE
        for x0, y0, x1, y1 in boxes
    ):
        raise ValueError("source PDF page bbox does not match current source")
    return boxes


def _schema(name: str) -> dict[str, Any]:
    return json.loads(
        (HARNESS / "schemas" / name).read_text(encoding="utf-8")
    )


def _validate_schema(document: Mapping[str, Any], schema_name: str) -> None:
    errors = sorted(
        Draft202012Validator(
            _schema(schema_name),
            format_checker=FormatChecker(),
        ).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        raise ValueError(f"{schema_name} validation failed")


def _labels(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        label
        for page in manifest["pages"]
        for label in page["labels"]
    ]


def validate_manifest(
    manifest: Mapping[str, Any],
    page_boxes: Sequence[Sequence[float]],
) -> dict[str, Any]:
    _validate_schema(manifest, "visual-symbol-eval.schema.json")
    if len(page_boxes) != 2:
        raise ValueError("manifest validation requires exactly two page bboxes")
    pages = manifest["pages"]
    page_indices = [page["page_index"] for page in pages]
    if len(set(page_indices)) != 2 or set(page_indices) != {0, 1}:
        raise ValueError("manifest page_index values must be unique 0 and 1")

    labels = _labels(manifest)
    label_ids = [label["label_id"] for label in labels]
    if len(label_ids) != len(set(label_ids)):
        raise ValueError("manifest label_id values must be globally unique")
    kind_order = {kind: index for index, kind in enumerate(ALL_SYMBOL_KINDS)}
    for page in pages:
        page_index = page["page_index"]
        page_x0, page_y0, page_x1, page_y1 = (
            float(value) for value in page_boxes[page_index]
        )
        for label in page["labels"]:
            bbox = tuple(float(value) for value in label["bbox_pdf"])
            if not all(math.isfinite(value) for value in bbox):
                raise ValueError("manifest bbox_pdf values must be finite")
            x0, y0, x1, y1 = bbox
            if x1 <= x0 or y1 <= y0:
                raise ValueError("manifest bbox_pdf must have positive area")
            if (
                x0 < page_x0
                or y0 < page_y0
                or x1 > page_x1
                or y1 > page_y1
            ):
                raise ValueError("manifest bbox_pdf must remain inside its page")
            kinds = label["symbol_kinds"]
            if kinds != sorted(kinds, key=kind_order.__getitem__):
                raise ValueError(
                    "manifest symbol_kinds must follow the frozen allowlist order"
                )

    positive_counts = Counter(
        kind
        for label in labels
        if label["symbol_kinds"] != ["frozen_negative"]
        for kind in label["symbol_kinds"]
    )
    if set(positive_counts) != set(POSITIVE_SYMBOL_KINDS) or any(
        positive_counts[kind] < 1 for kind in POSITIVE_SYMBOL_KINDS
    ):
        raise ValueError(
            "manifest positive symbol family coverage must contain all nine "
            "families"
        )
    negative_counts = Counter(
        label["negative_family"]
        for label in labels
        if label["symbol_kinds"] == ["frozen_negative"]
    )
    if set(negative_counts) != set(NEGATIVE_FAMILIES) or any(
        negative_counts[family] < 1 for family in NEGATIVE_FAMILIES
    ):
        raise ValueError(
            "manifest negative family coverage must contain all nine distinct "
            "families"
        )
    return {
        "label_count": len(labels),
        "positive_family_counts": {
            kind: positive_counts[kind] for kind in POSITIVE_SYMBOL_KINDS
        },
        "negative_family_counts": {
            family: negative_counts[family] for family in NEGATIVE_FAMILIES
        },
        "negative_family_count": len(negative_counts),
    }


def _assert_sanitized(value: Any, *, field_name: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            normalized = key_text.lower()
            if any(part in normalized for part in FORBIDDEN_FIELD_PARTS):
                raise ValueError("symbol eval artifact contains a forbidden field")
            _assert_sanitized(key_text)
            _assert_sanitized(child, field_name=normalized)
    elif isinstance(value, list):
        for child in value:
            _assert_sanitized(child, field_name=field_name)
    elif isinstance(value, str) and any(
        pattern.search(value) for pattern in FORBIDDEN_VALUE_PATTERNS
    ):
        raise ValueError("symbol eval artifact contains forbidden private data")


def build_artifacts(
    manifest: Mapping[str, Any],
    page_boxes: Sequence[Sequence[float]],
    *,
    recorded_at: str | None = None,
) -> dict[str, bytes]:
    _assert_sanitized(manifest)
    summary = validate_manifest(manifest, page_boxes)
    manifest_document = json.loads(_canonical_bytes(manifest))
    _assert_sanitized(manifest_document)
    manifest_bytes = _canonical_bytes(manifest_document)
    verdict = {
        "schema_version": "visual-symbol-annotation-verdict/1",
        "annotation_owner_role": "quality_owner",
        "overlay_scale_percent": 200,
        "unlabeled_target_count": 0,
        "negative_family_count": summary["negative_family_count"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "recorded_at": recorded_at or _iso_now(),
    }
    _assert_sanitized(verdict)
    _validate_schema(
        verdict,
        "visual-symbol-annotation-verdict.schema.json",
    )
    return {
        EVAL_ARTIFACT: manifest_bytes,
        VERDICT_ARTIFACT: _canonical_bytes(verdict),
    }


def validate_artifacts(
    artifacts: Mapping[str, bytes] | None,
) -> dict[str, bytes]:
    supplied = dict(artifacts or {})
    if set(supplied) != {EVAL_ARTIFACT, VERDICT_ARTIFACT}:
        raise ValueError(
            "symbol registration requires the exact visual-symbol eval/verdict "
            "artifact pair"
        )
    if any(not isinstance(content, bytes) for content in supplied.values()):
        raise TypeError("symbol registration artifact content must be bytes")
    validated = {
        name: supplied[name] for name in (EVAL_ARTIFACT, VERDICT_ARTIFACT)
    }
    manifest = _strict_json_document(
        validated[EVAL_ARTIFACT],
        kind="visual symbol manifest artifact",
        require_canonical=True,
    )
    verdict = _strict_json_document(
        validated[VERDICT_ARTIFACT],
        kind="visual symbol verdict artifact",
        require_canonical=True,
    )
    _assert_sanitized(manifest)
    _assert_sanitized(verdict)
    validate_manifest(manifest, CURRENT_PAGE_BOXES)
    _validate_schema(
        verdict,
        "visual-symbol-annotation-verdict.schema.json",
    )
    if verdict["manifest_sha256"] != hashlib.sha256(
        validated[EVAL_ARTIFACT]
    ).hexdigest():
        raise ValueError(
            "symbol annotation verdict manifest_sha256 does not match exact "
            "manifest bytes"
        )
    return validated


def _load_manifest(path: Path) -> dict[str, Any]:
    content = _stable_read(path, kind="manifest")
    return _strict_json_document(
        content,
        kind="manifest input",
        require_canonical=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(
        prog="stage-symbol-eval.py",
        description=__doc__,
        allow_abbrev=False,
    )
    parser.add_argument("--mode", required=True, choices=("live",))
    parser.add_argument("--source", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        if args.run_id is not None and not re.fullmatch(
            r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$",
            args.run_id,
        ):
            raise ValueError("--run-id must be one literal run ID")
        page_boxes = verify_source(Path(args.source))
        manifest = _load_manifest(Path(args.manifest))
        _assert_sanitized(manifest)
        summary = validate_manifest(manifest, page_boxes)
        artifacts = build_artifacts(manifest, page_boxes)
        runner = _load_module(
            "qi_run_p0_for_symbol_eval_staging",
            HARNESS / "scripts/run-p0.py",
        )
        run_id = runner.register_live_input_artifacts(
            task_id="D7-T2",
            artifacts=artifacts,
            run_id=args.run_id,
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"stage-symbol-eval: {exc}", file=sys.stderr)
        return 2

    print(
        f"run_id={run_id} source_sha256={SOURCE_SHA256} pages=2 "
        f"labels={summary['label_count']} "
        "positive_family_counts="
        + json.dumps(
            summary["positive_family_counts"],
            sort_keys=True,
            separators=(",", ":"),
        )
        + " negative_family_counts="
        + json.dumps(
            summary["negative_family_counts"],
            sort_keys=True,
            separators=(",", ":"),
        )
        + " overlay_scale_percent=200 unlabeled_target_count=0 "
        "negative_family_count=9 annotation_status=approved "
        "registration_state=sealed receipt=none formal_success=none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
