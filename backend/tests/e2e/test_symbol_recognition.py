from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.config import Settings
from app.db import engine
from app.main import app
from app.pdf.inventory import build_inventory
from app.processing import tasks
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.router import get_session, get_storage
from app.providers.base import VisionResult
from app.review.models import ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from tests.helpers.symbol_fixture import NEGATIVE_FAMILIES, build_symbol_fixture


_SYMBOL_KINDS_BY_TEXTS = {
    ("18",): ("diameter",),
    ("20",): ("diameter",),
    ("40",): ("diameter",),
    ("100",): ("diameter",),
    ("M6深12",): ("depth",),
    ("M8深8",): ("depth",),
    ("M10深16",): ("depth",),
    ("22 6",): ("counterbore", "depth", "diameter"),
    ("30 10",): ("counterbore", "depth", "diameter"),
    ("3.2",): ("surface_roughness",),
    ("1.6",): ("surface_roughness",),
    ("6.3",): ("surface_roughness",),
    ("0.1 A",): ("gdt_parallelism",),
    ("0.2 B",): ("gdt_perpendicularity",),
    ("0.05",): ("gdt_flatness",),
    ("A",): ("datum_reference",),
    ("C",): ("datum_reference",),
    ("1",): ("revision_marker",),
    ("2",): ("revision_marker",),
}
_OVERLAP_THRESHOLD = 0.5


class PassingPreflight:
    def check(self) -> None:
        return None


@dataclass
class DispatchRecorder:
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def __call__(
        self,
        project_id: str,
        source_ref: str,
        logical_task_key: str,
    ) -> None:
        self.calls.append((project_id, source_ref, logical_task_key))


class FrozenSymbolProvider:
    def __init__(self) -> None:
        self.factory_calls = 0
        self.symbol_calls = 0
        self.text_calls = 0
        self.symbol_recognition_modes: list[str] = []

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        assert set(request) == {
            "constraints",
            "detection_reporting_contract",
            "gdt_frame_contexts",
            "prompt_version",
            "response_schema",
            "schema_version",
            "symbol_kind_guide",
            "task",
            "visual_contexts",
            "visual_observation_ids",
        }
        assert request["prompt_version"] == "visual-symbol-prompt/4"
        contexts = {
            context["visual_observation_id"]: context
            for context in request["visual_contexts"]
        }
        assert set(contexts) == set(request["visual_observation_ids"])
        self.symbol_calls += 1
        detections = []
        for visual_id in request["visual_observation_ids"]:
            context = contexts[visual_id]
            line_texts = tuple(
                item["raw_text"]
                for item in context["associated_text_allowlist"]
                if item["observation_level"] == "line"
            )
            assert line_texts in _SYMBOL_KINDS_BY_TEXTS
            prompt_text_ids = tuple(
                item["observation_id"]
                for item in context["associated_text_allowlist"]
                if item["observation_level"] == "line"
            )
            detections.extend(
                {
                    "visual_observation_id": visual_id,
                    "symbol_kind": symbol_kind,
                    "bbox_normalized": context["context_bbox_normalized"],
                    "associated_text_observation_ids": list(prompt_text_ids),
                    "confidence_signal": 0.98,
                }
                for symbol_kind in _SYMBOL_KINDS_BY_TEXTS[line_texts]
            )
        gdt_frames = []
        tolerance_symbols = {
            "gdt_parallelism": "∥",
            "gdt_perpendicularity": "⊥",
            "gdt_flatness": "⏥",
        }
        for frame_context in request["gdt_frame_contexts"]:
            frame_text_ids = {
                item["observation_id"]
                for item in frame_context["associated_text_allowlist"]
                if item["observation_level"] == "line"
            }
            frame_texts = tuple(
                item["raw_text"]
                for item in frame_context["associated_text_allowlist"]
                if item["observation_level"] == "line"
            )
            frame_kinds = _SYMBOL_KINDS_BY_TEXTS.get(frame_texts, ())
            gdt_kind = next(
                kind for kind in frame_kinds if kind.startswith("gdt_")
            )
            value_and_datum = frame_texts[0].split()
            cells = frame_context["cells"]
            cell_evidence = [
                {
                    "cell_index": cells[0]["cell_index"],
                    "cell_role": "symbol",
                    "bbox_normalized": cells[0]["bbox_normalized"],
                    "raw_token": tolerance_symbols[gdt_kind],
                    "associated_text_observation_ids": list(frame_text_ids),
                    "confidence_signal": 0.98,
                },
                {
                    "cell_index": cells[1]["cell_index"],
                    "cell_role": "tolerance",
                    "bbox_normalized": cells[1]["bbox_normalized"],
                    "raw_token": value_and_datum[0],
                    "associated_text_observation_ids": list(frame_text_ids),
                    "confidence_signal": 0.98,
                },
            ]
            if len(cells) == 3:
                assert len(value_and_datum) == 2
                cell_evidence.append({
                    "cell_index": cells[2]["cell_index"],
                    "cell_role": "datum",
                    "bbox_normalized": cells[2]["bbox_normalized"],
                    "raw_token": value_and_datum[1],
                    "associated_text_observation_ids": list(frame_text_ids),
                    "confidence_signal": 0.98,
                })
            gdt_frames.append({
                "frame_observation_id": frame_context["frame_observation_id"],
                "frame_bbox_normalized": frame_context["frame_bbox_normalized"],
                "tolerance_type_signal": gdt_kind.removeprefix("gdt_"),
                "cells": cell_evidence,
                "confidence_signal": 0.98,
            })
        return VisionResult(
            request_id=f"fixture-symbol-{self.symbol_calls}",
            payload={
                "schema_version": "visual-symbol-review/3",
                "detections": detections,
                "gdt_frames": gdt_frames,
            },
            usage={},
        )

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        self.text_calls += 1
        expected_type = request["expected_type"]
        return VisionResult(
            request_id=f"fixture-text-{self.text_calls}",
            payload={
                "schema_version": "candidate-review/1",
                "raw_text": request["raw_text"],
                "item_type": expected_type or "linear_dimension",
                "normalized_text": (request["raw_text"] if expected_type else "?"),
                "requires_confirmation": True,
            },
            usage={},
        )


