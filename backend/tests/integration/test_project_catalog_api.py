from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.projects.models import Project, ProjectLifecycleStatus
from app.projects.router import get_session
from app.projects.state import ProjectState


@dataclass(frozen=True)
class CatalogContext:
    client: TestClient
    session: Session


@pytest.fixture
def catalog_context() -> Iterator[CatalogContext]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield CatalogContext(client, session)
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def _project(
    project_id: str,
    *,
    filename: str | None,
    created_at: str,
    last_opened_at: str,
) -> Project:
    return Project(
        id=uuid.UUID(project_id),
        state=ProjectState.EDITING,
        source_filename=filename,
        created_at=datetime.fromisoformat(created_at),
        last_opened_at=datetime.fromisoformat(last_opened_at),
    )


def test_list_projects_returns_only_catalog_rows_in_last_opened_order(
    catalog_context: CatalogContext,
) -> None:
    older_id = "11111111-1111-4111-8111-111111111111"
    newer_id = "22222222-2222-4222-8222-222222222222"
    hidden_id = "33333333-3333-4333-8333-333333333333"
    catalog_context.session.add_all(
        [
            _project(
                older_id,
                filename="older.pdf",
                created_at="2026-07-30T01:00:00+00:00",
                last_opened_at="2026-07-30T02:00:00+00:00",
            ),
            _project(
                newer_id,
                filename="newer.pdf",
                created_at="2026-07-30T03:00:00+00:00",
                last_opened_at="2026-07-30T04:00:00+00:00",
            ),
            _project(
                hidden_id,
                filename=None,
                created_at="2026-07-30T05:00:00+00:00",
                last_opened_at="2026-07-30T06:00:00+00:00",
            ),
        ]
    )
    catalog_context.session.commit()

    response = catalog_context.client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "project_id": newer_id,
                "file_name": "newer.pdf",
                "created_at": "2026-07-30T03:00:00Z",
                "last_opened_at": "2026-07-30T04:00:00Z",
            },
            {
                "project_id": older_id,
                "file_name": "older.pdf",
                "created_at": "2026-07-30T01:00:00Z",
                "last_opened_at": "2026-07-30T02:00:00Z",
            },
        ],
        "count": 2,
    }


def test_mark_project_opened_updates_server_time_and_reorders_catalog(
    catalog_context: CatalogContext,
) -> None:
    selected_id = "11111111-1111-4111-8111-111111111111"
    other_id = "22222222-2222-4222-8222-222222222222"
    catalog_context.session.add_all(
        [
            _project(
                selected_id,
                filename="selected.pdf",
                created_at="2026-01-01T00:00:00+00:00",
                last_opened_at="2026-01-01T00:00:00+00:00",
            ),
            _project(
                other_id,
                filename="other.pdf",
                created_at="2026-01-02T00:00:00+00:00",
                last_opened_at="2026-01-02T00:00:00+00:00",
            ),
        ]
    )
    catalog_context.session.commit()

    response = catalog_context.client.post(
        f"/api/v1/projects/{selected_id}/open"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == selected_id
    assert payload["file_name"] == "selected.pdf"
    assert datetime.fromisoformat(payload["last_opened_at"]) > datetime(
        2026,
        1,
        2,
        tzinfo=UTC,
    )
    listed = catalog_context.client.get("/api/v1/projects").json()
    assert [item["project_id"] for item in listed["items"]] == [
        selected_id,
        other_id,
    ]


def test_mark_project_opened_rejects_non_catalog_project(
    catalog_context: CatalogContext,
) -> None:
    hidden_id = "33333333-3333-4333-8333-333333333333"
    catalog_context.session.add(
        _project(
            hidden_id,
            filename=None,
            created_at="2026-01-01T00:00:00+00:00",
            last_opened_at="2026-01-01T00:00:00+00:00",
        )
    )
    catalog_context.session.commit()

    response = catalog_context.client.post(
        f"/api/v1/projects/{hidden_id}/open"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"

    missing_response = catalog_context.client.post(
        "/api/v1/projects/44444444-4444-4444-8444-444444444444/open"
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "project_not_found"


def test_catalog_hides_non_active_lifecycle_versions(
    catalog_context: CatalogContext,
) -> None:
    active = _project(
        "11111111-1111-4111-8111-111111111111",
        filename="active.pdf",
        created_at="2026-01-01T00:00:00+00:00",
        last_opened_at="2026-01-01T00:00:00+00:00",
    )
    hidden = _project(
        "22222222-2222-4222-8222-222222222222",
        filename="hidden.pdf",
        created_at="2026-01-02T00:00:00+00:00",
        last_opened_at="2026-01-02T00:00:00+00:00",
    )
    hidden.lifecycle_status = ProjectLifecycleStatus.REPROCESSING
    hidden.predecessor_project_id = active.id
    catalog_context.session.add_all([active, hidden])
    catalog_context.session.commit()

    listed = catalog_context.client.get("/api/v1/projects")
    opened = catalog_context.client.post(f"/api/v1/projects/{hidden.id}/open")

    assert [item["project_id"] for item in listed.json()["items"]] == [
        str(active.id)
    ]
    assert opened.status_code == 404
    assert opened.json()["error"]["code"] == "project_not_found"
