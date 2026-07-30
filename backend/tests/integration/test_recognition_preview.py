from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.main import app
from app.projects.models import Project
from app.projects.router import get_session, get_storage
from app.projects.state import ProjectState
from app.review.models import ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


@dataclass(frozen=True)
class PreviewContext:
    client: TestClient
    session: Session
    storage: LocalFileStorage


@pytest.fixture
def preview_context(tmp_path: Path) -> Iterator[PreviewContext]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    storage = LocalFileStorage(tmp_path / "storage")

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            yield PreviewContext(client=client, session=session, storage=storage)
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def _seed_project(context: PreviewContext) -> tuple[Project, StoredFile, bytes]:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    source_bytes = b"%PDF-1.7\\npreview-source\\n"
    stored = context.storage.write_verified(
        f"projects/{project.id}/source.pdf",
        source_bytes,
        sha256(source_bytes).hexdigest(),
    )
    source = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    context.session.add_all([project, source])
    context.session.commit()
    return project, source, source_bytes


def _migration_0012() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/0012_recognition_preview.py"
    )
    assert path.is_file()
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "test_migration_0012_recognition_preview",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _preview_service(session: Session):
    # Import inside the test so every RED assertion remains collectible before
    # the PRT-6 production owner exists.
    from app.processing.recognition_preview import RecognitionPreviewService

    return RecognitionPreviewService(session)


def _local_snapshot() -> dict[str, object]:
    return {
        "schema_version": "recognition-preview/1",
        "stage": "local_ready",
        "candidates": [{"candidate_id": "candidate-1", "kind": "thread"}],
        "counts": {
            "local_resolved": 1,
            "cache_resolved": 0,
            "vlm_pending": 1,
            "vlm_resolved": 0,
            "unresolved": 0,
        },
    }


def test_local_snapshot_is_immutable_revision_one_and_the_canonical_head(
    preview_context: PreviewContext,
) -> None:
    """Catches a preview owner that mutates or fails to establish local revision 1."""
    project, source, _ = _seed_project(preview_context)

    revision = _preview_service(preview_context.session).publish_local(
        project_id=project.id,
        source_file_id=source.id,
        semantic_snapshot=_local_snapshot(),
    )

    assert revision.revision == 1
    assert revision.parent_revision_id is None
    assert revision.semantic_sha256 == sha256(
        b'{"candidates":[{"candidate_id":"candidate-1","kind":"thread"}],'
        b'"counts":{"cache_resolved":0,"local_resolved":1,"unresolved":0,'
        b'"vlm_pending":1,"vlm_resolved":0},"schema_version":'
        b'"recognition-preview/1","stage":"local_ready"}'
    ).hexdigest()
    assert _preview_service(preview_context.session).head_for(project.id).id == revision.id


def test_enrichment_creates_a_successor_without_changing_the_local_snapshot(
    preview_context: PreviewContext,
) -> None:
    """Catches in-place enrichment that overwrites the locally visible revision."""
    project, source, _ = _seed_project(preview_context)
    service = _preview_service(preview_context.session)
    local = service.publish_local(
        project_id=project.id,
        source_file_id=source.id,
        semantic_snapshot=_local_snapshot(),
    )
    enriched_snapshot = {
        **_local_snapshot(),
        "stage": "vlm_enriching",
        "counts": {
            "local_resolved": 1,
            "cache_resolved": 0,
            "vlm_pending": 0,
            "vlm_resolved": 1,
            "unresolved": 0,
        },
    }

    enriched = service.append_enrichment(
        project_id=project.id,
        expected_head_version=1,
        parent_revision_id=local.id,
        semantic_snapshot=enriched_snapshot,
    )

    preview_context.session.refresh(local)
    assert enriched.revision == 2
    assert enriched.parent_revision_id == local.id
    assert local.semantic_snapshot == _local_snapshot()
    assert local.semantic_sha256 != enriched.semantic_sha256


def test_only_one_writer_can_advance_an_expected_preview_head(
    preview_context: PreviewContext,
) -> None:
    """Catches a lost-update race that accepts two successors for one head version."""
    project, source, _ = _seed_project(preview_context)
    service = _preview_service(preview_context.session)
    local = service.publish_local(
        project_id=project.id,
        source_file_id=source.id,
        semantic_snapshot=_local_snapshot(),
    )
    winner = service.append_enrichment(
        project_id=project.id,
        expected_head_version=1,
        parent_revision_id=local.id,
        semantic_snapshot={**_local_snapshot(), "stage": "vlm_enriching"},
    )

    with pytest.raises(service.CasConflict):
        service.append_enrichment(
            project_id=project.id,
            expected_head_version=1,
            parent_revision_id=local.id,
            semantic_snapshot={**_local_snapshot(), "stage": "late-writer"},
        )

    assert service.head_for(project.id).id == winner.id


