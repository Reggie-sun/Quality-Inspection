from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Iterator, Mapping
from hashlib import sha256
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.candidates.advisor import CandidateAdvisorFailure
from app.candidates.models import AutomaticResult
from app.config import Settings
from app.db import SessionLocal, engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob, set_processing_stage
from app.processing import tasks
from app.processing.pipeline import InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewService
from app.providers.base import VisionResult
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


class PassingPreflight:
    def check(self) -> None:
        return None


@pytest.fixture
def database_connection() -> Iterator[Connection]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    try:
        yield connection
    finally:
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def task_session_factory(
    database_connection: Connection,
) -> Callable[[], Session]:
    def factory() -> Session:
        return Session(
            bind=database_connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

    return factory


def _write_candidate_pdf(path: Path, raw_text: str = "M6") -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    page.insert_text((20.0, 30.0), raw_text)
    document.save(path)
    document.close()
    return path.read_bytes()


def _project_source(
    session: Session,
    storage: LocalFileStorage,
    tmp_path: Path,
    *,
    raw_text: str = "M6",
) -> tuple[Project, StoredFile]:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    content = _write_candidate_pdf(
        tmp_path / f"{project.id}.pdf",
        raw_text,
    )
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
    session.add_all([project, source_file])
    session.commit()
    return project, source_file


def _project_source_with_routing_identity(
    session: Session,
    storage: LocalFileStorage,
    tmp_path: Path,
    *,
    recognition_mode: str,
    recognition_router_version: str,
) -> tuple[Project, StoredFile]:
    project = Project(
        id=uuid.uuid4(),
        state=ProjectState.PROCESSING,
        recognition_mode=recognition_mode,
        recognition_router_version=recognition_router_version,
    )
    content = _write_candidate_pdf(tmp_path / f"{project.id}.pdf")
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
    session.add_all([project, source_file])
    session.commit()
    return project, source_file


def _configure_task(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_factory: Callable[[], Session],
    storage_root: Path,
    external_calls: list[str],
) -> None:
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(storage_root=storage_root),
    )
    monkeypatch.setattr(
        tasks,
        "ProcessingPreflight",
        lambda *_args, **_kwargs: PassingPreflight(),
    )
    monkeypatch.setattr(tasks.Redis, "from_url", lambda *_args, **_kwargs: object())

    def forbidden_provider_factory(_settings: Settings):
        external_calls.append("ocr-provider")
        raise AssertionError("vector processing must not construct the OCR Provider")

    monkeypatch.setattr(tasks, "OCR_PROVIDER_FACTORY", forbidden_provider_factory)

    def forbidden_vision_provider_factory(_settings: Settings):
        external_calls.append("vision-provider")
        raise AssertionError("clear candidate must not construct the Vision Provider")

    monkeypatch.setattr(
        tasks,
        "VISION_PROVIDER_FACTORY",
        forbidden_vision_provider_factory,
    )


def _counts(session: Session, project_id: uuid.UUID) -> dict[str, int]:
    return {
        "raw": session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project_id)
        ),
        "job": session.scalar(
            select(func.count())
            .select_from(LogicalJob)
            .where(LogicalJob.project_id == str(project_id))
        ),
        "working": session.scalar(
            select(func.count())
            .select_from(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.project_id == project_id)
        ),
        "error": session.scalar(
            select(func.count())
            .select_from(ErrorRecord)
            .where(ErrorRecord.project_id == project_id)
        ),
    }


def test_canonical_task_creates_one_review_working_copy_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(setup, storage, tmp_path)
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    key = f"product-process:{project.id}"

    first = inventory_project.run(str(project.id), source.resource_ref, key)
    second = inventory_project.run(str(project.id), source.resource_ref, key)

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        working = verify.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == project.id
            )
        )
        job = verify.scalar(
            select(LogicalJob).where(LogicalJob.project_id == str(project.id))
        )
        assert raw is not None
        assert working is not None
        assert job is not None
        assert first == second == f"automatic-result://{raw.id}"
        assert working.raw_result_id == raw.id
        assert verify.get(Project, project.id).state == ProjectState.EDITING
        assert job.status == "succeeded"
        assert job.result_ref == first
        assert _counts(verify, project.id) == {
            "raw": 1,
            "job": 1,
            "working": 1,
            "error": 0,
        }
        assert external_calls == []
        assert inventory_project.name == "quality_inspection.inventory_project"
        assert tuple(inspect.signature(inventory_project.run).parameters) == (
            "project_id",
            "source_ref",
            "logical_task_key",
        )
    finally:
        verify.close()


