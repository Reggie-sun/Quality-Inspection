from __future__ import annotations

import pytest

from app.pdf.coordinates import PageTransform
from app.pdf.gdt_raster_frames import detect_raster_gdt_frames
from tests.helpers.gdt_raster_fixture import (
    FIXTURE_NAMES,
    fixture_bytes,
    fixture_ocr_observations,
)


def fixture_transform() -> PageTransform:
    return PageTransform(width=240.0, height=80.0, rotation=0, scale=1.0)


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_raster_frame_conditions_keep_ordered_cells(fixture_name: str) -> None:
    frames = detect_raster_gdt_frames(
        png=fixture_bytes(fixture_name),
        page_index=0,
        transform=fixture_transform(),
        crop_bbox_pdf=(0.0, 0.0, 240.0, 80.0),
        text_observations=fixture_ocr_observations(fixture_name),
        source_sha256=fixture_name,
    )
    assert len(frames) == 1
    assert [cell.cell_index for cell in frames[0].cells] == list(
        range(len(frames[0].cells))
    )


def test_raster_revision_table_is_rejected() -> None:
    assert detect_raster_gdt_frames(
        png=fixture_bytes("revision-table-negative.png"),
        page_index=0,
        transform=fixture_transform(),
        crop_bbox_pdf=(0.0, 0.0, 240.0, 80.0),
        text_observations=(),
        source_sha256="revision-table-negative",
    ) == ()
