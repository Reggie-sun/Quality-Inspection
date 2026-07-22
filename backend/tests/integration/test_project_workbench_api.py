from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.projects.router import get_session as get_project_session
from app.projects.router import get_storage
from tests.integration.test_balloon_service import make_balloon_context


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
