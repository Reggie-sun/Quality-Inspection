from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.balloons.router import (
    get_balloon_service,
    get_session as get_balloon_session,
)
from app.balloons.service import BalloonService
from app.exports.router import (
    get_export_service,
    get_session as get_export_session,
    get_storage as get_export_storage,
)
from app.processing.recognition_preview import RecognitionPreviewService
from app.projects.models import Project, ProjectLifecycleStatus
from app.projects.router import get_dispatcher, get_session, get_storage
from app.projects.state import ProjectState
from app.review.router import get_session as get_review_session
from app.storage.models import StoredFile
from app.storage.local import LocalFileStorage


@dataclass
class LifecycleApiContext:
    client: TestClient
    session: Session
    project: Project
    source: StoredFile
    dispatched: list[tuple[str, str, str]]
    storage: LocalFileStorage


@pytest.fixture
def lifecycle_api_context(tmp_path: Path) -> Iterator[LifecycleApiContext]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    project = Project(
        id=uuid.uuid4(),
        state=ProjectState.EDITING,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
        source_filename="drawing.pdf",
        lifecycle_status=ProjectLifecycleStatus.ACTIVE,
    )
    source = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="b" * 64,
        size_bytes=10,
        mime_type="application/pdf",
    )
    session.add_all([project, source])
    session.flush()
    RecognitionPreviewService(session, project_id=project.id).publish_local(
        source_file_id=source.id,
        snapshot={
            "schema_version": "recognition-preview/1",
            "stage": "local_ready",
            "candidates": [],
            "sources": [],
            "counts": {
                "local_resolved": 0,
                "cache_resolved": 0,
                "vlm_pending": 0,
                "vlm_resolved": 0,
                "unresolved": 0,
            },
        },
    )
    session.commit()
    dispatched: list[tuple[str, str, str]] = []
    storage = LocalFileStorage(tmp_path / "storage")

    def override_session() -> Iterator[Session]:
        yield session

    def dispatch(project_id: str, source_ref: str, task_key: str) -> None:
        dispatched.append((project_id, source_ref, task_key))

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_review_session] = override_session
    app.dependency_overrides[get_balloon_session] = override_session
    app.dependency_overrides[get_balloon_service] = lambda: BalloonService(
        session,
        storage=storage,
    )
    app.dependency_overrides[get_export_session] = override_session
    app.dependency_overrides[get_dispatcher] = lambda: dispatch
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_export_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            yield LifecycleApiContext(
                client,
                session,
                project,
                source,
                dispatched,
                storage,
            )
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_reprocess_returns_new_processing_project(
    lifecycle_api_context: LifecycleApiContext,
) -> None:
    response = lifecycle_api_context.client.post(
        f"/api/v1/projects/{lifecycle_api_context.project.id}/reprocess"
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload == {
        "project_id": payload["project_id"],
        "predecessor_project_id": str(lifecycle_api_context.project.id),
        "phase": "processing",
        "lifecycle_status": "reprocessing",
    }
    successor_id = uuid.UUID(payload["project_id"])
    successor = lifecycle_api_context.session.get(Project, successor_id)
    assert successor is not None
    assert successor.predecessor_project_id == lifecycle_api_context.project.id
    assert lifecycle_api_context.dispatched == [
        (
            str(successor_id),
            lifecycle_api_context.source.resource_ref,
            f"product-process:{successor_id}",
        )
    ]


def test_reprocess_rejects_duplicate_successor(
    lifecycle_api_context: LifecycleApiContext,
) -> None:
    path = (
        f"/api/v1/projects/{lifecycle_api_context.project.id}/reprocess"
    )
    assert lifecycle_api_context.client.post(path).status_code == 202

    response = lifecycle_api_context.client.post(path)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_reprocess_in_progress"


def test_delete_tombstones_and_blocks_project_entry_points(
    lifecycle_api_context: LifecycleApiContext,
) -> None:
    project_id = lifecycle_api_context.project.id

    response = lifecycle_api_context.client.delete(
        f"/api/v1/projects/{project_id}"
    )

    assert response.status_code == 204
    assert response.content == b""
    assert lifecycle_api_context.client.get(
        "/api/v1/projects"
    ).json()["count"] == 0
    status = lifecycle_api_context.client.get(
        f"/api/v1/projects/{project_id}/status"
    )
    source = lifecycle_api_context.client.get(
        f"/api/v1/projects/{project_id}/source-pdf"
    )
    assert status.status_code == 404
    assert status.json()["error"]["code"] == "project_not_found"
    assert source.status_code == 404
    assert source.json()["error"]["code"] == "project_not_found"


def test_reprocessing_successor_allows_progress_reads_but_not_workbench(
    lifecycle_api_context: LifecycleApiContext,
) -> None:
    started = lifecycle_api_context.client.post(
        f"/api/v1/projects/{lifecycle_api_context.project.id}/reprocess"
    ).json()
    successor_id = started["project_id"]

    status = lifecycle_api_context.client.get(
        f"/api/v1/projects/{successor_id}/status"
    )
    workbench = lifecycle_api_context.client.get(
        f"/api/v1/projects/{successor_id}/workbench"
    )

    assert status.status_code == 200
    assert status.json()["phase"] == "queued"
    assert workbench.status_code == 404
    assert workbench.json()["error"]["code"] == "project_not_found"


def test_deleted_project_rejects_review_balloon_and_export_entry_points(
    lifecycle_api_context: LifecycleApiContext,
) -> None:
    project_id = lifecycle_api_context.project.id
    assert lifecycle_api_context.client.delete(
        f"/api/v1/projects/{project_id}"
    ).status_code == 204

    review = lifecycle_api_context.client.post(
        f"/api/v1/projects/{project_id}/review/lock",
        headers={"X-QI-Operator": "operator-a"},
        json={"ttl_seconds": 300},
    )
    balloons = lifecycle_api_context.client.get(
        f"/api/v1/projects/{project_id}/balloons"
    )
    export = lifecycle_api_context.client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"reviewed_result_id": str(uuid.uuid4())},
    )

    for response in (review, balloons, export):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"


