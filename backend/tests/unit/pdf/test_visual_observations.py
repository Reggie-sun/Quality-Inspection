from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from app.pdf.inventory import build_inventory
from app.pdf.coordinates import PageTransform
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import (
    MAX_AXIS_GAP_PT,
    MAX_CONTEXT_PAGE_AREA_RATIO,
    MAX_PATH_ITEM_EXTENT_PT,
    VisualObservationBlockingError,
    build_page_visual_observations,
    pack_visual_batches,
    reconstruct_visual_geometry_contexts,
)
from tests.helpers.symbol_fixture import NEGATIVE_FAMILIES, build_symbol_fixture


def _observation_signature(
    observations: tuple[VisualObservation, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            item.observation_id,
            item.page_index,
            item.bbox_pdf,
            item.bbox_normalized,
            item.geometry_sha256,
            item.associated_text_observation_ids,
        )
        for item in observations
    )


def _bbox_union(
    bboxes: tuple[tuple[float, float, float, float], ...],
) -> tuple[float, float, float, float]:
    return (
        min(item[0] for item in bboxes),
        min(item[1] for item in bboxes),
        max(item[2] for item in bboxes),
        max(item[3] for item in bboxes),
    )


def _gap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float]:
    return (
        max(0.0, left[0] - right[2], right[0] - left[2]),
        max(0.0, left[1] - right[3], right[1] - left[3]),
    )


def test_visual_observation_id_and_order_are_stable(tmp_path: Path) -> None:
    first_pdf, first_manifest = build_symbol_fixture(tmp_path / "first")
    second_pdf, second_manifest = build_symbol_fixture(tmp_path / "second")

    assert hashlib.sha256(first_pdf.read_bytes()).hexdigest() == hashlib.sha256(
        second_pdf.read_bytes()
    ).hexdigest()
    assert first_manifest == second_manifest
    assert first_manifest["page_boxes"] == [
        [0.0, 0.0, 612.0, 792.0],
        [0.0, 0.0, 612.0, 792.0],
    ]
    with pymupdf.open(first_pdf) as first_document, pymupdf.open(
        second_pdf
    ) as second_document:
        first_boxes = [
            [float(value) for value in tuple(page.rect)]
            for page in first_document
        ]
        second_boxes = [
            [float(value) for value in tuple(page.rect)]
            for page in second_document
        ]
    assert first_boxes == second_boxes == first_manifest["page_boxes"]

    first_pages = build_inventory(first_pdf)
    second_pages = build_inventory(second_pdf)
    assert [
        len(page.visual_observations) for page in first_pages
    ] == [10, 9]
    first = tuple(
        item
        for page in first_pages
        for item in page.visual_observations
    )
    second = tuple(
        item
        for page in second_pages
        for item in page.visual_observations
    )

    assert first
    assert _observation_signature(first) == _observation_signature(second)
    assert [item.observation_id for item in first] == sorted(
        (item.observation_id for item in first),
        key=lambda observation_id: next(
            (
                item.page_index,
                item.bbox_pdf[1],
                item.bbox_pdf[0],
                item.proposal_kind,
                item.observation_id,
            )
            for item in first
            if item.observation_id == observation_id
        ),
    )
    assert all(len(item.observation_id) == 24 for item in first)
    assert all(len(item.geometry_sha256) == 64 for item in first)

    positive_counts: dict[str, int] = {}
    negative_families: set[str] = set()
    negative_count = 0
    for page in first_manifest["pages"]:
        for label in page["labels"]:
            if label["symbol_kinds"] == ["frozen_negative"]:
                negative_count += 1
                negative_families.add(label["negative_family"])
            else:
                family = label["fixture_family"]
                positive_counts[family] = positive_counts.get(family, 0) + 1
    assert positive_counts == {
        "diameter": 4,
        "depth": 3,
        "counterbore": 2,
        "surface_roughness": 3,
        "gdt_parallelism": 1,
        "datum_reference": 2,
        "revision_marker": 2,
        "gdt_perpendicularity": 1,
        "gdt_flatness": 1,
    }
    assert negative_count == 12
    assert negative_families == set(NEGATIVE_FAMILIES)


