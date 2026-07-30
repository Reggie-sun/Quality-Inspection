from __future__ import annotations

import hashlib
import json
import uuid
import zlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.candidates.advisor as advisor_module
from app.candidates.advisor import (
    CandidateAdvisor,
    CandidateAdvisorFailure,
    VisualEvidenceContext,
    VisualExecutionIdentity,
)
from app.candidates.models import (
    SymbolEscalationAttemptEventRecord,
    SymbolEscalationOutcomeRecord,
    SymbolRoutingDecisionRecord,
    VisualSymbolCacheEntryRecord,
)
from app.candidates.routing_evidence import (
    ESCALATION_ATTEMPT_SCHEMA_VERSION,
    ESCALATION_OUTCOME_SCHEMA_VERSION,
    EscalationAttemptEvent,
    EscalationOutcome,
    ObservationOutcome,
    RoutingEvidenceConflict,
    RoutingEvidenceRepository,
    routing_decision_group_sha256,
)
from app.candidates.symbol_cache import (
    CACHE_IDENTITY_SCHEMA_VERSION,
    CacheLookupResult,
    CacheWriteRejected,
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
    SYMBOL_ROUTING_SCHEMA_VERSION,
    RoutingDecision,
)
from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.db import SessionLocal, engine
from app.pdf.schemas import TextObservation, VisualObservation
from app.processing import tasks as processing_tasks
from app.processing.automatic_result import CandidateSnapshot
from app.projects.models import Project
from app.projects.state import ProjectState
from app.providers.base import VisionResult
from app.providers.qwen_vl import (
    VisualSymbolProviderError,
    canonicalize_visual_png,
)
from app.storage.local import LocalFileStorage


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
PROJECT_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
PROJECT_B = uuid.UUID("22222222-2222-4222-8222-222222222222")
SYMBOL_TABLES = {
    "symbol_routing_decisions",
    "symbol_escalation_attempt_events",
    "symbol_escalation_outcomes",
    "visual_symbol_cache_entries",
}
PRE_PRT4_TABLES = {
    "alembic_version",
    "projects",
    "stored_files",
    "operation_records",
    "logical_jobs",
    "error_records",
    "automatic_results",
    "review_working_copies",
    "review_locks",
    "balloons",
    "reviewed_results",
    "export_jobs",
    "export_artifacts",
}


@pytest.fixture
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def project_id(db_session: Session) -> uuid.UUID:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    db_session.add(project)
    db_session.commit()
    return project.id


@pytest.fixture
def committed_project_id() -> uuid.UUID:
    project_id = uuid.uuid4()
    with SessionLocal() as session:
        session.add(Project(id=project_id, state=ProjectState.PROCESSING))
        session.commit()
    return project_id


def _decision(
    *,
    observation_id: str = "visual-1",
    input_sha256: str = SHA_A,
) -> RoutingDecision:
    return RoutingDecision(
        schema_version=SYMBOL_ROUTING_SCHEMA_VERSION,
        router_version=SYMBOL_ROUTER_VERSION,
        visual_observation_id=observation_id,
        input_sha256=input_sha256,
        disposition="escalate",
        local_resolution_reason_codes=(),
        escalation_reason_codes=("local_parse_incomplete",),
        block_reason_codes=(),
        requires_confirmation=True,
    )


def _attempt(
    *,
    routing_decision_sha256: str,
    event_code: str = "cache_miss",
    provider_request_id: str | None = None,
    cache_entry_id: uuid.UUID | None = None,
    attempt_index: int = 0,
) -> EscalationAttemptEvent:
    return EscalationAttemptEvent(
        schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION,
        escalation_group_id="group-1",
        routing_decision_sha256=routing_decision_sha256,
        attempt_index=attempt_index,
        event_code=event_code,
        cache_entry_id=cache_entry_id,
        provider_request_id=provider_request_id,
    )


def _group_sha256(
    decision: SymbolRoutingDecisionRecord,
) -> str:
    return routing_decision_group_sha256(
        (decision.decision_sha256,)
    )


def _outcome(
    *,
    routing_decision_sha256: str,
    attempt_event_sha256: str,
    outcome_code: str = "unresolved",
) -> EscalationOutcome:
    return EscalationOutcome(
        schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
        escalation_group_id="group-1",
        routing_decision_sha256=routing_decision_sha256,
        outcome_code=outcome_code,
        observation_outcomes=(
            ObservationOutcome(
                visual_observation_id="visual-1",
                outcome_code="provider_unavailable",
            ),
        ),
        attempt_event_sha256s=(attempt_event_sha256,),
        terminal=True,
    )


@pytest.mark.parametrize(
    ("observation_code", "group_code"),
    (
        ("routing_budget_exhausted", "budget_exhausted"),
        ("cancelled_after_project_budget", "cancelled"),
    ),
)
def test_budget_and_cancellation_outcomes_use_distinct_contract_codes(
    observation_code: str,
    group_code: str,
) -> None:
    outcome = EscalationOutcome(
        schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
        escalation_group_id="group-1",
        routing_decision_sha256=SHA_A,
        outcome_code=group_code,
        observation_outcomes=(
            ObservationOutcome(
                visual_observation_id="visual-1",
                outcome_code=observation_code,
            ),
        ),
        attempt_event_sha256s=(SHA_B,),
        terminal=True,
    )

    assert outcome.outcome_code == group_code


