from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.pdf.schemas import LayoutProfileMatch, TextObservation


MM_PER_PDF_POINT = 25.4 / 72.0
PAGE_SIZE_TOLERANCE_MM = 0.5
GRID_TOLERANCE_MM = 1.0
RULE_VERSION = "p0-a2-welli-layout/1"
_AXIS_TOLERANCE_MM = 0.05
_POSITION_CLUSTER_TOLERANCE_MM = 0.1
_MIN_AXIS_SEGMENT_MM = 1.0

_TITLE_GRID_X_MM = (
    0.0,
    12.0,
    24.0,
    40.0,
    52.0,
    64.0,
    80.0,
    106.0,
    118.0,
    130.0,
    144.0,
    180.0,
)
_TITLE_GRID_Y_MM = (
    0.0,
    7.0,
    14.0,
    18.0,
    21.0,
    28.0,
    35.0,
    38.0,
    42.0,
    47.0,
    49.0,
    56.0,
)
_REVISION_GRID_X_MM = (0.0, 10.0, 90.0)
_REVISION_GRID_Y_MM = (0.0, 5.0, 15.0, 25.0, 35.0)
_ARCHIVE_GRID_X_MM = (0.0, 25.0)
_ARCHIVE_GRID_Y_MM = (
    0.0,
    7.0,
    17.0,
    24.0,
    34.0,
    41.0,
    51.0,
    58.0,
    68.0,
    75.0,
    85.0,
    92.0,
    102.0,
)


@dataclass(frozen=True)
class _Profile:
    profile_id: str
    width_mm: float
    height_mm: float
    watermark_spacing_mm: tuple[float, float]

    @property
    def body_frame(self) -> tuple[float, float, float, float]:
        return (25.0, 5.0, self.width_mm - 5.0, self.height_mm - 5.0)

    @property
    def title_box(self) -> tuple[float, float, float, float]:
        return (
            self.width_mm - 185.0,
            self.height_mm - 61.0,
            self.width_mm - 5.0,
            self.height_mm - 5.0,
        )

    @property
    def revision_box(self) -> tuple[float, float, float, float]:
        return (self.width_mm - 95.0, 5.0, self.width_mm - 5.0, 40.0)

    @property
    def archive_box(self) -> tuple[float, float, float, float]:
        return (0.0, self.height_mm - 107.0, 25.0, self.height_mm - 5.0)


@dataclass(frozen=True)
class _SegmentMm:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def is_vertical(self) -> bool:
        return abs(self.x1 - self.x0) <= _AXIS_TOLERANCE_MM

    @property
    def is_horizontal(self) -> bool:
        return abs(self.y1 - self.y0) <= _AXIS_TOLERANCE_MM


_PROFILES = (
    _Profile("welli-a3-landscape/1", 420.0, 297.0, (100.0, 80.0)),
    _Profile("welli-a4-portrait/1", 210.0, 297.0, (65.0, 80.0)),
    _Profile("welli-a3-portrait/1", 297.0, 420.0, (100.0, 90.0)),
)


def _point_xy(point: Any) -> tuple[float, float]:
    if hasattr(point, "x") and hasattr(point, "y"):
        return (float(point.x), float(point.y))
    return (float(point[0]), float(point[1]))


def _rect_xyxy(rect: Any) -> tuple[float, float, float, float]:
    if all(hasattr(rect, name) for name in ("x0", "y0", "x1", "y1")):
        return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
    return tuple(float(rect[index]) for index in range(4))  # type: ignore[return-value]


def _segment_from_points(first: Any, second: Any) -> _SegmentMm | None:
    x0_pt, y0_pt = _point_xy(first)
    x1_pt, y1_pt = _point_xy(second)
    segment = _SegmentMm(
        x0=x0_pt * MM_PER_PDF_POINT,
        y0=y0_pt * MM_PER_PDF_POINT,
        x1=x1_pt * MM_PER_PDF_POINT,
        y1=y1_pt * MM_PER_PDF_POINT,
    )
    if not segment.is_vertical and not segment.is_horizontal:
        return None
    return segment


def _drawing_segments(drawings: Sequence[Mapping[str, Any]]) -> tuple[_SegmentMm, ...]:
    segments: list[_SegmentMm] = []
    for drawing in drawings:
        for item in drawing.get("items", ()):
            if not item:
                continue
            opcode = item[0]
            if opcode == "l" and len(item) >= 3:
                segment = _segment_from_points(item[1], item[2])
                if segment is not None:
                    segments.append(segment)
            elif opcode == "re" and len(item) >= 2:
                x0_pt, y0_pt, x1_pt, y1_pt = _rect_xyxy(item[1])
                corners = (
                    ((x0_pt, y0_pt), (x1_pt, y0_pt)),
                    ((x1_pt, y0_pt), (x1_pt, y1_pt)),
                    ((x1_pt, y1_pt), (x0_pt, y1_pt)),
                    ((x0_pt, y1_pt), (x0_pt, y0_pt)),
                )
                for first, second in corners:
                    segment = _segment_from_points(first, second)
                    if segment is not None:
                        segments.append(segment)
    return tuple(
        sorted(
            segments,
            key=lambda item: (item.x0, item.y0, item.x1, item.y1),
        )
    )


def _cluster_positions(positions: Sequence[float]) -> tuple[float, ...]:
    clusters: list[list[float]] = []
    for position in sorted(positions):
        if (
            not clusters
            or position - clusters[-1][-1] > _POSITION_CLUSTER_TOLERANCE_MM
        ):
            clusters.append([position])
        else:
            clusters[-1].append(position)
    return tuple(sum(cluster) / len(cluster) for cluster in clusters)