def test_small_nearby_path_items_form_text_adjacent_context(
    tmp_path: Path,
) -> None:
    pdf_path, _manifest = build_symbol_fixture(tmp_path)
    pages = build_inventory(pdf_path)
    contexts = reconstruct_visual_geometry_contexts(pdf_path, pages)
    native_by_page = {
        page.page_index: {
            observation.observation_id: observation
            for observation in page.observations
            if observation.source_type == "native"
        }
        for page in pages
    }

    assert len(contexts) == sum(
        len(page.visual_observations) for page in pages
    )
    for context in contexts:
        page = pages[context.page_index]
        observation = next(
            item
            for item in page.visual_observations
            if item.observation_id == context.observation_id
        )
        native = native_by_page[context.page_index]
        associated_lines = [
            native[observation_id]
            for observation_id in observation.associated_text_observation_ids
            if native[observation_id].observation_level == "line"
        ]
        assert len(associated_lines) == 1
        line = associated_lines[0]
        expected_associated_ids = tuple(
            sorted(
                (
                    line.observation_id,
                    *(
                        item.observation_id
                        for item in page.observations
                        if item.source_type == "native"
                        and item.observation_level == "span"
                        and item.parent_region_id == line.observation_id
                    ),
                )
            )
        )
        assert (
            observation.associated_text_observation_ids
            == expected_associated_ids
        )
        assert context.path_bboxes
        for bbox in context.path_bboxes:
            assert bbox[2] - bbox[0] <= MAX_PATH_ITEM_EXTENT_PT
            assert bbox[3] - bbox[1] <= MAX_PATH_ITEM_EXTENT_PT
            gap_x, gap_y = _gap(context.line_bbox_pdf, bbox)
            assert gap_x <= MAX_AXIS_GAP_PT
            assert gap_y <= MAX_AXIS_GAP_PT
        union = _bbox_union((context.line_bbox_pdf, *context.path_bboxes))
        area = (union[2] - union[0]) * (union[3] - union[1])
        assert area <= page.width * page.height * MAX_CONTEXT_PAGE_AREA_RATIO

    transform = PageTransform(width=200.0, height=200.0, rotation=0, scale=1.0)
    line = TextObservation(
        observation_id="all-opcodes-line",
        source_type="native",
        observation_level="line",
        raw_text="all opcodes",
        normalized_text="all opcodes",
        page_index=0,
        bbox_pdf=(20.0, 20.0, 40.0, 30.0),
        bbox_normalized=(0.1, 0.1, 0.2, 0.15),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )
    all_opcodes = [
        (
            "l",
            pymupdf.Point(10.0, 20.0),
            pymupdf.Point(15.0, 25.0),
        ),
        (
            "c",
            pymupdf.Point(10.0, 20.0),
            pymupdf.Point(12.0, 18.0),
            pymupdf.Point(14.0, 28.0),
            pymupdf.Point(16.0, 25.0),
        ),
        ("re", pymupdf.Rect(12.0, 20.0, 18.0, 28.0), 1),
        (
            "qu",
            pymupdf.Quad(
                ((12.0, 20.0), (18.0, 20.0), (12.0, 28.0), (18.0, 28.0))
            ),
        ),
    ]
    opcode_observations, opcode_contexts = build_page_visual_observations(
        page_index=0,
        page_width=200.0,
        page_height=200.0,
        source_sha256="a" * 64,
        native_observations=(line,),
        drawings=[
            {
                "items": all_opcodes,
                "width": -0.0,
                "dashes": "\t[ ] \n0  ",
                "lineCap": (0.0, 1, 2),
                "lineJoin": 0.0,
                "color": (-0.0, 0.5),
                "fill": None,
                "closePath": False,
            }
        ],
        transform=transform,
    )
    assert len(opcode_observations) == len(opcode_contexts) == 1
    canonical_items = [
        json.loads(item)
        for item in opcode_contexts[0].canonical_path_items
    ]
    assert {item["opcode"] for item in canonical_items} == {"l", "c", "re", "qu"}
    assert all(item["style"]["width"] == "0.000" for item in canonical_items)
    assert all(item["style"]["dashes"] == "[ ] 0" for item in canonical_items)
    assert all(item["style"]["lineJoin"] == 0 for item in canonical_items)
    assert all(item["style"]["lineCap"] == [0, 1, 2] for item in canonical_items)
    assert all(
        item["style"]["color"] == ["0.000", "0.500"]
        for item in canonical_items
    )

    shared_lines = (
        replace(
            line,
            observation_id="shared-line-a",
            raw_text="line a",
            normalized_text="line a",
            bbox_pdf=(20.0, 20.0, 40.0, 30.0),
            bbox_normalized=(0.1, 0.1, 0.2, 0.15),
        ),
        replace(
            line,
            observation_id="shared-line-b",
            raw_text="line b",
            normalized_text="line b",
            bbox_pdf=(20.0, 32.0, 40.0, 42.0),
            bbox_normalized=(0.1, 0.16, 0.2, 0.21),
        ),
    )
    shared_observations, shared_contexts = build_page_visual_observations(
        page_index=0,
        page_width=200.0,
        page_height=200.0,
        source_sha256="b" * 64,
        native_observations=shared_lines,
        drawings=[
            {
                "items": [
                    (
                        "l",
                        pymupdf.Point(15.0, 29.0),
                        pymupdf.Point(18.0, 33.0),
                    )
                ],
                "width": 1.0,
                "dashes": "[] 0",
                "lineCap": 0,
                "lineJoin": 0.0,
                "color": (0.0,),
                "fill": None,
                "closePath": False,
            }
        ],
        transform=transform,
    )
    assert len(shared_observations) == len(shared_contexts) == 2
    assert {
        observation.associated_text_observation_ids
        for observation in shared_observations
    } == {("shared-line-a",), ("shared-line-b",)}
    assert len(
        {observation.geometry_sha256 for observation in shared_observations}
    ) == 1


