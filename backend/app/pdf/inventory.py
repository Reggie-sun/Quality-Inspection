from __future__ import annotations

import hashlib
import math
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf

from app.pdf.classification import PageSignals, classify_page
from app.pdf.coordinates import BBox, PageTransform
from app.pdf.schemas import PageInventory, TextObservation


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _bbox(values: Any) -> BBox:
    x0, y0, x1, y1 = values
    return float(x0), float(y0), float(x1), float(y1)


def _observation_id(
    page_index: int,
    level: str,
    block_index: int,
    line_index: int,
    span_index: int | None,
    raw_text: str,
    bbox_pdf: BBox,
) -> str:
    seed = (
        f"{page_index}:{level}:{block_index}:{line_index}:{span_index}:"
        f"{raw_text}:{bbox_pdf}"
    ).encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:24]


def _native_observation(
    *,
    page_index: int,
    level: str,
    block_index: int,
    line_index: int,
    span_index: int | None,
    raw_text: str,
    bbox: BBox,
    direction: tuple[float, float],
    transform: PageTransform,
    parent_region_id: str | None = None,
    font_name: str | None = None,
) -> TextObservation:
    bbox_pdf = transform.clip_bbox(bbox)
    return TextObservation(
        observation_id=_observation_id(
            page_index,
            level,
            block_index,
            line_index,
            span_index,
            raw_text,
            bbox_pdf,
        ),
        source_type="native",
        observation_level=level,
        raw_text=raw_text,
        normalized_text=_normalize(raw_text),
        page_index=page_index,
        bbox_pdf=bbox_pdf,
        bbox_normalized=transform.normalize_bbox(bbox_pdf),
        direction=direction,
        direction_angle_degrees=math.degrees(math.atan2(direction[1], direction[0])),
        confidence=None,
        parent_region_id=parent_region_id,
        font_name=font_name,
    )


def _image_coverage(page: pymupdf.Page, page_area: float) -> float:
    coverage = 0.0
    for image in page.get_images(full=True):
        for rect in page.get_image_rects(image):
            visible = rect & page.rect
            if not visible.is_empty:
                coverage = max(coverage, min(1.0, visible.get_area() / page_area))
    return coverage


def build_inventory(
    pdf_path: Path,
    render_scale: float = 2.0,
) -> tuple[PageInventory, ...]:
    document = pymupdf.open(pdf_path)
    try:
        pages: list[PageInventory] = []
        for page_index, page in enumerate(document):
            crop = page.cropbox
            transform = PageTransform(
                width=float(crop.width),
                height=float(crop.height),
                rotation=int(page.rotation),
                scale=render_scale,
            )
            text_dict = page.get_text("dict", sort=False)
            observations: list[TextObservation] = []
            native_char_count = 0
            native_span_count = 0

            for block_index, block in enumerate(text_dict.get("blocks", [])):
                if block.get("type") != 0:
                    continue
                for line_index, line in enumerate(block.get("lines", [])):
                    spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                    if not spans:
                        continue
                    direction = tuple(float(value) for value in line.get("dir", (1.0, 0.0)))
                    raw_line = "".join(str(span.get("text", "")) for span in spans)
                    line_observation = _native_observation(
                        page_index=page_index,
                        level="line",
                        block_index=block_index,
                        line_index=line_index,
                        span_index=None,
                        raw_text=raw_line,
                        bbox=_bbox(line["bbox"]),
                        direction=direction,
                        transform=transform,
                    )
                    observations.append(line_observation)

                    for span_index, span in enumerate(spans):
                        raw_span = str(span.get("text", ""))
                        observations.append(
                            _native_observation(
                                page_index=page_index,
                                level="span",
                                block_index=block_index,
                                line_index=line_index,
                                span_index=span_index,
                                raw_text=raw_span,
                                bbox=_bbox(span["bbox"]),
                                direction=direction,
                                transform=transform,
                                parent_region_id=line_observation.observation_id,
                                font_name=str(span.get("font", "")) or None,
                            )
                        )
                        native_char_count += len(raw_span)
                        native_span_count += 1

            page_area = transform.width * transform.height
            signals = PageSignals(
                native_char_count=native_char_count,
                native_span_count=native_span_count,
                max_image_coverage=_image_coverage(page, page_area),
                vector_drawing_count=len(page.get_drawings()),
            )
            classification = classify_page(signals)
            pages.append(
                PageInventory(
                    page_index=page_index,
                    width=transform.width,
                    height=transform.height,
                    rotation=transform.rotation,
                    page_type=classification.page_type,
                    processing_route=classification.processing_route,
                    support_level=classification.support_level,
                    review_required=classification.review_required,
                    unsupported_reason=classification.unsupported_reason,
                    classification_confidence=classification.confidence,
                    classification_rule_version=classification.rule_version,
                    classification_evidence=classification.evidence,
                    pdf_to_render_matrix=transform.pdf_to_render_matrix,
                    render_to_pdf_matrix=transform.render_to_pdf_matrix,
                    observations=tuple(observations),
                )
            )
        return tuple(pages)
    finally:
        document.close()


def append_ocr_observations(
    page: PageInventory,
    observations: tuple[TextObservation, ...],
) -> PageInventory:
    for observation in observations:
        if observation.source_type != "ocr":
            raise ValueError("only OCR observations can be appended")
        if observation.page_index != page.page_index:
            raise ValueError("OCR observation page_index must match the inventory page")
    return replace(page, observations=(*page.observations, *observations))


def build_ocr_observation(
    *,
    page_index: int,
    raw_text: str,
    bbox_pdf: BBox,
    confidence: float,
    angle_degrees: float,
    request_id: str,
    observation_index: int,
    transform: PageTransform,
) -> TextObservation:
    """Build one independent, coordinate-safe OCR observation."""
    if not raw_text.strip():
        raise ValueError("OCR observation text must be non-blank")
    if not request_id.strip():
        raise ValueError("OCR request_id must be non-blank")
    clipped_bbox = transform.clip_bbox(bbox_pdf)
    if clipped_bbox[0] >= clipped_bbox[2] or clipped_bbox[1] >= clipped_bbox[3]:
        raise ValueError("OCR observation bbox must have positive area")
    angle_radians = math.radians(angle_degrees)
    seed = (
        f"{page_index}:ocr:{request_id}:{observation_index}:"
        f"{raw_text}:{clipped_bbox}"
    ).encode("utf-8")
    return TextObservation(
        observation_id=hashlib.sha256(seed).hexdigest()[:24],
        source_type="ocr",
        observation_level="region",
        raw_text=raw_text,
        normalized_text=_normalize(raw_text),
        page_index=page_index,
        bbox_pdf=clipped_bbox,
        bbox_normalized=transform.normalize_bbox(clipped_bbox),
        direction=(math.cos(angle_radians), math.sin(angle_radians)),
        direction_angle_degrees=angle_degrees,
        confidence=confidence,
    )
