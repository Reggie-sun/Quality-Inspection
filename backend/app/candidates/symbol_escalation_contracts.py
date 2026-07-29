from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass

from app.candidates.local_symbol_resolution import LOCAL_SYMBOL_FAMILIES
from app.candidates.symbol_routing import (
    ESCALATION_REASON_CODES,
    SYMBOL_ROUTER_VERSION,
    SYMBOL_ROUTING_SCHEMA_VERSION,
)
from app.pdf.coordinates import BBox


MAX_VISUAL_PRIMARY_GROUPS_PER_PAGE = 4
MAX_VISUAL_PRIMARY_GROUPS_PER_PROJECT = 8
MAX_VISUAL_PAGE_WALL_SECONDS = 45.0
MAX_VISUAL_PROJECT_WALL_SECONDS = 90.0
MAX_VISUAL_IN_FLIGHT = 2
MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE = 16


@dataclass(frozen=True)
class EscalationBatch:
    content_sha256: str
    lineage_sha256: str
    budget_sha256: str
    member_content_sha256s: tuple[str, ...]
    page_index: int
    observation_ids: tuple[str, ...]
    observation_member_bindings: tuple[tuple[str, str], ...]
    geometry_sha256s: tuple[str, ...]
    associated_text_observation_ids: tuple[str, ...]
    escalation_reason_codes: tuple[str, ...]
    family_hypotheses: tuple[str, ...]
    bbox_pdf: BBox
    projected_wall_seconds: float


@dataclass(frozen=True)
class EscalationBudgetState:
    page_primary_counts: tuple[tuple[int, int], ...]
    project_primary_count: int
    page_actual_call_counts: tuple[tuple[int, int], ...]
    page_wall_seconds: tuple[tuple[int, float], ...]
    project_wall_seconds: float
    primary_group_identities: tuple[tuple[int, str], ...]
    retried_group_identities: tuple[tuple[int, str], ...]

    @property
    def project_retry_count(self) -> int:
        return len(self.retried_group_identities)


@dataclass(frozen=True)
class BudgetReservationOutcome:
    allowed: bool
    reserved_batches: tuple[EscalationBatch, ...]
    state: EscalationBudgetState
    reason_codes: tuple[str, ...]


def valid_bbox(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 4
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value
        )
        and value[2] > value[0]
        and value[3] > value[1]
    )


def _content_sha256(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def semantic_content_sha256(
    *,
    member_content_sha256s: tuple[str, ...] = (),
    page_index: int,
    bbox_pdf: BBox,
    geometry_sha256s: tuple[str, ...],
    associated_text_observation_ids: tuple[str, ...],
    escalation_reason_codes: tuple[str, ...],
    family_hypotheses: tuple[str, ...],
) -> str:
    payload: dict[str, object] = {
        "decision_evidence": {
            "schema_version": SYMBOL_ROUTING_SCHEMA_VERSION,
            "router_version": SYMBOL_ROUTER_VERSION,
            "disposition": "escalate",
            "requires_confirmation": True,
            "escalation_reason_codes": sorted(set(escalation_reason_codes)),
        },
        "geometry_sha256s": sorted(set(geometry_sha256s)),
        "page_index": page_index,
        "bbox_pdf": [float(value) for value in bbox_pdf],
        "associated_text_observation_ids": sorted(
            set(associated_text_observation_ids)
        ),
        "family_hypotheses": sorted(set(family_hypotheses)),
    }
    if member_content_sha256s:
        payload["member_content_sha256s"] = sorted(
            set(member_content_sha256s)
        )
    return _content_sha256(payload)


def batch_lineage_sha256(
    content_sha256: str,
    page_index: int,
    bindings: tuple[tuple[str, str], ...],
) -> str:
    return _content_sha256(
        {
            "content_sha256": content_sha256,
            "page_index": page_index,
            "observation_member_bindings": [
                list(binding) for binding in bindings
            ],
        }
    )


def batch_budget_sha256(
    content_sha256: str,
    page_index: int,
    projected_wall_seconds: float,
) -> str:
    return _content_sha256(
        {
            "content_sha256": content_sha256,
            "page_index": page_index,
            "projected_wall_seconds": float(
                projected_wall_seconds
            ).hex(),
        }
    )


def _valid_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_nonnegative_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
        and math.isfinite(float(value))
    )


