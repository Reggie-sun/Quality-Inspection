from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Literal, Sequence

import pymupdf

from app.pdf.coordinates import BBox, PageTransform
from app.pdf.schemas import PageInventory, TextObservation, VisualObservation


PROPOSAL_RULE_VERSION = "visual-observation/3"
PROPOSAL_RULE_CANONICAL_JSON = (
    b'{"base_branch_order":["geometry_compact","geometry_wide_multi_item",'
    b'"geometry_filled","short_token_rescue"],"compact_item_filter":'
    b'{"max_item_height_max":"42.000","max_item_width_max":"60.000"},'
    b'"context_transform_order":["dense_short_token_compact_rescue",'
    b'"wide_compact_replacement","base_admission"],'
    b'"dense_short_token_compact_rescue":'
    b'{"base_context_area_relation":"greater_than_page_area_cap",'
    b'"compact_context_area_max":"6000.000",'
    b'"compact_context_area_relation":"less_than_or_equal_to_page_area_cap",'
    b'"compact_item_count_min_exclusive":40,'
    b'"compact_reason_required":"short_token_rescue"},'
    b'"feature_quantum":"0.001","geometry_common":'
    b'{"max_item_height_min_exclusive":"2.000",'
    b'"mean_item_height_max":"34.000"},'
    b'"geometry_compact":{"context_area_max":"6000.000","fill_count_max":1,'
    b'"max_item_width_max":"60.000"},"geometry_filled":'
    b'{"context_area_min_exclusive":"5800.000",'
    b'"fill_count_min_exclusive":1,"max_item_height_max":"42.000"},'
    b'"geometry_wide_multi_item":{"fill_count_max":1,'
    b'"item_count_min_exclusive":3,'
    b'"max_item_width_min_exclusive":"60.000"},'
    b'"proposal_rule_version":"visual-observation/3","provisional_context":'
    b'{"axis_gap_max":"12.000","item_extent_max":"96.000",'
    b'"page_area_ratio_max":"0.010"},"schema_version":"visual-proposal-gate/2",'
    b'"short_token_rescue":{"context_area_max":"6000.000",'
    b'"pattern":"[A-Z0-9]{1,3}"},"wide_compact_replacement":'
    b'{"base_context_area_relation":"less_than_or_equal_to_page_area_cap",'
    b'"base_reason_required":"geometry_wide_multi_item",'
    b'"compact_context_area_relation":"less_than_or_equal_to_page_area_cap",'
    b'"compact_reason_required":"geometry_compact"}}'
)
PROPOSAL_RULE_SHA256 = hashlib.sha256(
    PROPOSAL_RULE_CANONICAL_JSON
).hexdigest()
if PROPOSAL_RULE_SHA256 != (
    "8b7b67f4e303c7cfb7648c9dc2b11530198216f4799ee485f49199f0e99a8cfa"
):
    raise RuntimeError("visual proposal rule digest mismatch")

MAX_PATH_ITEM_EXTENT_PT = 96.0
MAX_AXIS_GAP_PT = 12.0
MAX_CONTEXT_PAGE_AREA_RATIO = 0.01
HASH_QUANTUM = Decimal("0.001")

_PROPOSAL_KIND = "text_adjacent_vector_context"
_ASCII_WHITESPACE = re.compile(r"[ \t\n\r\f\v]+")
_MAX_BATCH_AREA_RATIO = 0.075
_RENDER_DPI = 300.0
_MAX_RENDER_SIDE = 1536
_MAX_BATCH_OBSERVATIONS = 32


class VisualObservationBlockingError(RuntimeError):
    """A deterministic visual proposal failure that must block the page."""

    def __init__(self, code: str, *, page_index: int) -> None:
        self.code = code
        self.page_index = page_index
        super().__init__(f"{code}: page {page_index}")


@dataclass(frozen=True)
class VisualGeometryContext:
    observation_id: str
    page_index: int
    geometry_sha256: str
    line_bbox_pdf: BBox
    path_bboxes: tuple[BBox, ...]
    canonical_path_items: tuple[bytes, ...]


@dataclass(frozen=True)
class VisualBatch:
    page_index: int
    call_index: int
    observation_ids: tuple[str, ...]
    crop_bbox_pdf: BBox
    pixel_width: int
    pixel_height: int