def test_production_cache_identity_binds_members_and_exact_prompt_text() -> None:
    crop_png = _png()
    execution_identity = _execution_identity(crop_png)
    visual = _visual(
        "visual-1",
        associated_text_ids=("text-1", "text-2"),
    )
    texts = {
        "text-1": _text("text-1", raw_text="⌀10", observation_level="span"),
        "text-2": _text("text-2", raw_text="REF", observation_level="line"),
    }

    identity = CandidateAdvisor._production_cache_identity(
        execution_identity=execution_identity,
        visual_observations=(visual,),
        text_observations=texts,
        model="qwen3-vl-plus",
    )
    changed_text = CandidateAdvisor._production_cache_identity(
        execution_identity=execution_identity,
        visual_observations=(visual,),
        text_observations={
            **texts,
            "text-2": replace(texts["text-2"], raw_text="TYP"),
        },
        model="qwen3-vl-plus",
    )
    changed_level = CandidateAdvisor._production_cache_identity(
        execution_identity=execution_identity,
        visual_observations=(visual,),
        text_observations={
            **texts,
            "text-2": replace(
                texts["text-2"],
                observation_level="span",
            ),
        },
        model="qwen3-vl-plus",
    )

    assert identity.local_evidence_sha256s == (SHA_A, SHA_B)
    assert identity.local_evidence_sha256s != (
        SHA_C,
        SHA_C,
    )
    assert changed_text.associated_text_sha256 != (
        identity.associated_text_sha256
    )
    assert changed_level.associated_text_sha256 != (
        identity.associated_text_sha256
    )


@pytest.mark.parametrize(
    ("failure_mode", "expected_error", "expected_code"),
    (
        (
            "construction_unavailable",
            CapabilityUnavailable,
            "provider_unavailable",
        ),
        (
            "call_unavailable",
            CapabilityUnavailable,
            "provider_unavailable",
        ),
        (
            "call_transport",
            CandidateAdvisorFailure,
            "provider_transport_failure",
        ),
        (
            "schema_invalid",
            CandidateAdvisorFailure,
            "provider_schema_invalid",
        ),
    ),
)
def test_terminal_provider_failure_persists_one_complete_outcome(
    failure_mode: str,
    expected_error: type[Exception],
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    crop_png = _png()
    attempts: list[dict[str, object]] = []
    terminals: list[dict[str, object]] = []
    advisor = CandidateAdvisor(
        Settings(storage_root=tmp_path),
        LocalFileStorage(tmp_path),
        project_id=str(PROJECT_A),
        provider_factory=lambda _settings: (
            (_ for _ in ()).throw(
                CapabilityUnavailable(
                    "vision_provider",
                    "unavailable",
                )
            )
            if failure_mode == "construction_unavailable"
            else None
        ),
    )
    monkeypatch.setattr(
        advisor,
        "_append_attempt_event",
        lambda **kwargs: attempts.append(kwargs) or SHA_A,
    )
    monkeypatch.setattr(
        advisor,
        "_record_terminal_outcome",
        lambda **kwargs: terminals.append(kwargs),
    )

    def review_symbols(_image: bytes, _prompt: str) -> VisionResult:
        if failure_mode == "call_unavailable":
            raise CapabilityUnavailable(
                "vision_provider",
                "unavailable",
            )
        if failure_mode == "call_transport":
            raise RuntimeError("transport")
        if failure_mode == "schema_invalid":
            raise VisualSymbolProviderError(
                request_id="provider-request-invalid",
                usage={},
                failure_stage="tool_arguments_schema_invalid",
            )
        raise AssertionError("Provider should be constructed")

    with pytest.raises(expected_error):
        advisor._visual_review_result(
            provider=(
                None
                if failure_mode == "construction_unavailable"
                else SimpleNamespace(review_symbols=review_symbols)
            ),
            crop_png=crop_png,
            crop_bbox_pdf=(0.0, 0.0, 10.0, 10.0),
            source_sha256=SHA_A,
            visual_observations=(
                _visual("visual-1"),
                _visual("visual-2"),
            ),
            text_observations={"text-1": _text("text-1")},
            model="qwen3-vl-plus",
            execution_identity=_execution_identity(crop_png),
            legacy_cache_enabled=False,
            evidence_context=VisualEvidenceContext(
                escalation_group_id="group-1",
                routing_decision_sha256=SHA_C,
            ),
        )

    assert [attempt["event_code"] for attempt in attempts] == [
        expected_code
    ]
    assert len(terminals) == 1
    assert terminals[0]["outcome_code"] == "unresolved"
    assert terminals[0]["attempt_event_sha256s"] == (SHA_A,)
    assert terminals[0]["observation_outcomes"] == (
        ObservationOutcome(
            visual_observation_id="visual-1",
            outcome_code=expected_code,
        ),
        ObservationOutcome(
            visual_observation_id="visual-2",
            outcome_code=expected_code,
        ),
    )


def test_invalid_cache_winner_does_not_discard_fresh_provider_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    crop_png = _png()

    class SessionStub:
        commits = 0
        rollbacks = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

        def close(self) -> None:
            return None

    session = SessionStub()
    monkeypatch.setattr(
        VisualSymbolCache,
        "lookup",
        lambda *_args, **_kwargs: CacheLookupResult(
            hit=False,
            reason_code="cache_provenance_invalid",
            quarantine=True,
            response=None,
            attempt_event_sha256s=(SHA_A,),
        ),
    )
    monkeypatch.setattr(
        RoutingEvidenceRepository,
        "load_terminal_outcome",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        VisualSymbolCache,
        "store_if_absent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            InvalidCacheWinner("quarantined immutable winner")
        ),
    )
    advisor = CandidateAdvisor(
        Settings(storage_root=tmp_path),
        LocalFileStorage(tmp_path),
        project_id=str(PROJECT_A),
        provider_factory=lambda _settings: None,
        symbol_session_factory=lambda: session,  # type: ignore[arg-type]
        require_symbol_persistence=True,
    )
    monkeypatch.setattr(
        advisor,
        "_append_attempt_event",
        lambda **_kwargs: SHA_B,
    )

    outcome = advisor._visual_review_result(
        provider=SimpleNamespace(
            review_symbols=lambda _image, _prompt: VisionResult(
                request_id="provider-request-fresh",
                payload=_response(),
                usage={},
            )
        ),
        crop_png=crop_png,
        crop_bbox_pdf=(0.0, 0.0, 10.0, 10.0),
        source_sha256=SHA_A,
        visual_observations=(_visual("visual-1"),),
        text_observations={"text-1": _text("text-1")},
        model="qwen3-vl-plus",
        execution_identity=_execution_identity(crop_png),
        legacy_cache_enabled=False,
        evidence_context=VisualEvidenceContext(
            escalation_group_id="group-1",
            routing_decision_sha256=SHA_C,
        ),
    )

    assert outcome.result.request_id == "provider-request-fresh"
    assert outcome.cache_hit is False
    assert outcome.attempt_event_sha256s == (SHA_A, SHA_B)
    assert session.rollbacks == 1