def _valid_lower_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _canonical_string_tuple(
    value: object,
    *,
    allow_empty: bool = False,
) -> bool:
    if not isinstance(value, tuple) or (not allow_empty and not value):
        return False
    return all(
        isinstance(item, str) and bool(item) and item.strip() == item
        for item in value
    ) and value == tuple(sorted(set(value)))


def _valid_page_items(value: object, *, seconds: bool = False) -> bool:
    if not isinstance(value, tuple):
        return False
    valid_value = (
        _valid_nonnegative_number if seconds else _valid_nonnegative_int
    )
    return (
        all(
            isinstance(item, tuple)
            and len(item) == 2
            and _valid_nonnegative_int(item[0])
            and valid_value(item[1])
            for item in value
        )
        and value == tuple(sorted(value))
        and len({item[0] for item in value}) == len(value)
    )


def _valid_hash_pairs(value: object, *, observation_keys: bool) -> bool:
    if not isinstance(value, tuple):
        return False
    return (
        all(
            isinstance(item, tuple)
            and len(item) == 2
            and (
                (
                    isinstance(item[0], str)
                    and bool(item[0])
                    and item[0].strip() == item[0]
                )
                if observation_keys
                else _valid_nonnegative_int(item[0])
            )
            and _valid_lower_sha256(item[1])
            for item in value
        )
        and value == tuple(sorted(set(value)))
        and (
            not observation_keys
            or len({item[0] for item in value}) == len(value)
        )
    )


def _valid_family_reason_contract(
    family_hypotheses: tuple[str, ...],
    escalation_reason_codes: tuple[str, ...],
) -> bool:
    return bool(family_hypotheses) or escalation_reason_codes == (
        "unknown_symbol_pattern",
    )


