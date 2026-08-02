#!/usr/bin/env python3
"""Pure read-only validation for formal current-four live evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote


CURRENT_FOUR_ARTIFACT = "artifacts/current-four-manifest.json"
SYMBOL_EVAL_ARTIFACT = "artifacts/visual-symbol-eval.json"
SYMBOL_VERDICT_ARTIFACT = "artifacts/visual-symbol-annotation-verdict.json"
SYMBOL_RECOGNITION_REPORT = "reports/symbol-recognition.json"
SYMBOL_RECOGNITION_SELECTOR = (
    "phase://live/symbol-recognition?input_set=current-four"
)
HUMAN_VERDICT_ARTIFACT = "artifacts/human-verdict.json"
LIVE_EVIDENCE_ARTIFACT = "live-run-evidence.json"
LIVE_PHASES = ("process", "candidates", "review", "balloons", "export", "consistency")
FORMAL_ARTIFACT_KINDS = ("ballooned_pdf", "sip_excel", "manifest")
FORMAL_CONTENT_TYPES = {
    "ballooned_pdf": "application/pdf",
    "sip_excel": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    "manifest": "application/json",
}
ITEM_VERDICT_KEYS = {
    "automatic_candidates_are_actionable",
    "candidates_are_editable",
    "operator_confirmed_item_set_is_complete",
    "not_false_success",
}
BALLOON_VERDICT_KEYS = {
    "all_required_balloons_visible",
    "hard_collisions_resolved",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SchemaValidator = Callable[[Any, str, Path], None]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def run_artifact_path(
    root: Path,
    run: Mapping[str, Any],
    artifact_ref: str,
    *,
    run_dir: Path | None = None,
) -> Path:
    relative = Path(artifact_ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("contract result artifact_ref must stay inside its run")
    evidence_dir = (
        run_dir
        if run_dir is not None
        else root / ".agent/harness/runs" / str(run["run_id"])
    )
    artifact_path = evidence_dir / relative
    current = evidence_dir
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"run evidence artifact must not be a symlink: {artifact_ref}")
    if not artifact_path.is_file():
        raise ValueError(f"run evidence artifact is missing: {artifact_ref}")
    return artifact_path


def _verified_hashed_artifact(
    root: Path,
    run: Mapping[str, Any],
    artifact_ref: Any,
    expected_sha256: Any,
    *,
    run_dir: Path | None = None,
    expect_json: bool = False,
    expect_png: bool = False,
) -> tuple[Path, Any]:
    if not isinstance(artifact_ref, str) or not artifact_ref:
        raise ValueError("run evidence ref must be a non-empty relative path")
    path = run_artifact_path(root, run, artifact_ref, run_dir=run_dir)
    content = path.read_bytes()
    if (
        not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise ValueError(f"run evidence artifact hash changed: {artifact_ref}")
    if expect_png and not content.startswith(PNG_SIGNATURE):
        raise ValueError(f"run evidence artifact is not PNG: {artifact_ref}")
    if not expect_json:
        return path, content
    try:
        document = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"run evidence artifact is not JSON: {artifact_ref}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"run evidence JSON must be an object: {artifact_ref}")
    return path, document


def _item_number_pairs(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping) or set(entry) != {
            "item_id",
            "formal_number",
        }:
            return None
        item_id = entry.get("item_id")
        formal_number = entry.get("formal_number")
        if (
            not isinstance(item_id, str)
            or not item_id
            or not isinstance(formal_number, int)
            or isinstance(formal_number, bool)
            or formal_number < 1
        ):
            return None
        normalized.append(
            {"item_id": item_id, "formal_number": formal_number}
        )
    if len({entry["item_id"] for entry in normalized}) != len(normalized):
        return None
    if len({entry["formal_number"] for entry in normalized}) != len(normalized):
        return None
    return sorted(normalized, key=lambda entry: entry["item_id"])


def _unique_strings(value: Any) -> list[str] | None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        return None
    return sorted(value)


def _positive_integers(value: Any) -> list[int] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool):
            return None
        try:
            number = int(item)
        except (TypeError, ValueError):
            return None
        if number < 1 or str(item) != str(number):
            return None
        normalized.append(number)
    if len(set(normalized)) != len(normalized):
        return None
    return sorted(normalized)


def _valid_box(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(number, (int, float))
            and not isinstance(number, bool)
            and math.isfinite(number)
            for number in value
        )
        and value[0] < value[2]
        and value[1] < value[3]
    )


def canonical_project_url(project_id: str, operator_id: str) -> str:
    if not project_id or not operator_id:
        raise ValueError("project and operator identities must be non-empty")
    return f"/?project_id={quote(project_id)}&operator_id={quote(operator_id)}"


def design_qa_evidence(
    path: Path,
    run_dir: Path,
    *,
    expected_route: str,
    browser_name: str,
    viewport: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse and verify the run-bound Product Design QA document."""
    if path.name != "design-qa.md" or path.is_symlink() or not path.is_file():
        raise ValueError("design-qa.md is missing, symlinked, or misnamed")
    content = path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("design-qa.md must be UTF-8") from exc
    if "/home/" in text:
        raise ValueError("design-qa.md must not expose a host source path")

    def field(label: str) -> str:
        values = re.findall(
            rf"^{re.escape(label)}: (.+)$",
            text,
            flags=re.MULTILINE,
        )
        if len(values) != 1 or not values[0].strip():
            raise ValueError(
                f"design-qa.md required structured field is missing: {label}"
            )
        return values[0].strip()

    if len(re.findall(r"^final result: passed$", text, flags=re.MULTILINE)) != 1:
        raise ValueError("design-qa.md requires exactly one final result: passed")
    if re.search(r"^final result: blocked$", text, flags=re.MULTILINE):
        raise ValueError("blocked design QA cannot support formal evidence")
    source_sha256 = field("source sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("design-qa.md source identity must be SHA-256")
    if field("implementation route") != expected_route:
        raise ValueError("design-qa.md implementation route is not run-bound")
    implementation_state = field("implementation state")
    if implementation_state != "visual_qa_pending:first-pdf-balloons":
        raise ValueError("design-qa.md implementation state is not the pause barrier")
    width = viewport.get("width")
    height = viewport.get("height")
    if (
        field("browser") != browser_name
        or not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or field("viewport") != f"{width}x{height}"
    ):
        raise ValueError("design-qa.md browser/viewport differs from the run")

    captures: dict[str, str] = {}
    capture_refs: list[str] = []
    capture_digests: list[str] = []
    reports_root = (run_dir / "reports").resolve(strict=False)
    for kind in ("implementation", "comparison"):
        ref = field(f"{kind} capture")
        digest = field(f"{kind} capture sha256")
        if not re.fullmatch(
            r"reports/[A-Za-z0-9][A-Za-z0-9._-]*\.png",
            ref,
        ):
            raise ValueError(f"design-qa.md {kind} capture ref is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"design-qa.md {kind} capture identity is invalid")
        capture = run_dir / ref
        if (
            capture.is_symlink()
            or not capture.is_file()
            or reports_root not in capture.resolve().parents
        ):
            raise ValueError(f"design-qa.md {kind} capture is unavailable")
        capture_content = capture.read_bytes()
        if not capture_content.startswith(PNG_SIGNATURE):
            raise ValueError(f"design-qa.md {kind} capture must be a PNG")
        if hashlib.sha256(capture_content).hexdigest() != digest:
            raise ValueError(f"design-qa.md {kind} capture identity changed")
        captures[f"{kind}_capture_ref"] = ref
        captures[f"{kind}_capture_sha256"] = digest
        capture_refs.append(ref)
        capture_digests.append(digest)
    if len(set(capture_refs)) != 2 or len(set(capture_digests)) != 2:
        raise ValueError("design-qa.md comparison captures must be distinct")

    count_labels = {
        "console_error_count": "console errors",
        "network_error_count": "network errors",
        "p0": "P0 issues",
        "p1": "P1 issues",
        "p2": "P2 issues",
    }
    counts: dict[str, int] = {}
    for key, label in count_labels.items():
        if field(label) != "0":
            raise ValueError(f"design-qa.md {label} must be zero")
        counts[key] = 0
    return {
        "ref": "design-qa.md",
        "sha256": hashlib.sha256(content).hexdigest(),
        "final_result": "passed",
        "browser": browser_name,
        "viewport": dict(viewport),
        "source_sha256": source_sha256,
        "implementation_route": expected_route,
        "implementation_state": implementation_state,
        **captures,
        "console_error_count": counts["console_error_count"],
        "network_error_count": counts["network_error_count"],
        "issue_counts": {
            "p0": counts["p0"],
            "p1": counts["p1"],
            "p2": counts["p2"],
        },
    }


def validate_candidate_evidence(order: int, candidates: Mapping[str, Any]) -> None:
    candidate_ids = _unique_strings(candidates.get("candidate_ids"))
    source_ids = _unique_strings(candidates.get("source_location_ids"))
    records = candidates.get("candidate_records")
    count = candidates.get("candidate_count")
    coverage_count = candidates.get("coverage_disposition_count")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or candidate_ids is None
        or len(candidate_ids) != count
        or source_ids is None
        or not isinstance(records, list)
        or len(records) != count
        or candidates.get("coverage_checked") is not True
        or candidates.get("coverage_blocking_count") != 0
        or not isinstance(coverage_count, int)
        or isinstance(coverage_count, bool)
        or coverage_count < count
    ):
        raise ValueError(f"sample {order} candidate coverage is incomplete")
    record_ids: list[str] = []
    observed_source_ids: list[str] = []
    for record in records:
        if not isinstance(record, Mapping) or not _valid_box(
            record.get("coordinates")
        ):
            raise ValueError(f"sample {order} candidate coordinates are invalid")
        candidate_id = record.get("candidate_id")
        evidence = record.get("source_evidence")
        expected_source_ids = _unique_strings(record.get("source_location_ids"))
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(evidence, list)
            or not evidence
            or expected_source_ids is None
        ):
            raise ValueError(f"sample {order} candidate source evidence is missing")
        record_ids.append(candidate_id)
        record_source_ids: list[str] = []
        has_primary_candidate_coverage = False
        for source in evidence:
            if (
                not isinstance(source, Mapping)
                or set(source)
                != {
                    "source_location_id",
                    "source_type",
                    "observation_level",
                    "coordinates",
                    "coverage",
                }
                or not isinstance(source.get("source_location_id"), str)
                or not source["source_location_id"]
                or not isinstance(source.get("source_type"), str)
                or not source["source_type"]
                or not isinstance(source.get("observation_level"), str)
                or not source["observation_level"]
                or not _valid_box(source.get("coordinates"))
            ):
                raise ValueError(
                    f"sample {order} candidate source coordinates are invalid"
                )
            source_id = source["source_location_id"]
            coverage = source.get("coverage")
            if coverage is not None and (
                not isinstance(coverage, Mapping)
                or set(coverage) != {"disposition", "candidate_id"}
                or coverage.get("disposition")
                not in {
                    "candidate",
                    "reference_context",
                    "non_inspection",
                    "ambiguous",
                }
                or (
                    coverage.get("candidate_id") is not None
                    and (
                        not isinstance(coverage["candidate_id"], str)
                        or not coverage["candidate_id"]
                    )
                )
            ):
                raise ValueError(
                    f"sample {order} candidate source coverage is invalid"
                )
            if source["source_type"] == "visual":
                if (
                    source["observation_level"] != "annotation_context"
                    or not isinstance(coverage, Mapping)
                    or coverage.get("disposition") != "candidate"
                    or coverage.get("candidate_id") != candidate_id
                ):
                    raise ValueError(
                        f"sample {order} visual candidate coverage is missing"
                    )
                has_primary_candidate_coverage = True
            elif coverage is None:
                if (
                    source["source_type"] != "native"
                    or source["observation_level"] != "span"
                ):
                    raise ValueError(
                        f"sample {order} candidate text coverage is invalid"
                    )
            elif coverage.get("disposition") == "candidate":
                if coverage.get("candidate_id") != candidate_id:
                    raise ValueError(
                        f"sample {order} candidate text coverage is invalid"
                    )
                has_primary_candidate_coverage = True
            elif (
                coverage.get("disposition") != "ambiguous"
                or coverage.get("candidate_id") is not None
            ):
                raise ValueError(
                    f"sample {order} candidate text coverage is invalid"
                )
            record_source_ids.append(source_id)
        if _unique_strings(record_source_ids) != expected_source_ids:
            raise ValueError(f"sample {order} candidate source IDs are spliced")
        if not has_primary_candidate_coverage:
            raise ValueError(
                f"sample {order} candidate primary coverage is missing"
            )
        observed_source_ids.extend(expected_source_ids)
    if (
        _unique_strings(record_ids) != candidate_ids
        or sorted(set(observed_source_ids)) != source_ids
    ):
        raise ValueError(f"sample {order} candidate inventory is spliced")


