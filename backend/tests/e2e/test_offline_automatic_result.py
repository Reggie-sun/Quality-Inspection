from __future__ import annotations

import json
import socket
import uuid
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.advisor import CandidateAdvisor
from app.candidates.coverage import CoverageEntry
from app.candidates.confidence import CandidateSourceSignal
from app.candidates.models import AutomaticResult
from app.candidates.duplicates import DuplicateRelation
from app.config import Settings
from app.db import engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.pdf.schemas import PageInventory, TextObservation
from app.processing.automatic_result import (
    CandidateSnapshot,
    CoverageBlocking,
    candidate_snapshot_from_inventory,
)
from app.processing.pipeline import ConfidencePolicyError, InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.projects.models import Project
from app.projects.state import ProjectState
from app.providers.base import VisionResult
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


ROOT = Path(__file__).resolve().parents[3]
QWEN_FIXTURE = (
    ROOT
    / ".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json"
)
class PassingPreflight:
    def check(self) -> None:
        return None


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


def _page(observation: TextObservation) -> PageInventory:
    return PageInventory(
        page_index=0,
        width=100.0,
        height=100.0,
        rotation=0,
        page_type="vector",
        processing_route="native",
        support_level="supported",
        review_required=False,
        unsupported_reason=None,
        classification_confidence=1.0,
        classification_rule_version="fixture/1",
        classification_evidence={"native_char_count": len(observation.raw_text)},
        pdf_to_render_matrix=(1, 0, 0, 1, 0, 0),
        render_to_pdf_matrix=(1, 0, 0, 1, 0, 0),
        observations=(observation,),
    )


def _source(
    db_session: Session,
    storage: LocalFileStorage,
    project: Project,
    *,
    raw_text: str = "M6",
) -> StoredFile:
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    page.insert_text((20.0, 30.0), raw_text)
    content = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    stored = storage.write_verified(
        f"projects/{project.id}/source.pdf",
        content,
        sha256(content).hexdigest(),
    )
    source_file = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    db_session.add_all([project, source_file])
    db_session.commit()
    return source_file


def test_candidate_snapshot_source_signals_default_and_preserve() -> None:
    empty = CandidateSnapshot(
        candidates=(),
        coverage_entries=(),
        expected_observation_ids=(),
        duplicate_relations=(),
    )
    signal = CandidateSourceSignal(
        source_location_id="observation-1",
        source_type="native",
        normalized_value=Decimal("1"),
    )
    populated = CandidateSnapshot(
        candidates=(),
        coverage_entries=(),
        expected_observation_ids=(),
        duplicate_relations=(),
        source_signals=(signal,),
    )

    assert empty.source_signals == ()
    assert populated.source_signals == (signal,)
    assert replace(
        populated,
        provider_call_ids=("provider-call-1",),
    ).source_signals == (signal,)


@pytest.mark.parametrize("text", ("DRAFT", "DRAWING", "GENERAL"))
def test_plain_text_is_not_misclassified_as_roughness(text: str) -> None:
    """ITEM-003: an embedded 'ra' substring is not a roughness signal."""
    observation = TextObservation(
        observation_id=f"plain-{text.lower()}",
        source_type="native",
        observation_level="line",
        raw_text=text,
        normalized_text=text,
        page_index=0,
        bbox_pdf=(1, 2, 3, 4),
        bbox_normalized=(0.01, 0.02, 0.03, 0.04),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert snapshot.candidates == ()
    assert len(snapshot.coverage_entries) == 1
    assert snapshot.coverage_entries[0].disposition == "ambiguous"


def test_offline_provider_fixtures_freeze_one_automatic_result(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """D3-T2: sanitized fixtures yield one coverage-checked immutable result."""
    qwen = json.loads(QWEN_FIXTURE.read_text(encoding="utf-8"))["payload"]
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(
        db_session,
        storage,
        project,
        raw_text="Ra 3.2",
    )
    provider_network_connections = 0

    class FixtureVisionProvider:
        @staticmethod
        def review_candidate(_image: bytes, _prompt: str) -> VisionResult:
            return VisionResult(
                request_id=qwen["request_id"],
                payload={
                    "schema_version": "candidate-review/1",
                    "raw_text": "Ra 3.2",
                    "item_type": "roughness",
                    "normalized_text": "Ra 3.2",
                    "requires_confirmation": True,
                },
                usage=dict(qwen["usage"]),
            )

    def forbidden_ocr_factory(_settings: Settings):
        raise AssertionError("native fixture must not construct OCR Provider")

    advisor = CandidateAdvisor(
        Settings(storage_root=storage.root),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: FixtureVisionProvider(),
    )
    recognition = RuntimeRecognition(
        Settings(storage_root=storage.root),
        provider_factory=forbidden_ocr_factory,
        advisor=advisor,
    )

    def block_network(*_args, **_kwargs):
        nonlocal provider_network_connections
        provider_network_connections += 1
        raise AssertionError("offline Provider fixture attempted network access")

    pipeline = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=recognition.build_inventory,
        candidate_snapshot_builder=recognition.build_candidate_snapshot,
    )
    task_key = "process:offline-fixtures"

    with (
        patch.object(socket, "socket", new=block_network),
        patch.object(socket, "create_connection", new=block_network),
        patch.object(socket, "getaddrinfo", new=block_network),
    ):
        first_ref = pipeline.run(
            str(project.id),
            source_file.resource_ref,
            task_key,
        )
        second_ref = pipeline.run(
            str(project.id),
            source_file.resource_ref,
            task_key,
        )

    result = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert result is not None
    assert first_ref == second_ref == f"automatic-result://{result.id}"
    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 1
    assert result.source_file_id == source_file.id
    assert result.provider_call_ids == ["fixture-qwen-request-id"]
    assert result.coverage["coverage_checked"] is True
    assert result.coverage["blocking_count"] == 0
    assert result.candidates[0]["payload"]["coarse_type"] == "roughness"
    assert result.candidates[0]["source_location_ids"]
    assert result.candidates[0]["advisor_review"]["validated"] is True
    assert provider_network_connections == 0
    assert storage.resolve_resource_ref(result.inventory_ref).is_file()
    assert db_session.get(Project, project.id).state == ProjectState.READY_FOR_EDIT
    job = db_session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == str(project.id),
            LogicalJob.logical_task_key == task_key,
        )
    )
    assert job is not None
    assert job.status == "succeeded"
    assert job.result_ref == first_ref


