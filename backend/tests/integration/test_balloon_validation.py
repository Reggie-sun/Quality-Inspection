from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balloons.placement import BALLOON_RADIUS_PDF, circle_intersects_box
from app.balloons.validator import validate_balloons
from app.db import engine
from app.exports.models import ExportJob
from app.review.models import ReviewedResult
from app.review.service import ReviewConfirmationBlocked
from test_balloon_service import make_balloon_context


@dataclass(frozen=True)
class BalloonValue:
    inspection_item_id: str
    source_location_id: str
    page_index: int
    formal_number: int | None
    anchor_bbox_pdf: list[float]
    leader_target_pdf: list[float] | None
    center_pdf: list[float]
    placement_status: str
    collision_flags: list[str]
    status: str = "active"


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


def test_unresolved_hard_collision_blocks_confirm_and_export(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-BAL-014: every formal geometry defect remains a blocking Veto."""
    items = [
        {
            "item_id": "i1",
            "active": True,
            "balloon_required": True,
            "source_location_ids": ["s1"],
        },
        {
            "item_id": "i2",
            "active": True,
            "balloon_required": True,
            "source_location_ids": ["s2"],
        },
        {
            "item_id": "i3",
            "active": True,
            "balloon_required": True,
            "source_location_ids": ["s3"],
        },
    ]
    first = BalloonValue(
        inspection_item_id="i1",
        source_location_id="s1",
        page_index=0,
        formal_number=1,
        anchor_bbox_pdf=[20, 20, 40, 40],
        leader_target_pdf=[30, 30],
        center_pdf=[60, 60],
        placement_status="manual_required",
        collision_flags=["protected_overlap"],
    )
    overlapping = BalloonValue(
        inspection_item_id="i2",
        source_location_id="wrong-source",
        page_index=0,
        formal_number=2,
        anchor_bbox_pdf=[42, 42, 52, 52],
        leader_target_pdf=None,
        center_pdf=[68, 60],
        placement_status="placed",
        collision_flags=["source_text_overlap"],
    )
    unreadable = BalloonValue(
        inspection_item_id="i3",
        source_location_id="s3",
        page_index=0,
        formal_number=1234,
        anchor_bbox_pdf=[80, 80, 90, 90],
        leader_target_pdf=[85, 85],
        center_pdf=[5, 95],
        placement_status="placed",
        collision_flags=[],
    )
    blockers = set(
        validate_balloons(
            items,
            [first, overlapping, unreadable],
            {0: (100, 100)},
            protected_boxes={0: ((50, 50, 75, 75),)},
            source_text_boxes={0: ((62, 54, 74, 66),)},
        )
    )

    assert {
        "manual_required",
        "circle_overlap",
        "glyph_circle_overlap",
        "owner_glyph_outside_circle",
        "outside_cropbox",
        "protected_overlap",
        "source_text_overlap",
        "unreadable_number",
        "item_balloon_disconnect",
        "invalid_leader",
    } <= blockers

    context = make_balloon_context(db_session, tmp_path, frozen=True)
    generated = context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    generated[1].center_pdf = list(generated[0].center_pdf)
    generated[1].placement_status = "manual_required"
    generated[1].collision_flags = ["circle_overlap"]
    db_session.commit()

    with pytest.raises(ReviewConfirmationBlocked) as error:
        context.review_service.confirm(
            context.working_copy.id,
            expected_version=context.working_copy.version,
            operator_id="quality-1",
        )

    assert "manual_required" in error.value.blockers
    assert "circle_overlap" in error.value.blockers
    assert db_session.scalar(
        select(func.count())
        .select_from(ReviewedResult)
        .where(ReviewedResult.project_id == context.working_copy.project_id)
    ) == 0
    assert db_session.scalar(
        select(func.count())
        .select_from(ExportJob)
        .where(ExportJob.project_id == context.working_copy.project_id)
    ) == 0


def test_manual_required_and_formal_invalidity_are_both_blocking() -> None:
    """P0-BAL-014: manual placement cannot be converted to formal success."""
    items = [
        {
            "item_id": "i1",
            "active": True,
            "balloon_required": True,
            "source_location_ids": ["s1"],
        }
    ]
    manual = BalloonValue(
        inspection_item_id="i1",
        source_location_id="s1",
        page_index=0,
        formal_number=1,
        anchor_bbox_pdf=[20, 20, 40, 40],
        leader_target_pdf=[30, 30],
        center_pdf=[60, 60],
        placement_status="manual_required",
        collision_flags=[],
    )

    assert "manual_required" in validate_balloons(items, [manual], {0: (100, 100)})

    invalid = replace(
        manual,
        formal_number=None,
        center_pdf=[120, 120],
        leader_target_pdf=[90, 90],
    )
    blockers = validate_balloons(items, [invalid], {0: (100, 100)})

    assert "manual_required" in blockers
    assert "outside_cropbox" in blockers
    assert "unreadable_number" in blockers
    assert "invalid_leader" in blockers


def test_manual_item_source_bbox_is_part_of_the_collision_scene(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-BAL-014: manual source geometry is protected like detected text."""
    context = make_balloon_context(db_session, tmp_path, frozen=False)
    working = context.review_service.apply(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
        command={
            "type": "add",
            "raw_text": "M10",
            "item_type": "thread",
            "coordinates": [60, 60, 80, 80],
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
    )
    manual_item = working.items[-1]
    working = context.review_service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": manual_item["item_id"],
            "inspection_item": "M10",
            "inspection_standard": "confirmed M10",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
        },
    )
    working = context.review_service.freeze_items(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
    )
    generated = context.balloon_service.generate_formal(
        working.project_id,
        expected_version=working.version,
        operator_id="quality-1",
    )
    manual_balloon = next(
        balloon
        for balloon in generated
        if balloon.inspection_item_id == manual_item["item_id"]
    )

    moved = context.balloon_service.move(
        manual_balloon.id,
        center_pdf=(70.0, 50.0),
        expected_version=manual_balloon.version,
        operator_id="quality-1",
    )

    assert circle_intersects_box(
        tuple(moved.center_pdf),
        BALLOON_RADIUS_PDF,
        tuple(manual_item["coordinates"]),
    )
    assert moved.placement_status == "manual_required"
    assert "source_text_overlap" in moved.collision_flags
    assert "source_text_overlap" in context.balloon_service.validation_blockers(
        working.project_id
    )


