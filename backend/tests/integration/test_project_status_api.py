from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.main import app
from app.projects.models import Project
from app.projects.router import get_session, get_storage
from app.review.models import ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


@dataclass(frozen=True)
class StatusContext:
    client: TestClient
    session: Session


@pytest.fixture
def status_context(tmp_path: Path) -> Iterator[StatusContext]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    storage = LocalFileStorage(tmp_path)

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            yield StatusContext(client, session)
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def _seed_project_status(
    session: Session,
    *,
    project_state: str = "processing",
    job_status: str | None = None,
    has_working_copy: bool = False,
    result_completeness: str | None = None,
    processing_stage: str | None = None,
    error: dict[str, str] | None = None,
) -> uuid.UUID:
    project_id = uuid.uuid4()
    project = Project(id=project_id, state=project_state)
    session.add(project)
    session.flush()

    job: LogicalJob | None = None
    if job_status is not None:
        result_id = uuid.uuid4()
        job = LogicalJob(
            id=uuid.uuid4(),
            project_id=str(project_id),
            logical_task_key=f"product-process:{project_id}",
            status=job_status,
            processing_stage=processing_stage or "queued",
            result_ref=(
                f"automatic-result://{result_id}"
                if job_status == "succeeded"
                else None
            ),
        )
        session.add(job)
        session.flush()

        if job_status == "succeeded":
            source = StoredFile(
                id=uuid.uuid4(),
                resource_ref=f"asset://tests/{project_id}/source.pdf",
                sha256="0" * 64,
                size_bytes=1,
                mime_type="application/pdf",
            )
            session.add(source)
            session.flush()
            raw = AutomaticResult(
                id=result_id,
                project_id=project_id,
                source_file_id=source.id,
                logical_job_id=job.id,
                inventory_ref=f"asset://tests/{project_id}/inventory.json",
                candidates=[],
                coverage={},
                provider_call_ids=[],
                schema_version="automatic-result/1",
            )
            if result_completeness is not None:
                setattr(raw, "completeness", result_completeness)
            session.add(raw)
            session.flush()
            if has_working_copy:
                session.add(
                    ReviewWorkingCopy(
                        project_id=project_id,
                        raw_result_id=raw.id,
                        items=[],
                        coverage={},
                        sip_metadata={},
                    )
                )

    if error is not None:
        session.add(
            ErrorRecord(
                project_id=project_id,
                code=error["code"],
                message=error["message"],
                severity=error.get("severity", "blocking"),
                stage=error["stage"],
                location_ref=error.get("location_ref"),
                cause_category=error["cause_category"],
            )
        )
    session.commit()
    return project_id