def test_stale_completion_and_terminal_result_cannot_advance_the_preview_head(
    preview_context: PreviewContext,
) -> None:
    """Catches a late callback that regresses preview or rewrites terminal state."""
    project, source, _ = _seed_project(preview_context)
    service = _preview_service(preview_context.session)
    local = service.publish_local(
        project_id=project.id,
        source_file_id=source.id,
        semantic_snapshot=_local_snapshot(),
    )
    current = service.append_enrichment(
        project_id=project.id,
        expected_head_version=1,
        parent_revision_id=local.id,
        semantic_snapshot={**_local_snapshot(), "stage": "vlm_enriching"},
    )
    job = LogicalJob(
        project_id=str(project.id),
        logical_task_key=f"preview-terminal:{project.id}",
        status="succeeded",
        processing_stage="preparing_review",
    )
    terminal = AutomaticResult(
        project_id=project.id,
        source_file_id=source.id,
        logical_job=job,
        inventory_ref=f"asset://tests/{project.id}/inventory.json",
        candidates=[],
        coverage={},
        provider_call_ids=[],
        schema_version="automatic-result/1",
    )
    preview_context.session.add_all([job, terminal])
    preview_context.session.commit()

    service.supersede_with_terminal(project_id=project.id, automatic_result_id=terminal.id)
    with pytest.raises(service.CasConflict):
        service.append_enrichment(
            project_id=project.id,
            expected_head_version=2,
            parent_revision_id=current.id,
            semantic_snapshot={**_local_snapshot(), "stage": "late-completion"},
        )

    assert service.head_for(project.id).id == current.id
    assert preview_context.session.get(AutomaticResult, terminal.id) is not None


def test_preview_schema_requires_immutable_revisions_and_one_mutable_head() -> None:
    """Catches a migration without revision lineage, CAS, terminal binding, or guards."""
    inspector = inspect(engine)
    assert {"recognition_preview_revisions", "recognition_preview_heads"} <= set(
        inspector.get_table_names()
    )
    revision_columns = {
        column["name"] for column in inspector.get_columns("recognition_preview_revisions")
    }
    assert {
        "id", "project_id", "source_file_id", "revision", "parent_revision_id",
        "semantic_snapshot", "semantic_sha256", "schema_version",
    } <= revision_columns
    head_columns = {
        column["name"] for column in inspector.get_columns("recognition_preview_heads")
    }
    assert {"project_id", "revision_id", "version", "terminal_result_id"} <= head_columns
    assert any(
        constraint["column_names"] == ["project_id"]
        for constraint in inspector.get_unique_constraints("recognition_preview_heads")
    )


def test_recognition_preview_schema_is_owned_by_0012_after_0011() -> None:
    """Catches an unnumbered preview migration or one detached from the current head."""
    migration = _migration_0012()
    assert migration.revision == "0012"
    assert migration.down_revision == "0011"


def test_recognition_preview_route_is_registered_as_a_read_only_project_route() -> None:
    """Catches a missing preview read endpoint before response-shape assertions run."""
    routes = {
        (child.path, tuple(sorted(child.methods or set())))
        for route in app.routes
        for router in [getattr(route, "original_router", None)]
        if router is not None
        for child in router.routes
    }
    assert (
        "/api/v1/projects/{project_id}/recognition-preview",
        ("GET",),
    ) in routes


def test_preview_refresh_is_project_and_source_bound_without_working_copy(
    preview_context: PreviewContext,
) -> None:
    """Catches a preview read that fabricates review state or loses source identity."""
    project, source, source_bytes = _seed_project(preview_context)
    alternate_bytes = b"%PDF-1.7\\nwrong-source\\n"
    alternate = preview_context.storage.write_verified(
        f"projects/{project.id}/alternate.pdf",
        alternate_bytes,
        sha256(alternate_bytes).hexdigest(),
    )
    preview_context.session.add(StoredFile(
        resource_ref=alternate.resource_ref,
        sha256=alternate.sha256,
        size_bytes=alternate.size_bytes,
        mime_type="application/pdf",
    ))
    preview_context.session.commit()
    service = _preview_service(preview_context.session)
    revision = service.publish_local(
        project_id=project.id,
        source_file_id=source.id,
        semantic_snapshot=_local_snapshot(),
    )

    first = preview_context.client.get(
        f"/api/v1/projects/{project.id}/recognition-preview"
    )
    second = preview_context.client.get(
        f"/api/v1/projects/{project.id}/recognition-preview"
    )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert first.json() == {
        "revision": 1,
        "stage": "local_ready",
        "source_pdf_url": f"/api/v1/projects/{project.id}/source-pdf",
        "semantic_snapshot": revision.semantic_snapshot,
        "counts": _local_snapshot()["counts"],
    }
    source_response = preview_context.client.get(first.json()["source_pdf_url"])
    assert source_response.status_code == 200
    assert source_response.content == source_bytes
    assert preview_context.session.scalar(
        select(func.count()).select_from(ReviewWorkingCopy).where(
            ReviewWorkingCopy.project_id == project.id
        )
    ) == 0
