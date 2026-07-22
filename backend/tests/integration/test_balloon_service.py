from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.balloons.service import BalloonService, ItemSetNotFrozen
from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewService
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


@dataclass
class BalloonContext:
    session: Session
    storage: LocalFileStorage
    review_service: ReviewService
    balloon_service: BalloonService
    working_copy: ReviewWorkingCopy


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


def make_balloon_context(
    db_session: Session,
    tmp_path: Path,
    *,
    frozen: bool,
) -> BalloonContext:
    project_id = uuid.uuid4()
    result_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage = LocalFileStorage(tmp_path)
    source_bytes = b"%PDF-1.4\n% D5 balloon fixture\n"
    source = storage.write_verified(
        f"projects/{project_id}/source.pdf",
        source_bytes,
        hashlib.sha256(source_bytes).hexdigest(),
    )
    inventory_document = {
        "schema_version": "page-inventory/1",
        "pages": [
            {
                "page_index": 0,
                "width": 200.0,
                "height": 200.0,
                "rotation": 0,
                "pdf_to_render_matrix": [1, 0, 0, 1, 0, 0],
                "render_to_pdf_matrix": [1, 0, 0, 1, 0, 0],
                "observations": [
                    {
                        "observation_id": "s1",
                        "page_index": 0,
                        "bbox_pdf": [20.0, 20.0, 40.0, 40.0],
                        "direction": [1.0, 0.0],
                    },
                    {
                        "observation_id": "s2",
                        "page_index": 0,
                        "bbox_pdf": [120.0, 120.0, 140.0, 140.0],
                        "direction": [1.0, 0.0],
                    },
                ],
            }
        ],
    }
    inventory_bytes = json.dumps(inventory_document).encode("utf-8")
    inventory = storage.write_verified(
        f"projects/{project_id}/inventory.json",
        inventory_bytes,
        hashlib.sha256(inventory_bytes).hexdigest(),
    )
    db_session.add_all(
        [
            Project(id=project_id, state=ProjectState.READY_FOR_EDIT),
            StoredFile(
                id=uuid.uuid4(),
                resource_ref=source.resource_ref,
                sha256=source.sha256,
                size_bytes=source.size_bytes,
                mime_type="application/pdf",
            ),
            LogicalJob(
                id=job_id,
                project_id=str(project_id),
                logical_task_key=f"balloon:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{result_id}",
            ),
        ]
    )
    db_session.flush()
    source_file = db_session.query(StoredFile).filter_by(
        resource_ref=source.resource_ref
    ).one()
    db_session.add(
        AutomaticResult(
            id=result_id,
            project_id=project_id,
            source_file_id=source_file.id,
            logical_job_id=job_id,
            inventory_ref=inventory.resource_ref,
            candidates=[
                {
                    "candidate_id": "i1",
                    "payload": {
                        "candidate_id": "i1",
                        "item_type": "thread",
                        "raw_text": "M6",
                        "normalized_text": "M6",
                        "coordinates": [20, 20, 40, 40],
                        "scope": "local_feature",
                        "balloon_required": True,
                        "requires_confirmation": False,
                    },
                    "source_location_ids": ["s1"],
                },
                {
                    "candidate_id": "i2",
                    "payload": {
                        "candidate_id": "i2",
                        "item_type": "thread",
                        "raw_text": "M8",
                        "normalized_text": "M8",
                        "coordinates": [120, 120, 140, 140],
                        "scope": "local_feature",
                        "balloon_required": True,
                        "requires_confirmation": False,
                    },
                    "source_location_ids": ["s2"],
                },
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
    review_service = ReviewService(db_session, storage=storage)
    working = review_service.create_from_raw(result_id)
    acquire_lock(db_session, project_id, "quality-1")
    if frozen:
        working = review_service.freeze_items(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
        )
    return BalloonContext(
        session=db_session,
        storage=storage,
        review_service=review_service,
        balloon_service=BalloonService(db_session, storage=storage),
        working_copy=working,
    )


def test_formal_numbers_require_frozen_item_set(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-BAL-002: formal numbering requires the reviewed item-set freeze."""
    context = make_balloon_context(db_session, tmp_path, frozen=False)

    with pytest.raises(ItemSetNotFrozen):
        context.balloon_service.generate_formal(
            context.working_copy.project_id,
            expected_version=context.working_copy.version,
            operator_id="quality-1",
        )

    frozen = context.review_service.freeze_items(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    generated = context.balloon_service.generate_formal(
        frozen.project_id,
        expected_version=frozen.version,
        operator_id="quality-1",
    )

    assert [balloon.formal_number for balloon in generated] == [1, 2]
    assert [balloon.suggested_number for balloon in generated] == [1, 2]


@pytest.mark.parametrize(
    "command",
    [
        {"type": "exclude", "item_id": "i1"},
        {
            "type": "edit",
            "item_id": "i1",
            "fields": {"coordinates": [22, 22, 42, 42]},
        },
        {"type": "merge", "item_ids": ["i1", "i2"], "raw_text": "M6 20"},
        {
            "type": "split",
            "item_id": "i1",
            "parts": [{"raw_text": "M6"}, {"raw_text": "深10"}],
        },
        {
            "type": "add",
            "raw_text": "M10",
            "item_type": "thread",
            "coordinates": [60, 60, 80, 80],
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
    ],
)
def test_number_affecting_review_commands_mark_stale(
    db_session: Session,
    tmp_path: Path,
    command: dict[str, object],
) -> None:
    context = make_balloon_context(db_session, tmp_path, frozen=False)

    saved = context.review_service.apply(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
        command=command,
    )

    assert saved.numbering_stale is True


def test_manual_item_gets_explicit_page_and_stable_source_identity(
    db_session: Session,
    tmp_path: Path,
) -> None:
    context = make_balloon_context(db_session, tmp_path, frozen=False)

    saved = context.review_service.apply(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
        command={
            "type": "add",
            "raw_text": "M10",
            "item_type": "thread",
            "coordinates": [60, 60, 80, 80],
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
    )
    added = saved.items[-1]

    assert added["page_index"] == 0
    assert added["source_location_ids"] == [f"manual:{added['item_id']}"]