@pytest.mark.parametrize(
    (
        "project_state",
        "job_status",
        "has_working_copy",
        "processing_stage",
        "expected_phase",
        "expected_stage",
    ),
    [
        ("processing", None, False, None, "queued", "queued"),
        ("processing", "processing", False, "parsing", "processing", "parsing"),
        (
            "processing",
            "processing",
            False,
            "recognizing",
            "processing",
            "recognizing",
        ),
        (
            "ready_for_edit",
            "succeeded",
            False,
            "preparing_review",
            "processing",
            "preparing_review",
        ),
        (
            "editing",
            "succeeded",
            True,
            "preparing_review",
            "ready_for_review",
            None,
        ),
        (
            "processing_failed",
            "failed",
            False,
            "recognizing",
            "failed",
            None,
        ),
    ],
)
def test_status_projects_only_active_processing_stage(
    status_context: StatusContext,
    project_state: str,
    job_status: str | None,
    has_working_copy: bool,
    processing_stage: str | None,
    expected_phase: str,
    expected_stage: str | None,
) -> None:
    project_id = _seed_project_status(
        status_context.session,
        project_state=project_state,
        job_status=job_status,
        has_working_copy=has_working_copy,
        processing_stage=processing_stage,
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json()["phase"] == expected_phase
    assert response.json().get("stage") == expected_stage


@pytest.mark.parametrize(
    ("project_state", "job_status", "has_working_copy", "expected_phase"),
    [
        ("processing", None, False, "queued"),
        ("processing", "pending", False, "processing"),
        ("processing", "processing", False, "processing"),
        ("processing", "failed", False, "failed"),
        ("ready_for_edit", "succeeded", False, "processing"),
        ("editing", "succeeded", True, "ready_for_review"),
        ("reviewed", "succeeded", True, "ready_for_review"),
    ],
)
def test_project_status_projects_real_owners(
    status_context: StatusContext,
    project_state: str,
    job_status: str | None,
    has_working_copy: bool,
    expected_phase: str,
) -> None:
    project_id = _seed_project_status(
        status_context.session,
        project_state=project_state,
        job_status=job_status,
        has_working_copy=has_working_copy,
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == expected_phase
    assert payload["workbench_ready"] is (expected_phase == "ready_for_review")
    assert payload["retryable"] is False
    assert "project_id" not in payload
    assert "recognition_mode" not in payload
    assert "recognition_router_version" not in payload
    assert "resource_ref" not in response.text
    assert "asset://" not in response.text


def test_failed_logical_job_is_terminal_even_while_project_is_processing(
    status_context: StatusContext,
) -> None:
    project_id = _seed_project_status(
        status_context.session,
        project_state="processing",
        job_status="failed",
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json() == {
        "phase": "failed",
        "workbench_ready": False,
        "retryable": False,
        "error": {
            "code": "project_processing_failed",
            "stage": "processing",
        },
    }


def test_transient_failure_is_retryable_without_leaking_error_record(
    status_context: StatusContext,
) -> None:
    raw_message = (
        "Redis refused token=top-secret at /srv/private/customer.pdf "
        '{"provider_payload":"credential"}'
    )
    location_ref = "asset://projects/private/source.pdf"
    project_id = _seed_project_status(
        status_context.session,
        job_status="failed",
        error={
            "code": "redis_unavailable",
            "message": raw_message,
            "stage": "/srv/private/preflight",
            "location_ref": location_ref,
            "cause_category": "transient_dependency_unavailable",
        },
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json() == {
        "phase": "failed",
        "workbench_ready": False,
        "retryable": True,
        "error": {
            "code": "redis_unavailable",
            "stage": "preflight",
        },
    }
    for forbidden in (
        raw_message,
        location_ref,
        "asset://",
        "/srv/private",
        "top-secret",
        "provider_payload",
        "credential",
        "resource_ref",
        "traceback",
    ):
        assert forbidden not in response.text.lower()


def test_vision_provider_failure_projects_retryable_sanitized_status(
    status_context: StatusContext,
) -> None:
    project_id = _seed_project_status(
        status_context.session,
        project_state="processing_failed",
        job_status="failed",
        error={
            "code": "vision_provider_call_failed",
            "message": "/srv/private/customer.pdf credential=do-not-leak",
            "stage": "candidate_advisor",
            "cause_category": "transient_provider_failure",
        },
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json()["retryable"] is True
    assert response.json()["error"] == {
        "code": "vision_provider_call_failed",
        "stage": "candidate_advisor",
    }
    assert "do-not-leak" not in response.text
    assert "/srv/private" not in response.text


@pytest.mark.parametrize(
    ("code", "cause_category", "project_state", "job_status", "expected_stage"),
    [
        (
            "unsupported_input",
            "unsupported_input",
            "unsupported_input",
            "failed",
            "page_inventory",
        ),
        (
            "inventory_processing_failed",
            "processing_defect",
            "processing_failed",
            "failed",
            "page_inventory",
        ),
        (
            "review_bootstrap_failed",
            "processing_defect",
            "ready_for_edit",
            "succeeded",
            "review_bootstrap",
        ),
    ],
)
def test_deterministic_failures_are_terminal_and_not_retryable(
    status_context: StatusContext,
    code: str,
    cause_category: str,
    project_state: str,
    job_status: str,
    expected_stage: str,
) -> None:
    private_message = "backend traceback at /var/lib/private with password=hunter2"
    project_id = _seed_project_status(
        status_context.session,
        project_state=project_state,
        job_status=job_status,
        error={
            "code": code,
            "message": private_message,
            "stage": "/var/lib/private/stage",
            "location_ref": "asset://private/result.json",
            "cause_category": cause_category,
        },
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json() == {
        "phase": "failed",
        "workbench_ready": False,
        "retryable": False,
        "error": {
            "code": code,
            "stage": expected_stage,
        },
    }
    assert private_message not in response.text
    assert "/var/lib/private" not in response.text
    assert "asset://" not in response.text
    assert "hunter2" not in response.text


def test_working_copy_wins_over_stale_blocking_error(
    status_context: StatusContext,
) -> None:
    project_id = _seed_project_status(
        status_context.session,
        project_state="editing",
        job_status="succeeded",
        has_working_copy=True,
        error={
            "code": "redis_unavailable",
            "message": "old transient failure",
            "stage": "preflight",
            "cause_category": "transient_dependency_unavailable",
        },
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "ready_for_review"
    assert response.json()["workbench_ready"] is True
    assert response.json()["retryable"] is False


def test_partial_result_projects_terminal_review_required_status(
    status_context: StatusContext,
) -> None:
    """PRT-5 exposes terminal partial completeness without Provider detail."""
    project_id = _seed_project_status(
        status_context.session,
        project_state="editing",
        job_status="succeeded",
        has_working_copy=True,
        result_completeness="partial_review_required",
    )

    response = status_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )

    assert response.status_code == 200
    assert response.json() == {
        "phase": "partial_review_required",
        "workbench_ready": True,
        "retryable": False,
    }
    assert "provider" not in response.text.lower()
    assert "resource_ref" not in response.text
    assert "asset://" not in response.text


def test_unknown_project_uses_sanitized_not_found_envelope(
    status_context: StatusContext,
) -> None:
    missing = uuid.uuid4()

    response = status_context.client.get(
        f"/api/v1/projects/{missing}/status"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "project_not_found",
            "message": "project was not found",
            "severity": "blocking",
            "stage": "project_api",
            "location_ref": None,
            "cause_category": "not_found",
        }
    }
    assert str(missing) not in response.text