def review_item_set_ready(
    review: Mapping[str, Any],
    candidates: Mapping[str, Any],
    item_write: Mapping[str, Any],
    *,
    operator_id: str,
) -> bool:
    commands = set(review.get("operation_commands", []))
    candidate_ids = set(candidates.get("candidate_ids", []))
    operation_targets = set(review.get("operation_target_ids", []))
    decisions = review.get("candidate_decisions")
    if not isinstance(decisions, list):
        return False
    decision_ids: list[str] = []
    decisions_ok = True
    for decision in decisions:
        if not isinstance(decision, Mapping):
            return False
        candidate_id = decision.get("candidate_id")
        final_state = decision.get("final_state")
        decision_commands = set(decision.get("commands", []))
        if not isinstance(candidate_id, str):
            return False
        decision_ids.append(candidate_id)
        decisions_ok = decisions_ok and bool(
            (final_state == "active" and "keep" in decision_commands)
            or (final_state == "excluded" and "exclude" in decision_commands)
            or (
                final_state == "superseded"
                and bool({"merge", "split"} & decision_commands)
            )
        )
    disposition = item_write.get("merge_split_disposition")
    merge_split_ok = bool(
        (
            disposition == "not_applicable"
            and not ({"merge", "split"} & commands)
        )
        or (disposition == "merge" and "merge" in commands)
        or (disposition == "split" and "split" in commands)
    )
    required_commands = {
        "keep",
        "exclude",
        "edit",
        "add",
        "resolve_confirmation",
    }
    return bool(
        required_commands.issubset(commands)
        and candidate_ids
        and candidate_ids.issubset(operation_targets)
        and len(decision_ids) == len(set(decision_ids))
        and set(decision_ids) == candidate_ids
        and decisions_ok
        and review.get("operation_operator_ids") == [operator_id]
        and review.get("active_item_ids")
        and review.get("excluded_item_ids")
        and merge_split_ok
        and review.get("merge_split_disposition", disposition) == disposition
        and review.get("merge_split_note", item_write.get("merge_split_note"))
        == item_write.get("merge_split_note")
        and bool(item_write.get("merge_split_note"))
    )


def _strict_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be one UTC timestamp")
    try:
        parsed = _parse_iso(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be one UTC timestamp") from exc
    return parsed



def _validate_design_evidence(
    root: Path,
    run: Mapping[str, Any],
    design: Mapping[str, Any],
    expected_route: str,
    *,
    run_dir: Path | None = None,
    design_path: Path | None = None,
) -> None:
    live_identity = run.get("live_identity")
    if not isinstance(live_identity, Mapping):
        raise ValueError("formal live identity is missing")
    browser = live_identity.get("browser")
    viewport = live_identity.get("viewport")
    if not isinstance(browser, Mapping) or not isinstance(viewport, Mapping):
        raise ValueError("design QA browser or viewport is not run-bound")
    evidence_dir = (
        run_dir
        if run_dir is not None
        else root / ".agent/harness/runs" / str(run["run_id"])
    )
    evidence_path = (
        design_path if design_path is not None else root / "design-qa.md"
    )
    expected = design_qa_evidence(
        evidence_path,
        evidence_dir,
        expected_route=expected_route,
        browser_name=str(browser.get("name")),
        viewport=viewport,
    )
    if dict(design) != expected:
        raise ValueError("design QA evidence differs from its verified document")


def validate_browser_result(
    run_id: str,
    order: int,
    project_id: str,
    phase: str,
    result: Mapping[str, Any],
    *,
    expected_captured_at: Any = None,
) -> None:
    """Validate one browser result before it can become formal evidence."""
    if phase not in {"pre-export", "export"}:
        raise ValueError(f"sample {order} browser phase is invalid")
    table_pairs = _item_number_pairs(result.get("table_item_numbers"))
    backend_pairs = _item_number_pairs(result.get("backend_item_numbers"))
    overlay_pairs = _item_number_pairs(result.get("overlay_item_numbers"))
    active_ids = _unique_strings(result.get("table_active_item_ids"))
    expected_schema = f"p0-browser-{phase}-evidence/1"
    if (
        result.get("schema_version") != expected_schema
        or result.get("run_id") != run_id
        or result.get("order") != order
        or result.get("project_id") != project_id
        or result.get("phase") != phase
        or not isinstance(result.get("captured_at"), str)
        or (
            expected_captured_at is not None
            and result.get("captured_at") != expected_captured_at
        )
        or result.get("glyph_metrics_verified") is not True
        or table_pairs is None
        or table_pairs != backend_pairs
        or table_pairs != overlay_pairs
        or active_ids is None
    ):
        raise ValueError(f"sample {order} {phase} browser result is not run-bound")
    expected_ids = sorted(entry["item_id"] for entry in table_pairs)
    expected_numbers = sorted(entry["formal_number"] for entry in table_pairs)
    if phase == "pre-export":
        actions = result.get("actions")
        if (
            result.get("formal_publish_attempted") is not False
            or result.get("hard_collision_count") != 0
            or result.get("unresolved_manual_required_count") != 0
            or _unique_strings(result.get("active_item_ids")) != expected_ids
            or _positive_integers(result.get("active_item_numbers"))
            != expected_numbers
            or _positive_integers(result.get("overlay_numbers"))
            != expected_numbers
            or not isinstance(actions, Mapping)
            or dict(actions)
            != {"drag": True, "delete": True, "rebuild": True, "renumber": True}
        ):
            raise ValueError(
                f"sample {order} pre-export browser result is inconsistent"
            )
        return

    artifacts = result.get("artifacts")
    artifact_by_kind = {
        artifact.get("kind"): artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    } if isinstance(artifacts, list) else {}
    if (
        result.get("formal_publish_attempted") is not True
        or result.get("status") != "success"
        or not result.get("reviewed_result_id")
        or not result.get("export_id")
        or _unique_strings(result.get("reviewed_item_ids")) != expected_ids
        or _positive_integers(result.get("reviewed_numbers"))
        != expected_numbers
        or result.get("download_kinds") != list(FORMAL_ARTIFACT_KINDS)
        or not isinstance(artifacts, list)
        or len(artifacts) != 3
        or set(artifact_by_kind) != set(FORMAL_ARTIFACT_KINDS)
        or any(
            artifact.get("downloadable") is not True
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                str(artifact.get("sha256", "")),
            )
            or not isinstance(artifact.get("size_bytes"), int)
            or isinstance(artifact.get("size_bytes"), bool)
            or artifact["size_bytes"] < 1
            or not str(artifact.get("content_type", "")).startswith(
                FORMAL_CONTENT_TYPES[kind]
            )
            for kind, artifact in artifact_by_kind.items()
        )
    ):
        raise ValueError(f"sample {order} export browser result is inconsistent")


