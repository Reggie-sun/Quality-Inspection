from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import fitz
import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balloons.service import BalloonService
from app.candidates.models import AutomaticResult
from app.capabilities.service import ExportPreflight
from app.db import engine
from app.errors.models import ErrorRecord
from app.exports.models import ExportArtifact, ExportJob
from app.exports.router import _content_disposition
from app.exports.service import ExportInProgress, ExportService
from app.exports.template_registry import load_template_registration
from app.jobs.idempotency import LogicalJob, claim_logical_job
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.models import ReviewedResult
from app.review.service import ReviewService
from app.storage.local import LocalFileStorage
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


def _source_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((20, 20), "D6-T3 export fixture")
    content = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    return content


def _export_metadata() -> dict[str, object]:
    return {
        "material_code": "MAT-001",
        "material_name": "上座",
        "drawing_number": "JS26032501",
        "material": "SUS304",
        "revision": "A1",
    }


def _confirmed_export_items() -> list[dict[str, object]]:
    return [
        {
            "item_id": "i1",
            "inspection_item": "10 +/- 0.1",
            "inspection_standard": "9.9 <= x <= 10.1",
            "inspection_method": "caliper",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
        },
        {
            "item_id": "i2",
            "inspection_item": "deburr",
            "inspection_standard": "no sharp edge",
            "inspection_method": "visual",
            "key_dimension": "no",
            "inspection_role": "FQC",
            "source_page": 1,
        },
    ]


def _prepare_sip_review(
    service: ReviewService,
    working,
) -> object:
    current = working
    for item in _confirmed_export_items():
        current = service.apply(
            current.id,
            expected_version=current.version,
            operator_id="quality-1",
            command={"type": "set_sip_detail_fields", **item},
        )
    return service.apply(
        current.id,
        expected_version=current.version,
        operator_id="quality-1",
        command={"type": "set_sip_metadata", **_export_metadata()},
    )


