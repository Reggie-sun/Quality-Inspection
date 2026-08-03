from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass, replace
from typing import Sequence

from PIL import Image

from app.pdf.coordinates import BBox, PageTransform
from app.pdf.gdt_frames import (
    GdtFrameObservation,
    build_page_gdt_frame_observations,
)
from app.pdf.schemas import TextObservation


DESKEW_ANGLES = (-3, -2, -1, 0, 1, 2, 3)
MAX_RASTER_COLUMNS = 6
MAX_BROKEN_LINE_GAP_PX = 3


@dataclass(frozen=True)
class AxisRun:
    orientation: str
    coordinate: float
    start: float
    end: float


def _dark_threshold(image: Image.Image) -> int:
    histogram = image.histogram()
    pixel_count = sum(histogram)
    target = max(0, (pixel_count - 1) // 2)
    cumulative = 0
    median = 255
    for value, count in enumerate(histogram[:256]):
        cumulative += count
        if cumulative > target:
            median = value
            break
    return max(32, min(220, round(median * 0.72)))


def _contiguous_runs(values: Sequence[bool], gap: int) -> tuple[tuple[int, int], ...]:
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(values):
        if not values[index]:
            index += 1
            continue
        start = index
        end = index
        index += 1
        while index < len(values):
            if values[index]:
                end = index
                index += 1
                continue
            lookahead = index
            while lookahead < len(values) and not values[lookahead]:
                lookahead += 1
            if lookahead < len(values) and lookahead - index <= gap:
                end = lookahead
                index = lookahead + 1
                continue
            break
        runs.append((start, end))
        index = max(index, end + 1)
    return tuple(runs)


def _coalesce_runs(runs: Sequence[AxisRun]) -> tuple[AxisRun, ...]:
    result: list[AxisRun] = []
    for orientation in ("horizontal", "vertical"):
        current: AxisRun | None = None
        candidates = sorted(
            (run for run in runs if run.orientation == orientation),
            key=lambda run: (run.coordinate, run.start, run.end),
        )
        for run in candidates:
            overlap = min(current.end, run.end) - max(current.start, run.start) if current else 0
            if (
                current is not None
                and abs(current.coordinate - run.coordinate) <= 2.0
                and overlap >= 0
            ):
                current = AxisRun(
                    orientation=orientation,
                    coordinate=(current.coordinate + run.coordinate) / 2.0,
                    start=min(current.start, run.start),
                    end=max(current.end, run.end),
                )
            else:
                if current is not None:
                    result.append(current)
                current = run
        if current is not None:
            result.append(current)
    return tuple(result)


def detect_axis_runs(image: Image.Image) -> tuple[AxisRun, ...]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    threshold = _dark_threshold(grayscale)
    pixels = grayscale.load()
    runs: list[AxisRun] = []
    minimum_horizontal_length = max(8, round(width * 0.15))
    minimum_vertical_length = max(6, round(height * 0.20))
    for y in range(height):
        row = tuple(pixels[x, y] <= threshold for x in range(width))
        for start, end in _contiguous_runs(row, MAX_BROKEN_LINE_GAP_PX):
            if end - start + 1 >= minimum_horizontal_length:
                runs.append(AxisRun("horizontal", float(y), float(start), float(end)))
    for x in range(width):
        column = tuple(pixels[x, y] <= threshold for y in range(height))
        for start, end in _contiguous_runs(column, MAX_BROKEN_LINE_GAP_PX):
            if end - start + 1 >= minimum_vertical_length:
                runs.append(AxisRun("vertical", float(x), float(start), float(end)))
    return _coalesce_runs(runs)


def _line_score(image: Image.Image) -> float:
    runs = detect_axis_runs(image)
    score = sum(
        (run.end - run.start + 1)
        * (2.0 if run.orientation == "horizontal" else 1.0)
        for run in runs
    )
    horizontals = tuple(run for run in runs if run.orientation == "horizontal")
    verticals = tuple(run for run in runs if run.orientation == "vertical")
    if len(horizontals) >= 2 and len(verticals) >= 3:
        top = min(run.coordinate for run in horizontals)
        bottom = max(run.coordinate for run in horizontals)
        alignment_error = sum(
            abs(run.start - top) + abs(run.end - bottom)
            for run in verticals
        )
        score -= alignment_error * 20.0
        score -= max(0, len(horizontals) - 2) * 200.0
    return score


def select_deskew_angle(image: Image.Image) -> tuple[Image.Image, int]:
    source_image = image.convert("L")
    best_image = source_image
    best_angle = 0
    best_score = _line_score(best_image)
    for angle in DESKEW_ANGLES:
        if angle == 0:
            continue
        candidate = source_image.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=255,
        )
        score = _line_score(candidate)
        if score > best_score or (
            math.isclose(score, best_score)
            and abs(angle) < abs(best_angle)
        ):
            best_image = candidate
            best_angle = angle
            best_score = score
    return best_image, best_angle


def _pdf_point(
    point: tuple[float, float],
    *,
    image_size: tuple[int, int],
    crop_bbox_pdf: BBox,
) -> tuple[float, float]:
    width, height = image_size
    x0, y0, x1, y1 = crop_bbox_pdf
    return (
        x0 + point[0] / width * (x1 - x0),
        y0 + point[1] / height * (y1 - y0),
    )


def _runs_as_drawings(
    runs: Sequence[AxisRun],
    *,
    image_size: tuple[int, int],
    crop_bbox_pdf: BBox,
) -> tuple[dict[str, object], ...]:
    drawings: list[dict[str, object]] = []
    for run in runs:
        if run.orientation == "horizontal":
            start = (run.start, run.coordinate)
            end = (run.end, run.coordinate)
        else:
            start = (run.coordinate, run.start)
            end = (run.coordinate, run.end)
        drawings.append(
            {
                "items": [
                    (
                        "l",
                        _pdf_point(start, image_size=image_size, crop_bbox_pdf=crop_bbox_pdf),
                        _pdf_point(end, image_size=image_size, crop_bbox_pdf=crop_bbox_pdf),
                    )
                ]
            }
        )
    return tuple(drawings)


def build_raster_frame_observations(
    *,
    line_runs: Sequence[AxisRun],
    deskew_angle: int,
    page_index: int,
    transform: PageTransform,
    crop_bbox_pdf: BBox,
    image_size: tuple[int, int],
    text_observations: Sequence[TextObservation],
    source_sha256: str,
) -> tuple[GdtFrameObservation, ...]:
    drawings = _runs_as_drawings(
        line_runs,
        image_size=image_size,
        crop_bbox_pdf=crop_bbox_pdf,
    )
    frames = build_page_gdt_frame_observations(
        page_index=page_index,
        page_width=transform.width,
        page_height=transform.height,
        source_sha256=source_sha256,
        text_observations=text_observations,
        drawings=drawings,
        transform=transform,
        layout_profile_match=None,
    )
    return tuple(
        replace(
            frame,
            proposal_source="raster",
            observation_id=(
                hashlib.sha256(
                    f"{frame.observation_id}:{deskew_angle}".encode("utf-8")
                ).hexdigest()[:24]
            ),
        )
        for frame in frames
        if 2 <= len(frame.cells) <= MAX_RASTER_COLUMNS
    )


def detect_raster_gdt_frames(
    *,
    png: bytes,
    page_index: int,
    transform: PageTransform,
    crop_bbox_pdf: BBox,
    text_observations: Sequence[TextObservation],
    source_sha256: str,
) -> tuple[GdtFrameObservation, ...]:
    with Image.open(io.BytesIO(png)) as image:
        image.load()
        deskewed, angle = select_deskew_angle(image)
        line_runs = detect_axis_runs(deskewed)
        return build_raster_frame_observations(
            line_runs=line_runs,
            deskew_angle=angle,
            page_index=page_index,
            transform=transform,
            crop_bbox_pdf=crop_bbox_pdf,
            image_size=deskewed.size,
            text_observations=text_observations,
            source_sha256=source_sha256,
        )


__all__ = [
    "AxisRun",
    "DESKEW_ANGLES",
    "MAX_BROKEN_LINE_GAP_PX",
    "MAX_RASTER_COLUMNS",
    "build_raster_frame_observations",
    "detect_axis_runs",
    "detect_raster_gdt_frames",
    "select_deskew_angle",
]
