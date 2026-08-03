from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from app.pdf.schemas import TextObservation


FIXTURE_NAMES = (
    "parallelism-low-resolution.png",
    "flatness-skew-2deg.png",
    "position-broken-border.png",
    "perpendicularity-line-adhesion.png",
)
NEGATIVE_FIXTURE_NAME = "revision-table-negative.png"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gdt"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _draw_broken_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    gap: int = 0,
    width: int = 1,
) -> None:
    if start[1] == end[1]:
        x0, x1 = sorted((start[0], end[0]))
        cursor = x0
        while cursor < x1:
            run_end = min(x1, cursor + max(1, x1 - x0) // 3)
            draw.line((cursor, start[1], run_end, end[1]), fill=0, width=width)
            cursor = run_end + gap + 1
        return
    y0, y1 = sorted((start[1], end[1]))
    cursor = y0
    while cursor < y1:
        run_end = min(y1, cursor + max(1, y1 - y0) // 3)
        draw.line((start[0], cursor, end[0], run_end), fill=0, width=width)
        cursor = run_end + gap + 1


def _frame_image(name: str) -> Image.Image:
    low_resolution = name == "parallelism-low-resolution.png"
    width, height = (120, 40) if low_resolution else (240, 80)
    scale = 0.5 if low_resolution else 1.0
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)

    def point(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    x0, x1 = point(20, 20)[0], point(220, 20)[0]
    y0, y1 = point(20, 20)[1], point(20, 60)[1]
    separators = (round(90 * scale), round(155 * scale))
    line_width = 1
    gap = 3 if name == "position-broken-border.png" else 0
    for start, end in (
        ((x0, y0), (x1, y0)),
        ((x0, y1), (x1, y1)),
        ((x0, y0), (x0, y1)),
        ((x1, y0), (x1, y1)),
        *((((x, y0), (x, y1)) for x in separators)),
    ):
        _draw_broken_line(draw, start, end, gap=gap, width=line_width)
    if name == "perpendicularity-line-adhesion.png":
        for x in (x0, *separators, x1):
            draw.rectangle((x - 1, y0 + 1, x + 1, y0 + 3), fill=0)
            draw.rectangle((x - 1, y1 - 3, x + 1, y1 - 1), fill=0)
    if name == "flatness-skew-2deg.png":
        image = image.rotate(
            2.0,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=255,
        )
    return image


def _revision_table_image() -> Image.Image:
    image = Image.new("L", (240, 80), color=255)
    draw = ImageDraw.Draw(image)
    x_positions = (10, 55, 100, 145, 190, 230)
    y_positions = (10, 25, 40, 55, 70)
    for x in x_positions:
        draw.line((x, y_positions[0], x, y_positions[-1]), fill=0, width=1)
    for y in y_positions:
        draw.line((x_positions[0], y, x_positions[-1], y), fill=0, width=1)
    return image


def fixture_png(name: str) -> bytes:
    image = (
        _revision_table_image()
        if name == NEGATIVE_FIXTURE_NAME
        else _frame_image(name)
    )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def write_fixtures() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    names = (*FIXTURE_NAMES, NEGATIVE_FIXTURE_NAME)
    manifest = {
        "schema_version": "gdt-raster-fixtures/1",
        "fixtures": {},
    }
    for name in names:
        payload = fixture_png(name)
        (FIXTURE_DIR / name).write_bytes(payload)
        manifest["fixtures"][name] = {
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fixture_bytes(name: str) -> bytes:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload = (FIXTURE_DIR / name).read_bytes()
    expected = manifest["fixtures"][name]
    assert len(payload) == expected["size_bytes"]
    assert hashlib.sha256(payload).hexdigest() == expected["sha256"]
    return payload


def fixture_ocr_observations(name: str) -> tuple[TextObservation, ...]:
    if name == NEGATIVE_FIXTURE_NAME:
        return ()
    return (
        TextObservation(
            observation_id=f"{name}:value",
            source_type="ocr",
            observation_level="region",
            raw_text="0.1",
            normalized_text="0.1",
            page_index=0,
            bbox_pdf=(30.0, 30.0, 75.0, 50.0),
            bbox_normalized=(0.125, 0.375, 0.3125, 0.625),
            direction=(1.0, 0.0),
            direction_angle_degrees=0.0,
            confidence=0.9,
        ),
    )


__all__ = [
    "FIXTURE_NAMES",
    "FIXTURE_DIR",
    "MANIFEST_PATH",
    "NEGATIVE_FIXTURE_NAME",
    "fixture_bytes",
    "fixture_ocr_observations",
    "fixture_png",
    "write_fixtures",
]