def test_terminal_replay_reuses_valid_cache_without_new_attempt_or_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    crop_png = _png()
    terminal = EscalationOutcome(
        schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
        escalation_group_id="group-1",
        routing_decision_sha256=SHA_C,
        outcome_code="unresolved",
        observation_outcomes=(
            ObservationOutcome(
                visual_observation_id="visual-1",
                outcome_code="provider_no_detection",
            ),
        ),
        attempt_event_sha256s=(SHA_A,),
        terminal=True,
    )
    monkeypatch.setattr(
        RoutingEvidenceRepository,
        "load_terminal_outcome",
        lambda *_args, **_kwargs: terminal,
    )
    monkeypatch.setattr(
        VisualSymbolCache,
        "lookup",
        lambda *_args, **_kwargs: CacheLookupResult(
            hit=True,
            reason_code="cache_hit_valid",
            quarantine=False,
            response=_response(),
            entry=_cache_entry(producer_project_id=PROJECT_A),
        ),
    )
    appended: list[object] = []
    advisor = CandidateAdvisor(
        Settings(storage_root=tmp_path),
        LocalFileStorage(tmp_path),
        project_id=str(PROJECT_A),
        provider_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("terminal replay called Provider")
        ),
        symbol_session_factory=lambda: SimpleNamespace(
            commit=lambda: None,
            rollback=lambda: None,
            close=lambda: None,
        ),  # type: ignore[arg-type]
        require_symbol_persistence=True,
    )
    monkeypatch.setattr(
        advisor,
        "_append_attempt_event",
        lambda **kwargs: appended.append(kwargs) or SHA_B,
    )

    outcome = advisor._visual_review_result(
        provider=None,
        crop_png=crop_png,
        crop_bbox_pdf=(0.0, 0.0, 10.0, 10.0),
        source_sha256=SHA_A,
        visual_observations=(_visual("visual-1"),),
        text_observations={"text-1": _text("text-1")},
        model="qwen3-vl-plus",
        execution_identity=_execution_identity(crop_png),
        legacy_cache_enabled=False,
        evidence_context=VisualEvidenceContext(
            escalation_group_id="group-1",
            routing_decision_sha256=SHA_C,
        ),
    )

    assert outcome.terminal_replay is True
    assert outcome.attempt_event_sha256s == (SHA_A,)
    assert outcome.current_attempt_count == 0
    assert appended == []


