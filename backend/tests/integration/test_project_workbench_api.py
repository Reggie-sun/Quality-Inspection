from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.exports.models import ExportJob
from app.exports.service import ExportService
from app.main import app
from app.projects.router import get_session as get_project_session
from app.projects.router import get_storage
from app.review.models import ReviewedResult
from app.storage.models import StoredFile


_BALLOON_TEST_MODULE = "_qi_test_balloon_service"
_balloon_test_spec = importlib.util.spec_from_file_location(
    _BALLOON_TEST_MODULE,
    Path(__file__).with_name("test_balloon_service.py"),
)
assert _balloon_test_spec is not None and _balloon_test_spec.loader is not None
_balloon_test_module = importlib.util.module_from_spec(_balloon_test_spec)
sys.modules[_BALLOON_TEST_MODULE] = _balloon_test_module
_balloon_test_spec.loader.exec_module(_balloon_test_module)
make_balloon_context = _balloon_test_module.make_balloon_context


def _valid_source_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((20, 20), "Task 4 workbench recovery")
    content = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    return content


def test_project_workbench_delivers_real_pdf_without_internal_references(
    tmp_path: Path,
) -> None:
    """P0-UI-005/P0-UI-008 bootstrap one aggregate and controlled PDF bytes."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=True)
    generated = context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    expected_pdf = context.storage.read_bytes(
        f"asset://projects/{context.working_copy.project_id}/source.pdf"
    )

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_project_session] = override_session
    app.dependency_overrides[get_storage] = lambda: context.storage
    try:
        client = TestClient(app)
        base = f"/api/v1/projects/{context.working_copy.project_id}"
        export_count_before = session.scalar(
            select(func.count()).select_from(ExportJob)
        )
        reviewed_count_before = session.scalar(
            select(func.count()).select_from(ReviewedResult)
        )

        response = client.get(f"{base}/workbench")

        assert response.status_code == 200
        payload = response.json()
        assert payload["project"] == {
            "id": str(context.working_copy.project_id),
            "state": "editing",
            "version": 1,
        }
        assert payload["working_copy"]["id"] == str(context.working_copy.id)
        assert payload["working_copy"]["version"] == context.working_copy.version
        assert payload["source_pdf_url"] == f"{base}/source-pdf"
        assert payload["pages"] == [
            {
                "page_index": 0,
                "width": 200.0,
                "height": 200.0,
                "pdf_to_render_matrix": [1, 0, 0, 1, 0, 0],
                "render_to_pdf_matrix": [1, 0, 0, 1, 0, 0],
            }
        ]
        assert payload["candidates"][0]["item_id"] == "i1"
        assert payload["sources"][0]["item_ids"] == ["i1"]
        assert payload["balloons"][0]["inspection_item_id"] == "i1"
        assert {value["id"] for value in payload["balloons"]} == {
            str(value.id) for value in generated
        }
        assert payload["reviewed_result_id"] is None
        assert payload["latest_export"] is None
        assert session.scalar(select(func.count()).select_from(ExportJob)) == (
            export_count_before
        )
        assert session.scalar(select(func.count()).select_from(ReviewedResult)) == (
            reviewed_count_before
        )
        serialized = response.text
        assert "resource_ref" not in serialized
        assert "asset://" not in serialized
        assert str(tmp_path) not in serialized

        source = client.get(payload["source_pdf_url"])
        assert source.status_code == 200
        assert source.content == expected_pdf
        assert source.headers["content-type"] == "application/pdf"
        assert "content-disposition" not in source.headers
        assert "asset://" not in str(source.headers)

        missing = client.get(f"/api/v1/projects/00000000-0000-0000-0000-000000000000/workbench")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "project_not_found"
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_project_workbench_recovers_reviewed_result_and_latest_atomic_export(
    tmp_path: Path,
) -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=True)
    raw = session.get(AutomaticResult, context.working_copy.raw_result_id)
    assert raw is not None
    source = session.get(StoredFile, raw.source_file_id)
    assert source is not None
    source_bytes = _valid_source_pdf()
    stored = context.storage.write_verified(
        source.resource_ref.removeprefix("asset://"),
        source_bytes,
        hashlib.sha256(source_bytes).hexdigest(),
    )
    source.sha256 = stored.sha256
    source.size_bytes = stored.size_bytes
    session.commit()
    context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    reviewed = context.review_service.confirm(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    exported = ExportService(session, storage=context.storage).create(reviewed.id)
    assert exported.status == "success"

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_project_session] = override_session
    app.dependency_overrides[get_storage] = lambda: context.storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/projects/{context.working_copy.project_id}/workbench"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["reviewed_result_id"] == str(reviewed.id)
        latest = payload["latest_export"]
        assert {
            key: latest[key]
            for key in (
                "id",
                "project_id",
                "reviewed_result_id",
                "status",
                "error_id",
            )
        } == {
            "id": str(exported.id),
            "project_id": str(reviewed.project_id),
            "reviewed_result_id": str(reviewed.id),
            "status": "success",
            "error_id": None,
        }
        assert [artifact["kind"] for artifact in latest["artifacts"]] == [
            "ballooned_pdf",
            "sip_excel",
            "manifest",
        ]
        assert len(latest["artifacts"]) == 3
        for artifact in latest["artifacts"]:
            assert set(artifact) == {
                "kind",
                "sha256",
                "size_bytes",
                "reviewed_result_id",
                "downloadable",
            }
            assert artifact["sha256"]
            assert artifact["size_bytes"] > 0
            assert artifact["reviewed_result_id"] == str(reviewed.id)
            assert artifact["downloadable"] is True
        assert session.scalar(
            select(func.count()).select_from(ExportJob)
        ) == 1
        assert session.get(ReviewedResult, reviewed.id) is reviewed
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()
