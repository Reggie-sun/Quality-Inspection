from __future__ import annotations

from dataclasses import replace
import math

import pytest

from app.pdf.layout_profiles import (
    match_welli_layout_profile,
    welli_same_page_watermark_observation_ids,
)
from tests.helpers.welli_layout_fixture import (
    PROFILE_PAGE_SIZES_MM,
    make_welli_layout_fixture,
    welli_text_observation,
)


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


def _fixture_with_extra_observations(
    observations,
    *,
    profile_id: str = "welli-a3-landscape/1",
):
    fixture = make_welli_layout_fixture(profile_id=profile_id)
    return replace(
        fixture,
        observations=fixture.observations + tuple(observations),
    )


def _assignment_by_id(fixture):
    match = _match(fixture)
    assert match is not None
    return match, {
        assignment.observation_id: assignment
        for assignment in match.assignments
    }


@pytest.mark.parametrize(
    (
        "observation_id",
        "text",
        "bbox_mm",
        "expected_region",
        "expected_role",
        "expected_cell_id",
    ),
    (
        (
            "native:title-approval",
            "张三",
            (247.0, 246.0, 260.0, 250.0),
            "title_block",
            "title_approval_context",
            "title-approval-context",
        ),
        (
            "native:title-value",
            "260508",
            (340.0, 246.0, 355.0, 250.0),
            "title_block",
            "title_metadata_value",
            "title-metadata-value",
        ),
        (
            "native:revision-header",
            "更改描述",
            (340.0, 6.0, 360.0, 9.0),
            "revision_table",
            "revision_header",
            "revision-header",
        ),
        (
            "native:revision-marker-1",
            "1",
            (327.0, 12.0, 331.0, 16.0),
            "revision_table",
            "revision_marker",
            "revision-marker-1",
        ),
        (
            "native:revision-description-1",
            "修订",
            (340.0, 12.0, 355.0, 16.0),
            "revision_table",
            "revision_description",
            "revision-description-1",
        ),
        (
            "native:archive-label",
            "描图",
            (2.0, 208.0, 14.0, 211.0),
            "archive_strip",
            "archive_label",
            "archive-label-2",
        ),
        (
            "native:archive-record",
            "王工",
            (2.0, 214.0, 14.0, 218.0),
            "archive_strip",
            "archive_record",
            "archive-record-2",
        ),
        (
            "native:page-frame-top-1",
            "1",
            (103.0, 1.0, 107.0, 4.0),
            "page_frame",
            "page_frame_number",
            "page-frame-top-1",
        ),
    ),
)
def test_native_lines_receive_stable_cell_assignments(
    observation_id: str,
    text: str,
    bbox_mm: tuple[float, float, float, float],
    expected_region: str,
    expected_role: str,
    expected_cell_id: str,
) -> None:
    observation = welli_text_observation(
        observation_id=observation_id,
        text=text,
        bbox_mm=bbox_mm,
        page_size_mm=PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"],
    )
    _, assignments = _assignment_by_id(
        _fixture_with_extra_observations((observation,))
    )

    assignment = assignments[observation_id]
    assert assignment.region_id == expected_region
    assert assignment.cell_role == expected_role
    assert assignment.cell_id == expected_cell_id
    assert assignment.assignment_evidence_codes == (
        "bbox_inside_role",
        "center_in_role",
        "horizontal_direction",
        "single_role",
    )


def test_bottom_page_frame_assignment_uses_actual_matched_page_height() -> None:
    page_height_mm = 297.0000885009765
    observation = welli_text_observation(
        observation_id="native:page-frame-bottom-1",
        text="1",
        bbox_mm=(51.6546, 292.0848, 53.3838, page_height_mm),
        page_size_mm=(210.0, page_height_mm),
    )
    fixture = make_welli_layout_fixture(
        profile_id="welli-a4-portrait/1",
        page_size_delta_mm=(0.0, page_height_mm - 297.0),
    )
    match = _match(
        replace(
            fixture,
            observations=fixture.observations + (observation,),
        )
    )

    assert match is not None
    assignments = {
        assignment.observation_id: assignment
        for assignment in match.assignments
    }
    assignment = assignments[observation.observation_id]
    assert assignment.cell_id == "page-frame-bottom-1"
    assert assignment.boundary_distance_mm == pytest.approx(0.0)


