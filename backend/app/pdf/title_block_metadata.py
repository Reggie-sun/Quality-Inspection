from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from typing import Any


RULE_VERSION = "welli-title-metadata/1"
SIP_FIELD_ORDER = (
    "material_code",
    "material_name",
    "drawing_number",
    "material",
    "revision",
)

_TITLE_LABELS = {
    "material_code": frozenset({"物料编码"}),
    "drawing_number": frozenset({"图样代号"}),
    "material": frozenset({"材质", "材料"}),
    "revision": frozenset({"版本号"}),
}
_ANCHOR_LABELS = frozenset({"物料编码", "图样代号", "版本号"})
_ALL_LABELS = frozenset().union(*_TITLE_LABELS.values())
_CODE_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,63}")
_REVISION_VALUE = re.compile(
    r"[A-Za-z0-9]{1,4}(?:[./-][A-Za-z0-9]{1,4})?"
)
_CJK_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def suggest_sip_metadata(
    pages: list[object],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for page in pages:
        for suggestion in _suggest_page(page):
            grouped.setdefault(str(suggestion["field"]), []).append(suggestion)
    return [
        grouped[field][0]
        for field in SIP_FIELD_ORDER
        if len(grouped.get(field, ())) == 1
    ]


def _suggest_page(page: object) -> list[dict[str, object]]:
    if not isinstance(page, Mapping):
        return []
    width = _positive_number(page.get("width"))
    height = _positive_number(page.get("height"))
    page_index = page.get("page_index")
    raw_observations = page.get("observations")
    if (
        width is None
        or height is None
        or not isinstance(page_index, int)
        or not isinstance(raw_observations, list)
    ):
        return []

    observations = [
        observation
        for raw in raw_observations
        if (
            observation := _native_title_observation(
                raw,
                page_index=page_index,
                page_width=width,
                page_height=height,
            )
        )
        is not None
    ]
    anchor_texts = {
        observation["compact_text"]
        for observation in observations
        if observation["compact_text"] in _ANCHOR_LABELS
    }
    if len(anchor_texts) < 2:
        return []

    suggestions: dict[str, dict[str, object]] = {}
    for field in ("material_code", "drawing_number", "material"):
        label = _unique_label(observations, field)
        if label is None:
            continue
        candidates = _same_row_right_candidates(
            observations,
            label=label,
            value_kind=field,
            page_width=width,
        )
        if len(candidates) != 1:
            continue
        suggestions[field] = _suggestion(
            field=field,
            value=candidates[0],
            label=label,
            evidence_code="same_row_right_of_label",
        )

    revision_label = _unique_label(observations, "revision")
    if revision_label is not None:
        revision_candidates = _same_column_above_candidates(
            observations,
            label=revision_label,
        )
        if len(revision_candidates) == 1:
            suggestions["revision"] = _suggestion(
                field="revision",
                value=revision_candidates[0],
                label=revision_label,
                evidence_code="same_column_above_label",
            )

    drawing_suggestion = suggestions.get("drawing_number")
    drawing_label = _unique_label(observations, "drawing_number")
    if drawing_suggestion is not None and drawing_label is not None:
        drawing_value = next(
            (
                observation
                for observation in observations
                if observation["observation_id"]
                == drawing_suggestion["observation_id"]
            ),
            None,
        )
        if drawing_value is not None:
            name_candidates = _material_name_candidates(
                observations,
                drawing_value=drawing_value,
                page_width=width,
            )
            if len(name_candidates) == 1:
                suggestions["material_name"] = _suggestion(
                    field="material_name",
                    value=name_candidates[0],
                    label=drawing_label,
                    evidence_code="drawing_number_column",
                )

    return [
        suggestions[field]
        for field in SIP_FIELD_ORDER
        if field in suggestions
    ]


def _native_title_observation(
    raw: object,
    *,
    page_index: int,
    page_width: float,
    page_height: float,
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    if (
        raw.get("source_type") != "native"
        or raw.get("observation_level") != "line"
        or raw.get("page_index") != page_index
    ):
        return None
    angle = _number(raw.get("direction_angle_degrees"))
    if angle is None or abs((angle + 180.0) % 360.0 - 180.0) > 2.0:
        return None
    bbox = _bbox(raw.get("bbox_pdf"))
    observation_id = raw.get("observation_id")
    raw_text = raw.get("raw_text")
    normalized_text = raw.get("normalized_text")
    if (
        bbox is None
        or not isinstance(observation_id, str)
        or not observation_id
        or not isinstance(raw_text, str)
        or not isinstance(normalized_text, str)
    ):
        return None
    x0, y0, x1, y1 = bbox
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0
    if (
        x0 < 0.0
        or y0 < 0.0
        or x1 > page_width
        or y1 > page_height
        or center_x < page_width * 0.65
        or center_y < page_height * 0.80
    ):
        return None
    compact_text = _compact_text(normalized_text)
    if not compact_text:
        return None
    return {
        "observation_id": observation_id,
        "raw_text": raw_text.strip(),
        "compact_text": compact_text,
        "page_index": page_index,
        "bbox_pdf": list(bbox),
        "bbox": bbox,
    }


def _unique_label(
    observations: list[dict[str, Any]],
    field: str,
) -> dict[str, Any] | None:
    labels = [
        observation
        for observation in observations
        if observation["compact_text"] in _TITLE_LABELS[field]
    ]
    return labels[0] if len(labels) == 1 else None


def _same_row_right_candidates(
    observations: list[dict[str, Any]],
    *,
    label: dict[str, Any],
    value_kind: str,
    page_width: float,
) -> list[dict[str, Any]]:
    label_x0, label_y0, label_x1, label_y1 = label["bbox"]
    label_center_y = (label_y0 + label_y1) / 2.0
    label_height = label_y1 - label_y0
    candidates: list[dict[str, Any]] = []
    for observation in observations:
        if observation["observation_id"] == label["observation_id"]:
            continue
        if observation["compact_text"] in _ALL_LABELS:
            continue
        x0, y0, _, y1 = observation["bbox"]
        gap = x0 - label_x1
        center_y = (y0 + y1) / 2.0
        row_tolerance = max(2.0, min(label_height, y1 - y0) * 0.4)
        if (
            gap < 1.0
            or gap > page_width * 0.17
            or abs(center_y - label_center_y) > row_tolerance
            or not _value_matches(value_kind, observation["compact_text"])
        ):
            continue
        candidates.append(observation)
    return candidates


def _same_column_above_candidates(
    observations: list[dict[str, Any]],
    *,
    label: dict[str, Any],
) -> list[dict[str, Any]]:
    label_x0, label_y0, label_x1, _ = label["bbox"]
    candidates: list[dict[str, Any]] = []
    for observation in observations:
        if (
            observation["observation_id"] == label["observation_id"]
            or observation["compact_text"] in _ALL_LABELS
            or _REVISION_VALUE.fullmatch(observation["compact_text"]) is None
        ):
            continue
        value_x0, _, value_x1, value_y1 = observation["bbox"]
        gap = label_y0 - value_y1
        if (
            gap < 0.0
            or gap > 45.0
            or _overlap_ratio(
                label_x0,
                label_x1,
                value_x0,
                value_x1,
            )
            < 0.65
        ):
            continue
        candidates.append(observation)
    return candidates


def _material_name_candidates(
    observations: list[dict[str, Any]],
    *,
    drawing_value: dict[str, Any],
    page_width: float,
) -> list[dict[str, Any]]:
    drawing_x0, drawing_y0, drawing_x1, _ = drawing_value["bbox"]
    drawing_center_x = (drawing_x0 + drawing_x1) / 2.0
    candidates: list[dict[str, Any]] = []
    for observation in observations:
        if (
            observation["observation_id"] == drawing_value["observation_id"]
            or observation["compact_text"] in _ALL_LABELS
            or _CJK_CHARACTER.search(observation["compact_text"]) is None
        ):
            continue
        value_x0, _, value_x1, value_y1 = observation["bbox"]
        vertical_gap = drawing_y0 - value_y1
        value_center_x = (value_x0 + value_x1) / 2.0
        if (
            vertical_gap < 10.0
            or vertical_gap > 90.0
            or abs(value_center_x - drawing_center_x) > page_width * 0.08
            or _overlap_ratio(
                drawing_x0,
                drawing_x1,
                value_x0,
                value_x1,
            )
            < 0.5
        ):
            continue
        candidates.append(observation)
    return candidates


def _suggestion(
    *,
    field: str,
    value: dict[str, Any],
    label: dict[str, Any],
    evidence_code: str,
) -> dict[str, object]:
    return {
        "field": field,
        "value": value["raw_text"],
        "observation_id": value["observation_id"],
        "label_observation_id": label["observation_id"],
        "page_index": value["page_index"],
        "bbox_pdf": value["bbox_pdf"],
        "rule_version": RULE_VERSION,
        "evidence_codes": sorted(
            {
                "bottom_right_title_anchor",
                "native_line",
                evidence_code,
                "unique_candidate",
            }
        ),
    }


def _value_matches(value_kind: str, value: str) -> bool:
    if value_kind in {"material_code", "drawing_number"}:
        return _CODE_VALUE.fullmatch(value) is not None
    if value_kind == "material":
        return (
            len(value) <= 64
            and value not in _ALL_LABELS
            and any(character.isalnum() for character in value)
        )
    return False


def _compact_text(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split())


def _overlap_ratio(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> float:
    overlap = max(
        0.0,
        min(first_end, second_end) - max(first_start, second_start),
    )
    shorter = min(first_end - first_start, second_end - second_start)
    return overlap / shorter if shorter > 0.0 else 0.0


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    coordinates = tuple(_number(coordinate) for coordinate in value)
    if any(coordinate is None for coordinate in coordinates):
        return None
    x0, y0, x1, y1 = coordinates
    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    if x0 >= x1 or y0 >= y1:
        return None
    return (x0, y0, x1, y1)


def _positive_number(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0.0 else None


def _number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None
