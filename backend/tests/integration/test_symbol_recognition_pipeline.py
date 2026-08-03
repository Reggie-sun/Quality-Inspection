from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import get_args

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

import app.candidates.advisor as advisor_module
import app.candidates.symbol_escalation_planner as escalation_planner_module
from app.candidates.advisor import (
    CandidateAdvisor,
    CandidateAdvisorFailure,
    VisualEvidenceContext,
    VisualExecutionIdentity,
)
from app.candidates.complex_fallback import CoarseType
from app.candidates.coverage import CoverageEntry
from app.candidates.local_symbol_resolution import LocalResolution
from app.candidates.models import (
    AutomaticResult,
    SymbolEscalationAttemptEventRecord,
    SymbolEscalationOutcomeRecord,
    SymbolRoutingDecisionRecord,
    VisualSymbolCacheEntryRecord,
)
from app.candidates.routing_evidence import routing_decision_group_sha256
from app.candidates.schemas import CandidateType
from app.candidates.symbol_cache import (
    SymbolCacheProvenance,
    build_cache_entry,
)
from app.candidates.symbol_escalation_contracts import EscalationBatch
from app.candidates.symbol_escalation_planner import (
    EscalationPlan,
    EscalationRequest,
    plan_symbol_escalation_batches,
)
from app.candidates.symbol_routing import RoutingDecision, route_visual_observation
from app.candidates.symbol_review import (
    VisualReviewDecision,
    plan_visual_batches,
)
from app.config import Settings
from app.db import SessionLocal, engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.pdf.inventory import build_inventory
from app.pdf.schemas import PageInventory, TextObservation, VisualObservation
from app.pdf.visual_observations import (
    VisualObservationBlockingError,
    reconstruct_visual_geometry_contexts,
)
from app.processing import tasks
from app.processing.automatic_result import (
    CandidateSnapshot,
    CoverageBlocking,
    candidate_snapshot_from_inventory,
)
from app.processing.pipeline import InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.service import ProjectIntakeService
from app.projects.state import ProjectState
from app.providers.base import (
    ClassifiedProviderFailure,
    ProviderFailureFact,
    VisionResult,
)
from app.providers.qwen_vl import (
    VisualSymbolProviderError,
    canonicalize_visual_png,
)
from app.providers.usage_ledger import ProviderUsageLedger, ReservationPermit
from tests.support.provider_cycle import CYCLE_ID, create_cycle_authorization
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewNotFound, ReviewService
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile
from tests.helpers.symbol_fixture import build_symbol_fixture


_SYMBOL_KINDS_BY_TEXT = {
    "18": ("diameter",),
    "20": ("diameter",),
    "40": ("diameter",),
    "100": ("diameter",),
    "M6深12": ("depth",),
    "M8深8": ("depth",),
    "M10深16": ("depth",),
    "22 6": ("counterbore", "depth", "diameter"),
    "30 10": ("counterbore", "depth", "diameter"),
    "3.2": ("surface_roughness",),
    "1.6": ("surface_roughness",),
    "6.3": ("surface_roughness",),
    "0.1 A": ("gdt_parallelism",),
    "0.2 B": ("gdt_perpendicularity",),
    "0.05": ("gdt_flatness",),
    "A": ("datum_reference",),
    "C": ("datum_reference",),
    "1": ("revision_marker",),
    "2": ("revision_marker",),
}


class PassingPreflight:
    def check(self) -> None:
        return None


class NoSchemaRetryCoordinator:
    @staticmethod
    def authorize_schema_retry(*_args: object) -> bool:
        return False


@dataclass(frozen=True)
class SupportedPageStub:
    support_level: str = "supported"

    def to_dict(self) -> dict[str, str]:
        return {"support_level": self.support_level}


