from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pymupdf


GENERATOR_VERSION = "symbol-fixture/1"
PAGE_BOX = (0.0, 0.0, 612.0, 792.0)
NEGATIVE_FAMILIES = (
    "part_or_hole_geometry",
    "hatch_center_or_cross",
    "dimension_leader_or_section_line",
    "view_or_section_label",
    "revision_table_or_invalid_marker",
    "datum_like_letter_or_table_cell",
    "watermark_logo_title_or_signoff",
    "isometric_hole_slot_or_edge",
    "ordinary_text_number_material_or_requirement",
)


def _insert_native_text(
    page: pymupdf.Page,
    *,
    point: tuple[float, float],
    text: str,
) -> None:
    fontname = "china-s" if any(ord(character) > 127 for character in text) else "helv"
    page.insert_text(point, text, fontsize=9.0, fontname=fontname, color=(0, 0, 0))


def _draw_target_symbol(
    page: pymupdf.Page,
    *,
    symbol_kind: str,
    x: float,
    baseline: float,
) -> tuple[float, float, float, float]:
    shape = page.new_shape()
    y = baseline - 5.0
    if symbol_kind == "diameter":
        shape.draw_circle((x + 8.0, y), 6.0)
        shape.draw_line((x + 3.0, y + 5.0), (x + 13.0, y - 5.0))
        bbox = (x + 2.0, y - 6.0, x + 14.0, y + 6.0)
    elif symbol_kind == "depth":
        shape.draw_line((x + 8.0, y - 7.0), (x + 8.0, y + 5.0))
        shape.draw_line((x + 3.0, y), (x + 8.0, y + 5.0))
        shape.draw_line((x + 13.0, y), (x + 8.0, y + 5.0))
        shape.draw_line((x + 2.0, y - 7.0), (x + 14.0, y - 7.0))
        bbox = (x + 2.0, y - 7.0, x + 14.0, y + 5.0)
    elif symbol_kind == "counterbore":
        shape.draw_line((x + 2.0, y - 6.0), (x + 2.0, y + 5.0))
        shape.draw_line((x + 2.0, y + 5.0), (x + 14.0, y + 5.0))
        shape.draw_line((x + 14.0, y + 5.0), (x + 14.0, y - 6.0))
        shape.draw_line((x, y - 6.0), (x + 16.0, y - 6.0))
        bbox = (x, y - 6.0, x + 16.0, y + 5.0)
    elif symbol_kind == "surface_roughness":
        shape.draw_line((x + 1.0, y + 3.0), (x + 6.0, y + 7.0))
        shape.draw_line((x + 6.0, y + 7.0), (x + 13.0, y - 7.0))
        shape.draw_line((x + 10.0, y - 7.0), (x + 17.0, y - 7.0))
        bbox = (x + 1.0, y - 7.0, x + 17.0, y + 7.0)
    elif symbol_kind.startswith("gdt_"):
        shape.draw_rect(pymupdf.Rect(x, y - 8.0, x + 20.0, y + 8.0))
        if symbol_kind == "gdt_parallelism":
            shape.draw_line((x + 7.0, y - 5.0), (x + 7.0, y + 5.0))
            shape.draw_line((x + 12.0, y - 5.0), (x + 12.0, y + 5.0))
        elif symbol_kind == "gdt_perpendicularity":
            shape.draw_line((x + 5.0, y + 4.0), (x + 15.0, y + 4.0))
            shape.draw_line((x + 10.0, y - 5.0), (x + 10.0, y + 4.0))
        else:
            shape.draw_line((x + 4.0, y - 1.0), (x + 8.0, y - 3.0))
            shape.draw_line((x + 8.0, y - 3.0), (x + 13.0, y - 1.0))
            shape.draw_line((x + 13.0, y - 1.0), (x + 16.0, y - 3.0))
        bbox = (x, y - 8.0, x + 20.0, y + 8.0)
    elif symbol_kind == "datum_reference":
        shape.draw_rect(pymupdf.Rect(x, y - 8.0, x + 18.0, y + 8.0))
        shape.draw_line((x + 9.0, y + 8.0), (x + 9.0, y + 14.0))
        bbox = (x, y - 8.0, x + 18.0, y + 14.0)
    elif symbol_kind == "revision_marker":
        shape.draw_line((x + 9.0, y - 10.0), (x, y + 8.0))
        shape.draw_line((x, y + 8.0), (x + 18.0, y + 8.0))
        shape.draw_line((x + 18.0, y + 8.0), (x + 9.0, y - 10.0))
        bbox = (x, y - 10.0, x + 18.0, y + 8.0)
    else:
        raise AssertionError(f"unsupported target symbol: {symbol_kind}")
    shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()
    return bbox


