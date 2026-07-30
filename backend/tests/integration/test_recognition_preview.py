from __future__ import annotations

import copy
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import SessionLocal, engine
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


def _preview_service(session: Session, project_id: uuid.UUID):
    # Import inside the test so every RED assertion remains collectible before
    # the PRT-6 production owner exists.
    from app.processing.recognition_preview import RecognitionPreviewService

    return RecognitionPreviewService(session, project_id=project_id)


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

    preview = _preview_service(preview_context.session, project.id)
    revision = preview.publish_local(
        source_file_id=source.id,
        snapshot=_local_snapshot(),
    )

    assert revision.revision == 1
    assert revision.parent_revision_id is None
    assert revision.semantic_sha256 == sha256(
        b'{"candidates":[{"candidate_id":"candidate-1","kind":"thread"}],'
        b'"counts":{"cache_resolved":0,"local_resolved":1,"unresolved":0,'
        b'"vlm_pending":1,"vlm_resolved":0},"schema_version":'
        b'"recognition-preview/1","stage":"local_ready"}'
    ).hexdigest()
    assert preview.head().id == revision.id


def test_enrichment_creates_a_successor_without_changing_the_local_snapshot(
    preview_context: PreviewContext,
) -> None:
    """Catches in-place enrichment that overwrites the locally visible revision."""
    project, source, _ = _seed_project(preview_context)
    service = _preview_service(preview_context.session, project.id)
    local = service.publish_local(
        source_file_id=source.id,
        snapshot=_local_snapshot(),
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
        expected_head_version=1,
        parent_revision_id=local.id,
        snapshot=enriched_snapshot,
    )

    preview_context.session.refresh(local)
    assert enriched.revision == 2
    assert enriched.parent_revision_id == local.id
    assert local.semantic_snapshot == _local_snapshot()
    assert local.semantic_sha256 != enriched.semantic_sha256


def test_two_postgres_sessions_allow_one_expected_head_advance() -> None:
    """Catches a CAS implementation that only works inside one SQLAlchemy Session."""
    bootstrap = SessionLocal()
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    source = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="1" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )
    try:
        bootstrap.add_all([project, source])
        bootstrap.commit()
        bootstrap_preview = _preview_service(bootstrap, project.id)
        local = bootstrap_preview.publish_local(
            source_file_id=source.id,
            snapshot=_local_snapshot(),
        )
        bootstrap.commit()

        worker_thread_ids: set[int] = set()
        synchronized_head_threads: set[int] = set()
        listener_lock = threading.Lock()
        invoke_barrier = threading.Barrier(2)
        head_access_barrier = threading.Barrier(2)

        def synchronize_first_head_access(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            if "recognition_preview_heads" not in statement:
                return
            thread_id = threading.get_ident()
            with listener_lock:
                if (
                    thread_id not in worker_thread_ids
                    or thread_id in synchronized_head_threads
                ):
                    return
                synchronized_head_threads.add(thread_id)
            head_access_barrier.wait(timeout=5)

        def advance(marker: int) -> tuple[str, uuid.UUID]:
            session = SessionLocal()
            with listener_lock:
                worker_thread_ids.add(threading.get_ident())
            service = _preview_service(session, project.id)
            try:
                invoke_barrier.wait(timeout=5)
                revision = service.append_enrichment(
                    expected_head_version=1,
                    parent_revision_id=local.id,
                    snapshot={
                        **_local_snapshot(),
                        "stage": "vlm_enriching",
                        "candidates": [
                            {
                                "candidate_id": f"candidate-{marker}",
                                "kind": "thread",
                            }
                        ],
                        "counts": {
                            "local_resolved": 1,
                            "cache_resolved": 0,
                            "vlm_pending": 0,
                            "vlm_resolved": 1,
                            "unresolved": 0,
                        },
                    },
                )
                session.commit()
                return "winner", revision.id
            except service.CasConflict:
                session.rollback()
                winner = service.head()
                return "loser", winner.id
            finally:
                session.close()

        event.listen(engine, "before_cursor_execute", synchronize_first_head_access)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(advance, (1, 2)))
        finally:
            event.remove(engine, "before_cursor_execute", synchronize_first_head_access)

        winners = [revision_id for outcome, revision_id in outcomes if outcome == "winner"]
        losers = [revision_id for outcome, revision_id in outcomes if outcome == "loser"]
        assert len(winners) == 1
        assert losers == winners
        with engine.connect() as connection:
            assert connection.scalar(text(
                "SELECT count(*) FROM recognition_preview_revisions "
                "WHERE project_id = :project_id"
            ), {"project_id": project.id}) == 2
            assert connection.scalar(text(
                "SELECT count(*) FROM recognition_preview_heads "
                "WHERE project_id = :project_id"
            ), {"project_id": project.id}) == 1
            assert connection.scalar(text(
                "SELECT count(*) FROM recognition_preview_revisions revision "
                "LEFT JOIN recognition_preview_heads head ON head.revision_id = revision.id "
                "WHERE revision.project_id = :project_id "
                "AND revision.revision > 1 AND head.revision_id IS NULL"
            ), {"project_id": project.id}) == 0
    finally:
        bootstrap.close()
        # This test commits an isolated random project to the brief's disposable
        # PostgreSQL database. Step 1 destroys the whole disposable container;
        # this isolated evidence therefore remains safe and GREEN's immutable
        # revision trigger stays free to reject every DELETE.