class FixtureVisionProvider:
    def __init__(
        self,
        visual_inputs: dict[
            str,
            tuple[
                tuple[str, ...],
                tuple[str, ...],
                tuple[float, float, float, float],
            ],
        ],
        *,
        detect_symbols: bool = True,
    ) -> None:
        self._visual_inputs = visual_inputs
        self._detect_symbols = detect_symbols
        self.factory_calls = 0
        self.symbol_calls = 0
        self.text_calls = 0
        self.symbol_observation_ids: list[tuple[str, ...]] = []

    @property
    def total_calls(self) -> int:
        return self.symbol_calls + self.text_calls

    @property
    def visual_ids(self) -> set[str]:
        return set(self._visual_inputs)

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        self.symbol_calls += 1
        self.symbol_observation_ids.append(
            tuple(request["visual_observation_ids"])
        )
        detections = []
        if self._detect_symbols:
            for visual_id in request["visual_observation_ids"]:
                symbol_kinds, text_ids, normalized_bbox = self._visual_inputs[
                    visual_id
                ]
                for symbol_kind in symbol_kinds:
                    detections.append(
                        {
                            "visual_observation_id": visual_id,
                            "symbol_kind": symbol_kind,
                            "bbox_normalized": list(normalized_bbox),
                            "associated_text_observation_ids": list(text_ids),
                            "confidence_signal": 0.98,
                        }
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
            frame_kinds = _SYMBOL_KINDS_BY_TEXT.get(frame_texts[0], ())
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
            request_id=f"fixture-visual-{self.symbol_calls}",
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
                "normalized_text": request["raw_text"] if expected_type else "?",
                "requires_confirmation": True,
            },
            usage={},
        )


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
def db_session(database_connection: Connection) -> Iterator[Session]:
    session = Session(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()


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


@pytest.fixture
def committed_db_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def _store_project_source(
    session: Session,
    storage: LocalFileStorage,
    payload: bytes,
    *,
    recognition_mode: str = "legacy_high_recall",
    recognition_router_version: str = "legacy",
) -> tuple[Project, StoredFile]:
    project = Project(
        id=uuid.uuid4(),
        state=ProjectState.PROCESSING,
        recognition_mode=recognition_mode,
        recognition_router_version=recognition_router_version,
    )
    stored = storage.write_verified(
        f"projects/{project.id}/source.pdf",
        payload,
        sha256(payload).hexdigest(),
    )
    source_file = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    session.add_all([project, source_file])
    session.commit()
    return project, source_file


def _fixture_provider(
    source: Path,
    *,
    detect_symbols: bool = True,
) -> FixtureVisionProvider:
    pages = build_inventory(source)
    snapshot = candidate_snapshot_from_inventory(pages)
    text_by_id = {
        observation.observation_id: observation
        for page in pages
        for observation in page.observations
    }
    visual_by_id = {
        observation.observation_id: observation
        for page in pages
        for observation in page.visual_observations
    }
    visual_inputs: dict[
        str,
        tuple[
            tuple[str, ...],
            tuple[str, ...],
            tuple[float, float, float, float],
        ],
    ] = {}
    for page_batches in plan_visual_batches(pages, snapshot):
        for batch in page_batches:
            x0, y0, x1, y1 = batch.crop_bbox_pdf
            width = x1 - x0
            height = y1 - y0
            for visual_id in batch.observation_ids:
                visual = visual_by_id[visual_id]
                line = next(
                    text_by_id[text_id]
                    for text_id in visual.associated_text_observation_ids
                    if text_by_id[text_id].observation_level == "line"
                )
                bbox = visual.bbox_pdf
                normalized_bbox = (
                    max(0.0, (bbox[0] - x0) / width),
                    max(0.0, (bbox[1] - y0) / height),
                    min(1.0, (bbox[2] - x0) / width),
                    min(1.0, (bbox[3] - y0) / height),
                )
                visual_inputs[visual_id] = (
                    _SYMBOL_KINDS_BY_TEXT[line.raw_text],
                    (line.observation_id,),
                    normalized_bbox,
                )
    return FixtureVisionProvider(
        visual_inputs,
        detect_symbols=detect_symbols,
    )


def _configure_task(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_factory: Callable[[], Session],
    storage_root: Path,
    provider: FixtureVisionProvider,
) -> None:
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(
            storage_root=storage_root,
            qwen_model="qwen3-vl-plus",
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

    monkeypatch.setattr(tasks, "OCR_PROVIDER_FACTORY", forbidden_ocr_provider)
    def vision_provider_factory(_settings: Settings) -> FixtureVisionProvider:
        provider.factory_calls += 1
        return provider

    monkeypatch.setattr(tasks, "VISION_PROVIDER_FACTORY", vision_provider_factory)


def _visual_review(
    symbol_kinds: list[str],
    rejection_code: str | None,
) -> dict[str, object]:
    return {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/3",
        "symbol_kinds": symbol_kinds,
        "rejection_code": rejection_code,
        "confidence_signal": (
            None if rejection_code == "visual_no_detection" else 0.98
        ),
    }


def _snapshot(
    *,
    candidates: tuple[dict[str, object], ...],
    entries: tuple[CoverageEntry, ...],
) -> CandidateSnapshot:
    identities = tuple(entry.observation_id for entry in entries)
    return CandidateSnapshot(
        candidates=candidates,
        coverage_entries=entries,
        expected_observation_ids=identities,
        duplicate_relations=(),
        required_visual_observation_ids=identities,
    )


def _persist_snapshot(
    session: Session,
    storage: LocalFileStorage,
    snapshot: CandidateSnapshot,
) -> tuple[Project, AutomaticResult, ReviewWorkingCopy]:
    project, source = _store_project_source(
        session,
        storage,
        b"fixture-pdf",
        recognition_mode=snapshot.recognition_mode,
        recognition_router_version=snapshot.router_version,
    )
    result_ref = InventoryPipeline(
        session,
        storage,
        PassingPreflight(),
        inventory_builder=lambda _path: (SupportedPageStub(),),
        candidate_snapshot_builder=lambda _pages: snapshot,
    ).run(
        str(project.id),
        source.resource_ref,
        f"product-process:{project.id}",
    )
    raw = session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert raw is not None
    assert result_ref == f"automatic-result://{raw.id}"
    working = ReviewService(session).create_from_raw(raw.id)
    return project, raw, working


def _fixture_task(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> tuple[
    Project,
    FixtureVisionProvider,
    str,
    set[str],
]:
    source_path, _manifest = build_symbol_fixture(tmp_path / "fixture")
    provider = _fixture_provider(source_path)
    visual_ids = provider.visual_ids
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _store_project_source(
        setup,
        storage,
        source_path.read_bytes(),
    )
    setup.close()
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        provider=provider,
    )
    result_ref = inventory_project.run(
        str(project.id),
        source.resource_ref,
        f"product-process:{project.id}",
    )
    return project, provider, result_ref, visual_ids


def _bounded_symbol_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, tuple[PageInventory, ...], CandidateSnapshot]:
    source, _manifest = build_symbol_fixture(tmp_path / "bounded-fixture")
    original_pages = tuple(build_inventory(source))
    text_by_id = {
        observation.observation_id: observation
        for page in original_pages
        for observation in page.observations
    }
    preferred_ids = [
        visual.observation_id
        for page in original_pages
        for visual in page.visual_observations
        if any(
            text_by_id[text_id].raw_text in {"18", "20"}
            and text_by_id[text_id].observation_level == "line"
            for text_id in visual.associated_text_observation_ids
        )
    ]
    selected_ids = set(preferred_ids[:2])
    assert len(selected_ids) == 2
    contexts = tuple(
        context
        for context in reconstruct_visual_geometry_contexts(
            source,
            original_pages,
        )
        if context.observation_id in selected_ids
    )
    pages = tuple(
        replace(
            page,
            visual_observations=tuple(
                visual
                for visual in page.visual_observations
                if visual.observation_id in selected_ids
            ),
        )
        for page in original_pages
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _path, _pages: contexts,
    )
    return source, pages, candidate_snapshot_from_inventory(pages)


def _eight_admitted_symbol_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, tuple[PageInventory, ...], CandidateSnapshot]:
    source = tmp_path / "eight-admitted-fixture.pdf"
    document = pymupdf.open()
    for _page_index in range(2):
        page = document.new_page(width=240, height=180)
        page.insert_text((48, 24), "10")
        page.draw_line((34, 14), (42, 14), color=(0, 0, 0), width=1)
    document.save(source)
    document.close()
    original_pages = tuple(build_inventory(source))
    original_snapshot = candidate_snapshot_from_inventory(original_pages)
    original_contexts = reconstruct_visual_geometry_contexts(
        source,
        original_pages,
    )
    assert len(original_contexts) == 2
    visuals = tuple(
        replace(
            original_pages[index // 4].visual_observations[0],
            observation_id=f"fixture-visual-{index}",
            bbox_pdf=(
                8.0 + (index % 4) * 56.0,
                8.0,
                28.0 + (index % 4) * 56.0,
                28.0,
            ),
            bbox_normalized=(
                (8.0 + (index % 4) * 56.0) / 240.0,
                8.0 / 180.0,
                (28.0 + (index % 4) * 56.0) / 240.0,
                28.0 / 180.0,
            ),
            geometry_sha256=sha256(
                f"fixture-visual-{index}".encode()
            ).hexdigest(),
        )
        for index in range(8)
    )
    pages = tuple(
        replace(
            original_pages[page_index],
            visual_observations=visuals[
                page_index * 4:(page_index + 1) * 4
            ],
        )
        for page_index in range(2)
    )
    original_visual_ids = {
        page.visual_observations[0].observation_id
        for page in original_pages
    }
    original_visual_coverage = {
        entry.observation_id: entry
        for entry in original_snapshot.coverage_entries
        if entry.observation_id in original_visual_ids
    }
    snapshot = replace(
        original_snapshot,
        coverage_entries=(
            *(
                entry
                for entry in original_snapshot.coverage_entries
                if entry.observation_id not in original_visual_ids
            ),
            *(
                replace(
                    original_visual_coverage[
                        original_pages[visual.page_index]
                        .visual_observations[0]
                        .observation_id
                    ],
                    observation_id=visual.observation_id,
                    source_location_id=visual.observation_id,
                    coordinates=visual.bbox_pdf,
                )
                for visual in visuals
            ),
        ),
        expected_observation_ids=(
            *(
                identity
                for identity in original_snapshot.expected_observation_ids
                if identity not in original_visual_ids
            ),
            *(visual.observation_id for visual in visuals),
        ),
        required_visual_observation_ids=tuple(
            visual.observation_id for visual in visuals
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _path, _pages: tuple(
            replace(
                original_contexts[visual.page_index],
                observation_id=visual.observation_id,
                geometry_sha256=visual.geometry_sha256,
            )
            for visual in visuals
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **_kwargs: (),
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        lambda **kwargs: LocalResolution(
            visual_observation_id=kwargs["observation"].observation_id,
            family_hypotheses=(),
            resolved_family=None,
            reason_codes=("unknown_symbol_pattern",),
            projection=None,
        ),
    )
    return source, pages, snapshot


@dataclass(frozen=True)
class PartialMatrixInput:
    source: Path
    pages: tuple[PageInventory, ...]
    snapshot: CandidateSnapshot
    local_visual: VisualObservation
    cache_visual: VisualObservation
    vlm_visual: VisualObservation
    failed_visual: VisualObservation
    decisions: dict[str, RoutingDecision]
    plan: EscalationPlan


def _partial_matrix_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> PartialMatrixInput:
    source, _manifest = build_symbol_fixture(tmp_path / "partial-matrix")
    original_pages = tuple(build_inventory(source))
    original_snapshot = candidate_snapshot_from_inventory(original_pages)
    legacy_batches = plan_visual_batches(original_pages, original_snapshot)
    selected_ids = (
        legacy_batches[0][0].observation_ids[0],
        legacy_batches[0][1].observation_ids[0],
        legacy_batches[1][0].observation_ids[0],
        legacy_batches[1][-1].observation_ids[0],
    )
    selected = set(selected_ids)
    assert len(selected) == 4
    contexts = tuple(
        context
        for context in reconstruct_visual_geometry_contexts(
            source,
            original_pages,
        )
        if context.observation_id in selected
    )
    pages = tuple(
        replace(
            page,
            visual_observations=tuple(
                visual
                for visual in page.visual_observations
                if visual.observation_id in selected
            ),
        )
        for page in original_pages
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _path, _pages: contexts,
    )
    visuals = {
        visual.observation_id: visual
        for page in pages
        for visual in page.visual_observations
    }
    local_visual = visuals[selected_ids[0]]
    local_projection = VisualReviewDecision(
        observation_id=local_visual.observation_id,
        disposition="non_inspection",
        source_location_ids=(local_visual.observation_id,),
        coordinates=local_visual.bbox_pdf,
        candidate_id=None,
        existing_candidate_index=None,
        candidate_envelope=None,
        requires_confirmation=True,
        symbol_kinds=("revision_marker",),
        rejection_code=None,
    )

    def resolve(**kwargs: object) -> LocalResolution:
        observation = kwargs["observation"]
        assert isinstance(observation, VisualObservation)
        if observation.observation_id == local_visual.observation_id:
            return LocalResolution(
                visual_observation_id=observation.observation_id,
                family_hypotheses=("revision_marker",),
                resolved_family="revision_marker",
                reason_codes=(
                    "deterministic_geometry_complete",
                    "local_projection_complete",
                ),
                projection=local_projection,
            )
        return LocalResolution(
            visual_observation_id=observation.observation_id,
            family_hypotheses=(),
            resolved_family=None,
            reason_codes=("unknown_symbol_pattern",),
            projection=None,
        )

    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **kwargs: (
            ("revision_marker",)
            if kwargs["observation"].observation_id
            == local_visual.observation_id
            else ()
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        resolve,
    )
    decisions: dict[str, RoutingDecision] = {}
    requests: list[EscalationRequest] = []
    for visual in visuals.values():
        resolution = resolve(observation=visual)
        decision = route_visual_observation(resolution)
        decisions[visual.observation_id] = decision
        if decision.disposition == "escalate":
            requests.append(
                EscalationRequest(
                    decision=decision,
                    observation=visual,
                    local_resolution=resolution,
                    projected_wall_seconds=10.0,
                )
            )
    plan = plan_symbol_escalation_batches(
        requests,
        actual_call_capacity_by_page={
            page.page_index: 16 for page in pages
        },
    )
    assert plan.denied == ()
    assert [batch.observation_ids for batch in plan.batches] == [
        (selected_ids[1],),
        (selected_ids[2],),
        (selected_ids[3],),
    ]
    return PartialMatrixInput(
        source=source,
        pages=pages,
        snapshot=candidate_snapshot_from_inventory(pages),
        local_visual=local_visual,
        cache_visual=visuals[selected_ids[1]],
        vlm_visual=visuals[selected_ids[2]],
        failed_visual=visuals[selected_ids[3]],
        decisions=decisions,
        plan=plan,
    )


def _execution_input(
    matrix: PartialMatrixInput,
    batch: EscalationBatch,
) -> tuple[
    bytes,
    tuple[float, float, float, float],
    tuple[VisualObservation, ...],
    dict[str, TextObservation],
    VisualExecutionIdentity,
]:
    page_inventory = next(
        page for page in matrix.pages if page.page_index == batch.page_index
    )
    visuals = {
        visual.observation_id: visual
        for page in matrix.pages
        for visual in page.visual_observations
    }
    batch_visuals = tuple(
        visuals[observation_id]
        for observation_id in batch.observation_ids
    )
    packed = advisor_module.pack_visual_batches(
        page_inventory,
        batch_visuals,
    )
    assert len(packed) == 1
    crop_bbox_pdf = packed[0].crop_bbox_pdf
    with pymupdf.open(matrix.source) as document:
        crop_png = advisor_module._render_visual_crop(
            document[batch.page_index],
            crop_bbox_pdf,
        )
    canonical_crop = canonicalize_visual_png(crop_png)
    execution_identity = VisualExecutionIdentity(
        page_index=batch.page_index,
        content_sha256=batch.content_sha256,
        lineage_sha256=batch.lineage_sha256,
        budget_sha256=batch.budget_sha256,
        observation_member_bindings=batch.observation_member_bindings,
        crop_sha256=sha256(canonical_crop).hexdigest(),
        member_content_sha256s=batch.member_content_sha256s,
    )
    texts = {
        observation.observation_id: observation
        for page in matrix.pages
        for observation in page.observations
    }
    return (
        crop_png,
        crop_bbox_pdf,
        batch_visuals,
        texts,
        execution_identity,
    )


def _record_matrix_decisions(
    advisor: CandidateAdvisor,
    matrix: PartialMatrixInput,
) -> dict[str, str]:
    group_by_observation = {
        observation_id: batch.content_sha256
        for batch in matrix.plan.batches
        for observation_id in batch.observation_ids
    }
    member_index_by_observation = {
        observation_id: member_index
        for batch in matrix.plan.batches
        for member_index, observation_id in enumerate(
            batch.observation_ids
        )
    }
    return advisor._record_routing_decisions(
        decisions=tuple(matrix.decisions.values()),
        escalation_group_by_observation=group_by_observation,
        escalation_group_member_index_by_observation=(
            member_index_by_observation
        ),
    )


def _seed_matrix_cache(
    advisor: CandidateAdvisor,
    matrix: PartialMatrixInput,
) -> dict[str, str]:
    decision_hashes = _record_matrix_decisions(advisor, matrix)
    batch = matrix.plan.batches[0]
    (
        crop_png,
        crop_bbox_pdf,
        batch_visuals,
        texts,
        execution_identity,
    ) = _execution_input(matrix, batch)
    cache_provider = _fixture_provider(matrix.source)
    outcome = advisor._visual_review_result(
        provider=cache_provider,
        crop_png=crop_png,
        crop_bbox_pdf=crop_bbox_pdf,
        source_sha256=sha256(matrix.source.read_bytes()).hexdigest(),
        visual_observations=batch_visuals,
        text_observations=texts,
        model="qwen3-vl-plus",
        allow_schema_retry=False,
        execution_identity=execution_identity,
        legacy_cache_enabled=False,
        evidence_context=VisualEvidenceContext(
            escalation_group_id=batch.content_sha256,
            routing_decision_sha256=routing_decision_group_sha256(
                tuple(
                    decision_hashes[observation_id]
                    for observation_id in batch.observation_ids
                )
            ),
        ),
        production_retry_coordinator=NoSchemaRetryCoordinator(),
    )
    assert outcome.cache_hit is False
    assert cache_provider.symbol_observation_ids == [
        (matrix.cache_visual.observation_id,)
    ]
    return decision_hashes


def test_mixed_local_and_escalated_preserve_exact_source_and_coverage(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    tmp_path: Path,
) -> None:
    source, pages, initial = _bounded_symbol_input(
        tmp_path,
        monkeypatch,
    )
    visuals = tuple(
        visual
        for page in pages
        for visual in page.visual_observations
    )
    local_visual, escalated_visual = visuals
    local_projection = VisualReviewDecision(
        observation_id=local_visual.observation_id,
        disposition="non_inspection",
        source_location_ids=(local_visual.observation_id,),
        coordinates=local_visual.bbox_pdf,
        candidate_id=None,
        existing_candidate_index=None,
        candidate_envelope=None,
        requires_confirmation=True,
        symbol_kinds=("revision_marker",),
        rejection_code=None,
    )

    def local_resolution(**kwargs: object) -> LocalResolution:
        observation = kwargs["observation"]
        if observation.observation_id == local_visual.observation_id:
            return LocalResolution(
                visual_observation_id=observation.observation_id,
                family_hypotheses=("revision_marker",),
                resolved_family="revision_marker",
                reason_codes=(
                    "deterministic_geometry_complete",
                    "local_projection_complete",
                ),
                projection=local_projection,
            )
        return LocalResolution(
            visual_observation_id=observation.observation_id,
            family_hypotheses=(),
            resolved_family=None,
            reason_codes=("unknown_symbol_pattern",),
            projection=None,
        )

    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **kwargs: (
            ("revision_marker",)
            if kwargs["observation"].observation_id
            == local_visual.observation_id
            else ()
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        local_resolution,
    )
    provider = _fixture_provider(source, detect_symbols=False)
    pipeline_storage = LocalFileStorage(tmp_path / "pipeline-storage")
    project, source_file = _store_project_source(
        db_session,
        pipeline_storage,
        b"fixture-pdf",
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )

    reviewed = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "provider-storage"),
        project_id=str(project.id),
        provider_factory=lambda _settings: provider,
    ).review(source, pages, initial)

    assert {
        identity
        for batch_ids in provider.symbol_observation_ids
        for identity in batch_ids
    } == {escalated_visual.observation_id}
    assert sum(
        identity == escalated_visual.observation_id
        for batch_ids in provider.symbol_observation_ids
        for identity in batch_ids
    ) == 1
    coverage_by_id = {
        entry.observation_id: entry
        for entry in reviewed.coverage_entries
    }
    assert coverage_by_id[
        local_visual.observation_id
    ].source_location_id == local_visual.observation_id
    assert coverage_by_id[
        local_visual.observation_id
    ].disposition == "non_inspection"
    local_review = coverage_by_id[
        local_visual.observation_id
    ].advisor_review
    assert local_review is not None
    assert local_review["confidence_signal"] is None
    local_evidence = local_review["local_resolution_evidence"]
    assert isinstance(local_evidence, dict)
    assert local_evidence["schema_version"] == "symbol-routing-decision/1"
    assert local_evidence["router_version"] == "symbol-uncertainty-router/1"
    assert local_evidence["reason_codes"] == [
        "deterministic_geometry_complete",
        "local_projection_complete",
    ]
    assert isinstance(local_evidence["input_sha256"], str)
    assert len(local_evidence["input_sha256"]) == 64
    assert coverage_by_id[
        escalated_visual.observation_id
    ].source_location_id == escalated_visual.observation_id
    assert coverage_by_id[
        escalated_visual.observation_id
    ].advisor_review == _visual_review([], "visual_no_detection")
    assert initial == candidate_snapshot_from_inventory(pages)
    result_ref = InventoryPipeline(
        db_session,
        pipeline_storage,
        PassingPreflight(),
        inventory_builder=lambda _path: (SupportedPageStub(),),
        candidate_snapshot_builder=lambda _pages: reviewed,
    ).run(
        str(project.id),
        source_file.resource_ref,
        f"product-process:{project.id}",
    )
    raw = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert raw is not None
    assert result_ref == f"automatic-result://{raw.id}"
    assert raw.coverage["blocking_count"] == 0
    assert raw.coverage["coverage_checked"] is True


@pytest.mark.parametrize(
    ("failure_family", "expected_failure_stage"),
    (
        ("timeout", "provider_timeout"),
        ("transport", "provider_transport_failure"),
        ("schema", "provider_schema_invalid"),
    ),
)
def test_one_localized_provider_failure_preserves_every_sibling_as_partial(
    failure_family: str,
    expected_failure_stage: str,
    monkeypatch: pytest.MonkeyPatch,
    committed_db_session: Session,
    tmp_path: Path,
) -> None:
    """PRT-5 retains siblings and requirement evidence around one failed ROI."""
    matrix = _partial_matrix_input(tmp_path, monkeypatch)
    requirement = {
        "requirement_id": "prt5-localized-requirement",
        "ordinal": 1,
        "raw_text": "局部失败仍需保留技术要求",
        "normalized_text": "局部失败仍需保留技术要求",
        "source_location_ids": ["technical-requirement-source"],
        "page_index": 0,
        "coordinates": [[10.0, 10.0, 20.0, 20.0]],
        "category": "ambiguous",
        "subtype": "ambiguous",
        "parsed_parameters": {},
        "match_outcome": "unresolved",
        "matched_candidate_ids": [],
        "generated_candidate_id": None,
        "rule_id": "technical-requirement/ambiguous",
        "rule_version": "technical-requirement/1",
        "review_required": True,
        "sip_suggestion": {
            "inspection_item": None,
            "inspection_standard": None,
            "key_dimension": None,
            "source_page": 1,
            "remarks": "需人工确认",
        },
    }
    matrix = replace(
        matrix,
        snapshot=replace(
            matrix.snapshot,
            technical_requirements=(requirement,),
        ),
    )
    storage = LocalFileStorage(tmp_path / f"partial-{failure_family}")
    db_session = committed_db_session
    project, source_file = _store_project_source(
        db_session,
        storage,
        matrix.source.read_bytes(),
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )
    successful = _fixture_provider(matrix.source)

    class OneLocalizedFailureProvider:
        def __init__(self) -> None:
            self.symbol_observation_ids: list[tuple[str, ...]] = []

        def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
            request = json.loads(prompt)
            observation_ids = tuple(request["visual_observation_ids"])
            self.symbol_observation_ids.append(observation_ids)
            assert matrix.cache_visual.observation_id not in observation_ids
            assert matrix.local_visual.observation_id not in observation_ids
            if matrix.failed_visual.observation_id in observation_ids:
                if failure_family == "timeout":
                    raise ClassifiedProviderFailure(
                        ProviderFailureFact(
                            category="timeout",
                            origin="sdk_timeout",
                            http_status=None,
                            provider_request_id=None,
                            request_id_state="absent",
                        )
                    )
                if failure_family == "transport":
                    raise ClassifiedProviderFailure(
                        ProviderFailureFact(
                            category="transport",
                            origin="sdk_connection",
                            http_status=None,
                            provider_request_id=None,
                            request_id_state="absent",
                        )
                    )
                raise VisualSymbolProviderError(
                    request_id="fixture-localized-schema",
                    usage={},
                    failure_stage="tool_arguments_schema_invalid",
                )
            return successful.review_symbols(image, prompt)

        def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
            return successful.review_candidate(image, prompt)

    provider = OneLocalizedFailureProvider()
    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: provider,
        symbol_session_factory=SessionLocal,
        require_symbol_persistence=True,
    )
    _seed_matrix_cache(advisor, matrix)
    reviewed: CandidateSnapshot | None = None
    result_ref: str | None = None

    try:
        reviewed = advisor.review(
            matrix.source,
            matrix.pages,
            matrix.snapshot,
        )
    except CandidateAdvisorFailure:
        pass

    if reviewed is not None:
        result_ref = InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: matrix.pages,
            candidate_snapshot_builder=lambda _pages: reviewed,
        ).run(
            str(project.id),
            source_file.resource_ref,
            f"product-process:{project.id}",
        )

    db_session.expire_all()
    decisions = tuple(
        db_session.scalars(
            select(SymbolRoutingDecisionRecord)
            .where(SymbolRoutingDecisionRecord.project_id == project.id)
        )
    )
    assert {
        decision.visual_observation_id: decision.disposition
        for decision in decisions
    } == {
        matrix.local_visual.observation_id: "locally_resolved",
        matrix.cache_visual.observation_id: "escalate",
        matrix.vlm_visual.observation_id: "escalate",
        matrix.failed_visual.observation_id: "escalate",
    }
    outcomes = tuple(
        db_session.scalars(
            select(SymbolEscalationOutcomeRecord)
            .where(SymbolEscalationOutcomeRecord.project_id == project.id)
        )
    )
    outcome_by_observation = {
        outcome.observation_outcomes[0]["visual_observation_id"]:
        outcome.observation_outcomes[0]["outcome_code"]
        for outcome in outcomes
    }
    assert outcome_by_observation == {
        matrix.cache_visual.observation_id: "cache_resolved",
        matrix.vlm_visual.observation_id: "provider_resolved",
        matrix.failed_visual.observation_id: expected_failure_stage,
    }
    cache_attempt = db_session.scalar(
        select(SymbolEscalationAttemptEventRecord).where(
            SymbolEscalationAttemptEventRecord.project_id == project.id,
            SymbolEscalationAttemptEventRecord.event_code
            == "cache_hit_valid",
        )
    )
    assert cache_attempt is not None
    assert cache_attempt.cache_entry_id is not None
    assert (
        db_session.get(
            VisualSymbolCacheEntryRecord,
            cache_attempt.cache_entry_id,
        ).project_id
        == project.id
    )
    called_visual_ids = {
        observation_id
        for observation_ids in provider.symbol_observation_ids
        for observation_id in observation_ids
    }
    assert called_visual_ids == {
        matrix.vlm_visual.observation_id,
        matrix.failed_visual.observation_id,
    }
    if failure_family in {"timeout", "transport"}:
        assert sum(
            matrix.failed_visual.observation_id in observation_ids
            for observation_ids in provider.symbol_observation_ids
        ) == 1
        failed_attempts = tuple(
            db_session.scalars(
                select(SymbolEscalationAttemptEventRecord).where(
                    SymbolEscalationAttemptEventRecord.project_id == project.id,
                    SymbolEscalationAttemptEventRecord.event_code
                    == expected_failure_stage,
                )
            )
        )
        assert len(failed_attempts) == 1
        assert failed_attempts[0].attempt_index == 0
        assert failed_attempts[0].provider_request_id is None
        assert failed_attempts[0].schema_version == (
            "symbol-escalation-attempt/2"
        )
        assert failed_attempts[0].diagnostic == {
            "schema_version": "visual-symbol-provider-failure/1",
            "failure_category": failure_family,
            "failure_stage": expected_failure_stage,
            "scope": "roi_localized",
            "origin": (
                "sdk_timeout"
                if failure_family == "timeout"
                else "sdk_connection"
            ),
            "http_status": None,
            "request_id_state": "absent",
            "pipeline_cause_category": None,
            "retry_decision": "not_authorized",
        }
        assert failed_attempts[0].diagnostic_sha256 is not None
        assert len(failed_attempts[0].diagnostic_sha256) == 64
        failed_outcome = next(
            outcome
            for outcome in outcomes
            if outcome.observation_outcomes == [
                {
                    "visual_observation_id": (
                        matrix.failed_visual.observation_id
                    ),
                    "outcome_code": expected_failure_stage,
                }
            ]
        )
        assert failed_outcome.outcome_code == "unresolved"

        project_storage = storage.root / "projects" / str(project.id)
        request_dir = project_storage / "provider-requests" / "qwen-symbol"
        request_documents = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in request_dir.glob("*.json")
        ]
        referenced_crop_refs = {
            document["crop_ref"] for document in request_documents
        }
        crop_dir = project_storage / "provider-inputs" / "qwen-symbol"
        unreferenced_crops = [
            path
            for path in crop_dir.glob("*.png")
            if (
                "asset://"
                + path.relative_to(storage.root).as_posix()
            )
            not in referenced_crop_refs
        ]
        assert len(unreferenced_crops) == 1
        failed_crop_sha256 = unreferenced_crops[0].stem
        cache_records = tuple(
            db_session.scalars(
                select(VisualSymbolCacheEntryRecord).where(
                    VisualSymbolCacheEntryRecord.project_id == project.id
                )
            )
        )
        assert all(
            record.identity.get("canonical_crop_sha256")
            != failed_crop_sha256
            for record in cache_records
        )
        assert not (
            project_storage / "provider-calls" / "qwen-symbol-retries"
        ).exists()
        assert not (
            project_storage / "provider-requests" / "qwen-symbol-retries"
        ).exists()
        assert not (
            project_storage / "provider-responses" / "qwen-symbol-retries"
        ).exists()
        persisted_evidence = b"".join(
            path.read_bytes()
            for directory in (
                project_storage / "provider-calls",
                project_storage / "provider-requests",
                project_storage / "provider-responses",
                project_storage / "provider-cache",
            )
            if directory.exists()
            for path in directory.rglob("*.json")
        )
        assert b"do-not-leak" not in persisted_evidence

    raw = db_session.scalar(
        select(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    )
    assert reviewed is not None
    assert raw is not None
    assert result_ref == f"automatic-result://{raw.id}"
    assert getattr(reviewed, "completeness", None) == (
        "partial_review_required"
    )
    assert getattr(raw, "completeness", None) == "partial_review_required"
    assert reviewed.technical_requirements == (requirement,)
    assert raw.technical_requirements == [requirement]
    assert {
        entry.observation_id for entry in reviewed.coverage_entries
    } == set(matrix.snapshot.expected_observation_ids)
    coverage_by_id = {
        entry.observation_id: entry
        for entry in reviewed.coverage_entries
    }
    local_entry = coverage_by_id[matrix.local_visual.observation_id]
    assert (
        local_entry.disposition,
        local_entry.candidate_id,
        local_entry.source_location_id,
    ) == (
        "non_inspection",
        None,
        matrix.local_visual.observation_id,
    )
    local_review = local_entry.advisor_review
    assert local_review is not None
    assert "local_resolution_evidence" in local_review
    assert local_review["symbol_kinds"] == ["revision_marker"]

    cache_candidate_id = "f6c9f7280582b7403b89108c"
    vlm_candidate_id = "914e3d058f97c3a3356655f5"
    cache_entry = coverage_by_id[matrix.cache_visual.observation_id]
    vlm_entry = coverage_by_id[matrix.vlm_visual.observation_id]
    assert (
        cache_entry.disposition,
        cache_entry.candidate_id,
        cache_entry.source_location_id,
    ) == (
        "candidate",
        cache_candidate_id,
        matrix.cache_visual.observation_id,
    )
    assert cache_entry.advisor_review is not None
    assert cache_entry.advisor_review["symbol_kinds"] == ["diameter"]
    assert (
        vlm_entry.disposition,
        vlm_entry.candidate_id,
        vlm_entry.source_location_id,
    ) == (
        "candidate",
        vlm_candidate_id,
        matrix.vlm_visual.observation_id,
    )
    assert vlm_entry.advisor_review is not None
    assert vlm_entry.advisor_review["symbol_kinds"] == [
        "counterbore",
        "depth",
        "diameter",
    ]
    reviewed_candidates = {
        candidate["candidate_id"]: candidate
        for candidate in reviewed.candidates
    }
    assert reviewed_candidates[cache_candidate_id]["payload"][
        "item_type"
    ] == "diameter_dimension"
    assert reviewed_candidates[cache_candidate_id][
        "source_location_ids"
    ][0] == matrix.cache_visual.observation_id
    assert reviewed_candidates[vlm_candidate_id]["payload"][
        "item_type"
    ] == "composite"
    assert reviewed_candidates[vlm_candidate_id][
        "source_location_ids"
    ][0] == matrix.vlm_visual.observation_id

    raw_coverage_by_id = {
        entry["observation_id"]: entry
        for entry in raw.coverage["entries"]
    }
    assert {
        key: raw_coverage_by_id[matrix.local_visual.observation_id][key]
        for key in ("disposition", "candidate_id", "source_location_id")
    } == {
        "disposition": "non_inspection",
        "candidate_id": None,
        "source_location_id": matrix.local_visual.observation_id,
    }
    assert {
        key: raw_coverage_by_id[matrix.cache_visual.observation_id][key]
        for key in ("disposition", "candidate_id", "source_location_id")
    } == {
        "disposition": "candidate",
        "candidate_id": cache_candidate_id,
        "source_location_id": matrix.cache_visual.observation_id,
    }
    assert {
        key: raw_coverage_by_id[matrix.vlm_visual.observation_id][key]
        for key in ("disposition", "candidate_id", "source_location_id")
    } == {
        "disposition": "candidate",
        "candidate_id": vlm_candidate_id,
        "source_location_id": matrix.vlm_visual.observation_id,
    }
    raw_candidates = {
        candidate["candidate_id"]: candidate
        for candidate in raw.candidates
    }
    assert raw_candidates[cache_candidate_id]["payload"]["item_type"] == (
        "diameter_dimension"
    )
    assert raw_candidates[cache_candidate_id]["source_location_ids"][0] == (
        matrix.cache_visual.observation_id
    )
    assert raw_candidates[vlm_candidate_id]["payload"]["item_type"] == (
        "composite"
    )
    assert raw_candidates[vlm_candidate_id]["source_location_ids"][0] == (
        matrix.vlm_visual.observation_id
    )
    failed_entry = next(
        entry
        for entry in reviewed.coverage_entries
        if entry.observation_id == matrix.failed_visual.observation_id
    )
    assert failed_entry.source_location_id == (
        matrix.failed_visual.observation_id
    )
    assert failed_entry.coordinates == matrix.failed_visual.bbox_pdf
    assert failed_entry.requires_confirmation is True
    assert failed_entry.advisor_review is not None
    assert failed_entry.advisor_review["failure_stage"] == (
        expected_failure_stage
    )
    assert "do-not-leak" not in repr(failed_entry.advisor_review)

    service = ReviewService(db_session)
    first = service.create_from_raw(raw.id)
    second = service.create_from_raw(raw.id)
    assert first.id == second.id
    assert [
        entry["requirement_id"] for entry in first.technical_requirements
    ] == [requirement["requirement_id"]]
    assert first.technical_requirements[0]["raw_text"] == requirement[
        "raw_text"
    ]
    assert first.technical_requirements[0]["match_outcome"] == "unresolved"
    status = ProjectIntakeService(
        db_session,
        storage,
        lambda *_args: None,
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    ).status(project.id)
    assert status.phase == "partial_review_required"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project.id)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.project_id == project.id)
        )
        == 1
    )


