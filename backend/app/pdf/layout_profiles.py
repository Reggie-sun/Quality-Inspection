from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.pdf.schemas import (
    LayoutProfileMatch,
    ObservationRegionAssignment,
    TextObservation,
)


MM_PER_PDF_POINT = 25.4 / 72.0
PAGE_SIZE_TOLERANCE_MM = 0.5
GRID_TOLERANCE_MM = 1.0
RULE_VERSION = "p0-a2-welli-layout/1"
PHYSICAL_PAGE_OUTER_EDGE_EVIDENCE_CODE = "physical_page_outer_edge"
_AXIS_TOLERANCE_MM = 0.05
_POSITION_CLUSTER_TOLERANCE_MM = 0.1
_FLOAT_COMPARISON_ABS_TOLERANCE_MM = 1e-9
_MIN_AXIS_SEGMENT_MM = 1.0
_HORIZONTAL_ASSIGNMENT_ANGLE_TOLERANCE_DEGREES = 2.0
_WATERMARK_ANGLE_DEGREES = -30.0
_WATERMARK_ANGLE_TOLERANCE_DEGREES = 2.0
_WATERMARK_SPACING_TOLERANCE_MM = 2.0
_MIN_WATERMARK_NATIVE_LINE_COUNT = 9

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


@dataclass(frozen=True)
class _RoleRectMm:
    region_id: str
    cell_role: str
    cell_id: str
    box: tuple[float, float, float, float]
    expected_text: str | None = None
    center_x_target_mm: float | None = None


_PROFILES = (
    _Profile("welli-a3-landscape/1", 420.0, 297.0, (100.0, 80.0)),
    _Profile("welli-a4-portrait/1", 210.0, 297.0, (65.0, 80.0)),
    _Profile("welli-a3-portrait/1", 297.0, 420.0, (100.0, 90.0)),
)
_PROFILE_BY_ID = {profile.profile_id: profile for profile in _PROFILES}


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


def _role_rectangles(
    profile: _Profile,
    *,
    page_width_mm: float,
    page_height_mm: float,
) -> tuple[_RoleRectMm, ...]:
    title_x0, title_y0, title_x1, title_y1 = profile.title_box
    revision_x0, revision_y0, revision_x1, _ = profile.revision_box
    archive_x0, archive_y0, archive_x1, _ = profile.archive_box
    roles = [
        _RoleRectMm(
            "title_block",
            "title_approval_context",
            "title-approval-context",
            (title_x0, title_y0, title_x0 + 80.0, title_y1),
        ),
        _RoleRectMm(
            "title_block",
            "title_metadata_value",
            "title-metadata-value",
            (title_x0 + 80.0, title_y0, title_x1, title_y1),
        ),
        _RoleRectMm(
            "revision_table",
            "revision_header",
            "revision-header",
            (revision_x0, revision_y0, revision_x1, revision_y0 + 5.0),
        ),
    ]
    for row_index, row_y0 in enumerate((5.0, 15.0, 25.0), start=1):
        roles.extend(
            (
                _RoleRectMm(
                    "revision_table",
                    "revision_marker",
                    f"revision-marker-{row_index}",
                    (
                        revision_x0,
                        revision_y0 + row_y0,
                        revision_x0 + 10.0,
                        revision_y0 + row_y0 + 10.0,
                    ),
                ),
                _RoleRectMm(
                    "revision_table",
                    "revision_description",
                    f"revision-description-{row_index}",
                    (
                        revision_x0 + 10.0,
                        revision_y0 + row_y0,
                        revision_x1,
                        revision_y0 + row_y0 + 10.0,
                    ),
                ),
            )
        )
    archive_rows = tuple(zip(_ARCHIVE_GRID_Y_MM, _ARCHIVE_GRID_Y_MM[1:]))
    for row_index, (local_y0, local_y1) in enumerate(archive_rows):
        record_index = row_index // 2 + 1
        if row_index % 2 == 0:
            cell_role = "archive_label"
            cell_id = f"archive-label-{record_index}"
        else:
            cell_role = "archive_record"
            cell_id = f"archive-record-{record_index}"
        roles.append(
            _RoleRectMm(
                "archive_strip",
                cell_role,
                cell_id,
                (
                    archive_x0,
                    archive_y0 + local_y0,
                    archive_x1,
                    archive_y0 + local_y1,
                ),
            )
        )
    for band, band_y0, band_y1 in (
        ("top", 0.0, 5.0),
        ("bottom", page_height_mm - 5.0, page_height_mm),
    ):
        roles.extend(
            (
                _RoleRectMm(
                    "page_frame",
                    "page_frame_number",
                    f"page-frame-{band}-1",
                    (0.0, band_y0, page_width_mm / 2.0, band_y1),
                    expected_text="1",
                    center_x_target_mm=page_width_mm / 4.0,
                ),
                _RoleRectMm(
                    "page_frame",
                    "page_frame_number",
                    f"page-frame-{band}-2",
                    (
                        page_width_mm / 2.0,
                        band_y0,
                        page_width_mm,
                        band_y1,
                    ),
                    expected_text="2",
                    center_x_target_mm=page_width_mm * 3.0 / 4.0,
                ),
            )
        )
    return tuple(roles)


