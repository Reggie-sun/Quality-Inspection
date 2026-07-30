from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.candidates.coverage import check_coverage
from app.candidates.symbol_review import plan_visual_batches
from app.pdf.inventory import build_inventory
from app.processing.automatic_result import (
    CandidateSnapshot,
    candidate_snapshot_from_inventory,
    selected_observations,
    selected_visual_observations,
)


SCHEMA_VERSION = "welli-layout-regression/1"
_ROOT_ENV_NAMES = (
    "QI_CURRENT_FOUR_SOURCE_ROOT",
    "QI_WELLI_REGRESSION_SOURCE_ROOT",
)


def canonical_report_bytes(report: Mapping[str, object]) -> bytes:
    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pdf_paths_from_roots(roots: Sequence[Path]) -> tuple[Path, ...]:
    if not roots:
        raise ValueError("at least one corpus root is required")
    paths: list[Path] = []
    for root in roots:
        resolved = Path(root)
        if not resolved.is_dir():
            raise ValueError("corpus root must be one readable directory")
        paths.extend(
            path
            for path in resolved.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        )
    if not paths:
        raise ValueError("corpus roots contain no PDF inputs")
    return tuple(paths)


def _unique_pdf_inputs(
    pdf_paths: Sequence[Path],
) -> tuple[tuple[str, Path], int]:
    if not pdf_paths:
        raise ValueError("at least one PDF input is required")
    unique_by_sha: dict[str, Path] = {}
    duplicate_count = 0
    for raw_path in pdf_paths:
        path = Path(raw_path)
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError("input must be one PDF")
        source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if source_sha256 in unique_by_sha:
            duplicate_count += 1
            continue
        unique_by_sha[source_sha256] = path
    return (
        tuple(
            (source_sha256, unique_by_sha[source_sha256])
            for source_sha256 in sorted(unique_by_sha)
        ),
        duplicate_count,
    )


def discover_unique_pdfs(roots: Sequence[Path]) -> tuple[Path, ...]:
    unique_inputs, _duplicate_count = _unique_pdf_inputs(
        _pdf_paths_from_roots(roots)
    )
    return tuple(path for _source_sha256, path in unique_inputs)


def _observation_ids(pages: Sequence[Any]) -> tuple[str, ...]:
    identities = tuple(
        observation.observation_id
        for page in pages
        for observation in (
            *getattr(page, "observations", ()),
            *getattr(page, "visual_observations", ()),
        )
    )
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate observation identity")
    return identities


def _candidate_source_ids(snapshot: CandidateSnapshot) -> frozenset[str]:
    return frozenset(
        str(source_id)
        for candidate in snapshot.candidates
        for source_id in candidate.get("source_location_ids", ())
    )


def _coverage_by_id(
    snapshot: CandidateSnapshot,
) -> dict[str, Any]:
    grouped: dict[str, list[Any]] = {}
    for entry in snapshot.coverage_entries:
        grouped.setdefault(entry.observation_id, []).append(entry)
    if any(len(entries) != 1 for entries in grouped.values()):
        raise ValueError("duplicate observation identity")
    return {
        observation_id: entries[0]
        for observation_id, entries in grouped.items()
    }


def _empty_aggregate() -> dict[str, int]:
    return {
        "control_candidate_source_count": 0,
        "current_candidate_source_count": 0,
        "candidate_source_ids_rerouted": 0,
        "revision_marker_reroutes": 0,
        "revision_description_reroutes": 0,
        "title_metadata_reroutes": 0,
        "page_frame_reroutes": 0,
        "watermark_native_line_count": 0,
        "revision_engineering_preserved_line_count": 0,
        "resolved_visual_observation_count": 0,
        "required_visual_observation_count": 0,
        "resolved_visual_ids_in_planned_batches": 0,
        "coverage_blocking_count": 0,
    }


def _increment_reason_counts(
    aggregate: dict[str, int],
    *,
    rerouted_ids: frozenset[str],
    current_coverage: Mapping[str, Any],
) -> None:
    reason_metrics = {
        "welli_revision_marker": "revision_marker_reroutes",
        "welli_revision_description": "revision_description_reroutes",
        "welli_title_metadata_value": "title_metadata_reroutes",
        "welli_page_frame_number": "page_frame_reroutes",
    }
    for observation_id in rerouted_ids:
        entry = current_coverage.get(observation_id)
        metric = reason_metrics.get(
            getattr(entry, "disposition_reason", None)
        )
        if metric is not None:
            aggregate[metric] += 1