def test_revision_marker_and_description_have_distinct_row_identity() -> None:
    page_size = PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"]
    observations = (
        welli_text_observation(
            observation_id="native:marker-1",
            text="1",
            bbox_mm=(327.0, 12.0, 331.0, 16.0),
            page_size_mm=page_size,
        ),
        welli_text_observation(
            observation_id="native:description-1",
            text="change",
            bbox_mm=(340.0, 12.0, 355.0, 16.0),
            page_size_mm=page_size,
        ),
    )
    _, assignments = _assignment_by_id(
        _fixture_with_extra_observations(observations)
    )

    assert assignments["native:marker-1"].cell_id == "revision-marker-1"
    assert (
        assignments["native:description-1"].cell_id
        == "revision-description-1"
    )


@pytest.mark.parametrize(
    "bbox_mm",
    (
        (314.0, 246.0, 316.0, 250.0),
        (334.5, 12.0, 337.0, 16.0),
    ),
)
def test_bbox_crossing_two_roles_is_not_assigned(
    bbox_mm: tuple[float, float, float, float],
) -> None:
    observation = welli_text_observation(
        observation_id="native:cross-role",
        text="25",
        bbox_mm=bbox_mm,
        page_size_mm=PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"],
    )
    _, assignments = _assignment_by_id(
        _fixture_with_extra_observations((observation,))
    )

    assert observation.observation_id not in assignments


def test_boundary_distance_inside_tolerance_is_preserved_as_evidence() -> None:
    observation = welli_text_observation(
        observation_id="native:edge-inside",
        text="value",
        bbox_mm=(405.5, 246.0, 414.5, 250.0),
        page_size_mm=PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"],
    )
    _, assignments = _assignment_by_id(
        _fixture_with_extra_observations((observation,))
    )

    assert assignments[observation.observation_id].boundary_distance_mm == (
        pytest.approx(0.5)
    )


def test_negative_boundary_distance_does_not_create_assignment() -> None:
    observation = welli_text_observation(
        observation_id="native:outside-role",
        text="value",
        bbox_mm=(406.0, 246.0, 415.2, 250.0),
        page_size_mm=PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"],
    )
    _, assignments = _assignment_by_id(
        _fixture_with_extra_observations((observation,))
    )

    assert observation.observation_id not in assignments


@pytest.mark.parametrize(
    ("source_type", "observation_level", "angle", "parent_region_id"),
    (
        ("native", "span", 0.0, "native:parent"),
        ("ocr", "region", 0.0, None),
        ("native", "line", 2.1, None),
        ("native", "line", 0.0, "native:unexpected-parent"),
    ),
)
def test_non_line_or_conflicting_lineage_is_not_assigned(
    source_type: str,
    observation_level: str,
    angle: float,
    parent_region_id: str | None,
) -> None:
    observation = welli_text_observation(
        observation_id="source:not-assignable",
        text="value",
        bbox_mm=(340.0, 246.0, 355.0, 250.0),
        page_size_mm=PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"],
        source_type=source_type,
        observation_level=observation_level,
        direction_angle_degrees=angle,
        parent_region_id=parent_region_id,
    )
    _, assignments = _assignment_by_id(
        _fixture_with_extra_observations((observation,))
    )

    assert observation.observation_id not in assignments


