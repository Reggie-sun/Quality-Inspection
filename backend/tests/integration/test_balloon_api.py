from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.balloons.router import (
    get_balloon_service,
    get_session as get_balloon_session,
)
from app.db import engine
from app.main import app
from app.review.router import get_review_service, get_session as get_review_session
from tests.integration.test_balloon_service import make_balloon_context


def test_balloon_routes_require_lock_version_and_explicit_confirm(
    tmp_path: Path,
) -> None:
    """Balloon HTTP mutations preserve the canonical lock/version/confirm boundary."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=True)

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_balloon_session] = override_session
    app.dependency_overrides[get_review_session] = override_session
    app.dependency_overrides[get_balloon_service] = lambda: context.balloon_service
    app.dependency_overrides[get_review_service] = lambda: context.review_service
    try:
        client = TestClient(app)
        base = f"/api/v1/projects/{context.working_copy.project_id}"
        missing_operator = client.post(
            f"{base}/balloons/generate",
            json={"expected_version": context.working_copy.version},
        )
        assert missing_operator.status_code == 422

        generated = client.post(
            f"{base}/balloons/generate",
            headers={"X-QI-Operator": "quality-1"},
            json={"expected_version": context.working_copy.version},
        )
        assert generated.status_code == 200
        assert len(generated.json()["balloons"]) == 2
        balloon = generated.json()["balloons"][0]

        listed = client.get(f"{base}/balloons")
        assert listed.status_code == 200
        assert listed.json() == generated.json()

        stale = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "move",
                "balloon_id": balloon["id"],
                "expected_version": balloon["version"] + 10,
                "center_pdf": [70, 80],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "balloon_version_conflict"

        moved = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "move",
                "balloon_id": balloon["id"],
                "expected_version": balloon["version"],
                "center_pdf": [70, 80],
            },
        )
        assert moved.status_code == 200
        assert moved.json()["center_pdf"] == [70.0, 80.0]

        deleted = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "delete",
                "balloon_id": balloon["id"],
                "expected_version": moved.json()["version"],
            },
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "deleted"

        rebuilt = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "rebuild",
                "balloon_id": balloon["id"],
                "expected_version": deleted.json()["version"],
            },
        )
        assert rebuilt.status_code == 200
        assert rebuilt.json()["status"] == "active"

        reordered = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "reorder",
                "balloon_id": balloon["id"],
                "expected_version": rebuilt.json()["version"],
                "sort_order": 50,
            },
        )
        assert reordered.status_code == 200
        assert reordered.json()["formal_number"] == balloon["formal_number"]

        other = generated.json()["balloons"][1]
        renumbered = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "renumber",
                "ordered_balloon_ids": [other["id"], reordered.json()["id"]],
                "expected_versions": {
                    other["id"]: other["version"],
                    reordered.json()["id"]: reordered.json()["version"],
                },
            },
        )
        assert renumbered.status_code == 200
        assert [
            value["formal_number"] for value in renumbered.json()["balloons"]
        ] == [1, 2]

        confirmed = client.post(
            f"{base}/review/confirm",
            headers={"X-QI-Operator": "quality-1"},
            json={"expected_version": context.working_copy.version},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["project_id"] == str(context.working_copy.project_id)
        assert confirmed.json()["balloons"]

        finalized = client.post(
            f"{base}/balloons/commands",
            headers={"X-QI-Operator": "quality-1"},
            json={
                "type": "move",
                "balloon_id": renumbered.json()["balloons"][0]["id"],
                "expected_version": renumbered.json()["balloons"][0]["version"],
                "center_pdf": [75, 85],
            },
        )
        assert finalized.status_code == 409
        assert finalized.json()["error"]["code"] == "review_already_confirmed"
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()
