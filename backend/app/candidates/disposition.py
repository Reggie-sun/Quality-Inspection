from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import AbstractSet, Literal, Sequence

from app.candidates.parser import NUMBER, normalize_text, parse_annotation
from app.candidates.technical_requirements import (
    is_standalone_executable_requirement,
)
from app.pdf.layout_profiles import PHYSICAL_PAGE_OUTER_EDGE_EVIDENCE_CODE
from app.pdf.schemas import ObservationRegionAssignment, TextObservation


PRIMARY_DISPOSITION_RULE_VERSION = "p0-a1-r1"
WELLI_LAYOUT_RULE_VERSION = "p0-a2-welli-layout/1"
EXACT_METADATA_LABELS = frozenset(
    {
        "设计",
        "校对",
        "审核",
        "批准",
        "签名",
        "日期",
        "重量",
        "比例",
        "图样代号",
        "物料编码",
    }
)
DRAWING_SCALE = re.compile(r"^[1-9][0-9]*\s*:\s*[1-9][0-9]*$")
SECTION_VIEW_LABEL = re.compile(r"^(?P<label>[A-Z])\s*-\s*(?P=label)$")
STANDALONE_NUMBER = re.compile(rf"^{NUMBER}$")
STANDALONE_ROMAN_LABEL = re.compile(
    r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)$"
)
EXACT_WATERMARK_LABELS = frozenset(
    {
        "CONFIDENTIAL",
        "DRAFT",
        "SAMPLE",
        "作废",
        "仅供参考",
        "仅供审阅",
        "受控",
        "机密",
        "样本",
        "样张",
    }
)
REPEATED_OVERLAY_POSITION_GRID = 0.05
PAGE_FRAME_EDGE_RATIO = 0.02
TITLE_BLOCK_MIN_X = 0.65
TITLE_BLOCK_MIN_Y = 0.82
WELLI_PROFILE_IDS = frozenset(
    {
        "welli-a3-landscape/1",
        "welli-a4-portrait/1",
        "welli-a3-portrait/1",
    }
)
WELLI_TITLE_FIXED_LABELS = frozenset(
    {
        "更改文件号",
        "版本号",
        "设计",
        "签名",
        "年月日标准化",
        "年月日",
        "校对",
        "工艺",
        "批准",
        "审核",
        "重量",
        "重量/kg",
        "比例",
        "图样代号",
        "物料编码",
        "第一角法",
        "表面积",
        "共张",
        "第张",
    }
)
WELLI_ARCHIVE_LABEL_BY_CELL_ID = {
    "archive-label-1": "借通用件登记",
    "archive-label-2": "描图",
    "archive-label-3": "校描",
    "archive-label-4": "旧底图总号",
    "archive-label-5": "签字",
    "archive-label-6": "日期",
}
WELLI_REVISION_MARKER_BY_CELL_ID = {
    "revision-marker-1": "1",
    "revision-marker-2": "2",
    "revision-marker-3": "3",
}
WELLI_PAGE_FRAME_NUMBER_BY_CELL_ID = {
    "page-frame-top-1": "1",
    "page-frame-top-2": "2",
    "page-frame-bottom-1": "1",
    "page-frame-bottom-2": "2",
}


@dataclass(frozen=True)
class PrimaryDispositionDecision:
    disposition: Literal["reference_context", "non_inspection", "ambiguous"]
    reason: str
    rule_version: str = PRIMARY_DISPOSITION_RULE_VERSION
    requires_confirmation: bool = False


def _is_engineering_semantic(observation: TextObservation) -> bool:
    normalized = normalize_text(observation.normalized_text or observation.raw_text)
    if STANDALONE_NUMBER.fullmatch(normalized):
        return True
    if is_standalone_executable_requirement(normalized):
        return True
    try:
        parse_annotation(normalized)
    except ValueError:
        return False
    return True


