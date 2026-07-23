from __future__ import annotations

from pathlib import Path

import pytest

from app.exports.excel import (
    REQUIRED_DETAIL_FIELDS,
    REQUIRED_METADATA_FIELDS,
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


def test_all_fixed_fields_are_mapped() -> None:
    """P0-EXP-002 covers the fixed 12 cells fields and balloon-image mapping."""
    registration = _approved_registration()

    assert set(registration.metadata_cells) == REQUIRED_METADATA_FIELDS
    assert set(registration.detail_columns) == REQUIRED_DETAIL_FIELDS
    assert len(REQUIRED_METADATA_FIELDS | REQUIRED_DETAIL_FIELDS) == 12
    assert registration.image_sheet == "气泡图"
    assert registration.image_anchor == "B2"


def test_capacity_overflow_is_blocking() -> None:
    """P0-EXP-003 blocks details beyond the registered sip-v1 capacity."""
    registration = _approved_registration()

    assert registration.capacity == 512
    assert_capacity(registration, 512)
    with pytest.raises(CapacityExceeded):
        assert_capacity(registration, 513)
