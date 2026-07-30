from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any, Callable

import pymupdf
from sqlalchemy.orm import Session

from app.candidates.confidence import (
    CandidateSourceSignal,
    normalize_visual_signal,
)
from app.candidates.duplicates import (
    DuplicateCandidate,
    DuplicateRelation,
    suggest_cross_view_duplicates,
)
from app.candidates.local_symbol_resolution import (
    prepare_local_family_hypotheses,
    resolve_visual_observation,
)
from app.candidates.parser import normalize_text, parse_annotation
from app.candidates.schemas import stable_candidate_id
from app.candidates.symbol_escalation_contracts import (
    MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE,
    MAX_VISUAL_IN_FLIGHT,
    MAX_VISUAL_PAGE_WALL_SECONDS,
    MAX_VISUAL_PRIMARY_GROUPS_PER_PAGE,
    MAX_VISUAL_PROJECT_WALL_SECONDS,
)
from app.candidates.symbol_escalation_planner import (
    EscalationRequest,
    plan_symbol_escalation_batches,
    reserve_escalation_budget_window,
)
from app.candidates.routing_evidence import (
    ESCALATION_ATTEMPT_SCHEMA_VERSION,
    ESCALATION_OUTCOME_SCHEMA_VERSION,
    EscalationAttemptEvent,
    EscalationOutcome,
    ObservationOutcome,
    RoutingEvidenceRepository,
    routing_decision_sha256,
    routing_decision_group_sha256,
)
from app.candidates.symbol_cache import (
    CACHE_IDENTITY_SCHEMA_VERSION,
    CROP_CANONICALIZATION_VERSION,
    CacheConsumer,
    InvalidCacheWinner,
    SymbolCacheIdentity,
    SymbolCacheProvenance,
    VisualSymbolCache,
    VisualSymbolCacheEntry,
    build_cache_entry,
)
from app.candidates.symbol_routing import (
    SYMBOL_ROUTER_VERSION,
    RoutingDecision,
    route_visual_observation,
    validate_routing_decision,
)
from app.candidates.symbol_review import (
    VISUAL_ADAPTER_VERSION,
    VISUAL_PROMPT_VERSION,
    VISUAL_SCHEMA_VERSION,
    ValidatedSymbolDetection,
    VisualReviewDecision,
    build_visual_cache_envelope,
    build_visual_failure_envelope,
    build_visual_request_evidence,
    canonical_visual_response_bytes,
    parse_visual_cache_envelope,
    parse_visual_request_evidence,
    parse_visual_symbol_json,
    plan_visual_batches,
    project_visual_page,
    validate_symbol_detections,
    visual_cache_identity,
    visual_cache_key,
    visual_review_prompt,
)
from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.pdf.coordinates import BBox
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import (
    PROPOSAL_RULE_VERSION,
    pack_visual_batches,
    reconstruct_visual_geometry_contexts,
)
from app.processing.automatic_result import CandidateSnapshot, selected_observations
from app.providers.base import VisionResult
from app.providers.call_records import (
    ProviderCallRecord,
    persist_call_record,
    serialize_call_record,
)
from app.providers.qwen_vl import (
    VisualSymbolProviderError,
    canonicalize_visual_png,
    parse_candidate_json,
    validate_visual_request_metadata,
)
from app.providers.runtime import VisionProviderFactory
from app.storage.local import LocalFileStorage


PROMPT_VERSION = "candidate-review-prompt/2"
SCHEMA_VERSION = "candidate-review/1"
ADAPTER_VERSION = "qwen-openai-compatible/1"
RENDER_SCALE = 2.0
PROJECTED_VISUAL_PRIMARY_WALL_SECONDS = (
    MAX_VISUAL_PAGE_WALL_SECONDS / MAX_VISUAL_PRIMARY_GROUPS_PER_PAGE
)
ALLOWED_SUGGESTION_TYPES = {
    "linear_dimension",
    "diameter_dimension",
    "thread",
    "radius",
    "angle",
    "general_requirement",
    "composite",
    "geometric_tolerance",
    "roughness",
    "weld",
}
_PARSEABLE_TYPES = {
    "linear_dimension",
    "diameter_dimension",
    "thread",
    "radius",
    "angle",
}
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9-]+$")
_CACHE_FIELDS = {
    "cache_schema_version",
    "provider",
    "request_id",
    "model",
    "prompt_version",
    "schema_version",
    "crop_sha256",
    "suggestion",
    "usage",
}


class CandidateAdvisorFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class RoutedObject:
    page_index: int
    source_ids: tuple[str, ...]
    raw_text: str
    expected_type: str | None
    review_reason: str
    bbox_pdf: BBox
    candidate_index: int | None
    candidate_id: str | None
    coverage_index: int
    requires_confirmation: bool


@dataclass(frozen=True)
class VisualExecutionIdentity:
    page_index: int
    content_sha256: str
    lineage_sha256: str
    budget_sha256: str
    observation_member_bindings: tuple[tuple[str, str], ...]
    crop_sha256: str
    member_content_sha256s: tuple[str, ...] = ()


@dataclass(frozen=True)
class VisualReviewOutcome:
    result: VisionResult
    provider: object | None
    provenance_request_ids: tuple[str, ...]
    current_attempt_request_ids: tuple[str, ...]
    current_attempt_count: int
    retry_count: int
    attempt_duration_ms: tuple[int, ...]
    measured_duration_ms: int
    cache_hit: bool
    execution_identity: VisualExecutionIdentity | None
    attempt_event_sha256s: tuple[str, ...] = ()
    terminal_replay: bool = False

    def __iter__(self) -> Iterator[object]:
        yield self.result
        yield self.provider
        yield self.provenance_request_ids


@dataclass(frozen=True)
class ProductionVisualJob:
    page_position: int
    page_index: int
    observation_ids: tuple[str, ...]
    crop_bbox_pdf: BBox
    crop_png: bytes
    visual_observations: tuple[VisualObservation, ...]
    execution_identity: VisualExecutionIdentity
    escalation_group_id: str
    routing_decision_sha256: str


@dataclass(frozen=True)
class VisualEvidenceContext:
    escalation_group_id: str
    routing_decision_sha256: str


class ProductionRetryCoordinator:
    def __init__(
        self,
        *,
        plan: Any,
        actual_call_capacity_by_page: dict[int, int],
        execution_identities: Sequence[VisualExecutionIdentity],
    ) -> None:
        self._state = plan.budget_state
        self._actual_call_capacity_by_page = dict(
            actual_call_capacity_by_page
        )
        self._batches = {
            (batch.page_index, batch.content_sha256): batch
            for batch in plan.batches
        }
        self._execution_identities = {
            (identity.page_index, identity.content_sha256): identity
            for identity in execution_identities
        }
        self._actual_page_seconds: dict[int, float] = defaultdict(float)
        self._actual_project_seconds = 0.0
        self._outstanding_projected_seconds: dict[
            tuple[int, str], float
        ] = {}
        self._primary_accounted: set[tuple[int, str]] = set()
        self._retry_outstanding: set[tuple[int, str]] = set()
        self._lock = Lock()

    @staticmethod
    def _key(
        identity: VisualExecutionIdentity,
    ) -> tuple[int, str]:
        return identity.page_index, identity.content_sha256

    def _batch_for_identity(
        self,
        identity: VisualExecutionIdentity | None,
    ) -> Any | None:
        if identity is None:
            return None
        key = self._key(identity)
        batch = self._batches.get(key)
        return (
            batch
            if batch is not None
            and identity == self._execution_identities.get(key)
            and batch.lineage_sha256 == identity.lineage_sha256
            and batch.budget_sha256 == identity.budget_sha256
            and batch.observation_member_bindings
            == identity.observation_member_bindings
            else None
        )

    def _wall_allows(
        self,
        *,
        page_index: int,
        projected_seconds: float,
    ) -> bool:
        page_outstanding = sum(
            seconds
            for (page, _), seconds in (
                self._outstanding_projected_seconds.items()
            )
            if page == page_index
        )
        project_outstanding = sum(
            self._outstanding_projected_seconds.values()
        )
        return (
            self._actual_page_seconds[page_index]
            + page_outstanding
            + projected_seconds
            <= MAX_VISUAL_PAGE_WALL_SECONDS
            and self._actual_project_seconds
            + project_outstanding
            + projected_seconds
            <= MAX_VISUAL_PROJECT_WALL_SECONDS
        )

    def start_primary(self, identity: VisualExecutionIdentity) -> bool:
        with self._lock:
            batch = self._batch_for_identity(identity)
            if batch is None:
                return False
            key = self._key(identity)
            if key in self._outstanding_projected_seconds:
                return False
            if not self._wall_allows(
                page_index=identity.page_index,
                projected_seconds=batch.projected_wall_seconds,
            ):
                return False
            self._outstanding_projected_seconds[key] = (
                batch.projected_wall_seconds
            )
            return True

    def _account_primary(
        self,
        identity: VisualExecutionIdentity,
        measured_duration_ms: int,
    ) -> None:
        key = self._key(identity)
        if key in self._primary_accounted:
            return
        self._outstanding_projected_seconds.pop(key, None)
        measured_seconds = measured_duration_ms / 1000.0
        self._actual_page_seconds[identity.page_index] += measured_seconds
        self._actual_project_seconds += measured_seconds
        self._primary_accounted.add(key)

    def authorize(
        self,
        identity: VisualExecutionIdentity | None,
        primary_duration_ms: int,
    ) -> bool:
        batch = self._batch_for_identity(identity)
        if identity is None or batch is None:
            return False
        with self._lock:
            self._account_primary(identity, primary_duration_ms)
            if not self._wall_allows(
                page_index=identity.page_index,
                projected_seconds=batch.projected_wall_seconds,
            ):
                return False
            reservation = reserve_escalation_budget_window(
                self._state,
                (batch,),
                actual_call_capacity_by_page=(
                    self._actual_call_capacity_by_page
                ),
                retry=True,
            )
            if not reservation.allowed:
                return False
            self._state = reservation.state
            key = self._key(identity)
            self._outstanding_projected_seconds[key] = (
                batch.projected_wall_seconds
            )
            self._retry_outstanding.add(key)
            return True

    def complete(self, outcome: VisualReviewOutcome) -> None:
        identity = outcome.execution_identity
        if identity is None:
            return
        with self._lock:
            key = self._key(identity)
            if outcome.retry_count:
                self._outstanding_projected_seconds.pop(key, None)
                retry_ms = outcome.attempt_duration_ms[-1]
                retry_seconds = retry_ms / 1000.0
                self._actual_page_seconds[
                    identity.page_index
                ] += retry_seconds
                self._actual_project_seconds += retry_seconds
                self._retry_outstanding.discard(key)
            else:
                self._account_primary(
                    identity,
                    outcome.measured_duration_ms,
                )


def _bbox_union(observations: Sequence[TextObservation]) -> BBox:
    return (
        min(observation.bbox_pdf[0] for observation in observations),
        min(observation.bbox_pdf[1] for observation in observations),
        max(observation.bbox_pdf[2] for observation in observations),
        max(observation.bbox_pdf[3] for observation in observations),
    )


