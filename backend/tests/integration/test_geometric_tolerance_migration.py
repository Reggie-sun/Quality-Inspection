from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import SessionLocal, engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.storage.models import StoredFile


BACKEND = Path(__file__).parents[2]


def _config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


def _postgres_available() -> None:
    try:
        with engine.connect():
            return
    except OperationalError:
        pytest.skip("isolated PostgreSQL is unavailable")


def _legacy_payload() -> dict[str, Any]:
    return {
        "raw_text": "∥ 0.1",
        "coordinates": [1.0, 2.0, 3.0, 4.0],
        "coarse_type": "geometric_tolerance",
        "requires_confirmation": True,
    }


def _structured_payload() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-structured",
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
        "source_location_ids": ["source-structured"],
        "evidence_ref": "asset://tests/gdt-evidence.json",
        "requires_confirmation": True,
    }


def _seed_layers(
    session: Session,
    *,
    candidate_payload: dict[str, Any],
    schema_version: str,
    include_review_layers: bool = False,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID | None]:
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    logical_job_id = uuid.uuid4()
    automatic_result_id = uuid.uuid4()
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
                id=logical_job_id,
                project_id=str(project_id),
                logical_task_key=f"process:gdt-migration:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{automatic_result_id}",
            ),
        ]
    )
    session.flush()
    session.add(
        AutomaticResult(
            id=automatic_result_id,
            project_id=project_id,
            source_file_id=source_file_id,
            logical_job_id=logical_job_id,
            inventory_ref=f"asset://tests/{project_id}/inventory.json",
            candidates=[
                {
                    "candidate_id": "candidate-1",
                    "payload": candidate_payload,
                    "source_location_ids": ["source-structured"],
                }
            ],
            coverage={"entries": [], "coverage_checked": True},
            technical_requirements=[],
            provider_call_ids=[],
            schema_version=schema_version,
        )
    )
    working_copy_id: uuid.UUID | None = None
    if include_review_layers:
        working_copy_id = uuid.uuid4()
        review_payload = {
            key: value
            for key, value in candidate_payload.items()
            if key != "candidate_id"
        }
        session.add(
            ReviewWorkingCopy(
                id=working_copy_id,
                project_id=project_id,
                raw_result_id=automatic_result_id,
                version=1,
                items=[
                    {
                        "item_id": "candidate-1",
                        **review_payload,
                        "source_location_ids": ["source-structured"],
                        "source_type": "automatic",
                        "status": "pending",
                        "active": True,
                    }
                ],
                coverage={"entries": [], "coverage_checked": True},
                technical_requirements=[],
                sip_metadata={},
                numbering_stale=False,
            )
        )
        session.add(
            ReviewedResult(
                id=uuid.uuid4(),
                project_id=project_id,
                working_copy_id=working_copy_id,
                working_version=1,
                items=[
                    {
                        "item_id": "candidate-1",
                        **review_payload,
                        "source_location_ids": ["source-structured"],
                        "source_type": "automatic",
                        "status": "pending",
                        "active": True,
                    }
                ],
                balloons=[],
                sip_metadata={},
                schema_version="reviewed-result/2",
            )
        )
    session.commit()
    return project_id, source_file_id, automatic_result_id, working_copy_id


def _automatic_payload(session: Session, result_id: uuid.UUID) -> dict[str, Any]:
    result = session.get(AutomaticResult, result_id)
    assert result is not None
    return result.candidates[0]["payload"]


def _legacy_gdt_counts(session: Session) -> dict[str, int]:
    queries = {
        "automatic_results": """
            SELECT COUNT(*)
            FROM automatic_results ar
            CROSS JOIN LATERAL jsonb_array_elements(ar.candidates) candidate
            WHERE candidate->'payload'->>'coarse_type'
                = 'geometric_tolerance'
        """,
        "review_working_copies": """
            SELECT COUNT(*)
            FROM review_working_copies rwc
            CROSS JOIN LATERAL jsonb_array_elements(rwc.items) item
            WHERE item->>'coarse_type' = 'geometric_tolerance'
        """,
        "reviewed_results": """
            SELECT COUNT(*)
            FROM reviewed_results rr
            CROSS JOIN LATERAL jsonb_array_elements(rr.items) item
            WHERE item->>'coarse_type' = 'geometric_tolerance'
        """,
    }
    return {
        table: int(session.execute(text(query)).scalar_one())
        for table, query in queries.items()
    }


def test_upgrade_converts_legacy_gdt_to_typed_unknown() -> None:
    _postgres_available()
    config = _config()
    command.downgrade(config, "0012")
    session = SessionLocal()
    try:
        _, _, result_id, _ = _seed_layers(
            session,
            candidate_payload=_legacy_payload(),
            schema_version="automatic-result/2",
        )
        command.upgrade(config, "0013")
        session.expire_all()
        payload = _automatic_payload(session, result_id)
        assert payload["item_type"] == "geometric_tolerance"
        assert payload["tolerance_type"] == "unknown"
        assert payload["raw_text"] == "∥ 0.1"
        assert payload["frames"] == []
        assert payload["requires_confirmation"] is True
    finally:
        session.close()
        command.upgrade(config, "head")


def test_upgrade_removes_legacy_gdt_from_all_result_layers() -> None:
    _postgres_available()
    config = _config()
    command.downgrade(config, "0012")
    session = SessionLocal()
    try:
        _seed_layers(
            session,
            candidate_payload=_legacy_payload(),
            schema_version="automatic-result/2",
            include_review_layers=True,
        )
        command.upgrade(config, "0013")
        session.expire_all()
        assert _legacy_gdt_counts(session) == {
            "automatic_results": 0,
            "review_working_copies": 0,
            "reviewed_results": 0,
        }
    finally:
        session.close()
        command.upgrade(config, "head")


def test_downgrade_restores_old_coarse_shape_for_all_result_layers() -> None:
    _postgres_available()
    config = _config()
    command.downgrade(config, "0012")
    session = SessionLocal()
    try:
        project_id, _, result_id, working_copy_id = _seed_layers(
            session,
            candidate_payload=_structured_payload(),
            schema_version="automatic-result/3",
            include_review_layers=True,
        )
        assert working_copy_id is not None
        command.upgrade(config, "0013")
        command.downgrade(config, "0012")
        session.expire_all()
        automatic_payload = _automatic_payload(session, result_id)
        assert set(automatic_payload) == {
            "raw_text",
            "coordinates",
            "coarse_type",
            "requires_confirmation",
        }
        assert automatic_payload["coarse_type"] == "geometric_tolerance"
        working = session.get(ReviewWorkingCopy, working_copy_id)
        assert working is not None
        assert working.items[0]["coarse_type"] == "geometric_tolerance"
        reviewed = session.scalar(
            select(ReviewedResult).where(
                ReviewedResult.project_id == project_id
            )
        )
        assert reviewed is not None
        assert reviewed.items[0]["coarse_type"] == "geometric_tolerance"
    finally:
        session.close()
        command.upgrade(config, "head")