def test_large_distant_or_page_geometry_is_rejected(tmp_path: Path) -> None:
    pdf_path, manifest = build_symbol_fixture(tmp_path)
    pages = build_inventory(pdf_path)
    observations = tuple(
        observation
        for page in pages
        for observation in page.visual_observations
    )

    negative_bboxes = [
        tuple(label["bbox_pdf"])
        for page in manifest["pages"]
        for label in page["labels"]
        if label["symbol_kinds"] == ["frozen_negative"]
    ]
    assert negative_bboxes
    for observation in observations:
        for negative_bbox in negative_bboxes:
            intersection = (
                max(observation.bbox_pdf[0], negative_bbox[0]),
                max(observation.bbox_pdf[1], negative_bbox[1]),
                min(observation.bbox_pdf[2], negative_bbox[2]),
                min(observation.bbox_pdf[3], negative_bbox[3]),
            )
            assert intersection[0] >= intersection[2] or intersection[1] >= intersection[3]

    oversized_line = next(
        observation
        for observation in pages[1].observations
        if observation.observation_level == "line"
        and observation.raw_text.startswith("MATERIAL STEEL")
    )
    assert not any(
        oversized_line.observation_id
        in observation.associated_text_observation_ids
        for observation in pages[1].visual_observations
    )

    transform = PageTransform(width=100.0, height=100.0, rotation=0, scale=1.0)
    line = TextObservation(
        observation_id="line",
        source_type="native",
        observation_level="line",
        raw_text="ordinary",
        normalized_text="ordinary",
        page_index=0,
        bbox_pdf=(10.0, 10.0, 90.0, 20.0),
        bbox_normalized=(0.1, 0.1, 0.9, 0.2),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )
    valid_style = {
        "width": 1.0,
        "dashes": "[] 0",
        "lineCap": (0, 0, 0),
        "lineJoin": 0.0,
        "color": (0.0,),
        "fill": None,
        "closePath": False,
    }
    oversized_drawings = [
        {
            **valid_style,
            "items": [
                ("l", pymupdf.Point(5.0, 5.0), pymupdf.Point(25.0, 25.0)),
                ("l", pymupdf.Point(75.0, 5.0), pymupdf.Point(95.0, 25.0)),
            ],
        }
    ]
    rejected, contexts = build_page_visual_observations(
        page_index=0,
        page_width=100.0,
        page_height=100.0,
        source_sha256="a" * 64,
        native_observations=(line,),
        drawings=oversized_drawings,
        transform=transform,
    )
    assert rejected == ()
    assert contexts == ()

    with pytest.raises(
        VisualObservationBlockingError,
        match="visual_geometry_unknown_opcode",
    ):
        build_page_visual_observations(
            page_index=0,
            page_width=100.0,
            page_height=100.0,
            source_sha256="a" * 64,
            native_observations=(line,),
            drawings=[{**valid_style, "items": [("z",)]}],
            transform=transform,
        )
    for invalid_line_join in (True, 0.5, math.nan, math.inf, -math.inf):
        with pytest.raises(
            VisualObservationBlockingError,
            match="visual_geometry_invalid_style",
        ):
            build_page_visual_observations(
                page_index=0,
                page_width=100.0,
                page_height=100.0,
                source_sha256="a" * 64,
                native_observations=(line,),
                drawings=[
                    {
                        **valid_style,
                        "lineJoin": invalid_line_join,
                        "items": [
                            (
                                "l",
                                pymupdf.Point(70.0, 70.0),
                                pymupdf.Point(80.0, 80.0),
                            )
                        ],
                    }
                ],
                transform=transform,
            )
    with pytest.raises(VisualObservationBlockingError) as nonfinite:
        build_page_visual_observations(
            page_index=0,
            page_width=100.0,
            page_height=100.0,
            source_sha256="a" * 64,
            native_observations=(line,),
            drawings=[
                {
                    **valid_style,
                    "items": [
                        (
                            "l",
                            pymupdf.Point(math.nan, 70.0),
                            pymupdf.Point(80.0, 80.0),
                        )
                    ],
                }
            ],
            transform=transform,
        )
    assert nonfinite.value.code == "visual_geometry_nonfinite"


