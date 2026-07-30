from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pymupdf

from app.pdf.schemas import TextObservation


MM_PER_PDF_POINT = 25.4 / 72.0
PDF_POINTS_PER_MM = 1.0 / MM_PER_PDF_POINT

PROFILE_PAGE_SIZES_MM = {
    "welli-a3-landscape/1": (420.0, 297.0),
    "welli-a4-portrait/1": (210.0, 297.0),
    "welli-a3-portrait/1": (297.0, 420.0),
}

TITLE_GRID_X_MM = (0.0, 12.0, 24.0, 40.0, 52.0, 64.0, 80.0, 106.0, 118.0, 130.0, 144.0, 180.0)
TITLE_GRID_Y_MM = (0.0, 7.0, 14.0, 18.0, 21.0, 28.0, 35.0, 38.0, 42.0, 47.0, 49.0, 56.0)
REVISION_GRID_X_MM = (0.0, 10.0, 90.0)
REVISION_GRID_Y_MM = (0.0, 5.0, 15.0, 25.0, 35.0)
ARCHIVE_GRID_X_MM = (0.0, 25.0)
ARCHIVE_GRID_Y_MM = (0.0, 7.0, 17.0, 24.0, 34.0, 41.0, 51.0, 58.0, 68.0, 75.0, 85.0, 92.0, 102.0)


@dataclass(frozen=True)
class WelliLayoutFixture:
    page_width_pt: float
    page_height_pt: float
    page_rotation: int
    observations: tuple[TextObservation, ...]
    drawings: tuple[Mapping[str, Any], ...]


def mm_to_pt(value: float) -> float:
    return value * PDF_POINTS_PER_MM


def welli_text_observation(
    *,
    observation_id: str,
    text: str,
    page_index: int = 0,
    bbox_mm: tuple[float, float, float, float],
    page_size_mm: tuple[float, float],
    direction_angle_degrees: float = 0.0,
    direction: tuple[float, float] = (1.0, 0.0),
    source_type: str = "native",
    observation_level: str = "line",
    parent_region_id: str | None = None,
) -> TextObservation:
    width_mm, height_mm = page_size_mm
    x0, y0, x1, y1 = bbox_mm
    return TextObservation(
        observation_id=observation_id,
        source_type=source_type,
        observation_level=observation_level,
        raw_text=text,
        normalized_text=text,
        page_index=page_index,
        bbox_pdf=tuple(mm_to_pt(value) for value in bbox_mm),
        bbox_normalized=(
            x0 / width_mm,
            y0 / height_mm,
            x1 / width_mm,
            y1 / height_mm,
        ),
        direction=direction,
        direction_angle_degrees=direction_angle_degrees,
        confidence=None if source_type == "native" else 0.9,
        parent_region_id=parent_region_id,
    )


def _region_boxes(
    width_mm: float,
    height_mm: float,
) -> dict[str, tuple[float, float, float, float]]:
    return {
        "body_frame": (25.0, 5.0, width_mm - 5.0, height_mm - 5.0),
        "title": (
            width_mm - 185.0,
            height_mm - 61.0,
            width_mm - 5.0,
            height_mm - 5.0,
        ),
        "revision": (width_mm - 95.0, 5.0, width_mm - 5.0, 40.0),
        "archive": (0.0, height_mm - 107.0, 25.0, height_mm - 5.0),
    }


def _draw_grid(
    page: pymupdf.Page,
    *,
    region_name: str,
    box_mm: tuple[float, float, float, float],
    grid_x_mm: Sequence[float],
    grid_y_mm: Sequence[float],
    omit_grid: tuple[str, str, float] | None,
    conflicting_grid: tuple[str, str, float] | None,
) -> None:
    x0, y0, x1, y1 = box_mm
    shape = page.new_shape()
    shape.draw_rect(
        pymupdf.Rect(mm_to_pt(x0), mm_to_pt(y0), mm_to_pt(x1), mm_to_pt(y1))
    )
    for local_x in grid_x_mm[1:-1]:
        if omit_grid == (region_name, "x", local_x):
            continue
        x = x0 + local_x
        shape.draw_line(
            (mm_to_pt(x), mm_to_pt(y0)),
            (mm_to_pt(x), mm_to_pt(y1)),
        )
        if conflicting_grid == (region_name, "x", local_x):
            shape.draw_line(
                (mm_to_pt(x + 0.6), mm_to_pt(y0)),
                (mm_to_pt(x + 0.6), mm_to_pt(y1)),
            )
    for local_y in grid_y_mm[1:-1]:
        if omit_grid == (region_name, "y", local_y):
            continue
        y = y0 + local_y
        shape.draw_line(
            (mm_to_pt(x0), mm_to_pt(y)),
            (mm_to_pt(x1), mm_to_pt(y)),
        )
        if conflicting_grid == (region_name, "y", local_y):
            shape.draw_line(
                (mm_to_pt(x0), mm_to_pt(y + 0.6)),
                (mm_to_pt(x1), mm_to_pt(y + 0.6)),
            )
    shape.finish(width=0.5, color=(0, 0, 0), closePath=False)
    shape.commit()


