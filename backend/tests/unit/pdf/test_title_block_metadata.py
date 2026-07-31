from __future__ import annotations

from copy import deepcopy

import pytest

from app.pdf.title_block_metadata import suggest_sip_metadata


PAGE_WIDTH = 1190.550048828125
PAGE_HEIGHT = 841.8900146484375


def _observation(
    observation_id: str,
    text: str,
    bbox_pdf: tuple[float, float, float, float],
    *,
    page_index: int = 0,
    source_type: str = "native",
    angle: float = 0.0,
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "source_type": source_type,
        "observation_level": "line",
        "raw_text": text,
        "normalized_text": text,
        "page_index": page_index,
        "bbox_pdf": list(bbox_pdf),
        "direction_angle_degrees": angle,
    }


def _welli_page(*extra: dict[str, object]) -> dict[str, object]:
    return {
        "page_index": 0,
        "width": PAGE_WIDTH,
        "height": PAGE_HEIGHT,
        "observations": [
            _observation(
                "material-code-label",
                "物料编码",
                (1037.62, 806.98, 1071.06, 821.72),
            ),
            _observation(
                "material-code-value",
                "12320096476",
                (1098.47, 807.02, 1152.38, 821.77),
            ),
            _observation(
                "drawing-number-label",
                "图样代号",
                (1037.62, 781.46, 1071.07, 796.21),
            ),
            _observation(
                "drawing-number-value",
                "ZHZS25032501-04",
                (1088.29, 781.55, 1162.57, 796.3),
            ),
            _observation(
                "revision-label",
                "版本号",
                (818.01, 730.45, 843.1, 745.2),
            ),
            _observation(
                "revision-value",
                "A/0",
                (821.55, 710.48, 839.54, 725.22),
            ),
            _observation(
                "material-name-value",
                "横行滑板",
                (1088.47, 739.28, 1121.92, 754.02),
            ),
            *extra,
        ],
    }


def _by_field(
    pages: list[object],
) -> dict[str, dict[str, object]]:
    return {
        str(suggestion["field"]): suggestion
        for suggestion in suggest_sip_metadata(pages)
    }


def test_suggests_evidence_backed_welli_title_block_metadata() -> None:
    suggestions = _by_field([_welli_page()])

    assert {
        field: suggestion["value"]
        for field, suggestion in suggestions.items()
    } == {
        "material_code": "12320096476",
        "material_name": "横行滑板",
        "drawing_number": "ZHZS25032501-04",
        "revision": "A/0",
    }
    assert "material" not in suggestions
    assert suggestions["drawing_number"] == {
        "field": "drawing_number",
        "value": "ZHZS25032501-04",
        "observation_id": "drawing-number-value",
        "label_observation_id": "drawing-number-label",
        "page_index": 0,
        "bbox_pdf": [1088.29, 781.55, 1162.57, 796.3],
        "rule_version": "welli-title-metadata/1",
        "evidence_codes": [
            "bottom_right_title_anchor",
            "native_line",
            "same_row_right_of_label",
            "unique_candidate",
        ],
    }
    assert suggestions["material_name"]["label_observation_id"] == (
        "drawing-number-label"
    )
    assert suggestions["material_name"]["evidence_codes"] == [
        "bottom_right_title_anchor",
        "drawing_number_column",
        "native_line",
        "unique_candidate",
    ]


def test_explicit_material_label_can_supply_material() -> None:
    suggestions = _by_field(
        [
            _welli_page(
                _observation(
                    "material-label",
                    "材质",
                    (900.0, 760.0, 925.0, 775.0),
                ),
                _observation(
                    "material-value",
                    "6061-T6",
                    (940.0, 760.0, 990.0, 775.0),
                ),
            )
        ]
    )

    assert suggestions["material"]["value"] == "6061-T6"
    assert suggestions["material"]["label_observation_id"] == "material-label"


def test_ambiguous_same_row_value_omits_only_conflicting_field() -> None:
    suggestions = _by_field(
        [
            _welli_page(
                _observation(
                    "material-code-conflict",
                    "12320096477",
                    (1080.0, 807.0, 1150.0, 821.7),
                )
            )
        ]
    )

    assert "material_code" not in suggestions
    assert suggestions["drawing_number"]["value"] == "ZHZS25032501-04"


def test_ocr_rotated_and_cross_page_values_are_not_suggestions() -> None:
    page = _welli_page()
    observations = page["observations"]
    assert isinstance(observations, list)
    for observation in observations:
        if observation["observation_id"] == "material-code-value":
            observation["source_type"] = "ocr"
        if observation["observation_id"] == "drawing-number-value":
            observation["direction_angle_degrees"] = 90.0
        if observation["observation_id"] == "revision-value":
            observation["page_index"] = 1

    suggestions = _by_field([page])

    assert "material_code" not in suggestions
    assert "drawing_number" not in suggestions
    assert "material_name" not in suggestions
    assert "revision" not in suggestions


def test_title_labels_outside_bottom_right_band_do_not_create_suggestions() -> None:
    page = _welli_page()
    observations = page["observations"]
    assert isinstance(observations, list)
    for observation in observations:
        bbox = observation["bbox_pdf"]
        assert isinstance(bbox, list)
        observation["bbox_pdf"] = [
            float(bbox[0]) - 750.0,
            float(bbox[1]) - 600.0,
            float(bbox[2]) - 750.0,
            float(bbox[3]) - 600.0,
        ]

    assert suggest_sip_metadata([page]) == []


def test_same_field_suggested_on_multiple_pages_fails_closed() -> None:
    first = _welli_page()
    second = deepcopy(first)
    second["page_index"] = 1
    observations = second["observations"]
    assert isinstance(observations, list)
    for observation in observations:
        observation["page_index"] = 1
        observation["observation_id"] = f"page-2-{observation['observation_id']}"

    assert suggest_sip_metadata([first, second]) == []


def test_ambiguous_field_on_another_page_suppresses_unique_suggestion() -> None:
    first = _welli_page()
    second = deepcopy(first)
    second["page_index"] = 1
    observations = second["observations"]
    assert isinstance(observations, list)
    for observation in observations:
        observation["page_index"] = 1
        observation["observation_id"] = f"page-2-{observation['observation_id']}"
    observations.append(
        _observation(
            "page-2-material-code-conflict",
            "12320096477",
            (1080.0, 807.0, 1150.0, 821.7),
            page_index=1,
        )
    )

    suggestions = _by_field([first, second])

    assert "material_code" not in suggestions


@pytest.mark.parametrize("non_name", ["2026年7月31日", "第1页"])
def test_date_and_page_tokens_are_not_material_name_suggestions(
    non_name: str,
) -> None:
    page = _welli_page()
    observations = page["observations"]
    assert isinstance(observations, list)
    for observation in observations:
        if observation["observation_id"] == "material-name-value":
            observation["raw_text"] = non_name
            observation["normalized_text"] = non_name

    suggestions = _by_field([page])

    assert "material_name" not in suggestions


def test_malformed_inventory_pages_are_ignored() -> None:
    assert suggest_sip_metadata([None, {}, {"observations": "invalid"}]) == []