def test_visual_bbox_round_trip_and_union(tmp_path: Path) -> None:
    pdf_path, _manifest = build_symbol_fixture(tmp_path)
    pages = build_inventory(pdf_path)
    contexts = reconstruct_visual_geometry_contexts(pdf_path, pages)
    observations = {
        item.observation_id: item
        for page in pages
        for item in page.visual_observations
    }

    for context in contexts:
        observation = observations[context.observation_id]
        expected_union = _bbox_union(
            (context.line_bbox_pdf, *context.path_bboxes)
        )
        assert observation.bbox_pdf == pytest.approx(expected_union)
        page = pages[context.page_index]
        assert observation.bbox_normalized == pytest.approx(
            (
                expected_union[0] / page.width,
                expected_union[1] / page.height,
                expected_union[2] / page.width,
                expected_union[3] / page.height,
            )
        )
        for point in (
            expected_union[:2],
            expected_union[2:],
        ):
            rendered = (
                page.pdf_to_render_matrix[0] * point[0]
                + page.pdf_to_render_matrix[2] * point[1]
                + page.pdf_to_render_matrix[4],
                page.pdf_to_render_matrix[1] * point[0]
                + page.pdf_to_render_matrix[3] * point[1]
                + page.pdf_to_render_matrix[5],
            )
            restored = (
                page.render_to_pdf_matrix[0] * rendered[0]
                + page.render_to_pdf_matrix[2] * rendered[1]
                + page.render_to_pdf_matrix[4],
                page.render_to_pdf_matrix[1] * rendered[0]
                + page.render_to_pdf_matrix[3] * rendered[1]
                + page.render_to_pdf_matrix[5],
            )
            assert restored == pytest.approx(point)

    first_page = pages[0]
    assert first_page.visual_observations
    missing_page = replace(
        first_page,
        visual_observations=first_page.visual_observations[1:],
    )
    with pytest.raises(VisualObservationBlockingError) as missing:
        reconstruct_visual_geometry_contexts(
            pdf_path,
            (missing_page, *pages[1:]),
        )
    assert missing.value.code == "visual_reconstruction_mismatch"

    mismatched_observation = replace(
        first_page.visual_observations[0],
        geometry_sha256="0" * 64,
    )
    mismatched_page = replace(
        first_page,
        visual_observations=(
            mismatched_observation,
            *first_page.visual_observations[1:],
        ),
    )
    with pytest.raises(VisualObservationBlockingError) as mismatch:
        reconstruct_visual_geometry_contexts(
            pdf_path,
            (mismatched_page, *pages[1:]),
        )
    assert mismatch.value.code == "visual_reconstruction_mismatch"

    original_observation = first_page.visual_observations[0]
    tampered_observations = (
        replace(
            original_observation,
            bbox_pdf=(
                original_observation.bbox_pdf[0] + 1.0,
                *original_observation.bbox_pdf[1:],
            ),
        ),
        replace(
            original_observation,
            bbox_normalized=(
                original_observation.bbox_normalized[0] + 0.001,
                *original_observation.bbox_normalized[1:],
            ),
        ),
        replace(
            original_observation,
            page_index=original_observation.page_index + 1,
        ),
        replace(
            original_observation,
            proposal_kind="tampered_proposal_kind",
        ),
        replace(
            original_observation,
            associated_text_observation_ids=(
                *original_observation.associated_text_observation_ids,
                "tampered-associated-id",
            ),
        ),
    )
    for tampered_observation in tampered_observations:
        tampered_page = replace(
            first_page,
            visual_observations=(
                tampered_observation,
                *first_page.visual_observations[1:],
            ),
        )
        with pytest.raises(VisualObservationBlockingError) as tampered:
            reconstruct_visual_geometry_contexts(
                pdf_path,
                (tampered_page, *pages[1:]),
            )
        assert tampered.value.code == "visual_reconstruction_mismatch"