def _review_prompt(route: RoutedObject) -> str:
    item_type_schema: dict[str, object] = (
        {"const": route.expected_type}
        if route.expected_type is not None
        else {"enum": sorted(ALLOWED_SUGGESTION_TYPES)}
    )
    confirmation_schema: dict[str, object] = (
        {"const": True}
        if route.requires_confirmation
        else {"type": "boolean"}
    )
    return json.dumps(
        {
            "task": "review_local_engineering_annotation",
            "raw_text": route.raw_text,
            "expected_type": route.expected_type,
            "review_reason": route.review_reason,
            "output_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version",
                    "raw_text",
                    "item_type",
                    "normalized_text",
                    "requires_confirmation",
                ],
                "properties": {
                    "schema_version": {"const": SCHEMA_VERSION},
                    "raw_text": {"const": route.raw_text},
                    "item_type": item_type_schema,
                    "normalized_text": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "requires_confirmation": confirmation_schema,
                },
            },
            "constraints": [
                "do_not_translate_raw_text",
                "do_not_guess_missing_context",
                "keep_or_raise_requires_confirmation",
                "return_frozen_schema_only",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _crop_rect(page: pymupdf.Page, bbox: BBox) -> tuple[pymupdf.Rect, float]:
    source = pymupdf.Rect(bbox)
    padding = min(24.0, max(6.0, source.height))
    crop = pymupdf.Rect(
        source.x0 - padding,
        source.y0 - padding,
        source.x1 + padding,
        source.y1 + padding,
    ) & page.rect
    if crop.is_empty or crop.get_area() <= 0:
        raise CandidateAdvisorFailure("Vision candidate crop is unavailable")
    return crop, padding


def _render_crop(page: pymupdf.Page, crop: pymupdf.Rect) -> bytes:
    rendered = crop * page.rotation_matrix
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE),
        clip=rendered,
        alpha=False,
    )
    if pixmap.width <= 0 or pixmap.height <= 0:
        raise CandidateAdvisorFailure("Vision candidate crop is unavailable")
    return pixmap.tobytes("png")


def _render_visual_crop(page: pymupdf.Page, bbox: BBox) -> bytes:
    crop = pymupdf.Rect(bbox)
    rendered = crop * page.rotation_matrix
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(300 / 72, 300 / 72),
        clip=rendered,
        alpha=False,
    )
    if pixmap.width <= 0 or pixmap.height <= 0:
        raise CandidateAdvisorFailure("Visual symbol crop is unavailable")
    return pixmap.tobytes("png")


def _candidate_reason(
    payload: dict[str, Any],
    observations: Sequence[TextObservation],
) -> tuple[str, str | None] | None:
    coarse_type = payload.get("coarse_type")
    if coarse_type in {"geometric_tolerance", "roughness", "weld"}:
        return "coarse_type", str(coarse_type)
    item_type = payload.get("item_type")
    if item_type == "composite":
        return "composite", "composite"
    if payload.get("requires_confirmation") is True:
        return "confirmation", str(item_type) if item_type is not None else None
    if any(observation.source_type == "ocr" for observation in observations):
        expected = coarse_type if coarse_type is not None else item_type
        return "ocr_source", str(expected) if expected is not None else None
    return None


def _route_objects(
    pages: Sequence[Any],
    snapshot: CandidateSnapshot,
    *,
    max_calls_by_page: dict[int, int] | None = None,
    excluded_source_ids: frozenset[str] = frozenset(),
    excluded_candidate_ids: frozenset[str] = frozenset(),
) -> tuple[RoutedObject, ...]:
    observations = {
        observation.observation_id: observation
        for observation in selected_observations(pages)
    }
    coverage_indexes = {
        entry.observation_id: index
        for index, entry in enumerate(snapshot.coverage_entries)
    }
    routes: list[RoutedObject] = []

    for candidate_index, candidate in enumerate(snapshot.candidates):
        payload = candidate.get("payload")
        source_ids = tuple(
            str(source_id)
            for source_id in candidate.get("source_location_ids", ())
            if str(source_id) in observations
        )
        members = tuple(observations[source_id] for source_id in source_ids)
        if not isinstance(payload, dict) or not members:
            continue
        reason = _candidate_reason(payload, members)
        if reason is None:
            continue
        review_reason, expected_type = reason
        routes.append(
            RoutedObject(
                page_index=members[0].page_index,
                source_ids=source_ids,
                raw_text=str(payload.get("raw_text", members[0].raw_text)),
                expected_type=expected_type,
                review_reason=review_reason,
                bbox_pdf=_bbox_union(members),
                candidate_index=candidate_index,
                candidate_id=str(candidate["candidate_id"]),
                coverage_index=coverage_indexes[source_ids[0]],
                requires_confirmation=bool(
                    payload.get("requires_confirmation", False)
                ),
            )
        )

    candidate_source_ids = {
        source_id
        for candidate in snapshot.candidates
        for source_id in candidate.get("source_location_ids", ())
    }
    for coverage_index, entry in enumerate(snapshot.coverage_entries):
        if (
            entry.disposition != "ambiguous"
            or entry.observation_id in candidate_source_ids
        ):
            continue
        observation = observations.get(entry.observation_id)
        if observation is None:
            continue
        routes.append(
            RoutedObject(
                page_index=observation.page_index,
                source_ids=(observation.observation_id,),
                raw_text=observation.raw_text,
                expected_type=None,
                review_reason="parser_failed",
                bbox_pdf=observation.bbox_pdf,
                candidate_index=None,
                candidate_id=None,
                coverage_index=coverage_index,
                requires_confirmation=True,
            )
        )

    routes = [
        route
        for route in routes
        if not set(route.source_ids).intersection(excluded_source_ids)
        and route.candidate_id not in excluded_candidate_ids
    ]
    routes.sort(
        key=lambda route: (
            route.page_index,
            route.bbox_pdf[1],
            route.bbox_pdf[0],
            route.source_ids,
        )
    )
    calls_per_page: dict[int, int] = defaultdict(int)
    bounded: list[RoutedObject] = []
    for route in routes:
        page_cap = (
            MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE
            if max_calls_by_page is None
            else max_calls_by_page.get(
                route.page_index,
                MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE,
            )
        )
        if calls_per_page[route.page_index] >= page_cap:
            continue
        calls_per_page[route.page_index] += 1
        bounded.append(route)
    return tuple(bounded)


def _rejection_code(
    route: RoutedObject,
    payload: dict[str, Any],
) -> str | None:
    if normalize_text(str(payload.get("raw_text", ""))) != normalize_text(
        route.raw_text
    ):
        return "raw_text_mismatch"
    if payload.get("item_type") not in ALLOWED_SUGGESTION_TYPES:
        return "unknown_type"
    if (
        route.expected_type is not None
        and payload.get("item_type") != route.expected_type
    ):
        return "type_mismatch"
    if (
        route.requires_confirmation
        and payload.get("requires_confirmation") is False
    ):
        return "confirmation_downgrade"
    return None


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _visual_retry_evidence_paths(
    project_id: str,
    cache_key: str,
) -> tuple[str, str, str]:
    filename = f"{cache_key}.attempt-1.json"
    return (
        f"projects/{project_id}/provider-calls/"
        f"qwen-symbol-retries/{filename}",
        f"projects/{project_id}/provider-requests/"
        f"qwen-symbol-retries/{filename}",
        f"projects/{project_id}/provider-responses/"
        f"qwen-symbol-retries/{filename}",
    )


def _cache_key(
    *,
    model: str,
    route: RoutedObject,
    crop_bbox_pdf: tuple[float, float, float, float],
    crop_sha256: str,
) -> str:
    document = {
        "provider_role": "advisor",
        "adapter_version": ADAPTER_VERSION,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "page_index": route.page_index,
        "crop_bbox_pdf": list(crop_bbox_pdf),
        "crop_sha256": crop_sha256,
    }
    return hashlib.sha256(_json_bytes(document)).hexdigest()


def _validated_suggestion(payload: dict[str, Any]) -> dict[str, Any]:
    return parse_candidate_json(_json_bytes(payload).decode("utf-8"))


def _duplicate_relations(
    candidates: Sequence[dict[str, Any]],
    observations: dict[str, TextObservation],
) -> tuple[DuplicateRelation, ...]:
    duplicate_inputs: list[DuplicateCandidate] = []
    for candidate in candidates:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            continue
        source_ids = [
            str(source_id)
            for source_id in candidate.get("source_location_ids", ())
        ]
        source = next(
            (
                observations[source_id]
                for source_id in source_ids
                if source_id in observations
            ),
            None,
        )
        if source is None:
            continue
        duplicate_inputs.append(
            DuplicateCandidate(
                candidate_id=str(candidate["candidate_id"]),
                normalized_text=str(
                    payload.get("normalized_text", payload.get("raw_text", ""))
                ),
                view_id=f"page:{source.page_index}",
                disposition="candidate",
            )
        )
    return tuple(suggest_cross_view_duplicates(duplicate_inputs))