def bind_post_export_evidence(
    run_id: str,
    order: int,
    project_id: str,
    browser_result: Mapping[str, Any],
    export: Mapping[str, Any],
    consistency: Mapping[str, Any],
) -> dict[str, Any]:
    """Cross-bind browser downloads, backend export, and reviewed item numbers."""
    validate_browser_result(
        run_id,
        order,
        project_id,
        "export",
        browser_result,
    )
    reviewed_result_id = export.get("reviewed_result_id")
    artifact_hashes = export.get("artifact_sha256")
    artifact_reviewed_ids = export.get("artifact_reviewed_result_ids")
    artifacts = browser_result.get("artifacts")
    artifact_by_kind = {
        artifact.get("kind"): artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    } if isinstance(artifacts, list) else {}
    if (
        not isinstance(reviewed_result_id, str)
        or not reviewed_result_id
        or not export.get("export_id")
        or export.get("status") != "success"
        or export.get("artifact_kinds") != list(FORMAL_ARTIFACT_KINDS)
        or export.get("download_kinds") != list(FORMAL_ARTIFACT_KINDS)
        or not isinstance(artifact_hashes, list)
        or len(artifact_hashes) != 3
        or any(
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in artifact_hashes
        )
        or artifact_reviewed_ids != [reviewed_result_id] * 3
        or browser_result.get("reviewed_result_id") != reviewed_result_id
        or browser_result.get("export_id") != export.get("export_id")
        or set(artifact_by_kind) != set(FORMAL_ARTIFACT_KINDS)
    ):
        raise ValueError(f"sample {order} formal artifact set is incomplete")
    for index, kind in enumerate(FORMAL_ARTIFACT_KINDS):
        artifact = artifact_by_kind[kind]
        if (
            artifact.get("sha256") != artifact_hashes[index]
            or artifact.get("download_sha256") != artifact_hashes[index]
            or artifact.get("reviewed_result_id") != reviewed_result_id
            or artifact.get("download_size_bytes") != artifact.get("size_bytes")
        ):
            raise ValueError(
                f"sample {order} downloaded {kind} identity is inconsistent"
            )

    table_pairs = _item_number_pairs(browser_result.get("table_item_numbers"))
    overlay_pairs = _item_number_pairs(
        browser_result.get("overlay_item_numbers")
    )
    backend_pairs = _item_number_pairs(
        browser_result.get("backend_item_numbers")
    )
    reviewed_pairs = _item_number_pairs(
        consistency.get("reviewed_item_numbers")
    )
    table_active_ids = _unique_strings(
        browser_result.get("table_active_item_ids")
    )
    reviewed_active_ids = _unique_strings(
        consistency.get("reviewed_active_item_ids")
    )
    if (
        table_pairs is None
        or table_pairs != overlay_pairs
        or table_pairs != backend_pairs
        or table_pairs != reviewed_pairs
        or table_active_ids is None
        or table_active_ids != reviewed_active_ids
    ):
        raise ValueError(
            f"sample {order} workbench items differ from reviewed result"
        )
    bound = dict(consistency)
    bound["workbench_item_numbers"] = table_pairs
    bound["workbench_overlay_item_numbers"] = overlay_pairs
    bound["workbench_active_item_ids"] = table_active_ids
    bound["workbench_numbers"] = sorted(
        entry["formal_number"] for entry in table_pairs
    )
    return bound


def _validate_browser_evidence(
    root: Path,
    run: Mapping[str, Any],
    *,
    run_dir: Path | None = None,
    order: int,
    project_id: str,
    phase: str,
    browser: Mapping[str, Any],
) -> dict[str, Any]:
    screenshots = browser.get("screenshot_refs")
    if browser.get("passed") is not True or not isinstance(screenshots, list) or len(screenshots) != 1:
        raise ValueError(f"sample {order} {phase} browser evidence is incomplete")
    _verified_hashed_artifact(
        root,
        run,
        browser.get("report_ref"),
        browser.get("report_sha256"),
        run_dir=run_dir,
        expect_json=True,
    )
    _verified_hashed_artifact(
        root,
        run,
        screenshots[0],
        browser.get("screenshot_sha256"),
        run_dir=run_dir,
        expect_png=True,
    )
    _, result = _verified_hashed_artifact(
        root,
        run,
        browser.get("result_ref"),
        browser.get("result_sha256"),
        run_dir=run_dir,
        expect_json=True,
    )
    validate_browser_result(
        str(run.get("run_id")),
        order,
        project_id,
        phase,
        result,
        expected_captured_at=browser.get("captured_at"),
    )
    return result


