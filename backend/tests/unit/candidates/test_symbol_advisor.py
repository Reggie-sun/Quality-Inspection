from __future__ import annotations

import copy

import pytest

from app.candidates.symbol_review import (
    VisualSymbolSchemaError,
    parse_visual_symbol_json,
    validate_symbol_detections,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": "visual-symbol-review/1",
        "detections": [
            {
                "visual_observation_id": "visual-001",
                "symbol_kind": "diameter",
                "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
                "associated_text_observation_ids": ["text-001"],
                "requires_confirmation": True,
            },
            {
                "visual_observation_id": "visual-002",
                "symbol_kind": "revision_marker",
                "bbox_normalized": [0.6, 0.5, 0.8, 0.9],
                "associated_text_observation_ids": ["text-002"],
                "requires_confirmation": True,
            },
        ],
    }


def test_visual_symbol_response_accepts_only_exact_schema() -> None:
    """ADV-01: only the frozen visual-symbol response shape crosses the port."""
    payload = _payload()
    assert parse_visual_symbol_json(payload) == payload

    invalid_payloads: list[dict[str, object]] = []
    missing = copy.deepcopy(payload)
    del missing["detections"][0]["symbol_kind"]  # type: ignore[index]
    invalid_payloads.append(missing)
    extra_root = copy.deepcopy(payload)
    extra_root["explanation"] = "not allowed"
    invalid_payloads.append(extra_root)
    extra_detection = copy.deepcopy(payload)
    extra_detection["detections"][0]["confidence"] = 0.99  # type: ignore[index]
    invalid_payloads.append(extra_detection)
    unconfirmed = copy.deepcopy(payload)
    unconfirmed["detections"][0]["requires_confirmation"] = False  # type: ignore[index]
    invalid_payloads.append(unconfirmed)

    for invalid in invalid_payloads:
        with pytest.raises(
            VisualSymbolSchemaError,
            match="^visual symbol response violates frozen schema$",
        ):
            parse_visual_symbol_json(invalid)

    private_marker = "private-marker-should-not-cross-schema-boundary"
    with pytest.raises(VisualSymbolSchemaError) as raised:
        parse_visual_symbol_json(private_marker)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert private_marker not in str(raised.value)


def test_visual_symbol_response_rejects_invalid_identity_or_shape() -> None:
    """ADV-02: local identity, geometry, cardinality and duplicate rules fail closed."""
    payload = _payload()
    payload["detections"] = [
        payload["detections"][0],  # type: ignore[index]
        copy.deepcopy(payload["detections"][0]),  # type: ignore[index]
        {
            "visual_observation_id": "unknown-visual",
            "symbol_kind": "diameter",
            "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
            "associated_text_observation_ids": ["text-001"],
            "requires_confirmation": True,
        },
        {
            "visual_observation_id": "visual-002",
            "symbol_kind": "depth",
            "bbox_normalized": [0.4, 0.4, 0.4, 0.6],
            "associated_text_observation_ids": ["text-002"],
            "requires_confirmation": True,
        },
        {
            "visual_observation_id": "visual-002",
            "symbol_kind": "counterbore",
            "bbox_normalized": [0.5, 0.5, 0.7, 0.7],
            "associated_text_observation_ids": ["unknown-text"],
            "requires_confirmation": True,
        },
    ]
    unchanged = copy.deepcopy(payload)
    accepted, rejected = validate_symbol_detections(
        parse_visual_symbol_json(payload),
        visual_observation_ids=("visual-001", "visual-002"),
        text_allowlists={
            "visual-001": ("text-001",),
            "visual-002": ("text-002",),
        },
        crop_bbox_pdf=(10.0, 20.0, 110.0, 220.0),
    )

    assert len(accepted) == 1
    assert accepted[0].visual_observation_id == "visual-001"
    assert accepted[0].bbox_pdf == (20.0, 60.0, 40.0, 100.0)
    assert {item.rejection_code for item in rejected} == {
        "visual_bbox_invalid",
        "visual_source_mismatch",
        "visual_duplicate_detection",
    }
    assert payload == unchanged

    overflow = _payload()
    overflow["detections"] = [
        {
            "visual_observation_id": "visual-001",
            "symbol_kind": "diameter",
            "bbox_normalized": [0.1 * index, 0.1, 0.1 * index + 0.05, 0.2],
            "associated_text_observation_ids": ["text-001"],
            "requires_confirmation": True,
        }
        for index in range(5)
    ]
    accepted, rejected = validate_symbol_detections(
        parse_visual_symbol_json(overflow),
        visual_observation_ids=("visual-001",),
        text_allowlists={"visual-001": ("text-001",)},
        crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
    )
    assert accepted == ()
    assert len(rejected) == 5
    assert {item.rejection_code for item in rejected} == {
        "visual_source_mismatch"
    }

    for field, value in (
        ("bbox_normalized", [-0.1, 0.1, 0.2, 0.3]),
        ("symbol_kind", "unknown"),
    ):
        invalid = _payload()
        invalid["detections"][0][field] = value  # type: ignore[index]
        with pytest.raises(VisualSymbolSchemaError):
            parse_visual_symbol_json(invalid)