@dataclass(frozen=True)
class SymbolFlow:
    manifest: dict[str, Any]
    inventory: dict[str, Any]
    candidates: list[dict[str, Any]]
    coverage_entries: list[dict[str, Any]]
    working_items: list[dict[str, Any]]
    working_coverage_entries: list[dict[str, Any]]
    provider: FrozenSymbolProvider
    external_calls: int


@pytest.fixture
def database_connection() -> Iterator[Connection]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    try:
        yield connection
    finally:
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def task_session_factory(
    database_connection: Connection,
) -> Callable[[], Session]:
    def factory() -> Session:
        return Session(
            bind=database_connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

    return factory


def _fixture_provider(source: Path) -> FrozenSymbolProvider:
    pages = tuple(build_inventory(source))
    text_by_id = {
        observation.observation_id: observation
        for page in pages
        for observation in page.observations
    }
    for page in pages:
        for visual in page.visual_observations:
            lines = tuple(
                sorted(
                    (
                        text_by_id[text_id]
                        for text_id in visual.associated_text_observation_ids
                        if text_by_id[text_id].observation_level == "line"
                    ),
                    key=lambda item: (
                        item.page_index,
                        item.bbox_pdf[1],
                        item.bbox_pdf[0],
                        item.observation_id,
                    ),
                )
            )
            assert tuple(line.raw_text for line in lines) in _SYMBOL_KINDS_BY_TEXTS
    return FrozenSymbolProvider()


def _configure_task(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_factory: Callable[[], Session],
    storage_root: Path,
    provider: FrozenSymbolProvider,
) -> None:
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(
            storage_root=storage_root,
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="legacy_high_recall",
        ),
    )
    monkeypatch.setattr(
        tasks,
        "ProcessingPreflight",
        lambda *_args, **_kwargs: PassingPreflight(),
    )
    monkeypatch.setattr(tasks.Redis, "from_url", lambda *_args, **_kwargs: object())

    def forbidden_ocr_provider(_settings: Settings) -> object:
        raise AssertionError("vector fixture must not construct the OCR Provider")

    def vision_provider_factory(_settings: Settings) -> FrozenSymbolProvider:
        provider.factory_calls += 1
        provider.symbol_recognition_modes.append(
            _settings.symbol_recognition_mode
        )
        return provider

    monkeypatch.setattr(tasks, "OCR_PROVIDER_FACTORY", forbidden_ocr_provider)
    monkeypatch.setattr(
        tasks,
        "VISION_PROVIDER_FACTORY",
        vision_provider_factory,
    )