def _validate_formal_sample(
    root: Path,
    run: Mapping[str, Any],
    entry: Mapping[str, Any],
    verdict_sample: Mapping[str, Any],
    sample: Mapping[str, Any],
    *,
    run_dir: Path | None = None,
) -> None:
    order = int(entry["order"])
    project_id = sample.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError(f"sample {order} project identity is missing")
    if (
        sample.get("order") != order
        or sample.get("opaque_ref") != entry.get("opaque_ref")
        or verdict_sample.get("order") != order
        or verdict_sample.get("project_id") != project_id
    ):
        raise ValueError(f"sample {order} current-four identity is spliced")

    live_identity = run.get("live_identity")
    operator_id = (
        live_identity.get("operator_id")
        if isinstance(live_identity, Mapping)
        else None
    )
    item_write = verdict_sample.get("item_set")
    balloon_write = verdict_sample.get("balloons")
    if not isinstance(item_write, Mapping) or not isinstance(balloon_write, Mapping):
        raise ValueError(f"sample {order} human verdict stages are incomplete")
    item_answers = item_write.get("answers")
    balloon_answers = balloon_write.get("answers")
    if (
        not isinstance(item_answers, Mapping)
        or set(item_answers) != ITEM_VERDICT_KEYS
        or not all(value is True for value in item_answers.values())
        or not isinstance(balloon_answers, Mapping)
        or set(balloon_answers) != BALLOON_VERDICT_KEYS
        or not all(value is True for value in balloon_answers.values())
        or item_write.get("operator_id") != operator_id
        or balloon_write.get("operator_id") != operator_id
    ):
        raise ValueError(f"sample {order} human verdict is not affirmative/run-bound")
    merged = {**item_answers, **balloon_answers}
    if (
        verdict_sample.get("merged_verdict") != merged
        or sample.get("human_verdict") != merged
    ):
        raise ValueError(f"sample {order} merged human verdict is inconsistent")

    process = sample.get("process")
    candidates = sample.get("candidates")
    review = sample.get("review")
    balloons = sample.get("balloons")
    export = sample.get("export")
    consistency = sample.get("consistency")
    if not all(
        isinstance(section, Mapping)
        for section in (process, candidates, review, balloons, export, consistency)
    ):
        raise ValueError(f"sample {order} live phase evidence is incomplete")
    validate_candidate_evidence(order, candidates)
    metadata = entry.get("page_metadata")
    if (
        not isinstance(metadata, Mapping)
        or process.get("source_sha256") != entry.get("sha256")
        or process.get("actual_page_count") != metadata.get("page_count")
        or process.get("expected_page_count") != metadata.get("page_count")
        or process.get("expected_physical_page") != metadata.get("physical_page")
        or process.get("actual_physical_pages") != [metadata.get("physical_page")]
    ):
        raise ValueError(f"sample {order} source/page evidence is inconsistent")
    _verified_hashed_artifact(
        root,
        run,
        process.get("prepare_log_ref"),
        process.get("prepare_log_sha256"),
        run_dir=run_dir,
    )

    _, review_report = _verified_hashed_artifact(
        root,
        run,
        review.get("evidence_ref"),
        review.get("evidence_sha256"),
        run_dir=run_dir,
        expect_json=True,
    )
    expected_review = {
        key: value
        for key, value in review.items()
        if key
        not in {
            "merge_split_disposition",
            "merge_split_note",
            "evidence_ref",
            "evidence_sha256",
        }
    }
    if (
        review_report.get("run_id") != run.get("run_id")
        or review_report.get("order") != order
        or review_report.get("project_id") != project_id
        or review_report.get("review") != expected_review
        or review_report.get("balloons")
        != {key: value for key, value in balloons.items() if key != "browser"}
        or review.get("merge_split_disposition")
        != item_write.get("merge_split_disposition")
        or review.get("merge_split_note") != item_write.get("merge_split_note")
    ):
        raise ValueError(f"sample {order} review evidence is not cross-bound")
    if not (
        _strict_timestamp(item_write.get("recorded_at"), "item verdict")
        < _strict_timestamp(review.get("items_frozen_at"), "item freeze")
    ):
        raise ValueError(f"sample {order} item verdict did not precede freeze")
    active_item_ids = _unique_strings(review.get("active_item_ids"))
    balloon_required_ids = _unique_strings(review.get("balloon_required_item_ids"))
    excluded_item_ids = _unique_strings(review.get("excluded_item_ids"))
    if (
        not review.get("frozen_version")
        or review.get("frozen_by") != operator_id
        or active_item_ids is None
        or balloon_required_ids is None
        or excluded_item_ids is None
        or not set(balloon_required_ids) <= set(active_item_ids)
        or set(active_item_ids) & set(excluded_item_ids)
        or not review_item_set_ready(
            review,
            candidates,
            item_write,
            operator_id=str(operator_id),
        )
    ):
        raise ValueError(f"sample {order} frozen review ownership is inconsistent")

    balloon_browser = balloons.get("browser")
    export_browser = export.get("browser")
    if not isinstance(balloon_browser, Mapping) or not isinstance(export_browser, Mapping):
        raise ValueError(f"sample {order} browser phase evidence is missing")
    pre_result = _validate_browser_evidence(
        root,
        run,
        run_dir=run_dir,
        order=order,
        project_id=project_id,
        phase="pre-export",
        browser=balloon_browser,
    )
    export_result = _validate_browser_evidence(
        root,
        run,
        run_dir=run_dir,
        order=order,
        project_id=project_id,
        phase="export",
        browser=export_browser,
    )
    if not (
        _strict_timestamp(pre_result.get("captured_at"), "pre-export capture")
        < _strict_timestamp(balloon_write.get("recorded_at"), "balloon verdict")
        < _strict_timestamp(export_result.get("captured_at"), "export capture")
    ):
        raise ValueError(f"sample {order} balloon verdict order is invalid")
    if (
        balloons.get("hard_collision_count") != 0
        or balloons.get("unresolved_manual_required_count") != 0
        or _unique_strings(balloons.get("active_item_ids"))
        != balloon_required_ids
        or len(balloons.get("formal_numbers", [])) != len(balloon_required_ids)
        or pre_result.get("formal_publish_attempted") is not False
        or pre_result.get("hard_collision_count") != 0
        or pre_result.get("unresolved_manual_required_count") != 0
    ):
        raise ValueError(f"sample {order} balloon gate is not clear")
    pre_pairs = _item_number_pairs(pre_result.get("table_item_numbers"))
    if (
        pre_pairs is None
        or sorted(entry["item_id"] for entry in pre_pairs)
        != sorted(balloons["active_item_ids"])
        or sorted(entry["formal_number"] for entry in pre_pairs)
        != sorted(balloons["formal_numbers"])
        or pre_result.get("formal_publish_attempted") is not False
        or pre_result.get("actions")
        != {"drag": True, "delete": True, "rebuild": True, "renumber": True}
    ):
        raise ValueError(f"sample {order} pre-export mapping is inconsistent")

    bound_consistency = bind_post_export_evidence(
        str(run.get("run_id")),
        order,
        project_id,
        export_result,
        export,
        consistency,
    )
    if dict(consistency) != bound_consistency:
        raise ValueError(
            f"sample {order} stored post-export binding is inconsistent"
        )
    reviewed_result_id = export.get("reviewed_result_id")

    _, consistency_report = _verified_hashed_artifact(
        root,
        run,
        consistency.get("evidence_ref"),
        consistency.get("evidence_sha256"),
        run_dir=run_dir,
        expect_json=True,
    )
    expected_consistency = {
        key: value
        for key, value in consistency.items()
        if key not in {"evidence_ref", "evidence_sha256"}
    }
    number_sets = [
        consistency.get(name)
        for name in (
            "workbench_numbers",
            "reviewed_numbers",
            "pdf_numbers",
            "excel_numbers",
        )
    ]
    normalized_numbers = [
        sorted(values) if isinstance(values, list) else None
        for values in number_sets
    ]
    if (
        consistency_report.get("run_id") != run.get("run_id")
        or consistency_report.get("order") != order
        or consistency_report.get("project_id") != project_id
        or consistency_report.get("export")
        != {key: value for key, value in export.items() if key != "browser"}
        or consistency_report.get("consistency") != expected_consistency
        or consistency.get("verified") is not True
        or consistency.get("reviewed_result_id") != reviewed_result_id
        or consistency.get("reviewed_item_ids")
        != consistency.get("balloon_item_ids")
        or normalized_numbers[0] is None
        or normalized_numbers[0]
        != normalized_numbers[1]
        or normalized_numbers[0]
        != normalized_numbers[2]
        or normalized_numbers[0]
        != normalized_numbers[3]
        or consistency.get("reviewed_item_count")
        != consistency.get("manifest_reviewed_item_count")
        or consistency.get("balloon_count")
        != consistency.get("manifest_balloon_count")
        or consistency.get("balloon_required_count")
        != consistency.get("manifest_balloon_required_count")
        or consistency.get("source_page_count")
        != consistency.get("manifest_source_page_count")
        or consistency.get("source_page_count") != process.get("actual_page_count")
    ):
        raise ValueError(f"sample {order} export consistency is not cross-bound")
    item_pairs = _item_number_pairs(consistency.get("reviewed_item_numbers"))
    reviewed_active_ids = _unique_strings(
        consistency.get("reviewed_active_item_ids")
    )
    reviewed_item_ids = _unique_strings(consistency.get("reviewed_item_ids"))
    balloon_item_ids = _unique_strings(consistency.get("balloon_item_ids"))
    if (
        not item_pairs
        or reviewed_active_ids != active_item_ids
        or reviewed_item_ids != balloon_required_ids
        or balloon_item_ids != balloon_required_ids
        or consistency.get("reviewed_item_count") != len(reviewed_active_ids)
        or consistency.get("balloon_required_count") != len(balloon_required_ids)
        or consistency.get("balloon_count") != len(balloon_required_ids)
        or [entry["item_id"] for entry in item_pairs] != reviewed_item_ids
        or sorted(entry["formal_number"] for entry in item_pairs)
        != normalized_numbers[0]
        or len(number_sets[0] or []) != len(balloon_required_ids)
    ):
        raise ValueError(f"sample {order} item-number projections differ")


