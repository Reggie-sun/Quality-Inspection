from __future__ import annotations

from dataclasses import dataclass


Point = tuple[float, float]
BBox = tuple[float, float, float, float]
Matrix = tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class PageTransform:
    width: float
    height: float
    rotation: int
    scale: float
    crop_x: float = 0.0
    crop_y: float = 0.0

    def __post_init__(self) -> None:
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("rotation must be 0, 90, 180 or 270")
        if self.width <= 0 or self.height <= 0 or self.scale <= 0:
            raise ValueError("page dimensions and scale must be positive")

    @staticmethod
    def apply_matrix(matrix: Matrix, point: Point) -> Point:
        a, b, c, d, e, f = matrix
        x, y = point
        return a * x + c * y + e, b * x + d * y + f

    def pdf_to_render_point(self, point: Point) -> Point:
        return self.apply_matrix(self.pdf_to_render_matrix, point)

    def render_to_pdf_point(self, point: Point) -> Point:
        return self.apply_matrix(self.render_to_pdf_matrix, point)

    def clip_bbox(self, bbox: BBox) -> BBox:
        x0, y0, x1, y1 = bbox
        if x0 > x1 or y0 > y1:
            raise ValueError("bbox has inverted bounds")
        local = (
            x0 - self.crop_x,
            y0 - self.crop_y,
            x1 - self.crop_x,
            y1 - self.crop_y,
        )
        return (
            max(0.0, min(local[0], self.width)),
            max(0.0, min(local[1], self.height)),
            max(0.0, min(local[2], self.width)),
            max(0.0, min(local[3], self.height)),
        )

    def normalize_bbox(self, bbox: BBox) -> BBox:
        x0, y0, x1, y1 = bbox
        if x0 > x1 or y0 > y1:
            raise ValueError("bbox has inverted bounds")
        return (
            x0 / self.width,
            y0 / self.height,
            x1 / self.width,
            y1 / self.height,
        )

    @property
    def pdf_to_render_matrix(self) -> Matrix:
        scale, width, height = self.scale, self.width, self.height
        return {
            0: (scale, 0.0, 0.0, scale, 0.0, 0.0),
            90: (0.0, scale, -scale, 0.0, height * scale, 0.0),
            180: (-scale, 0.0, 0.0, -scale, width * scale, height * scale),
            270: (0.0, -scale, scale, 0.0, 0.0, width * scale),
        }[self.rotation]

    @property
    def render_to_pdf_matrix(self) -> Matrix:
        inverse, width, height = 1.0 / self.scale, self.width, self.height
        return {
            0: (inverse, 0.0, 0.0, inverse, 0.0, 0.0),
            90: (0.0, -inverse, inverse, 0.0, 0.0, height),
            180: (-inverse, 0.0, 0.0, -inverse, width, height),
            270: (0.0, inverse, -inverse, 0.0, width, 0.0),
        }[self.rotation]