def test_denied_group_persists_budget_terminal_before_whole_pdf_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    visual = _visual("visual-1")
    page = SimpleNamespace(
        page_index=0,
        observations=(_text("text-1"),),
        visual_observations=(visual,),
    )
    denied_batch = SimpleNamespace(
        content_sha256=SHA_C,
        observation_ids=("visual-1",),
    )
    decision = _decision()
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **_kwargs: (),
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        lambda **_kwargs: SimpleNamespace(projection=None),
    )
    monkeypatch.setattr(
        advisor_module,
        "route_visual_observation",
        lambda _resolution: decision,
    )
    monkeypatch.setattr(
        advisor_module,
        "plan_symbol_escalation_batches",
        lambda *_args, **_kwargs: SimpleNamespace(
            batches=(),
            denied=(denied_batch,),
        ),
    )
    advisor = CandidateAdvisor(
        Settings(
            storage_root=tmp_path,
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path),
        project_id=str(PROJECT_A),
        provider_factory=lambda _settings: None,
        symbol_session_factory=lambda: None,  # type: ignore[arg-type]
        require_symbol_persistence=True,
    )
    monkeypatch.setattr(
        advisor,
        "_record_routing_decisions",
        lambda **_kwargs: {"visual-1": SHA_A},
    )
    attempts: list[dict[str, object]] = []
    terminals: list[dict[str, object]] = []
    monkeypatch.setattr(
        advisor,
        "_append_attempt_event",
        lambda **kwargs: attempts.append(kwargs) or SHA_B,
    )
    monkeypatch.setattr(
        advisor,
        "_record_terminal_outcome",
        lambda **kwargs: terminals.append(kwargs),
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="routing contract is invalid",
    ):
        advisor.review(
            tmp_path / "not-opened.pdf",
            (page,),
            CandidateSnapshot(
                candidates=(),
                coverage_entries=(),
                expected_observation_ids=(),
                duplicate_relations=(),
            ),
        )

    group_sha256 = routing_decision_group_sha256((SHA_A,))
    assert attempts == [
        {
            "context": VisualEvidenceContext(
                escalation_group_id=SHA_C,
                routing_decision_sha256=group_sha256,
            ),
            "attempt_index": 0,
            "event_code": "not_started_budget_exhausted",
        }
    ]
    assert terminals == [
        {
            "context": VisualEvidenceContext(
                escalation_group_id=SHA_C,
                routing_decision_sha256=group_sha256,
            ),
            "outcome_code": "budget_exhausted",
            "observation_outcomes": (
                ObservationOutcome(
                    visual_observation_id="visual-1",
                    outcome_code="routing_budget_exhausted",
                ),
            ),
            "attempt_event_sha256s": (SHA_B,),
        }
    ]


def _identity() -> SymbolCacheIdentity:
    return SymbolCacheIdentity(
        schema_version=CACHE_IDENTITY_SCHEMA_VERSION,
        canonical_crop_sha256=SHA_A,
        associated_text_sha256=SHA_B,
        local_evidence_sha256s=(SHA_A, SHA_C),
        router_version=SYMBOL_ROUTER_VERSION,
        proposal_version="visual-observation-proposal/1",
        prompt_version="visual-symbol-prompt/4",
        response_schema_version="visual-symbol-review/1",
        adapter_version="qwen-visual-symbol-adapter/5",
        model_identity="qwen3-vl-plus",
        pymupdf_version="1.26.3",
        crop_canonicalization_version="symbol-roi-crop/1",
    )


def _response() -> dict[str, object]:
    return {
        "schema_version": "visual-symbol-review/1",
        "detections": [],
    }


