from __future__ import annotations

from typing import Any

import pymupdf

from app.pdf.coordinates import PageTransform
from app.pdf.gdt_frames import build_page_gdt_frame_observations
from app.pdf.schemas import (
    LayoutProfileMatch,
    ObservationRegionAssignment,
    TextObservation,
)


def identity_transform() -> PageTransform:
    return PageTransform(width=1190.0, height=842.0, rotation=0, scale=1.0)


def text_line(
    observation_id: str,
    raw_text: str,
    bbox: tuple[float, float, float, float],
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native",
        observation_level="line",
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=0,
        bbox_pdf=bbox,
        bbox_normalized=(
            bbox[0] / 1190.0,
            bbox[1] / 842.0,
            bbox[2] / 1190.0,
            bbox[3] / 842.0,
        ),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )


def line_drawing(
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, Any]:
    return {
        "items": [
            (
                "l",
                pymupdf.Point(*start),
                pymupdf.Point(*end),
            )
        ]
    }


def feature_control_frame_drawings() -> tuple[dict[str, Any], ...]:
    x0, x1 = 680.0, 760.0
    y0, y1 = 380.0, 420.0
    separators = (706.0, 732.0)
    return (
        line_drawing((x0, y0), (x1, y0)),
        line_drawing((x0, y1), (x1, y1)),
        line_drawing((x0, y0), (x0, y1)),
        line_drawing((x1, y0), (x1, y1)),
        *(line_drawing((x, y0), (x, y1)) for x in separators),
    )


def revision_table_drawings(
    *,
    rows: int,
    columns: int,
) -> tuple[dict[str, Any], ...]:
    x0, y0 = 880.0, 10.0
    x1, y1 = 1080.0, 50.0
    verticals = tuple(
        x0 + (x1 - x0) * index / columns for index in range(columns + 1)
    )
    horizontals = tuple(
        y0 + (y1 - y0) * index / rows for index in range(rows + 1)
    )
    return tuple(
        [
            *(line_drawing((x, y0), (x, y1)) for x in verticals),
            *(line_drawing((x0, y), (x1, y)) for y in horizontals),
        ]
    )


def revision_table_layout_match() -> LayoutProfileMatch:
    return LayoutProfileMatch(
        page_index=0,
        profile_id="welli-a3-landscape/1",
        match_state="high_confidence",
        geometry_evidence_codes=("revision_grid",),
        text_anchor_evidence_codes=("revision_anchor_quorum",),
        assignments=(
            ObservationRegionAssignment(
                observation_id="title",
                page_index=0,
                profile_id="welli-a3-landscape/1",
                region_id="revision_table",
                cell_role="revision_header",
                cell_id="revision-header",
                assignment_evidence_codes=("bbox_inside_role",),
                boundary_distance_mm=0.0,
                rule_version="p0-a2-welli-layout/1",
            ),
        ),
        rule_version="p0-a2-welli-layout/1",
    )


def test_parallelism_frame_collects_independent_datum_line() -> None:
    observations = (
        text_line("value", "0.1", (684.0, 390.0, 702.0, 408.0)),
        text_line("datum", "A", (712.0, 390.0, 721.0, 408.0)),
    )
    frames = build_page_gdt_frame_observations(
        page_index=0,
        page_width=1190.0,
        page_height=842.0,
        source_sha256="fixture-source",
        text_observations=observations,
        drawings=feature_control_frame_drawings(),
        transform=identity_transform(),
        layout_profile_match=None,
    )
    assert len(frames) == 1
    assert frames[0].associated_text_observation_ids == ("value", "datum")
    assert len(frames[0].cells) == 3


def test_table_grid_is_not_a_feature_control_frame() -> None:
    frames = build_page_gdt_frame_observations(
        page_index=0,
        page_width=1190.0,
        page_height=842.0,
        source_sha256="table-negative",
        text_observations=(
            text_line("title", "REV", (900.0, 20.0, 940.0, 35.0)),
        ),
        drawings=revision_table_drawings(rows=4, columns=5),
        transform=identity_transform(),
        layout_profile_match=revision_table_layout_match(),
    )
    assert frames == ()