def test_project_failure_terminalizes_all_admitted_groups_without_result(
    monkeypatch: pytest.MonkeyPatch,
    committed_db_session: Session,
    tmp_path: Path,
) -> None:
    source, pages, snapshot = _eight_admitted_symbol_input(
        tmp_path,
        monkeypatch,
    )
    observation_ids = tuple(
        visual.observation_id
        for page in pages
        for visual in page.visual_observations
    )
    assert len(observation_ids) == 8
    storage = LocalFileStorage(tmp_path / "project-failure-storage")
    db_session = committed_db_session
    project, _source_file = _store_project_source(
        db_session,
        storage,
        source.read_bytes(),
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )
    authorization_root = create_cycle_authorization(
        tmp_path / "project-failure-authorization",
        project_ids=(str(project.id),),
    )
    ledger = ProviderUsageLedger.open(
        cycle_id=CYCLE_ID,
        storage_root=storage.root,
        authorization_root=authorization_root,
        project_id=str(project.id),
    )

    class ProjectBlockingProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def review_symbols(
            self,
            _image: bytes,
            prompt: str,
            *,
            reservation_permit: ReservationPermit | None = None,
        ) -> VisionResult:
            observation_id = json.loads(prompt)[
                "visual_observation_ids"
            ][0]
            assert reservation_permit is not None
            reservation_permit.consume_for_adapter(
                provider="qwen-vl",
                operation="review_symbols",
            )
            self.calls.append(observation_id)
            raise ClassifiedProviderFailure(
                ProviderFailureFact(
                    category="rate_limited",
                    origin="sdk_http_status",
                    http_status=429,
                    provider_request_id=(
                        f"safe-rate-{len(self.calls)}"
                    ),
                    request_id_state="accepted",
                )
            )

        def review_candidate(
            self,
            _image: bytes,
            _prompt: str,
        ) -> VisionResult:
            raise AssertionError("legacy review must not run")

    provider = ProjectBlockingProvider()
    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: provider,
        symbol_session_factory=SessionLocal,
        require_symbol_persistence=True,
        usage_ledger=ledger,
    )

    with pytest.raises(CandidateAdvisorFailure) as caught:
        advisor.review(source, pages, snapshot)

    db_session.expire_all()
    decisions = tuple(
        db_session.scalars(
            select(SymbolRoutingDecisionRecord).where(
                SymbolRoutingDecisionRecord.project_id == project.id,
                SymbolRoutingDecisionRecord.disposition == "escalate",
            )
        )
    )
    attempts = tuple(
        db_session.scalars(
            select(SymbolEscalationAttemptEventRecord).where(
                SymbolEscalationAttemptEventRecord.project_id
                == project.id
            )
        )
    )
    outcomes = tuple(
        db_session.scalars(
            select(SymbolEscalationOutcomeRecord).where(
                SymbolEscalationOutcomeRecord.project_id == project.id
            )
        )
    )
    blocking_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.event_code == "provider_rate_limited"
    )
    cancelled_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.event_code
        == "not_started_after_project_failure"
    )

    assert len(decisions) == 8
    assert len(provider.calls) == 2
    assert set(provider.calls) == set(observation_ids[:2])
    assert len(outcomes) == 8
    assert len(blocking_attempts) == 2
    assert len(cancelled_attempts) == 6
    first_group = next(
        outcome.escalation_group_id
        for outcome in outcomes
        if outcome.observation_outcomes[0]["visual_observation_id"]
        == observation_ids[0]
    )
    first_blocking = next(
        attempt
        for attempt in blocking_attempts
        if attempt.escalation_group_id == first_group
    )
    assert caught.value.failure_event_sha256 == (
        first_blocking.event_sha256
    )
    assert caught.value.failure_category == "rate_limited"
    assert caught.value.failure_scope == "project_blocking"
    assert {
        attempt.diagnostic["blocking_event_sha256"]
        for attempt in cancelled_attempts
    } == {first_blocking.event_sha256}
    assert {
        attempt.diagnostic["stop_reason"]
        for attempt in cancelled_attempts
    } == {"project_blocking_provider_failure"}
    cancelled_group_ids = {
        attempt.escalation_group_id for attempt in cancelled_attempts
    }
    admitted_group_ids = {
        decision.escalation_group_id for decision in decisions
    }
    submission_started_group_ids = {
        entry.subject_id for entry in ledger.snapshot().entries
    }
    terminal_group_ids = {
        outcome.escalation_group_id for outcome in outcomes
    }
    assert admitted_group_ids == (
        submission_started_group_ids | cancelled_group_ids
    )
    assert submission_started_group_ids.isdisjoint(cancelled_group_ids)
    assert terminal_group_ids == admitted_group_ids
    assert len(submission_started_group_ids) == 2
    ledger_snapshot = ledger.snapshot()
    assert ledger_snapshot.reserved_only_count == 0
    assert ledger_snapshot.submission_started_count == 2
    assert ledger_snapshot.unsettled_started_count == 0
    assert ledger_snapshot.committed_total_cny == "3.526656"
    assert {
        entry.state for entry in ledger_snapshot.entries
    } == {"reserved_unknown"}
    assert all(
        outcome.outcome_code == "cancelled"
        and {
            item["outcome_code"]
            for item in outcome.observation_outcomes
        } == {"cancelled_after_project_failure"}
        for outcome in outcomes
        if outcome.escalation_group_id in cancelled_group_ids
    )
    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(ReviewWorkingCopy).where(
            ReviewWorkingCopy.project_id == project.id
        )
    ) == 0
    project_storage = storage.root / "projects" / str(project.id)
    crop_dir = project_storage / "provider-inputs" / "qwen-symbol"
    assert len(tuple(crop_dir.glob("*.png"))) == 2
    written_paths = {
        str(path.relative_to(storage.root))
        for path in storage.root.rglob("*")
        if path.is_file()
    }
    assert not any(
        marker in path
        for path in written_paths
        for marker in ("pause", "symbol-report", "receipt")
    )


