from __future__ import annotations

from pathlib import Path

import pytest

from app.exports.excel import (
    CapacityExceeded,
    assert_capacity,
)
from app.exports.template_registry import load_template_registration


def _approved_registration():
    backend_root = Path(__file__).resolve().parents[3]
    return load_template_registration(
        backend_root / "assets/templates/sip-v1.xlsx",
        backend_root / "assets/templates/sip-v1.mapping.json",
    )


def test_all_v3_fixed_fields_are_mapped() -> None:
    """Catches a workbook registration that leaves the v3 header or row map incomplete."""
    registration = _approved_registration()

    assert registration.metadata_cells == {
        "source_filename": "B2",
        "inspection_date": "F2",
        "toleranced_count": "I2",
        "page_count": "B3",
        "detail_count": "F3",
        "unit": "I3",
        "general_tolerance_note": "A4",
    }
    assert registration.detail_columns == {
        "number": "A",
        "source_page": "B",
        "type_label": "C",
        "basic_size": "D",
        "tolerance": "E",
        "upper_limit": "F",
        "lower_limit": "G",
    }
    assert registration.measurement_column == "H"
    assert registration.result_column == "I"
    assert registration.image_sheet == "气泡图"
    assert registration.image_anchor == "B2"


def test_capacity_overflow_is_blocking() -> None:
    """P0-EXP-003 blocks details beyond the registered sip-v1 capacity."""
    registration = _approved_registration()

    assert registration.capacity == 512
    assert_capacity(registration, 512)
    with pytest.raises(CapacityExceeded):
        assert_capacity(registration, 513)
