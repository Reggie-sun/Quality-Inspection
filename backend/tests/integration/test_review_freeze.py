from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.models import ReviewedResult
from app.review.service import FreezeBlocked, ItemsFrozen, ReviewService
from app.storage.models import StoredFile


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
def working_copy(db_session: Session) -> ReviewWorkingCopy:
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
    db_session.add_all(
        [
            Project(id=project_id, state=ProjectState.READY_FOR_EDIT),
            StoredFile(
                id=source_file_id,
                resource_ref=f"asset://tests/{project_id}/source.pdf",
                sha256="0" * 64,
                size_bytes=1,
                mime_type="application/pdf",
            ),
            LogicalJob(
                id=job_id,
                project_id=str(project_id),
                logical_task_key=f"review-freeze:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{result_id}",
            ),
        ]
    )
    db_session.flush()
    db_session.add(
        AutomaticResult(
            id=result_id,
            project_id=project_id,
            source_file_id=source_file_id,
            logical_job_id=job_id,
            inventory_ref=f"asset://tests/{project_id}/inventory.json",
            candidates=[
                {
                    "candidate_id": "i1",
                    "payload": {
                        "candidate_id": "i1",
                        "item_type": "thread",
                        "raw_text": "M6",
                        "normalized_text": "M6",
                        "coordinates": [1, 2, 3, 4],
                        "scope": "local_feature",
                        "balloon_required": True,
                        "requires_confirmation": False,
                    },
                    "source_location_ids": ["s1"],
                }
            ],
            coverage={
                "blocking_count": 0,
                "review_required_count": 0,
                "coverage_checked": True,
                "blocking_observation_ids": [],
                "entries": [],
                "relations": [],
            },
            provider_call_ids=[],
            schema_version="automatic-result/1",
        )
    )
    db_session.commit()
    service = ReviewService(db_session)
    working = service.create_from_raw(result_id)
    acquire_lock(db_session, project_id, "quality-1")
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "M6",
            "inspection_standard": "6H",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
            "remarks": "",
        },
    )
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "fixture",
            "drawing_number": "FREEZE-001",
            "material": "steel",
            "revision": "A",
        },
    )
    return working


def test_unresolved_confirmation_blocks_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    """PRT-5 unresolved evidence remains the freeze Veto."""
    items = copy.deepcopy(working_copy.items)
    items[0]["requires_confirmation"] = True
    working_copy.items = items
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.code == "unresolved_confirmation"
    assert error.value.blockers == ("unresolved_confirmation",)


def test_legacy_source_only_confirmation_is_normalized_before_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-only",
            "source_location_id": "source-only",
            "candidate_id": None,
            "disposition": "ambiguous",
            "coordinates": [5, 6, 7, 8],
            "requires_confirmation": True,
        }
    ]
    coverage["review_required_count"] = 1
    working_copy.coverage = coverage
    db_session.commit()

    frozen = ReviewService(db_session).freeze_items(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
    )

    assert frozen.items_frozen_at is not None
    assert frozen.coverage["review_required_count"] == 0
    assert frozen.coverage["entries"] == [
            {
                "observation_id": "source-only",
                "source_location_id": "source-only",
                "candidate_id": None,
                "disposition": "non_inspection",
            "coordinates": [5, 6, 7, 8],
            "requires_confirmation": False,
            "confirmation_accepted": False,
            "resolution_source": "system_default",
            "resolution_rule_version": "review-source-default/1",
        }
    ]


@pytest.mark.parametrize(
    "malformed_entry",
    [
        {
            "observation_id": "missing-candidate-id",
            "source_location_id": "missing-candidate-id",
            "disposition": "ambiguous",
            "coordinates": [1, 2, 3, 4],
            "requires_confirmation": True,
        },
        {
            "observation_id": "string-confirmation",
            "source_location_id": "string-confirmation",
            "candidate_id": None,
            "disposition": "ambiguous",
            "coordinates": [5, 6, 7, 8],
            "requires_confirmation": "true",
        },
    ],
)
def test_malformed_legacy_coverage_blocks_freeze_without_persistence(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
    malformed_entry: dict[str, object],
) -> None:
    malformed_coverage = {
        "blocking_count": 0,
        "review_required_count": 1,
        "entries": [malformed_entry],
    }
    working_copy.coverage = copy.deepcopy(malformed_coverage)
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.blockers == ("coverage_blocking",)
    db_session.refresh(working_copy)
    assert working_copy.items_frozen_at is None
    assert working_copy.coverage == malformed_coverage