def test_hard_budget_denial_preserves_admitted_siblings_as_partial(
    monkeypatch: pytest.MonkeyPatch,
    committed_db_session: Session,
    tmp_path: Path,
) -> None:
    """A legal hard-budget denial is partial evidence, not whole-PDF failure."""
    matrix = _partial_matrix_input(tmp_path, monkeypatch)
    monkeypatch.setattr(
        escalation_planner_module,
        "MAX_VISUAL_PRIMARY_GROUPS_PER_PROJECT",
        2,
    )
    storage = LocalFileStorage(tmp_path / "hard-budget-partial")
    db_session = committed_db_session
    project, source_file = _store_project_source(
        db_session,
        storage,
        matrix.source.read_bytes(),
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )
    provider = _fixture_provider(matrix.source)
    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: provider,
        symbol_session_factory=SessionLocal,
        require_symbol_persistence=True,
    )
    reviewed: CandidateSnapshot | None = None
    failure: CandidateAdvisorFailure | None = None

    try:
        reviewed = advisor.review(
            matrix.source,
            matrix.pages,
            matrix.snapshot,
        )
    except CandidateAdvisorFailure as exc:
        failure = exc

    db_session.expire_all()
    attempts = tuple(
        db_session.scalars(
            select(SymbolEscalationAttemptEventRecord).where(
                SymbolEscalationAttemptEventRecord.project_id == project.id,
                SymbolEscalationAttemptEventRecord.event_code
                == "not_started_budget_exhausted",
            )
        )
    )
    outcomes = tuple(
        db_session.scalars(
            select(SymbolEscalationOutcomeRecord).where(
                SymbolEscalationOutcomeRecord.project_id == project.id,
                SymbolEscalationOutcomeRecord.outcome_code
                == "budget_exhausted",
            )
        )
    )
    assert len(attempts) == 1
    assert attempts[0].schema_version == "symbol-escalation-attempt/2"
    assert attempts[0].diagnostic == {
        "schema_version": "visual-symbol-budget-control/1",
        "budget_origin": "routing_plan",
    }
    assert len(outcomes) == 1
    assert outcomes[0].observation_outcomes == [
        {
            "visual_observation_id": matrix.failed_visual.observation_id,
            "outcome_code": "routing_budget_exhausted",
        }
    ]
    assert failure is None, (
        "a legitimate hard-budget denial must not invalidate the whole "
        f"routing contract: {failure}"
    )
    assert reviewed is not None

    called_visual_ids = {
        observation_id
        for observation_ids in provider.symbol_observation_ids
        for observation_id in observation_ids
    }
    assert called_visual_ids == {
        matrix.cache_visual.observation_id,
        matrix.vlm_visual.observation_id,
    }
    assert matrix.failed_visual.observation_id not in called_visual_ids
    coverage_by_id = {
        entry.observation_id: entry
        for entry in reviewed.coverage_entries
    }
    assert set(coverage_by_id) == set(
        matrix.snapshot.expected_observation_ids
    )
    local_entry = coverage_by_id[matrix.local_visual.observation_id]
    assert (
        local_entry.disposition,
        local_entry.source_location_id,
    ) == (
        "non_inspection",
        matrix.local_visual.observation_id,
    )
    denied_entry = coverage_by_id[matrix.failed_visual.observation_id]
    assert (
        denied_entry.disposition,
        denied_entry.candidate_id,
        denied_entry.source_location_id,
        denied_entry.coordinates,
        denied_entry.requires_confirmation,
    ) == (
        "ambiguous",
        None,
        matrix.failed_visual.observation_id,
        matrix.failed_visual.bbox_pdf,
        True,
    )
    assert denied_entry.advisor_review is not None
    assert denied_entry.advisor_review["failure_stage"] == (
        "routing_budget_exhausted"
    )
    assert reviewed.completeness == "partial_review_required"
    assert reviewed.recognition_summary["unresolved_roi_count"] == 1
    assert matrix.failed_visual.observation_id not in (
        reviewed.required_visual_observation_ids
    )

    result_ref = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=lambda _path: matrix.pages,
        candidate_snapshot_builder=lambda _pages: reviewed,
    ).run(
        str(project.id),
        source_file.resource_ref,
        f"product-process:{project.id}",
    )
    raw = db_session.scalar(
        select(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    )
    assert raw is not None
    assert result_ref == f"automatic-result://{raw.id}"
    assert raw.completeness == "partial_review_required"

    service = ReviewService(db_session)
    first = service.create_from_raw(raw.id)
    second = service.create_from_raw(raw.id)
    assert first.id == second.id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project.id)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.project_id == project.id)
        )
        == 1
    )