@pytest.fixture
def reviewed_result(
    db_session: Session,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> tuple[ReviewedResult, LocalFileStorage]:
    one_sided_tolerance = getattr(request, "param", None) is True
    project_id = uuid.uuid4()
    source_bytes = _source_pdf()
    storage = LocalFileStorage(tmp_path / "storage")
    stored = storage.write_verified(
        f"projects/{project_id}/drawing.pdf",
        source_bytes,
        hashlib.sha256(source_bytes).hexdigest(),
    )
    inventory_bytes = json.dumps(
        {
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
                        }
                    ],
                }
            ],
        },
        sort_keys=True,
    ).encode("utf-8")
    inventory = storage.write_verified(
        f"projects/{project_id}/inventory.json",
        inventory_bytes,
        hashlib.sha256(inventory_bytes).hexdigest(),
    )
    project = Project(id=project_id, state=ProjectState.READY_FOR_EDIT)
    source_file = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    logical_job = LogicalJob(
        project_id=str(project_id),
        logical_task_key=f"automatic:{project_id}",
        status="succeeded",
        result_ref=f"automatic-result://{project_id}",
    )
    db_session.add_all([project, source_file, logical_job])
    db_session.flush()
    raw = AutomaticResult(
        project_id=project_id,
        source_file_id=source_file.id,
        logical_job_id=logical_job.id,
        inventory_ref=inventory.resource_ref,
        candidates=[
            {
                "candidate_id": "i1",
                "payload": {
                    "candidate_id": "i1",
                    "item_type": "linear_dimension",
                    "raw_text": "unconfirmed automatic value",
                    "normalized_text": "10 +/- 0.1",
                    "coordinates": [20, 20, 40, 40],
                    "scope": "local_feature",
                    "balloon_required": True,
                    "requires_confirmation": False,
                    **(
                        {"upper_tolerance": "0.2"}
                        if one_sided_tolerance
                        else {}
                    ),
                },
                "source_location_ids": ["s1"],
            },
            {
                "candidate_id": "i2",
                "payload": {
                    "candidate_id": "i2",
                    "item_type": "general_requirement",
                    "raw_text": "unconfirmed automatic requirement",
                    "normalized_text": "deburr",
                    "coordinates": [50, 50, 80, 80],
                    "scope": "global_requirement",
                    "balloon_required": False,
                    "requires_confirmation": False,
                },
                "source_location_ids": [],
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
    db_session.add(raw)
    db_session.commit()
    review_service = ReviewService(db_session, storage=storage)
    working = review_service.create_from_raw(raw.id)
    acquire_lock(db_session, project_id, "quality-1")
    for item_id in ("i1", "i2"):
        working = review_service.apply(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
            command={"type": "keep", "item_id": item_id},
        )
    working = _prepare_sip_review(review_service, working)
    frozen = review_service.freeze_items(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
    )
    BalloonService(db_session, storage=storage).generate_formal(
        project_id,
        expected_version=frozen.version,
        operator_id="quality-1",
    )
    reviewed = review_service.confirm(
        frozen.id,
        expected_version=frozen.version,
        operator_id="quality-1",
    )
    return reviewed, storage


class _FailingPublishStorage(LocalFileStorage):
    def write_verified(
        self,
        relative_path: str,
        content: bytes,
        expected_sha256: str,
    ):
        if relative_path.startswith("exports/") and not relative_path.startswith(
            "exports/.staging/"
        ):
            raise OSError("injected publish failure")
        return super().write_verified(relative_path, content, expected_sha256)


def _raise_injected(*_args, **_kwargs):
    raise RuntimeError("injected artifact failure")


def _service(
    db_session: Session,
    storage: LocalFileStorage,
    failure_point: str | None = None,
) -> ExportService:
    kwargs: dict[str, object] = {}
    if failure_point == "pdf":
        kwargs["pdf_renderer"] = _raise_injected
    elif failure_point == "excel":
        kwargs["excel_renderer"] = _raise_injected
    elif failure_point == "manifest":
        kwargs["manifest_serializer"] = _raise_injected
    elif failure_point == "publish":
        storage = _FailingPublishStorage(storage.root)
    return ExportService(db_session, storage=storage, **kwargs)


@pytest.mark.parametrize("failure_point", ["pdf", "excel", "manifest", "publish"])
def test_no_artifact_is_downloadable_after_subartifact_failure(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
    failure_point: str,
) -> None:
    """P0-EXP-009 exposes zero downloads after any subartifact failure."""
    reviewed, storage = reviewed_result
    service = _service(db_session, storage, failure_point)

    export = service.create(reviewed.id)

    assert export.status == "failed"
    assert export.error_id is not None
    assert db_session.get(ErrorRecord, export.error_id) is not None
    assert db_session.scalar(
        select(func.count())
        .select_from(ErrorRecord)
        .where(ErrorRecord.project_id == reviewed.project_id)
    ) == 1
    artifacts = list(
        db_session.scalars(
            select(ExportArtifact).where(ExportArtifact.export_id == export.id)
        )
    )
    assert all(artifact.published_ref is None for artifact in artifacts)
    for kind in ("ballooned_pdf", "sip_excel", "manifest"):
        assert service.download_ref(export.id, kind) is None


@pytest.mark.parametrize("reviewed_result", [True], indirect=True)
def test_one_sided_tolerance_fails_before_export_artifacts_are_staged(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
) -> None:
    """Catches an incomplete reviewed tolerance that reaches any publish stage."""
    reviewed, storage = reviewed_result

    with pytest.raises(ValueError, match="one-sided structured tolerance"):
        _service(db_session, storage).create(reviewed.id)

    assert db_session.scalar(select(func.count()).select_from(ExportJob)) == 0
    assert not (storage.root / "exports").exists()


def test_export_passes_v3_workbook_metadata_after_pdf_validation(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
) -> None:
    """Catches v3 header metadata being built before PDF validation or from SIP metadata."""
    reviewed, storage = reviewed_result
    captured: dict[str, object] = {}

    def capture_renderer(
        _template_path: Path,
        _registration: object,
        metadata: dict[str, object],
        _rows: list[dict[str, object]],
        page_images: list[Path],
    ) -> bytes:
        captured["metadata"] = metadata
        captured["page_images"] = page_images
        raise RuntimeError("stop after v3 workbook metadata capture")

    export = ExportService(
        db_session,
        storage=storage,
        excel_renderer=capture_renderer,
    ).create(reviewed.id)

    assert export.status == "failed"
    assert export.created_at is not None
    assert captured["metadata"] == {
        "source_filename": "drawing.pdf",
        "inspection_date": export.created_at.astimezone(
            ZoneInfo("Asia/Hong_Kong")
        ).strftime("%Y-%m-%d %H:%M"),
        "toleranced_count": 0,
        "page_count": 1,
        "detail_count": 2,
        "unit": "mm / 按项目",
        "general_tolerance_note": "【未注公差标准】未确认",
    }
    assert len(captured["page_images"]) == 1


def test_success_exposes_exactly_three_verified_downloads(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
) -> None:
    """P0-EXP-009 publishes exactly three artifacts after every gate passes."""
    reviewed, storage = reviewed_result
    service = _service(db_session, storage)

    export = service.create(reviewed.id)

    assert export.status == "success"
    artifacts = list(
        db_session.scalars(
            select(ExportArtifact)
            .where(ExportArtifact.export_id == export.id)
            .order_by(ExportArtifact.kind)
        )
    )
    assert {artifact.kind for artifact in artifacts} == {
        "ballooned_pdf",
        "sip_excel",
        "manifest",
    }
    assert {artifact.reviewed_result_id for artifact in artifacts} == {reviewed.id}
    assert all(artifact.published_ref for artifact in artifacts)
    assert all(
        service.download_ref(export.id, artifact.kind) == artifact.published_ref
        for artifact in artifacts
    )
    manifest_ref = service.download_ref(export.id, "manifest")
    assert manifest_ref is not None
    manifest = json.loads(storage.read_bytes(manifest_ref))
    assert manifest["schema_version"] == "export-manifest/2"
    assert manifest["confidence_policy_versions"] == []
    assert manifest["auto_accepted_item_count"] == 0
    assert manifest["manual_override_item_count"] == 0
    assert manifest["reviewed_result_id"] == str(reviewed.id)
    assert {
        artifact["reviewed_result_id"] for artifact in manifest["artifacts"]
    } == {str(reviewed.id)}

    excel_ref = service.download_ref(export.id, "sip_excel")
    assert excel_ref is not None
    backend_root = Path(__file__).resolve().parents[2]
    registration = load_template_registration(
        backend_root / "assets/templates/sip-v1.xlsx",
        backend_root / "assets/templates/sip-v1.mapping.json",
    )
    workbook = load_workbook(BytesIO(storage.read_bytes(excel_ref)), data_only=False)
    try:
        sheet = workbook[registration.sheet]
        for field, address in registration.metadata_cells.items():
            assert sheet[address].value == str(_export_metadata()[field])
        for row_offset, item in enumerate(_confirmed_export_items()):
            for field, column in registration.detail_columns.items():
                expected = "1" if field == "balloon_number" and row_offset == 0 else ""
                if field != "balloon_number":
                    expected = str(item[field])
                assert sheet[f"{column}{registration.first_row + row_offset}"].value == (
                    expected or None
                )
    finally:
        workbook.close()


def test_export_preflight_runs_before_status_running(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
) -> None:
    """P0-EXP-009 runs the existing ExportPreflight before running state."""
    reviewed, storage = reviewed_result
    backend_root = Path(__file__).resolve().parents[2]
    real_preflight = ExportPreflight(
        template_path=backend_root / "assets/templates/sip-v1.xlsx",
        mapping_path=backend_root / "assets/templates/sip-v1.mapping.json",
        font_path=backend_root / "assets/fonts/DejaVuSans.ttf",
        font_license_path=backend_root / "assets/fonts/LICENSE-DejaVu.txt",
    )
    observed_running_counts: list[int] = []

    class ObservingPreflight:
        def check(self):
            observed_running_counts.append(
                db_session.scalar(
                    select(func.count())
                    .select_from(ExportJob)
                    .where(ExportJob.status == "running")
                )
                or 0
            )
            return real_preflight.check()

    service = ExportService(
        db_session,
        storage=storage,
        preflight=ObservingPreflight(),
    )

    export = service.create(reviewed.id)

    assert observed_running_counts == [0]
    assert export.status == "success"


def test_logical_export_claim_has_one_execution_owner(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
) -> None:
    """P0-EXP-009 permits only one runner past the logical export claim."""
    reviewed, storage = reviewed_result
    logical_job = claim_logical_job(
        db_session,
        project_id=str(reviewed.project_id),
        logical_task_key=ExportService._logical_task_key(reviewed.id),
    )
    first = ExportService(db_session, storage=storage)
    second = ExportService(db_session, storage=storage)

    assert first._claim_execution(logical_job, reviewed.id) is None
    db_session.expire_all()
    contender = db_session.get(LogicalJob, logical_job.id)
    assert contender is not None
    with pytest.raises(ExportInProgress):
        second._claim_execution(contender, reviewed.id)


def test_unicode_download_filename_has_rfc5987_fallback() -> None:
    """P0-EXP-009 keeps successful Unicode artifact downloads serializable."""
    header = _content_disposition("上座-sip.xlsx")

    assert header.encode("latin-1")
    assert 'filename="-sip.xlsx"' not in header
    assert 'filename="_-' not in header
    assert "filename*=UTF-8''%E4%B8%8A%E5%BA%A7-sip.xlsx" in header


def test_latest_export_for_project_uses_created_at_then_id_descending(
    db_session: Session,
    reviewed_result: tuple[ReviewedResult, LocalFileStorage],
) -> None:
    reviewed, storage = reviewed_result
    created_at = datetime(2026, 7, 23, 5, 0, tzinfo=timezone.utc)
    older = ExportJob(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        project_id=reviewed.project_id,
        reviewed_result_id=reviewed.id,
        status="failed",
        template_version="1",
        mapping_version="1",
        renderer_version="balloon-pdf/1",
        created_at=datetime(2026, 7, 23, 4, 59, tzinfo=timezone.utc),
    )
    same_time_lower_id = ExportJob(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        project_id=reviewed.project_id,
        reviewed_result_id=reviewed.id,
        status="failed",
        template_version="1",
        mapping_version="1",
        renderer_version="balloon-pdf/1",
        created_at=created_at,
    )
    same_time_higher_id = ExportJob(
        id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        project_id=reviewed.project_id,
        reviewed_result_id=reviewed.id,
        status="running",
        template_version="1",
        mapping_version="1",
        renderer_version="balloon-pdf/1",
        created_at=created_at,
    )
    db_session.add_all([older, same_time_lower_id, same_time_higher_id])
    db_session.commit()

    service = ExportService(db_session, storage=storage)

    assert service.latest_for_project(reviewed.project_id) is same_time_higher_id
    assert service.latest_for_project(uuid.uuid4()) is None