def _engineering_preserved_ids(
    pages: Sequence[Any],
    current_coverage: Mapping[str, Any],
) -> frozenset[str]:
    assigned_ids = {
        assignment.observation_id
        for page in pages
        if getattr(page, "layout_profile_match", None) is not None
        for assignment in page.layout_profile_match.assignments
        if assignment.cell_role == "revision_description"
    }
    return frozenset(
        observation_id
        for observation_id in assigned_ids
        if observation_id in current_coverage
        and current_coverage[observation_id].disposition_reason
        != "welli_revision_description"
    )


def build_welli_layout_report(
    pdf_paths: Sequence[Path],
) -> dict[str, object]:
    unique_inputs, duplicate_count = _unique_pdf_inputs(pdf_paths)
    documents: list[dict[str, object]] = []
    aggregate = _empty_aggregate()
    total_pages = 0

    for source_sha256, pdf_path in unique_inputs:
        pages = tuple(build_inventory(pdf_path))
        _observation_ids(pages)
        expected_ids = tuple(
            observation.observation_id
            for observation in (
                *selected_observations(pages),
                *selected_visual_observations(pages),
            )
        )
        current = candidate_snapshot_from_inventory(pages)
        control_pages = tuple(
            replace(page, layout_profile_match=None)
            for page in pages
        )
        control = candidate_snapshot_from_inventory(control_pages)
        current_coverage = _coverage_by_id(current)
        _coverage_by_id(control)
        if current.expected_observation_ids != expected_ids:
            raise ValueError("current snapshot observation identity mismatch")
        if control.expected_observation_ids != expected_ids:
            raise ValueError("control snapshot observation identity mismatch")

        current_sources = _candidate_source_ids(current)
        control_sources = _candidate_source_ids(control)
        rerouted_ids = frozenset(control_sources - current_sources)
        aggregate["control_candidate_source_count"] += len(
            control_sources
        )
        aggregate["current_candidate_source_count"] += len(
            current_sources
        )
        aggregate["candidate_source_ids_rerouted"] += len(rerouted_ids)
        _increment_reason_counts(
            aggregate,
            rerouted_ids=rerouted_ids,
            current_coverage=current_coverage,
        )

        aggregate["watermark_native_line_count"] += sum(
            entry.disposition_reason == "welli_same_page_watermark"
            for entry in current.coverage_entries
        )
        aggregate["revision_engineering_preserved_line_count"] += len(
            _engineering_preserved_ids(pages, current_coverage)
        )
        resolved_visual_ids = frozenset(
            entry.observation_id
            for entry in current.coverage_entries
            if entry.disposition_reason == "welli_layout_visual_context"
        )
        aggregate["resolved_visual_observation_count"] += len(
            resolved_visual_ids
        )
        aggregate["required_visual_observation_count"] += len(
            current.required_visual_observation_ids
        )
        planned_ids = {
            observation_id
            for page_batches in plan_visual_batches(pages, current)
            for batch in page_batches
            for observation_id in batch.observation_ids
        }
        aggregate["resolved_visual_ids_in_planned_batches"] += len(
            resolved_visual_ids.intersection(planned_ids)
        )
        coverage = check_coverage(
            current.coverage_entries,
            expected_observation_ids=current.expected_observation_ids,
            required_visual_observation_ids=(),
        )
        aggregate["coverage_blocking_count"] += coverage.blocking_count

        page_count = len(pages)
        unsupported_count = sum(
            page.support_level == "unsupported" for page in pages
        )
        matched_count = sum(
            getattr(page, "layout_profile_match", None) is not None
            and page.layout_profile_match.match_state == "high_confidence"
            for page in pages
        )
        total_pages += page_count
        documents.append(
            {
                "source_sha256": source_sha256,
                "page_count": page_count,
                "parseable_page_count": page_count - unsupported_count,
                "unsupported_page_count": unsupported_count,
                "matched_page_count": matched_count,
            }
        )

    report: dict[str, object] = {
        "input_summary": {
            "unique_document_count": len(unique_inputs),
            "duplicate_document_count": duplicate_count,
            "page_count": total_pages,
        },
        "documents": documents,
        "aggregate": aggregate,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report": report,
        "report_sha256": hashlib.sha256(
            canonical_report_bytes(report)
        ).hexdigest(),
    }


def _environment_roots() -> tuple[Path, ...]:
    values = tuple(os.environ.get(name, "").strip() for name in _ROOT_ENV_NAMES)
    if any(not value for value in values):
        raise ValueError("corpus root environment variables are required")
    return tuple(Path(value) for value in values)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    raw_paths = _pdf_paths_from_roots(_environment_roots())
    result = build_welli_layout_report(raw_paths)
    arguments.output.write_bytes(canonical_report_bytes(result) + b"\n")
    print(
        canonical_report_bytes(
            {
                "schema_version": result["schema_version"],
                "aggregate": result["report"]["aggregate"],
                "report_sha256": result["report_sha256"],
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