def _anchor_observations(
    *,
    page_size_mm: tuple[float, float],
    anchor_groups: frozenset[str],
) -> tuple[TextObservation, ...]:
    width_mm, height_mm = page_size_mm
    boxes = _region_boxes(width_mm, height_mm)
    observations: list[TextObservation] = []
    if "title" in anchor_groups:
        title_x0, title_y0, _, _ = boxes["title"]
        for index, text in enumerate(("物料编码", "图样代号", "比例", "重量")):
            observations.append(
                welli_text_observation(
                    observation_id=f"native:title-anchor:{index}",
                    text=text,
                    bbox_mm=(
                        title_x0 + 82.0 + index * 20.0,
                        title_y0 + 2.0,
                        title_x0 + 92.0 + index * 20.0,
                        title_y0 + 5.0,
                    ),
                    page_size_mm=page_size_mm,
                )
            )
    if "revision" in anchor_groups:
        revision_x0, revision_y0, _, _ = boxes["revision"]
        for index, text in enumerate(("标记", "更改描述")):
            observations.append(
                welli_text_observation(
                    observation_id=f"native:revision-anchor:{index}",
                    text=text,
                    bbox_mm=(
                        revision_x0 + 1.0 + index * 12.0,
                        revision_y0 + 1.0,
                        revision_x0 + 8.0 + index * 30.0,
                        revision_y0 + 4.0,
                    ),
                    page_size_mm=page_size_mm,
                )
            )
    if "archive" in anchor_groups:
        _, archive_y0, _, _ = boxes["archive"]
        observations.append(
            welli_text_observation(
                observation_id="native:archive-anchor:0",
                text="旧底图总号",
                bbox_mm=(2.0, archive_y0 + 52.0, 20.0, archive_y0 + 56.0),
                page_size_mm=page_size_mm,
            )
        )
    return tuple(observations)


def make_welli_layout_fixture(
    *,
    profile_id: str = "welli-a3-landscape/1",
    page_size_delta_mm: tuple[float, float] = (0.0, 0.0),
    page_rotation: int = 0,
    geometry_groups: frozenset[str] = frozenset(
        {"body_frame", "title", "revision", "archive"}
    ),
    anchor_groups: frozenset[str] = frozenset({"title", "revision", "archive"}),
    include_optional_title_x93: bool = True,
    include_unknown_opcode: bool = False,
    omit_grid: tuple[str, str, float] | None = None,
    conflicting_grid: tuple[str, str, float] | None = None,
    unsupported_page_size_mm: tuple[float, float] | None = None,
) -> WelliLayoutFixture:
    canonical_width_mm, canonical_height_mm = PROFILE_PAGE_SIZES_MM[profile_id]
    if unsupported_page_size_mm is None:
        width_mm = canonical_width_mm + page_size_delta_mm[0]
        height_mm = canonical_height_mm + page_size_delta_mm[1]
    else:
        width_mm, height_mm = unsupported_page_size_mm
    page_size_mm = (width_mm, height_mm)
    boxes = _region_boxes(width_mm, height_mm)

    document = pymupdf.open()
    page = document.new_page(width=mm_to_pt(width_mm), height=mm_to_pt(height_mm))
    if "body_frame" in geometry_groups:
        shape = page.new_shape()
        x0, y0, x1, y1 = boxes["body_frame"]
        shape.draw_rect(
            pymupdf.Rect(mm_to_pt(x0), mm_to_pt(y0), mm_to_pt(x1), mm_to_pt(y1))
        )
        shape.finish(width=0.5, color=(0, 0, 0), closePath=False)
        shape.commit()
    if "title" in geometry_groups:
        title_x = list(TITLE_GRID_X_MM)
        if include_optional_title_x93:
            title_x.append(93.0)
            title_x.sort()
        _draw_grid(
            page,
            region_name="title",
            box_mm=boxes["title"],
            grid_x_mm=title_x,
            grid_y_mm=TITLE_GRID_Y_MM,
            omit_grid=omit_grid,
            conflicting_grid=conflicting_grid,
        )
    if "revision" in geometry_groups:
        _draw_grid(
            page,
            region_name="revision",
            box_mm=boxes["revision"],
            grid_x_mm=REVISION_GRID_X_MM,
            grid_y_mm=REVISION_GRID_Y_MM,
            omit_grid=omit_grid,
            conflicting_grid=conflicting_grid,
        )
    if "archive" in geometry_groups:
        _draw_grid(
            page,
            region_name="archive",
            box_mm=boxes["archive"],
            grid_x_mm=ARCHIVE_GRID_X_MM,
            grid_y_mm=ARCHIVE_GRID_Y_MM,
            omit_grid=omit_grid,
            conflicting_grid=conflicting_grid,
        )
    if include_unknown_opcode:
        shape = page.new_shape()
        shape.draw_bezier(
            (mm_to_pt(40.0), mm_to_pt(40.0)),
            (mm_to_pt(45.0), mm_to_pt(50.0)),
            (mm_to_pt(55.0), mm_to_pt(30.0)),
            (mm_to_pt(60.0), mm_to_pt(40.0)),
        )
        shape.finish(width=0.5, color=(0, 0, 0), closePath=False)
        shape.commit()

    drawings = tuple(page.get_drawings())
    document.close()
    return WelliLayoutFixture(
        page_width_pt=mm_to_pt(width_mm),
        page_height_pt=mm_to_pt(height_mm),
        page_rotation=page_rotation,
        observations=_anchor_observations(
            page_size_mm=page_size_mm,
            anchor_groups=anchor_groups,
        ),
        drawings=drawings,
    )
