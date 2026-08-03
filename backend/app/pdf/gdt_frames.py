from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Literal, Mapping, Sequence

from app.pdf.coordinates import BBox, PageTransform
from app.pdf.schemas import LayoutProfileMatch, TextObservation


MAX_FRAME_HEIGHT_PT = 48.0
MAX_FRAME_WIDTH_PT = 240.0
MIN_FRAME_HEIGHT_PT = 6.0
TEXT_FRAME_PADDING_PT = 1.5
MIN_TEXT_OVERLAP_RATIO = 0.5

_AXIS_TOLERANCE_PT = 0.25
_JOIN_GAP_PT = 1.5
_MIN_FRAME_WIDTH_PT = 12.0
_FRAME_GEOMETRY_QUANTUM = 0.001


@dataclass(frozen=True)
class GdtCellObservation:
    cell_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox


@dataclass(frozen=True)
class GdtFrameObservation:
    observation_id: str
    page_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox
    cells: tuple[GdtCellObservation, ...]
    associated_text_observation_ids: tuple[str, ...]
    proposal_source: Literal["native_vector", "raster"]
    proposal_state: Literal["complete", "ambiguous"]
    geometry_sha256: str


@dataclass(frozen=True)
class _AxisSegment:
    orientation: Literal["horizontal", "vertical"]
    coordinate: float
    start: float
    end: float


def _point_xy(value: Any) -> tuple[float, float] | None:
    try:
        if hasattr(value, "x") and hasattr(value, "y"):
            return float(value.x), float(value.y)
        return float(value[0]), float(value[1])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def _rect_xyxy(value: Any) -> BBox | None:
    try:
        if all(hasattr(value, name) for name in ("x0", "y0", "x1", "y1")):
            result = (float(value.x0), float(value.y0), float(value.x1), float(value.y1))
        else:
            result = tuple(float(value[index]) for index in range(4))
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    if result[0] > result[2] or result[1] > result[3]:
        return None
    return result  # type: ignore[return-value]


def _axis_segment(first: Any, second: Any) -> _AxisSegment | None:
    first_xy = _point_xy(first)
    second_xy = _point_xy(second)
    if first_xy is None or second_xy is None:
        return None
    x0, y0 = first_xy
    x1, y1 = second_xy
    if abs(y1 - y0) <= _AXIS_TOLERANCE_PT and abs(x1 - x0) > _AXIS_TOLERANCE_PT:
        return _AxisSegment("horizontal", (y0 + y1) / 2.0, min(x0, x1), max(x0, x1))
    if abs(x1 - x0) <= _AXIS_TOLERANCE_PT and abs(y1 - y0) > _AXIS_TOLERANCE_PT:
        return _AxisSegment("vertical", (x0 + x1) / 2.0, min(y0, y1), max(y0, y1))
    return None


def _rectangle_segments(rect: Any) -> tuple[_AxisSegment, ...]:
    bbox = _rect_xyxy(rect)
    if bbox is None:
        return ()
    x0, y0, x1, y1 = bbox
    corners = (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    )
    return tuple(
        segment
        for first, second in corners
        if (segment := _axis_segment(first, second)) is not None
    )


def _drawing_segments(drawings: Sequence[Mapping[str, Any]]) -> tuple[_AxisSegment, ...]:
    segments: list[_AxisSegment] = []
    for drawing in drawings:
        items = drawing.get("items", ())
        if not isinstance(items, (tuple, list)):
            continue
        for item in items:
            if not isinstance(item, (tuple, list)) or not item:
                continue
            if item[0] == "l" and len(item) >= 3:
                segment = _axis_segment(item[1], item[2])
                if segment is not None:
                    segments.append(segment)
            elif item[0] == "re" and len(item) >= 2:
                segments.extend(_rectangle_segments(item[1]))
    return tuple(segments)


def _join_collinear_segments(
    segments: Sequence[_AxisSegment],
) -> tuple[_AxisSegment, ...]:
    joined: list[_AxisSegment] = []
    for orientation in ("horizontal", "vertical"):
        current: _AxisSegment | None = None
        candidates = sorted(
            (segment for segment in segments if segment.orientation == orientation),
            key=lambda segment: (segment.coordinate, segment.start, segment.end),
        )
        for segment in candidates:
            if (
                current is not None
                and abs(current.coordinate - segment.coordinate) <= _AXIS_TOLERANCE_PT
                and segment.start <= current.end + _JOIN_GAP_PT
            ):
                current = _AxisSegment(
                    orientation,
                    (current.coordinate + segment.coordinate) / 2.0,
                    min(current.start, segment.start),
                    max(current.end, segment.end),
                )
            else:
                if current is not None:
                    joined.append(current)
                current = segment
        if current is not None:
            joined.append(current)
    return tuple(
        sorted(
            joined,
            key=lambda segment: (
                segment.coordinate,
                segment.start,
                segment.end,
                segment.orientation,
            ),
        )
    )


