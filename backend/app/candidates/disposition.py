from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import AbstractSet, Literal, Sequence

from app.candidates.parser import NUMBER, normalize_text, parse_annotation
from app.candidates.schemas import Candidate, stable_candidate_id
from app.pdf.schemas import TextObservation


INSPECTION_VERB = re.compile(r"检查|检验|检测|测量|确认|验证")
VERIFIABLE_CRITERION = re.compile(
    r"不得|不允许|应为|应达到|应符合|符合|不大于|不小于|≤|≥|无(?:毛刺|裂纹|缺陷|损伤)"
)
PRIMARY_DISPOSITION_RULE_VERSION = "p0-a1-r1"
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


@dataclass(frozen=True)
class PrimaryDispositionDecision:
    disposition: Literal["non_inspection", "ambiguous"]
    reason: str
    rule_version: str = PRIMARY_DISPOSITION_RULE_VERSION
    requires_confirmation: bool = False


def classify_technical_requirement(
    raw_text: str,
    coordinates: tuple[float, float, float, float] | None = None,
    *,
    source_id: str,
) -> Candidate | None:
    source_identity = source_id.strip()
    if not source_identity:
        raise ValueError("source_id must be non-blank")
    normalized = normalize_text(raw_text)
    if not INSPECTION_VERB.search(normalized):
        return None
    if not VERIFIABLE_CRITERION.search(normalized):
        return None
    return Candidate(
        candidate_id=stable_candidate_id(
            "general-requirement",
            source_identity,
            raw_text,
        ),
        item_type="general_requirement",
        raw_text=raw_text,
        normalized_text=normalized,
        coordinates=coordinates,
        scope="global_requirement",
        balloon_required=False,
    )


def _is_engineering_semantic(observation: TextObservation) -> bool:
    normalized = normalize_text(observation.normalized_text or observation.raw_text)
    if STANDALONE_NUMBER.fullmatch(normalized):
        return True
    if INSPECTION_VERB.search(normalized) and VERIFIABLE_CRITERION.search(normalized):
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


def classify_primary_disposition(
    observation: TextObservation,
    *,
    has_visual_context: bool = False,
    repeated_overlay_observation_ids: AbstractSet[str] = frozenset(),
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