def _draw_negative_geometry(
    page: pymupdf.Page,
    *,
    variant: str,
    bbox: tuple[float, float, float, float],
) -> None:
    x0, y0, x1, y1 = bbox
    shape = page.new_shape()
    if variant in {"part_outline", "title_border", "revision_table"}:
        shape.draw_rect(pymupdf.Rect(*bbox))
        if variant == "revision_table":
            shape.draw_line(((x0 + x1) / 2.0, y0), ((x0 + x1) / 2.0, y1))
    elif variant == "hatch":
        for offset in (0.0, 12.0, 24.0):
            shape.draw_line((x0, y0 + offset), (x1, y0 + offset + 20.0))
    elif variant == "dimension":
        mid = (y0 + y1) / 2.0
        shape.draw_line((x0, mid), (x1, mid))
        shape.draw_line((x0, mid), (x0 + 8.0, mid - 4.0))
        shape.draw_line((x0, mid), (x0 + 8.0, mid + 4.0))
    elif variant == "invalid_triangle":
        shape.draw_line(((x0 + x1) / 2.0, y0), (x0, y1))
        shape.draw_line((x0, y1), (x1, y1))
        shape.draw_line((x1, y1), ((x0 + x1) / 2.0, y0))
    elif variant == "slot":
        radius = (y1 - y0) / 2.0
        shape.draw_line((x0 + radius, y0), (x1 - radius, y0))
        shape.draw_line((x0 + radius, y1), (x1 - radius, y1))
        shape.draw_circle((x0 + radius, (y0 + y1) / 2.0), radius)
        shape.draw_circle((x1 - radius, (y0 + y1) / 2.0), radius)
    elif variant == "cross":
        shape.draw_line((x0, y0), (x1, y1))
        shape.draw_line((x0, y1), (x1, y0))
    elif variant == "circle":
        shape.draw_circle(((x0 + x1) / 2.0, (y0 + y1) / 2.0), (x1 - x0) / 2.0)
    elif variant == "oversized_context":
        shape.draw_rect(pymupdf.Rect(x0, y0, x0 + 40.0, y1))
        shape.draw_rect(pymupdf.Rect(x1 - 40.0, y0, x1, y1))
    else:
        raise AssertionError(f"unsupported negative geometry: {variant}")
    shape.finish(width=1.0, color=(0, 0, 0), closePath=False)
    shape.commit()


def _positive_label(
    page: pymupdf.Page,
    *,
    page_index: int,
    label_index: int,
    symbol_kind: str,
    baseline: float,
    token: str,
    expected_disposition: str = "candidate",
    expected_projection: str | None = None,
) -> dict[str, Any]:
    symbol_bbox = _draw_target_symbol(
        page,
        symbol_kind=symbol_kind,
        x=70.0,
        baseline=baseline,
    )
    text_x = 75.0 if symbol_kind in {"datum_reference", "revision_marker"} else 94.0
    _insert_native_text(page, point=(text_x, baseline), text=token)
    return {
        "label_id": f"P{page_index + 1}-POS-{label_index:02d}",
        "bbox_pdf": [
            min(symbol_bbox[0], text_x),
            min(symbol_bbox[1], baseline - 10.0),
            max(symbol_bbox[2], text_x + max(12.0, len(token) * 5.0)),
            max(symbol_bbox[3], baseline + 3.0),
        ],
        "fixture_family": symbol_kind,
        "symbol_kinds": (
            ["diameter", "depth", "counterbore"]
            if symbol_kind == "counterbore"
            else [symbol_kind]
        ),
        "expected_disposition": expected_disposition,
        "expected_projection": expected_projection,
    }


def _negative_label(
    page: pymupdf.Page,
    *,
    page_index: int,
    label_index: int,
    negative_family: str,
    variant: str | None,
    bbox: tuple[float, float, float, float],
    text: str | None = None,
    expected_disposition: str = "ambiguous",
) -> dict[str, Any]:
    if variant is not None:
        _draw_negative_geometry(page, variant=variant, bbox=bbox)
    if text is not None:
        _insert_native_text(page, point=(bbox[0], bbox[3]), text=text)
    return {
        "label_id": f"P{page_index + 1}-NEG-{label_index:02d}",
        "bbox_pdf": list(bbox),
        "symbol_kinds": ["frozen_negative"],
        "negative_family": negative_family,
        "expected_disposition": expected_disposition,
        "expected_projection": None,
    }