@pytest.fixture
def symbol_flow(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> Iterator[SymbolFlow]:
    source, manifest = build_symbol_fixture(tmp_path / "fixture")
    storage = LocalFileStorage(tmp_path / "storage")
    dispatch = DispatchRecorder()
    intake_session = task_session_factory()

    def override_session() -> Iterator[Session]:
        yield intake_session

    previous_overrides = dict(app.dependency_overrides)
    monkeypatch.setattr(inventory_project, "delay", dispatch)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                files={
                    "file": (
                        "symbol-fixture.pdf",
                        source.read_bytes(),
                        "application/pdf",
                    )
                },
            )
        assert response.status_code == 202
        project_id = response.json()["project_id"]
        assert dispatch.calls == [
            (
                project_id,
                f"asset://projects/{project_id}/source.pdf",
                f"product-process:{project_id}",
            )
        ]

        provider = _fixture_provider(source)
        _configure_task(
            monkeypatch,
            session_factory=task_session_factory,
            storage_root=storage.root,
            provider=provider,
        )
        external_calls = 0

        def block_network(*_args: object, **_kwargs: object) -> None:
            nonlocal external_calls
            external_calls += 1
            raise AssertionError("sanitized fixture attempted external network access")

        with (
            patch.object(socket, "socket", new=block_network),
            patch.object(socket, "create_connection", new=block_network),
            patch.object(socket, "getaddrinfo", new=block_network),
        ):
            result_ref = inventory_project.run(*dispatch.calls[0])

        verify = task_session_factory()
        try:
            project = verify.get(Project, project_id)
            raw = verify.scalar(
                select(AutomaticResult).where(AutomaticResult.project_id == project_id)
            )
            working = verify.scalar(
                select(ReviewWorkingCopy).where(
                    ReviewWorkingCopy.project_id == project_id
                )
            )
            assert project is not None
            assert raw is not None
            assert working is not None
            assert result_ref == f"automatic-result://{raw.id}"
            inventory = json.loads(storage.read_bytes(raw.inventory_ref))
            yield SymbolFlow(
                manifest=manifest,
                inventory=inventory,
                candidates=list(raw.candidates),
                coverage_entries=list(raw.coverage["entries"]),
                working_items=list(working.items),
                working_coverage_entries=list(working.coverage["entries"]),
                provider=provider,
                external_calls=external_calls,
            )
        finally:
            verify.close()
    finally:
        intake_session.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _overlap(left: list[float], right: list[float]) -> float:
    intersection = [
        max(left[0], right[0]),
        max(left[1], right[1]),
        min(left[2], right[2]),
        min(left[3], right[3]),
    ]
    denominator = min(_area(left), _area(right))
    return _area(intersection) / denominator if denominator > 0.0 else 0.0


def _source_index(
    inventory: dict[str, Any],
) -> dict[str, tuple[int, list[float], str]]:
    return {
        observation["observation_id"]: (
            page["page_index"],
            observation["bbox_pdf"],
            source_type,
        )
        for page in inventory["pages"]
        for source_type, observations in (
            ("text", page["observations"]),
            ("visual", page["visual_observations"]),
        )
        for observation in observations
    }


def _source_overlaps_label(
    source_ids: list[str],
    *,
    page_index: int,
    bbox: list[float],
    sources: dict[str, tuple[int, list[float], str]],
) -> bool:
    return any(
        source_id in sources
        and sources[source_id][0] == page_index
        and _overlap(sources[source_id][1], bbox) >= _OVERLAP_THRESHOLD
        for source_id in source_ids
    )


def _positive_labels(manifest: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (page["page_index"], label)
        for page in manifest["pages"]
        for label in page["labels"]
        if label["symbol_kinds"] != ["frozen_negative"]
    ]


def _negative_labels(manifest: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (page["page_index"], label)
        for page in manifest["pages"]
        for label in page["labels"]
        if label["symbol_kinds"] == ["frozen_negative"]
    ]