class CandidateAdvisor:
    def __init__(
        self,
        settings: Settings,
        storage: LocalFileStorage,
        *,
        project_id: str,
        provider_factory: VisionProviderFactory,
        symbol_session_factory: Callable[[], Session] | None = None,
        require_symbol_persistence: bool = False,
    ) -> None:
        if _SAFE_PROJECT_ID.fullmatch(project_id) is None:
            raise ValueError("project_id must be one safe path segment")
        self._settings = settings
        self._storage = storage
        self._project_id = project_id
        self._provider_factory = provider_factory
        self._symbol_session_factory = symbol_session_factory
        self._require_symbol_persistence = require_symbol_persistence

    def _project_uuid(self) -> uuid.UUID:
        try:
            return uuid.UUID(self._project_id)
        except ValueError:
            raise CandidateAdvisorFailure(
                "Symbol routing persistence project identity is invalid"
            ) from None

    def _record_routing_decisions(
        self,
        *,
        decisions: Sequence[RoutingDecision],
        escalation_group_by_observation: dict[str, str],
        escalation_group_member_index_by_observation: dict[str, int],
    ) -> dict[str, str]:
        if self._symbol_session_factory is None:
            return {}
        session = self._symbol_session_factory()
        try:
            evidence = RoutingEvidenceRepository(session)
            hashes: dict[str, str] = {}
            for decision in decisions:
                record = evidence.record_decision(
                    project_id=self._project_uuid(),
                    decision=decision,
                    escalation_group_id=(
                        escalation_group_by_observation.get(
                            decision.visual_observation_id
                        )
                        if decision.disposition == "escalate"
                        else None
                    ),
                    escalation_group_member_index=(
                        escalation_group_member_index_by_observation.get(
                            decision.visual_observation_id
                        )
                        if decision.disposition == "escalate"
                        else None
                    ),
                    local_resolution_ref=(
                        f"sha256:{decision.input_sha256}"
                        if decision.disposition == "locally_resolved"
                        else None
                    ),
                )
                hashes[decision.visual_observation_id] = (
                    record.decision_sha256
                )
            session.commit()
            return hashes
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _production_cache_identity(
        *,
        execution_identity: VisualExecutionIdentity,
        visual_observations: Sequence[VisualObservation],
        text_observations: dict[str, TextObservation],
        model: str,
    ) -> SymbolCacheIdentity:
        associated_text_sha256 = hashlib.sha256(
            _json_bytes(
                [
                    {
                        "visual_observation_id": (
                            observation.observation_id
                        ),
                        "associated_text_allowlist": [
                            {
                                "observation_id": text.observation_id,
                                "observation_level": (
                                    text.observation_level
                                ),
                                "raw_text": text.raw_text,
                            }
                            for text in (
                                text_observations[text_id]
                                for text_id in (
                                    observation
                                    .associated_text_observation_ids
                                )
                            )
                        ],
                    }
                    for observation in visual_observations
                ]
            )
        ).hexdigest()
        local_evidence_sha256s = (
            execution_identity.member_content_sha256s
            or tuple(
                evidence_sha256
                for _, evidence_sha256 in (
                    execution_identity.observation_member_bindings
                )
            )
        )
        return SymbolCacheIdentity(
            schema_version=CACHE_IDENTITY_SCHEMA_VERSION,
            canonical_crop_sha256=execution_identity.crop_sha256,
            associated_text_sha256=associated_text_sha256,
            local_evidence_sha256s=local_evidence_sha256s,
            router_version=SYMBOL_ROUTER_VERSION,
            proposal_version=PROPOSAL_RULE_VERSION,
            prompt_version=VISUAL_PROMPT_VERSION,
            response_schema_version=VISUAL_SCHEMA_VERSION,
            adapter_version=VISUAL_ADAPTER_VERSION,
            model_identity=model,
            pymupdf_version=pymupdf.VersionBind,
            crop_canonicalization_version=(
                CROP_CANONICALIZATION_VERSION
            ),
        )

    def _production_cache_provenance_valid(
        self,
        entry: VisualSymbolCacheEntry,
    ) -> bool:
        provenance = entry.provenance
        if provenance is None:
            return False
        try:
            audit_path = self._storage.resolve_resource_ref(
                provenance.producer_call_record_ref
            )
            audit_content = audit_path.read_bytes()
            audit = json.loads(audit_content)
            if (
                not isinstance(audit, dict)
                or serialize_call_record(audit) != audit_content
                or audit.get("provider") != "qwen-vl"
                or audit.get("request_id")
                != provenance.producer_request_id
                or audit.get("model") != entry.identity.model_identity
                or audit.get("prompt_version")
                != entry.identity.prompt_version
                or audit.get("schema_version")
                != entry.identity.response_schema_version
            ):
                return False
            request_ref = audit.get("request_ref")
            response_ref = audit.get("response_ref")
            if not isinstance(request_ref, str) or not isinstance(
                response_ref, str
            ):
                return False
            request_path = self._storage.resolve_resource_ref(request_ref)
            request_content = request_path.read_bytes()
            request_payload = json.loads(request_content)
            if not isinstance(request_payload, dict):
                return False
            crop_ref = request_payload.get("crop_ref")
            usage = request_payload.get("usage")
            if not isinstance(crop_ref, str) or not isinstance(usage, dict):
                return False
            request_evidence = parse_visual_request_evidence(
                request_payload,
                expected_crop_ref=crop_ref,
                expected_crop_sha256=(
                    entry.identity.canonical_crop_sha256
                ),
                expected_usage=usage,
            )
            crop_path = self._storage.resolve_resource_ref(crop_ref)
            response_path = self._storage.resolve_resource_ref(response_ref)
            return (
                _json_bytes(request_evidence) == request_content
                and hashlib.sha256(crop_path.read_bytes()).hexdigest()
                == entry.identity.canonical_crop_sha256
                and response_path.read_bytes()
                == canonical_visual_response_bytes(entry.response)
                and hashlib.sha256(
                    canonical_visual_response_bytes(entry.response)
                ).hexdigest()
                == entry.response_sha256
            )
        except Exception:
            return False

    def _append_attempt_event(
        self,
        *,
        context: VisualEvidenceContext,
        attempt_index: int,
        event_code: str,
        cache_entry_id: uuid.UUID | None = None,
        provider_request_id: str | None = None,
    ) -> str:
        if self._symbol_session_factory is None:
            return ""
        session = self._symbol_session_factory()
        try:
            record = RoutingEvidenceRepository(session).append_attempt(
                project_id=self._project_uuid(),
                event=EscalationAttemptEvent(
                    schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION,
                    escalation_group_id=context.escalation_group_id,
                    routing_decision_sha256=(
                        context.routing_decision_sha256
                    ),
                    attempt_index=attempt_index,
                    event_code=event_code,
                    cache_entry_id=cache_entry_id,
                    provider_request_id=provider_request_id,
                ),
            )
            session.commit()
            return record.event_sha256
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _record_terminal_outcome(
        self,
        *,
        context: VisualEvidenceContext,
        outcome_code: str,
        observation_outcomes: tuple[ObservationOutcome, ...],
        attempt_event_sha256s: tuple[str, ...],
    ) -> None:
        if self._symbol_session_factory is None:
            return
        del attempt_event_sha256s
        session = self._symbol_session_factory()
        try:
            evidence = RoutingEvidenceRepository(session)
            canonical_attempt_sha256s = (
                evidence.canonical_attempt_sha256s(
                    project_id=self._project_uuid(),
                    escalation_group_id=context.escalation_group_id,
                    routing_decision_sha256=(
                        context.routing_decision_sha256
                    ),
                )
            )
            evidence.record_terminal_outcome(
                project_id=self._project_uuid(),
                outcome=EscalationOutcome(
                    schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
                    escalation_group_id=context.escalation_group_id,
                    routing_decision_sha256=(
                        context.routing_decision_sha256
                    ),
                    outcome_code=outcome_code,
                    observation_outcomes=observation_outcomes,
                    attempt_event_sha256s=canonical_attempt_sha256s,
                    terminal=True,
                ),
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _cache_result(
        self,
        relative_path: str,
        *,
        audit_relative_path: str,
        crop_sha256: str,
        model: str,
    ) -> VisionResult | None:
        cache_path = self._storage.root.joinpath(*relative_path.split("/"))
        if not cache_path.exists():
            return None
        try:
            self._storage.resolve_resource_ref(f"asset://{audit_relative_path}")
        except ValueError:
            raise CandidateAdvisorFailure(
                "Vision candidate Advisor cache audit record is missing"
            ) from None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != _CACHE_FIELDS:
                raise ValueError("cache fields")
            if (
                payload["cache_schema_version"] != "candidate-advisor-cache/1"
                or payload["provider"] != "qwen-vl"
                or payload["model"] != model
                or payload["prompt_version"] != PROMPT_VERSION
                or payload["schema_version"] != SCHEMA_VERSION
                or payload["crop_sha256"] != crop_sha256
                or not isinstance(payload["request_id"], str)
                or not payload["request_id"].strip()
                or not isinstance(payload["suggestion"], dict)
                or not isinstance(payload["usage"], dict)
            ):
                raise ValueError("cache values")
            suggestion = _validated_suggestion(payload["suggestion"])
            usage = {
                str(key): value
                for key, value in payload["usage"].items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            if len(usage) != len(payload["usage"]):
                raise ValueError("cache usage")
            return VisionResult(
                request_id=payload["request_id"],
                payload=suggestion,
                usage=usage,
            )
        except Exception:
            raise CandidateAdvisorFailure(
                "Vision candidate Advisor cache is invalid"
            ) from None

    def _visual_cache_result(
        self,
        relative_path: str,
        *,
        audit_relative_path: str,
        crop_relative_path: str,
        request_relative_path: str,
        identity: dict[str, object],
    ) -> tuple[VisionResult, tuple[str, ...]] | None:
        cache_candidate = self._storage.root.joinpath(
            *relative_path.split("/")
        )
        current = self._storage.root
        cache_path_has_symlink = False
        for part in relative_path.split("/"):
            current /= part
            if current.is_symlink():
                cache_path_has_symlink = True
                break
        if not cache_candidate.exists() and not cache_path_has_symlink:
            return None
        try:
            cache_path = self._storage.resolve_resource_ref(
                f"asset://{relative_path}"
            )
            audit_path = self._storage.resolve_resource_ref(
                f"asset://{audit_relative_path}"
            )
            request_path = self._storage.resolve_resource_ref(
                f"asset://{request_relative_path}"
            )
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            audit_content = audit_path.read_bytes()
            audit = json.loads(audit_content)
            request_content = request_path.read_bytes()
            request_payload = json.loads(request_content)
            if (
                not isinstance(payload, dict)
                or not isinstance(audit, dict)
                or not isinstance(request_payload, dict)
            ):
                raise ValueError("cache values")
            request_id, response, usage = parse_visual_cache_envelope(
                payload,
                expected_identity=identity,
            )
            request_id, usage = validate_visual_request_metadata(
                request_id,
                usage,
            )
            request_evidence = parse_visual_request_evidence(
                request_payload,
                expected_crop_ref=f"asset://{crop_relative_path}",
                expected_crop_sha256=str(identity["crop_sha256"]),
                expected_usage=usage,
            )
            if _json_bytes(request_evidence) != request_content:
                raise ValueError("request evidence")
            crop_path = self._storage.resolve_resource_ref(
                request_evidence["crop_ref"]
            )
            response_content = canonical_visual_response_bytes(response)
            response_sha256 = hashlib.sha256(response_content).hexdigest()
            response_relative_path = (
                f"projects/{self._project_id}/provider-responses/"
                f"qwen-symbol/{response_sha256}.json"
            )
            response_path = self._storage.resolve_resource_ref(
                f"asset://{response_relative_path}"
            )
            if serialize_call_record(audit) != audit_content:
                raise ValueError("cache audit")
            retry_count = audit.get("retry_count")
            if (
                not isinstance(retry_count, int)
                or isinstance(retry_count, bool)
                or retry_count not in (0, 1)
            ):
                raise ValueError("cache retry count")
            expected_audit = {
                "provider": "qwen-vl",
                "request_id": request_id,
                "model": identity["model"],
                "prompt_version": VISUAL_PROMPT_VERSION,
                "schema_version": VISUAL_SCHEMA_VERSION,
                "input_image_count": 1,
                "estimated_cost": None,
                "logical_task_reused": False,
                "request_ref": f"asset://{request_relative_path}",
                "response_ref": f"asset://{response_relative_path}",
            }
            if any(
                audit.get(key) != value
                for key, value in expected_audit.items()
            ) or hashlib.sha256(crop_path.read_bytes()).hexdigest() != identity.get(
                "crop_sha256"
            ) or response_path.read_bytes() != response_content:
                raise ValueError("cache audit")

            cache_key = Path(audit_relative_path).stem
            retry_paths = _visual_retry_evidence_paths(
                self._project_id,
                cache_key,
            )
            retry_request_ids: tuple[str, ...] = ()
            retry_candidates = tuple(
                self._storage.root.joinpath(*path.split("/"))
                for path in retry_paths
            )
            if retry_count == 0:
                if any(
                    path.exists() or path.is_symlink()
                    for path in retry_candidates
                ):
                    raise ValueError("unexpected retry evidence")
            else:
                retry_audit_path = self._storage.resolve_resource_ref(
                    f"asset://{retry_paths[0]}"
                )
                retry_request_path = self._storage.resolve_resource_ref(
                    f"asset://{retry_paths[1]}"
                )
                retry_response_path = self._storage.resolve_resource_ref(
                    f"asset://{retry_paths[2]}"
                )
                retry_audit_content = retry_audit_path.read_bytes()
                retry_audit = json.loads(retry_audit_content)
                retry_request_content = retry_request_path.read_bytes()
                retry_request = json.loads(retry_request_content)
                retry_response_content = retry_response_path.read_bytes()
                retry_response = json.loads(retry_response_content)
                if (
                    not isinstance(retry_audit, dict)
                    or not isinstance(retry_request, dict)
                    or not isinstance(retry_response, dict)
                    or serialize_call_record(retry_audit)
                    != retry_audit_content
                    or retry_audit.get("request_id") == request_id
                ):
                    raise ValueError("retry evidence")
                expected_retry_audit = {
                    "provider": "qwen-vl",
                    "model": identity["model"],
                    "prompt_version": VISUAL_PROMPT_VERSION,
                    "schema_version": VISUAL_SCHEMA_VERSION,
                    "retry_count": 0,
                    "input_image_count": 1,
                    "estimated_cost": None,
                    "logical_task_reused": False,
                    "request_ref": f"asset://{retry_paths[1]}",
                    "response_ref": f"asset://{retry_paths[2]}",
                }
                if any(
                    retry_audit.get(key) != value
                    for key, value in expected_retry_audit.items()
                ):
                    raise ValueError("retry audit")
                retry_request_evidence = parse_visual_request_evidence(
                    retry_request,
                    expected_crop_ref=f"asset://{crop_relative_path}",
                    expected_crop_sha256=str(identity["crop_sha256"]),
                    expected_usage=retry_request.get("usage"),
                )
                expected_retry_response = build_visual_failure_envelope(
                    "tool_arguments_schema_invalid"
                )
                if (
                    _json_bytes(retry_request_evidence)
                    != retry_request_content
                    or retry_response != expected_retry_response
                    or _json_bytes(expected_retry_response)
                    != retry_response_content
                ):
                    raise ValueError("retry payload")
                retry_request_ids = (str(retry_audit["request_id"]),)
            return (
                VisionResult(
                    request_id=request_id,
                    payload=response,
                    usage=usage,
                ),
                (*retry_request_ids, request_id),
            )
        except Exception:
            raise CandidateAdvisorFailure(
                "Visual symbol Advisor cache is invalid"
            ) from None

    def _visual_review_result(
        self,
        *,
        provider: object | None,
        crop_png: bytes,
        crop_bbox_pdf: BBox,
        source_sha256: str,
        visual_observations: Sequence[VisualObservation],
        text_observations: dict[str, TextObservation],
        model: str,
        allow_schema_retry: bool = False,
        execution_identity: VisualExecutionIdentity | None = None,
        retry_authorizer: (
            Callable[[VisualExecutionIdentity | None, int], bool] | None
        ) = None,
        legacy_cache_enabled: bool = True,
        evidence_context: VisualEvidenceContext | None = None,
    ) -> VisualReviewOutcome:
        if not isinstance(allow_schema_retry, bool):
            raise ValueError("visual schema retry flag must be boolean")
        if retry_authorizer is not None and not callable(retry_authorizer):
            raise ValueError("visual retry authorizer must be callable")
        if not isinstance(legacy_cache_enabled, bool):
            raise ValueError("legacy visual cache flag must be boolean")
        if (evidence_context is None) != (execution_identity is None):
            if evidence_context is not None:
                raise ValueError(
                    "visual evidence context requires execution identity"
                )
        canonical_crop_png = canonicalize_visual_png(crop_png)
        crop_sha256 = hashlib.sha256(canonical_crop_png).hexdigest()
        if (
            execution_identity is not None
            and execution_identity.crop_sha256 != crop_sha256
        ):
            raise CandidateAdvisorFailure(
                "Visual symbol execution identity is invalid"
            )
        visual_observation_ids = tuple(
            observation.observation_id
            for observation in visual_observations
        )
        identity = visual_cache_identity(
            source_sha256=source_sha256,
            visual_observation_ids=visual_observation_ids,
            crop_bbox_pdf=crop_bbox_pdf,
            crop_sha256=crop_sha256,
            model=model,
        )
        cache_key = visual_cache_key(
            source_sha256=source_sha256,
            visual_observation_ids=visual_observation_ids,
            crop_bbox_pdf=crop_bbox_pdf,
            crop_sha256=crop_sha256,
            model=model,
        )
        cache_relative = (
            f"projects/{self._project_id}/provider-cache/qwen-symbol/"
            f"{cache_key}.json"
        )
        audit_relative = (
            f"projects/{self._project_id}/provider-calls/qwen-symbol/"
            f"{cache_key}.json"
        )
        crop_relative = (
            f"projects/{self._project_id}/provider-inputs/qwen-symbol/"
            f"{crop_sha256}.png"
        )
        request_relative = (
            f"projects/{self._project_id}/provider-requests/"
            f"qwen-symbol/{cache_key}.json"
        )
        attempt_event_sha256s: list[str] = []
        production_cache_identity: SymbolCacheIdentity | None = None
        if (
            evidence_context is not None
            and execution_identity is not None
            and self._symbol_session_factory is not None
        ):
            if (
                self._require_symbol_persistence
                and (
                    not execution_identity.member_content_sha256s
                    or len(
                        set(
                            execution_identity.member_content_sha256s
                        )
                    )
                    != len(execution_identity.member_content_sha256s)
                )
            ):
                raise CandidateAdvisorFailure(
                    "Visual symbol cache member identity is invalid"
                )
            production_cache_identity = (
                self._production_cache_identity(
                    execution_identity=execution_identity,
                    visual_observations=visual_observations,
                    text_observations=text_observations,
                    model=model,
                )
            )
            session = self._symbol_session_factory()
            terminal_outcome: EscalationOutcome | None = None
            try:
                evidence = RoutingEvidenceRepository(session)
                terminal_outcome = evidence.load_terminal_outcome(
                    project_id=self._project_uuid(),
                    escalation_group_id=(
                        evidence_context.escalation_group_id
                    ),
                    routing_decision_sha256=(
                        evidence_context.routing_decision_sha256
                    ),
                )
                lookup = VisualSymbolCache(session).lookup(
                    project_id=self._project_uuid(),
                    identity=production_cache_identity,
                    consumer=(
                        None
                        if terminal_outcome is not None
                        else CacheConsumer(
                            escalation_group_id=(
                                evidence_context.escalation_group_id
                            ),
                            routing_decision_sha256=(
                                evidence_context.routing_decision_sha256
                            ),
                            attempt_index=0,
                        )
                    ),
                    evidence=(
                        None if terminal_outcome is not None else evidence
                    ),
                    provenance_validator=(
                        self._production_cache_provenance_valid
                    ),
                )
                if terminal_outcome is not None and not lookup.hit:
                    raise CandidateAdvisorFailure(
                        "Visual symbol terminal replay cache is invalid"
                    )
                session.commit()
            except Exception:
                session.rollback()
                raise CandidateAdvisorFailure(
                    "Visual symbol cache lookup failed"
                ) from None
            finally:
                session.close()
            attempt_event_sha256s.extend(
                (
                    terminal_outcome.attempt_event_sha256s
                    if terminal_outcome is not None
                    else lookup.attempt_event_sha256s
                )
            )
            if lookup.hit:
                if (
                    lookup.response is None
                    or lookup.entry is None
                    or lookup.entry.provenance is None
                ):
                    raise CandidateAdvisorFailure(
                        "Visual symbol cache hit is invalid"
                    )
                return VisualReviewOutcome(
                    result=VisionResult(
                        request_id=(
                            lookup.entry.provenance.producer_request_id
                        ),
                        payload=lookup.response,
                        usage={},
                    ),
                    provider=provider,
                    provenance_request_ids=(
                        lookup.entry.provenance.producer_request_id,
                    ),
                    current_attempt_request_ids=(),
                    current_attempt_count=0,
                    retry_count=0,
                    attempt_duration_ms=(),
                    measured_duration_ms=0,
                    cache_hit=True,
                    execution_identity=execution_identity,
                    attempt_event_sha256s=tuple(
                        attempt_event_sha256s
                    ),
                    terminal_replay=terminal_outcome is not None,
                )
        cached = (
            self._visual_cache_result(
                cache_relative,
                audit_relative_path=audit_relative,
                crop_relative_path=crop_relative,
                request_relative_path=request_relative,
                identity=identity,
            )
            if legacy_cache_enabled
            else None
        )
        if cached is not None:
            cached_result, cached_request_ids = cached
            if len(cached_request_ids) > 1 and not allow_schema_retry:
                raise CandidateAdvisorFailure(
                    "Visual symbol Advisor retry budget is invalid"
                )
            return VisualReviewOutcome(
                result=cached_result,
                provider=provider,
                provenance_request_ids=cached_request_ids,
                current_attempt_request_ids=(),
                current_attempt_count=0,
                retry_count=0,
                attempt_duration_ms=(),
                measured_duration_ms=0,
                cache_hit=True,
                execution_identity=execution_identity,
                attempt_event_sha256s=(),
            )

        def append_attempt(
            *,
            attempt_index: int,
            event_code: str,
            provider_request_id: str | None = None,
        ) -> None:
            if evidence_context is None:
                return
            event_sha256 = self._append_attempt_event(
                context=evidence_context,
                attempt_index=attempt_index,
                event_code=event_code,
                provider_request_id=provider_request_id,
            )
            if event_sha256:
                attempt_event_sha256s.append(event_sha256)

        def persist_terminal_failure(observation_code: str) -> None:
            if evidence_context is None:
                return
            self._record_terminal_outcome(
                context=evidence_context,
                outcome_code="unresolved",
                observation_outcomes=tuple(
                    ObservationOutcome(
                        visual_observation_id=(
                            observation.observation_id
                        ),
                        outcome_code=observation_code,
                    )
                    for observation in visual_observations
                ),
                attempt_event_sha256s=tuple(
                    attempt_event_sha256s
                ),
            )

        if provider is None:
            try:
                provider = self._provider_factory(self._settings)
            except CapabilityUnavailable:
                append_attempt(
                    attempt_index=0,
                    event_code="provider_unavailable",
                )
                persist_terminal_failure("provider_unavailable")
                raise
            except Exception:
                append_attempt(
                    attempt_index=0,
                    event_code="provider_transport_failure",
                )
                persist_terminal_failure(
                    "provider_transport_failure"
                )
                raise CandidateAdvisorFailure(
                    "Visual symbol Advisor call failed"
                ) from None
        crop_write = self._storage.write_verified(
            crop_relative,
            canonical_crop_png,
            crop_sha256,
        )
        prompt = visual_review_prompt(
            visual_observations,
            text_observations=text_observations,
            crop_bbox_pdf=crop_bbox_pdf,
        )

        def call_once() -> tuple[
            VisionResult | None,
            tuple[str, dict[str, int], str] | None,
            int,
        ]:
            started = time.perf_counter_ns()
            result: VisionResult | None = None
            failure: tuple[str, dict[str, int], str] | None = None
            unexpected_failure = False
            try:
                raw_result = provider.review_symbols(
                    canonical_crop_png,
                    prompt,
                )
                response = parse_visual_symbol_json(raw_result.payload)
                request_id, usage = validate_visual_request_metadata(
                    raw_result.request_id,
                    raw_result.usage,
                )
                result = VisionResult(
                    request_id=request_id,
                    payload=response,
                    usage=usage,
                )
            except VisualSymbolProviderError as exc:
                failure = (
                    exc.request_id,
                    dict(exc.usage),
                    exc.failure_stage,
                )
            except CapabilityUnavailable:
                raise
            except Exception:
                unexpected_failure = True
            duration_ms = max(
                0,
                (time.perf_counter_ns() - started) // 1_000_000,
            )
            if unexpected_failure:
                raise CandidateAdvisorFailure(
                    "Visual symbol Advisor call failed"
                ) from None
            return result, failure, duration_ms

        def persist_failure(
            failure: tuple[str, dict[str, int], str],
            *,
            duration_ms: int,
            retry_count: int,
            audit_path: str,
            request_path: str,
            response_path: str,
        ) -> None:
            request_id, usage, failure_stage = failure
            request_content = _json_bytes(
                build_visual_request_evidence(
                    crop_ref=crop_write.resource_ref,
                    crop_sha256=crop_write.sha256,
                    usage=usage,
                )
            )
            request_write = self._storage.write_verified(
                request_path,
                request_content,
                hashlib.sha256(request_content).hexdigest(),
            )
            failure_content = _json_bytes(
                build_visual_failure_envelope(failure_stage)
            )
            failure_write = self._storage.write_verified(
                response_path,
                failure_content,
                hashlib.sha256(failure_content).hexdigest(),
            )
            persist_call_record(
                self._storage,
                audit_path,
                ProviderCallRecord(
                    provider="qwen-vl",
                    request_id=request_id,
                    model=model,
                    prompt_version=VISUAL_PROMPT_VERSION,
                    schema_version=VISUAL_SCHEMA_VERSION,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                    input_image_count=1,
                    estimated_cost=None,
                    logical_task_reused=False,
                    request_ref=request_write.resource_ref,
                    response_ref=failure_write.resource_ref,
                ),
            )

        try:
            result, provider_failure, duration_ms = call_once()
        except CapabilityUnavailable:
            append_attempt(
                attempt_index=0,
                event_code="provider_unavailable",
            )
            persist_terminal_failure("provider_unavailable")
            raise
        except CandidateAdvisorFailure:
            append_attempt(
                attempt_index=0,
                event_code="provider_transport_failure",
            )
            persist_terminal_failure("provider_transport_failure")
            raise
        request_ids: list[str] = []
        attempt_durations = [duration_ms]
        retry_count = 0
        if (
            provider_failure is not None
            and allow_schema_retry
            and provider_failure[2] == "tool_arguments_schema_invalid"
            and (
                retry_authorizer is None
                or retry_authorizer(
                    execution_identity,
                    duration_ms,
                )
                is True
            )
        ):
            retry_paths = _visual_retry_evidence_paths(
                self._project_id,
                cache_key,
            )
            persist_failure(
                provider_failure,
                duration_ms=duration_ms,
                retry_count=0,
                audit_path=retry_paths[0],
                request_path=retry_paths[1],
                response_path=retry_paths[2],
            )
            append_attempt(
                attempt_index=0,
                event_code="provider_schema_invalid",
                provider_request_id=provider_failure[0],
            )
            append_attempt(
                attempt_index=0,
                event_code="retry_scheduled",
                provider_request_id=provider_failure[0],
            )
            request_ids.append(provider_failure[0])
            try:
                result, provider_failure, duration_ms = call_once()
            except CapabilityUnavailable:
                append_attempt(
                    attempt_index=1,
                    event_code="provider_unavailable",
                )
                persist_terminal_failure("provider_unavailable")
                raise
            except CandidateAdvisorFailure:
                append_attempt(
                    attempt_index=1,
                    event_code="provider_transport_failure",
                )
                persist_terminal_failure(
                    "provider_transport_failure"
                )
                raise
            attempt_durations.append(duration_ms)
            retry_count = 1

        if provider_failure is not None:
            persist_failure(
                provider_failure,
                duration_ms=duration_ms,
                retry_count=retry_count,
                audit_path=audit_relative,
                request_path=request_relative,
                response_path=(
                    f"projects/{self._project_id}/provider-responses/"
                    f"qwen-symbol/{cache_key}.json"
                ),
            )
            append_attempt(
                attempt_index=retry_count,
                event_code="provider_schema_invalid",
                provider_request_id=provider_failure[0],
            )
            persist_terminal_failure("provider_schema_invalid")
            raise CandidateAdvisorFailure(
                "Visual symbol Advisor response is invalid"
            ) from None
        if result is None:
            append_attempt(
                attempt_index=retry_count,
                event_code="provider_transport_failure",
            )
            persist_terminal_failure("provider_transport_failure")
            raise CandidateAdvisorFailure(
                "Visual symbol Advisor call failed"
            ) from None
        request_ids.append(result.request_id)
        request_content = _json_bytes(
            build_visual_request_evidence(
                crop_ref=crop_write.resource_ref,
                crop_sha256=crop_write.sha256,
                usage=result.usage,
            )
        )
        request_write = self._storage.write_verified(
            request_relative,
            request_content,
            hashlib.sha256(request_content).hexdigest(),
        )
        response_content = canonical_visual_response_bytes(result.payload)
        response_sha256 = hashlib.sha256(response_content).hexdigest()
        response_relative = (
            f"projects/{self._project_id}/provider-responses/"
            f"qwen-symbol/{response_sha256}.json"
        )
        response_write = self._storage.write_verified(
            response_relative,
            response_content,
            response_sha256,
        )
        cache_payload = build_visual_cache_envelope(
            request_id=result.request_id,
            identity=identity,
            response=result.payload,
            usage=result.usage,
        )
        cache_content = _json_bytes(cache_payload)
        if legacy_cache_enabled:
            self._storage.write_verified(
                cache_relative,
                cache_content,
                hashlib.sha256(cache_content).hexdigest(),
            )
        persist_call_record(
            self._storage,
            audit_relative,
            ProviderCallRecord(
                provider="qwen-vl",
                request_id=result.request_id,
                model=model,
                prompt_version=VISUAL_PROMPT_VERSION,
                schema_version=VISUAL_SCHEMA_VERSION,
                duration_ms=duration_ms,
                retry_count=retry_count,
                input_image_count=1,
                estimated_cost=None,
                logical_task_reused=False,
                request_ref=request_write.resource_ref,
                response_ref=response_write.resource_ref,
            ),
        )
        if (
            production_cache_identity is not None
            and self._symbol_session_factory is not None
        ):
            session = self._symbol_session_factory()
            try:
                VisualSymbolCache(session).store_if_absent(
                    project_id=self._project_uuid(),
                    entry=build_cache_entry(
                        identity=production_cache_identity,
                        response=result.payload,
                        provenance=SymbolCacheProvenance(
                            identity_sha256=(
                                production_cache_identity.sha256
                            ),
                            producer_project_id=self._project_id,
                            producer_request_id=result.request_id,
                            producer_call_record_ref=(
                                f"asset://{audit_relative}"
                            ),
                            response_sha256=response_sha256,
                            created_at=datetime.now(UTC),
                            model_identity=model,
                            response_schema_version=(
                                VISUAL_SCHEMA_VERSION
                            ),
                            router_version=SYMBOL_ROUTER_VERSION,
                            validation_outcome="schema_valid",
                        ),
                        provider_event_code="provider_response_valid",
                        schema_valid=True,
                    ),
                )
                if evidence_context is None:
                    raise CandidateAdvisorFailure(
                        "Visual symbol routing evidence is incomplete"
                    )
                attempt = RoutingEvidenceRepository(
                    session
                ).append_attempt(
                    project_id=self._project_uuid(),
                    event=EscalationAttemptEvent(
                        schema_version=(
                            ESCALATION_ATTEMPT_SCHEMA_VERSION
                        ),
                        escalation_group_id=(
                            evidence_context.escalation_group_id
                        ),
                        routing_decision_sha256=(
                            evidence_context.routing_decision_sha256
                        ),
                        attempt_index=retry_count,
                        event_code="provider_response_valid",
                        cache_entry_id=None,
                        provider_request_id=result.request_id,
                    ),
                )
                session.commit()
                attempt_event_sha256s.append(attempt.event_sha256)
            except InvalidCacheWinner:
                session.rollback()
                append_attempt(
                    attempt_index=retry_count,
                    event_code="provider_response_valid",
                    provider_request_id=result.request_id,
                )
            except Exception:
                session.rollback()
                raise CandidateAdvisorFailure(
                    "Visual symbol cache persistence failed"
                ) from None
            finally:
                session.close()
        else:
            append_attempt(
                attempt_index=retry_count,
                event_code="provider_response_valid",
                provider_request_id=result.request_id,
            )
        current_request_ids = tuple(request_ids)
        return VisualReviewOutcome(
            result=result,
            provider=provider,
            provenance_request_ids=current_request_ids,
            current_attempt_request_ids=current_request_ids,
            current_attempt_count=len(current_request_ids),
            retry_count=retry_count,
            attempt_duration_ms=tuple(attempt_durations),
            measured_duration_ms=sum(attempt_durations),
            cache_hit=False,
            execution_identity=execution_identity,
            attempt_event_sha256s=tuple(attempt_event_sha256s),
        )

    def _review_result(
        self,
        *,
        provider: object | None,
        route: RoutedObject,
        crop_png: bytes,
        crop_bbox_pdf: tuple[float, float, float, float],
        padding_pdf: float,
        model: str,
    ) -> tuple[VisionResult, object | None]:
        del padding_pdf
        crop_sha256 = hashlib.sha256(crop_png).hexdigest()
        cache_key = _cache_key(
            model=model,
            route=route,
            crop_bbox_pdf=crop_bbox_pdf,
            crop_sha256=crop_sha256,
        )
        cache_relative = (
            f"projects/{self._project_id}/provider-cache/qwen/{cache_key}.json"
        )
        audit_relative = (
            f"projects/{self._project_id}/provider-calls/qwen/{cache_key}.json"
        )
        cached = self._cache_result(
            cache_relative,
            audit_relative_path=audit_relative,
            crop_sha256=crop_sha256,
            model=model,
        )
        if cached is not None:
            return cached, provider

        if provider is None:
            provider = self._provider_factory(self._settings)
        started = time.perf_counter_ns()
        try:
            raw_result = provider.review_candidate(
                crop_png,
                _review_prompt(route),
            )
            suggestion = _validated_suggestion(raw_result.payload)
            if (
                not isinstance(raw_result.request_id, str)
                or not raw_result.request_id.strip()
            ):
                raise ValueError("missing request ID")
            result = VisionResult(
                request_id=raw_result.request_id,
                payload=suggestion,
                usage=dict(raw_result.usage),
            )
        except CapabilityUnavailable:
            raise
        except Exception:
            raise CandidateAdvisorFailure(
                "Vision candidate Advisor call failed"
            ) from None
        duration_ms = max(0, (time.perf_counter_ns() - started) // 1_000_000)

        crop_relative = (
            f"projects/{self._project_id}/provider-inputs/qwen/"
            f"{crop_sha256}.png"
        )
        crop_write = self._storage.write_verified(
            crop_relative,
            crop_png,
            crop_sha256,
        )
        cache_payload = {
            "cache_schema_version": "candidate-advisor-cache/1",
            "provider": "qwen-vl",
            "request_id": result.request_id,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "crop_sha256": crop_sha256,
            "suggestion": result.payload,
            "usage": result.usage,
        }
        cache_content = _json_bytes(cache_payload)
        cache_write = self._storage.write_verified(
            cache_relative,
            cache_content,
            hashlib.sha256(cache_content).hexdigest(),
        )
        persist_call_record(
            self._storage,
            audit_relative,
            ProviderCallRecord(
                provider="qwen-vl",
                request_id=result.request_id,
                model=model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                duration_ms=duration_ms,
                retry_count=0,
                input_image_count=1,
                estimated_cost=None,
                logical_task_reused=False,
                request_ref=crop_write.resource_ref,
                response_ref=cache_write.resource_ref,
            ),
        )
        return result, provider

    def review(
        self,
        pdf_path: Path,
        pages: Sequence[Any],
        snapshot: CandidateSnapshot,
    ) -> CandidateSnapshot:
        production_local_decisions: list[list[VisualReviewDecision]] = [
            [] for _ in pages
        ]
        production_contexts: dict[str, Any] | None = None
        uncertainty_mode = self._settings.symbol_recognition_mode
        routing_decision_sha256_by_observation: dict[str, str] = {}
        uncertainty_routing_decisions: list[RoutingDecision] = []
        local_resolution_evidence_by_observation: dict[
            str, dict[str, object]
        ] = {}
        if (
            self._require_symbol_persistence
            and uncertainty_mode
            in {"shadow_uncertainty", "production_uncertainty"}
            and self._symbol_session_factory is None
        ):
            raise CandidateAdvisorFailure(
                "Symbol routing persistence is required"
            )
        if uncertainty_mode in {
            "shadow_uncertainty",
            "production_uncertainty",
        }:
            all_text = tuple(
                observation
                for page in pages
                for observation in page.observations
            )
            production_contexts = {
                item.observation_id: item
                for item in reconstruct_visual_geometry_contexts(
                    pdf_path,
                    pages,
                )
            }
            requests: list[EscalationRequest] = []
            routing_blocked = False
            try:
                for page_position, page in enumerate(pages):
                    for observation in page.visual_observations:
                        local_resolution = resolve_visual_observation(
                            observation=observation,
                            family_hypotheses=(
                                prepare_local_family_hypotheses(
                                    observation=observation,
                                    text_observations=all_text,
                                    candidates=snapshot.candidates,
                                    geometry_context=production_contexts.get(
                                        observation.observation_id
                                    ),
                                )
                            ),
                            text_observations=all_text,
                            candidates=snapshot.candidates,
                            geometry_context=production_contexts.get(
                                observation.observation_id
                            ),
                        )
                        routing_decision = validate_routing_decision(
                            route_visual_observation(local_resolution)
                        )
                        if (
                            routing_decision.visual_observation_id
                            != observation.observation_id
                        ):
                            raise ValueError(
                                "routing decision observation mismatch"
                            )
                        uncertainty_routing_decisions.append(
                            routing_decision
                        )
                        if routing_decision.disposition == "block":
                            routing_blocked = True
                            continue
                        if routing_decision.disposition == "locally_resolved":
                            if local_resolution.projection is None:
                                raise ValueError(
                                    "local symbol projection missing"
                                )
                            decision_sha256 = routing_decision_sha256(
                                decision=routing_decision,
                                escalation_group_id=None,
                                escalation_group_member_index=None,
                                local_resolution_ref=(
                                    "sha256:"
                                    + routing_decision.input_sha256
                                ),
                            )
                            local_resolution_evidence_by_observation[
                                observation.observation_id
                            ] = {
                                "schema_version": (
                                    routing_decision.schema_version
                                ),
                                "router_version": (
                                    routing_decision.router_version
                                ),
                                "input_sha256": (
                                    routing_decision.input_sha256
                                ),
                                "decision_sha256": decision_sha256,
                                "reason_codes": list(
                                    routing_decision
                                    .local_resolution_reason_codes
                                ),
                            }
                            production_local_decisions[
                                page_position
                            ].append(local_resolution.projection)
                            continue
                        requests.append(
                            EscalationRequest(
                                decision=routing_decision,
                                observation=observation,
                                local_resolution=local_resolution,
                                projected_wall_seconds=(
                                    PROJECTED_VISUAL_PRIMARY_WALL_SECONDS
                                ),
                            )
                        )
                if uncertainty_mode == "production_uncertainty":
                    plan = plan_symbol_escalation_batches(
                        requests,
                        actual_call_capacity_by_page={
                            page.page_index:
                            MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE
                            for page in pages
                        },
                    )
            except Exception:
                raise CandidateAdvisorFailure(
                    "Visual symbol routing contract is invalid"
                ) from None
            if uncertainty_mode == "production_uncertainty":
                visual_by_id = {
                    observation.observation_id: observation
                    for page in pages
                    for observation in page.visual_observations
                }
                ordered_group_members = {
                    batch.content_sha256: tuple(
                        sorted(
                            batch.observation_ids,
                            key=lambda observation_id: (
                                visual_by_id[observation_id].page_index,
                                visual_by_id[observation_id].bbox_pdf[1],
                                visual_by_id[observation_id].bbox_pdf[0],
                                visual_by_id[
                                    observation_id
                                ].proposal_kind,
                                observation_id,
                            ),
                        )
                    )
                    for batch in (*plan.batches, *plan.denied)
                }
                escalation_group_by_observation = {
                    observation_id: batch.content_sha256
                    for batch in (*plan.batches, *plan.denied)
                    for observation_id in batch.observation_ids
                }
                escalation_group_member_index_by_observation = {
                    observation_id: member_index
                    for group_id, observation_ids
                    in ordered_group_members.items()
                    for member_index, observation_id
                    in enumerate(observation_ids)
                }
            else:
                escalation_group_by_observation = {
                    decision.visual_observation_id: hashlib.sha256(
                        (
                            "shadow:"
                            + decision.visual_observation_id
                        ).encode("utf-8")
                    ).hexdigest()
                    for decision in uncertainty_routing_decisions
                    if decision.disposition == "escalate"
                }
                escalation_group_member_index_by_observation = {
                    decision.visual_observation_id: 0
                    for decision in uncertainty_routing_decisions
                    if decision.disposition == "escalate"
                }
            try:
                routing_decision_sha256_by_observation = (
                    self._record_routing_decisions(
                        decisions=uncertainty_routing_decisions,
                        escalation_group_by_observation=(
                            escalation_group_by_observation
                        ),
                        escalation_group_member_index_by_observation=(
                            escalation_group_member_index_by_observation
                        ),
                    )
                )
            except Exception:
                raise CandidateAdvisorFailure(
                    "Visual symbol routing evidence persistence failed"
                ) from None
            if (
                self._require_symbol_persistence
                and len(routing_decision_sha256_by_observation)
                != len(uncertainty_routing_decisions)
            ):
                raise CandidateAdvisorFailure(
                    "Visual symbol routing evidence is incomplete"
                )
            if any(
                routing_decision_sha256_by_observation.get(
                    observation_id,
                    evidence["decision_sha256"],
                )
                != evidence["decision_sha256"]
                for observation_id, evidence
                in local_resolution_evidence_by_observation.items()
            ):
                raise CandidateAdvisorFailure(
                    "Visual symbol local routing evidence conflicts"
                )
            if (
                uncertainty_mode == "production_uncertainty"
                and plan.denied
                and self._symbol_session_factory is not None
            ):
                try:
                    for denied_batch in plan.denied:
                        denied_observation_ids = tuple(
                            ordered_group_members[
                                denied_batch.content_sha256
                            ]
                        )
                        denied_decision_hashes = tuple(
                            routing_decision_sha256_by_observation[
                                observation_id
                            ]
                            for observation_id in denied_observation_ids
                        )
                        denied_context = VisualEvidenceContext(
                            escalation_group_id=(
                                denied_batch.content_sha256
                            ),
                            routing_decision_sha256=(
                                routing_decision_group_sha256(
                                    denied_decision_hashes
                                )
                            ),
                        )
                        event_sha256 = self._append_attempt_event(
                            context=denied_context,
                            attempt_index=0,
                            event_code=(
                                "not_started_budget_exhausted"
                            ),
                        )
                        self._record_terminal_outcome(
                            context=denied_context,
                            outcome_code="budget_exhausted",
                            observation_outcomes=tuple(
                                ObservationOutcome(
                                    visual_observation_id=(
                                        observation_id
                                    ),
                                    outcome_code=(
                                        "routing_budget_exhausted"
                                    ),
                                )
                                for observation_id
                                in denied_observation_ids
                            ),
                            attempt_event_sha256s=(event_sha256,),
                        )
                except Exception:
                    raise CandidateAdvisorFailure(
                        "Visual symbol routing evidence persistence failed"
                    ) from None
            if routing_blocked or (
                uncertainty_mode == "production_uncertainty"
                and plan.denied
            ):
                raise CandidateAdvisorFailure(
                    "Visual symbol routing contract is invalid"
                )
            if uncertainty_mode == "production_uncertainty":
                visual_batches = tuple(
                    tuple(
                        batch
                        for batch in plan.batches
                        if batch.page_index == page.page_index
                    )
                    for page in pages
                )
            else:
                production_local_decisions = [[] for _ in pages]
                local_resolution_evidence_by_observation = {}
                visual_batches = plan_visual_batches(pages, snapshot)
        else:
            visual_batches = plan_visual_batches(pages, snapshot)
        planned_visual_calls_by_page = {
            page.page_index: len(visual_batches[index])
            for index, page in enumerate(pages)
        }
        locally_resolved_text_ids: frozenset[str] = frozenset()
        locally_resolved_candidate_ids: frozenset[str] = frozenset()
        if uncertainty_mode == "production_uncertainty":
            locally_resolved_visual_ids = {
                decision.observation_id
                for page_decisions in production_local_decisions
                for decision in page_decisions
            }
            locally_resolved_text_ids = frozenset(
                text_id
                for page in pages
                for visual in page.visual_observations
                if visual.observation_id in locally_resolved_visual_ids
                for text_id in visual.associated_text_observation_ids
            )
            locally_resolved_candidate_ids = frozenset(
                candidate_id
                for page_decisions in production_local_decisions
                for decision in page_decisions
                for candidate_id in (
                    decision.candidate_id,
                    (
                        str(
                            snapshot.candidates[
                                decision.existing_candidate_index
                            ]["candidate_id"]
                        )
                        if decision.existing_candidate_index is not None
                        else None
                    ),
                )
                if candidate_id is not None
            )
        routes = _route_objects(
            pages,
            snapshot,
            max_calls_by_page={
                page_index: MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE - count
                for page_index, count in planned_visual_calls_by_page.items()
            },
            excluded_source_ids=locally_resolved_text_ids,
            excluded_candidate_ids=locally_resolved_candidate_ids,
        )
        model = self._settings.qwen_model.strip()
        provider: object | None = None
        candidates = [dict(candidate) for candidate in snapshot.candidates]
        coverage_entries = list(snapshot.coverage_entries)
        provider_call_ids = list(snapshot.provider_call_ids)
        source_signals = list(snapshot.source_signals)
        observations = {
            observation.observation_id: observation
            for observation in selected_observations(pages)
        }
        all_text_observations = tuple(
            observation
            for page in pages
            for observation in page.observations
        )
        text_observations_by_id = {
            observation.observation_id: observation
            for observation in all_text_observations
        }
        visual_observations = {
            observation.observation_id: observation
            for page in pages
            for observation in page.visual_observations
        }
        visual_coverage_indexes = {
            entry.observation_id: index
            for index, entry in enumerate(coverage_entries)
            if entry.observation_id in visual_observations
        }
        contexts = (
            production_contexts
            if production_contexts is not None
            else {
                item.observation_id: item
                for item in (
                    reconstruct_visual_geometry_contexts(pdf_path, pages)
                    if any(visual_batches)
                    else ()
                )
            }
        )
        source_sha256 = (
            hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
            if any(visual_batches)
            else ""
        )
        candidates_changed = False
        visual_retry_available = True
        actual_visual_calls_by_page = {
            page.page_index: 0
            for page in pages
        }
        document = pymupdf.open(pdf_path)
        try:
            accepted_by_page: list[list[ValidatedSymbolDetection]] = [
                [] for _ in pages
            ]
            rejection_sets_by_page: list[dict[str, set[str]]] = [
                {} for _ in pages
            ]

            def consume_visual_outcome(
                *,
                page_position: int,
                page_index: int,
                observation_ids: tuple[str, ...],
                batch_observations: tuple[VisualObservation, ...],
                crop_bbox_pdf: BBox,
                outcome: VisualReviewOutcome,
                evidence_context: VisualEvidenceContext | None = None,
            ) -> None:
                nonlocal provider, visual_retry_available
                result = outcome.result
                request_ids = outcome.provenance_request_ids
                if uncertainty_mode != "production_uncertainty":
                    provider = outcome.provider
                actual_visual_calls_by_page[
                    page_index
                ] += (
                    outcome.current_attempt_count
                    if uncertainty_mode == "production_uncertainty"
                    else len(outcome.provenance_request_ids)
                )
                if (
                    outcome.retry_count > 0
                    or (
                        uncertainty_mode != "production_uncertainty"
                        and len(request_ids) > 1
                    )
                ):
                    visual_retry_available = False
                accepted, rejected = validate_symbol_detections(
                    result.payload,
                    visual_observation_ids=observation_ids,
                    text_allowlists={
                        item.observation_id:
                        item.associated_text_observation_ids
                        for item in batch_observations
                    },
                    crop_bbox_pdf=crop_bbox_pdf,
                )
                accepted_by_page[page_position].extend(accepted)
                rejection_sets = rejection_sets_by_page[page_position]
                for rejected_item in rejected:
                    affected = (
                        (rejected_item.visual_observation_id,)
                        if rejected_item.visual_observation_id
                        in observation_ids
                        else observation_ids
                    )
                    for identity in affected:
                        rejection_sets.setdefault(identity, set()).add(
                            rejected_item.rejection_code
                        )
                if (
                    evidence_context is not None
                    and not outcome.terminal_replay
                ):
                    accepted_ids = {
                        detection.visual_observation_id
                        for detection in accepted
                    }
                    rejected_codes_by_observation: dict[
                        str, set[str]
                    ] = defaultdict(set)
                    for rejected_item in rejected:
                        affected = (
                            (
                                rejected_item.visual_observation_id,
                            )
                            if rejected_item.visual_observation_id
                            in observation_ids
                            else observation_ids
                        )
                        for observation_id in affected:
                            rejected_codes_by_observation[
                                observation_id
                            ].add(rejected_item.rejection_code)
                    observation_outcomes = tuple(
                        ObservationOutcome(
                            visual_observation_id=observation_id,
                            outcome_code=(
                                (
                                    "cache_resolved"
                                    if outcome.cache_hit
                                    else "provider_resolved"
                                )
                                if observation_id in accepted_ids
                                else (
                                    "provider_no_detection"
                                    if "visual_no_detection"
                                    in rejected_codes_by_observation.get(
                                        observation_id,
                                        set(),
                                    )
                                    else "provider_projection_rejected"
                                )
                            ),
                        )
                        for observation_id in observation_ids
                    )
                    resolved_count = sum(
                        item.outcome_code
                        in {"cache_resolved", "provider_resolved"}
                        for item in observation_outcomes
                    )
                    self._record_terminal_outcome(
                        context=evidence_context,
                        outcome_code=(
                            "resolved"
                            if resolved_count
                            == len(observation_outcomes)
                            else (
                                "partial_unresolved"
                                if resolved_count
                                else "unresolved"
                            )
                        ),
                        observation_outcomes=observation_outcomes,
                        attempt_event_sha256s=(
                            outcome.attempt_event_sha256s
                        ),
                    )
                provider_call_ids.extend(request_ids)

            if uncertainty_mode == "production_uncertainty":
                production_jobs: list[ProductionVisualJob] = []
                for page_position, page_batches in enumerate(
                    visual_batches
                ):
                    page_inventory = pages[page_position]
                    page = document[page_inventory.page_index]
                    for batch in page_batches:
                        ordered_observation_ids = (
                            ordered_group_members[
                                batch.content_sha256
                            ]
                        )
                        batch_observations = tuple(
                            visual_observations[identity]
                            for identity in ordered_observation_ids
                        )
                        packed_batches = pack_visual_batches(
                            page_inventory,
                            batch_observations,
                        )
                        if (
                            len(packed_batches) != 1
                            or set(packed_batches[0].observation_ids)
                            != set(ordered_observation_ids)
                        ):
                            raise CandidateAdvisorFailure(
                                "Visual symbol execution crop is invalid"
                            )
                        crop_bbox_pdf = packed_batches[0].crop_bbox_pdf
                        crop_png = _render_visual_crop(
                            page,
                            crop_bbox_pdf,
                        )
                        crop_sha256 = hashlib.sha256(
                            canonicalize_visual_png(crop_png)
                        ).hexdigest()
                        decision_hashes = tuple(
                            routing_decision_sha256_by_observation[
                                observation_id
                            ]
                            for observation_id in ordered_observation_ids
                            if observation_id
                            in routing_decision_sha256_by_observation
                        )
                        if (
                            self._require_symbol_persistence
                            and len(decision_hashes)
                            != len(ordered_observation_ids)
                        ):
                            raise CandidateAdvisorFailure(
                                "Visual symbol routing evidence is incomplete"
                            )
                        production_jobs.append(
                            ProductionVisualJob(
                                page_position=page_position,
                                page_index=batch.page_index,
                                observation_ids=ordered_observation_ids,
                                crop_bbox_pdf=crop_bbox_pdf,
                                crop_png=crop_png,
                                visual_observations=batch_observations,
                                execution_identity=VisualExecutionIdentity(
                                    page_index=batch.page_index,
                                    content_sha256=batch.content_sha256,
                                    lineage_sha256=batch.lineage_sha256,
                                    budget_sha256=batch.budget_sha256,
                                    observation_member_bindings=(
                                        batch.observation_member_bindings
                                    ),
                                    crop_sha256=crop_sha256,
                                    member_content_sha256s=(
                                        batch.member_content_sha256s
                                    ),
                                ),
                                escalation_group_id=batch.content_sha256,
                                routing_decision_sha256=(
                                    routing_decision_group_sha256(
                                        decision_hashes
                                    )
                                    if len(decision_hashes)
                                    == len(ordered_observation_ids)
                                    else batch.lineage_sha256
                                ),
                            )
                        )
                retry_coordinator = ProductionRetryCoordinator(
                    plan=plan,
                    actual_call_capacity_by_page={
                        page.page_index:
                        MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE
                        for page in pages
                    },
                    execution_identities=tuple(
                        job.execution_identity
                        for job in production_jobs
                    ),
                )
                outcomes: list[VisualReviewOutcome | None] = [
                    None for _ in production_jobs
                ]
                worker_failures: dict[int, Exception] = {}
                with ThreadPoolExecutor(
                    max_workers=MAX_VISUAL_IN_FLIGHT
                ) as executor:
                    outstanding: dict[int, Any] = {}
                    next_job_index = 0

                    def submit_job(job_index: int) -> bool:
                        job = production_jobs[job_index]
                        if not retry_coordinator.start_primary(
                            job.execution_identity
                        ):
                            context = VisualEvidenceContext(
                                escalation_group_id=(
                                    job.escalation_group_id
                                ),
                                routing_decision_sha256=(
                                    job.routing_decision_sha256
                                ),
                            )
                            event_sha256 = self._append_attempt_event(
                                context=context,
                                attempt_index=0,
                                event_code=(
                                    "not_started_budget_exhausted"
                                ),
                            )
                            self._record_terminal_outcome(
                                context=context,
                                outcome_code="budget_exhausted",
                                observation_outcomes=tuple(
                                    ObservationOutcome(
                                        visual_observation_id=(
                                            observation_id
                                        ),
                                        outcome_code=(
                                            "routing_budget_exhausted"
                                        ),
                                    )
                                    for observation_id
                                    in job.observation_ids
                                ),
                                attempt_event_sha256s=(
                                    event_sha256,
                                ),
                            )
                            worker_failures[job_index] = (
                                CandidateAdvisorFailure(
                                "Visual symbol actual wall budget exceeded"
                                )
                            )
                            return False
                        outstanding[job_index] = executor.submit(
                            self._visual_review_result,
                            provider=None,
                            crop_png=job.crop_png,
                            crop_bbox_pdf=job.crop_bbox_pdf,
                            source_sha256=source_sha256,
                            visual_observations=job.visual_observations,
                            text_observations=text_observations_by_id,
                            model=model,
                            allow_schema_retry=True,
                            execution_identity=(
                                job.execution_identity
                            ),
                            evidence_context=VisualEvidenceContext(
                                escalation_group_id=(
                                    job.escalation_group_id
                                ),
                                routing_decision_sha256=(
                                    job.routing_decision_sha256
                                ),
                            ),
                            retry_authorizer=retry_coordinator.authorize,
                            legacy_cache_enabled=False,
                        )
                        return True
                    while (
                        next_job_index < len(production_jobs)
                        and len(outstanding) < MAX_VISUAL_IN_FLIGHT
                    ):
                        submitted = submit_job(next_job_index)
                        next_job_index += 1
                        if not submitted:
                            break
                    while outstanding:
                        completed_futures, _ = wait(
                            tuple(outstanding.values()),
                            return_when=FIRST_COMPLETED,
                        )
                        completed_indexes = sorted(
                            index
                            for index, future in outstanding.items()
                            if future in completed_futures
                        )
                        for completed_index in completed_indexes:
                            future = outstanding.pop(completed_index)
                            try:
                                outcome = future.result()
                            except Exception as exc:
                                worker_failures[completed_index] = exc
                            else:
                                retry_coordinator.complete(outcome)
                                outcomes[completed_index] = outcome
                        while (
                            not worker_failures
                            and next_job_index < len(production_jobs)
                            and len(outstanding)
                            < MAX_VISUAL_IN_FLIGHT
                        ):
                            submitted = submit_job(next_job_index)
                            next_job_index += 1
                            if not submitted:
                                break
                started_job_count = next_job_index
                for job_index in range(started_job_count):
                    job = production_jobs[job_index]
                    outcome = outcomes[job_index]
                    if outcome is None:
                        continue
                    consume_visual_outcome(
                        page_position=job.page_position,
                        page_index=job.page_index,
                        observation_ids=job.observation_ids,
                        batch_observations=job.visual_observations,
                        crop_bbox_pdf=job.crop_bbox_pdf,
                        outcome=outcome,
                        evidence_context=VisualEvidenceContext(
                            escalation_group_id=(
                                job.escalation_group_id
                            ),
                            routing_decision_sha256=(
                                job.routing_decision_sha256
                            ),
                        ),
                    )
                if worker_failures:
                    raise worker_failures[min(worker_failures)]
                if any(outcome is None for outcome in outcomes):
                    raise CandidateAdvisorFailure(
                        "Visual symbol execution outcome is missing"
                    )
            else:
                for page_position, page_batches in enumerate(visual_batches):
                    page_inventory = pages[page_position]
                    page = document[page_inventory.page_index]
                    for batch in page_batches:
                        crop_bbox_pdf = batch.crop_bbox_pdf
                        batch_observations = tuple(
                            visual_observations[identity]
                            for identity in batch.observation_ids
                        )
                        crop_png = _render_visual_crop(
                            page,
                            crop_bbox_pdf,
                        )
                        outcome = self._visual_review_result(
                            provider=provider,
                            crop_png=crop_png,
                            crop_bbox_pdf=crop_bbox_pdf,
                            source_sha256=source_sha256,
                            visual_observations=batch_observations,
                            text_observations=text_observations_by_id,
                            model=model,
                            allow_schema_retry=(
                                visual_retry_available
                                and len(page_batches)
                                < MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE
                            ),
                        )
                        consume_visual_outcome(
                            page_position=page_position,
                            page_index=page_inventory.page_index,
                            observation_ids=batch.observation_ids,
                            batch_observations=batch_observations,
                            crop_bbox_pdf=crop_bbox_pdf,
                            outcome=outcome,
                        )

            base_candidates = tuple(candidates)
            visual_decisions = []
            for page_position, page in enumerate(pages):
                visual_decisions.extend(
                    project_visual_page(
                        visual_observations=page.visual_observations,
                        detections=tuple(
                            accepted_by_page[page_position]
                        ),
                        rejection_codes={
                            identity: sorted(codes)[0]
                            for identity, codes in (
                                rejection_sets_by_page[
                                    page_position
                                ].items()
                            )
                        },
                        text_observations=all_text_observations,
                        candidates=base_candidates,
                        geometry_contexts=contexts,
                        local_decisions=tuple(
                            production_local_decisions[page_position]
                        ),
                    )
                )

            retirement_by_candidate: dict[str, VisualReviewDecision] = {}
            replacement_by_candidate: dict[str, dict[str, Any]] = {}
            appended_by_candidate: dict[str, dict[str, Any]] = {}
            for decision in visual_decisions:
                review: dict[str, object] = {
                    "route": "visual_symbol",
                    "schema_version": VISUAL_SCHEMA_VERSION,
                    "symbol_kinds": list(decision.symbol_kinds),
                    "rejection_code": decision.rejection_code,
                    "confidence_signal": decision.confidence_signal,
                }
                local_resolution_evidence = (
                    local_resolution_evidence_by_observation.get(
                        decision.observation_id
                    )
                )
                if local_resolution_evidence is not None:
                    review["local_resolution_evidence"] = dict(
                        local_resolution_evidence
                    )
                if (
                    decision.disposition == "candidate"
                    and decision.candidate_envelope is not None
                    and decision.candidate_id is not None
                ):
                    target = (
                        replacement_by_candidate
                        if decision.existing_candidate_index is not None
                        else appended_by_candidate
                    )
                    target[decision.candidate_id] = (
                        decision.candidate_envelope
                    )
                elif (
                    decision.rejection_code is None
                    and decision.disposition
                    in {"reference_context", "non_inspection"}
                    and decision.existing_candidate_index is not None
                ):
                    retired = base_candidates[
                        decision.existing_candidate_index
                    ]
                    retirement_by_candidate[
                        str(retired["candidate_id"])
                    ] = decision

                coverage_index = visual_coverage_indexes[
                    decision.observation_id
                ]
                coverage_entries[coverage_index] = replace(
                    coverage_entries[coverage_index],
                    disposition=decision.disposition,
                    source_location_id=decision.observation_id,
                    coordinates=decision.coordinates,
                    candidate_id=decision.candidate_id,
                    requires_confirmation=decision.requires_confirmation,
                    advisor_review=review,
                )

            if replacement_by_candidate:
                candidates = [
                    replacement_by_candidate.get(
                        str(candidate["candidate_id"]),
                        candidate,
                    )
                    for candidate in candidates
                ]
            for candidate_id, envelope in appended_by_candidate.items():
                if not any(
                    str(candidate["candidate_id"]) == candidate_id
                    for candidate in candidates
                ):
                    candidates.append(envelope)
            if retirement_by_candidate:
                candidates = [
                    candidate
                    for candidate in candidates
                    if str(candidate["candidate_id"])
                    not in retirement_by_candidate
                ]
                for index, entry in enumerate(coverage_entries):
                    if (
                        entry.candidate_id is None
                        or entry.candidate_id
                        not in retirement_by_candidate
                    ):
                        continue
                    retirement = retirement_by_candidate[
                        entry.candidate_id
                    ]
                    coverage_entries[index] = replace(
                        entry,
                        disposition=retirement.disposition,
                        candidate_id=None,
                        requires_confirmation=(
                            retirement.requires_confirmation
                        ),
                        advisor_review={
                            "route": "visual_symbol",
                            "schema_version": VISUAL_SCHEMA_VERSION,
                            "symbol_kinds": list(
                                retirement.symbol_kinds
                            ),
                            "rejection_code": None,
                            "confidence_signal": (
                                retirement.confidence_signal
                            ),
                            **(
                                {
                                    "local_resolution_evidence": dict(
                                        local_resolution_evidence_by_observation[
                                            retirement.observation_id
                                        ]
                                    )
                                }
                                if retirement.observation_id
                                in local_resolution_evidence_by_observation
                                else {}
                            ),
                        },
                    )
            candidates_changed = candidates != list(base_candidates)
            visual_signal_values: dict[str, Decimal] = {}
            for decision in visual_decisions:
                if (
                    decision.disposition != "candidate"
                    or decision.candidate_id is None
                    or decision.confidence_signal is None
                ):
                    continue
                normalized = normalize_visual_signal(
                    decision.confidence_signal
                )
                for source_id in decision.source_location_ids:
                    if source_id not in visual_observations:
                        continue
                    prior = visual_signal_values.get(source_id)
                    visual_signal_values[source_id] = (
                        normalized
                        if prior is None
                        else min(prior, normalized)
                    )
            source_signals.extend(
                CandidateSourceSignal(
                    source_location_id=source_id,
                    source_type="visual",
                    normalized_value=visual_signal_values[source_id],
                )
                for source_id in sorted(visual_signal_values)
            )

            if (
                not routes
                and not any(visual_batches)
                and not any(production_local_decisions)
            ):
                return snapshot

            text_calls_by_page = {
                page.page_index: 0
                for page in pages
            }
            for frozen_route in routes:
                if (
                    actual_visual_calls_by_page[frozen_route.page_index]
                    + text_calls_by_page[frozen_route.page_index]
                    >= MAX_UNIFIED_ACTUAL_CALLS_PER_PAGE
                ):
                    continue
                if frozen_route.candidate_id is not None:
                    current_indexes = [
                        index
                        for index, candidate in enumerate(candidates)
                        if str(candidate.get("candidate_id"))
                        == frozen_route.candidate_id
                    ]
                else:
                    current_indexes = [
                        index
                        for index, candidate in enumerate(candidates)
                        if set(frozen_route.source_ids).intersection(
                            candidate.get("source_location_ids", ())
                        )
                    ]
                if len(current_indexes) > 1:
                    continue
                if (
                    frozen_route.candidate_id is not None
                    and not current_indexes
                ):
                    continue
                route = replace(
                    frozen_route,
                    candidate_index=(
                        current_indexes[0] if current_indexes else None
                    ),
                )
                page = document[route.page_index]
                crop, padding = _crop_rect(page, route.bbox_pdf)
                crop_png = _render_crop(page, crop)
                crop_bbox_pdf = (
                    float(crop.x0),
                    float(crop.y0),
                    float(crop.x1),
                    float(crop.y1),
                )
                result, provider = self._review_result(
                    provider=provider,
                    route=route,
                    crop_png=crop_png,
                    crop_bbox_pdf=crop_bbox_pdf,
                    padding_pdf=padding,
                    model=model,
                )
                text_calls_by_page[route.page_index] += 1
                rejection_code = _rejection_code(route, result.payload)

                updated_payload: dict[str, Any] | None = None
                promoted_candidate: dict[str, Any] | None = None
                if rejection_code is None and route.candidate_index is None:
                    try:
                        parsed = parse_annotation(
                            str(result.payload["normalized_text"])
                        )
                    except ValueError:
                        rejection_code = "local_parse_failed"
                    else:
                        if parsed.item_type != result.payload["item_type"]:
                            rejection_code = "type_mismatch"
                        else:
                            parsed = parsed.model_copy(
                                update={
                                    "candidate_id": stable_candidate_id(
                                        "annotation",
                                        route.raw_text,
                                    ),
                                    "raw_text": route.raw_text,
                                    "coordinates": route.bbox_pdf,
                                    "requires_confirmation": True,
                                }
                            )
                            promoted_candidate = {
                                "candidate_id": parsed.candidate_id,
                                "payload": parsed.model_dump(
                                    mode="json",
                                    exclude_none=True,
                                ),
                                "source_location_ids": list(route.source_ids),
                            }
                elif rejection_code is None and route.candidate_index is not None:
                    current_payload = candidates[route.candidate_index].get(
                        "payload"
                    )
                    if isinstance(current_payload, dict):
                        updated_payload = dict(current_payload)
                        item_type = current_payload.get("item_type")
                        if item_type in _PARSEABLE_TYPES:
                            try:
                                parsed = parse_annotation(
                                    str(result.payload["normalized_text"])
                                )
                            except ValueError:
                                rejection_code = "local_parse_failed"
                            else:
                                if parsed.item_type != item_type:
                                    rejection_code = "type_mismatch"
                                else:
                                    updated_payload["normalized_text"] = (
                                        parsed.normalized_text
                                    )
                        if rejection_code is None:
                            updated_payload["requires_confirmation"] = bool(
                                current_payload.get(
                                    "requires_confirmation",
                                    False,
                                )
                                or result.payload["requires_confirmation"]
                            )

                advisor_review: dict[str, object] = {
                    "provider_role": "advisor",
                    "review_reason": route.review_reason,
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "page_index": route.page_index,
                    "crop_bbox_pdf": list(crop_bbox_pdf),
                    "padding_pdf": float(padding),
                    "crop_sha256": hashlib.sha256(crop_png).hexdigest(),
                    "validated": rejection_code is None,
                    "rejection_code": rejection_code,
                }
                provider_call_ids.append(result.request_id)
                if route.candidate_index is not None:
                    candidate = dict(candidates[route.candidate_index])
                    if rejection_code is None and updated_payload is not None:
                        if updated_payload != candidate.get("payload"):
                            candidates_changed = True
                        candidate["payload"] = updated_payload
                    candidate["advisor_review"] = advisor_review
                    candidates[route.candidate_index] = candidate
                elif rejection_code is None and promoted_candidate is not None:
                    promoted_candidate["advisor_review"] = advisor_review
                    candidates.append(promoted_candidate)
                    coverage_entries[route.coverage_index] = replace(
                        coverage_entries[route.coverage_index],
                        disposition="candidate",
                        candidate_id=str(promoted_candidate["candidate_id"]),
                        requires_confirmation=True,
                        advisor_review=advisor_review,
                    )
                    candidates_changed = True
                else:
                    coverage_entries[route.coverage_index] = replace(
                        coverage_entries[route.coverage_index],
                        advisor_review=advisor_review,
                    )
        finally:
            document.close()

        duplicate_relations = (
            _duplicate_relations(candidates, observations)
            if candidates_changed
            else snapshot.duplicate_relations
        )
        return CandidateSnapshot(
            candidates=tuple(candidates),
            coverage_entries=tuple(coverage_entries),
            expected_observation_ids=snapshot.expected_observation_ids,
            duplicate_relations=duplicate_relations,
            source_signals=tuple(source_signals),
            provider_call_ids=tuple(provider_call_ids),
            required_visual_observation_ids=(
                snapshot.required_visual_observation_ids
            ),
        )