def _response_sha256() -> str:
    return hashlib.sha256(
        json.dumps(
            _response(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _cache_entry(
    *,
    producer_project_id: uuid.UUID,
):
    identity = _identity()
    return build_cache_entry(
        identity=identity,
        response=_response(),
        provenance=SymbolCacheProvenance(
            identity_sha256=identity.sha256,
            producer_project_id=str(producer_project_id),
            producer_request_id="provider-request-1",
            producer_call_record_ref=(
                f"asset://projects/{producer_project_id}/provider-calls/"
                "qwen-symbol/provider-request-1.json"
            ),
            response_sha256=_response_sha256(),
            created_at=datetime(2026, 7, 30, tzinfo=UTC),
            model_identity=identity.model_identity,
            response_schema_version=identity.response_schema_version,
            router_version=identity.router_version,
            validation_outcome="schema_valid",
        ),
        provider_event_code="provider_response_valid",
        schema_valid=True,
    )


def _png(width: int = 8, height: int = 8) -> bytes:
    def chunk(kind: bytes, content: bytes) -> bytes:
        return (
            len(content).to_bytes(4, "big")
            + kind
            + content
            + (zlib.crc32(kind + content) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    scanlines = (b"\x00" + b"\x00" * (width * 3)) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            width.to_bytes(4, "big")
            + height.to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00",
        )
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def _text(
    observation_id: str,
    *,
    raw_text: str = "⌀10",
    observation_level: str = "span",
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native_pdf",
        observation_level=observation_level,
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=0,
        bbox_pdf=(0.0, 0.0, 10.0, 10.0),
        bbox_normalized=(0.0, 0.0, 0.1, 0.1),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )


def _visual(
    observation_id: str,
    *,
    associated_text_ids: tuple[str, ...] = ("text-1",),
) -> VisualObservation:
    return VisualObservation(
        observation_id=observation_id,
        source_type="visual",
        observation_level="annotation_context",
        page_index=0,
        bbox_pdf=(0.0, 0.0, 10.0, 10.0),
        bbox_normalized=(0.0, 0.0, 0.1, 0.1),
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256=SHA_A,
        associated_text_observation_ids=associated_text_ids,
    )


def _execution_identity(crop_png: bytes) -> VisualExecutionIdentity:
    canonical_crop = canonicalize_visual_png(crop_png)
    return VisualExecutionIdentity(
        page_index=0,
        content_sha256=SHA_A,
        lineage_sha256=SHA_B,
        budget_sha256=SHA_C,
        observation_member_bindings=(
            ("visual-1", SHA_C),
            ("visual-2", SHA_C),
        ),
        crop_sha256=hashlib.sha256(canonical_crop).hexdigest(),
        member_content_sha256s=(SHA_A, SHA_B),
    )


def test_prt4_adds_exactly_the_four_owned_tables() -> None:
    tables = set(inspect(engine).get_table_names())

    assert tables == PRE_PRT4_TABLES | SYMBOL_TABLES
    assert {
        SymbolRoutingDecisionRecord.__tablename__,
        SymbolEscalationAttemptEventRecord.__tablename__,
        SymbolEscalationOutcomeRecord.__tablename__,
        VisualSymbolCacheEntryRecord.__tablename__,
    } == SYMBOL_TABLES


def test_inventory_task_injects_required_independent_symbol_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_id = uuid.uuid4()
    session = SimpleNamespace(
        get=lambda model, identity: (
            SimpleNamespace(
                recognition_mode="production_uncertainty",
                recognition_router_version=SYMBOL_ROUTER_VERSION,
            )
            if model is Project and identity == project_id
            else None
        ),
        close=lambda: None,
    )

    def session_factory():
        return session

    seen: dict[str, object] = {}

    def candidate_advisor(_settings, _storage, **kwargs):
        seen.update(kwargs)
        return object()

    class Pipeline:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def run(self, *_args) -> str:
            return (
                "automatic-result://"
                "33333333-3333-4333-8333-333333333333"
            )

    class Review:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def create_from_raw(self, _result_id: uuid.UUID) -> None:
            return None

    monkeypatch.setattr(processing_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        processing_tasks,
        "get_settings",
        lambda: Settings(storage_root=tmp_path),
    )
    monkeypatch.setattr(
        processing_tasks,
        "ProcessingPreflight",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        processing_tasks,
        "CandidateAdvisor",
        candidate_advisor,
    )
    monkeypatch.setattr(
        processing_tasks,
        "RuntimeRecognition",
        lambda *_args, **_kwargs: SimpleNamespace(
            build_inventory=lambda *_values: (),
            build_candidate_snapshot=lambda *_values: None,
        ),
    )
    monkeypatch.setattr(processing_tasks, "InventoryPipeline", Pipeline)
    monkeypatch.setattr(processing_tasks, "ReviewService", Review)

    processing_tasks.inventory_project.run(
        str(project_id),
        "asset://projects/source.pdf",
        "process:test-symbol-persistence",
    )

    assert seen["symbol_session_factory"] is session_factory
    assert seen["require_symbol_persistence"] is True


def test_decision_attempt_and_terminal_outcome_are_exact_one_and_immutable(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    decision = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    attempt = evidence.append_attempt(
        project_id=project_id,
        event=_attempt(routing_decision_sha256=_group_sha256(decision)),
    )
    outcome = evidence.record_terminal_outcome(
        project_id=project_id,
        outcome=_outcome(
            routing_decision_sha256=_group_sha256(decision),
            attempt_event_sha256=attempt.event_sha256,
        ),
    )
    db_session.commit()

    replayed_decision = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    replayed_attempt = evidence.append_attempt(
        project_id=project_id,
        event=_attempt(routing_decision_sha256=_group_sha256(decision)),
    )
    replayed_outcome = evidence.record_terminal_outcome(
        project_id=project_id,
        outcome=_outcome(
            routing_decision_sha256=_group_sha256(decision),
            attempt_event_sha256=attempt.event_sha256,
        ),
    )
    db_session.commit()

    assert replayed_decision.id == decision.id
    assert replayed_attempt.id == attempt.id
    assert replayed_outcome.id == outcome.id
    assert db_session.scalar(
        select(func.count()).select_from(SymbolRoutingDecisionRecord)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(SymbolEscalationAttemptEventRecord)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(SymbolEscalationOutcomeRecord)
    ) == 1

    decision.disposition = "locally_resolved"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    persisted_outcome = db_session.get(
        SymbolEscalationOutcomeRecord,
        outcome.id,
    )
    assert persisted_outcome is not None
    db_session.delete(persisted_outcome)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_committed_attempt_history_replays_idempotently_but_closes_at_terminal(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    decision = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    group_sha256 = _group_sha256(decision)
    cache_miss_event = _attempt(
        routing_decision_sha256=group_sha256,
    )
    cache_miss = evidence.append_attempt(
        project_id=project_id,
        event=cache_miss_event,
    )
    db_session.commit()

    evidence = RoutingEvidenceRepository(db_session)
    provider_event = _attempt(
        routing_decision_sha256=group_sha256,
        event_code="provider_response_valid",
        provider_request_id="provider-request-1",
    )
    provider = evidence.append_attempt(
        project_id=project_id,
        event=provider_event,
    )
    db_session.commit()
    canonical_attempts = evidence.canonical_attempt_sha256s(
        project_id=project_id,
        escalation_group_id="group-1",
        routing_decision_sha256=group_sha256,
    )
    assert canonical_attempts == (
        cache_miss.event_sha256,
        provider.event_sha256,
    )

    evidence.record_terminal_outcome(
        project_id=project_id,
        outcome=EscalationOutcome(
            schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
            escalation_group_id="group-1",
            routing_decision_sha256=group_sha256,
            outcome_code="unresolved",
            observation_outcomes=(
                ObservationOutcome(
                    visual_observation_id="visual-1",
                    outcome_code="provider_no_detection",
                ),
            ),
            attempt_event_sha256s=canonical_attempts,
            terminal=True,
        ),
    )
    db_session.commit()

    replayed = evidence.append_attempt(
        project_id=project_id,
        event=provider_event,
    )
    assert replayed.id == provider.id
    with pytest.raises(
        RoutingEvidenceConflict,
        match="follows terminal outcome",
    ):
        evidence.append_attempt(
            project_id=project_id,
            event=_attempt(
                routing_decision_sha256=group_sha256,
                event_code="provider_transport_failure",
                attempt_index=1,
            ),
        )


def test_repository_rejects_partial_group_and_unordered_attempt_claims(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    first = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(observation_id="visual-1", input_sha256=SHA_A),
    )
    second = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=1,
        decision=_decision(observation_id="visual-2", input_sha256=SHA_B),
    )
    group_sha256 = routing_decision_group_sha256(
        (first.decision_sha256, second.decision_sha256)
    )

    with pytest.raises(
        RoutingEvidenceConflict,
        match="group decision hash conflicts",
    ):
        evidence.append_attempt(
            project_id=project_id,
            event=_attempt(
                routing_decision_sha256=first.decision_sha256,
            ),
        )

    cache_miss = evidence.append_attempt(
        project_id=project_id,
        event=_attempt(routing_decision_sha256=group_sha256),
    )
    provider = evidence.append_attempt(
        project_id=project_id,
        event=_attempt(
            routing_decision_sha256=group_sha256,
            event_code="provider_response_valid",
            provider_request_id="provider-request-1",
        ),
    )
    incomplete_observations = EscalationOutcome(
        schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
        escalation_group_id="group-1",
        routing_decision_sha256=group_sha256,
        outcome_code="unresolved",
        observation_outcomes=(
            ObservationOutcome(
                visual_observation_id="visual-1",
                outcome_code="provider_no_detection",
            ),
        ),
        attempt_event_sha256s=(
            cache_miss.event_sha256,
            provider.event_sha256,
        ),
        terminal=True,
    )
    with pytest.raises(
        RoutingEvidenceConflict,
        match="observation set conflicts",
    ):
        evidence.record_terminal_outcome(
            project_id=project_id,
            outcome=incomplete_observations,
        )

    wrong_observation_order = replace(
        incomplete_observations,
        observation_outcomes=(
            ObservationOutcome(
                visual_observation_id="visual-2",
                outcome_code="provider_no_detection",
            ),
            ObservationOutcome(
                visual_observation_id="visual-1",
                outcome_code="provider_no_detection",
            ),
        ),
    )
    with pytest.raises(
        RoutingEvidenceConflict,
        match="observation set conflicts",
    ):
        evidence.record_terminal_outcome(
            project_id=project_id,
            outcome=wrong_observation_order,
        )

    reversed_attempts = replace(
        incomplete_observations,
        observation_outcomes=(
            ObservationOutcome(
                visual_observation_id="visual-1",
                outcome_code="provider_no_detection",
            ),
            ObservationOutcome(
                visual_observation_id="visual-2",
                outcome_code="provider_no_detection",
            ),
        ),
        attempt_event_sha256s=(
            provider.event_sha256,
            cache_miss.event_sha256,
        ),
    )
    with pytest.raises(
        RoutingEvidenceConflict,
        match="attempt set conflicts",
    ):
        evidence.record_terminal_outcome(
            project_id=project_id,
            outcome=reversed_attempts,
        )


def test_group_hash_follows_persisted_reading_order_not_lexical_ids(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    reading_first = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-reading-order",
        escalation_group_member_index=0,
        decision=_decision(
            observation_id="visual-ff",
            input_sha256=SHA_A,
        ),
    )
    reading_second = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-reading-order",
        escalation_group_member_index=1,
        decision=_decision(
            observation_id="visual-00",
            input_sha256=SHA_B,
        ),
    )
    ordered_hash = routing_decision_group_sha256(
        (
            reading_first.decision_sha256,
            reading_second.decision_sha256,
        )
    )
    lexical_hash = routing_decision_group_sha256(
        (
            reading_second.decision_sha256,
            reading_first.decision_sha256,
        )
    )

    assert ordered_hash != lexical_hash
    evidence.append_attempt(
        project_id=project_id,
        event=EscalationAttemptEvent(
            schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION,
            escalation_group_id="group-reading-order",
            routing_decision_sha256=ordered_hash,
            attempt_index=0,
            event_code="cache_miss",
            cache_entry_id=None,
            provider_request_id=None,
        ),
    )
    with pytest.raises(
        RoutingEvidenceConflict,
        match="group decision hash conflicts",
    ):
        evidence.append_attempt(
            project_id=project_id,
            event=EscalationAttemptEvent(
                schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION,
                escalation_group_id="group-reading-order",
                routing_decision_sha256=lexical_hash,
                attempt_index=1,
                event_code="provider_transport_failure",
                cache_entry_id=None,
                provider_request_id=None,
            ),
        )


def test_conflicting_replay_fails_closed_without_rewriting_evidence(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    original = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    db_session.commit()

    with pytest.raises(RoutingEvidenceConflict):
        evidence.record_decision(
            project_id=project_id,
            escalation_group_id="group-1",
            escalation_group_member_index=0,
            decision=_decision(input_sha256=SHA_B),
        )
    db_session.rollback()

    persisted = db_session.get(SymbolRoutingDecisionRecord, original.id)
    assert persisted is not None
    assert persisted.input_sha256 == SHA_A
    assert db_session.scalar(
        select(func.count()).select_from(SymbolRoutingDecisionRecord)
    ) == 1


def test_cache_namespace_is_project_local_even_when_content_key_matches(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            Project(id=PROJECT_A, state=ProjectState.PROCESSING),
            Project(id=PROJECT_B, state=ProjectState.PROCESSING),
        ]
    )
    db_session.commit()
    cache = VisualSymbolCache(db_session)
    entry = _cache_entry(producer_project_id=PROJECT_A)

    stored = cache.store_if_absent(project_id=PROJECT_A, entry=entry)
    db_session.commit()

    assert stored.entry.identity.sha256 == _identity().sha256
    assert cache.lookup(project_id=PROJECT_B, identity=_identity()).hit is False
    assert (
        cache.lookup(project_id=PROJECT_B, identity=_identity()).reason_code
        == "cache_miss"
    )
    with pytest.raises(CacheWriteRejected):
        cache.store_if_absent(project_id=PROJECT_B, entry=entry)


def test_lookup_quarantines_detached_embedded_identity_and_audits_miss(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    expected_identity = _identity()
    detached_identity = replace(
        expected_identity,
        associated_text_sha256="d" * 64,
    )
    detached_entry = build_cache_entry(
        identity=detached_identity,
        response=_response(),
        provenance=SymbolCacheProvenance(
            identity_sha256=detached_identity.sha256,
            producer_project_id=str(project_id),
            producer_request_id="provider-request-detached",
            producer_call_record_ref=(
                f"asset://projects/{project_id}/provider-calls/"
                "qwen-symbol/provider-request-detached.json"
            ),
            response_sha256=_response_sha256(),
            created_at=datetime(2026, 7, 30, tzinfo=UTC),
            model_identity=detached_identity.model_identity,
            response_schema_version=(
                detached_identity.response_schema_version
            ),
            router_version=detached_identity.router_version,
            validation_outcome="schema_valid",
        ),
        provider_event_code="provider_response_valid",
        schema_valid=True,
    )
    assert detached_entry.provenance is not None
    provenance = asdict(detached_entry.provenance)
    provenance["created_at"] = (
        detached_entry.provenance.created_at.isoformat()
    )
    record = VisualSymbolCacheEntryRecord(
        project_id=project_id,
        cache_key=expected_identity.sha256,
        cache_schema_version="visual-symbol-cache-entry/1",
        identity_sha256=detached_identity.sha256,
        identity=asdict(detached_identity),
        response=detached_entry.response,
        response_sha256=detached_entry.response_sha256,
        producer_request_id=(
            detached_entry.provenance.producer_request_id
        ),
        producer_call_record_ref=(
            detached_entry.provenance.producer_call_record_ref
        ),
        producer_provenance=provenance,
        provenance_sha256=hashlib.sha256(
            json.dumps(
                provenance,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )
    db_session.add(record)
    evidence = RoutingEvidenceRepository(db_session)
    decision = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    db_session.commit()

    lookup = VisualSymbolCache(db_session).lookup(
        project_id=project_id,
        identity=expected_identity,
        consumer=CacheConsumer(
            escalation_group_id="group-1",
            routing_decision_sha256=_group_sha256(decision),
            attempt_index=0,
        ),
        evidence=evidence,
    )

    assert lookup.hit is False
    assert lookup.reason_code == "cache_provenance_invalid"
    assert lookup.quarantine is True
    assert lookup.entry is not None
    attempt = db_session.scalar(
        select(SymbolEscalationAttemptEventRecord).where(
            SymbolEscalationAttemptEventRecord.project_id == project_id,
            SymbolEscalationAttemptEventRecord.event_code
            == "cache_provenance_invalid",
        )
    )
    assert attempt is not None
    assert attempt.cache_entry_id == record.id


def test_concurrent_same_key_writers_leave_one_first_writer_record(
    committed_project_id: uuid.UUID,
) -> None:
    first_entry = _cache_entry(producer_project_id=committed_project_id)
    second_entry = replace(
        first_entry,
        provenance=replace(
            first_entry.provenance,
            producer_request_id="provider-request-2",
        ),
    )
    start = Barrier(2)

    def write(
        entry: VisualSymbolCacheEntry,
    ) -> tuple[bool, uuid.UUID, str]:
        with SessionLocal() as session:
            cache = VisualSymbolCache(session)
            start.wait()
            stored = cache.store_if_absent(
                project_id=committed_project_id,
                entry=entry,
            )
            session.commit()
            assert stored.entry.id is not None
            assert stored.entry.provenance is not None
            return (
                stored.inserted,
                stored.entry.id,
                stored.entry.provenance.producer_request_id,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(write, (first_entry, second_entry)))

    assert sorted(inserted for inserted, _, _ in results) == [False, True]
    assert len({entry_id for _, entry_id, _ in results}) == 1
    assert len({producer for _, _, producer in results}) == 1
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count())
            .select_from(VisualSymbolCacheEntryRecord)
            .where(
                VisualSymbolCacheEntryRecord.project_id
                == committed_project_id
            )
        ) == 1


def test_valid_hit_records_current_project_consumer_attempt(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    decision = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    cache = VisualSymbolCache(db_session)
    cache.store_if_absent(
        project_id=project_id,
        entry=_cache_entry(producer_project_id=project_id),
    )
    db_session.commit()

    lookup = cache.lookup(
        project_id=project_id,
        identity=_identity(),
        consumer=CacheConsumer(
            escalation_group_id="group-1",
            routing_decision_sha256=_group_sha256(decision),
            attempt_index=0,
        ),
        evidence=evidence,
    )
    db_session.commit()

    assert lookup.hit is True
    attempt = db_session.scalar(
        select(SymbolEscalationAttemptEventRecord).where(
            SymbolEscalationAttemptEventRecord.project_id == project_id,
            SymbolEscalationAttemptEventRecord.event_code
            == "cache_hit_valid",
        )
    )
    assert attempt is not None
    assert attempt.cache_entry_id == lookup.entry.id
    assert attempt.project_id == project_id


def test_attempt_cache_entry_must_belong_to_consumer_project(
    db_session: Session,
) -> None:
    consumer_project_id = uuid.uuid4()
    producer_project_id = uuid.uuid4()
    db_session.add_all(
        [
            Project(
                id=consumer_project_id,
                state=ProjectState.PROCESSING,
            ),
            Project(
                id=producer_project_id,
                state=ProjectState.PROCESSING,
            ),
        ]
    )
    db_session.commit()
    evidence = RoutingEvidenceRepository(db_session)
    decision = evidence.record_decision(
        project_id=consumer_project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    stored = VisualSymbolCache(db_session).store_if_absent(
        project_id=producer_project_id,
        entry=_cache_entry(producer_project_id=producer_project_id),
    )
    assert stored.entry.id is not None

    with pytest.raises(
        RoutingEvidenceConflict,
        match="cache attempt project scope conflicts",
    ):
        evidence.append_attempt(
            project_id=consumer_project_id,
            event=_attempt(
                routing_decision_sha256=_group_sha256(decision),
                event_code="cache_hit_valid",
                cache_entry_id=stored.entry.id,
            ),
        )


def test_invalid_persisted_provenance_is_quarantined_and_audited_as_miss(
    db_session: Session,
    project_id: uuid.UUID,
) -> None:
    evidence = RoutingEvidenceRepository(db_session)
    decision = evidence.record_decision(
        project_id=project_id,
        escalation_group_id="group-1",
        escalation_group_member_index=0,
        decision=_decision(),
    )
    identity = _identity()
    producer_provenance = {
        "identity_sha256": SHA_B,
        "producer_project_id": str(project_id),
        "producer_request_id": "provider-request-corrupt",
        "producer_call_record_ref": (
            f"asset://projects/{project_id}/provider-calls/"
            "qwen-symbol/provider-request-corrupt.json"
        ),
        "response_sha256": _response_sha256(),
        "created_at": datetime(2026, 7, 30, tzinfo=UTC).isoformat(),
        "model_identity": identity.model_identity,
        "response_schema_version": identity.response_schema_version,
        "router_version": identity.router_version,
        "validation_outcome": "schema_valid",
    }
    invalid_entry = VisualSymbolCacheEntryRecord(
        project_id=project_id,
        cache_key=identity.sha256,
        cache_schema_version="visual-symbol-cache-entry/1",
        identity_sha256=identity.sha256,
        identity=asdict(identity),
        response=_response(),
        response_sha256=_response_sha256(),
        producer_request_id="provider-request-corrupt",
        producer_call_record_ref=(
            producer_provenance["producer_call_record_ref"]
        ),
        producer_provenance=producer_provenance,
        provenance_sha256=hashlib.sha256(
            json.dumps(
                producer_provenance,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )
    db_session.add(invalid_entry)
    db_session.commit()

    cache = VisualSymbolCache(db_session)
    lookup = cache.lookup(
        project_id=project_id,
        identity=identity,
        consumer=CacheConsumer(
            escalation_group_id="group-1",
            routing_decision_sha256=_group_sha256(decision),
            attempt_index=0,
        ),
        evidence=evidence,
    )
    db_session.commit()

    assert lookup.hit is False
    assert lookup.reason_code == "cache_provenance_invalid"
    assert lookup.quarantine is True
    assert lookup.response is None
    attempt = db_session.scalar(
        select(SymbolEscalationAttemptEventRecord).where(
            SymbolEscalationAttemptEventRecord.project_id == project_id,
            SymbolEscalationAttemptEventRecord.event_code
            == "cache_provenance_invalid",
        )
    )
    assert attempt is not None
    assert attempt.cache_entry_id == invalid_entry.id
    assert attempt.project_id == project_id
    with pytest.raises(InvalidCacheWinner):
        cache.store_if_absent(
            project_id=project_id,
            entry=_cache_entry(producer_project_id=project_id),
        )