def _position_bucket(
    bbox_normalized: tuple[float, float, float, float],
) -> tuple[int, int]:
    x0, y0, x1, y1 = bbox_normalized
    center_x = (x0 + x1) / 2
    center_y = (y0 + y1) / 2
    return (
        round(center_x / REPEATED_OVERLAY_POSITION_GRID),
        round(center_y / REPEATED_OVERLAY_POSITION_GRID),
    )


def _bbox_center(
    bbox_normalized: tuple[float, float, float, float],
) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox_normalized
    return (x0 + x1) / 2, (y0 + y1) / 2


def _standalone_number_region(
    observation: TextObservation,
) -> Literal["page_frame", "title_block"] | None:
    center_x, center_y = _bbox_center(observation.bbox_normalized)
    if (
        center_y <= PAGE_FRAME_EDGE_RATIO
        or center_y >= 1.0 - PAGE_FRAME_EDGE_RATIO
    ):
        return "page_frame"
    if center_x >= TITLE_BLOCK_MIN_X and center_y >= TITLE_BLOCK_MIN_Y:
        return "title_block"
    return None


def repeated_page_overlay_observation_ids(
    observations: Sequence[TextObservation],
) -> frozenset[str]:
    grouped: dict[
        tuple[str, tuple[int, int]],
        list[TextObservation],
    ] = defaultdict(list)
    for observation in observations:
        normalized = normalize_text(
            observation.normalized_text or observation.raw_text
        )
        if not normalized or _is_engineering_semantic(observation):
            continue
        grouped[(normalized, _position_bucket(observation.bbox_normalized))].append(
            observation
        )

    repeated_ids: set[str] = set()
    for group in grouped.values():
        if len({observation.page_index for observation in group}) < 2:
            continue
        repeated_ids.update(observation.observation_id for observation in group)
    return frozenset(repeated_ids)