def test_coverage_blocking_creates_no_raw_result_and_records_error(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """CAND-005: coverage veto persists a structured error before raw insert."""
    observation = TextObservation(
        observation_id="observation-1",
        source_type="native",
        observation_level="line",
        raw_text="M6",
        normalized_text="M6",
        page_index=0,
        bbox_pdf=(1, 2, 3, 4),
        bbox_normalized=(0.01, 0.02, 0.03, 0.04),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)
    blocking_snapshot = CandidateSnapshot(
        candidates=(),
        coverage_entries=(
            CoverageEntry(
                "observation-1",
                "ambiguous",
                None,
                (1, 2, 3, 4),
            ),
        ),
        expected_observation_ids=("observation-1",),
        duplicate_relations=(),
    )

    with pytest.raises(CoverageBlocking, match="coverage_blocking"):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (_page(observation),),
            candidate_snapshot_builder=lambda _pages: blocking_snapshot,
        ).run(
            str(project.id),
            source_file.resource_ref,
            "process:coverage-blocking",
        )

    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert error.code == "coverage_blocking"
    assert error.stage == "coverage"
    assert error.severity == "blocking"
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED


def _linear_candidate(
    candidate_id: str,
    source_location_id: str,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "payload": {
            "candidate_id": candidate_id,
            "item_type": "linear_dimension",
            "raw_text": "10",
            "normalized_text": "10",
            "coordinates": [1, 2, 11, 12],
            "scope": "local_feature",
            "nominal": "10",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": [source_location_id],
        "source_truth_preserved": True,
    }


def test_pipeline_freezes_mixed_confidence_decisions_after_coverage(
    db_session: Session,
    tmp_path: Path,
) -> None:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)
    candidates = tuple(
        _linear_candidate(f"candidate-{index}", f"source-{index}")
        for index in range(1, 6)
    )
    coverage_entries = tuple(
        CoverageEntry(
            observation_id=f"source-{index}",
            disposition="ambiguous" if index == 4 else "candidate",
            source_location_id=f"source-{index}",
            coordinates=(1, 2, 11, 12),
            candidate_id=f"candidate-{index}",
            requires_confirmation=index == 4,
        )
        for index in range(1, 6)
    )
    snapshot = CandidateSnapshot(
        candidates=candidates,
        coverage_entries=coverage_entries,
        expected_observation_ids=tuple(
            f"source-{index}" for index in range(1, 6)
        ),
        duplicate_relations=(
            DuplicateRelation(
                left_candidate_id="candidate-5",
                right_candidate_id="other-candidate",
            ),
        ),
        source_signals=tuple(
            CandidateSourceSignal(
                source_location_id=f"source-{index}",
                source_type="native",
                normalized_value=value,
            )
            for index, value in enumerate(
                (
                    Decimal("1"),
                    Decimal("0.80"),
                    Decimal("0.50"),
                    Decimal("1"),
                    Decimal("1"),
                ),
                start=1,
            )
        ),
    )
    observation = TextObservation(
        observation_id="inventory-source",
        source_type="native",
        observation_level="line",
        raw_text="10",
        normalized_text="10",
        page_index=0,
        bbox_pdf=(1, 2, 11, 12),
        bbox_normalized=(0.01, 0.02, 0.11, 0.12),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )

    result_ref = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=lambda _path: (_page(observation),),
        candidate_snapshot_builder=lambda _pages: snapshot,
    ).run(
        str(project.id),
        source_file.resource_ref,
        "process:mixed-confidence",
    )

    result = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert result is not None
    assert result_ref == f"automatic-result://{result.id}"
    assert result.schema_version == "automatic-result/2"
    decisions = [
        candidate["confidence_decision"] for candidate in result.candidates
    ]
    assert [decision["band"] for decision in decisions] == [
        "high",
        "medium",
        "low",
        "low",
        "low",
    ]
    assert all(
        set(candidate).intersection({"confidence_decision"})
        == {"confidence_decision"}
        for candidate in result.candidates
    )
    assert (
        decisions[0]["review_disposition"] == "auto_accepted"
        and decisions[1]["review_disposition"] == "review_required"
    )
    assert "ambiguous_source" in decisions[3]["evidence_codes"]
    assert "possible_duplicate" in decisions[4]["evidence_codes"]