def test_symbol_fixture_positive_flow(symbol_flow: SymbolFlow) -> None:
    """E2E-01: all fixture positives survive upload, automatic and review."""
    sources = _source_index(symbol_flow.inventory)
    candidates_by_id = {
        candidate["candidate_id"]: candidate for candidate in symbol_flow.candidates
    }
    items_by_id = {item["item_id"]: item for item in symbol_flow.working_items}
    working_coverage_by_id = {
        entry["observation_id"]: entry for entry in symbol_flow.working_coverage_entries
    }
    positive_labels = _positive_labels(symbol_flow.manifest)
    comparisons: list[str] = []
    failures: list[str] = []
    matched_candidate_ids: set[str] = set()
    matched_visual_ids: set[str] = set()
    persisted_visual_ids = {
        source_id
        for source_id, (_page, _bbox, source_type) in sources.items()
        if source_type == "visual"
    }
    raw_visual_coverage_ids = [
        entry["observation_id"]
        for entry in symbol_flow.coverage_entries
        if entry["observation_id"] in persisted_visual_ids
    ]
    working_visual_coverage_ids = [
        entry["observation_id"]
        for entry in symbol_flow.working_coverage_entries
        if entry["observation_id"] in persisted_visual_ids
    ]

    assert len(positive_labels) == 19
    for page_index, label in positive_labels:
        matching_entries = [
            entry
            for entry in symbol_flow.coverage_entries
            if entry["observation_id"] in sources
            and sources[entry["observation_id"]][2] == "visual"
            and sources[entry["observation_id"]][0] == page_index
            and _overlap(
                sources[entry["observation_id"]][1],
                label["bbox_pdf"],
            )
            >= _OVERLAP_THRESHOLD
            and set(entry.get("advisor_review", {}).get("symbol_kinds", ()))
            == set(label["symbol_kinds"])
        ]
        if len(matching_entries) != 1:
            failures.append(f"{label['label_id']}: match_count={len(matching_entries)}")
            comparisons.append(label["label_id"])
            continue
        entry = matching_entries[0]
        if entry["observation_id"] in matched_visual_ids:
            failures.append(f"{label['label_id']}: visual observation reused")
        matched_visual_ids.add(entry["observation_id"])
        working_entry = working_coverage_by_id.get(entry["observation_id"])
        if working_entry is None:
            failures.append(f"{label['label_id']}: working coverage missing")
        elif (
            working_entry["disposition"] != entry["disposition"]
            or working_entry["candidate_id"] != entry["candidate_id"]
        ):
            failures.append(f"{label['label_id']}: working coverage mismatch")
        if entry["disposition"] != label["expected_disposition"]:
            failures.append(f"{label['label_id']}: disposition={entry['disposition']}")

        if label["expected_disposition"] == "candidate":
            candidate_id = entry["candidate_id"]
            if candidate_id not in candidates_by_id:
                failures.append(f"{label['label_id']}: candidate missing")
                comparisons.append(label["label_id"])
                continue
            if candidate_id not in items_by_id:
                failures.append(f"{label['label_id']}: working item missing")
                comparisons.append(label["label_id"])
                continue
            candidate = candidates_by_id[candidate_id]
            item = items_by_id[candidate_id]
            matched_candidate_ids.add(candidate_id)
            source_id = entry["observation_id"]
            if source_id not in candidate["source_location_ids"]:
                failures.append(
                    f"{label['label_id']}: candidate visual lineage missing"
                )
            if source_id not in item["source_location_ids"]:
                failures.append(f"{label['label_id']}: item visual lineage missing")
            projection = label["expected_projection"]
            if not (
                candidate["payload"].get("item_type") == projection
                or candidate["payload"].get("coarse_type") == projection
            ):
                failures.append(
                    f"{label['label_id']}: candidate projection="
                    f"{candidate['payload'].get('item_type') or candidate['payload'].get('coarse_type')}"
                )
            if not (
                item.get("item_type") == projection
                or item.get("coarse_type") == projection
            ):
                failures.append(
                    f"{label['label_id']}: item projection="
                    f"{item.get('item_type') or item.get('coarse_type')}"
                )
            if projection == "geometric_tolerance":
                expected_gdt = {
                    "gdt_parallelism": ("parallelism", "∥", "0.1", "A"),
                    "gdt_perpendicularity": ("perpendicularity", "⊥", "0.2", "B"),
                    "gdt_flatness": ("flatness", "⏥", "0.05", None),
                }[label["fixture_family"]]
                for payload, name in ((candidate["payload"], "candidate"), (item, "item")):
                    assert payload["item_type"] == "geometric_tolerance", name
                    assert payload["tolerance_type"] == expected_gdt[0], name
                    assert payload["tolerance_symbol"] == expected_gdt[1], name
                    assert payload["tolerance_value"] == expected_gdt[2], name
                    if expected_gdt[3] is None:
                        assert payload["datum_references"] == [], name
                    else:
                        assert [datum["datum"] for datum in payload["datum_references"]] == [expected_gdt[3]], name
        else:
            if entry["candidate_id"] is not None:
                failures.append(f"{label['label_id']}: unexpected candidate id")
            source_id = entry["observation_id"]
            if any(
                source_id in candidate["source_location_ids"]
                for candidate in symbol_flow.candidates
            ):
                failures.append(f"{label['label_id']}: source entered candidate")
            if any(
                source_id in item["source_location_ids"]
                for item in symbol_flow.working_items
            ):
                failures.append(f"{label['label_id']}: source entered item")
        comparisons.append(label["label_id"])

    assert len(comparisons) == len(set(comparisons)) == 19
    assert failures == []
    assert len(raw_visual_coverage_ids) == len(set(raw_visual_coverage_ids)) == 19
    assert (
        len(working_visual_coverage_ids) == len(set(working_visual_coverage_ids)) == 19
    )
    assert matched_visual_ids == persisted_visual_ids
    assert set(raw_visual_coverage_ids) == set(working_visual_coverage_ids)
    assert len(matched_candidate_ids) == 15
    assert matched_candidate_ids == set(candidates_by_id) == set(items_by_id)
    assert symbol_flow.external_calls == 0
    assert symbol_flow.provider.factory_calls == 1
    assert symbol_flow.provider.symbol_calls > 0