def test_postgres_rejects_direct_preview_revision_update_and_delete(
    preview_context: PreviewContext,
) -> None:
    """Catches a schema that stores revisions but permits destructive mutation."""
    project, source, _ = _seed_project(preview_context)
    service = _preview_service(preview_context.session, project.id)
    revision = service.publish_local(
        source_file_id=source.id,
        snapshot=_local_snapshot(),
    )
    original_snapshot = copy.deepcopy(revision.semantic_snapshot)
    original_hash = revision.semantic_sha256

    with pytest.raises(DBAPIError):
        preview_context.session.execute(text(
            "UPDATE recognition_preview_revisions "
            "SET semantic_snapshot = '{\"tampered\":true}'::jsonb WHERE id = :id"
        ), {"id": revision.id})
        preview_context.session.commit()
    preview_context.session.rollback()
    with pytest.raises(DBAPIError):
        preview_context.session.execute(text(
            "DELETE FROM recognition_preview_revisions WHERE id = :id"
        ), {"id": revision.id})
        preview_context.session.commit()
    preview_context.session.rollback()

    persisted = service.revision_for(revision.revision)
    assert persisted.semantic_snapshot == original_snapshot
    assert persisted.semantic_sha256 == original_hash


def test_stale_completion_and_terminal_result_cannot_advance_the_preview_head(
    preview_context: PreviewContext,
) -> None:
    """Catches a late callback that regresses preview or rewrites terminal state."""
    project, source, _ = _seed_project(preview_context)
    service = _preview_service(preview_context.session, project.id)
    local = service.publish_local(
        source_file_id=source.id,
        snapshot=_local_snapshot(),
    )
    current = service.append_enrichment(
        expected_head_version=1,
        parent_revision_id=local.id,
        snapshot={**_local_snapshot(), "stage": "vlm_enriching"},
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
    service.supersede_with_terminal(automatic_result_id=terminal.id)
    preview_context.session.refresh(terminal)
    preview_context.session.refresh(project)
    terminal_after_supersession = {
        "candidates": copy.deepcopy(terminal.candidates),
        "coverage": copy.deepcopy(terminal.coverage),
        "provider_call_ids": copy.deepcopy(terminal.provider_call_ids),
        "schema_version": terminal.schema_version,
        "project_state": project.state,
        "project_version": project.version,
    }
    head_after_supersession = service.head()
    revision_count_after_supersession = preview_context.session.scalar(text(
        "SELECT count(*) FROM recognition_preview_revisions "
        "WHERE project_id = :project_id"
    ), {"project_id": project.id})

    with pytest.raises(service.CasConflict):
        service.append_enrichment(
            expected_head_version=2,
            parent_revision_id=current.id,
            snapshot={
                **_local_snapshot(),
                "stage": "vlm_enriching",
                "candidates": [{"candidate_id": "candidate-late", "kind": "thread"}],
            },
        )

    preview_context.session.expire_all()
    persisted_terminal = preview_context.session.get(AutomaticResult, terminal.id)
    persisted_project = preview_context.session.get(Project, project.id)
    assert persisted_terminal is not None
    assert persisted_project is not None
    assert service.head().id == head_after_supersession.id
    assert persisted_terminal.candidates == terminal_after_supersession["candidates"]
    assert persisted_terminal.coverage == terminal_after_supersession["coverage"]
    assert persisted_terminal.provider_call_ids == terminal_after_supersession["provider_call_ids"]
    assert persisted_terminal.schema_version == terminal_after_supersession["schema_version"]
    assert persisted_project.state == terminal_after_supersession["project_state"]
    assert persisted_project.version == terminal_after_supersession["project_version"]
    assert preview_context.session.scalar(text(
        "SELECT count(*) FROM recognition_preview_revisions "
        "WHERE project_id = :project_id"
    ), {"project_id": project.id}) == revision_count_after_supersession
    terminal_preview = preview_context.client.get(
        f"/api/v1/projects/{project.id}/recognition-preview"
    )
    assert terminal_preview.status_code == 409
    assert "semantic_snapshot" not in terminal_preview.json()


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
    assert inspector.get_pk_constraint("recognition_preview_revisions")["constrained_columns"] == ["id"]
    assert {
        tuple(constraint["column_names"] or ())
        for constraint in inspector.get_unique_constraints("recognition_preview_revisions")
    } >= {("project_id", "revision")}
    revision_foreign_keys = {
        (
            tuple(constraint["constrained_columns"]),
            constraint["referred_table"],
            tuple(constraint["referred_columns"]),
        )
        for constraint in inspector.get_foreign_keys("recognition_preview_revisions")
    }
    assert revision_foreign_keys >= {
        (("project_id",), "projects", ("id",)),
        (("source_file_id",), "stored_files", ("id",)),
        (("parent_revision_id",), "recognition_preview_revisions", ("id",)),
    }
    revision_column_details = {
        column["name"]: column
        for column in inspector.get_columns("recognition_preview_revisions")
    }
    assert all(
        revision_column_details[column]["nullable"] is False
        for column in (
            "project_id",
            "source_file_id",
            "revision",
            "semantic_snapshot",
            "semantic_sha256",
            "schema_version",
        )
    )
    head_columns = {
        column["name"] for column in inspector.get_columns("recognition_preview_heads")
    }
    assert {"project_id", "revision_id", "version", "terminal_result_id"} <= head_columns
    assert inspector.get_pk_constraint("recognition_preview_heads")["constrained_columns"] == ["project_id"]
    assert inspector.get_columns("recognition_preview_heads")[
        next(index for index, column in enumerate(
            inspector.get_columns("recognition_preview_heads")
        ) if column["name"] == "version")
    ]["nullable"] is False
    head_foreign_keys = {
        (
            tuple(constraint["constrained_columns"]),
            constraint["referred_table"],
            tuple(constraint["referred_columns"]),
        )
        for constraint in inspector.get_foreign_keys("recognition_preview_heads")
    }
    assert head_foreign_keys >= {
        (("project_id",), "projects", ("id",)),
        (("revision_id",), "recognition_preview_revisions", ("id",)),
        (("terminal_result_id",), "automatic_results", ("id",)),
    }
    head_column_details = {
        column["name"]: column
        for column in inspector.get_columns("recognition_preview_heads")
    }
    assert all(
        head_column_details[column]["nullable"] is False
        for column in ("project_id", "revision_id", "version")
    )
    with engine.connect() as connection:
        revision_triggers = set(
            connection.scalars(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'recognition_preview_revisions'::regclass "
                    "AND NOT tgisinternal"
                )
            )
        )
    assert revision_triggers == {"prevent_recognition_preview_revision_update_delete"}


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
    project, _, _ = _seed_project(preview_context)
    alternate_bytes = b"%PDF-1.7\\nwrong-source\\n"
    alternate = preview_context.storage.write_verified(
        f"projects/{project.id}/alternate.pdf",
        alternate_bytes,
        sha256(alternate_bytes).hexdigest(),
    )
    alternate_source = StoredFile(
        resource_ref=alternate.resource_ref,
        sha256=alternate.sha256,
        size_bytes=alternate.size_bytes,
        mime_type="application/pdf",
    )
    preview_context.session.add(alternate_source)
    preview_context.session.commit()
    service = _preview_service(preview_context.session, project.id)
    revision = service.publish_local(
        source_file_id=alternate_source.id,
        snapshot=_local_snapshot(),
    )

    first = preview_context.client.get(
        f"/api/v1/projects/{project.id}/recognition-preview"
    )
    assert first.status_code == 200
    assert first.json() == {
        "revision": 1,
        "stage": "local_ready",
        "source_pdf_url": f"/api/v1/projects/{project.id}/source-pdf",
        "semantic_snapshot": revision.semantic_snapshot,
        "counts": _local_snapshot()["counts"],
    }
    source_response = preview_context.client.get(first.json()["source_pdf_url"])
    assert source_response.status_code == 200
    assert source_response.content == alternate_bytes
    assert preview_context.session.scalar(
        select(func.count()).select_from(ReviewWorkingCopy).where(
            ReviewWorkingCopy.project_id == project.id
        )
    ) == 0
    preview_context.session.expire_all()
    reconnected_session = Session(
        bind=preview_context.session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    original_session_override = app.dependency_overrides[get_session]

    def override_reconnected_session() -> Iterator[Session]:
        yield reconnected_session

    app.dependency_overrides[get_session] = override_reconnected_session
    try:
        with TestClient(app) as reconnected_client:
            second = reconnected_client.get(
                f"/api/v1/projects/{project.id}/recognition-preview"
            )
            second_source_response = reconnected_client.get(
                second.json()["source_pdf_url"]
            )
            workbench_response = reconnected_client.get(
                f"/api/v1/projects/{project.id}/workbench"
            )
            reconnected_working_copy_count = reconnected_session.scalar(
                select(func.count()).select_from(ReviewWorkingCopy).where(
                    ReviewWorkingCopy.project_id == project.id
                )
            )
    finally:
        app.dependency_overrides[get_session] = original_session_override
        reconnected_session.close()

    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["revision"] == 1
    assert second_source_response.content == alternate_bytes
    assert workbench_response.status_code == 409
    assert reconnected_working_copy_count == 0


def test_preview_project_still_has_no_workbench_without_real_working_copy(
    preview_context: PreviewContext,
) -> None:
    """Catches preview routing that silently synthesizes a ReviewWorkingCopy."""
    project, _, _ = _seed_project(preview_context)

    response = preview_context.client.get(
        f"/api/v1/projects/{project.id}/workbench"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_workbench_unavailable"
    assert preview_context.session.scalar(
        select(func.count()).select_from(ReviewWorkingCopy).where(
            ReviewWorkingCopy.project_id == project.id
        )
    ) == 0
