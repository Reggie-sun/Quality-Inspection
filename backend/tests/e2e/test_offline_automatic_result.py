from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.coverage import CoverageEntry
from app.candidates.models import AutomaticResult
from app.db import engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.pdf.schemas import PageInventory, TextObservation
from app.processing.automatic_result import (
    CandidateSnapshot,
    CoverageBlocking,
    candidate_snapshot_from_inventory,
)
from app.processing.pipeline import InventoryPipeline
from app.projects.models import Project
from app.projects.state import ProjectState
from app.providers.qwen_vl import parse_candidate_json
from app.providers.tencent_ocr import normalize_response
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


ROOT = Path(__file__).resolve().parents[3]
QWEN_FIXTURE = (
    ROOT
    / ".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json"
)
TENCENT_FIXTURE = (
    ROOT
    / ".agent/harness/fixtures/providers/tencent-ocr/general-accurate-v1.json"
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
) -> StoredFile:
    content = b"offline-provider-fixture-pdf"
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
    tencent = json.loads(TENCENT_FIXTURE.read_text(encoding="utf-8"))["payload"]
    advisor_payload = parse_candidate_json(qwen["content"])
    ocr_result = normalize_response(tencent)
    assert advisor_payload["raw_text"] == ocr_result.observations[0].raw_text
    polygon = ocr_result.observations[0].polygon
    observation = TextObservation(
        observation_id="ocr-observation-1",
        source_type="ocr",
        observation_level="region",
        raw_text=ocr_result.observations[0].raw_text,
        normalized_text=ocr_result.observations[0].raw_text,
        page_index=0,
        bbox_pdf=(
            min(point[0] for point in polygon),
            min(point[1] for point in polygon),
            max(point[0] for point in polygon),
            max(point[1] for point in polygon),
        ),
        bbox_normalized=(0.12, 0.14, 0.72, 0.34),
        direction=(1.0, 0.0),
        direction_angle_degrees=ocr_result.observations[0].angle,
        confidence=ocr_result.observations[0].confidence,
    )
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    def fixture_snapshot(pages):
        return replace(
            candidate_snapshot_from_inventory(pages),
            provider_call_ids=(ocr_result.request_id, qwen["request_id"]),
        )

    pipeline = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=lambda _path: (_page(observation),),
        candidate_snapshot_builder=fixture_snapshot,
    )
    task_key = "process:offline-fixtures"

    first_ref = pipeline.run(str(project.id), source_file.resource_ref, task_key)
    second_ref = pipeline.run(str(project.id), source_file.resource_ref, task_key)

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
    assert result.provider_call_ids == [
        "fixture-request-id",
        "fixture-qwen-request-id",
    ]
    assert result.coverage["coverage_checked"] is True
    assert result.coverage["blocking_count"] == 0
    assert result.candidates[0]["payload"]["item_type"] == "thread"
    assert result.candidates[0]["source_location_ids"] == [
        "ocr-observation-1"
    ]
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