@dataclass(frozen=True)
class _ProposalFeatures:
    context_area: Decimal
    max_item_width: Decimal
    max_item_height: Decimal
    mean_item_height: Decimal
    fill_count: int
    item_count: int
    short_token_fullmatch: bool


@dataclass(frozen=True)
class _ProposalDecision:
    retained: bool
    reason_code: Literal[
        "geometry_compact",
        "geometry_wide_multi_item",
        "geometry_filled",
        "short_token_rescue",
        "no_admission_branch",
    ]


@dataclass(frozen=True)
class _CanonicalPathItem:
    bbox: BBox
    content: bytes
    has_fill: bool


@dataclass(frozen=True)
class _Proposal:
    observation: VisualObservation
    context: VisualGeometryContext


def _blocking(code: str, page_index: int) -> VisualObservationBlockingError:
    return VisualObservationBlockingError(code, page_index=page_index)


def _number_string(value: Any, *, page_index: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise _blocking("visual_geometry_invalid_number", page_index)
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        quantized = number.quantize(HASH_QUANTUM, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError):
        raise _blocking("visual_geometry_nonfinite", page_index) from None
    if quantized == 0:
        quantized = abs(quantized)
    return format(quantized, "f")


def _integer_style(value: Any, *, page_index: int) -> int | list[int] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise _blocking("visual_geometry_invalid_style", page_index)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        # PyMuPDF 1.28 emits lineJoin=0.0 with integer semantics.
        if float(value).is_integer():
            return int(value)
        raise _blocking("visual_geometry_invalid_style", page_index)
    if isinstance(value, (tuple, list)):
        return [
            _integer_style_component(component, page_index=page_index)
            for component in value
        ]
    raise _blocking("visual_geometry_invalid_style", page_index)


def _integer_style_component(value: Any, *, page_index: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not float(value).is_integer()
    ):
        raise _blocking("visual_geometry_invalid_style", page_index)
    return int(value)


def _color_style(
    value: Any,
    *,
    page_index: int,
) -> list[str] | None:
    if value is None:
        return None
    if (
        not isinstance(value, (tuple, list))
        or isinstance(value, (str, bytes))
        or not 1 <= len(value) <= 4
    ):
        raise _blocking("visual_geometry_invalid_style", page_index)
    return [
        _number_string(component, page_index=page_index)
        for component in value
    ]


def _style(
    drawing: dict[str, Any],
    *,
    page_index: int,
) -> dict[str, Any]:
    dashes = drawing.get("dashes")
    if dashes is not None:
        if not isinstance(dashes, str):
            raise _blocking("visual_geometry_invalid_style", page_index)
        dashes = _ASCII_WHITESPACE.sub(" ", dashes).strip()
    close_path = drawing.get("closePath")
    if close_path is not None and not isinstance(close_path, bool):
        raise _blocking("visual_geometry_invalid_style", page_index)
    width = drawing.get("width")
    return {
        "closePath": close_path,
        "color": _color_style(drawing.get("color"), page_index=page_index),
        "dashes": dashes,
        "fill": _color_style(drawing.get("fill"), page_index=page_index),
        "lineCap": _integer_style(
            drawing.get("lineCap"),
            page_index=page_index,
        ),
        "lineJoin": _integer_style(
            drawing.get("lineJoin"),
            page_index=page_index,
        ),
        "width": (
            None
            if width is None
            else _number_string(width, page_index=page_index)
        ),
    }


def _point_coordinates(
    point: Any,
    *,
    page_index: int,
) -> tuple[list[str], BBox]:
    try:
        x = float(point.x)
        y = float(point.y)
    except (AttributeError, TypeError, ValueError):
        raise _blocking("visual_geometry_invalid_coordinate", page_index) from None
    coordinates = [
        _number_string(x, page_index=page_index),
        _number_string(y, page_index=page_index),
    ]
    return coordinates, (x, y, x, y)


def _rect_coordinates(
    rect: Any,
    *,
    page_index: int,
) -> tuple[list[str], BBox]:
    try:
        values = tuple(float(value) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
    except (AttributeError, TypeError, ValueError):
        raise _blocking("visual_geometry_invalid_coordinate", page_index) from None
    if values[0] > values[2] or values[1] > values[3]:
        raise _blocking("visual_geometry_invalid_coordinate", page_index)
    coordinates = [
        _number_string(value, page_index=page_index)
        for value in values
    ]
    return coordinates, values


def _union_bboxes(bboxes: Sequence[BBox]) -> BBox:
    return (
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    )


def _canonical_path_item(
    *,
    bbox: BBox,
    payload: dict[str, Any],
    style: dict[str, Any],
) -> _CanonicalPathItem:
    return _CanonicalPathItem(
        bbox=bbox,
        content=json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        has_fill=style["fill"] is not None,
    )


def _point_item(
    opcode: str,
    values: Sequence[Any],
    style: dict[str, Any],
    *,
    page_index: int,
) -> _CanonicalPathItem:
    coordinates: list[list[str]] = []
    point_bboxes: list[BBox] = []
    for value in values:
        coordinate, bbox = _point_coordinates(value, page_index=page_index)
        coordinates.append(coordinate)
        point_bboxes.append(bbox)
    payload = {
        "coordinates": coordinates,
        "opcode": opcode,
        "style": style,
    }
    return _canonical_path_item(
        bbox=_union_bboxes(point_bboxes),
        payload=payload,
        style=style,
    )


def _canonical_item(
    raw_item: Any,
    style: dict[str, Any],
    *,
    page_index: int,
) -> _CanonicalPathItem:
    if not isinstance(raw_item, (tuple, list)) or not raw_item:
        raise _blocking("visual_geometry_unknown_opcode", page_index)
    opcode = raw_item[0]
    if opcode == "l" and len(raw_item) == 3:
        return _point_item(
            opcode,
            raw_item[1:],
            style,
            page_index=page_index,
        )
    if opcode == "c" and len(raw_item) == 5:
        return _point_item(
            opcode,
            raw_item[1:],
            style,
            page_index=page_index,
        )
    if opcode == "re" and len(raw_item) == 3:
        coordinates, bbox = _rect_coordinates(
            raw_item[1],
            page_index=page_index,
        )
        orientation = _integer_style_component(
            raw_item[2],
            page_index=page_index,
        )
        payload = {
            "coordinates": coordinates,
            "opcode": opcode,
            "orientation": orientation,
            "style": style,
        }
        return _canonical_path_item(
            bbox=bbox,
            payload=payload,
            style=style,
        )
    if opcode == "qu" and len(raw_item) == 2:
        quad = raw_item[1]
        try:
            points = (quad.ul, quad.ur, quad.ll, quad.lr)
        except AttributeError:
            raise _blocking("visual_geometry_invalid_coordinate", page_index) from None
        return _point_item(
            opcode,
            points,
            style,
            page_index=page_index,
        )
    raise _blocking("visual_geometry_unknown_opcode", page_index)


def _canonical_path_items(
    drawings: Sequence[dict[str, Any]],
    *,
    page_index: int,
) -> tuple[_CanonicalPathItem, ...]:
    items: list[_CanonicalPathItem] = []
    for drawing in drawings:
        style = _style(drawing, page_index=page_index)
        raw_items = drawing.get("items")
        if not isinstance(raw_items, (tuple, list)):
            raise _blocking("visual_geometry_unknown_opcode", page_index)
        for raw_item in raw_items:
            items.append(
                _canonical_item(
                    raw_item,
                    style,
                    page_index=page_index,
                )
            )
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.bbox[1],
                item.bbox[0],
                item.bbox[3],
                item.bbox[2],
                item.content,
            ),
        )
    )