def _axis_position_matches(
    segments: Sequence[_SegmentMm],
    *,
    axis: str,
    expected_position: float,
    span_start: float,
    span_end: float,
) -> bool:
    positions: list[float] = []
    for segment in segments:
        if axis == "x" and segment.is_vertical:
            position = (segment.x0 + segment.x1) / 2.0
            segment_start, segment_end = sorted((segment.y0, segment.y1))
        elif axis == "y" and segment.is_horizontal:
            position = (segment.y0 + segment.y1) / 2.0
            segment_start, segment_end = sorted((segment.x0, segment.x1))
        else:
            continue
        overlap = min(segment_end, span_end) - max(segment_start, span_start)
        if overlap < _MIN_AXIS_SEGMENT_MM:
            continue
        if abs(position - expected_position) <= GRID_TOLERANCE_MM:
            positions.append(position)
    return len(_cluster_positions(positions)) == 1


def _grid_matches(
    segments: Sequence[_SegmentMm],
    *,
    box: tuple[float, float, float, float],
    local_x_positions: Sequence[float],
    local_y_positions: Sequence[float],
) -> bool:
    x0, y0, x1, y1 = box
    return all(
        _axis_position_matches(
            segments,
            axis="x",
            expected_position=x0 + local_x,
            span_start=y0,
            span_end=y1,
        )
        for local_x in local_x_positions
    ) and all(
        _axis_position_matches(
            segments,
            axis="y",
            expected_position=y0 + local_y,
            span_start=x0,
            span_end=x1,
        )
        for local_y in local_y_positions
    )


def _box_matches(
    segments: Sequence[_SegmentMm],
    box: tuple[float, float, float, float],
) -> bool:
    x0, y0, x1, y1 = box
    return (
        _axis_position_matches(
            segments,
            axis="x",
            expected_position=x0,
            span_start=y0,
            span_end=y1,
        )
        and _axis_position_matches(
            segments,
            axis="x",
            expected_position=x1,
            span_start=y0,
            span_end=y1,
        )
        and _axis_position_matches(
            segments,
            axis="y",
            expected_position=y0,
            span_start=x0,
            span_end=x1,
        )
        and _axis_position_matches(
            segments,
            axis="y",
            expected_position=y1,
            span_start=x0,
            span_end=x1,
        )
    )


def _compact_text(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split())


def _text_anchor_evidence(
    observations: Sequence[TextObservation],
) -> tuple[str, ...]:
    texts = {
        _compact_text(observation.normalized_text)
        for observation in observations
        if observation.source_type == "native"
        and observation.observation_level == "line"
    }
    evidence: list[str] = []
    if len(texts & {"物料编码", "图样代号", "比例", "重量"}) >= 3:
        evidence.append("title_anchor_quorum")
    if {"标记", "更改描述"} <= texts:
        evidence.append("revision_anchor_quorum")
    if "旧底图总号" in texts:
        evidence.append("archive_anchor")
    return tuple(sorted(evidence))


def _page_profile(
    *,
    page_width_pt: float,
    page_height_pt: float,
    page_rotation: int,
) -> _Profile | None:
    if page_rotation != 0:
        return None
    width_mm = page_width_pt * MM_PER_PDF_POINT
    height_mm = page_height_pt * MM_PER_PDF_POINT
    matches = tuple(
        profile
        for profile in _PROFILES
        if math.isclose(
            width_mm,
            profile.width_mm,
            abs_tol=PAGE_SIZE_TOLERANCE_MM,
        )
        and math.isclose(
            height_mm,
            profile.height_mm,
            abs_tol=PAGE_SIZE_TOLERANCE_MM,
        )
    )
    return matches[0] if len(matches) == 1 else None


def match_welli_layout_profile(
    *,
    page_index: int,
    page_width_pt: float,
    page_height_pt: float,
    page_rotation: int,
    observations: Sequence[TextObservation],
    drawings: Sequence[Mapping[str, Any]],
) -> LayoutProfileMatch | None:
    profile = _page_profile(
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
        page_rotation=page_rotation,
    )
    if profile is None:
        return None

    segments = _drawing_segments(drawings)
    if not _box_matches(segments, profile.body_frame):
        return None

    geometry_evidence = ["body_frame"]
    if _grid_matches(
        segments,
        box=profile.title_box,
        local_x_positions=_TITLE_GRID_X_MM,
        local_y_positions=_TITLE_GRID_Y_MM,
    ):
        geometry_evidence.append("title_grid")
    if _grid_matches(
        segments,
        box=profile.revision_box,
        local_x_positions=_REVISION_GRID_X_MM,
        local_y_positions=_REVISION_GRID_Y_MM,
    ):
        geometry_evidence.append("revision_grid")
    if _grid_matches(
        segments,
        box=profile.archive_box,
        local_x_positions=_ARCHIVE_GRID_X_MM,
        local_y_positions=_ARCHIVE_GRID_Y_MM,
    ):
        geometry_evidence.append("archive_grid")
    if len(geometry_evidence) < 3:
        return None

    text_anchor_evidence = _text_anchor_evidence(observations)
    if len(text_anchor_evidence) < 2:
        return None

    return LayoutProfileMatch(
        page_index=page_index,
        profile_id=profile.profile_id,
        match_state="high_confidence",
        geometry_evidence_codes=tuple(sorted(geometry_evidence)),
        text_anchor_evidence_codes=text_anchor_evidence,
        assignments=(),
        rule_version=RULE_VERSION,
    )


def welli_same_page_watermark_observation_ids(
    *,
    profile_match: LayoutProfileMatch | None,
    observations: Sequence[TextObservation],
) -> frozenset[str]:
    del profile_match, observations
    return frozenset()