def test_deleted_project_rejects_existing_export_metadata_and_download(
    lifecycle_api_context: LifecycleApiContext,
) -> None:
    project_id = lifecycle_api_context.project.id
    export_id = uuid.uuid4()
    manifest = b"{}"
    stored = lifecycle_api_context.storage.write_verified(
        f"tests/{export_id}/manifest.json",
        manifest,
        hashlib.sha256(manifest).hexdigest(),
    )
    export = SimpleNamespace(
        id=export_id,
        project_id=project_id,
        reviewed_result_id=uuid.uuid4(),
        status="success",
        error_id=None,
        template_version="template/1",
        mapping_version="mapping/1",
        renderer_version="renderer/1",
    )

    class ExistingExportService:
        def get(self, requested_id: uuid.UUID) -> SimpleNamespace:
            assert requested_id == export_id
            return export

        def artifacts(self, requested_id: uuid.UUID) -> list[object]:
            assert requested_id == export_id
            return []

        def download_ref(self, requested_id: uuid.UUID, kind: str) -> str:
            assert requested_id == export_id
            assert kind == "manifest"
            return stored.resource_ref

    lifecycle_api_context.client.app.dependency_overrides[
        get_export_service
    ] = ExistingExportService
    assert lifecycle_api_context.client.delete(
        f"/api/v1/projects/{project_id}"
    ).status_code == 204

    metadata = lifecycle_api_context.client.get(f"/api/v1/exports/{export_id}")
    download = lifecycle_api_context.client.get(
        f"/api/v1/exports/{export_id}/downloads/manifest"
    )

    for response in (metadata, download):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"