@pytest.mark.parametrize(
    "corruption",
    ("malformed_provenance", "incompatible_identity"),
)
def test_invalid_project_cache_is_quarantined_before_fresh_recomputation(
    corruption: str,
    monkeypatch: pytest.MonkeyPatch,
    committed_db_session: Session,
    tmp_path: Path,
) -> None:
    """PRT-5 never promotes a malformed or incompatible cache winner."""
    matrix = _partial_matrix_input(tmp_path, monkeypatch)
    storage = LocalFileStorage(tmp_path / f"quarantine-{corruption}")
    project, _source_file = _store_project_source(
        committed_db_session,
        storage,
        matrix.source.read_bytes(),
    )
    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: None,
        symbol_session_factory=SessionLocal,
        require_symbol_persistence=True,
    )
    decision_hashes = _record_matrix_decisions(advisor, matrix)
    batch = matrix.plan.batches[0]
    (
        crop_png,
        crop_bbox_pdf,
        batch_visuals,
        texts,
        execution_identity,
    ) = _execution_input(matrix, batch)
    expected_identity = advisor._production_cache_identity(
        execution_identity=execution_identity,
        visual_observations=batch_visuals,
        text_observations=texts,
        model="qwen3-vl-plus",
    )
    stored_identity = (
        expected_identity
        if corruption == "malformed_provenance"
        else replace(
            expected_identity,
            router_version="symbol-uncertainty-router/incompatible",
        )
    )
    response = {
        "schema_version": "visual-symbol-review/3",
        "detections": [],
        "gdt_frames": [],
    }
    response_sha256 = sha256(
        json.dumps(
            response,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    entry = build_cache_entry(
        identity=stored_identity,
        response=response,
        provenance=SymbolCacheProvenance(
            identity_sha256=stored_identity.sha256,
            producer_project_id=str(project.id),
            producer_request_id="provider-request-invalid",
            producer_call_record_ref=(
                f"asset://projects/{project.id}/provider-calls/"
                "qwen-symbol/provider-request-invalid.json"
            ),
            response_sha256=response_sha256,
            created_at=datetime(2026, 7, 30, tzinfo=UTC),
            model_identity=stored_identity.model_identity,
            response_schema_version=(
                stored_identity.response_schema_version
            ),
            router_version=stored_identity.router_version,
            validation_outcome="schema_valid",
        ),
        provider_event_code="provider_response_valid",
        schema_valid=True,
    )
    assert entry.provenance is not None
    provenance = asdict(entry.provenance)
    provenance["created_at"] = entry.provenance.created_at.isoformat()
    if corruption == "malformed_provenance":
        provenance["identity_sha256"] = "f" * 64
    invalid_record = VisualSymbolCacheEntryRecord(
        project_id=project.id,
        cache_key=expected_identity.sha256,
        cache_schema_version="visual-symbol-cache-entry/1",
        identity_sha256=stored_identity.sha256,
        identity=asdict(stored_identity),
        response=entry.response,
        response_sha256=entry.response_sha256,
        producer_request_id=entry.provenance.producer_request_id,
        producer_call_record_ref=(
            entry.provenance.producer_call_record_ref
        ),
        producer_provenance=provenance,
        provenance_sha256=sha256(
            json.dumps(
                provenance,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )
    committed_db_session.add(invalid_record)
    committed_db_session.commit()

    fresh_provider = _fixture_provider(matrix.source)
    outcome = advisor._visual_review_result(
        provider=fresh_provider,
        crop_png=crop_png,
        crop_bbox_pdf=crop_bbox_pdf,
        source_sha256=sha256(matrix.source.read_bytes()).hexdigest(),
        visual_observations=batch_visuals,
        text_observations=texts,
        model="qwen3-vl-plus",
        allow_schema_retry=False,
        execution_identity=execution_identity,
        legacy_cache_enabled=False,
        evidence_context=VisualEvidenceContext(
            escalation_group_id=batch.content_sha256,
            routing_decision_sha256=routing_decision_group_sha256(
                tuple(
                    decision_hashes[observation_id]
                    for observation_id in batch.observation_ids
                )
            ),
        ),
        production_retry_coordinator=NoSchemaRetryCoordinator(),
    )

    assert outcome.cache_hit is False
    assert outcome.result.request_id == "fixture-visual-1"
    assert fresh_provider.symbol_observation_ids == [
        (matrix.cache_visual.observation_id,)
    ]
    attempts = tuple(
        committed_db_session.scalars(
            select(SymbolEscalationAttemptEventRecord)
            .where(
                SymbolEscalationAttemptEventRecord.project_id
                == project.id
            )
        )
    )
    attempt_by_code = {
        attempt.event_code: attempt for attempt in attempts
    }
    assert set(attempt_by_code) == {
        "cache_provenance_invalid",
        "provider_response_valid",
    }
    assert (
        attempt_by_code["cache_provenance_invalid"].cache_entry_id
        == invalid_record.id
    )
    assert (
        attempt_by_code["provider_response_valid"].provider_request_id
        == "fixture-visual-1"
    )
    assert all(attempt.project_id == project.id for attempt in attempts)


def test_persisted_routing_evidence_revalidation_failure_creates_no_result(
    monkeypatch: pytest.MonkeyPatch,
    committed_db_session: Session,
    tmp_path: Path,
) -> None:
    """PRT-5 distinguishes persisted evidence conflict from write failure."""
    matrix = _partial_matrix_input(tmp_path, monkeypatch)
    storage = LocalFileStorage(tmp_path / "evidence-revalidation")
    project, source_file = _store_project_source(
        committed_db_session,
        storage,
        matrix.source.read_bytes(),
    )

    class CountingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def review_symbols(
            self,
            _image: bytes,
            _prompt: str,
        ) -> VisionResult:
            self.calls += 1
            return VisionResult(
                request_id="provider-must-not-run",
                payload={
                    "schema_version": "visual-symbol-review/3",
                    "detections": [],
                    "gdt_frames": [],
                },
                usage={},
            )

    provider = CountingProvider()
    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: provider,
        symbol_session_factory=SessionLocal,
        require_symbol_persistence=True,
    )
    _record_matrix_decisions(advisor, matrix)
    batch = matrix.plan.batches[0]
    decisions = tuple(
        committed_db_session.scalars(
            select(SymbolRoutingDecisionRecord).where(
                SymbolRoutingDecisionRecord.project_id == project.id
            )
        )
    )
    assert {
        decision.visual_observation_id for decision in decisions
    } == set(matrix.decisions)
    batch_decisions = tuple(
        sorted(
            (
                decision
                for decision in decisions
                if decision.escalation_group_id
                == batch.content_sha256
            ),
            key=lambda decision: (
                decision.escalation_group_member_index
            ),
        )
    )
    assert tuple(
        decision.visual_observation_id
        for decision in batch_decisions
    ) == batch.observation_ids
    persisted_group_sha256 = routing_decision_group_sha256(
        tuple(
            decision.decision_sha256
            for decision in batch_decisions
        )
    )
    conflicting_group_sha256 = "f" * 64
    assert persisted_group_sha256 != conflicting_group_sha256

    monkeypatch.setattr(advisor_module, "MAX_VISUAL_IN_FLIGHT", 1)
    actual_group_sha256 = advisor_module.routing_decision_group_sha256

    def conflict_claimed_group(
        decision_sha256s: tuple[str, ...],
    ) -> str:
        actual = actual_group_sha256(decision_sha256s)
        return (
            conflicting_group_sha256
            if actual == persisted_group_sha256
            else actual
        )

    monkeypatch.setattr(
        advisor_module,
        "routing_decision_group_sha256",
        conflict_claimed_group,
    )

    with pytest.raises(CandidateAdvisorFailure) as advisor_failure:
        advisor.review(matrix.source, matrix.pages, matrix.snapshot)

    assert str(advisor_failure.value) == "Visual symbol cache lookup failed"
    assert advisor_failure.value.failure_origin == "routing_evidence"
    assert provider.calls == 0

    def candidate_builder(_pages: tuple[object, ...]) -> CandidateSnapshot:
        raise advisor_failure.value

    with pytest.raises(CandidateAdvisorFailure):
        InventoryPipeline(
            committed_db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: matrix.pages,
            candidate_snapshot_builder=candidate_builder,
        ).run(
            str(project.id),
            source_file.resource_ref,
            f"product-process:revalidation:{project.id}",
        )

    error = committed_db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    job = committed_db_session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == str(project.id)
        )
    )
    assert error is not None
    assert job is not None
    assert (
        committed_db_session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project.id)
        )
        == 0
    )
    assert job.result_ref is None
    assert error.code == "symbol_routing_evidence_failed"
    assert error.stage == "candidate_advisor"
    assert error.cause_category == "processing_defect"
    assert (
        committed_db_session.scalar(
            select(func.count())
            .select_from(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.project_id == project.id)
        )
        == 0
    )