def validate_symbol_recognition_evidence(
    root: Path,
    run: Mapping[str, Any],
    current_four: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    schema_validator: SchemaValidator,
    run_dir: Path,
) -> None:
    evidence = live.get("symbol_recognition")
    if not isinstance(evidence, Mapping):
        raise ValueError("symbol recognition evidence is missing")
    symbol_path = run_artifact_path(
        root,
        run,
        SYMBOL_EVAL_ARTIFACT,
        run_dir=run_dir,
    )
    verdict_path = run_artifact_path(
        root,
        run,
        SYMBOL_VERDICT_ARTIFACT,
        run_dir=run_dir,
    )
    symbol_bytes = symbol_path.read_bytes()
    verdict_bytes = verdict_path.read_bytes()
    try:
        symbol_manifest = json.loads(symbol_bytes)
        annotation_verdict = json.loads(verdict_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("sealed symbol input is not JSON") from exc
    schema_validator(
        symbol_manifest,
        "visual-symbol-eval.schema.json",
        root,
    )
    schema_validator(
        annotation_verdict,
        "visual-symbol-annotation-verdict.schema.json",
        root,
    )
    manifest_sha256 = hashlib.sha256(symbol_bytes).hexdigest()
    verdict_sha256 = hashlib.sha256(verdict_bytes).hexdigest()
    entries = current_four.get("entries")
    samples = live.get("samples")
    if (
        not isinstance(entries, list)
        or not entries
        or not isinstance(samples, list)
        or not samples
        or symbol_manifest.get("source_sha256") != entries[0].get("sha256")
        or annotation_verdict.get("manifest_sha256") != manifest_sha256
        or evidence.get("source_sha256") != entries[0].get("sha256")
        or evidence.get("manifest_sha256") != manifest_sha256
        or evidence.get("annotation_verdict_sha256") != verdict_sha256
        or evidence.get("order") != 1
        or evidence.get("project_id") != samples[0].get("project_id")
        or evidence.get("automatic_result_id")
        != samples[0].get("process", {}).get("automatic_result_id")
    ):
        raise ValueError("symbol recognition input/result identity is inconsistent")

    labels = [
        label
        for page in symbol_manifest.get("pages", [])
        for label in page.get("labels", [])
    ]
    positives = [
        label
        for label in labels
        if label.get("symbol_kinds") != ["frozen_negative"]
    ]
    negatives = [
        label
        for label in labels
        if label.get("symbol_kinds") == ["frozen_negative"]
    ]
    positive_counts: dict[str, int] = {}
    for label in positives:
        for kind in label.get("symbol_kinds", []):
            positive_counts[str(kind)] = positive_counts.get(str(kind), 0) + 1
    negative_counts: dict[str, int] = {}
    for label in negatives:
        family = str(label.get("negative_family"))
        negative_counts[family] = negative_counts.get(family, 0) + 1
    if (
        evidence.get("passed") is not True
        or evidence.get("selector") != SYMBOL_RECOGNITION_SELECTOR
        or evidence.get("label_count") != len(labels)
        or evidence.get("positive_label_count") != len(positives)
        or evidence.get("negative_label_count") != len(negatives)
        or evidence.get("positive_family_counts") != positive_counts
        or evidence.get("negative_family_counts") != negative_counts
        or evidence.get("negative_false_positive_count") != 0
        or evidence.get("source_command_count") != 0
    ):
        raise ValueError("symbol recognition counts or verdict are inconsistent")

    visual_calls = evidence.get("visual_calls_by_page")
    total_calls = evidence.get("total_vision_calls_by_page")
    if (
        not isinstance(visual_calls, list)
        or not isinstance(total_calls, list)
        or len(visual_calls) != 2
        or len(total_calls) != 2
        or any(
            visual.get("page_index") != total.get("page_index")
            or not isinstance(visual.get("count"), int)
            or not isinstance(total.get("count"), int)
            or visual["count"] < 0
            or total["count"] < visual["count"]
            or visual["count"] > 16
            or total["count"] > 16
            for visual, total in zip(visual_calls, total_calls, strict=True)
            if isinstance(visual, Mapping) and isinstance(total, Mapping)
        )
        or any(
            not isinstance(item, Mapping)
            for item in (*visual_calls, *total_calls)
        )
    ):
        raise ValueError("symbol recognition Vision call counts are invalid")

    _, report = _verified_hashed_artifact(
        root,
        run,
        evidence.get("report_ref"),
        evidence.get("report_sha256"),
        run_dir=run_dir,
        expect_json=True,
    )
    expected_report_fields = {
        "schema_version",
        "selector",
        "run_id",
        "order",
        "project_id",
        "automatic_result_id",
        "source_sha256",
        "manifest_sha256",
        "annotation_verdict_sha256",
        "visual_calls_by_page",
        "total_vision_calls_by_page",
        "source_command_count",
        "typed_gdt_cases",
        "provider_call_identities",
        "evaluation",
        "failures",
        "passed",
    }
    evaluation = report.get("evaluation")
    typed_cases = report.get("typed_gdt_cases")
    provider_identities = report.get("provider_call_identities")
    expected_cases = {
        "case_a": ("parallelism", "∥", "0.1", ["A"], "gdt_parallelism"),
        "case_b": ("flatness", "⏥", "0.08", [], "gdt_flatness"),
    }
    typed_cases_valid = isinstance(typed_cases, Mapping) and set(
        typed_cases
    ) == set(expected_cases)
    if typed_cases_valid:
        for case_name, expected in expected_cases.items():
            case = typed_cases[case_name]
            datums = case.get("datum_references") if isinstance(case, Mapping) else None
            datum_names = (
                [entry.get("datum") for entry in datums if isinstance(entry, Mapping)]
                if isinstance(datums, list)
                else None
            )
            frames = case.get("frames") if isinstance(case, Mapping) else None
            first_frame = frames[0] if isinstance(frames, list) and frames else None
            segments = (
                first_frame.get("segments")
                if isinstance(first_frame, Mapping)
                else None
            )
            first_segment = (
                segments[0]
                if isinstance(segments, list) and segments
                else None
            )
            segment_datums = (
                first_segment.get("datum_references")
                if isinstance(first_segment, Mapping)
                else None
            )
            segment_datum_names = (
                [
                    entry.get("datum")
                    for entry in segment_datums
                    if isinstance(entry, Mapping)
                ]
                if isinstance(segment_datums, list)
                else None
            )
            if (
                not isinstance(case, Mapping)
                or set(case)
                != {
                    "candidate_id",
                    "annotation_label_id",
                    "schema_version",
                    "item_type",
                    "tolerance_type",
                    "tolerance_symbol",
                    "tolerance_value",
                    "datum_references",
                    "frames",
                    "source_location_ids",
                }
                or not isinstance(case.get("candidate_id"), str)
                or not isinstance(case.get("annotation_label_id"), str)
                or case.get("schema_version")
                != "geometric-tolerance-candidate/1"
                or case.get("item_type") != "geometric_tolerance"
                or (
                    case.get("tolerance_type"),
                    case.get("tolerance_symbol"),
                    case.get("tolerance_value"),
                    datum_names,
                )
                != expected[:4]
                or not isinstance(first_segment, Mapping)
                or first_segment.get("tolerance_value") != expected[2]
                or first_segment.get("diameter_modifier") is not False
                or segment_datum_names != expected[3]
                or not isinstance(case.get("source_location_ids"), list)
                or not case["source_location_ids"]
            ):
                typed_cases_valid = False
                break
    schema_path = (
        root / "backend/app/providers/visual_symbol_review.schema.json"
    )
    expected_schema_sha256 = (
        hashlib.sha256(schema_path.read_bytes()).hexdigest()
        if schema_path.is_file()
        else None
    )

    def provider_identity_is_valid(identity: Any) -> bool:
        if not isinstance(identity, Mapping):
            return False
        visual_ids = identity.get("visual_observation_ids")
        crop_bbox_pdf = identity.get("crop_bbox_pdf")
        prompt_identity = json.dumps(
            {
                "prompt_version": identity.get("prompt_version"),
                "schema_version": identity.get("schema_version"),
                "visual_observation_ids": visual_ids,
                "crop_bbox_pdf": crop_bbox_pdf,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            crop_artifact_valid = _verified_hashed_artifact(
                root,
                run,
                identity.get("crop_ref"),
                identity.get("crop_sha256"),
                run_dir=run_dir,
                expect_png=True,
            )[0].is_file()
        except ValueError:
            crop_artifact_valid = False
        return bool(
            set(identity)
            == {
                "source_sha256",
                "visual_observation_ids",
                "crop_bbox_pdf",
                "crop_sha256",
                "crop_ref",
                "model",
                "model_identity_sha256",
                "prompt_version",
                "prompt_identity_sha256",
                "schema_version",
                "schema_sha256",
                "request_id_sha256",
            }
            and identity.get("source_sha256") == report.get("source_sha256")
            and identity.get("crop_ref")
            == f"artifacts/provider-crops/{identity.get('crop_sha256')}.png"
            and isinstance(visual_ids, list)
            and bool(visual_ids)
            and isinstance(crop_bbox_pdf, list)
            and len(crop_bbox_pdf) == 4
            and all(
                isinstance(identity.get(field), str)
                and bool(identity[field])
                for field in ("model", "prompt_version", "schema_version")
            )
            and all(
                isinstance(identity.get(field), str)
                and re.fullmatch(r"[0-9a-f]{64}", identity[field]) is not None
                for field in (
                    "source_sha256",
                    "crop_sha256",
                    "model_identity_sha256",
                    "prompt_identity_sha256",
                    "schema_sha256",
                    "request_id_sha256",
                )
            )
            and identity.get("model_identity_sha256")
            == hashlib.sha256(identity["model"].encode("utf-8")).hexdigest()
            and identity.get("prompt_identity_sha256")
            == hashlib.sha256(prompt_identity).hexdigest()
            and (
                expected_schema_sha256 is None
                or identity.get("schema_sha256") == expected_schema_sha256
            )
            and crop_artifact_valid
        )

    provider_identities_valid = (
        isinstance(provider_identities, list)
        and bool(provider_identities)
        and all(provider_identity_is_valid(identity) for identity in provider_identities)
        and len(
            {identity["request_id_sha256"] for identity in provider_identities}
        )
        == len(provider_identities)
    )
    case_bindings_valid = bool(
        typed_cases_valid
        and isinstance(typed_cases, Mapping)
        and isinstance(evaluation, Mapping)
        and isinstance(evaluation.get("label_matches"), list)
        and all(
            any(
                isinstance(match, Mapping)
                and match.get("candidate_id") == case.get("candidate_id")
                and match.get("label_id") == case.get("annotation_label_id")
                and match.get("disposition") == "candidate"
                and any(
                    label.get("label_id") == case.get("annotation_label_id")
                    and label.get("symbol_kinds") == [expected_cases[name][4]]
                    for page in symbol_manifest.get("pages", [])
                    if isinstance(page, Mapping)
                    for label in page.get("labels", [])
                    if isinstance(label, Mapping)
                )
                for match in evaluation["label_matches"]
            )
            for name, case in typed_cases.items()
        )
    )
    evaluation_counts = (
        evaluation.get("counts") if isinstance(evaluation, Mapping) else None
    )
    if (
        set(report) != expected_report_fields
        or report.get("schema_version") != "symbol-recognition-live-report/2"
        or report.get("selector") != SYMBOL_RECOGNITION_SELECTOR
        or report.get("run_id") != run.get("run_id")
        or report.get("order") != 1
        or report.get("project_id") != evidence.get("project_id")
        or report.get("automatic_result_id")
        != evidence.get("automatic_result_id")
        or report.get("source_sha256") != evidence.get("source_sha256")
        or report.get("manifest_sha256") != manifest_sha256
        or report.get("annotation_verdict_sha256") != verdict_sha256
        or report.get("visual_calls_by_page") != visual_calls
        or report.get("total_vision_calls_by_page") != total_calls
        or report.get("source_command_count") != 0
        or report.get("failures") != []
        or report.get("passed") is not True
        or not typed_cases_valid
        or not provider_identities_valid
        or not case_bindings_valid
        or not isinstance(evaluation, Mapping)
        or evaluation.get("schema_version") != "symbol-eval-report/1"
        or evaluation.get("passed") is not True
        or evaluation.get("failures") != []
        or not isinstance(evaluation_counts, Mapping)
        or evaluation_counts.get("candidate_match_count")
        != evidence.get("candidate_match_count")
        or evaluation_counts.get("reference_match_count")
        != evidence.get("reference_match_count")
        or evaluation_counts.get("non_inspection_match_count")
        != evidence.get("non_inspection_match_count")
        or evaluation_counts.get("negative_false_positive_count")
        != 0
    ):
        raise ValueError("symbol recognition report is stale or incomplete")


def validate_live_evidence(
    root: Path,
    run: Mapping[str, Any],
    manifest: Mapping[str, Any],
    human: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    schema_validator: SchemaValidator,
    run_dir: Path | None = None,
    design_path: Path | None = None,
) -> None:
    """Reject current-four evidence that is incomplete, spliced, or stale."""
    evidence_dir = (
        run_dir
        if run_dir is not None
        else root / ".agent/harness/runs" / str(run["run_id"])
    )
    if evidence_dir.name != run.get("run_id"):
        raise ValueError("live evidence directory is not run-bound")
    for document, schema_name in (
        (run, "run.schema.json"),
        (manifest, "current-four-manifest.schema.json"),
        (human, "human-verdict.schema.json"),
        (live, "live-run-evidence.schema.json"),
    ):
        schema_validator(document, schema_name, root)
    if (
        human.get("run_id") != run.get("run_id")
        or live.get("run_id") != run.get("run_id")
        or live.get("input_set") != "current-four"
        or live.get("phases") != list(LIVE_PHASES)
        or live.get("child_run_ids") != []
    ):
        raise ValueError("current-four live evidence identity is inconsistent")

    validate_paid_cycle_evidence(
        run,
        live,
        evidence_dir=evidence_dir,
        root=root,
    )

    entries = manifest.get("entries")
    samples = live.get("samples")
    verdict_samples = human.get("samples")
    expected_orders = {1, 2, 3, 4}
    if (
        manifest.get("input_set") != "current-four"
        or not isinstance(entries, list)
        or len(entries) != 4
        or not isinstance(samples, list)
        or len(samples) != 4
        or not isinstance(verdict_samples, list)
        or len(verdict_samples) != 4
        or {entry.get("order") for entry in entries} != expected_orders
        or {sample.get("order") for sample in samples} != expected_orders
        or {sample.get("order") for sample in verdict_samples} != expected_orders
        or len({entry.get("sha256") for entry in entries}) != 4
        or len({sample.get("project_id") for sample in samples}) != 4
    ):
        raise ValueError("current-four must contain four unique frozen samples")
    first = entries[0]
    if manifest.get("first_checkpoint") != {
        key: first[key]
        for key in ("order", "basename", "sha256", "opaque_ref")
    }:
        raise ValueError("current-four first checkpoint is inconsistent")
    validate_symbol_recognition_evidence(
        root,
        run,
        manifest,
        live,
        schema_validator=schema_validator,
        run_dir=evidence_dir,
    )

    entry_by_order = {int(entry["order"]): entry for entry in entries}
    sample_by_order = {int(sample["order"]): sample for sample in samples}
    verdict_by_order = {
        int(sample["order"]): sample for sample in verdict_samples
    }
    live_identity = run.get("live_identity")
    operator_id = (
        live_identity.get("operator_id")
        if isinstance(live_identity, Mapping)
        else None
    )
    if not isinstance(operator_id, str) or not operator_id:
        raise ValueError("formal live operator identity is missing")
    canonical_routes: dict[int, str] = {}
    for order, sample in sample_by_order.items():
        project_id = sample.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            raise ValueError(f"sample {order} project identity is missing")
        canonical_route = canonical_project_url(project_id, operator_id)
        if sample.get("project_url") != canonical_route:
            raise ValueError(f"sample {order} project route is not identity-bound")
        canonical_routes[order] = canonical_route
    design = live.get("design_qa")
    if not isinstance(design, Mapping):
        raise ValueError("design QA evidence is missing")
    _validate_design_evidence(
        root,
        run,
        design,
        canonical_routes[1],
        run_dir=evidence_dir,
        design_path=design_path,
    )

    for order in sorted(expected_orders):
        _validate_formal_sample(
            root,
            run,
            entry_by_order[order],
            verdict_by_order[order],
            sample_by_order[order],
            run_dir=evidence_dir,
        )


def _canonical_document_hash(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("content_sha256", None)
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def account_readiness_projection(
    run: Mapping[str, Any],
    live: Mapping[str, Any],
    runtime_acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the only permitted public projection of a sealed acceptance fact."""
    fact_keys = {
        "schema_version",
        "cycle_id",
        "run_id",
        "project_id",
        "readiness_sha256",
        "submission_started_sha256",
        "settlement_sha256",
        "call_evidence_sha256",
        "model",
        "ledger_attempt_index",
        "accepted_at",
        "content_sha256",
    }
    if (
        set(runtime_acceptance) != fact_keys
        or runtime_acceptance.get("schema_version")
        != "provider-account-runtime-acceptance/1"
        or runtime_acceptance.get("content_sha256")
        != _canonical_document_hash(runtime_acceptance)
        or not isinstance(runtime_acceptance.get("project_id"), str)
        or not runtime_acceptance["project_id"]
        or not isinstance(runtime_acceptance.get("ledger_attempt_index"), int)
        or runtime_acceptance["ledger_attempt_index"] < 1
        or runtime_acceptance.get("model") != "qwen3-vl-plus-2025-12-19"
        or not isinstance(runtime_acceptance.get("accepted_at"), str)
        or not runtime_acceptance["accepted_at"]
        or any(
            not isinstance(runtime_acceptance.get(name), str)
            or re.fullmatch(r"[0-9a-f]{64}", runtime_acceptance[name]) is None
            for name in (
                "readiness_sha256",
                "submission_started_sha256",
                "settlement_sha256",
                "call_evidence_sha256",
            )
        )
    ):
        raise ValueError("runtime acceptance fact is invalid")
    authorization = run.get("cycle_authorization")
    paid = live.get("paid_cycle")
    if (
        run.get("schema_version") != "run/3"
        or live.get("schema_version") != "live-run-evidence/3"
        or not isinstance(authorization, Mapping)
        or not isinstance(paid, Mapping)
        or runtime_acceptance.get("run_id") != run.get("run_id")
        or runtime_acceptance.get("cycle_id") != authorization.get("cycle_id")
        or paid.get("cycle_id") != authorization.get("cycle_id")
    ):
        raise ValueError("runtime acceptance binding is invalid")
    readiness = authorization.get("readiness_evidence")
    live_readiness = paid.get("readiness_evidence")
    if (
        not isinstance(readiness, Mapping)
        or not isinstance(live_readiness, Mapping)
        or dict(live_readiness) != dict(readiness)
    ):
        raise ValueError("runtime acceptance readiness projection is invalid")
    if (
        readiness.get("schema_version") != "provider-account-readiness-evidence/1"
        or readiness.get("runtime_state") != "not_yet_accepted"
        or readiness.get("runtime_acceptance_sha256") is not None
        or readiness.get("binding_match") is not True
        or runtime_acceptance.get("readiness_sha256")
        != readiness.get("readiness_sha256")
    ):
        raise ValueError("runtime acceptance readiness binding is invalid")
    projected = json.loads(json.dumps(live))
    projected["paid_cycle"]["readiness_evidence"] = {
        **dict(readiness),
        "runtime_state": "runtime_accepted",
        "runtime_acceptance_sha256": runtime_acceptance["content_sha256"],
    }
    return projected


def _validate_v3_runtime_acceptance(
    run: Mapping[str, Any],
    live: Mapping[str, Any],
    evidence_dir: Path,
    *,
    require_accepted: bool,
) -> None:
    """Require the public v3 state to be the exact projection of one sealed fact."""
    authorization = run.get("cycle_authorization")
    paid = live.get("paid_cycle")
    if not isinstance(authorization, Mapping) or not isinstance(paid, Mapping):
        raise ValueError("runtime acceptance evidence is missing")
    readiness = authorization.get("readiness_evidence")
    live_readiness = paid.get("readiness_evidence")
    if not isinstance(readiness, Mapping) or not isinstance(live_readiness, Mapping):
        raise ValueError("runtime acceptance readiness projection is missing")
    fact_path = evidence_dir / "reports/provider-account-runtime-acceptance.json"
    accepted = live_readiness.get("runtime_state") == "runtime_accepted"
    terminal = paid.get("terminal")
    completed_terminal = (
        isinstance(terminal, Mapping) and terminal.get("status") == "completed"
    )
    acceptance_required = (
        require_accepted
        or run.get("execution_state") in {"visual_qa_pending", "completed"}
        or completed_terminal
    )
    if not accepted:
        if live_readiness != readiness or fact_path.exists():
            raise ValueError("runtime acceptance projection is inconsistent")
        if acceptance_required:
            raise ValueError("runtime acceptance fact is required")
        return
    if fact_path.is_symlink() or not fact_path.is_file():
        raise ValueError("runtime acceptance fact is missing")
    try:
        raw = fact_path.read_bytes()
        fact = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime acceptance fact is invalid") from exc
    if (
        not isinstance(fact, dict)
        or raw
        != (
            json.dumps(
                fact,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ):
        raise ValueError("runtime acceptance fact is non-canonical")
    initial = json.loads(json.dumps(live))
    initial["paid_cycle"]["readiness_evidence"] = dict(readiness)
    if account_readiness_projection(run, initial, fact) != live:
        raise ValueError("runtime acceptance projection is inconsistent")


def _official_pricing_sha256(root: Path) -> str:
    pricing = _load_json(
        root / "backend/app/providers/provider_pricing_gdt10d_v1.json"
    )
    digest = pricing.get("content_sha256")
    if (
        not isinstance(digest, str)
        or digest != _canonical_document_hash(pricing)
    ):
        raise ValueError("paid cycle pricing snapshot is invalid")
    return digest


def _paid_ledger_entries(
    *,
    run: Mapping[str, Any],
    paid: Mapping[str, Any],
    ledger: Mapping[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], ...]:
    report = _load_json(evidence_dir / "reports/provider-usage-ledger.json")
    expected_keys = {
        "schema_version",
        "run_id",
        "pricing_sha256",
        "cycle_id",
        "journal_ref",
        "committed_total_cny",
        "reservation_count",
        "reserved_only_count",
        "submission_started_count",
        "unsettled_started_count",
        "settled_count",
        "entries",
        "content_sha256",
    }
    entries = report.get("entries")
    maximum = _paid_cycle_maximum(run)
    if (
        set(report) != expected_keys
        or report.get("schema_version") != "provider-usage-evidence/1"
        or report.get("run_id") != run.get("run_id")
        or report.get("pricing_sha256") != paid.get("pricing_sha256")
        or report.get("cycle_id") != paid.get("cycle_id")
        or report.get("journal_ref") != paid.get("journal_ref")
        or report.get("content_sha256") != _canonical_document_hash(report)
        or report.get("content_sha256") != ledger.get("evidence_sha256")
        or not isinstance(entries, list)
        or any(not isinstance(entry, Mapping) for entry in entries)
    ):
        raise ValueError("paid cycle ledger evidence is inconsistent")
    typed_entries = tuple(dict(entry) for entry in entries)
    entry_keys = {
        "attempt_index",
        "provider",
        "operation",
        "project_id",
        "page_index",
        "subject_kind",
        "subject_id",
        "retry_index",
        "crop_expansion_count",
        "state",
        "reservation_cny",
        "charged_cny",
    }
    attempt_indices = [entry.get("attempt_index") for entry in typed_entries]
    if (
        len(typed_entries) != report.get("reservation_count")
        or attempt_indices != list(range(1, len(typed_entries) + 1))
        or any(set(entry) != entry_keys for entry in typed_entries)
    ):
        raise ValueError("paid cycle ledger attempt sequence is invalid")
    admitted_project_ids = {
        project.get("project_id")
        for project in paid.get("projects", [])
        if isinstance(project, Mapping)
    }
    page_counts: dict[tuple[str, str, int], int] = {}
    subject_retries: dict[tuple[str, str, str], list[int]] = {}
    charged_total = Decimal("0")
    states = []
    for entry in typed_entries:
        try:
            reservation = Decimal(str(entry.get("reservation_cny")))
            charged = Decimal(str(entry.get("charged_cny")))
        except InvalidOperation as exc:
            raise ValueError("paid cycle ledger amount is invalid") from exc
        provider = entry.get("provider")
        operation = entry.get("operation")
        project_id = entry.get("project_id")
        page_index = entry.get("page_index")
        retry_index = entry.get("retry_index")
        crop_expansion = entry.get("crop_expansion_count")
        state = entry.get("state")
        if (
            not reservation.is_finite()
            or not charged.is_finite()
            or reservation < 0
            or charged < 0
            or charged > reservation
            or reservation.as_tuple().exponent < -6
            or charged.as_tuple().exponent < -6
            or project_id not in admitted_project_ids
            or provider not in {"qwen-vl", "tencent-ocr"}
            or not isinstance(page_index, int)
            or isinstance(page_index, bool)
            or page_index < 0
            or retry_index not in {0, 1}
            or crop_expansion not in {0, 1}
            or state
            not in {
                "reserved_only",
                "submission_started_unknown",
                "settled_verified",
                "reserved_unknown",
            }
        ):
            raise ValueError("paid cycle ledger entry is invalid")
        if (
            (provider == "qwen-vl" and operation not in {"review_symbols", "review_candidate"})
            or (
                provider == "tencent-ocr"
                and (operation != "GeneralAccurateOCR" or retry_index != 0)
            )
        ):
            raise ValueError("paid cycle ledger provider operation is invalid")
        page_key = (str(project_id), str(provider), page_index)
        page_counts[page_key] = page_counts.get(page_key, 0) + 1
        if page_counts[page_key] > 16:
            raise ValueError("paid cycle ledger page budget is invalid")
        if provider == "qwen-vl":
            subject_key = (
                str(project_id),
                str(entry.get("subject_kind")),
                str(entry.get("subject_id")),
            )
            subject_retries.setdefault(subject_key, []).append(retry_index)
            if subject_retries[subject_key] != list(
                range(len(subject_retries[subject_key]))
            ) or len(subject_retries[subject_key]) > 2:
                raise ValueError("paid cycle ledger subject budget is invalid")
        charged_total += charged
        states.append(state)
    try:
        committed = Decimal(str(report.get("committed_total_cny")))
    except InvalidOperation as exc:
        raise ValueError("paid cycle ledger total is invalid") from exc
    if (
        not committed.is_finite()
        or committed != charged_total
        or committed > maximum
        or report.get("reserved_only_count") != states.count("reserved_only")
        or report.get("submission_started_count")
        != len(states) - states.count("reserved_only")
        or report.get("unsettled_started_count")
        != states.count("submission_started_unknown")
        or report.get("settled_count")
        != states.count("settled_verified") + states.count("reserved_unknown")
        or any(report.get(key) != ledger.get(key) for key in (
            "committed_total_cny",
            "reservation_count",
            "reserved_only_count",
            "submission_started_count",
            "settled_count",
        ))
    ):
        raise ValueError("paid cycle ledger aggregate is invalid")
    return typed_entries


def _paid_cycle_maximum(run: Mapping[str, Any]) -> Decimal:
    """Use the immutable authorization ceiling for GDT-10E and v2's fixed cap."""
    if run.get("schema_version") != "run/3":
        return Decimal("50.000000")
    authorization = run.get("cycle_authorization")
    if (
        not isinstance(authorization, Mapping)
        or authorization.get("max_total_cny") != "46.473344"
    ):
        raise ValueError("paid cycle authorization ceiling is inconsistent")
    return Decimal("46.473344")


def _validate_paid_routing_reports(
    *,
    run: Mapping[str, Any],
    paid: Mapping[str, Any],
    entries: tuple[dict[str, Any], ...],
    evidence_dir: Path,
    require_success: bool,
) -> None:
    for project in paid.get("projects", []):
        if not isinstance(project, Mapping):
            raise ValueError("paid cycle project admission is invalid")
        if project.get("admission_sha256") is None:
            continue
        order = project.get("project_order")
        project_id = project.get("project_id")
        routing = _load_json(
            evidence_dir / f"reports/provider-routing-{order}.json"
        )
        expected_keys = {
            "schema_version",
            "run_id",
            "order",
            "project_id",
            "total_decisions",
            "escalated_group_ids",
            "denied_group_ids",
            "admitted_group_ids",
            "provider_cycle_reservation_denied_group_ids",
            "cancelled_group_ids",
            "terminal_group_ids",
            "paid_artifact_group_ids",
            "attempt_event_codes",
            "submission_started_group_ids",
            "never_submission_started_group_ids",
            "reserved_only_group_ids",
            "content_sha256",
        }
        group_fields = (
            "escalated_group_ids",
            "denied_group_ids",
            "admitted_group_ids",
            "provider_cycle_reservation_denied_group_ids",
            "cancelled_group_ids",
            "terminal_group_ids",
            "paid_artifact_group_ids",
            "submission_started_group_ids",
            "never_submission_started_group_ids",
            "reserved_only_group_ids",
        )
        if (
            set(routing) != expected_keys
            or routing.get("schema_version") != "provider-routing-aggregate/1"
            or routing.get("run_id") != run.get("run_id")
            or routing.get("order") != order
            or routing.get("project_id") != project_id
            or routing.get("content_sha256") != _canonical_document_hash(routing)
            or any(
                not isinstance(routing.get(field), list)
                or len(routing[field]) != len(set(routing[field]))
                for field in group_fields
            )
        ):
            raise ValueError("paid cycle routing evidence is invalid")
        escalated = set(routing["escalated_group_ids"])
        denied = set(routing["denied_group_ids"])
        admitted = set(routing["admitted_group_ids"])
        provider_reservation_denied = set(
            routing["provider_cycle_reservation_denied_group_ids"]
        )
        cancelled = set(routing["cancelled_group_ids"])
        terminal = set(routing["terminal_group_ids"])
        started = set(routing["submission_started_group_ids"])
        never_started = set(routing["never_submission_started_group_ids"])
        reserved_only = set(routing["reserved_only_group_ids"])
        paid_artifacts = set(routing["paid_artifact_group_ids"])
        ledger_started = {
            entry["subject_id"]
            for entry in entries
            if entry["project_id"] == project_id
            and entry["subject_kind"] == "escalation_group"
            and entry["state"] != "reserved_only"
        }
        ledger_reserved_only = {
            entry["subject_id"]
            for entry in entries
            if entry["project_id"] == project_id
            and entry["subject_kind"] == "escalation_group"
            and entry["state"] == "reserved_only"
        }
        storage = _load_json(
            evidence_dir / f"reports/provider-storage-{order}.json"
        )
        storage_artifacts = storage.get("artifacts")
        if (
            not isinstance(storage, Mapping)
            or set(storage)
            != {
                "schema_version",
                "run_id",
                "order",
                "project_id",
                "artifacts",
                "content_sha256",
            }
            or storage.get("schema_version")
            != "provider-storage-inventory/1"
            or storage.get("run_id") != run.get("run_id")
            or storage.get("order") != order
            or storage.get("project_id") != project_id
            or storage.get("content_sha256")
            != _canonical_document_hash(storage)
            or not isinstance(storage_artifacts, list)
            or any(
                not isinstance(artifact, Mapping)
                or set(artifact) != {"ref", "sha256", "size"}
                or not isinstance(artifact.get("ref"), str)
                or not artifact["ref"].startswith(
                    f"asset://projects/{project_id}/provider-"
                )
                or re.fullmatch(
                    r"[0-9a-f]{64}", str(artifact.get("sha256"))
                )
                is None
                or not isinstance(artifact.get("size"), int)
                or isinstance(artifact.get("size"), bool)
                or artifact["size"] < 0
                for artifact in storage_artifacts
            )
        ):
            raise ValueError("paid cycle storage inventory is invalid")
        symbol_crop_count = sum(
            "/provider-inputs/qwen-symbol/" in artifact["ref"]
            and artifact["ref"].endswith(".png")
            for artifact in storage_artifacts
        )
        if (
            escalated != denied | admitted
            or denied & admitted
            or not provider_reservation_denied <= admitted
            or admitted != started | never_started
            or started & never_started
            or not cancelled <= never_started
            or terminal != escalated
            or started != ledger_started
            or reserved_only != ledger_reserved_only
            or (require_success and reserved_only)
            or never_started
            & (paid_artifacts | ledger_started | ledger_reserved_only)
            or symbol_crop_count != len(started)
        ):
            raise ValueError("paid cycle routing terminal reconciliation failed")
        if require_success and provider_reservation_denied:
            raise ValueError(
                "paid cycle provider reservation rejection blocks formal success"
            )
        if order == 1 and (
            routing.get("total_decisions") != 199
            or len(escalated) != 198
            or len(denied) != 190
            or len(admitted) != 8
        ):
            raise ValueError("paid cycle sample-1 routing identity changed")


def _validate_paid_close_bridge(
    *,
    run: Mapping[str, Any],
    terminal: Mapping[str, Any],
    evidence_dir: Path,
) -> None:
    bridge = _load_json(
        evidence_dir / "reports/provider-cycle-close-bridge.json"
    )
    authorization = run.get("cycle_authorization")
    expected_keys = {
        "schema_version",
        "run_id",
        "image_id",
        "storage_volume",
        "network",
        "container_user",
        "authorization_owner_uid",
        "authorization_owner_gid",
        "mounts",
        "terminal_sha256",
        "content_sha256",
    }
    if (
        set(bridge) != expected_keys
        or bridge.get("schema_version") != "provider-cycle-close-bridge/1"
        or bridge.get("run_id") != run.get("run_id")
        or not isinstance(bridge.get("image_id"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", bridge["image_id"])
        is None
        or not isinstance(authorization, Mapping)
        or bridge.get("image_id") != authorization.get("backend_image_id")
        or not isinstance(bridge.get("storage_volume"), str)
        or not bridge["storage_volume"].endswith("_storage_qa_dev")
        or bridge.get("network") != "none"
        or bridge.get("container_user") != "0:0"
        or not isinstance(bridge.get("authorization_owner_uid"), int)
        or not isinstance(bridge.get("authorization_owner_gid"), int)
        or bridge.get("mounts")
        != [
            {"type": "volume", "target": "/data", "mode": "rw"},
            {"type": "bind", "target": "/auth", "mode": "rw"},
        ]
        or bridge.get("terminal_sha256") != terminal.get("terminal_sha256")
        or bridge.get("content_sha256")
        != terminal.get("bridge_evidence_sha256")
        or bridge.get("content_sha256") != _canonical_document_hash(bridge)
    ):
        raise ValueError("paid cycle close bridge evidence is inconsistent")


def validate_paid_cycle_evidence(
    run: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    require_success: bool = True,
    evidence_dir: Path | None = None,
    root: Path | None = None,
) -> None:
    """Validate immutable authorization, admission, cost, and terminal bindings."""
    is_v3 = run.get("schema_version") == "run/3"
    if not is_v3 and run.get("schema_version") != "run/2":
        return
    authorization = run.get("cycle_authorization")
    paid = live.get("paid_cycle")
    if not isinstance(authorization, Mapping) or not isinstance(paid, Mapping):
        raise ValueError("paid cycle evidence is missing")
    actual_root = root or Path(__file__).resolve().parents[3]
    actual_evidence_dir = evidence_dir or (
        actual_root / ".agent/harness/runs" / str(run.get("run_id"))
    )
    if paid.get("pricing_sha256") != _official_pricing_sha256(actual_root):
        raise ValueError("paid cycle pricing snapshot identity is inconsistent")
    for key in (
        "cycle_id",
        "pricing_sha256",
        "issuance_sha256",
        "consumption_sha256",
        "run_authorization_sha256",
    ):
        if paid.get(key) != authorization.get(key):
            raise ValueError("paid cycle authorization binding is inconsistent")
    if authorization.get("run_id") != run.get("run_id"):
        raise ValueError("paid cycle literal run binding is inconsistent")
    expected_journal = (
        f"asset://provider-usage-cycles/{authorization.get('cycle_id')}/"
    )
    if paid.get("journal_ref") != expected_journal:
        raise ValueError("paid cycle ledger identity is inconsistent")
    projects = paid.get("projects")
    if not isinstance(projects, list):
        raise ValueError("paid cycle project admissions are missing")
    orders = [project.get("project_order") for project in projects if isinstance(project, Mapping)]
    project_ids = [project.get("project_id") for project in projects if isinstance(project, Mapping)]
    admitted_projects = [
        project
        for project in projects
        if isinstance(project, Mapping)
        and isinstance(project.get("admission_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", project["admission_sha256"])
        is not None
    ]
    pending_projects = [
        project
        for project in projects
        if isinstance(project, Mapping)
        and project.get("admission_sha256") is None
    ]
    if (
        len(orders) != len(projects)
        or len(set(orders)) != len(orders)
        or len(set(project_ids)) != len(project_ids)
        or len(admitted_projects) + len(pending_projects) != len(projects)
        or (require_success and pending_projects)
    ):
        raise ValueError("paid cycle project admissions are duplicated")
    samples = live.get("samples")
    if isinstance(samples, list) and len(samples) == 4:
        admitted = {
            (project.get("project_order"), project.get("project_id"))
            for project in admitted_projects
            if isinstance(project, Mapping)
        }
        observed = {
            (sample.get("order"), sample.get("project_id"))
            for sample in samples
            if isinstance(sample, Mapping)
        }
        if admitted != observed:
            raise ValueError("paid cycle project admissions do not match samples")
    ledger = paid.get("ledger")
    terminal = paid.get("terminal")
    if not isinstance(terminal, Mapping):
        raise ValueError("paid cycle terminal evidence is missing")
    _validate_paid_close_bridge(
        run=run,
        terminal=terminal,
        evidence_dir=actual_evidence_dir,
    )
    if not admitted_projects:
        if require_success or ledger is not None:
            raise ValueError("paid cycle ledger evidence is inconsistent")
        if is_v3:
            _validate_v3_runtime_acceptance(
                run, live, actual_evidence_dir, require_accepted=require_success
            )
        return
    if not isinstance(ledger, Mapping):
        raise ValueError("paid cycle ledger evidence is missing")
    try:
        committed = Decimal(str(ledger.get("committed_total_cny")))
    except InvalidOperation as exc:
        raise ValueError("paid cycle cost aggregate is invalid") from exc
    maximum = _paid_cycle_maximum(run)
    if (
        not committed.is_finite()
        or committed < 0
        or committed > maximum
        or terminal.get("status") not in {"completed", "failed", "aborted"}
    ):
        raise ValueError("paid cycle terminal aggregate is invalid")
    if require_success and (
        ledger.get("reserved_only_count") != 0
        or paid.get("resume_consumed_sha256") is None
        or terminal.get("status") != "completed"
    ):
        raise ValueError("paid cycle terminal aggregate blocks formal success")
    entries = _paid_ledger_entries(
        run=run,
        paid=paid,
        ledger=ledger,
        evidence_dir=actual_evidence_dir,
    )
    _validate_paid_routing_reports(
        run=run,
        paid=paid,
        entries=entries,
        evidence_dir=actual_evidence_dir,
        require_success=require_success,
    )
    if require_success and terminal.get("status") != "completed":
        raise ValueError("paid cycle terminal aggregate blocks formal success")
    if is_v3:
        _validate_v3_runtime_acceptance(
            run, live, actual_evidence_dir, require_accepted=require_success
        )


def validate_final_p0_release(
    root: Path,
    run: Mapping[str, Any],
    result_by_id: Mapping[str, Mapping[str, Any]],
    policies: Mapping[str, Mapping[str, Any]],
    *,
    schema_validator: SchemaValidator,
) -> None:
    """Reject any full-P0 evidence set that cannot support a passed receipt."""
    required_count = int(policies["p0_acceptance_policy"]["required_contract_count"])
    pause_identity = {
        "code_identity": run.get("code_identity"),
        "config_identity": run.get("config_identity"),
        "contract_definition_hash": run.get("contract_definition_hash"),
        "input_identity": run.get("input_identity"),
        "live_identity": run.get("live_identity"),
    }
    if (
        run.get("mode") != "live"
        or run.get("scope") != "full-p0"
        or run.get("task_id") is not None
        or run.get("execution_state") != "completed"
        or run.get("failure_reason") is not None
        or run.get("completed_at") is None
        or run.get("pause_identity") != pause_identity
        or len(result_by_id) != required_count
        or any(
            result.get("result_state") != "passed" or result.get("exit_code") != 0
            for result in result_by_id.values()
        )
    ):
        raise ValueError("formal full-P0 lifecycle or result set is incomplete")
    proof = policies["failure_severity_policy"].get("failure_proof")
    proof_id = proof.get("contract_id") if isinstance(proof, Mapping) else None
    proof_result = result_by_id.get(str(proof_id))
    if (
        not isinstance(proof, Mapping)
        or not isinstance(proof_result, Mapping)
        or proof_result.get("result_state") != "passed"
        or proof_result.get("command") != proof.get("selector")
        or not {proof.get("report_ref"), proof.get("junit_ref")} <= set(
            proof_result.get("artifact_refs", [])
        )
    ):
        raise ValueError("P0-ACC-007 failure proof is not passed and bound")

    for result in result_by_id.values():
        for artifact_ref in result.get("artifact_refs", []):
            run_artifact_path(root, run, artifact_ref)

    run_dir = root / ".agent/harness/runs" / str(run["run_id"])
    manifest = _load_json(
        run_artifact_path(
            root,
            run,
            CURRENT_FOUR_ARTIFACT,
            run_dir=run_dir,
        )
    )
    human = _load_json(
        run_artifact_path(
            root,
            run,
            HUMAN_VERDICT_ARTIFACT,
            run_dir=run_dir,
        )
    )
    live = _load_json(
        run_artifact_path(
            root,
            run,
            LIVE_EVIDENCE_ARTIFACT,
            run_dir=run_dir,
        )
    )
    if (
        policies["p0_acceptance_policy"].get(
            "required_symbol_recognition_selector"
        )
        != SYMBOL_RECOGNITION_SELECTOR
        or (live.get("symbol_recognition") or {}).get("selector")
        != SYMBOL_RECOGNITION_SELECTOR
    ):
        raise ValueError("formal release is missing the controlled symbol selector")
    validate_live_evidence(
        root,
        run,
        manifest,
        human,
        live,
        schema_validator=schema_validator,
        run_dir=run_dir,
    )