def test_confidence_policy_failure_is_structured_and_atomic(
    db_session: Session,
    tmp_path: Path,
) -> None:
    class ExplodingPolicy:
        def evaluate_candidates(self, *_args, **_kwargs):
            raise ValueError("private policy implementation detail")

    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    with pytest.raises(ConfidencePolicyError):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (),
            confidence_policy=ExplodingPolicy(),
        ).run(
            str(project.id),
            source_file.resource_ref,
            "process:confidence-policy-failure",
        )

    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert error.code == "confidence_policy_failed"
    assert error.stage == "confidence_policy"
    assert error.cause_category == "processing_defect"
    assert error.message == "Confidence policy evaluation failed"
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED


def test_unknown_confidence_policy_version_is_rejected_before_persistence(
    db_session: Session,
    tmp_path: Path,
) -> None:
    candidate = _linear_candidate("candidate-1", "source-1")

    class UnknownVersionPolicy:
        def evaluate_candidates(self, *_args, **_kwargs):
            decided = dict(candidate)
            decided["confidence_decision"] = {
                "band": "high",
                "review_disposition": "auto_accepted",
                "policy_version": "candidate-confidence/unknown",
                "evidence_codes": ["typed_schema_complete"],
            }
            return (decided,)

    snapshot = CandidateSnapshot(
        candidates=(candidate,),
        coverage_entries=(
            CoverageEntry(
                observation_id="source-1",
                disposition="candidate",
                source_location_id="source-1",
                coordinates=(1, 2, 11, 12),
                candidate_id="candidate-1",
            ),
        ),
        expected_observation_ids=("source-1",),
        duplicate_relations=(),
    )
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    with pytest.raises(ConfidencePolicyError):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (),
            candidate_snapshot_builder=lambda _pages: snapshot,
            confidence_policy=UnknownVersionPolicy(),
        ).run(
            str(project.id),
            source_file.resource_ref,
            "process:unknown-confidence-policy",
        )

    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert (
        error.code,
        error.stage,
        error.cause_category,
    ) == (
        "confidence_policy_failed",
        "confidence_policy",
        "processing_defect",
    )


@pytest.mark.parametrize(
    "invalid_candidates",
    (
        None,
        "candidate-1",
        b"candidate-1",
        bytearray(b"candidate-1"),
        {"candidate_id": "candidate-1"},
    ),
    ids=("none", "string", "bytes", "bytearray", "mapping"),
)
def test_invalid_confidence_candidate_container_is_structured_and_atomic(
    db_session: Session,
    tmp_path: Path,
    invalid_candidates: object,
) -> None:
    class InvalidContainerPolicy:
        def evaluate_candidates(self, *_args, **_kwargs):
            return invalid_candidates

    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    with pytest.raises(ConfidencePolicyError) as failure:
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (),
            confidence_policy=InvalidContainerPolicy(),
        ).run(
            str(project.id),
            source_file.resource_ref,
            f"process:invalid-confidence-container:{type(invalid_candidates).__name__}",
        )

    assert str(failure.value.__cause__) == (
        "automatic-result/2 candidates must be a non-string sequence"
    )
    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert (
        error.code,
        error.stage,
        error.cause_category,
    ) == (
        "confidence_policy_failed",
        "confidence_policy",
        "processing_defect",
    )
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED
