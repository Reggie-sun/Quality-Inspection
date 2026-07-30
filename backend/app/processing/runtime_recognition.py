from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
import uuid

import pymupdf

from app.candidates.advisor import CandidateAdvisor
from app.config import Settings
from app.pdf.coordinates import BBox, PageTransform, Point
from app.pdf.inventory import (
    append_ocr_observations,
    build_inventory as build_native_inventory,
    build_ocr_observation,
)
from app.pdf.schemas import PageInventory, TextObservation
from app.processing.automatic_result import (
    CandidateSnapshot,
    candidate_snapshot_from_inventory,
)
from app.providers.base import OcrProvider
from app.providers.runtime import OcrProviderFactory, build_ocr_provider


_MAX_OCR_CALLS_PER_PAGE = 16
_WHOLE_PAGE_IMAGE_RATIO = 0.8
_NATIVE_COVERAGE_RATIO = 0.8


class RuntimeRecognition:
    """Add bounded local OCR observations without replacing native PDF facts."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider_factory: OcrProviderFactory = build_ocr_provider,
        advisor: CandidateAdvisor | None = None,
        render_scale: float = 2.0,
    ) -> None:
        self._settings = settings
        self._provider_factory = provider_factory
        self._render_scale = render_scale
        self._provider_call_ids: tuple[str, ...] = ()
        self._advisor = advisor
        self._source_path: Path | None = None

    def build_inventory(self, pdf_path: Path) -> tuple[PageInventory, ...]:
        self._source_path = pdf_path
        native_pages = build_native_inventory(
            pdf_path,
            render_scale=self._render_scale,
        )
        enhanced_pages = list(native_pages)
        provider: OcrProvider | None = None
        provider_call_ids: list[str] = []

        with pymupdf.open(pdf_path) as document:
            for page_index, inventory in enumerate(native_pages):
                if (
                    inventory.processing_route != "hybrid"
                    or inventory.support_level == "unsupported"
                ):
                    continue
                page = document[page_index]
                transform = PageTransform(
                    width=inventory.width,
                    height=inventory.height,
                    rotation=inventory.rotation,
                    scale=self._render_scale,
                )
                appended: list[TextObservation] = []
                for region in self._eligible_regions(page, inventory):
                    if provider is None:
                        provider = self._provider_factory(self._settings)
                    png, render_origin = self._render_region(
                        page,
                        region,
                        transform,
                    )
                    result = provider.recognize_png(png)
                    provider_call_ids.append(result.request_id)
                    for observation_index, observation in enumerate(
                        result.observations
                    ):
                        bbox_pdf = self._polygon_bbox_pdf(
                            observation.polygon,
                            render_origin=render_origin,
                            transform=transform,
                        )
                        if bbox_pdf is None:
                            continue
                        appended.append(
                            build_ocr_observation(
                                page_index=page_index,
                                raw_text=observation.raw_text,
                                bbox_pdf=bbox_pdf,
                                confidence=observation.confidence,
                                angle_degrees=self._pdf_angle(
                                    observation.angle,
                                    render_origin=render_origin,
                                    transform=transform,
                                ),
                                request_id=result.request_id,
                                observation_index=observation_index,
                                transform=transform,
                            )
                        )
                if appended:
                    enhanced_pages[page_index] = append_ocr_observations(
                        inventory,
                        tuple(appended),
                    )

        self._provider_call_ids = tuple(provider_call_ids)
        return tuple(enhanced_pages)

    def build_candidate_snapshot(
        self,
        pages: tuple[PageInventory, ...],
        *,
        source_file_id: uuid.UUID | None = None,
    ) -> CandidateSnapshot:
        snapshot = replace(
            candidate_snapshot_from_inventory(pages),
            provider_call_ids=self._provider_call_ids,
        )
        if self._advisor is None:
            return snapshot
        if self._source_path is None:
            raise RuntimeError("candidate snapshot requires one source PDF")
        return self._advisor.review(
            self._source_path,
            pages,
            snapshot,
            source_file_id=source_file_id,
        )

    @staticmethod
    def _eligible_regions(
        page: pymupdf.Page,
        inventory: PageInventory,
    ) -> tuple[pymupdf.Rect, ...]:
        visible_page = pymupdf.Rect(
            0.0,
            0.0,
            inventory.width,
            inventory.height,
        )
        page_area = inventory.width * inventory.height
        native = tuple(
            observation
            for observation in inventory.observations
            if observation.source_type == "native"
        )
        regions: list[pymupdf.Rect] = []
        seen: set[tuple[float, float, float, float]] = set()
        for image in page.get_images(full=True):
            for raw_region in page.get_image_rects(image):
                region = raw_region & visible_page
                if region.is_empty or region.get_area() <= 0:
                    continue
                for crop in RuntimeRecognition._bounded_crops(region, page_area):
                    key = tuple(round(float(value), 6) for value in crop)
                    if key in seen:
                        continue
                    seen.add(key)
                    if RuntimeRecognition._covered_by_native(crop, native):
                        continue
                    regions.append(crop)
        regions.sort(key=lambda value: (value.y0, value.x0, value.y1, value.x1))
        return tuple(regions[:_MAX_OCR_CALLS_PER_PAGE])

    @staticmethod
    def _bounded_crops(
        region: pymupdf.Rect,
        page_area: float,
    ) -> tuple[pymupdf.Rect, ...]:
        if region.get_area() / page_area < _WHOLE_PAGE_IMAGE_RATIO:
            return (region,)
        midpoint_x = (region.x0 + region.x1) / 2.0
        midpoint_y = (region.y0 + region.y1) / 2.0
        return (
            pymupdf.Rect(region.x0, region.y0, midpoint_x, midpoint_y),
            pymupdf.Rect(midpoint_x, region.y0, region.x1, midpoint_y),
            pymupdf.Rect(region.x0, midpoint_y, midpoint_x, region.y1),
            pymupdf.Rect(midpoint_x, midpoint_y, region.x1, region.y1),
        )

    @staticmethod
    def _native_coverage_ratio(
        region: pymupdf.Rect,
        observations: tuple[TextObservation, ...],
    ) -> float:
        intersections: list[pymupdf.Rect] = []
        for observation in observations:
            bbox = pymupdf.Rect(observation.bbox_pdf)
            if bbox.is_empty:
                continue
            overlap = bbox & region
            if not overlap.is_empty and overlap.get_area() > 0:
                intersections.append(overlap)
        if not intersections:
            return 0.0

        x_coordinates = sorted(
            {
                coordinate
                for intersection in intersections
                for coordinate in (intersection.x0, intersection.x1)
            }
        )
        covered_area = 0.0
        for x0, x1 in zip(x_coordinates, x_coordinates[1:], strict=False):
            if x1 <= x0:
                continue
            intervals = sorted(
                (intersection.y0, intersection.y1)
                for intersection in intersections
                if intersection.x0 < x1 and intersection.x1 > x0
            )
            if not intervals:
                continue
            covered_height = 0.0
            start, end = intervals[0]
            for interval_start, interval_end in intervals[1:]:
                if interval_start > end:
                    covered_height += end - start
                    start, end = interval_start, interval_end
                else:
                    end = max(end, interval_end)
            covered_height += end - start
            covered_area += (x1 - x0) * covered_height
        return min(1.0, covered_area / region.get_area())

    @staticmethod
    def _covered_by_native(
        region: pymupdf.Rect,
        observations: tuple[TextObservation, ...],
    ) -> bool:
        return (
            RuntimeRecognition._native_coverage_ratio(region, observations)
            >= _NATIVE_COVERAGE_RATIO
        )

    @staticmethod
    def _render_region(
        page: pymupdf.Page,
        region: pymupdf.Rect,
        transform: PageTransform,
    ) -> tuple[bytes, Point]:
        rendered_clip = region * page.rotation_matrix
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(transform.scale, transform.scale),
            clip=rendered_clip,
            alpha=False,
        )
        if pixmap.width <= 0 or pixmap.height <= 0:
            raise ValueError("OCR crop rendered with empty dimensions")
        return pixmap.tobytes("png"), (float(pixmap.x), float(pixmap.y))

    @staticmethod
    def _polygon_bbox_pdf(
        polygon: tuple[Point, ...],
        *,
        render_origin: Point,
        transform: PageTransform,
    ) -> BBox | None:
        if not polygon:
            return None
        points = [
            transform.render_to_pdf_point(
                (
                    render_origin[0] + float(point[0]),
                    render_origin[1] + float(point[1]),
                )
            )
            for point in polygon
        ]
        bbox = transform.clip_bbox(
            (
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            )
        )
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            return None
        return bbox

    @staticmethod
    def _pdf_angle(
        angle_degrees: float,
        *,
        render_origin: Point,
        transform: PageTransform,
    ) -> float:
        angle = math.radians(angle_degrees)
        origin = transform.render_to_pdf_point(render_origin)
        endpoint = transform.render_to_pdf_point(
            (
                render_origin[0] + math.cos(angle),
                render_origin[1] + math.sin(angle),
            )
        )
        return math.degrees(
            math.atan2(
                endpoint[1] - origin[1],
                endpoint[0] - origin[0],
            )
        )