def _welli_layout_decision(
    observation: TextObservation,
    *,
    normalized: str,
    layout_assignment: ObservationRegionAssignment | None,
    engineering_preservation_observation_ids: AbstractSet[str],
) -> PrimaryDispositionDecision | None:
    assignment = layout_assignment
    if (
        assignment is None
        or assignment.observation_id != observation.observation_id
        or assignment.page_index != observation.page_index
        or assignment.profile_id not in WELLI_PROFILE_IDS
        or assignment.rule_version != WELLI_LAYOUT_RULE_VERSION
    ):
        return None

    if (
        assignment.region_id == "page_frame"
        and assignment.cell_role == "page_frame_number"
        and WELLI_PAGE_FRAME_NUMBER_BY_CELL_ID.get(assignment.cell_id)
        == normalized
        and (
            assignment.boundary_distance_mm >= 1.0
            or welli_page_frame_assignment_touches_outer_edge(assignment)
        )
    ):
        return PrimaryDispositionDecision(
            disposition="non_inspection",
            reason="welli_page_frame_number",
            rule_version=WELLI_LAYOUT_RULE_VERSION,
        )

    if assignment.boundary_distance_mm < 1.0:
        return None

    if (
        assignment.region_id == "revision_table"
        and assignment.cell_role == "revision_marker"
        and WELLI_REVISION_MARKER_BY_CELL_ID.get(assignment.cell_id)
        == normalized
    ):
        return PrimaryDispositionDecision(
            disposition="reference_context",
            reason="welli_revision_marker",
            rule_version=WELLI_LAYOUT_RULE_VERSION,
        )

    if observation.observation_id in engineering_preservation_observation_ids:
        return None

    if assignment.region_id == "title_block":
        if normalized in WELLI_TITLE_FIXED_LABELS:
            return PrimaryDispositionDecision(
                disposition="non_inspection",
                reason="welli_title_fixed_label",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        if assignment.cell_role == "title_metadata_value":
            return PrimaryDispositionDecision(
                disposition="reference_context",
                reason="welli_title_metadata_value",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        if assignment.cell_role == "title_approval_context":
            return PrimaryDispositionDecision(
                disposition="reference_context",
                reason="welli_title_approval_context",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        return None

    if assignment.region_id == "revision_table":
        if (
            assignment.cell_role == "revision_header"
            and normalized in {"标记", "更改描述"}
        ):
            return PrimaryDispositionDecision(
                disposition="non_inspection",
                reason="welli_revision_header",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        if assignment.cell_role == "revision_description":
            return PrimaryDispositionDecision(
                disposition="reference_context",
                reason="welli_revision_description",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        return None

    if assignment.region_id == "archive_strip":
        if (
            assignment.cell_role == "archive_label"
            and WELLI_ARCHIVE_LABEL_BY_CELL_ID.get(assignment.cell_id)
            == normalized
        ):
            return PrimaryDispositionDecision(
                disposition="non_inspection",
                reason="welli_archive_label",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        if assignment.cell_role == "archive_record":
            return PrimaryDispositionDecision(
                disposition="reference_context",
                reason="welli_archive_record",
                rule_version=WELLI_LAYOUT_RULE_VERSION,
            )
        return None

    return None


def welli_page_frame_assignment_touches_outer_edge(
    assignment: ObservationRegionAssignment,
) -> bool:
    return (
        assignment.region_id == "page_frame"
        and assignment.cell_role == "page_frame_number"
        and PHYSICAL_PAGE_OUTER_EDGE_EVIDENCE_CODE
        in assignment.assignment_evidence_codes
    )


def classify_primary_disposition(
    observation: TextObservation,
    *,
    has_visual_context: bool = False,
    repeated_overlay_observation_ids: AbstractSet[str] = frozenset(),
    layout_assignment: ObservationRegionAssignment | None = None,
    welli_watermark_observation_ids: AbstractSet[str] = frozenset(),
    engineering_preservation_observation_ids: AbstractSet[str] = frozenset(),
) -> PrimaryDispositionDecision | None:
    normalized = normalize_text(observation.normalized_text or observation.raw_text)
    if normalized in EXACT_METADATA_LABELS:
        return PrimaryDispositionDecision(
            disposition="non_inspection",
            reason="exact_metadata_label",
        )
    if DRAWING_SCALE.fullmatch(normalized):
        return PrimaryDispositionDecision(
            disposition="non_inspection",
            reason="drawing_scale",
        )
    if SECTION_VIEW_LABEL.fullmatch(normalized.upper()):
        return PrimaryDispositionDecision(
            disposition="non_inspection",
            reason="section_view_label",
        )
    layout_decision = _welli_layout_decision(
        observation,
        normalized=normalized,
        layout_assignment=layout_assignment,
        engineering_preservation_observation_ids=(
            engineering_preservation_observation_ids
        ),
    )
    if layout_decision is not None:
        return layout_decision
    if observation.observation_id in welli_watermark_observation_ids:
        if observation.observation_id in engineering_preservation_observation_ids:
            return None
        return PrimaryDispositionDecision(
            disposition="non_inspection",
            reason="welli_same_page_watermark",
            rule_version=WELLI_LAYOUT_RULE_VERSION,
        )
    if STANDALONE_NUMBER.fullmatch(normalized):
        if has_visual_context:
            return None
        region = _standalone_number_region(observation)
        if region == "page_frame":
            return PrimaryDispositionDecision(
                disposition="non_inspection",
                reason="page_frame_number",
            )
        if region == "title_block":
            return PrimaryDispositionDecision(
                disposition="ambiguous",
                reason="title_block_number",
                requires_confirmation=True,
            )
        return None
    if STANDALONE_ROMAN_LABEL.fullmatch(normalized.upper()):
        if has_visual_context:
            return None
        return PrimaryDispositionDecision(
            disposition="ambiguous",
            reason="standalone_roman_label",
            requires_confirmation=True,
        )
    if observation.observation_id in repeated_overlay_observation_ids:
        if normalized.upper() not in EXACT_WATERMARK_LABELS:
            return PrimaryDispositionDecision(
                disposition="ambiguous",
                reason="repeated_page_text",
                requires_confirmation=True,
            )
        return PrimaryDispositionDecision(
            disposition="non_inspection",
            reason="repeated_page_overlay",
        )
    return None
