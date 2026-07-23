from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import fitz


BALLOON_RADIUS_PDF = 12.0


@dataclass(frozen=True)
class FrozenBalloon:
    page_index: int
    formal_number: int
    center_pdf: tuple[float, float]
    leader_target_pdf: tuple[float, float]


def _point(value: tuple[float, float]) -> fitz.Point:
    if len(value) != 2 or not all(math.isfinite(float(part)) for part in value):
        raise ValueError("invalid balloon geometry")
    return fitz.Point(float(value[0]), float(value[1]))


def render_ballooned_pdf(
    source_pdf: bytes,
    balloons: list[FrozenBalloon],
    font_path: Path,
) -> bytes:
    with fitz.open(stream=source_pdf, filetype="pdf") as document:
        by_page: dict[int, list[FrozenBalloon]] = {}
        for balloon in balloons:
            if (
                not isinstance(balloon.page_index, int)
                or isinstance(balloon.page_index, bool)
                or not isinstance(balloon.formal_number, int)
                or isinstance(balloon.formal_number, bool)
                or balloon.formal_number < 1
            ):
                raise ValueError("invalid frozen balloon identity")
            by_page.setdefault(balloon.page_index, []).append(balloon)

        for page_index, page_balloons in sorted(by_page.items()):
            if page_index < 0 or page_index >= document.page_count:
                raise ValueError(f"balloon page out of range: {page_index}")
            page = document[page_index]
            page.insert_font(fontname="QIBalloon", fontfile=str(font_path))
            for balloon in sorted(page_balloons, key=lambda item: item.formal_number):
                center = _point(balloon.center_pdf)
                target = _point(balloon.leader_target_pdf)
                circle = fitz.Rect(
                    center.x - BALLOON_RADIUS_PDF,
                    center.y - BALLOON_RADIUS_PDF,
                    center.x + BALLOON_RADIUS_PDF,
                    center.y + BALLOON_RADIUS_PDF,
                )
                if not page.rect.contains(circle) or not page.rect.contains(target):
                    raise ValueError(
                        f"invalid balloon geometry: {balloon.formal_number}"
                    )
                page.draw_line(
                    center,
                    target,
                    color=(0, 0, 0),
                    width=0.8,
                    overlay=True,
                )
                page.draw_circle(
                    center,
                    BALLOON_RADIUS_PDF,
                    color=(0, 0, 0),
                    width=0.8,
                    overlay=True,
                )
                remaining = page.insert_textbox(
                    circle,
                    str(balloon.formal_number),
                    fontname="QIBalloon",
                    fontsize=9,
                    align=fitz.TEXT_ALIGN_CENTER,
                    color=(0, 0, 0),
                    overlay=True,
                )
                if remaining < 0:
                    raise ValueError(
                        f"balloon number does not fit: {balloon.formal_number}"
                    )
        return document.tobytes(garbage=4, deflate=True, no_new_id=True)