def _populate_page(
    page: pymupdf.Page,
    *,
    page_index: int,
) -> list[dict[str, Any]]:
    if page_index == 0:
        positive_specs = (
            ("diameter", 60.0, "18", "diameter_dimension"),
            ("diameter", 110.0, "20", "diameter_dimension"),
            ("depth", 160.0, "M6深12", "thread"),
            ("depth", 210.0, "M8深8", "thread"),
            ("counterbore", 260.0, "22 6", "composite"),
            ("surface_roughness", 310.0, "3.2", "roughness"),
            ("surface_roughness", 360.0, "1.6", "roughness"),
            ("gdt_parallelism", 410.0, "0.1 A", "geometric_tolerance"),
            ("datum_reference", 460.0, "A", None),
            ("revision_marker", 510.0, "1", None),
        )
        negative_specs = (
            ("part_or_hole_geometry", "part_outline", (300.0, 40.0, 570.0, 150.0), None),
            ("hatch_center_or_cross", "hatch", (340.0, 190.0, 470.0, 235.0), None),
            (
                "dimension_leader_or_section_line",
                "dimension",
                (320.0, 280.0, 550.0, 300.0),
                None,
            ),
            ("view_or_section_label", None, (430.0, 330.0, 470.0, 345.0), "A-A"),
            (
                "revision_table_or_invalid_marker",
                "revision_table",
                (320.0, 370.0, 550.0, 415.0),
                "REV",
            ),
            (
                "datum_like_letter_or_table_cell",
                None,
                (430.0, 455.0, 445.0, 470.0),
                "B",
            ),
        )
    else:
        positive_specs = (
            ("diameter", 60.0, "40", "diameter_dimension"),
            ("diameter", 110.0, "100", "diameter_dimension"),
            ("depth", 160.0, "M10深16", "thread"),
            ("counterbore", 210.0, "30 10", "composite"),
            ("surface_roughness", 260.0, "6.3", "roughness"),
            ("gdt_perpendicularity", 310.0, "0.2 B", "geometric_tolerance"),
            ("gdt_flatness", 360.0, "0.05", "geometric_tolerance"),
            ("datum_reference", 410.0, "C", None),
            ("revision_marker", 460.0, "2", None),
        )
        negative_specs = (
            (
                "watermark_logo_title_or_signoff",
                "title_border",
                (300.0, 40.0, 580.0, 155.0),
                None,
            ),
            (
                "isometric_hole_slot_or_edge",
                "slot",
                (350.0, 200.0, 410.0, 220.0),
                None,
            ),
            (
                "ordinary_text_number_material_or_requirement",
                "oversized_context",
                (300.0, 245.0, 580.0, 280.0),
                "MATERIAL STEEL REQUIREMENT ORDINARY TEXT 12345",
            ),
            ("revision_table_or_invalid_marker", "invalid_triangle", (360.0, 320.0, 390.0, 350.0), None),
            ("part_or_hole_geometry", "circle", (350.0, 400.0, 390.0, 440.0), None),
            ("hatch_center_or_cross", "cross", (350.0, 490.0, 390.0, 530.0), None),
        )

    labels: list[dict[str, Any]] = []
    for index, (kind, baseline, token, projection) in enumerate(positive_specs, start=1):
        disposition = (
            "reference_context"
            if kind == "datum_reference"
            else "non_inspection"
            if kind == "revision_marker"
            else "candidate"
        )
        labels.append(
            _positive_label(
                page,
                page_index=page_index,
                label_index=index,
                symbol_kind=kind,
                baseline=baseline,
                token=token,
                expected_disposition=disposition,
                expected_projection=projection,
            )
        )
    for index, (family, variant, bbox, text) in enumerate(negative_specs, start=1):
        labels.append(
            _negative_label(
                page,
                page_index=page_index,
                label_index=index,
                negative_family=family,
                variant=variant,
                bbox=bbox,
                text=text,
                expected_disposition=(
                    "non_inspection"
                    if family == "view_or_section_label" and text == "A-A"
                    else "ambiguous"
                ),
            )
        )
    return labels


def build_symbol_fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Build a byte-stable sanitized vector fixture and its independent manifest."""
    output_dir = Path(tmp_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "symbol-fixture.pdf"

    document = pymupdf.open()
    pages: list[dict[str, Any]] = []
    for page_index in range(2):
        page = document.new_page(width=PAGE_BOX[2], height=PAGE_BOX[3])
        pages.append(
            {
                "page_index": page_index,
                "labels": _populate_page(page, page_index=page_index),
            }
        )
    document.set_metadata({})
    document.save(
        pdf_path,
        garbage=4,
        deflate=True,
        no_new_id=True,
    )
    document.close()

    helper_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity = {
        "generator_version": GENERATOR_VERSION,
        "helper_sha256": helper_sha256,
        "pymupdf_version": pymupdf.__version__,
    }
    identity_bytes = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest: dict[str, Any] = {
        "schema_version": "symbol-fixture-manifest/1",
        "input_identity": identity,
        "fixture_identity_sha256": hashlib.sha256(identity_bytes).hexdigest(),
        "source_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "page_boxes": [list(PAGE_BOX), list(PAGE_BOX)],
        "pages": pages,
    }
    return pdf_path, manifest
