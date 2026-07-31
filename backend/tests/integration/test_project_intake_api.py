from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import engine
from app.errors.models import ErrorRecord
from app.main import app
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.router import get_session, get_storage
from app.projects.state import ProjectState
from app.review.models import ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


@dataclass
class DispatchRecorder:
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    failure: str | None = None

    def __call__(
        self,
        project_id: str,
        source_ref: str,
        logical_task_key: str,
    ) -> None:
        self.calls.append((project_id, source_ref, logical_task_key))
        if self.failure is not None:
            raise RuntimeError(self.failure)


@dataclass(frozen=True)
class IntakeContext:
    client: TestClient
    session: Session
    storage: LocalFileStorage
    dispatch: DispatchRecorder


@pytest.fixture
def one_page_vector_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((24, 40), "M6 inspection")
    content = document.tobytes()
    document.close()
    assert content.startswith(b"%PDF-")
    return content


@pytest.fixture
def intake_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[IntakeContext]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    storage = LocalFileStorage(tmp_path)
    dispatch = DispatchRecorder()

    def override_session() -> Iterator[Session]:
        yield session

    monkeypatch.setattr(inventory_project, "delay", dispatch)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            yield IntakeContext(client, session, storage, dispatch)
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_create_project_accepts_one_pdf_and_dispatches_canonical_task(
    intake_context: IntakeContext,
    one_page_vector_pdf: bytes,
) -> None:
    response = intake_context.client.post(
        "/api/v1/projects",
        files={
            "file": (
                "../../credential-secret.pdf",
                one_page_vector_pdf,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 202
    payload = response.json()
    project_id = uuid.UUID(payload["project_id"])
    assert payload == {
        "project_id": str(project_id),
        "phase": "queued",
        "workbench_ready": False,
        "retryable": False,
        "error": None,
        "stage": "queued",
    }
    project = intake_context.session.get(Project, project_id)
    source_ref = f"asset://projects/{project_id}/source.pdf"
    source = intake_context.session.scalar(
        select(StoredFile).where(StoredFile.resource_ref == source_ref)
    )
    assert project is not None
    assert project.state == ProjectState.PROCESSING
    assert project.recognition_mode == "legacy_high_recall"
    assert project.recognition_router_version == "legacy"
    assert source is not None
    assert source.mime_type == "application/pdf"
    assert intake_context.storage.read_bytes(source.resource_ref) == one_page_vector_pdf
    assert intake_context.dispatch.calls == [
        (str(project_id), source.resource_ref, f"product-process:{project_id}")
    ]
    assert "credential-secret.pdf" not in source.resource_ref
    assert "asset://" not in response.text
    assert str(intake_context.storage.root) not in response.text
    assert "credential-secret.pdf" not in response.text


def test_project_freezes_allowlisted_recognition_mode_at_intake(
    intake_context: IntakeContext,
    one_page_vector_pdf: bytes,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        storage_root=intake_context.storage.root,
        symbol_recognition_mode="production_uncertainty",
    )

    response = intake_context.client.post(
        "/api/v1/projects",
        files={"file": ("drawing.pdf", one_page_vector_pdf, "application/pdf")},
    )

    assert response.status_code == 202
    project_id = uuid.UUID(response.json()["project_id"])
    project = intake_context.session.get(Project, project_id)
    assert project is not None
    assert project.recognition_mode == "production_uncertainty"
    assert project.recognition_router_version == "symbol-uncertainty-router/1"
    assert intake_context.dispatch.calls == [
        (str(project_id), f"asset://projects/{project_id}/source.pdf", f"product-process:{project_id}")
    ]


def test_runtime_rejects_verification_high_recall_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "QI_SYMBOL_RECOGNITION_MODE",
        "verification_high_recall",
    )
    with pytest.raises(ValueError):
        Settings(_env_file=None)


_ZERO_PAGE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog>>endobj\n"
    b"xref\n0 2\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"trailer<</Size 2/Root 1 0 R>>\n"
    b"startxref\n45\n%%EOF\n"
)


@pytest.mark.parametrize(
    ("filename", "content_type", "payload"),
    [
        ("empty.pdf", "application/pdf", b""),
        ("drawing.txt", "text/plain", b"%PDF-1.4\n%%EOF\n"),
        ("signature.pdf", "application/pdf", b"not-a-pdf"),
        ("broken.pdf", "application/pdf", b"%PDF-not-a-document"),
        ("zero-pages.pdf", "application/pdf", _ZERO_PAGE_PDF),
    ],
)
def test_create_project_rejects_invalid_upload_without_orphans_or_dispatch(
    intake_context: IntakeContext,
    filename: str,
    content_type: str,
    payload: bytes,
) -> None:
    project_count = intake_context.session.scalar(
        select(func.count()).select_from(Project)
    )
    file_count = intake_context.session.scalar(
        select(func.count()).select_from(StoredFile)
    )

    response = intake_context.client.post(
        "/api/v1/projects",
        files={"file": (filename, payload, content_type)},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_pdf",
            "message": "uploaded file is not a valid PDF",
            "severity": "blocking",
            "stage": "project_api",
            "location_ref": None,
            "cause_category": "validation",
        }
    }
    assert intake_context.dispatch.calls == []
    assert intake_context.session.scalar(
        select(func.count()).select_from(Project)
    ) == project_count
    assert intake_context.session.scalar(
        select(func.count()).select_from(StoredFile)
    ) == file_count
    assert not [path for path in intake_context.storage.root.rglob("*") if path.is_file()]
    assert filename not in response.text
    assert "asset://" not in response.text