def test_shadow_uncertainty_uses_legacy_candidate_semantics_with_provenance(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    tmp_path: Path,
) -> None:
    source, pages, initial = _bounded_symbol_input(
        tmp_path,
        monkeypatch,
    )
    legacy_provider = _fixture_provider(source)
    shadow_provider = _fixture_provider(source)
    legacy = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="legacy_high_recall",
        ),
        LocalFileStorage(tmp_path / "legacy-provider-storage"),
        project_id="shadow-legacy",
        provider_factory=lambda _settings: legacy_provider,
    ).review(source, pages, initial)
    shadow = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="shadow_uncertainty",
        ),
        LocalFileStorage(tmp_path / "shadow-provider-storage"),
        project_id="shadow-evaluation",
        provider_factory=lambda _settings: shadow_provider,
    ).review(source, pages, initial)

    assert replace(
        shadow,
        recognition_mode="legacy_high_recall",
        router_version="legacy",
    ) == legacy
    assert shadow.recognition_mode == "shadow_uncertainty"
    assert shadow.router_version == "symbol-uncertainty-router/1"
    assert shadow.recognition_evidence_ref is None
    assert shadow_provider.symbol_observation_ids == (
        legacy_provider.symbol_observation_ids
    )
    assert shadow_provider.total_calls == legacy_provider.total_calls
    project, raw, _working = _persist_snapshot(
        db_session,
        LocalFileStorage(tmp_path / "result-storage"),
        shadow,
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project.id)
        )
        == 1
    )
    assert tuple(raw.provider_call_ids) == shadow.provider_call_ids


def test_vector_fixture_builds_visual_candidate_and_working_copy(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    """INT-01 persists a visual candidate through the one canonical task."""
    project, provider, result_ref, visual_ids = _fixture_task(
        monkeypatch,
        task_session_factory,
        tmp_path,
    )

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        working = verify.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == project.id
            )
        )
        assert raw is not None
        assert working is not None
        assert result_ref == f"automatic-result://{raw.id}"
        visual_candidates = [
            candidate
            for candidate in raw.candidates
            if visual_ids.intersection(candidate["source_location_ids"])
        ]
        assert visual_candidates
        assert len(working.items) == len(raw.candidates)
        assert any(
            visual_ids.intersection(item["source_location_ids"])
            for item in working.items
        )
        recognized = next(
            candidate
            for candidate in visual_candidates
            if candidate["payload"].get("normalized_text")
            and candidate["payload"]["normalized_text"]
            != candidate["payload"]["raw_text"]
        )
        recognized_item = next(
            item
            for item in working.items
            if item["item_id"] == recognized["candidate_id"]
        )
        assert recognized_item["raw_text"] == recognized["payload"]["raw_text"]
        assert (
            recognized_item["normalized_text"]
            == recognized["payload"]["normalized_text"]
        )
        assert provider.symbol_calls > 0
        assert provider.factory_calls == 1
        assert raw.provider_call_ids
        raw_payload = json.dumps(
            {
                "candidates": raw.candidates,
                "coverage": raw.coverage,
            },
            sort_keys=True,
        )
        assert "fixture_family" not in raw_payload
        assert "expected_projection" not in raw_payload
        assert "label_id" not in raw_payload
    finally:
        verify.close()


