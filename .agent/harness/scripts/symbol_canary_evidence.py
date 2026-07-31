#!/usr/bin/env python3
"""Emit one sanitized, read-only production-routing canary ledger."""

from __future__ import annotations

import argparse
import json
import math
import re
import stat
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "symbol-routing-canary-evidence/1"
EXPECTED_MODE = "production_uncertainty"
EXPECTED_ROUTER = "symbol-uncertainty-router/1"
EXPECTED_MODEL = "qwen3-vl-plus-2025-12-19"
EXPECTED_PROMPT = "visual-symbol-prompt/4"
EXPECTED_RESPONSE_SCHEMA = "visual-symbol-review/2"
ISOLATED_DATABASE_HOST = "qi-prt8-canary-postgres"
CALL_RECORD_FIELDS = frozenset(
    {
        "provider",
        "request_id",
        "model",
        "prompt_version",
        "schema_version",
        "duration_ms",
        "retry_count",
        "input_image_count",
        "estimated_cost",
        "logical_task_reused",
        "request_ref",
        "response_ref",
    }
)
REASON_FIELDS = (
    "local_resolution_reason_codes",
    "escalation_reason_codes",
    "block_reason_codes",
)
RESOLVED_OBSERVATION_OUTCOMES = frozenset({"cache_resolved", "provider_resolved"})
TEST_REFS = (
    "backend/tests/unit/candidates/test_symbol_routing.py::"
    "test_concurrent_budget_window_denial_reserves_zero_members",
    "backend/tests/unit/candidates/test_advisor.py::"
    "test_concurrent_schema_failures_reserve_exactly_one_project_retry",
    "backend/tests/unit/candidates/test_advisor.py::"
    "test_actual_wall_budget_stops_queued_job_with_fake_clock",
    "backend/tests/unit/candidates/test_advisor.py::"
    "test_actual_primary_wall_blocks_retry_before_second_call",
)
FORBIDDEN_KEY_RE = re.compile(
    r"authorization|api[_-]?key|credential|password|secret|base64|raw",
    re.IGNORECASE,
)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid arguments\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _SafeArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--schema", required=True)
    return parser.parse_args(argv)


def validate_database_url(database_url: str) -> None:
    from sqlalchemy.engine import make_url

    try:
        parsed = make_url(database_url)
    except Exception:
        raise ValueError("database URL is not the isolated canary database") from None
    if (
        parsed.drivername != "postgresql+psycopg"
        or parsed.host != ISOLATED_DATABASE_HOST
        or parsed.port != 5432
        or parsed.database != "qi"
        or parsed.username != "qi"
        or bool(parsed.query)
    ):
        raise ValueError("database URL is not the isolated canary database")


