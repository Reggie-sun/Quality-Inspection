from __future__ import annotations

import pytest

from app.candidates.gdt_evidence import (
    GdtEvidenceValidationError,
    validate_gdt_frame_evidence,
    validate_gdt_frame_evidence_batch,
)
from app.pdf.gdt_frames import GdtCellObservation, GdtFrameObservation


def _frame_observation() -> GdtFrameObservation:
    return GdtFrameObservation(
        observation_id="frame-a",
        page_index=0,
        bbox_pdf=(10.0, 10.0, 90.0, 30.0),
        bbox_normalized=(0.1, 0.1, 0.9, 0.3),
        cells=(
            GdtCellObservation(0, (10.0, 10.0, 35.0, 30.0), (0.1, 0.1, 0.35, 0.3)),
            GdtCellObservation(1, (35.0, 10.0, 65.0, 30.0), (0.35, 0.1, 0.65, 0.3)),
            GdtCellObservation(2, (65.0, 10.0, 90.0, 30.0), (0.65, 0.1, 0.9, 0.3)),
        ),
        associated_text_observation_ids=("value-a", "datum-a"),
        proposal_source="native_vector",
        proposal_state="complete",
        geometry_sha256="a" * 64,
    )


def _provider_frame(*, text_ids: tuple[str, ...] = ("value-a",)) -> dict[str, object]:
    return {
        "frame_observation_id": "frame-a",
        "frame_bbox_normalized": [0.1, 0.1, 0.9, 0.3],
        "tolerance_type_signal": "parallelism",
        "cells": [
            {
                "cell_index": 0,
                "cell_role": "symbol",
                "bbox_normalized": [0.1, 0.1, 0.35, 0.3],
                "raw_token": "∥",
                "associated_text_observation_ids": [],
                "confidence_signal": 0.97,
            },
            {
                "cell_index": 1,
                "cell_role": "tolerance",
                "bbox_normalized": [0.35, 0.1, 0.65, 0.3],
                "raw_token": "0.1",
                "associated_text_observation_ids": list(text_ids),
                "confidence_signal": 0.95,
            },
            {
                "cell_index": 2,
                "cell_role": "datum",
                "bbox_normalized": [0.65, 0.1, 0.9, 0.3],
                "raw_token": "A",
                "associated_text_observation_ids": ["datum-a"],
                "confidence_signal": 0.96,
            },
        ],
        "confidence_signal": 0.96,
    }


def test_gdt_frame_evidence_accepts_ordered_cells() -> None:
    evidence = validate_gdt_frame_evidence(
        provider_frame=_provider_frame(),
        observation=_frame_observation(),
        crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
    )

    assert evidence.frame_observation_id == "frame-a"
    assert [cell.cell_index for cell in evidence.cells] == [0, 1, 2]


def test_gdt_cell_rejects_text_id_outside_frame_allowlist() -> None:
    with pytest.raises(
        GdtEvidenceValidationError,
        match="text_id_not_allowlisted",
    ) as raised:
        validate_gdt_frame_evidence(
            provider_frame=_provider_frame(text_ids=("other-page",)),
            observation=_frame_observation(),
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
        )

    assert raised.value.code == "text_id_not_allowlisted"


def test_gdt_cell_indexes_must_be_contiguous() -> None:
    provider_frame = _provider_frame()
    provider_frame["cells"] = [
        dict(provider_frame["cells"][0]),
        {**provider_frame["cells"][2], "cell_index": 2},
    ]

    with pytest.raises(GdtEvidenceValidationError, match="cell_index_not_contiguous"):
        validate_gdt_frame_evidence(
            provider_frame=provider_frame,
            observation=_frame_observation(),
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
        )


def test_gdt_evidence_rejects_frame_bbox_outside_observation() -> None:
    provider_frame = _provider_frame()
    provider_frame["frame_bbox_normalized"] = [0.1, 0.1, 0.95, 0.3]

    with pytest.raises(GdtEvidenceValidationError, match="frame_bbox_out_of_bounds"):
        validate_gdt_frame_evidence(
            provider_frame=provider_frame,
            observation=_frame_observation(),
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
        )


def test_gdt_evidence_rejects_extra_provider_fields() -> None:
    provider_frame = _provider_frame()
    provider_frame["status"] = "review_required"

    with pytest.raises(GdtEvidenceValidationError, match="provider_schema_invalid"):
        validate_gdt_frame_evidence(
            provider_frame=provider_frame,
            observation=_frame_observation(),
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
        )


def test_gdt_evidence_rejects_more_provider_frames_than_observations() -> None:
    with pytest.raises(
        GdtEvidenceValidationError,
        match="provider_frame_count_exceeded",
    ):
        validate_gdt_frame_evidence_batch(
            provider_frames=[_provider_frame(), _provider_frame()],
            observations=[_frame_observation()],
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
        )
