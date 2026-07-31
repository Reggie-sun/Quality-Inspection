from __future__ import annotations

import copy

import pytest

from app.review.sip_mapping import SipMappingResult, map_sip_item


def test_linear_item_maps_to_complete_sip_row() -> None:
    item = {
        "item_id": "linear-1",
        "item_type": "linear_dimension",
        "normalized_text": "35",
        "quantity": 2,
        "page_index": 0,
    }

    result = map_sip_item(item, inspection_role=" IPQC ")

    assert result == SipMappingResult(
        fields={
            "inspection_item": "线性尺寸：35（2处）",
            "inspection_standard": "图纸要求",
            "inspection_method": "游标卡尺",
            "key_dimension": "否",
            "inspection_role": "IPQC",
            "source_page": 1,
            "remarks": "",
        },
        provenance={
            "inspection_item": "sip-auto-map/1",
            "inspection_standard": "sip-auto-map/1",
            "inspection_method": "sip-auto-map/1",
            "key_dimension": "sip-auto-map/1",
            "inspection_role": "sip-auto-map/1",
            "source_page": "sip-auto-map/1",
            "remarks": "sip-auto-map/1",
        },
        exceptions=(),
    )
    assert item == {
        "item_id": "linear-1",
        "item_type": "linear_dimension",
        "normalized_text": "35",
        "quantity": 2,
        "page_index": 0,
    }


@pytest.mark.parametrize(
    ("item_type", "expected_item", "expected_method"),
    [
        ("diameter_dimension", "直径尺寸：Φ20", "游标卡尺"),
        ("thread", "螺纹：M6", "螺纹规"),
        ("radius", "半径：R3", "半径规"),
        ("angle", "角度：45°", "万能角度尺"),
        ("general_requirement", "通用要求：锐边去毛刺", "目视"),
    ],
)
def test_supported_item_types_use_versioned_methods(
    item_type: str,
    expected_item: str,
    expected_method: str,
) -> None:
    result = map_sip_item(
        {
            "item_id": item_type,
            "item_type": item_type,
            "normalized_text": {
                "diameter_dimension": "Φ20",
                "thread": "M6",
                "radius": "R3",
                "angle": "45°",
                "general_requirement": "锐边去毛刺",
            }[item_type],
            "page_index": 1,
        },
        inspection_role="IPQC",
    )

    assert result.fields["inspection_item"] == expected_item
    assert result.fields["inspection_method"] == expected_method
    assert result.fields["source_page"] == 2
    assert result.exceptions == ()


def test_confirmed_requirement_values_win_over_rule_defaults() -> None:
    item = {
        "item_id": "linear-1",
        "item_type": "linear_dimension",
        "normalized_text": "35",
        "page_index": 0,
        "inspection_item": "未注尺寸公差",
        "inspection_standard": "GB/T 1804-m",
        "key_dimension": "是",
        "source_page": 3,
        "remarks": "技术要求第 4 条",
        "sip_suggestion_provenance": {
            "inspection_item": "requirement-4",
            "inspection_standard": "requirement-4",
            "key_dimension": "requirement-4",
            "source_page": "requirement-4",
            "remarks": "requirement-4",
        },
    }
    original = copy.deepcopy(item)

    result = map_sip_item(item, inspection_role="IPQC")

    assert result.fields == {
        "inspection_item": "未注尺寸公差",
        "inspection_standard": "GB/T 1804-m",
        "inspection_method": "游标卡尺",
        "key_dimension": "是",
        "inspection_role": "IPQC",
        "source_page": 3,
        "remarks": "技术要求第 4 条",
    }
    assert result.provenance == {
        "inspection_item": "requirement-4",
        "inspection_standard": "requirement-4",
        "inspection_method": "sip-auto-map/1",
        "key_dimension": "requirement-4",
        "inspection_role": "sip-auto-map/1",
        "source_page": "requirement-4",
        "remarks": "requirement-4",
    }
    assert result.exceptions == ()
    assert item == original


@pytest.mark.parametrize(
    ("item", "inspection_role", "expected"),
    [
        (
            {
                "item_id": "missing-role",
                "item_type": "thread",
                "normalized_text": "M6",
                "page_index": 0,
            },
            " ",
            ("missing_inspection_role",),
        ),
        (
            {
                "item_id": "missing-page",
                "item_type": "thread",
                "normalized_text": "M6",
                "page_index": None,
            },
            "IPQC",
            ("missing_source_page",),
        ),
        (
            {
                "item_id": "unknown",
                "normalized_text": "28.5",
                "page_index": 0,
            },
            "IPQC",
            ("unsupported_item_type",),
        ),
        (
            {
                "item_id": "composite",
                "item_type": "composite",
                "normalized_text": "Φ10 深20",
                "page_index": 0,
            },
            "IPQC",
            ("composite_method_required",),
        ),
    ],
)
def test_unresolved_inputs_return_exact_exceptions(
    item: dict[str, object],
    inspection_role: str,
    expected: tuple[str, ...],
) -> None:
    result = map_sip_item(item, inspection_role=inspection_role)

    assert result.exceptions == expected


def test_same_text_from_different_sources_is_not_collapsed() -> None:
    first = map_sip_item(
        {
            "item_id": "first",
            "item_type": "linear_dimension",
            "normalized_text": "35",
            "page_index": 0,
            "source_location_ids": ["source-first"],
        },
        inspection_role="IPQC",
    )
    second = map_sip_item(
        {
            "item_id": "second",
            "item_type": "linear_dimension",
            "normalized_text": "35",
            "page_index": 1,
            "source_location_ids": ["source-second"],
        },
        inspection_role="IPQC",
    )

    assert first.fields["source_page"] == 1
    assert second.fields["source_page"] == 2
    assert first.fields["inspection_item"] == second.fields["inspection_item"]