def _mapping(value: object, *, kind: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{kind} is invalid")
    return value


def _sequence(value: object, *, kind: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{kind} is invalid")
    return value


def _text(value: object, *, kind: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{kind} is invalid")
    return value


def _integer(value: object, *, kind: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{kind} is invalid")
    return value


def _distribution(values: Counter[str]) -> list[dict[str, Any]]:
    return [{"code": code, "count": count} for code, count in sorted(values.items())]


def _safe_ref(value: object, *, kind: str) -> str:
    ref = _text(value, kind=kind)
    prefix = next(
        (
            candidate
            for candidate in ("asset://", "fixture://")
            if ref.startswith(candidate)
        ),
        None,
    )
    if prefix is None:
        raise ValueError(f"{kind} is invalid")
    relative = ref.removeprefix(prefix)
    path = PurePosixPath(relative)
    if (
        not relative
        or path.is_absolute()
        or "\\" in relative
        or any(
            part in {"", ".", ".."}
            or part != part.strip()
            or any(character.isspace() for character in part)
            for part in relative.split("/")
        )
    ):
        raise ValueError(f"{kind} is invalid")
    return ref


def _recognition_evidence_ref(value: object, *, project_id: str) -> str:
    ref = _text(value, kind="recognition evidence ref")
    if ref != f"symbol-routing-evidence://{project_id}":
        raise ValueError("recognition evidence ref is invalid")
    return ref


def _stable_json(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        before = path.lstat()
    except OSError:
        raise ValueError(f"{kind} is unavailable") from None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{kind} must be a real file")
    try:
        content = path.read_bytes()
        after = path.lstat()
        document = json.loads(content)
    except Exception:
        raise ValueError(f"{kind} is invalid JSON") from None
    if (
        after.st_ino != before.st_ino
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_size != before.st_size
        or len(content) != before.st_size
        or stat.S_ISLNK(after.st_mode)
        or not isinstance(document, dict)
    ):
        raise ValueError(f"{kind} changed while reading")
    return document


def _storage_path(
    storage_root: Path,
    relative: PurePosixPath,
    *,
    kind: str,
) -> Path:
    if storage_root.is_symlink():
        raise ValueError(f"{kind} contains a symlink")
    root = storage_root.resolve()
    current = storage_root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{kind} contains a symlink")
    resolved = current.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{kind} escapes storage root")
    return resolved


def _asset_path(
    storage_root: Path,
    resource_ref: object,
    *,
    kind: str,
) -> Path:
    ref = _safe_ref(resource_ref, kind=kind)
    if not ref.startswith("asset://"):
        raise ValueError(f"{kind} must use asset storage")
    relative = ref.removeprefix("asset://")
    return _storage_path(storage_root, PurePosixPath(relative), kind=kind)


def _validate_call_record(document: object) -> dict[str, Any]:
    record = dict(_mapping(document, kind="Provider call record"))
    if set(record) != CALL_RECORD_FIELDS or any(
        FORBIDDEN_KEY_RE.search(str(key)) for key in record
    ):
        raise ValueError("Provider call record does not match the redacted allowlist")
    for field in (
        "provider",
        "request_id",
        "model",
        "prompt_version",
        "schema_version",
    ):
        _text(record.get(field), kind=f"Provider call record {field}")
    if (
        record["provider"] != "qwen-vl"
        or record["model"] != EXPECTED_MODEL
        or record["prompt_version"] != EXPECTED_PROMPT
        or record["schema_version"] != EXPECTED_RESPONSE_SCHEMA
        or _integer(
            record.get("retry_count"),
            kind="Provider call record retry count",
        )
        not in {0, 1}
        or _integer(
            record.get("input_image_count"),
            kind="Provider call record input image count",
        )
        != 1
        or record.get("logical_task_reused") is not False
    ):
        raise ValueError("Provider call record identity is invalid")
    _integer(record.get("duration_ms"), kind="Provider call record duration")
    estimated_cost = record.get("estimated_cost")
    if estimated_cost is not None and (
        isinstance(estimated_cost, bool)
        or not isinstance(estimated_cost, (int, float))
        or not math.isfinite(float(estimated_cost))
        or estimated_cost < 0
    ):
        raise ValueError("Provider call record estimated cost is invalid")
    record["request_ref"] = _safe_ref(
        record.get("request_ref"),
        kind="Provider call request ref",
    )
    record["response_ref"] = _safe_ref(
        record.get("response_ref"),
        kind="Provider call response ref",
    )
    return record


def _load_call_records(
    storage_root: Path,
    project_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    by_request: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_ref: dict[str, dict[str, Any]] = {}
    root = storage_root.resolve()
    project_relative = PurePosixPath("projects") / project_id / "provider-calls"
    for family in ("qwen-symbol", "qwen-symbol-retries"):
        directory = _storage_path(
            storage_root,
            project_relative / family,
            kind="Provider call record directory",
        )
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Provider call record directory is invalid")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise ValueError("Provider call record path is invalid")
            document = _validate_call_record(
                _stable_json(path, kind="Provider call record")
            )
            ref = f"asset://{path.relative_to(root).as_posix()}"
            if ref in by_ref:
                raise ValueError("Provider call record ref is duplicated")
            by_ref[ref] = document
            by_request[document["request_id"]].append(document)
    return dict(by_request), by_ref


def _inventory_index(
    storage_root: Path,
    inventory_ref: object,
) -> dict[str, int]:
    inventory = _stable_json(
        _asset_path(
            storage_root,
            inventory_ref,
            kind="page inventory ref",
        ),
        kind="page inventory",
    )
    if inventory.get("schema_version") != "page-inventory/1":
        raise ValueError("page inventory schema is invalid")
    visual_pages: dict[str, int] = {}
    for raw_page in _sequence(inventory.get("pages"), kind="inventory pages"):
        page = _mapping(raw_page, kind="inventory page")
        page_index = _integer(
            page.get("page_index"),
            kind="inventory page index",
        )
        for raw_visual in _sequence(
            page.get("visual_observations", ()),
            kind="visual observations",
        ):
            visual = _mapping(raw_visual, kind="visual observation")
            observation_id = _text(
                visual.get("observation_id"),
                kind="visual observation id",
            )
            if (
                observation_id in visual_pages
                or _integer(
                    visual.get("page_index"),
                    kind="visual observation page",
                )
                != page_index
            ):
                raise ValueError("visual observation inventory is invalid")
            visual_pages[observation_id] = page_index
    if not visual_pages:
        raise ValueError("page inventory has no visual observations")
    return visual_pages


def _coverage_ids(
    automatic_result: Mapping[str, Any],
    visual_ids: set[str],
) -> tuple[str, ...]:
    coverage = _mapping(
        automatic_result.get("coverage"),
        kind="automatic result coverage",
    )
    identities = tuple(
        _text(
            _mapping(item, kind="coverage entry").get("observation_id"),
            kind="coverage observation id",
        )
        for item in _sequence(coverage.get("entries"), kind="coverage entries")
    )
    visual_coverage = tuple(
        identity for identity in identities if identity in visual_ids
    )
    if len(set(visual_coverage)) != len(visual_coverage):
        raise ValueError("coverage contains duplicate observations")
    return visual_coverage


def _decision_groups(
    decisions: Sequence[Any],
    visual_pages: Mapping[str, int],
) -> tuple[
    dict[str, list[Mapping[str, Any]]],
    Counter[str],
    Counter[str],
]:
    indexed: dict[str, Mapping[str, Any]] = {}
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    dispositions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for raw_decision in decisions:
        decision = _mapping(raw_decision, kind="routing decision")
        observation_id = _text(
            decision.get("visual_observation_id"),
            kind="routing observation id",
        )
        if observation_id in indexed or observation_id not in visual_pages:
            raise ValueError("routing decision coverage is invalid")
        indexed[observation_id] = decision
        disposition = _text(
            decision.get("disposition"),
            kind="routing disposition",
        )
        if disposition not in {"locally_resolved", "escalate", "block"}:
            raise ValueError("routing disposition is invalid")
        dispositions[disposition] += 1
        group_id = decision.get("escalation_group_id")
        member_index = decision.get("escalation_group_member_index")
        if disposition == "escalate":
            group = _text(group_id, kind="escalation group id")
            _integer(member_index, kind="escalation group member index")
            groups[group].append(decision)
        elif group_id is not None or member_index is not None:
            raise ValueError("non-escalated routing decision has a group")
        for field in REASON_FIELDS:
            for code in _sequence(
                decision.get(field),
                kind="routing reason codes",
            ):
                reasons[_text(code, kind="routing reason code")] += 1
    if set(indexed) != set(visual_pages):
        raise ValueError("routing decision coverage is incomplete")
    for group_id, members in groups.items():
        del group_id
        ordered = sorted(
            members,
            key=lambda item: int(item["escalation_group_member_index"]),
        )
        indexes = [int(item["escalation_group_member_index"]) for item in ordered]
        pages = {visual_pages[str(item["visual_observation_id"])] for item in ordered}
        if indexes != list(range(len(ordered))):
            raise ValueError("escalation group member indexes are invalid")
        if len(pages) != 1:
            raise ValueError("cross-page escalation group is invalid")
        members[:] = ordered
    return dict(groups), dispositions, reasons


def _cache_entries(
    rows: Sequence[Any],
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for raw_entry in rows:
        entry = _mapping(raw_entry, kind="cache entry")
        entry_id = _text(entry.get("id"), kind="cache entry id")
        if entry_id in indexed:
            raise ValueError("cache entry is duplicated")
        indexed[entry_id] = entry
    return indexed


def _attempt_bindings(
    attempts: Sequence[Any],
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
    visual_pages: Mapping[str, int],
    cache_entries: Mapping[str, Mapping[str, Any]],
    call_records_by_ref: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, tuple[str, int, int]],
    int,
    set[str],
    dict[str, str],
]:
    bindings: dict[str, tuple[str, int, int]] = {}
    cache_reuses = 0
    cache_producer_ids: set[str] = set()
    group_hashes: dict[str, str] = {}
    seen_events: set[tuple[str, int, str]] = set()
    seen_groups: set[str] = set()
    for raw_attempt in attempts:
        attempt = _mapping(raw_attempt, kind="attempt event")
        group_id = _text(
            attempt.get("escalation_group_id"),
            kind="attempt group id",
        )
        if group_id not in groups:
            raise ValueError("attempt event references an unknown group")
        seen_groups.add(group_id)
        attempt_index = _integer(
            attempt.get("attempt_index"),
            kind="attempt index",
        )
        if attempt_index not in {0, 1}:
            raise ValueError("attempt index exceeds the retry contract")
        event_code = _text(
            attempt.get("event_code"),
            kind="attempt event code",
        )
        event_key = (group_id, attempt_index, event_code)
        if event_key in seen_events:
            raise ValueError("attempt event is duplicated")
        seen_events.add(event_key)
        routing_hash = _text(
            attempt.get("routing_decision_sha256"),
            kind="attempt routing hash",
        )
        if group_id in group_hashes and group_hashes[group_id] != routing_hash:
            raise ValueError("attempt routing hash conflicts")
        group_hashes[group_id] = routing_hash
        request_id = attempt.get("provider_request_id")
        if event_code == "cache_hit_valid":
            if request_id is not None:
                raise ValueError("cache producer cannot be a current call")
            cache_entry_id = _text(
                attempt.get("cache_entry_id"),
                kind="cache entry id",
            )
            entry = cache_entries.get(cache_entry_id)
            if entry is None:
                raise ValueError("cache hit entry is missing")
            producer_request_id = _text(
                entry.get("producer_request_id"),
                kind="cache producer request id",
            )
            producer_ref = _safe_ref(
                entry.get("producer_call_record_ref"),
                kind="cache producer call record ref",
            )
            producer_record = call_records_by_ref.get(producer_ref)
            if (
                producer_record is None
                or producer_record.get("request_id") != producer_request_id
            ):
                raise ValueError("cache producer call record is invalid")
            cache_reuses += 1
            cache_producer_ids.add(producer_request_id)
        elif request_id is not None:
            current_id = _text(request_id, kind="current Provider request id")
            page_index = visual_pages[str(groups[group_id][0]["visual_observation_id"])]
            binding = (group_id, page_index, attempt_index)
            if current_id in bindings and bindings[current_id] != binding:
                raise ValueError("current Provider request binding conflicts")
            bindings[current_id] = binding
    if set(groups) != seen_groups:
        raise ValueError("escalation group attempt evidence is incomplete")
    if cache_producer_ids.intersection(bindings):
        raise ValueError("cache producer was counted as a current call")
    return bindings, cache_reuses, cache_producer_ids, group_hashes


def _outcome_evidence(
    outcomes: Sequence[Any],
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
    group_hashes: Mapping[str, str],
) -> tuple[Counter[str], Counter[str], int]:
    group_codes: Counter[str] = Counter()
    observation_codes: Counter[str] = Counter()
    seen_groups: set[str] = set()
    unresolved = 0
    for raw_outcome in outcomes:
        outcome = _mapping(raw_outcome, kind="escalation outcome")
        group_id = _text(
            outcome.get("escalation_group_id"),
            kind="outcome group id",
        )
        if group_id not in groups or group_id in seen_groups:
            raise ValueError("escalation outcome group is invalid")
        seen_groups.add(group_id)
        if outcome.get("terminal") is not True:
            raise ValueError("escalation outcome is not terminal")
        if _text(
            outcome.get("routing_decision_sha256"),
            kind="outcome routing hash",
        ) != group_hashes.get(group_id):
            raise ValueError("outcome routing hash conflicts")
        group_codes[_text(outcome.get("outcome_code"), kind="group outcome code")] += 1
        observed_ids: list[str] = []
        for raw_observation in _sequence(
            outcome.get("observation_outcomes"),
            kind="observation outcomes",
        ):
            observation = _mapping(
                raw_observation,
                kind="observation outcome",
            )
            observed_ids.append(
                _text(
                    observation.get("visual_observation_id"),
                    kind="outcome observation id",
                )
            )
            code = _text(
                observation.get("outcome_code"),
                kind="observation outcome code",
            )
            observation_codes[code] += 1
            unresolved += code not in RESOLVED_OBSERVATION_OUTCOMES
        expected_ids = [str(item["visual_observation_id"]) for item in groups[group_id]]
        if observed_ids != expected_ids:
            raise ValueError("outcome observation coverage is invalid")
    if seen_groups != set(groups):
        raise ValueError("escalation outcome evidence is incomplete")
    return group_codes, observation_codes, unresolved


def _current_calls(
    bindings: Mapping[str, tuple[str, int, int]],
    records_by_request: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for request_id, (_, page_index, attempt_index) in bindings.items():
        records = records_by_request.get(request_id, ())
        if len(records) != 1:
            raise ValueError("current call record count is not exactly one")
        record = dict(records[0])
        if record["retry_count"] != attempt_index:
            raise ValueError("current call record retry arithmetic conflicts")
        calls.append(
            {
                "page_index": page_index,
                "attempt_index": attempt_index,
                **record,
            }
        )
    return sorted(
        calls,
        key=lambda item: (
            item["page_index"],
            item["attempt_index"],
            item["request_id"],
        ),
    )


def _call_ledgers(
    visual_pages: Mapping[str, int],
    calls: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_page: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    visual_counts = Counter(visual_pages.values())
    for call in calls:
        by_page[int(call["page_index"])].append(call)
    ledgers: list[dict[str, Any]] = []
    for page_index in sorted(visual_counts):
        page_calls = by_page.get(page_index, [])
        primary = sum(call["attempt_index"] == 0 for call in page_calls)
        retry = sum(call["attempt_index"] > 0 for call in page_calls)
        duration_ms = sum(int(call["duration_ms"]) for call in page_calls)
        if primary > 4:
            raise ValueError("page primary call budget exceeded")
        if duration_ms > 45000:
            raise ValueError("page duration budget exceeded")
        ledgers.append(
            {
                "page_index": page_index,
                "visual_observations": visual_counts[page_index],
                "primary_calls": primary,
                "retry_calls": retry,
                "external_calls": len(page_calls),
                "duration_ms": duration_ms,
            }
        )
    project = {
        "primary_calls": sum(int(item["primary_calls"]) for item in ledgers),
        "retry_calls": sum(int(item["retry_calls"]) for item in ledgers),
        "external_calls": len(calls),
        "duration_ms": sum(int(item["duration_ms"]) for item in ledgers),
    }
    if project["primary_calls"] > 8:
        raise ValueError("project primary call budget exceeded")
    if project["retry_calls"] > 1:
        raise ValueError("project retry budget exceeded")
    if project["duration_ms"] > 90000:
        raise ValueError("project duration budget exceeded")
    if project["external_calls"] != project["primary_calls"] + project["retry_calls"]:
        raise ValueError("project call arithmetic conflicts")
    return ledgers, project


def build_canary_evidence(
    *,
    project_id: str,
    bundle: Mapping[str, Any],
    storage_root: Path,
) -> dict[str, Any]:
    try:
        canonical_project_id = str(uuid.UUID(project_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("project id is invalid") from None
    if canonical_project_id != project_id:
        raise ValueError("project id is not canonical")
    automatic_result = _mapping(
        bundle.get("automatic_result"),
        kind="automatic result",
    )
    if automatic_result.get("project_id") != project_id:
        raise ValueError("automatic result project identity conflicts")
    inventory_ref = _safe_ref(
        automatic_result.get("inventory_ref"),
        kind="inventory ref",
    )
    visual_pages = _inventory_index(storage_root, inventory_ref)
    if set(_coverage_ids(automatic_result, set(visual_pages))) != set(visual_pages):
        raise ValueError("coverage does not match visual inventory")
    groups, dispositions, reasons = _decision_groups(
        _sequence(bundle.get("decisions"), kind="routing decisions"),
        visual_pages,
    )
    records_by_request, records_by_ref = _load_call_records(
        storage_root,
        project_id,
    )
    cache_entries = _cache_entries(
        _sequence(bundle.get("cache_entries"), kind="cache entries")
    )
    bindings, cache_reuses, _, group_hashes = _attempt_bindings(
        _sequence(bundle.get("attempts"), kind="attempt events"),
        groups,
        visual_pages,
        cache_entries,
        records_by_ref,
    )
    group_outcomes, observation_outcomes, unresolved = _outcome_evidence(
        _sequence(bundle.get("outcomes"), kind="escalation outcomes"),
        groups,
        group_hashes,
    )
    calls = _current_calls(bindings, records_by_request)
    page_ledgers, project_ledger = _call_ledgers(visual_pages, calls)
    completeness = _text(
        automatic_result.get("completeness"),
        kind="automatic result completeness",
    )
    mode = _text(
        automatic_result.get("recognition_mode"),
        kind="recognition mode",
    )
    router = _text(
        automatic_result.get("router_version"),
        kind="recognition router",
    )
    if (
        completeness not in {"complete", "partial_review_required"}
        or mode != EXPECTED_MODE
        or router != EXPECTED_ROUTER
    ):
        raise ValueError("automatic result recognition identity is invalid")
    evidence_ref = _recognition_evidence_ref(
        automatic_result.get("recognition_evidence_ref"),
        project_id=project_id,
    )
    counts = {
        "admitted": len(visual_pages),
        "locally_resolved": dispositions["locally_resolved"],
        "escalated": dispositions["escalate"],
        "blocked": dispositions["block"],
        "deduped_groups": len(groups),
        "cache_reuses": cache_reuses,
        "primary_calls": project_ledger["primary_calls"],
        "retry_calls": project_ledger["retry_calls"],
        "external_calls": project_ledger["external_calls"],
        "unresolved": unresolved + dispositions["block"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "recognition_identity": {
            "mode": mode,
            "router_version": router,
            "completeness": completeness,
            "inventory_ref": inventory_ref,
            "recognition_evidence_ref": evidence_ref,
        },
        "counts": counts,
        "reason_distribution": _distribution(reasons),
        "group_outcome_distribution": _distribution(group_outcomes),
        "observation_outcome_distribution": _distribution(observation_outcomes),
        "page_ledgers": page_ledgers,
        "project_ledger": project_ledger,
        "call_records": calls,
        "latency_distribution": {
            "sample_count": 1,
            "durations_ms": [project_ledger["duration_ms"]],
            "p50_eligible": False,
            "p95_eligible": False,
        },
        "live_concurrency_observable": False,
        "carried_offline_evidence": {
            "in_flight_limit": 2,
            "test_refs": list(TEST_REFS),
        },
        "promotion_eligible": False,
    }


def _query_database(database_url: str, project_id: str) -> dict[str, Any]:
    from sqlalchemy import create_engine, text

    queries = {
        "automatic_result": """
            SELECT project_id::text AS project_id, inventory_ref, coverage,
                   completeness, recognition_mode, router_version,
                   recognition_evidence_ref
            FROM automatic_results
            WHERE project_id = CAST(:project_id AS uuid)
            ORDER BY created_at
        """,
        "decisions": """
            SELECT visual_observation_id, escalation_group_id,
                   escalation_group_member_index, disposition,
                   local_resolution_reason_codes, escalation_reason_codes,
                   block_reason_codes
            FROM symbol_routing_decisions
            WHERE project_id = CAST(:project_id AS uuid)
            ORDER BY visual_observation_id
        """,
        "attempts": """
            SELECT escalation_group_id, routing_decision_sha256,
                   attempt_index, event_code, cache_entry_id::text,
                   provider_request_id, event_sha256
            FROM symbol_escalation_attempt_events
            WHERE project_id = CAST(:project_id AS uuid)
            ORDER BY escalation_group_id, attempt_index, event_code
        """,
        "outcomes": """
            SELECT escalation_group_id, routing_decision_sha256,
                   outcome_code, observation_outcomes, terminal
            FROM symbol_escalation_outcomes
            WHERE project_id = CAST(:project_id AS uuid)
            ORDER BY escalation_group_id
        """,
        "cache_entries": """
            SELECT id::text, producer_request_id, producer_call_record_ref
            FROM visual_symbol_cache_entries
            WHERE project_id = CAST(:project_id AS uuid)
            ORDER BY id
        """,
    }
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            rows = {
                name: [
                    dict(item)
                    for item in connection.execute(
                        text(statement),
                        {"project_id": project_id},
                    ).mappings()
                ]
                for name, statement in queries.items()
            }
    finally:
        engine.dispose()
    automatic_rows = rows.pop("automatic_result")
    if len(automatic_rows) != 1:
        raise ValueError("canary project automatic result count is invalid")
    return {
        "automatic_result": automatic_rows[0],
        **rows,
    }


def _load_schema(path: Path) -> dict[str, Any]:
    return _stable_json(path, kind="canary evidence schema")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_database_url(args.database_url)
        project_id = str(uuid.UUID(args.project_id))
        if project_id != args.project_id or args.storage_root != "/data":
            raise ValueError("canary collector arguments are invalid")
        storage_root = Path(args.storage_root)
        if (
            not storage_root.is_absolute()
            or storage_root.is_symlink()
            or not storage_root.is_dir()
        ):
            raise ValueError("canary storage root is invalid")
        schema_path = Path(args.schema)
        if (
            not schema_path.is_absolute()
            or schema_path.name != "symbol-routing-canary-evidence.schema.json"
        ):
            raise ValueError("canary evidence schema path is invalid")
        evidence = build_canary_evidence(
            project_id=project_id,
            bundle=_query_database(args.database_url, project_id),
            storage_root=storage_root,
        )
        from jsonschema import Draft202012Validator, FormatChecker

        validator = Draft202012Validator(
            _load_schema(schema_path),
            format_checker=FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(evidence),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            raise ValueError("canary evidence failed closed-schema validation")
        sys.stdout.write(
            json.dumps(
                evidence,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 0
    except Exception:
        sys.stderr.write("symbol canary evidence rejected\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
