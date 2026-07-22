from app.balloons.placement import PlacementInput, place_balloon


def test_layout_is_deterministic() -> None:
    """P0-BAL-006: fixed candidates and scoring produce identical placement."""
    placement = PlacementInput(
        page_size=(100, 100),
        anchor_bbox=(45, 45, 55, 55),
        forbidden=((35, 20, 65, 40),),
    )

    first = place_balloon(placement)
    second = place_balloon(placement)

    assert first == second
    assert first.status == "placed"
    assert first.center == (68.0, 32.0)
    assert first.collision_flags == ()
    assert first.reason is None


def test_forced_collision_returns_manual_required() -> None:
    """P0-BAL-007: forced collision returns a deterministic best attempt."""
    result = place_balloon(
        PlacementInput(
            page_size=(100, 100),
            anchor_bbox=(45, 45, 55, 55),
            forbidden=((0, 0, 100, 100),),
        )
    )

    assert result.status == "manual_required"
    assert result.center is not None
    assert result.collision_flags
    assert result.reason == "no_valid_candidate"
