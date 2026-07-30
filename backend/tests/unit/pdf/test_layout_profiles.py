from __future__ import annotations

from dataclasses import replace

import pytest

from app.pdf.layout_profiles import match_welli_layout_profile
from tests.helpers.welli_layout_fixture import make_welli_layout_fixture


def _match(fixture):
    return match_welli_layout_profile(
        page_index=0,
        page_width_pt=fixture.page_width_pt,
        page_height_pt=fixture.page_height_pt,
        page_rotation=fixture.page_rotation,
        observations=fixture.observations,
        drawings=fixture.drawings,
    )


@pytest.mark.parametrize(
    ("profile_id", "expected_profile_id"),
    (
        ("welli-a3-landscape/1", "welli-a3-landscape/1"),
        ("welli-a4-portrait/1", "welli-a4-portrait/1"),
        ("welli-a3-portrait/1", "welli-a3-portrait/1"),
    ),
)
def test_supported_page_variants_match(
    profile_id: str,
    expected_profile_id: str,
) -> None:
    match = _match(make_welli_layout_fixture(profile_id=profile_id))

    assert match is not None
    assert match.profile_id == expected_profile_id
    assert match.match_state == "high_confidence"


@pytest.mark.parametrize(
    ("delta_mm", "matches"),
    (
        (0.49, True),
        (0.51, False),
        (-0.49, True),
        (-0.51, False),
    ),
)
def test_page_size_tolerance_is_fixed(delta_mm: float, matches: bool) -> None:
    fixture = make_welli_layout_fixture(page_size_delta_mm=(delta_mm, 0.0))

    assert (_match(fixture) is not None) is matches


def test_rotated_page_does_not_match() -> None:
    fixture = make_welli_layout_fixture(page_rotation=90)

    assert _match(fixture) is None


@pytest.mark.parametrize(
    ("geometry_groups", "anchor_groups"),
    (
        (frozenset(), frozenset()),
        (frozenset(), frozenset({"title", "revision", "archive"})),
        (
            frozenset({"body_frame", "title", "revision", "archive"}),
            frozenset(),
        ),
    ),
)
def test_page_size_text_or_geometry_alone_cannot_match(
    geometry_groups: frozenset[str],
    anchor_groups: frozenset[str],
) -> None:
    fixture = make_welli_layout_fixture(
        geometry_groups=geometry_groups,
        anchor_groups=anchor_groups,
    )

    assert _match(fixture) is None


def test_body_two_region_geometries_and_two_anchor_groups_match() -> None:
    fixture = make_welli_layout_fixture(
        geometry_groups=frozenset({"body_frame", "title", "revision"}),
        anchor_groups=frozenset({"title", "revision"}),
    )

    match = _match(fixture)

    assert match is not None
    assert match.geometry_evidence_codes == (
        "body_frame",
        "revision_grid",
        "title_grid",
    )
    assert match.text_anchor_evidence_codes == (
        "revision_anchor_quorum",
        "title_anchor_quorum",
    )


def test_optional_title_x93_is_evidence_neutral() -> None:
    with_optional = _match(make_welli_layout_fixture(include_optional_title_x93=True))
    without_optional = _match(
        make_welli_layout_fixture(include_optional_title_x93=False)
    )

    assert with_optional is not None
    assert without_optional is not None
    assert with_optional == without_optional


@pytest.mark.parametrize(
    "grid_change",
    (
        ("title", "x", 12.0),
        ("revision", "y", 15.0),
        ("archive", "y", 58.0),
    ),
)
def test_missing_critical_grid_prevents_that_region_evidence(
    grid_change: tuple[str, str, float],
) -> None:
    fixture = make_welli_layout_fixture(
        geometry_groups=frozenset({"body_frame", grid_change[0]}),
        anchor_groups=frozenset({"title", "revision", "archive"}),
        omit_grid=grid_change,
    )

    assert _match(fixture) is None


def test_conflicting_grid_prevents_high_confidence_match() -> None:
    fixture = make_welli_layout_fixture(
        geometry_groups=frozenset({"body_frame", "title", "revision"}),
        anchor_groups=frozenset({"title", "revision"}),
        conflicting_grid=("revision", "x", 10.0),
    )

    assert _match(fixture) is None


def test_unknown_drawing_opcode_is_ignored() -> None:
    baseline = _match(make_welli_layout_fixture())
    with_unknown = _match(make_welli_layout_fixture(include_unknown_opcode=True))

    assert baseline is not None
    assert with_unknown == baseline


def test_input_order_does_not_change_match() -> None:
    fixture = make_welli_layout_fixture()
    reordered = replace(
        fixture,
        observations=tuple(reversed(fixture.observations)),
        drawings=tuple(reversed(fixture.drawings)),
    )

    assert _match(reordered) == _match(fixture)