def _bbox_mm(observation: TextObservation) -> tuple[float, float, float, float]:
    return tuple(  # type: ignore[return-value]
        float(value) * MM_PER_PDF_POINT for value in observation.bbox_pdf
    )


def _horizontal_angle_matches(angle_degrees: float) -> bool:
    normalized = (angle_degrees + 180.0) % 360.0 - 180.0
    return abs(normalized) <= _HORIZONTAL_ASSIGNMENT_ANGLE_TOLERANCE_DEGREES


def _role_boundary_distance(
    bbox: tuple[float, float, float, float],
    role: _RoleRectMm,
) -> float:
    x0, y0, x1, y1 = bbox
    role_x0, role_y0, role_x1, role_y1 = role.box
    return min(
        x0 - role_x0,
        y0 - role_y0,
        role_x1 - x1,
        role_y1 - y1,
    )


def _touches_physical_page_outer_edge(
    *,
    bbox: tuple[float, float, float, float],
    role: _RoleRectMm,
    page_height_mm: float,
) -> bool:
    if role.region_id != "page_frame":
        return False
    _, y0, _, y1 = bbox
    _, role_y0, _, role_y1 = role.box
    return (
        role_y0 == 0.0
        and abs(y0) <= _FLOAT_COMPARISON_ABS_TOLERANCE_MM
    ) or (
        role_y1 == page_height_mm
        and abs(y1 - page_height_mm)
        <= _FLOAT_COMPARISON_ABS_TOLERANCE_MM
    )


def _assignment_for_observation(
    *,
    profile: _Profile,
    page_width_mm: float,
    page_height_mm: float,
    page_index: int,
    observation: TextObservation,
) -> ObservationRegionAssignment | None:
    if (
        observation.page_index != page_index
        or observation.source_type != "native"
        or observation.observation_level != "line"
        or observation.parent_region_id is not None
        or not _horizontal_angle_matches(observation.direction_angle_degrees)
    ):
        return None
    bbox = _bbox_mm(observation)
    x0, y0, x1, y1 = bbox
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0
    compact_text = _compact_text(observation.normalized_text)
    matches: list[tuple[_RoleRectMm, float]] = []
    for role in _role_rectangles(
        profile,
        page_width_mm=page_width_mm,
        page_height_mm=page_height_mm,
    ):
        role_x0, role_y0, role_x1, role_y1 = role.box
        if not (
            role_x0 <= center_x <= role_x1
            and role_y0 <= center_y <= role_y1
        ):
            continue
        boundary_distance = _role_boundary_distance(bbox, role)
        if boundary_distance < 0.0:
            continue
        if role.expected_text is not None:
            if compact_text != role.expected_text:
                continue
            if role.center_x_target_mm is None or (
                abs(center_x - role.center_x_target_mm) > GRID_TOLERANCE_MM
            ):
                continue
        matches.append((role, boundary_distance))
    if len(matches) != 1:
        return None
    role, boundary_distance = matches[0]
    assignment_evidence_codes = (
        "bbox_inside_role",
        "center_in_role",
        "horizontal_direction",
        "single_role",
    )
    if _touches_physical_page_outer_edge(
        bbox=bbox,
        role=role,
        page_height_mm=page_height_mm,
    ):
        assignment_evidence_codes += (
            PHYSICAL_PAGE_OUTER_EDGE_EVIDENCE_CODE,
        )
    return ObservationRegionAssignment(
        observation_id=observation.observation_id,
        page_index=page_index,
        profile_id=profile.profile_id,
        region_id=role.region_id,  # type: ignore[arg-type]
        cell_role=role.cell_role,
        cell_id=role.cell_id,
        assignment_evidence_codes=assignment_evidence_codes,
        boundary_distance_mm=boundary_distance,
        rule_version=RULE_VERSION,
    )