def _validate_budget_state(state: object) -> EscalationBudgetState:
    if not isinstance(state, EscalationBudgetState):
        raise ValueError("escalation budget state invalid")
    if (
        not _valid_page_items(state.page_primary_counts)
        or not _valid_nonnegative_int(state.project_primary_count)
        or not _valid_page_items(state.page_actual_call_counts)
        or not _valid_page_items(state.page_wall_seconds, seconds=True)
        or not _valid_nonnegative_number(state.project_wall_seconds)
        or not _valid_hash_pairs(
            state.primary_group_identities, observation_keys=False
        )
        or not _valid_hash_pairs(
            state.retried_group_identities, observation_keys=False
        )
        or len(state.retried_group_identities) > 1
        or state.project_primary_count
        != sum(count for _, count in state.page_primary_counts)
        or not math.isclose(
            float(state.project_wall_seconds),
            sum(float(seconds) for _, seconds in state.page_wall_seconds),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or any(
            count > MAX_VISUAL_PRIMARY_GROUPS_PER_PAGE
            for _, count in state.page_primary_counts
        )
        or state.project_primary_count
        > MAX_VISUAL_PRIMARY_GROUPS_PER_PROJECT
        or any(
            seconds > MAX_VISUAL_PAGE_WALL_SECONDS
            for _, seconds in state.page_wall_seconds
        )
        or state.project_wall_seconds > MAX_VISUAL_PROJECT_WALL_SECONDS
    ):
        raise ValueError("escalation budget state invalid")
    identity_page_counts: dict[int, int] = {}
    for page, _ in state.primary_group_identities:
        identity_page_counts[page] = identity_page_counts.get(page, 0) + 1
    expected_actual_counts = identity_page_counts.copy()
    for page, identity in state.retried_group_identities:
        if (page, identity) not in state.primary_group_identities:
            raise ValueError("escalation budget state invalid")
        expected_actual_counts[page] = expected_actual_counts.get(page, 0) + 1
    if (
        tuple(sorted(identity_page_counts.items()))
        != state.page_primary_counts
        or tuple(sorted(expected_actual_counts.items()))
        != state.page_actual_call_counts
    ):
        raise ValueError("escalation budget state invalid")
    return state


def validate_budget_state(state: object) -> EscalationBudgetState:
    try:
        return _validate_budget_state(state)
    except Exception as exc:
        raise ValueError("escalation budget state invalid") from exc


def _validate_escalation_batch(batch: object) -> EscalationBatch:
    if not isinstance(batch, EscalationBatch):
        raise ValueError("escalation batch contract invalid")
    if (
        not _valid_lower_sha256(batch.content_sha256)
        or not _valid_lower_sha256(batch.lineage_sha256)
        or not _valid_lower_sha256(batch.budget_sha256)
        or not _canonical_string_tuple(batch.member_content_sha256s)
        or any(
            not _valid_lower_sha256(value)
            for value in batch.member_content_sha256s
        )
        or not _valid_nonnegative_int(batch.page_index)
        or not _canonical_string_tuple(batch.observation_ids)
        or not _valid_hash_pairs(
            batch.observation_member_bindings, observation_keys=True
        )
        or not _canonical_string_tuple(batch.geometry_sha256s)
        or any(
            not _valid_lower_sha256(value)
            for value in batch.geometry_sha256s
        )
        or not _canonical_string_tuple(
            batch.associated_text_observation_ids
        )
        or not _canonical_string_tuple(batch.escalation_reason_codes)
        or not set(batch.escalation_reason_codes).issubset(
            ESCALATION_REASON_CODES
        )
        or not _canonical_string_tuple(
            batch.family_hypotheses,
            allow_empty=True,
        )
        or not set(batch.family_hypotheses).issubset(
            LOCAL_SYMBOL_FAMILIES
        )
        or not _valid_family_reason_contract(
            batch.family_hypotheses,
            batch.escalation_reason_codes,
        )
        or not valid_bbox(batch.bbox_pdf)
        or not _valid_nonnegative_number(batch.projected_wall_seconds)
    ):
        raise ValueError("escalation batch contract invalid")
    expected_content_sha256 = semantic_content_sha256(
        member_content_sha256s=(
            ()
            if len(batch.member_content_sha256s) == 1
            else batch.member_content_sha256s
        ),
        page_index=batch.page_index,
        bbox_pdf=batch.bbox_pdf,
        geometry_sha256s=batch.geometry_sha256s,
        associated_text_observation_ids=(
            batch.associated_text_observation_ids
        ),
        escalation_reason_codes=batch.escalation_reason_codes,
        family_hypotheses=batch.family_hypotheses,
    )
    binding_ids = tuple(
        observation_id
        for observation_id, _ in batch.observation_member_bindings
    )
    binding_hashes = {
        member_hash
        for _, member_hash in batch.observation_member_bindings
    }
    if (
        batch.content_sha256 != expected_content_sha256
        or batch.observation_ids != binding_ids
        or binding_hashes != set(batch.member_content_sha256s)
        or (
            len(batch.member_content_sha256s) == 1
            and batch.member_content_sha256s[0]
            != batch.content_sha256
        )
        or batch.lineage_sha256
        != batch_lineage_sha256(
            batch.content_sha256,
            batch.page_index,
            batch.observation_member_bindings,
        )
        or batch.budget_sha256
        != batch_budget_sha256(
            batch.content_sha256,
            batch.page_index,
            batch.projected_wall_seconds,
        )
    ):
        raise ValueError("escalation batch contract invalid")
    return batch


def validate_escalation_batch(batch: object) -> EscalationBatch:
    try:
        return _validate_escalation_batch(batch)
    except Exception as exc:
        raise ValueError("escalation batch contract invalid") from exc


def _validate_actual_call_capacity(value: object) -> dict[int, int]:
    # PRT-3 must wire CandidateAdvisor to this budget Owner and retire its
    # legacy local 16/page constant when the executor integration lands.
    if not isinstance(value, Mapping):
        raise ValueError("actual call capacity contract invalid")
    items = tuple(value.items())
    snapshot = dict(items)
    if len(snapshot) != len(items) or any(
            not _valid_nonnegative_int(page)
            or not _valid_nonnegative_int(capacity)
            or capacity > MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE
            for page, capacity in snapshot.items()
    ):
        raise ValueError("actual call capacity contract invalid")
    return snapshot


def validate_actual_call_capacity(value: object) -> dict[int, int]:
    try:
        return _validate_actual_call_capacity(value)
    except Exception as exc:
        raise ValueError("actual call capacity contract invalid") from exc