def test_visual_batches_use_stable_first_fit(tmp_path: Path) -> None:
    first_pdf, _first_manifest = build_symbol_fixture(tmp_path / "first")
    second_pdf, _second_manifest = build_symbol_fixture(tmp_path / "second")
    first_pages = build_inventory(first_pdf)
    second_pages = build_inventory(second_pdf)

    first_batches = tuple(
        batch
        for page in first_pages
        for batch in pack_visual_batches(page, page.visual_observations)
    )
    second_batches = tuple(
        batch
        for page in second_pages
        for batch in pack_visual_batches(page, page.visual_observations)
    )

    assert first_batches == second_batches
    assert first_batches
    expected_order = [
        item.observation_id
        for page in first_pages
        for item in page.visual_observations
    ]
    assert [
        observation_id
        for batch in first_batches
        for observation_id in batch.observation_ids
    ] == expected_order
    assert [batch.call_index for batch in first_batches] == [
        index
        for page in first_pages
        for index, _batch in enumerate(
            pack_visual_batches(page, page.visual_observations)
        )
    ]
    for batch in first_batches:
        page = first_pages[batch.page_index]
        x0, y0, x1, y1 = batch.crop_bbox_pdf
        assert batch.pixel_width == math.ceil((x1 - x0) * 300.0 / 72.0)
        assert batch.pixel_height == math.ceil((y1 - y0) * 300.0 / 72.0)
        assert batch.pixel_width <= 1536
        assert batch.pixel_height <= 1536
        assert len(batch.observation_ids) <= 32
        assert (x1 - x0) * (y1 - y0) <= page.width * page.height * 0.075

    synthetic_page = replace(first_pages[0], width=200.0, height=200.0)

    def visual(
        observation_id: str,
        bbox_pdf: tuple[float, float, float, float],
    ) -> VisualObservation:
        return VisualObservation(
            observation_id=observation_id,
            source_type="visual",
            observation_level="annotation_context",
            page_index=synthetic_page.page_index,
            bbox_pdf=bbox_pdf,
            bbox_normalized=(
                bbox_pdf[0] / synthetic_page.width,
                bbox_pdf[1] / synthetic_page.height,
                bbox_pdf[2] / synthetic_page.width,
                bbox_pdf[3] / synthetic_page.height,
            ),
            proposal_kind="text_adjacent_vector_context",
            geometry_sha256=hashlib.sha256(
                observation_id.encode("ascii")
            ).hexdigest(),
            associated_text_observation_ids=(f"text-{observation_id}",),
        )

    observation_a = visual("A", (10.0, 10.0, 20.0, 20.0))
    observation_b = visual("B", (160.0, 160.0, 170.0, 170.0))
    observation_c = visual("C", (30.0, 10.0, 40.0, 20.0))
    synthetic_batches = pack_visual_batches(
        synthetic_page,
        (observation_a, observation_b, observation_c),
    )

    assert [
        batch.observation_ids for batch in synthetic_batches
    ] == [("A", "C"), ("B",)]
    assert [
        batch.crop_bbox_pdf for batch in synthetic_batches
    ] == [(4.0, 4.0, 46.0, 26.0), (154.0, 154.0, 176.0, 176.0)]
    assert [batch.call_index for batch in synthetic_batches] == [0, 1]

    oversized = visual("oversized", (0.0, 0.0, 200.0, 200.0))
    with pytest.raises(VisualObservationBlockingError) as error:
        pack_visual_batches(synthetic_page, (oversized,))
    assert error.value.code == "visual_crop_oversize"
