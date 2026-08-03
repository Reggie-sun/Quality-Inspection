from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.candidates.geometric_tolerance import (
    DatumReference,
    GdtFrame,
    GdtSegment,
)
from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.router import _working_copy
from app.review.schemas import (
    EditGeometricTolerance,
    ReviewWorkingCopyResponse,
    parse_review_command,
    validate_edit_fields,
)
from app.review.service import ReviewService, ReviewVersionConflict
from app.storage.models import StoredFile


@pytest.fixture
def db_session() -> Iterator[Session]:
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("isolated PostgreSQL is unavailable")
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


def _frames(*datums: str) -> tuple[GdtFrame, ...]:
    return (
        GdtFrame(
            segments=(
                GdtSegment(
                    tolerance_value="0.12",
                    diameter_modifier=False,
                    datum_references=tuple(
                        DatumReference(datum=datum) for datum in datums
                    ),
                ),
            ),
        ),
    )


def _edit_command(
    *,
    item_id: str = "case-a",
    datums: tuple[str, ...] = ("B",),
) -> dict[str, object]:
    return EditGeometricTolerance(
        type="edit_geometric_tolerance",
        item_id=item_id,
        tolerance_type="parallelism",
        frames=_frames(*datums),
        standard_context="unspecified",
    ).model_dump(mode="json")


def _structured_payload() -> dict[str, object]:
    return {
        "candidate_id": "case-a",
        "item_type": "geometric_tolerance",
        "schema_version": "geometric-tolerance-candidate/1",
        "raw_text": "∥ | 0.1 | A",
        "normalized_text": "∥ | 0.1 | A",
        "tolerance_type": "parallelism",
        "tolerance_symbol": "∥",
        "tolerance_value": "0.1",
        "diameter_modifier": False,
        "modifiers": [],
        "datum_references": [{"datum": "A", "modifiers": []}],
        "frames": [
            {
                "segments": [
                    {
                        "tolerance_value": "0.1",
                        "diameter_modifier": False,
                        "modifiers": [],
                        "datum_references": [
                            {"datum": "A", "modifiers": []}
                        ],
                    }
                ]
            }
        ],
        "standard_context": "unspecified",
        "coordinates": [1.0, 2.0, 3.0, 4.0],
        "source_location_ids": ["source-a"],
        "evidence_ref": "asset://tests/gdt-evidence.json",
        "requires_confirmation": True,
    }


def _seed_working_copy(session: Session) -> tuple[AutomaticResult, object]:
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
    session.add_all(
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
                logical_task_key=f"process:gdt-review:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{result_id}",
            ),
        ]
    )
    session.flush()
    result = AutomaticResult(
        id=result_id,
        project_id=project_id,
        source_file_id=source_file_id,
        logical_job_id=job_id,
        inventory_ref=f"asset://tests/{project_id}/inventory.json",
        candidates=[
            {
                "candidate_id": "case-a",
                "payload": _structured_payload(),
                "source_location_ids": ["source-a"],
            }
        ],
        coverage={
            "blocking_count": 0,
            "review_required_count": 1,
            "coverage_checked": True,
            "blocking_observation_ids": [],
            "entries": [],
            "relations": [],
        },
        technical_requirements=[],
        provider_call_ids=[],
        schema_version="automatic-result/3",
    )
    session.add(result)
    session.commit()
    working = ReviewService(session).create_from_raw(result.id)
    acquire_lock(session, working.project_id, "gdt-reviewer")
    return result, working


def test_edit_geometric_tolerance_command_is_exact() -> None:
    parsed = parse_review_command(_edit_command())
    assert isinstance(parsed, EditGeometricTolerance)
    assert parsed.tolerance_type == "parallelism"
    assert parsed.frames[0].segments[0].datum_references[0].datum == "B"


def test_extra_modifier_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="maximum_material_condition"):
        parse_review_command(
            {
                **_edit_command(),
                "frames": [
                    {
                        "segments": [
                            {
                                "tolerance_value": "0.12",
                                "diameter_modifier": False,
                                "modifiers": [
                                    {"kind": "not-a-modifier", "raw_symbol": "?"}
                                ],
                                "datum_references": [],
                            }
                        ]
                    }
                ],
            }
        )


def test_generic_edit_rejects_derived_gdt_fields() -> None:
    with pytest.raises(ValueError, match="derived geometric tolerance fields"):
        validate_edit_fields(
            {
                "item_type": "geometric_tolerance",
                "normalized_text": "∥ | 0.1 | A",
                "tolerance_type": "parallelism",
            },
            {"normalized_text": "∥ | 0.2 | A"},
        )


def test_edit_geometric_tolerance_regenerates_derived_fields(
    db_session: Session,
) -> None:
    _, working = _seed_working_copy(db_session)
    service = ReviewService(db_session)
    updated = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="gdt-reviewer",
        command=_edit_command(),
    )

    item = updated.items[0]
    assert item["normalized_text"] == "∥ | 0.12 | B"
    assert item["tolerance_value"] == "0.12"
    assert item["datum_references"][0]["datum"] == "B"
    assert item["acceptance_source"] == "manual"
    response = ReviewWorkingCopyResponse.model_validate(_working_copy(updated))
    assert response.items[0].frames[0].segments[0].datum_references[0].datum == "B"


def test_edit_geometric_tolerance_rejects_stale_version(
    db_session: Session,
) -> None:
    _, working = _seed_working_copy(db_session)
    service = ReviewService(db_session)
    service.apply(
        working.id,
        expected_version=working.version,
        operator_id="gdt-reviewer",
        command=_edit_command(),
    )

    with pytest.raises(ReviewVersionConflict):
        service.apply(
            working.id,
            expected_version=1,
            operator_id="gdt-reviewer",
            command=_edit_command(datums=("C",)),
        )