def test_create_project_rejects_a_second_multipart_file(
    intake_context: IntakeContext,
    one_page_vector_pdf: bytes,
) -> None:
    project_count = intake_context.session.scalar(
        select(func.count()).select_from(Project)
    )
    file_count = intake_context.session.scalar(
        select(func.count()).select_from(StoredFile)
    )

    response = intake_context.client.post(
        "/api/v1/projects",
        files=[
            ("file", ("drawing.pdf", one_page_vector_pdf, "application/pdf")),
            ("attachment", ("extra.pdf", one_page_vector_pdf, "application/pdf")),
        ],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pdf"
    assert intake_context.dispatch.calls == []
    assert intake_context.session.scalar(
        select(func.count()).select_from(Project)
    ) == project_count
    assert intake_context.session.scalar(
        select(func.count()).select_from(StoredFile)
    ) == file_count
    assert not [path for path in intake_context.storage.root.rglob("*") if path.is_file()]


def test_dispatch_failure_is_sanitized_retryable_and_durable(
    intake_context: IntakeContext,
    one_page_vector_pdf: bytes,
) -> None:
    secret = "token=super-secret /srv/private/customer/drawing.pdf"
    intake_context.dispatch.failure = secret

    response = intake_context.client.post(
        "/api/v1/projects",
        files={"file": ("drawing.pdf", one_page_vector_pdf, "application/pdf")},
    )

    assert response.status_code == 503
    payload = response.json()
    project_id = uuid.UUID(payload["error"]["project_id"])
    assert payload == {
        "error": {
            "code": "project_dispatch_failed",
            "message": "project dispatch failed",
            "severity": "blocking",
            "stage": "dispatch",
            "location_ref": None,
            "cause_category": "transient_dispatch_failure",
            "project_id": str(project_id),
            "retryable": True,
            "phase": "failed",
            "workbench_ready": False,
        },
    }
    project = intake_context.session.get(Project, project_id)
    error = intake_context.session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project_id)
    )
    source = intake_context.session.scalar(
        select(StoredFile).where(
            StoredFile.resource_ref == f"asset://projects/{project_id}/source.pdf"
        )
    )
    working = intake_context.session.scalar(
        select(ReviewWorkingCopy).where(ReviewWorkingCopy.project_id == project_id)
    )
    assert project is not None
    assert project.state == ProjectState.PROCESSING_FAILED
    assert error is not None
    assert error.code == "project_dispatch_failed"
    assert error.severity == "blocking"
    assert error.stage == "dispatch"
    assert error.cause_category == "transient_dispatch_failure"
    assert secret not in error.message
    assert source is not None
    assert intake_context.storage.read_bytes(source.resource_ref) == one_page_vector_pdf
    assert working is None
    assert secret not in response.text
    assert "asset://" not in response.text
    assert str(intake_context.storage.root) not in response.text

    status = intake_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )
    assert status.status_code == 200
    assert status.json()["phase"] == "failed"
    assert status.json()["retryable"] is True
    assert status.json()["error"]["code"] == "project_dispatch_failed"
    assert secret not in status.text


def test_database_failure_deletes_only_the_new_source_and_is_sanitized(
    intake_context: IntakeContext,
    one_page_vector_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_failure = "password=hunter2 /var/lib/private/postgres"

    def fail_commit() -> None:
        raise RuntimeError(private_failure)

    monkeypatch.setattr(intake_context.session, "commit", fail_commit)

    response = intake_context.client.post(
        "/api/v1/projects",
        files={"file": ("drawing.pdf", one_page_vector_pdf, "application/pdf")},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "project_intake_failed",
            "message": "project intake failed",
            "severity": "fatal",
            "stage": "project_api",
            "location_ref": None,
            "cause_category": "internal",
        }
    }
    assert intake_context.dispatch.calls == []
    assert not [path for path in intake_context.storage.root.rglob("*") if path.is_file()]
    assert private_failure not in response.text
    assert "asset://" not in response.text
