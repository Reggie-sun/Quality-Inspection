from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from app.candidates.symbol_review import visual_cache_key

SCHEMA_PATH = (
    Path(__file__).parents[2]
    / "app/providers/visual_symbol_review.schema.json"
)


def _cell(index: int, role: str, token: str) -> dict[str, object]:
    return {
        "cell_index": index,
        "cell_role": role,
        "bbox_normalized": [0.1 + index * 0.2, 0.1, 0.3 + index * 0.2, 0.3],
        "raw_token": token,
        "associated_text_observation_ids": [],
        "confidence_signal": 0.97,
    }


def test_visual_symbol_review_v3_accepts_ordered_gdt_cells() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    response = {
        "schema_version": "visual-symbol-review/3",
        "detections": [],
        "gdt_frames": [
            {
                "frame_observation_id": "frame-a",
                "frame_bbox_normalized": [0.1, 0.1, 0.8, 0.3],
                "tolerance_type_signal": "parallelism",
                "cells": [
                    _cell(0, "symbol", "∥"),
                    _cell(1, "tolerance", "0.1"),
                    _cell(2, "datum", "A"),
                ],
                "confidence_signal": 0.97,
            }
        ],
    }

    jsonschema.validate(response, schema)


def test_visual_symbol_review_v2_cannot_satisfy_v3_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    response = {"schema_version": "visual-symbol-review/2", "detections": []}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(response, schema)


def test_visual_cache_identity_changes_when_schema_version_changes() -> None:
    identity = {
        "source_sha256": "a" * 64,
        "visual_observation_ids": ["visual-a"],
        "crop_bbox_pdf": [0.0, 0.0, 100.0, 100.0],
        "crop_sha256": "b" * 64,
        "model": "qwen3-vl-plus",
        "prompt_version": "visual-symbol-prompt/4",
        "adapter_version": "qwen-openai-compatible/5",
        "proposal_version": "visual-observation/3",
        "pymupdf_version": "1.28.0",
    }

    key_v2 = visual_cache_key(**identity, schema_version="visual-symbol-review/2")
    key_v3 = visual_cache_key(**identity, schema_version="visual-symbol-review/3")

    assert key_v2 != key_v3