def test_diameter_depth_and_counterbore_group_as_one_annotation(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    tmp_path: Path,
) -> None:
    """INT-02 keeps one primary item per locally projected symbol group."""
    def text_observation(
        observation_id: str,
        raw_text: str,
        y0: float,
    ) -> TextObservation:
        bbox = (90.0, y0, 150.0, y0 + 12.0)
        return TextObservation(
            observation_id=observation_id,
            source_type="native",
            observation_level="line",
            raw_text=raw_text,
            normalized_text=raw_text,
            page_index=0,
            bbox_pdf=bbox,
            bbox_normalized=(
                bbox[0] / 240.0,
                bbox[1] / 200.0,
                bbox[2] / 240.0,
                bbox[3] / 200.0,
            ),
            direction=(1.0, 0.0),
            direction_angle_degrees=0.0,
            confidence=None,
        )

    text_observations = (
        text_observation("text-diameter", "10", 30.0),
        text_observation("text-depth", "M6 深12", 80.0),
        text_observation("text-counterbore-diameter", "22", 130.0),
        text_observation("text-counterbore-depth", "深6", 143.0),
    )
    visual_observations = (
        VisualObservation(
            "visual-diameter",
            "visual",
            "annotation_context",
            0,
            (50.0, 25.0, 80.0, 45.0),
            (50 / 240, 25 / 200, 80 / 240, 45 / 200),
            "text_adjacent_vector_context",
            "1" * 64,
            ("text-diameter",),
        ),
        VisualObservation(
            "visual-depth",
            "visual",
            "annotation_context",
            0,
            (50.0, 75.0, 80.0, 95.0),
            (50 / 240, 75 / 200, 80 / 240, 95 / 200),
            "text_adjacent_vector_context",
            "2" * 64,
            ("text-depth",),
        ),
        VisualObservation(
            "visual-counterbore",
            "visual",
            "annotation_context",
            0,
            (50.0, 125.0, 80.0, 160.0),
            (50 / 240, 125 / 200, 80 / 240, 160 / 200),
            "text_adjacent_vector_context",
            "3" * 64,
            ("text-counterbore-diameter", "text-counterbore-depth"),
        ),
    )
    page = PageInventory(
        page_index=0,
        width=240.0,
        height=200.0,
        rotation=0,
        page_type="vector",
        processing_route="native",
        support_level="supported",
        review_required=False,
        unsupported_reason=None,
        classification_confidence=1.0,
        classification_rule_version="fixture",
        classification_evidence={},
        pdf_to_render_matrix=(1, 0, 0, 1, 0, 0),
        render_to_pdf_matrix=(1, 0, 0, 1, 0, 0),
        observations=text_observations,
        visual_observations=visual_observations,
    )
    source = tmp_path / "grouping-source.pdf"
    document = pymupdf.open()
    pdf_page = document.new_page(width=page.width, height=page.height)
    for observation in text_observations:
        pdf_page.insert_text(
            (
                observation.bbox_pdf[0],
                observation.bbox_pdf[1] + 10.0,
            ),
            observation.raw_text,
        )
    for observation in visual_observations:
        pdf_page.draw_rect(
            observation.bbox_pdf,
            color=(0, 0, 0),
            width=1,
        )
    document.save(source)
    document.close()

    initial = candidate_snapshot_from_inventory((page,))
    kinds_by_visual = {
        "visual-diameter": ("diameter",),
        "visual-depth": ("depth",),
        "visual-counterbore": ("counterbore", "depth", "diameter"),
    }
    visual_inputs: dict[
        str,
        tuple[
            tuple[str, ...],
            tuple[str, ...],
            tuple[float, float, float, float],
        ],
    ] = {}
    visual_by_id = {
        observation.observation_id: observation
        for observation in visual_observations
    }
    for page_batches in plan_visual_batches((page,), initial):
        for batch in page_batches:
            x0, y0, x1, y1 = batch.crop_bbox_pdf
            width = x1 - x0
            height = y1 - y0
            for visual_id in batch.observation_ids:
                observation = visual_by_id[visual_id]
                bbox = observation.bbox_pdf
                visual_inputs[visual_id] = (
                    kinds_by_visual[visual_id],
                    observation.associated_text_observation_ids,
                    (
                        (bbox[0] - x0) / width,
                        (bbox[1] - y0) / height,
                        (bbox[2] - x0) / width,
                        (bbox[3] - y0) / height,
                    ),
                )

    provider = FixtureVisionProvider(visual_inputs)
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda *_args, **_kwargs: (),
    )
    reviewed = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "provider-storage"),
        project_id="int-02",
        provider_factory=lambda _settings: provider,
    ).review(source, (page,), initial)

    _project, raw, working = _persist_snapshot(
        db_session,
        LocalFileStorage(tmp_path / "storage"),
        reviewed,
    )

    assert len(raw.candidates) == len(working.items) == 3
    assert {
        candidate["payload"]["item_type"]
        for candidate in raw.candidates
    } == {
        "diameter_dimension",
        "thread",
        "composite",
    }
    visual_entries = [
        entry
        for entry in raw.coverage["entries"]
        if entry["observation_id"] in kinds_by_visual
    ]
    assert len({entry["candidate_id"] for entry in visual_entries}) == 3
    assert all(entry["disposition"] == "candidate" for entry in visual_entries)
    for candidate in raw.candidates:
        assert (
            sum(
                item["item_id"] == candidate["candidate_id"]
                for item in working.items
            )
            == 1
        )


def test_roughness_gdt_and_datum_project_without_schema_expansion(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    """INT-03 reuses coarse shapes and keeps typed GDTs separate."""
    project, _provider, _result_ref, visual_ids = _fixture_task(
        monkeypatch,
        task_session_factory,
        tmp_path,
    )

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        working = verify.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == project.id
            )
        )
        assert raw is not None
        assert working is not None
        assert "roughness" in {
            item["coarse_type"]
            for item in working.items
            if "coarse_type" in item
        }
        assert any(
            item.get("item_type") == "geometric_tolerance"
            for item in working.items
        )
        datum_entries = [
            entry
            for entry in raw.coverage["entries"]
            if entry["observation_id"] in visual_ids
            and entry.get("advisor_review", {}).get("symbol_kinds")
            == ["datum_reference"]
        ]
        assert len(datum_entries) == 2
        assert all(
            entry["disposition"] == "reference_context"
            and entry["candidate_id"] is None
            and entry["requires_confirmation"] is False
            for entry in datum_entries
        )
        datum_ids = {entry["observation_id"] for entry in datum_entries}
        assert not any(
            datum_ids.intersection(item["source_location_ids"])
            for item in working.items
        )
        revision_entries = [
            entry
            for entry in raw.coverage["entries"]
            if entry["observation_id"] in visual_ids
            and entry.get("advisor_review", {}).get("symbol_kinds")
            == ["revision_marker"]
        ]
        assert len(revision_entries) == 2
        assert all(
            entry["disposition"] == "non_inspection"
            and entry["candidate_id"] is None
            and entry["requires_confirmation"] is True
            for entry in revision_entries
        )
        revision_ids = {
            entry["observation_id"] for entry in revision_entries
        }
        assert not any(
            revision_ids.intersection(item["source_location_ids"])
            for item in working.items
        )
        retired_revision_entries = [
            entry
            for entry in raw.coverage["entries"]
            if entry["observation_id"] not in visual_ids
            and entry.get("advisor_review", {}).get("symbol_kinds")
            == ["revision_marker"]
        ]
        assert len(retired_revision_entries) == 2
        assert all(
            entry["advisor_review"]
            == _visual_review(["revision_marker"], None)
            for entry in retired_revision_entries
        )
        working_coverage_by_id = {
            entry["observation_id"]: entry
            for entry in working.coverage["entries"]
        }
        assert all(
            working_coverage_by_id[entry["observation_id"]][
                "symbol_kinds"
            ]
            == ["revision_marker"]
            and working_coverage_by_id[entry["observation_id"]][
                "rejection_code"
            ]
            is None
            and "advisor_review"
            not in working_coverage_by_id[entry["observation_id"]]
            for entry in retired_revision_entries
        )
        assert set(get_args(CandidateType)) == {
            "linear_dimension",
            "diameter_dimension",
            "thread",
            "radius",
            "angle",
            "general_requirement",
            "composite",
        }
        assert set(get_args(CoarseType)) == {
            "roughness",
            "weld",
            "cross_view_duplicate",
        }
    finally:
        verify.close()