def test_worker_uses_frozen_project_mode_after_settings_change(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source_with_routing_identity(
        setup,
        storage,
        tmp_path,
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    seen_modes: list[tuple[str, str]] = []
    original_advisor = tasks.CandidateAdvisor
    original_recognition = tasks.RuntimeRecognition

    def recording_advisor(settings: Settings, *args, **kwargs):
        seen_modes.append(("advisor", settings.symbol_recognition_mode))
        return original_advisor(settings, *args, **kwargs)

    def recording_recognition(settings: Settings, *args, **kwargs):
        seen_modes.append(("recognition", settings.symbol_recognition_mode))
        return original_recognition(settings, *args, **kwargs)

    monkeypatch.setattr(tasks, "CandidateAdvisor", recording_advisor)
    monkeypatch.setattr(tasks, "RuntimeRecognition", recording_recognition)

    inventory_project.run(
        str(project.id),
        source.resource_ref,
        f"product-process:{project.id}",
    )

    assert seen_modes == [
        ("advisor", "production_uncertainty"),
        ("recognition", "production_uncertainty"),
    ]
    assert external_calls == []


def test_task_injects_one_session_bound_preview_sink_into_candidate_advisor(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    """Catches task wiring that bypasses the persistence-only preview Owner."""
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source_with_routing_identity(
        setup,
        storage,
        tmp_path,
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    preview_sinks: list[RecordingPreviewService] = []
    local_submissions: list[tuple[uuid.UUID, Mapping[str, object]]] = []
    terminal_result_ids: list[uuid.UUID] = []

    class RecordingPreviewService:
        def __init__(self, session: Session, *, project_id: uuid.UUID) -> None:
            assert session.bind is not None
            assert project_id == project.id
            preview_sinks.append(self)

        def publish_local(
            self,
            *,
            source_file_id: uuid.UUID,
            snapshot: Mapping[str, object],
        ) -> object:
            assert set(snapshot) == {
                "schema_version",
                "stage",
                "candidates",
                "sources",
                "counts",
            }
            assert set(snapshot["counts"]) == {
                "local_resolved",
                "cache_resolved",
                "vlm_pending",
                "vlm_resolved",
                "unresolved",
            }
            candidates = snapshot["candidates"]
            sources = snapshot["sources"]
            assert isinstance(candidates, list)
            assert isinstance(sources, list)
            assert all(
                set(candidate) == {"candidate_id", "kind", "label"}
                for candidate in candidates
            )
            assert all(
                set(source) == {
                    "source_location_id",
                    "source_type",
                    "page_index",
                    "raw_text",
                }
                for source in sources
            )
            local_submissions.append((source_file_id, snapshot))
            return type("PreviewRevision", (), {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000701"),
                "revision": 1,
            })()

        def append_enrichment(
            self,
            *,
            expected_head_version: int,
            parent_revision_id: uuid.UUID,
            snapshot: Mapping[str, object],
        ) -> object:
            del expected_head_version, parent_revision_id, snapshot
            return object()

        def supersede_with_terminal(
            self,
            *,
            automatic_result_id: uuid.UUID,
        ) -> None:
            terminal_result_ids.append(automatic_result_id)

    original_advisor = tasks.CandidateAdvisor

    def recording_advisor(*args, **kwargs):
        preview_sink = kwargs["preview_sink"]
        assert isinstance(preview_sink, tasks._VisibleRecognitionPreviewSink)
        assert preview_sink._project_id == project.id
        return original_advisor(*args, **kwargs)

    monkeypatch.setattr(tasks, "RecognitionPreviewService", RecordingPreviewService)
    monkeypatch.setattr(tasks, "CandidateAdvisor", recording_advisor)

    logical_task_key = f"preview-process:{project.id}"
    first_result = inventory_project.run(
        str(project.id),
        source.resource_ref,
        logical_task_key,
    )
    retry_result = inventory_project.run(
        str(project.id),
        source.resource_ref,
        logical_task_key,
    )

    assert len(preview_sinks) == 2
    assert local_submissions and local_submissions[0][0] == source.id
    assert len(local_submissions) == 1
    assert len(terminal_result_ids) == 1
    assert first_result == retry_result
    assert external_calls == []


def test_task_preview_composition_commits_each_preview_before_provider_stage() -> None:
    """Catches task-owned preview writes hidden from the next-stage Session."""
    bootstrap = SessionLocal()
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    source = StoredFile(
        resource_ref=f"asset://tests/{project.id}/preview-source.pdf",
        sha256="3" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )
    logical_task_key = f"preview-visible:{project.id}"
    job = LogicalJob(
        project_id=str(project.id),
        logical_task_key=logical_task_key,
        status="processing",
        processing_stage="recognizing",
    )
    snapshot = {
        "schema_version": "recognition-preview/1",
        "stage": "local_ready",
        "candidates": [
            {"candidate_id": "candidate-1", "kind": "thread", "label": "M6"}
        ],
        "sources": [
            {
                "source_location_id": "source-1",
                "source_type": "native",
                "page_index": 0,
                "raw_text": "M6",
            }
        ],
        "counts": {
            "local_resolved": 1,
            "cache_resolved": 0,
            "vlm_pending": 0,
            "vlm_resolved": 0,
            "unresolved": 0,
        },
    }
    try:
        bootstrap.add_all([project, source, job])
        bootstrap.commit()
        sink = tasks._VisibleRecognitionPreviewSink(
            SessionLocal,
            project_id=project.id,
            logical_task_key=logical_task_key,
        )
        local = sink.publish_local(source_file_id=source.id, snapshot=snapshot)

        # This is the provider-stage callback's independent Session.
        observer = SessionLocal()
        try:
            from app.processing.recognition_preview import RecognitionPreviewService

            observed_local = RecognitionPreviewService(
                observer, project_id=project.id
            ).head()
            assert observed_local.id == local.id
            assert observed_local.revision == 1
            observed_job = observer.scalar(
                select(LogicalJob).where(
                    LogicalJob.project_id == str(project.id),
                    LogicalJob.logical_task_key == logical_task_key,
                )
            )
            assert observed_job is not None
            assert observed_job.processing_stage == "local_ready"
        finally:
            observer.close()

        enriched = sink.append_enrichment(
            expected_head_version=local.revision,
            parent_revision_id=local.id,
            snapshot={
                **snapshot,
                "stage": "vlm_enriching",
                "counts": {**snapshot["counts"], "vlm_resolved": 1},
            },
        )
        observer = SessionLocal()
        try:
            from app.processing.recognition_preview import RecognitionPreviewService

            observed_enriched = RecognitionPreviewService(
                observer, project_id=project.id
            ).head()
            assert observed_enriched.id == enriched.id
            assert observed_enriched.revision == 2
            observed_job = observer.scalar(
                select(LogicalJob).where(
                    LogicalJob.project_id == str(project.id),
                    LogicalJob.logical_task_key == logical_task_key,
                )
            )
            assert observed_job is not None
            assert observed_job.processing_stage == "vlm_enriching"
        finally:
            observer.close()

        stage_session = SessionLocal()
        try:
            set_processing_stage(
                stage_session,
                job_id=job.id,
                stage="recognizing",
            )
        finally:
            stage_session.close()
        with pytest.raises(tasks.LogicalJobStateError):
            sink.append_enrichment(
                expected_head_version=enriched.revision,
                parent_revision_id=enriched.id,
                snapshot={**snapshot, "stage": "vlm_enriching"},
            )
        observer = SessionLocal()
        try:
            from app.processing.recognition_preview import RecognitionPreviewService

            assert RecognitionPreviewService(
                observer, project_id=project.id
            ).head().id == enriched.id
            observed_job = observer.scalar(
                select(LogicalJob).where(
                    LogicalJob.project_id == str(project.id),
                    LogicalJob.logical_task_key == logical_task_key,
                )
            )
            assert observed_job is not None
            assert observed_job.processing_stage == "recognizing"
        finally:
            observer.close()
    finally:
        bootstrap.close()


def test_pipeline_project_lock_allows_preview_fk_and_blocks_project_writers(
    tmp_path: Path,
) -> None:
    """Catches a Project FOR UPDATE lock that self-blocks preview FK insertion."""
    setup = SessionLocal()
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    source = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="4" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )
    logical_task_key = f"preview-project-lock:{project.id}"
    job = LogicalJob(
        project_id=str(project.id),
        logical_task_key=logical_task_key,
        status="processing",
        processing_stage="recognizing",
    )
    snapshot = {
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
    }
    lock_sql: list[str] = []

    def record_project_lock(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if "FROM projects" in statement and "FOR " in statement:
            lock_sql.append(statement)

    def timed_session() -> Session:
        session = SessionLocal()
        session.execute(text("SET LOCAL lock_timeout = '250ms'"))
        return session

    session_a = SessionLocal()
    try:
        setup.add_all([project, source, job])
        setup.commit()
        event.listen(engine, "before_cursor_execute", record_project_lock)
        pipeline = InventoryPipeline(
            session_a,
            LocalFileStorage(tmp_path / "storage"),
            PassingPreflight(),
        )
        assert pipeline._project(str(project.id), for_update=True).id == project.id

        sink = tasks._VisibleRecognitionPreviewSink(
            timed_session,
            project_id=project.id,
            logical_task_key=logical_task_key,
        )
        local = sink.publish_local(source_file_id=source.id, snapshot=snapshot)
        assert any("FOR NO KEY UPDATE" in statement for statement in lock_sql)

        observer = SessionLocal()
        try:
            from app.processing.recognition_preview import RecognitionPreviewService

            assert RecognitionPreviewService(
                observer, project_id=project.id
            ).head().id == local.id
            observed_job = observer.scalar(
                select(LogicalJob).where(LogicalJob.id == job.id)
            )
            assert observed_job is not None
            assert observed_job.processing_stage == "local_ready"
        finally:
            observer.close()

        writer = timed_session()
        try:
            with pytest.raises(OperationalError) as error:
                writer.execute(
                    update(Project)
                    .where(Project.id == project.id)
                    .values(state=ProjectState.EDITING)
                )
            assert getattr(error.value.orig, "sqlstate", None) == "55P03"
        finally:
            writer.rollback()
            writer.close()
    finally:
        event.remove(engine, "before_cursor_execute", record_project_lock)
        session_a.rollback()
        session_a.close()
        setup.close()


def test_worker_rejects_corrupt_frozen_pair_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source_with_routing_identity(
        setup,
        storage,
        tmp_path,
        recognition_mode="production_uncertainty",
        recognition_router_version="legacy",
    )
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )

    def forbidden_advisor(*_args, **_kwargs):
        external_calls.append("advisor-construction")
        raise AssertionError("corrupt mode must fail before advisor construction")

    monkeypatch.setattr(tasks, "CandidateAdvisor", forbidden_advisor)

    with pytest.raises(ValueError, match="router version"):
        inventory_project.run(
            str(project.id),
            source.resource_ref,
            f"product-process:{project.id}",
        )

    assert external_calls == []


def test_canonical_task_calls_vision_once_for_eligible_candidate(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(
        setup,
        storage,
        tmp_path,
        raw_text="Ra 3.2",
    )
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    vision_calls: list[str] = []

    class FakeVisionProvider:
        def review_candidate(self, _image: bytes, prompt: str) -> VisionResult:
            import json

            raw_text = str(json.loads(prompt)["raw_text"])
            vision_calls.append(raw_text)
            return VisionResult(
                request_id="fixture-qwen-request-id",
                payload={
                    "schema_version": "candidate-review/1",
                    "raw_text": raw_text,
                    "item_type": "roughness",
                    "normalized_text": raw_text,
                    "requires_confirmation": True,
                },
                usage={"total_tokens": 10},
            )

    monkeypatch.setattr(
        tasks,
        "VISION_PROVIDER_FACTORY",
        lambda _settings: FakeVisionProvider(),
    )
    observed_stages: list[str] = []
    original_snapshot_builder = RuntimeRecognition.build_candidate_snapshot

    def recording_snapshot_builder(
        recognition: RuntimeRecognition,
        pages,
        *,
        source_file_id: uuid.UUID | None = None,
    ):
        observer = task_session_factory()
        try:
            job = observer.scalar(
                select(LogicalJob).where(
                    LogicalJob.project_id == str(project.id)
                )
            )
            assert job is not None
            observed_stages.append(job.processing_stage)
        finally:
            observer.close()
        return original_snapshot_builder(
            recognition,
            pages,
            source_file_id=source_file_id,
        )

    monkeypatch.setattr(
        RuntimeRecognition,
        "build_candidate_snapshot",
        recording_snapshot_builder,
    )
    key = f"product-process:{project.id}"

    first_result_ref = inventory_project.run(
        str(project.id),
        source.resource_ref,
        key,
    )
    second_result_ref = inventory_project.run(
        str(project.id),
        source.resource_ref,
        key,
    )

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(
                AutomaticResult.project_id == project.id
            )
        )
        assert raw is not None
        completed_job = verify.scalar(
            select(LogicalJob).where(
                LogicalJob.project_id == str(project.id)
            )
        )
        assert completed_job is not None
        assert observed_stages == ["recognizing"]
        assert completed_job.processing_stage == "preparing_review"
        assert vision_calls == ["Ra 3.2"]
        assert raw.provider_call_ids == ["fixture-qwen-request-id"]
        assert raw.candidates[0]["advisor_review"]["validated"] is True
        assert second_result_ref == first_result_ref
        assert vision_calls == ["Ra 3.2"]
        assert external_calls == []
    finally:
        verify.close()


@pytest.mark.parametrize(
    ("provider_exception", "expected_category"),
    (
        (
            lambda private_detail: RuntimeError(private_detail),
            "transport",
        ),
        (
            lambda _private_detail: CandidateAdvisorFailure(
                "typed Provider response failure",
                failure_category="schema",
            ),
            "schema",
        ),
    ),
    ids=("generic-runtime", "typed-schema"),
)
def test_vision_failure_is_sanitized_without_result_layers(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
    provider_exception: Callable[[str], Exception],
    expected_category: str,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(
        setup,
        storage,
        tmp_path,
        raw_text="Ra 3.2",
    )
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    private_detail = "/srv/private/customer.pdf credential=do-not-leak"

    class FailingVisionProvider:
        def review_candidate(self, _image: bytes, _prompt: str) -> VisionResult:
            raise provider_exception(private_detail)

    monkeypatch.setattr(
        tasks,
        "VISION_PROVIDER_FACTORY",
        lambda _settings: FailingVisionProvider(),
    )

    with pytest.raises(CandidateAdvisorFailure) as raised:
        inventory_project.run(
            str(project.id),
            source.resource_ref,
            f"product-process:{project.id}",
        )
    assert raised.value.failure_category == expected_category

    verify = task_session_factory()
    try:
        error = verify.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        assert _counts(verify, project.id)["raw"] == 0
        assert _counts(verify, project.id)["working"] == 0
        assert error is not None
        assert error.code == "vision_provider_call_failed"
        assert error.stage == "candidate_advisor"
        assert error.cause_category == "transient_provider_failure"
        assert private_detail not in error.message
    finally:
        verify.close()


def test_review_bootstrap_failure_is_sanitized_durable_and_retry_safe(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(setup, storage, tmp_path)
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    original_create = ReviewService.create_from_raw
    private_detail = "/srv/private/customer.pdf credential=do-not-leak"

    def fail_bootstrap(_service: ReviewService, _raw_id: uuid.UUID):
        raise RuntimeError(private_detail)

    monkeypatch.setattr(ReviewService, "create_from_raw", fail_bootstrap)
    key = f"product-process:{project.id}"

    with pytest.raises(RuntimeError, match="do-not-leak"):
        inventory_project.run(str(project.id), source.resource_ref, key)
    with pytest.raises(RuntimeError, match="do-not-leak"):
        inventory_project.run(str(project.id), source.resource_ref, key)

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        job = verify.scalar(
            select(LogicalJob).where(LogicalJob.project_id == str(project.id))
        )
        error = verify.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        assert raw is not None
        assert job is not None
        assert job.status == "succeeded"
        assert job.result_ref == f"automatic-result://{raw.id}"
        assert verify.get(Project, project.id).state == ProjectState.READY_FOR_EDIT
        assert _counts(verify, project.id) == {
            "raw": 1,
            "job": 1,
            "working": 0,
            "error": 1,
        }
        assert error is not None
        assert error.code == "review_bootstrap_failed"
        assert error.message == "Review working copy could not be prepared"
        assert error.severity == "blocking"
        assert error.stage == "review_bootstrap"
        assert error.location_ref is None
        assert error.cause_category == "processing_defect"
        assert private_detail not in error.message
        assert external_calls == []
    finally:
        verify.close()

    monkeypatch.setattr(ReviewService, "create_from_raw", original_create)
    result_ref = inventory_project.run(str(project.id), source.resource_ref, key)

    recovered = task_session_factory()
    try:
        assert result_ref.startswith("automatic-result://")
        assert recovered.get(Project, project.id).state == ProjectState.EDITING
        assert _counts(recovered, project.id) == {
            "raw": 1,
            "job": 1,
            "working": 1,
            "error": 1,
        }
        assert external_calls == []
    finally:
        recovered.close()
