from __future__ import annotations

import pytest

from app.exports.sip_workbook_contract import (
    NUMERIC_DETAIL_FIELDS,
    NUMERIC_METADATA_FIELDS,
    TEXT_DETAIL_FIELDS,
    TEXT_METADATA_FIELDS,
    expected_result_formula,
)


def test_registered_v3_field_partitions_and_result_formula_are_exact() -> None:
    """Catches a divergent numeric/text allowlist or result formula owner."""
    assert NUMERIC_METADATA_FIELDS == frozenset(
        {"toleranced_count", "page_count", "detail_count"}
    )
    assert NUMERIC_DETAIL_FIELDS == frozenset(
        {"number", "source_page", "upper_limit", "lower_limit"}
    )
    assert TEXT_METADATA_FIELDS == frozenset(
        {
            "source_filename",
            "inspection_date",
            "unit",
            "general_tolerance_note",
        }
    )
    assert TEXT_DETAIL_FIELDS == frozenset(
        {"type_label", "basic_size", "tolerance"}
    )

    partitions = (
        NUMERIC_METADATA_FIELDS,
        NUMERIC_DETAIL_FIELDS,
        TEXT_METADATA_FIELDS,
        TEXT_DETAIL_FIELDS,
    )
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(partitions)
        for right in partitions[index + 1 :]
    )
    assert NUMERIC_METADATA_FIELDS | TEXT_METADATA_FIELDS == {
        "source_filename",
        "inspection_date",
        "toleranced_count",
        "page_count",
        "detail_count",
        "unit",
        "general_tolerance_note",
    }
    assert NUMERIC_DETAIL_FIELDS | TEXT_DETAIL_FIELDS == {
        "number",
        "source_page",
        "type_label",
        "basic_size",
        "tolerance",
        "upper_limit",
        "lower_limit",
    }
    assert expected_result_formula(6) == (
        '=IF(H6="","",IF(OR(F6="",G6=""),"",'
        'IF(AND(ISNUMBER(H6),H6<=F6,H6>=G6),"OK","NG")))'
    )
    with pytest.raises(ValueError):
        expected_result_formula(0)
