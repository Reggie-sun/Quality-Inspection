from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import get_args

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

import app.candidates.advisor as advisor_module
from app.candidates.advisor import CandidateAdvisor, CandidateAdvisorFailure
from app.candidates.complex_fallback import CoarseType
from app.candidates.coverage import CoverageEntry
from app.candidates.local_symbol_resolution import LocalResolution
from app.candidates.models import AutomaticResult
from app.candidates.schemas import CandidateType
from app.candidates.symbol_review import (
    VisualReviewDecision,
    plan_visual_batches,
)
from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.db import engine
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
from app.projects.state import ProjectState
from app.providers.base import VisionResult
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewService
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
                            "requires_confirmation": True,
                        }
                    )
        return VisionResult(
            request_id=f"fixture-visual-{self.symbol_calls}",
            payload={
                "schema_version": "visual-symbol-review/1",
                "detections": detections,
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


def _store_project_source(
    session: Session,
    storage: LocalFileStorage,
    payload: bytes,
) -> tuple[Project, StoredFile]:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
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
        "schema_version": "visual-symbol-review/1",
        "symbol_kinds": symbol_kinds,
        "rejection_code": rejection_code,
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
    project, source = _store_project_source(session, storage, b"fixture-pdf")
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
    selected_ids = {
        visual.observation_id
        for page in original_pages
        for visual in page.visual_observations
    }
    selected_ids = set(sorted(selected_ids)[:2])
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


def test_mixed_local_and_escalated_preserve_exact_source_and_coverage(
    monkeypatch: pytest.MonkeyPatch,
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

    reviewed = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "provider-storage"),
        project_id="mixed-routing",
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
    assert coverage_by_id[
        escalated_visual.observation_id
    ].source_location_id == escalated_visual.observation_id
    assert coverage_by_id[
        escalated_visual.observation_id
    ].advisor_review == _visual_review([], "visual_no_detection")
    assert initial == candidate_snapshot_from_inventory(pages)


def test_shadow_uncertainty_uses_legacy_final_write_without_extra_provider(
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

    assert shadow == legacy
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
    """INT-03 reuses coarse shapes and keeps datum as source-only context."""
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
        assert {
            item["coarse_type"]
            for item in working.items
            if "coarse_type" in item
        }.issuperset({"roughness", "geometric_tolerance"})
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
            "geometric_tolerance",
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
            "provider_unavailable",
            "vision_provider_call_failed",
            "candidate_advisor",
            "transient_provider_failure",
        ),
        (
            "invalid_root_schema",
            "vision_provider_call_failed",
            "candidate_advisor",
            "transient_provider_failure",
        ),
        (
            "invalid_cache_audit",
            "vision_provider_call_failed",
            "candidate_advisor",
            "transient_provider_failure",
        ),
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
    ),
)
def test_visual_provider_failure_prevents_ready_for_edit(
    db_session: Session,
    tmp_path: Path,
    failure_case: str,
    expected_code: str,
    expected_stage: str,
    expected_category: str,
) -> None:
    """INT-04 fails closed before either result layer exists."""
    advisor_failure_cases = {
        "provider_unavailable",
        "invalid_root_schema",
        "invalid_cache_audit",
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

    if failure_case == "coverage_conflict":
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
                        "schema_version": "visual-symbol-review/1",
                        "symbol_kinds": ["diameter"],
                        "rejection_code": "visual_no_detection",
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
        initial = candidate_snapshot_from_inventory(visual_pages)

        if failure_case == "provider_unavailable":

            def provider_factory(_settings: Settings) -> object:
                raise CapabilityUnavailable(
                    "vision_provider_unavailable",
                    private_detail,
                )

            expected_exception = CapabilityUnavailable
        elif failure_case == "invalid_root_schema":

            class InvalidRootSchemaProvider:
                @staticmethod
                def review_symbols(
                    _image: bytes,
                    _prompt: str,
                ) -> VisionResult:
                    return VisionResult(
                        request_id="fixture-invalid-schema",
                        payload={"schema_version": "visual-symbol-review/1"},
                        usage={},
                    )

                @staticmethod
                def review_candidate(
                    _image: bytes,
                    _prompt: str,
                ) -> VisionResult:
                    raise AssertionError(
                        "invalid visual root schema reached text review"
                    )

            invalid_schema_provider = InvalidRootSchemaProvider()

            def provider_factory(_settings: Settings) -> object:
                return invalid_schema_provider

            expected_exception = CandidateAdvisorFailure
        else:
            valid_provider = _fixture_provider(source_path)
            CandidateAdvisor(
                Settings(qwen_model="qwen3-vl-plus"),
                storage,
                project_id=str(project.id),
                provider_factory=lambda _settings: valid_provider,
            ).review(source_path, visual_pages, initial)
            audit_path = next(
                storage.root.glob(
                    f"projects/{project.id}/provider-calls/"
                    "qwen-symbol/*.json"
                )
            )
            audit_path.unlink()

            class MustNotCallProvider:
                @staticmethod
                def review_symbols(
                    _image: bytes,
                    _prompt: str,
                ) -> VisionResult:
                    raise AssertionError("invalid cache reached visual Provider")

                @staticmethod
                def review_candidate(
                    _image: bytes,
                    _prompt: str,
                ) -> VisionResult:
                    raise AssertionError("invalid cache reached text Provider")

            must_not_call = MustNotCallProvider()

            def provider_factory(_settings: Settings) -> object:
                return must_not_call

            expected_exception = CandidateAdvisorFailure

        advisor = CandidateAdvisor(
            Settings(qwen_model="qwen3-vl-plus"),
            storage,
            project_id=str(project.id),
            provider_factory=provider_factory,
        )

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
    assert {
        "code": error.code,
        "stage": error.stage,
        "category": error.cause_category,
        "severity": error.severity,
    } == {
        "code": expected_code,
        "stage": expected_stage,
        "category": expected_category,
        "severity": "blocking",
    }
    if failure_case == "coverage_conflict":
        assert error.location_ref is not None
        assert error.location_ref.startswith(
            f"asset://projects/{project.id}/inventory/"
        )
        assert storage.resolve_resource_ref(error.location_ref).is_file()
    else:
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


@pytest.mark.parametrize("resolution", ("promote", "ignore"))
def test_visual_no_detection_remains_actionable_source_review(
    db_session: Session,
    tmp_path: Path,
    resolution: str,
) -> None:
    """INT-05 exposes source context without silently creating an item."""
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
    assert entry == {
        "observation_id": observation_id,
        "disposition": "ambiguous",
        "source_location_id": observation_id,
        "coordinates": list(visual.bbox_pdf),
        "candidate_id": None,
        "requires_confirmation": True,
        "symbol_kinds": [],
        "rejection_code": "visual_no_detection",
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
    initial_item_count = len(working.items)

    service = ReviewService(db_session)
    acquire_lock(db_session, working.project_id, "quality-1")
    if resolution == "promote":
        saved = service.apply(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
            command={
                "type": "promote_source",
                "observation_id": observation_id,
                "raw_text": "M6",
                "item_type": "thread",
                "scope": "local_feature",
                "balloon_required": True,
                "page_index": 0,
            },
        )
        saved_entry = next(
            entry
            for entry in saved.coverage["entries"]
            if entry["observation_id"] == observation_id
        )
        assert len(saved.items) == initial_item_count + 1
        assert saved.items[-1]["source_location_ids"] == [observation_id]
        assert saved_entry["candidate_id"] == saved.items[-1]["item_id"]
    else:
        saved = service.apply(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
            command={
                "type": "ignore_source",
                "observation_id": observation_id,
            },
        )
        saved_entry = next(
            entry
            for entry in saved.coverage["entries"]
            if entry["observation_id"] == observation_id
        )
        assert len(saved.items) == initial_item_count
        assert saved_entry["disposition"] == "non_inspection"
    assert saved_entry["requires_confirmation"] is False


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


@pytest.mark.parametrize("resolution", ("promote", "ignore"))
def test_revision_marker_stays_noninspection_until_explicit_promote_source(
    db_session: Session,
    tmp_path: Path,
    resolution: str,
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
    entry = working.coverage["entries"][0]
    assert entry["disposition"] == "non_inspection"
    assert entry["candidate_id"] is None
    assert entry["requires_confirmation"] is True
    assert entry["symbol_kinds"] == ["revision_marker"]
    assert entry["rejection_code"] is None

    service = ReviewService(db_session)
    acquire_lock(db_session, working.project_id, "quality-1")
    if resolution == "promote":
        saved = service.apply(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
            command={
                "type": "promote_source",
                "observation_id": observation_id,
                "raw_text": "REV 1",
                "item_type": "general_requirement",
                "scope": "global_requirement",
                "balloon_required": False,
                "page_index": 0,
            },
        )
        assert len(saved.items) == 1
        assert saved.items[0]["source_type"] == "manual"
        assert saved.coverage["entries"][0]["candidate_id"] == saved.items[0]["item_id"]
    else:
        saved = service.apply(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
            command={
                "type": "ignore_source",
                "observation_id": observation_id,
            },
        )
        assert saved.items == []
        assert saved.coverage["entries"][0]["candidate_id"] is None
    assert saved.coverage["entries"][0]["requires_confirmation"] is False