@pytest.mark.parametrize(
    ("failure_case", "expected_code", "expected_stage", "expected_category"),
    (
        (
            "visual_crop_oversize",
            "visual_crop_oversize",
            "candidate_advisor",
            "processing_defect",
        ),
        (
            "symbol_route_budget_exhausted",
            "symbol_route_budget_exhausted",
            "candidate_advisor",
            "processing_defect",
        ),
        (
            "coverage_conflict",
            "coverage_blocking",
            "coverage",
            "processing_defect",
        ),
        (
            "missing_source_identity",
            "inventory_processing_failed",
            "page_inventory",
            "processing_defect",
        ),
        (
            "invalid_routing_schema",
            None,
            "candidate_advisor",
            "processing_defect",
        ),
        (
            "evidence_persistence_failed",
            None,
            "candidate_advisor",
            "processing_defect",
        ),
    ),
)
def test_systemic_symbol_failure_creates_no_result(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    tmp_path: Path,
    failure_case: str,
    expected_code: str | None,
    expected_stage: str,
    expected_category: str,
) -> None:
    """PRT-5 systemic scheduling/coverage corruption remains fail-closed."""
    advisor_failure_cases = {
        "invalid_routing_schema",
        "evidence_persistence_failed",
    }
    source_payload = b"fixture-pdf"
    if failure_case in advisor_failure_cases:
        fixture_source, _manifest = build_symbol_fixture(
            tmp_path / "failure-fixture"
        )
        source_payload = fixture_source.read_bytes()
    storage = LocalFileStorage(tmp_path / "storage")
    project, source = _store_project_source(db_session, storage, source_payload)
    source_path = storage.resolve_resource_ref(source.resource_ref)
    private_detail = "/srv/private/customer.pdf credential=do-not-leak"
    inventory_pages: tuple[object, ...] = (SupportedPageStub(),)

    if failure_case == "missing_source_identity":
        db_session.delete(source)
        db_session.commit()

        def candidate_builder(_pages: tuple[object, ...]) -> CandidateSnapshot:
            raise AssertionError("missing source reached CandidateAdvisor")

        expected_exception = ValueError
    elif failure_case == "coverage_conflict":
        conflict = _snapshot(
            candidates=(),
            entries=(
                CoverageEntry(
                    "visual-conflict",
                    "ambiguous",
                    "visual-conflict",
                    (1, 2, 3, 4),
                    requires_confirmation=True,
                    advisor_review={
                        "route": "visual_symbol",
                        "schema_version": "visual-symbol-review/3",
                        "symbol_kinds": ["diameter"],
                        "rejection_code": "visual_no_detection",
                        "confidence_signal": None,
                    },
                ),
            ),
        )

        def candidate_builder(_pages: tuple[object, ...]) -> CandidateSnapshot:
            return conflict

        expected_exception: type[Exception] = CoverageBlocking
    elif failure_case in {
        "visual_crop_oversize",
        "symbol_route_budget_exhausted",
    }:

        def candidate_builder(_pages: tuple[object, ...]) -> CandidateSnapshot:
            raise VisualObservationBlockingError(
                failure_case,
                page_index=0,
            )

        expected_exception = VisualObservationBlockingError
    else:
        visual_pages = tuple(build_inventory(source_path))
        inventory_pages = visual_pages
        if failure_case == "invalid_routing_schema":
            monkeypatch.setattr(
                advisor_module,
                "route_visual_observation",
                lambda _resolution: object(),
            )

            def symbol_session_factory() -> Session:
                raise AssertionError(
                    "invalid routing reached evidence persistence"
                )
        else:
            def symbol_session_factory() -> Session:
                raise RuntimeError("routing evidence persistence unavailable")

        advisor = CandidateAdvisor(
            Settings(
                qwen_model="qwen3-vl-plus",
                symbol_recognition_mode="production_uncertainty",
            ),
            storage,
            project_id=str(project.id),
            provider_factory=lambda _settings: (_ for _ in ()).throw(
                AssertionError("systemic corruption reached Provider")
            ),
            symbol_session_factory=symbol_session_factory,
            require_symbol_persistence=True,
        )
        expected_exception = CandidateAdvisorFailure

        def candidate_builder(
            current_pages: tuple[object, ...],
        ) -> CandidateSnapshot:
            return advisor.review(
                source_path,
                current_pages,
                candidate_snapshot_from_inventory(current_pages),
            )

    with pytest.raises(expected_exception):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: inventory_pages,
            candidate_snapshot_builder=candidate_builder,
        ).run(
            str(project.id),
            source.resource_ref,
            f"product-process:{project.id}",
        )

    db_session.expire_all()
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    job = db_session.scalar(
        select(LogicalJob).where(LogicalJob.project_id == str(project.id))
    )
    assert error is not None
    assert job is not None
    if expected_code is not None:
        assert error.code == expected_code
    assert error.stage == expected_stage
    assert error.cause_category == expected_category
    assert error.severity == "blocking"
    if failure_case == "coverage_conflict":
        assert error.location_ref is not None
        assert error.location_ref.startswith(
            f"asset://projects/{project.id}/inventory/"
        )
        assert storage.resolve_resource_ref(error.location_ref).is_file()
    elif failure_case != "missing_source_identity":
        assert error.location_ref is None
    assert private_detail not in error.message
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED
    assert job.status == "failed"
    assert job.result_ref is None
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project.id)
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.project_id == project.id)
        )
        == 0
    )


@pytest.mark.parametrize("command_type", ("promote", "ignore"))
def test_visual_no_detection_uses_system_default_source_disposition(
    db_session: Session,
    tmp_path: Path,
    command_type: str,
) -> None:
    """INT-05 preserves raw evidence while settling the new working copy."""
    fixture_source, _manifest = build_symbol_fixture(
        tmp_path / "no-detection-fixture"
    )
    storage = LocalFileStorage(tmp_path / "storage")
    project, source = _store_project_source(
        db_session,
        storage,
        fixture_source.read_bytes(),
    )
    source_path = storage.resolve_resource_ref(source.resource_ref)
    pages = tuple(build_inventory(source_path))
    provider = _fixture_provider(
        source_path,
        detect_symbols=False,
    )
    advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: provider,
    )
    InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=lambda _path: pages,
        candidate_snapshot_builder=lambda current_pages: advisor.review(
            source_path,
            current_pages,
            candidate_snapshot_from_inventory(current_pages),
        ),
    ).run(
        str(project.id),
        source.resource_ref,
        f"product-process:{project.id}",
    )
    raw = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert raw is not None
    working = ReviewService(db_session).create_from_raw(raw.id)
    visual = pages[0].visual_observations[0]
    observation_id = visual.observation_id
    raw_entry = next(
        entry
        for entry in raw.coverage["entries"]
        if entry["observation_id"] == observation_id
    )
    entry = next(
        entry
        for entry in working.coverage["entries"]
        if entry["observation_id"] == observation_id
    )
    assert raw_entry["advisor_review"] == _visual_review(
        [],
        "visual_no_detection",
    )
    assert raw_entry["disposition"] == "ambiguous"
    assert raw_entry["requires_confirmation"] is True
    assert entry == {
        "observation_id": observation_id,
        "disposition": "non_inspection",
        "source_location_id": observation_id,
        "coordinates": list(visual.bbox_pdf),
        "candidate_id": None,
        "requires_confirmation": False,
        "symbol_kinds": [],
        "rejection_code": "visual_no_detection",
        "confirmation_accepted": False,
        "resolution_source": "system_default",
        "resolution_rule_version": "review-source-default/1",
    }
    inventory = json.loads(storage.read_bytes(raw.inventory_ref))
    persisted_visual = next(
        item
        for item in inventory["pages"][0]["visual_observations"]
        if item["observation_id"] == observation_id
    )
    assert persisted_visual["page_index"] == visual.page_index == 0
    assert persisted_visual["bbox_pdf"] == list(visual.bbox_pdf)
    assert not any(
        observation_id in item["source_location_ids"]
        for item in working.items
    )
    before_items = list(working.items)
    before_coverage = dict(working.coverage)
    before_version = working.version

    service = ReviewService(db_session)
    acquire_lock(db_session, working.project_id, "quality-1")
    command: dict[str, object]
    if command_type == "promote":
        command = {
            "type": "promote_source",
            "observation_id": observation_id,
            "raw_text": "M6",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        }
    else:
        command = {
            "type": "ignore_source",
            "observation_id": observation_id,
        }
    with pytest.raises(
        ReviewNotFound,
        match=f"source review target {observation_id} was not found",
    ):
        service.apply(
            working.id,
            expected_version=before_version,
            operator_id="quality-1",
            command=command,
        )

    db_session.expire_all()
    persisted = db_session.get(ReviewWorkingCopy, working.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.items == before_items
    assert persisted.coverage == before_coverage


def test_visual_processing_replay_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    """INT-06 returns the persisted winner without Provider or cache work."""
    project, provider, first_ref, _visual_ids = _fixture_task(
        monkeypatch,
        task_session_factory,
        tmp_path,
    )
    calls_after_first = (provider.factory_calls, provider.total_calls)

    def must_not_rebuild(
        _recognition: RuntimeRecognition,
        _source: Path,
    ) -> tuple[object, ...]:
        raise AssertionError("successful replay rebuilt the visual inventory")

    monkeypatch.setattr(RuntimeRecognition, "build_inventory", must_not_rebuild)
    second_ref = inventory_project.run(
        str(project.id),
        f"asset://projects/{project.id}/source.pdf",
        f"product-process:{project.id}",
    )

    verify = task_session_factory()
    try:
        assert second_ref == first_ref
        assert (provider.factory_calls, provider.total_calls) == calls_after_first
        assert (
            verify.scalar(
                select(func.count())
                .select_from(AutomaticResult)
                .where(AutomaticResult.project_id == project.id)
            )
            == 1
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(ReviewWorkingCopy)
                .where(ReviewWorkingCopy.project_id == project.id)
            )
            == 1
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(ErrorRecord)
                .where(ErrorRecord.project_id == project.id)
            )
            == 0
        )
    finally:
        verify.close()


@pytest.mark.parametrize("command_type", ("promote", "ignore"))
def test_revision_marker_uses_system_default_source_disposition(
    db_session: Session,
    tmp_path: Path,
    command_type: str,
) -> None:
    observation_id = "visual-revision"
    snapshot = _snapshot(
        candidates=(),
        entries=(
            CoverageEntry(
                observation_id,
                "non_inspection",
                observation_id,
                (10, 20, 30, 40),
                requires_confirmation=True,
                advisor_review=_visual_review(["revision_marker"], None),
            ),
        ),
    )
    _project, raw, working = _persist_snapshot(
        db_session,
        LocalFileStorage(tmp_path / "storage"),
        snapshot,
    )
    assert raw.candidates == []
    assert working.items == []
    raw_entry = raw.coverage["entries"][0]
    assert raw_entry["disposition"] == "non_inspection"
    assert raw_entry["requires_confirmation"] is True
    assert raw_entry["advisor_review"] == _visual_review(
        ["revision_marker"],
        None,
    )
    entry = working.coverage["entries"][0]
    assert entry == {
        "observation_id": observation_id,
        "disposition": "non_inspection",
        "source_location_id": observation_id,
        "coordinates": [10, 20, 30, 40],
        "candidate_id": None,
        "requires_confirmation": False,
        "symbol_kinds": ["revision_marker"],
        "rejection_code": None,
        "confirmation_accepted": False,
        "resolution_source": "system_default",
        "resolution_rule_version": "review-source-default/1",
    }
    before_coverage = dict(working.coverage)
    before_version = working.version

    service = ReviewService(db_session)
    acquire_lock(db_session, working.project_id, "quality-1")
    command: dict[str, object]
    if command_type == "promote":
        command = {
            "type": "promote_source",
            "observation_id": observation_id,
            "raw_text": "REV 1",
            "item_type": "general_requirement",
            "scope": "global_requirement",
            "balloon_required": False,
            "page_index": 0,
        }
    else:
        command = {
            "type": "ignore_source",
            "observation_id": observation_id,
        }
    with pytest.raises(
        ReviewNotFound,
        match=f"source review target {observation_id} was not found",
    ):
        service.apply(
            working.id,
            expected_version=before_version,
            operator_id="quality-1",
            command=command,
        )

    db_session.expire_all()
    persisted = db_session.get(ReviewWorkingCopy, working.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.items == []
    assert persisted.coverage == before_coverage