def _dedupe_positions(positions: Sequence[float]) -> tuple[float, ...]:
    result: list[float] = []
    for position in sorted(positions):
        if not result or position - result[-1] > _AXIS_TOLERANCE_PT:
            result.append(position)
        else:
            result[-1] = (result[-1] + position) / 2.0
    return tuple(result)


def _bbox_area(bbox: BBox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _intersection_area(left: BBox, right: BBox) -> float:
    return _bbox_area(
        (
            max(left[0], right[0]),
            max(left[1], right[1]),
            min(left[2], right[2]),
            min(left[3], right[3]),
        )
    )


def _expand_bbox(bbox: BBox, padding: float) -> BBox:
    return (bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding)


def _point_in_bbox(point: tuple[float, float], bbox: BBox) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def text_belongs_to_frame(text_bbox: BBox, frame_bbox: BBox) -> bool:
    area = _bbox_area(text_bbox)
    if area <= 0.0:
        return False
    center_x = (text_bbox[0] + text_bbox[2]) / 2.0
    center_y = (text_bbox[1] + text_bbox[3]) / 2.0
    padded = _expand_bbox(frame_bbox, TEXT_FRAME_PADDING_PT)
    return _point_in_bbox((center_x, center_y), padded) or (
        _intersection_area(text_bbox, padded) / area >= MIN_TEXT_OVERLAP_RATIO
    )


def _covers(segment: _AxisSegment, start: float, end: float) -> bool:
    return segment.start <= start + _AXIS_TOLERANCE_PT and segment.end >= end - _AXIS_TOLERANCE_PT


def _layout_conflict(
    layout_profile_match: LayoutProfileMatch | None,
    associated_text_ids: Sequence[str],
) -> bool:
    if layout_profile_match is None:
        return False
    associated = set(associated_text_ids)
    return any(
        assignment.observation_id in associated
        and assignment.region_id in {"title_block", "revision_table", "archive_strip", "page_frame"}
        for assignment in layout_profile_match.assignments
    )


def _text_cell_index(
    observation: TextObservation,
    cell_boundaries: Sequence[float],
) -> int:
    center_x = (observation.bbox_pdf[0] + observation.bbox_pdf[2]) / 2.0
    for index in range(len(cell_boundaries) - 1):
        if center_x <= cell_boundaries[index + 1]:
            return index
    return len(cell_boundaries) - 2


def _ordered_text_ids(
    observations: Sequence[TextObservation],
    frame_bbox: BBox,
    cell_boundaries: Sequence[float],
) -> tuple[str, ...]:
    entries = [
        (
            _text_cell_index(observation, cell_boundaries),
            observation,
        )
        for observation in observations
        if text_belongs_to_frame(observation.bbox_pdf, frame_bbox)
    ]
    level_order = {"line": 0, "span": 1, "word": 2, "character": 3}
    entries.sort(
        key=lambda item: (
            item[0],
            item[1].bbox_pdf[1],
            item[1].bbox_pdf[0],
            level_order.get(item[1].observation_level, 99),
            item[1].observation_id,
        )
    )
    ordered: list[str] = []
    seen: set[str] = set()
    for _, observation in entries:
        if observation.observation_id not in seen:
            seen.add(observation.observation_id)
            ordered.append(observation.observation_id)
    return tuple(ordered)


def _geometry_digest(
    *,
    page_index: int,
    frame_bbox: BBox,
    cell_boundaries: Sequence[float],
) -> str:
    payload = {
        "page_index": page_index,
        "bbox": [round(value, 3) for value in frame_bbox],
        "cells": [round(value, 3) for value in cell_boundaries],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _frame_observation(
    *,
    page_index: int,
    source_sha256: str,
    frame_bbox: BBox,
    cell_boundaries: Sequence[float],
    text_observations: Sequence[TextObservation],
    transform: PageTransform,
    layout_profile_match: LayoutProfileMatch | None,
) -> GdtFrameObservation | None:
    associated_ids = _ordered_text_ids(
        text_observations,
        frame_bbox,
        cell_boundaries,
    )
    if _layout_conflict(layout_profile_match, associated_ids):
        return None
    geometry_sha256 = _geometry_digest(
        page_index=page_index,
        frame_bbox=frame_bbox,
        cell_boundaries=cell_boundaries,
    )
    observation_id = hashlib.sha256(
        f"{source_sha256}:{page_index}:gdt-frame:{geometry_sha256}".encode("utf-8")
    ).hexdigest()[:24]
    cells = tuple(
        GdtCellObservation(
            cell_index=index,
            bbox_pdf=(
                cell_boundaries[index],
                frame_bbox[1],
                cell_boundaries[index + 1],
                frame_bbox[3],
            ),
            bbox_normalized=transform.normalize_bbox(
                (
                    cell_boundaries[index],
                    frame_bbox[1],
                    cell_boundaries[index + 1],
                    frame_bbox[3],
                )
            ),
        )
        for index in range(len(cell_boundaries) - 1)
    )
    return GdtFrameObservation(
        observation_id=observation_id,
        page_index=page_index,
        bbox_pdf=frame_bbox,
        bbox_normalized=transform.normalize_bbox(frame_bbox),
        cells=cells,
        associated_text_observation_ids=associated_ids,
        proposal_source="native_vector",
        proposal_state="complete",
        geometry_sha256=geometry_sha256,
    )


def build_page_gdt_frame_observations(
    *,
    page_index: int,
    page_width: float,
    page_height: float,
    source_sha256: str,
    text_observations: Sequence[TextObservation],
    drawings: Sequence[Mapping[str, Any]],
    transform: PageTransform,
    layout_profile_match: LayoutProfileMatch | None,
) -> tuple[GdtFrameObservation, ...]:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page dimensions must be positive")
    joined = _join_collinear_segments(_drawing_segments(drawings))
    horizontals = tuple(segment for segment in joined if segment.orientation == "horizontal")
    verticals = tuple(segment for segment in joined if segment.orientation == "vertical")
    proposals: dict[BBox, GdtFrameObservation] = {}
    for top, bottom in combinations(horizontals, 2):
        if top.coordinate >= bottom.coordinate:
            continue
        y0, y1 = top.coordinate, bottom.coordinate
        height = y1 - y0
        if not MIN_FRAME_HEIGHT_PT <= height <= MAX_FRAME_HEIGHT_PT:
            continue
        crossing = tuple(
            segment
            for segment in verticals
            if segment.start <= y0 + _AXIS_TOLERANCE_PT
            and segment.end >= y1 - _AXIS_TOLERANCE_PT
        )
        cell_boundaries = _dedupe_positions(
            segment.coordinate for segment in crossing
        )
        if len(cell_boundaries) < 3:
            continue
        if any(
            segment.start < y0 - _AXIS_TOLERANCE_PT
            or segment.end > y1 + _AXIS_TOLERANCE_PT
            for segment in crossing
        ):
            continue
        x0, x1 = cell_boundaries[0], cell_boundaries[-1]
        width = x1 - x0
        if not _MIN_FRAME_WIDTH_PT <= width <= MAX_FRAME_WIDTH_PT:
            continue
        if not _covers(top, x0, x1) or not _covers(bottom, x0, x1):
            continue
        full_width_horizontals = tuple(
            segment
            for segment in horizontals
            if y0 - _AXIS_TOLERANCE_PT <= segment.coordinate <= y1 + _AXIS_TOLERANCE_PT
            and _covers(segment, x0, x1)
        )
        if len(full_width_horizontals) != 2:
            continue
        frame_bbox = (x0, y0, x1, y1)
        proposal = _frame_observation(
            page_index=page_index,
            source_sha256=source_sha256,
            frame_bbox=frame_bbox,
            cell_boundaries=cell_boundaries,
            text_observations=tuple(
                observation
                for observation in text_observations
                if observation.page_index == page_index
            ),
            transform=transform,
            layout_profile_match=layout_profile_match,
        )
        if proposal is not None:
            proposals[frame_bbox] = proposal
    return tuple(
        sorted(
            proposals.values(),
            key=lambda proposal: (
                proposal.bbox_pdf[1],
                proposal.bbox_pdf[0],
                proposal.geometry_sha256,
            ),
        )
    )


__all__ = [
    "GdtCellObservation",
    "GdtFrameObservation",
    "MAX_FRAME_HEIGHT_PT",
    "MAX_FRAME_WIDTH_PT",
    "MIN_FRAME_HEIGHT_PT",
    "MIN_TEXT_OVERLAP_RATIO",
    "TEXT_FRAME_PADDING_PT",
    "build_page_gdt_frame_observations",
    "text_belongs_to_frame",
]