def test_manual_move_revalidates_every_active_balloon(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-BAL-014: resolving one overlap clears the peer's stale Veto state."""
    context = make_balloon_context(db_session, tmp_path, frozen=True)
    first, second = context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    first = context.balloon_service.move(
        first.id,
        center_pdf=(70.0, 100.0),
        expected_version=first.version,
        operator_id="quality-1",
    )
    second = context.balloon_service.move(
        second.id,
        center_pdf=(80.0, 100.0),
        expected_version=second.version,
        operator_id="quality-1",
    )
    assert "circle_overlap" in second.collision_flags

    context.balloon_service.move(
        first.id,
        center_pdf=(50.0, 130.0),
        expected_version=first.version,
        operator_id="quality-1",
    )

    active = [
        balloon
        for balloon in context.balloon_service.list_for_project(
            context.working_copy.project_id
        )
        if balloon.status == "active"
    ]
    assert all(balloon.placement_status == "placed" for balloon in active)
    assert all(balloon.collision_flags == [] for balloon in active)
    blockers = context.balloon_service.validation_blockers(
        context.working_copy.project_id
    )
    assert "circle_overlap" not in blockers
    assert "manual_required" not in blockers


def test_registered_title_strip_blank_space_is_protected(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-BAL-014: the fixed drawing administration range is a hard Veto."""
    context = make_balloon_context(db_session, tmp_path, frozen=True)
    first, _ = context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )

    moved = context.balloon_service.move(
        first.id,
        center_pdf=(100.0, 170.0),
        expected_version=first.version,
        operator_id="quality-1",
    )

    assert moved.placement_status == "manual_required"
    assert "protected_overlap" in moved.collision_flags
    assert "protected_overlap" in context.balloon_service.validation_blockers(
        context.working_copy.project_id
    )
