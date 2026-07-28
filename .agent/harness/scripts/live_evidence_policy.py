#!/usr/bin/env python3
"""Pure read-only validation for formal current-four live evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
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
        "evaluation",
        "failures",
        "passed",
    }
    evaluation = report.get("evaluation")
    if (
        set(report) != expected_report_fields
        or report.get("schema_version") != "symbol-recognition-live-report/1"
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
        or not isinstance(evaluation, Mapping)
        or evaluation.get("schema_version") != "symbol-eval-report/1"
        or evaluation.get("passed") is not True
        or evaluation.get("failures") != []
        or evaluation.get("counts", {}).get("candidate_match_count")
        != evidence.get("candidate_match_count")
        or evaluation.get("counts", {}).get("reference_match_count")
        != evidence.get("reference_match_count")
        or evaluation.get("counts", {}).get("non_inspection_match_count")
        != evidence.get("non_inspection_match_count")
        or evaluation.get("counts", {}).get("negative_false_positive_count")
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