def test_optional_material_does_not_block_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    metadata = copy.deepcopy(working_copy.sip_metadata)
    metadata["material"] = ""
    working_copy.sip_metadata = metadata
    db_session.commit()

    frozen = ReviewService(db_session).freeze_items(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
    )

    assert frozen.items_frozen_at is not None
    assert frozen.sip_metadata["material"] == ""


def test_unconfirmed_technical_requirement_suggestion_blocks_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    items = copy.deepcopy(working_copy.items)
    items[0]["sip_detail_fields_confirmed"] = False
    items[0]["sip_suggestion_provenance"] = {
        "inspection_standard": {
            "requirement_id": "technical-requirement-5",
            "rule_version": "technical-requirement/1",
        }
    }
    working_copy.items = items
    db_session.commit()

    assert ReviewService._sip_confirmation_blockers(
        working_copy.items,
        working_copy.sip_metadata,
    ) == ["sip_detail_fields_unconfirmed"]
    with pytest.raises(FreezeBlocked, match="unresolved_confirmation"):
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )


def test_generated_complete_sip_row_does_not_need_manual_confirmation(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for field in (
        "inspection_item",
        "inspection_standard",
        "inspection_method",
        "key_dimension",
        "inspection_role",
        "source_page",
        "remarks",
        "sip_detail_fields_confirmed",
    ):
        items[0].pop(field, None)
    items[0]["page_index"] = 0
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    service = ReviewService(db_session)

    generated = service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )
    frozen = service.freeze_items(
        generated.id,
        expected_version=generated.version,
        operator_id="quality-1",
    )

    assert generated.items[0]["sip_detail_fields_confirmed"] is True
    assert generated.items[0]["sip_mapping_exceptions"] == []
    assert frozen.items_frozen_at is not None


def test_generated_exception_remains_a_freeze_blocker(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for field in (
        "inspection_item",
        "inspection_standard",
        "inspection_method",
        "key_dimension",
        "inspection_role",
        "source_page",
        "remarks",
        "sip_detail_fields_confirmed",
    ):
        items[0].pop(field, None)
    items[0]["item_type"] = "composite"
    items[0]["page_index"] = 0
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    service = ReviewService(db_session)

    generated = service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )

    assert generated.items[0]["sip_mapping_exceptions"] == [
        "composite_method_required"
    ]
    with pytest.raises(FreezeBlocked) as error:
        service.freeze_items(
            generated.id,
            expected_version=generated.version,
            operator_id="quality-1",
        )
    assert error.value.blockers == ("unresolved_confirmation",)


def test_freeze_reports_only_the_three_exact_blockers(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    items = copy.deepcopy(working_copy.items)
    items[0]["requires_confirmation"] = True
    items[0]["balloon_required"] = None
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["blocking_count"] = 1
    working_copy.items = items
    working_copy.coverage = coverage
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.blockers == (
        "coverage_blocking",
        "unresolved_confirmation",
        "balloon_required_unconfirmed",
    )


def test_item_set_freeze_preserves_editing_without_reviewed_result(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    before_version = working_copy.version
    service = ReviewService(db_session)

    frozen = service.freeze_items(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
    )

    project = db_session.get(Project, working_copy.project_id)
    assert frozen.items_frozen_at is not None
    assert frozen.items_frozen_by == "quality-1"
    assert frozen.items_frozen_version == before_version
    assert frozen.version == before_version
    assert project is not None
    assert project.state == ProjectState.EDITING
    assert service.reviewed_result_for(working_copy.project_id) is None
    assert db_session.scalar(
        select(func.count()).select_from(ReviewedResult).where(
            ReviewedResult.project_id == working_copy.project_id
        )
    ) == 0


def test_item_set_freeze_rejects_later_semantic_commands(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    service = ReviewService(db_session)
    frozen = service.freeze_items(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
    )

    with pytest.raises(ItemsFrozen):
        service.apply(
            working_copy.id,
            expected_version=frozen.version,
            operator_id="quality-1",
            command={"type": "keep", "item_id": "i1"},
        )