def test_symbol_fixture_negative_regions_do_not_create_items(
    symbol_flow: SymbolFlow,
) -> None:
    """E2E-02: every frozen negative remains present and produces no result."""
    sources = _source_index(symbol_flow.inventory)
    negative_labels = _negative_labels(symbol_flow.manifest)
    comparisons: dict[str, dict[str, list[str]]] = {}

    assert len(negative_labels) == 12
    assert {label["negative_family"] for _, label in negative_labels} == set(
        NEGATIVE_FAMILIES
    )
    for page_index, label in negative_labels:
        bbox = label["bbox_pdf"]
        visual_ids = [
            source_id
            for source_id, (source_page, source_bbox, source_type) in sources.items()
            if source_type == "visual"
            and source_page == page_index
            and _overlap(source_bbox, bbox) >= _OVERLAP_THRESHOLD
        ]
        candidate_ids = [
            candidate["candidate_id"]
            for candidate in symbol_flow.candidates
            if _source_overlaps_label(
                candidate["source_location_ids"],
                page_index=page_index,
                bbox=bbox,
                sources=sources,
            )
        ]
        semantic_coverage = [
            entry
            for entry in symbol_flow.coverage_entries
            if entry["disposition"] in {"reference_context", "non_inspection"}
            and _source_overlaps_label(
                [entry["observation_id"]],
                page_index=page_index,
                bbox=bbox,
                sources=sources,
            )
        ]
        expected_semantic_disposition = label["expected_disposition"]
        if expected_semantic_disposition in {
            "reference_context",
            "non_inspection",
        }:
            semantic_coverage_errors = (
                []
                if len(semantic_coverage) == 1
                and semantic_coverage[0]["disposition"]
                == expected_semantic_disposition
                else [
                    f"{entry['observation_id']}:{entry['disposition']}"
                    for entry in semantic_coverage
                ]
                or ["missing"]
            )
        else:
            semantic_coverage_errors = [
                f"{entry['observation_id']}:{entry['disposition']}"
                for entry in semantic_coverage
            ]
        item_ids = [
            item["item_id"]
            for item in symbol_flow.working_items
            if _source_overlaps_label(
                item["source_location_ids"],
                page_index=page_index,
                bbox=bbox,
                sources=sources,
            )
        ]
        comparisons[label["label_id"]] = {
            "visual_observations": visual_ids,
            "candidates": candidate_ids,
            "semantic_coverage": semantic_coverage_errors,
            "items": item_ids,
        }

    assert len(comparisons) == 12
    failures = {
        label_id: result
        for label_id, result in comparisons.items()
        if result["visual_observations"]
        or result["candidates"]
        or result["semantic_coverage"]
        or result["items"]
    }
    assert failures == {}
    assert symbol_flow.external_calls == 0


def test_frozen_default_and_explicit_legacy_mode_preserve_sealed_semantics(
    symbol_flow: SymbolFlow,
) -> None:
    """E2E-03: frozen legacy routing remains the default sealed flow."""
    assert Settings(qwen_model="qwen3-vl-plus").symbol_recognition_mode == (
        "legacy_high_recall"
    )
    assert symbol_flow.provider.symbol_recognition_modes == [
        "legacy_high_recall"
    ]
    assert symbol_flow.provider.factory_calls == 1
    assert symbol_flow.provider.symbol_calls > 0
    assert symbol_flow.external_calls == 0
    assert len(_positive_labels(symbol_flow.manifest)) == 19
    assert len(_negative_labels(symbol_flow.manifest)) == 12
    assert len(symbol_flow.candidates) == len(symbol_flow.working_items) == 15
    assert len(symbol_flow.coverage_entries) == len(
        symbol_flow.working_coverage_entries
    )
