import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from app.projects.models import Project
from app.review.locks import acquire_lock
from app.review.models import ReviewLock


def test_lock_expiry_uses_database_clock() -> None:
    """P0-RUN-008: lease takeover and expiry are based on PostgreSQL now()."""
    project_id = uuid.uuid4()
    database_now = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
    expired = ReviewLock(
        project_id=project_id,
        operator_id="quality-1",
        expires_at=database_now - timedelta(seconds=1),
    )
    session = Mock()
    session.scalar.side_effect = [
        Project(id=project_id, state="editing"),
        database_now,
        expired,
    ]

    acquired = acquire_lock(
        session,
        project_id,
        "quality-2",
        ttl_seconds=45,
    )

    assert acquired is expired
    assert acquired.operator_id == "quality-2"
    assert acquired.expires_at == database_now + timedelta(seconds=45)
    assert "now()" in str(session.scalar.call_args_list[1].args[0]).lower()
    session.commit.assert_called_once_with()