def test_assignment_order_is_canonical() -> None:
    page_size = PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"]
    observations = (
        welli_text_observation(
            observation_id="native:z",
            text="z",
            bbox_mm=(340.0, 246.0, 355.0, 250.0),
            page_size_mm=page_size,
        ),
        welli_text_observation(
            observation_id="native:a",
            text="a",
            bbox_mm=(247.0, 246.0, 260.0, 250.0),
            page_size_mm=page_size,
        ),
    )
    fixture = _fixture_with_extra_observations(observations)
    reordered = replace(
        fixture,
        observations=tuple(reversed(fixture.observations)),
    )

    assert _match(fixture) == _match(reordered)
    assert tuple(
        assignment.observation_id
        for assignment in _match(fixture).assignments  # type: ignore[union-attr]
    ) == tuple(
        sorted(
            assignment.observation_id
            for assignment in _match(fixture).assignments  # type: ignore[union-attr]
        )
    )


def _watermark_observations(
    *,
    x_positions: tuple[float, ...] = (50.0, 150.0, 250.0),
    y_positions: tuple[float, ...] = (40.0, 120.0, 200.0),
    text: str = "伟立机器人",
    angle: float = -30.0,
    source_level: str = "line",
):
    page_size = PROFILE_PAGE_SIZES_MM["welli-a3-landscape/1"]
    observations = []
    for row, y in enumerate(y_positions):
        for column, x in enumerate(x_positions):
            observations.append(
                welli_text_observation(
                    observation_id=f"native:watermark:{row}:{column}:{source_level}",
                    text=text,
                    bbox_mm=(x - 8.0, y - 2.0, x + 8.0, y + 2.0),
                    page_size_mm=page_size,
                    direction_angle_degrees=angle,
                    direction=(math.cos(math.radians(angle)), math.sin(math.radians(angle))),
                    observation_level=source_level,
                    parent_region_id=(
                        f"native:watermark:{row}:{column}:line"
                        if source_level == "span"
                        else None
                    ),
                )
            )
    return tuple(observations)


def _watermark_ids(observations):
    fixture = _fixture_with_extra_observations(observations)
    match = _match(fixture)
    assert match is not None
    return welli_same_page_watermark_observation_ids(
        profile_match=match,
        observations=fixture.observations,
    )


def test_same_page_watermark_requires_exact_profile_grid() -> None:
    observations = _watermark_observations()

    assert _watermark_ids(observations) == frozenset(
        observation.observation_id for observation in observations
    )


def test_same_page_watermark_uses_lattice_quorum_for_partial_outer_row() -> None:
    lattice = _watermark_observations(
        x_positions=(50.0, 150.0, 250.0, 350.0),
    )
    partial_outer_row = tuple(
        replace(
            observation,
            observation_id=f"native:watermark:partial:{index}",
        )
        for index, observation in enumerate(
            _watermark_observations(
                x_positions=(52.0, 152.0),
                y_positions=(267.0,),
            )
        )
    )
    observations = lattice + partial_outer_row

    assert _watermark_ids(observations) == frozenset(
        observation.observation_id for observation in observations
    )


@pytest.mark.parametrize(
    "observations",
    (
        _watermark_observations()[:-1],
        _watermark_observations(text="伟立机器人有限公司"),
        _watermark_observations(angle=0.0),
        _watermark_observations(angle=-27.0),
        _watermark_observations(
            x_positions=(50.0,),
            y_positions=tuple(20.0 + index * 20.0 for index in range(9)),
        ),
        _watermark_observations(
            x_positions=(10.0, 110.0, 210.0, 310.0, 410.0),
            y_positions=(40.0, 120.0),
        ),
        _watermark_observations(x_positions=(50.0, 120.0, 190.0)),
    ),
)
def test_same_page_watermark_rejects_incomplete_or_wrong_grid(
    observations,
) -> None:
    assert _watermark_ids(observations) == frozenset()


def test_line_and_span_sources_do_not_double_count_watermarks() -> None:
    lines = _watermark_observations()[:-1]
    spans = _watermark_observations(source_level="span")

    assert _watermark_ids(lines + spans) == frozenset()


def test_watermark_requires_profile_match() -> None:
    assert (
        welli_same_page_watermark_observation_ids(
            profile_match=None,
            observations=_watermark_observations(),
        )
        == frozenset()
    )
