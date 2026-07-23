from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.balloons.models import Balloon
from app.db import engine
from app.review.models import ReviewWorkingCopy
from tests.integration.test_balloon_service import (
    BalloonContext,
    make_balloon_context,
)


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


@pytest.fixture
def context(db_session: Session, tmp_path: Path) -> BalloonContext:
    return make_balloon_context(db_session, tmp_path, frozen=True)


def _generated(context: BalloonContext) -> list[Balloon]:
    return context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )


def test_move_persists_pdf_coordinates(context: BalloonContext) -> None:
    """P0-BAL-008: move persists PDF coordinates, never viewport pixels."""
    balloon = _generated(context)[0]

    moved = context.balloon_service.move(
        balloon.id,
        center_pdf=(72.5, 81.25),
        expected_version=balloon.version,
        operator_id="quality-1",
    )

    context.session.expire_all()
    persisted = context.session.get(Balloon, balloon.id)
    assert moved.center_pdf == [72.5, 81.25]
    assert persisted is not None
    assert persisted.center_pdf == [72.5, 81.25]


def test_delete_balloon_preserves_item_and_requirement(
    context: BalloonContext,
) -> None:
    """P0-BAL-009: delete affects only the balloon aggregate."""
    balloon = _generated(context)[0]

    deleted = context.balloon_service.delete(
        balloon.id,
        expected_version=balloon.version,
        operator_id="quality-1",
    )
    working = context.review_service.get_working_copy(context.working_copy.id)
    item = next(item for item in working.items if item["item_id"] == "i1")

    assert item["active"] is True
    assert item["balloon_required"] is True
    assert deleted.status == "deleted"


def test_rebuild_balloon(context: BalloonContext) -> None:
    """P0-BAL-010: rebuild never collides with an explicitly reused number."""
    balloon, other = _generated(context)
    deleted = context.balloon_service.delete(
        balloon.id,
        expected_version=balloon.version,
        operator_id="quality-1",
    )
    renumbered = context.balloon_service.renumber(
        context.working_copy.project_id,
        ordered_balloon_ids=[other.id],
        expected_versions={other.id: other.version},
        operator_id="quality-1",
    )

    rebuilt = context.balloon_service.rebuild(
        balloon.id,
        expected_version=deleted.version,
        operator_id="quality-1",
    )

    assert rebuilt.id == balloon.id
    assert rebuilt.status == "active"
    assert rebuilt.center_pdf == balloon.center_pdf
    assert rebuilt.formal_number is None
    assert context.review_service.get_working_copy(
        context.working_copy.id
    ).numbering_stale is True

    final = context.balloon_service.renumber(
        context.working_copy.project_id,
        ordered_balloon_ids=[rebuilt.id, renumbered[0].id],
        expected_versions={
            rebuilt.id: rebuilt.version,
            renumbered[0].id: renumbered[0].version,
        },
        operator_id="quality-1",
    )
    assert [value.formal_number for value in final] == [1, 2]

    active_rebuild = context.balloon_service.rebuild(
        final[0].id,
        expected_version=final[0].version,
        operator_id="quality-1",
    )
    assert active_rebuild.formal_number == 1
    assert context.review_service.get_working_copy(
        context.working_copy.id
    ).numbering_stale is False


def test_reorder_does_not_silently_renumber(context: BalloonContext) -> None:
    """P0-BAL-011: reorder changes sort order, not formal numbers."""
    balloons = _generated(context)
    original_number = balloons[0].formal_number

    reordered = context.balloon_service.reorder(
        balloons[0].id,
        sort_order=50,
        expected_version=balloons[0].version,
        operator_id="quality-1",
    )
    working = context.session.get(ReviewWorkingCopy, context.working_copy.id)

    assert reordered.sort_order == 50
    assert reordered.formal_number == original_number
    assert working is not None
    assert working.numbering_stale is True


def test_explicit_renumber_is_contiguous(context: BalloonContext) -> None:
    """P0-BAL-012: explicit renumber writes one complete contiguous sequence."""
    balloons = _generated(context)
    reordered = context.balloon_service.reorder(
        balloons[0].id,
        sort_order=50,
        expected_version=balloons[0].version,
        operator_id="quality-1",
    )

    renumbered = context.balloon_service.renumber(
        context.working_copy.project_id,
        ordered_balloon_ids=[balloons[1].id, reordered.id],
        expected_versions={
            balloons[1].id: balloons[1].version,
            reordered.id: reordered.version,
        },
        operator_id="quality-1",
    )

    assert [balloon.id for balloon in renumbered] == [balloons[1].id, reordered.id]
    assert [balloon.formal_number for balloon in renumbered] == [1, 2]