def _observation_assignments(
    *,
    profile: _Profile,
    page_width_mm: float,
    page_height_mm: float,
    page_index: int,
    observations: Sequence[TextObservation],
) -> tuple[ObservationRegionAssignment, ...]:
    assignments = tuple(
        assignment
        for observation in observations
        if (
            assignment := _assignment_for_observation(
                profile=profile,
                page_width_mm=page_width_mm,
                page_height_mm=page_height_mm,
                page_index=page_index,
                observation=observation,
            )
        )
        is not None
    )
    return tuple(
        sorted(
            assignments,
            key=lambda item: (
                item.observation_id,
                item.region_id,
                item.cell_id,
            ),
        )
    )


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
        assignments=_observation_assignments(
            profile=profile,
            page_width_mm=page_width_pt * MM_PER_PDF_POINT,
            page_height_mm=page_height_pt * MM_PER_PDF_POINT,
            page_index=page_index,
            observations=observations,
        ),
        rule_version=RULE_VERSION,
    )


def _angle_matches(actual: float, expected: float, tolerance: float) -> bool:
    difference = (actual - expected + 180.0) % 360.0 - 180.0
    return abs(difference) <= tolerance


def _lattice_cell(
    *,
    x_mm: float,
    y_mm: float,
    origin_x_mm: float,
    origin_y_mm: float,
    spacing_x_mm: float,
    spacing_y_mm: float,
) -> tuple[int, int] | None:
    column = round((x_mm - origin_x_mm) / spacing_x_mm)
    row = round((y_mm - origin_y_mm) / spacing_y_mm)
    expected_x = origin_x_mm + column * spacing_x_mm
    expected_y = origin_y_mm + row * spacing_y_mm
    if (
        abs(x_mm - expected_x) > _WATERMARK_SPACING_TOLERANCE_MM
        or abs(y_mm - expected_y) > _WATERMARK_SPACING_TOLERANCE_MM
    ):
        return None
    return (column, row)


def _has_watermark_lattice_quorum(
    centers: Sequence[tuple[TextObservation, float, float]],
    *,
    spacing_x_mm: float,
    spacing_y_mm: float,
) -> bool:
    for _origin, origin_x, origin_y in centers:
        cells: dict[tuple[int, int], TextObservation] = {}
        has_conflict = False
        for observation, center_x, center_y in centers:
            cell = _lattice_cell(
                x_mm=center_x,
                y_mm=center_y,
                origin_x_mm=origin_x,
                origin_y_mm=origin_y,
                spacing_x_mm=spacing_x_mm,
                spacing_y_mm=spacing_y_mm,
            )
            if cell is None:
                continue
            if cell in cells:
                has_conflict = True
                break
            cells[cell] = observation
        if has_conflict:
            continue
        if (
            len(cells) >= _MIN_WATERMARK_NATIVE_LINE_COUNT
            and len({cell[0] for cell in cells}) >= 2
            and len({cell[1] for cell in cells}) >= 3
        ):
            return True
    return False


def welli_same_page_watermark_observation_ids(
    *,
    profile_match: LayoutProfileMatch | None,
    observations: Sequence[TextObservation],
) -> frozenset[str]:
    if profile_match is None or profile_match.match_state != "high_confidence":
        return frozenset()
    profile = _PROFILE_BY_ID.get(profile_match.profile_id)
    if profile is None:
        return frozenset()
    candidates = tuple(
        sorted(
            (
                observation
                for observation in observations
                if observation.page_index == profile_match.page_index
                and observation.source_type == "native"
                and observation.observation_level == "line"
                and observation.parent_region_id is None
                and _compact_text(observation.normalized_text) == "伟立机器人"
                and _angle_matches(
                    observation.direction_angle_degrees,
                    _WATERMARK_ANGLE_DEGREES,
                    _WATERMARK_ANGLE_TOLERANCE_DEGREES,
                )
            ),
            key=lambda item: item.observation_id,
        )
    )
    if len(candidates) < _MIN_WATERMARK_NATIVE_LINE_COUNT:
        return frozenset()

    centers = tuple(
        (
            observation,
            (bbox[0] + bbox[2]) / 2.0,
            (bbox[1] + bbox[3]) / 2.0,
        )
        for observation in candidates
        for bbox in (_bbox_mm(observation),)
    )
    spacing_x, spacing_y = profile.watermark_spacing_mm
    if not _has_watermark_lattice_quorum(
        centers,
        spacing_x_mm=spacing_x,
        spacing_y_mm=spacing_y,
    ):
        return frozenset()
    return frozenset(observation.observation_id for observation in candidates)