def _axis_gaps(left: BBox, right: BBox) -> tuple[float, float]:
    return (
        max(0.0, left[0] - right[2], right[0] - left[2]),
        max(0.0, left[1] - right[3], right[1] - left[3]),
    )


def _area(bbox: BBox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


_SHORT_TOKEN = re.compile(r"[A-Z0-9]{1,3}")


def _measure(value: int | float | Decimal, *, page_index: int) -> Decimal:
    return Decimal(_number_string(value, page_index=page_index))


def _short_token_fullmatch(raw_text: str) -> bool:
    normalized = _ASCII_WHITESPACE.sub(" ", raw_text).strip().upper()
    return _SHORT_TOKEN.fullmatch(normalized) is not None


def _proposal_features(
    *,
    raw_text: str,
    selected: Sequence[_CanonicalPathItem],
    source_union: BBox,
    page_index: int,
) -> _ProposalFeatures:
    widths = tuple(
        _measure(item.bbox[2] - item.bbox[0], page_index=page_index)
        for item in selected
    )
    heights = tuple(
        _measure(item.bbox[3] - item.bbox[1], page_index=page_index)
        for item in selected
    )
    mean_height = _measure(
        sum(heights, start=Decimal("0")) / Decimal(len(heights)),
        page_index=page_index,
    )
    return _ProposalFeatures(
        context_area=_measure(_area(source_union), page_index=page_index),
        max_item_width=max(widths),
        max_item_height=max(heights),
        mean_item_height=mean_height,
        fill_count=sum(item.has_fill for item in selected),
        item_count=len(selected),
        short_token_fullmatch=_short_token_fullmatch(raw_text),
    )


def _proposal_decision(
    features: _ProposalFeatures,
) -> _ProposalDecision:
    common = (
        features.mean_item_height <= Decimal("34.000")
        and features.max_item_height > Decimal("2.000")
    )
    if (
        common
        and features.fill_count <= 1
        and features.max_item_width <= Decimal("60.000")
        and features.context_area <= Decimal("6000.000")
    ):
        return _ProposalDecision(True, "geometry_compact")
    if (
        common
        and features.fill_count <= 1
        and features.max_item_width > Decimal("60.000")
        and features.item_count > 3
    ):
        return _ProposalDecision(True, "geometry_wide_multi_item")
    if (
        common
        and features.fill_count > 1
        and features.context_area > Decimal("5800.000")
        and features.max_item_height <= Decimal("42.000")
    ):
        return _ProposalDecision(True, "geometry_filled")
    if (
        features.short_token_fullmatch
        and features.context_area <= Decimal("6000.000")
    ):
        return _ProposalDecision(True, "short_token_rescue")
    return _ProposalDecision(False, "no_admission_branch")


def _quantized_bbox(bbox: BBox, *, page_index: int) -> list[str]:
    return [
        _number_string(value, page_index=page_index)
        for value in bbox
    ]


def _observation_id(
    *,
    source_sha256: str,
    page_index: int,
    bbox_pdf: BBox,
    geometry_sha256: str,
    associated_text_ids: tuple[str, ...],
) -> str:
    seed = json.dumps(
        [
            PROPOSAL_RULE_VERSION,
            source_sha256,
            page_index,
            _PROPOSAL_KIND,
            _quantized_bbox(bbox_pdf, page_index=page_index),
            geometry_sha256,
            list(associated_text_ids),
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:24]


def _iou(left: BBox, right: BBox) -> float:
    intersection = (
        max(left[0], right[0]),
        max(left[1], right[1]),
        min(left[2], right[2]),
        min(left[3], right[3]),
    )
    intersection_area = _area(intersection)
    if intersection_area == 0:
        return 0.0
    return intersection_area / (_area(left) + _area(right) - intersection_area)


def build_page_visual_observations(
    *,
    page_index: int,
    page_width: float,
    page_height: float,
    source_sha256: str,
    native_observations: Sequence[TextObservation],
    drawings: Sequence[dict[str, Any]],
    transform: PageTransform,
) -> tuple[tuple[VisualObservation, ...], tuple[VisualGeometryContext, ...]]:
    """Build one page's deterministic observations and internal geometry facts."""
    path_items = _canonical_path_items(drawings, page_index=page_index)
    native_spans = [
        observation
        for observation in native_observations
        if observation.source_type == "native"
        and observation.observation_level == "span"
    ]
    proposals: list[_Proposal] = []

    for line in native_observations:
        if (
            line.source_type != "native"
            or line.observation_level != "line"
            or not line.raw_text.strip()
        ):
            continue
        selected = []
        for item in path_items:
            width = item.bbox[2] - item.bbox[0]
            height = item.bbox[3] - item.bbox[1]
            if (
                width > MAX_PATH_ITEM_EXTENT_PT
                or height > MAX_PATH_ITEM_EXTENT_PT
            ):
                continue
            gap_x, gap_y = _axis_gaps(line.bbox_pdf, item.bbox)
            if gap_x <= MAX_AXIS_GAP_PT and gap_y <= MAX_AXIS_GAP_PT:
                selected.append(item)
        if not selected:
            continue
        source_union = _union_bboxes(
            (line.bbox_pdf, *(item.bbox for item in selected))
        )
        page_area_cap = (
            page_width * page_height * MAX_CONTEXT_PAGE_AREA_RATIO
        )
        base_decision = _proposal_decision(
            _proposal_features(
                raw_text=line.raw_text,
                selected=selected,
                source_union=source_union,
                page_index=page_index,
            )
        )
        compact_items = [
            item
            for item in selected
            if _measure(
                item.bbox[2] - item.bbox[0],
                page_index=page_index,
            )
            <= Decimal("60.000")
            and _measure(
                item.bbox[3] - item.bbox[1],
                page_index=page_index,
            )
            <= Decimal("42.000")
        ]
        if _area(source_union) > page_area_cap:
            if not compact_items:
                continue
            compact_union = _union_bboxes(
                (
                    line.bbox_pdf,
                    *(item.bbox for item in compact_items),
                )
            )
            compact_features = _proposal_features(
                raw_text=line.raw_text,
                selected=compact_items,
                source_union=compact_union,
                page_index=page_index,
            )
            compact_decision = _proposal_decision(compact_features)
            if (
                _area(compact_union) > page_area_cap
                or compact_features.context_area > Decimal("6000.000")
                or len(compact_items) <= 40
                or not compact_decision.retained
                or compact_decision.reason_code != "short_token_rescue"
            ):
                continue
            selected = compact_items
            source_union = compact_union
        else:
            if not base_decision.retained:
                continue
            if (
                base_decision.reason_code == "geometry_wide_multi_item"
                and compact_items
            ):
                compact_union = _union_bboxes(
                    (
                        line.bbox_pdf,
                        *(item.bbox for item in compact_items),
                    )
                )
                if _area(compact_union) <= page_area_cap:
                    compact_decision = _proposal_decision(
                        _proposal_features(
                            raw_text=line.raw_text,
                            selected=compact_items,
                            source_union=compact_union,
                            page_index=page_index,
                        )
                    )
                    if (
                        compact_decision.retained
                        and compact_decision.reason_code == "geometry_compact"
                    ):
                        selected = compact_items
                        source_union = compact_union
        bbox_pdf = transform.clip_bbox(source_union)
        selected = sorted(
            selected,
            key=lambda item: (
                item.bbox[1],
                item.bbox[0],
                item.bbox[3],
                item.bbox[2],
                item.content,
            ),
        )
        canonical_items = tuple(item.content for item in selected)
        geometry_sha256 = hashlib.sha256(b"".join(canonical_items)).hexdigest()
        associated_text_ids = tuple(
            sorted(
                (
                    line.observation_id,
                    *(
                        span.observation_id
                        for span in native_spans
                        if span.parent_region_id == line.observation_id
                    ),
                )
            )
        )
        observation_id = _observation_id(
            source_sha256=source_sha256,
            page_index=page_index,
            bbox_pdf=bbox_pdf,
            geometry_sha256=geometry_sha256,
            associated_text_ids=associated_text_ids,
        )
        observation = VisualObservation(
            observation_id=observation_id,
            source_type="visual",
            observation_level="annotation_context",
            page_index=page_index,
            bbox_pdf=bbox_pdf,
            bbox_normalized=transform.normalize_bbox(bbox_pdf),
            proposal_kind=_PROPOSAL_KIND,
            geometry_sha256=geometry_sha256,
            associated_text_observation_ids=associated_text_ids,
        )
        proposals.append(
            _Proposal(
                observation=observation,
                context=VisualGeometryContext(
                    observation_id=observation_id,
                    page_index=page_index,
                    geometry_sha256=geometry_sha256,
                    line_bbox_pdf=line.bbox_pdf,
                    path_bboxes=tuple(item.bbox for item in selected),
                    canonical_path_items=canonical_items,
                ),
            )
        )

    proposals.sort(
        key=lambda proposal: (
            proposal.observation.page_index,
            proposal.observation.bbox_pdf[1],
            proposal.observation.bbox_pdf[0],
            proposal.observation.proposal_kind,
            proposal.observation.observation_id,
        )
    )
    retained: list[_Proposal] = []
    seen_geometry: set[tuple[str, tuple[str, ...]]] = set()
    for proposal in proposals:
        identity = (
            proposal.observation.geometry_sha256,
            proposal.observation.associated_text_observation_ids,
        )
        if identity in seen_geometry:
            continue
        if any(
            existing.observation.associated_text_observation_ids
            == proposal.observation.associated_text_observation_ids
            and _iou(
                existing.observation.bbox_pdf,
                proposal.observation.bbox_pdf,
            )
            >= 0.8
            for existing in retained
        ):
            continue
        seen_geometry.add(identity)
        retained.append(proposal)
    return (
        tuple(proposal.observation for proposal in retained),
        tuple(proposal.context for proposal in retained),
    )


def reconstruct_visual_geometry_contexts(
    pdf_path: Path,
    pages: Sequence[PageInventory],
) -> tuple[VisualGeometryContext, ...]:
    """Rebuild private geometry facts and exact-match persisted observations."""
    source_path = Path(pdf_path)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    document = pymupdf.open(source_path)
    try:
        if len(document) != len(pages):
            raise _blocking("visual_reconstruction_mismatch", -1)
        contexts: list[VisualGeometryContext] = []
        for expected_index, inventory_page in enumerate(pages):
            if inventory_page.page_index != expected_index:
                raise _blocking(
                    "visual_reconstruction_mismatch",
                    expected_index,
                )
            source_page = document[expected_index]
            crop = source_page.cropbox
            transform = PageTransform(
                width=float(crop.width),
                height=float(crop.height),
                rotation=int(source_page.rotation),
                scale=1.0,
            )
            observations, rebuilt_contexts = build_page_visual_observations(
                page_index=expected_index,
                page_width=transform.width,
                page_height=transform.height,
                source_sha256=source_sha256,
                native_observations=inventory_page.observations,
                drawings=source_page.get_drawings(),
                transform=transform,
            )
            persisted = inventory_page.visual_observations
            if observations != persisted:
                raise _blocking(
                    "visual_reconstruction_mismatch",
                    expected_index,
                )
            contexts.extend(rebuilt_contexts)
        return tuple(contexts)
    finally:
        document.close()


def _batch_geometry(
    *,
    page_width: float,
    page_height: float,
    observations: Sequence[VisualObservation],
) -> tuple[BBox, int, int] | None:
    union = _union_bboxes(tuple(item.bbox_pdf for item in observations))
    padding = min(
        24,
        max(
            6,
            math.ceil(
                0.10
                * max(
                    union[2] - union[0],
                    union[3] - union[1],
                )
            ),
        ),
    )
    crop = (
        max(0.0, union[0] - padding),
        max(0.0, union[1] - padding),
        min(page_width, union[2] + padding),
        min(page_height, union[3] + padding),
    )
    pixel_width = math.ceil((crop[2] - crop[0]) * _RENDER_DPI / 72.0)
    pixel_height = math.ceil((crop[3] - crop[1]) * _RENDER_DPI / 72.0)
    if (
        _area(crop) > page_width * page_height * _MAX_BATCH_AREA_RATIO
        or pixel_width > _MAX_RENDER_SIDE
        or pixel_height > _MAX_RENDER_SIDE
        or len(observations) > _MAX_BATCH_OBSERVATIONS
    ):
        return None
    return crop, pixel_width, pixel_height


def pack_visual_batches(
    page: PageInventory,
    ordered_observations: Sequence[VisualObservation],
) -> tuple[VisualBatch, ...]:
    """Pack priority-neutral observations with stable first-fit."""
    members: list[list[VisualObservation]] = []
    geometry: list[tuple[BBox, int, int]] = []
    for observation in ordered_observations:
        if observation.page_index != page.page_index:
            raise _blocking("visual_observation_page_mismatch", page.page_index)
        placed = False
        for index, batch_members in enumerate(members):
            candidate = (*batch_members, observation)
            candidate_geometry = _batch_geometry(
                page_width=page.width,
                page_height=page.height,
                observations=candidate,
            )
            if candidate_geometry is None:
                continue
            batch_members.append(observation)
            geometry[index] = candidate_geometry
            placed = True
            break
        if placed:
            continue
        single_geometry = _batch_geometry(
            page_width=page.width,
            page_height=page.height,
            observations=(observation,),
        )
        if single_geometry is None:
            raise _blocking("visual_crop_oversize", page.page_index)
        members.append([observation])
        geometry.append(single_geometry)

    return tuple(
        VisualBatch(
            page_index=page.page_index,
            call_index=index,
            observation_ids=tuple(
                observation.observation_id
                for observation in batch_members
            ),
            crop_bbox_pdf=batch_geometry[0],
            pixel_width=batch_geometry[1],
            pixel_height=batch_geometry[2],
        )
        for index, (batch_members, batch_geometry) in enumerate(
            zip(members, geometry, strict=True)
        )
    )
