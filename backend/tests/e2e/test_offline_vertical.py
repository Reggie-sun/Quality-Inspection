from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree

import fitz
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balloons.renderer import render_ballooned_pdf
from app.balloons.service import BalloonService
from app.candidates.advisor import CandidateAdvisor
from app.candidates.models import AutomaticResult
from app.capabilities.service import (
    CapabilityUnavailable,
    ExportPreflight,
    ProcessingPreflight,
)
from app.db import engine
from app.config import Settings
from app.errors.models import ErrorRecord
from app.exports.models import ExportArtifact, ExportJob
from app.exports.service import ExportService
from app.jobs.idempotency import LogicalJob
from app.pdf.inventory import build_inventory
from app.processing.pipeline import InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.projects.models import Project
from app.projects.state import ProjectState
from app.providers.base import VisionResult
from app.review.locks import acquire_lock
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.review.service import ReviewService
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


ROOT = Path(__file__).resolve().parents[3]
QWEN_FIXTURE = (
    ROOT / ".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json"
)
FAILURE_EVIDENCE_REQUIREMENTS = {
    "provider": {
        "evidence_source": "error_record",
        "status_owner": "logical_job",
        "error_code": "vision_provider_unavailable",
        "recorded_stage": "preflight",
        "error_severity": "blocking",
        "severity_source": "error_record",
    },
    "storage": {
        "evidence_source": "error_record",
        "status_owner": "logical_job",
        "error_code": "storage_unavailable",
        "recorded_stage": "preflight",
        "error_severity": "blocking",
        "severity_source": "error_record",
    },
    "template": {
        "evidence_source": "capability_exception",
        "status_owner": "capability_exception",
        "error_code": "export_template_unavailable",
        "recorded_stage": "export_preflight",
        "error_severity": "fatal",
        "severity_source": "failure_policy",
    },
    "font": {
        "evidence_source": "capability_exception",
        "status_owner": "capability_exception",
        "error_code": "export_font_unavailable",
        "recorded_stage": "export_preflight",
        "error_severity": "fatal",
        "severity_source": "failure_policy",
    },
    "ballooned_pdf": {
        "evidence_source": "error_record",
        "status_owner": "export_job",
        "error_code": "export_artifact_failed",
        "recorded_stage": "export_pdf",
        "error_severity": "fatal",
        "severity_source": "error_record",
    },
    "sip_excel": {
        "evidence_source": "error_record",
        "status_owner": "export_job",
        "error_code": "export_artifact_failed",
        "recorded_stage": "export_excel",
        "error_severity": "fatal",
        "severity_source": "error_record",
    },
    "manifest": {
        "evidence_source": "error_record",
        "status_owner": "export_job",
        "error_code": "export_artifact_failed",
        "recorded_stage": "export_manifest",
        "error_severity": "fatal",
        "severity_source": "error_record",
    },
}
FAILURE_POINTS = set(FAILURE_EVIDENCE_REQUIREMENTS)
ARTIFACT_KINDS = ("ballooned_pdf", "sip_excel", "manifest")
OPERATOR_ID = "d7-t1-reviewer"


class PassingPreflight:
    def check(self) -> None:
        return None


class HealthyRedis:
    @staticmethod
    def ping() -> bool:
        return True


class HealthyInspect:
    @staticmethod
    def ping() -> dict[str, dict[str, str]]:
        return {"fixture-worker": {"ok": "pong"}}


class HealthyControl:
    @staticmethod
    def inspect(*, timeout: int) -> HealthyInspect:
        assert timeout == 1
        return HealthyInspect()


class HealthyCelery:
    control = HealthyControl()


class FailingProbeStorage(LocalFileStorage):
    def probe(self) -> None:
        raise OSError("injected storage probe failure")



@dataclass(frozen=True)
class PreparedVertical:
    source_bytes: bytes
    raw: AutomaticResult
    working: ReviewWorkingCopy
    reviewed: ReviewedResult
    states: tuple[str, ...]
    boundaries: tuple[str, ...]


@dataclass(frozen=True)
class VerticalResult:
    source_page_count: int
    states: tuple[str, ...]
    boundaries: tuple[str, ...]
    raw_automatic_result_id: uuid.UUID
    review_working_copy_id: uuid.UUID
    reviewed_result_id: uuid.UUID
    artifact_reviewed_result_ids: set[uuid.UUID]
    formal_download_kinds: set[str]
    provider_network_connections: int


@dataclass(frozen=True)
class FailureAttempt:
    attempt_id: uuid.UUID
    project_id: uuid.UUID
    failure_point: str
    evidence_source: str
    status_owner: str
    error_code: str
    recorded_stage: str
    severity: str
    severity_source: str
    error_id: uuid.UUID | None = None
    logical_job_id: uuid.UUID | None = None
    export_id: uuid.UUID | None = None


@pytest.fixture
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


class VerticalSystem:
    def __init__(self, session: Session, storage: LocalFileStorage) -> None:
        self.session = session
        self.storage = storage
        self.provider_network_connections = 0
        self._failure_point: str | None = None
        self._attempts: dict[uuid.UUID, FailureAttempt] = {}

    @staticmethod
    def _source_pdf() -> bytes:
        document = fitz.open()
        for raw_text in ("M6", "Ra 3.2"):
            page = document.new_page(width=240, height=180)
            page.insert_text((32, 48), raw_text)
            page.draw_rect(fitz.Rect(20, 24, 180, 120))
        content = document.tobytes(garbage=4, deflate=True, no_new_id=True)
        document.close()
        return content

    def _create_processing_source(self) -> tuple[Project, StoredFile, bytes]:
        project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
        source_bytes = self._source_pdf()
        stored = self.storage.write_verified(
            f"projects/{project.id}/drawing.pdf",
            source_bytes,
            hashlib.sha256(source_bytes).hexdigest(),
        )
        source_file = StoredFile(
            resource_ref=stored.resource_ref,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            mime_type="application/pdf",
        )
        self.session.add_all([project, source_file])
        self.session.commit()
        return project, source_file, source_bytes

    def _vision_provider(self):
        qwen = json.loads(QWEN_FIXTURE.read_text(encoding="utf-8"))["payload"]

        class FixtureVisionProvider:
            @staticmethod
            def review_candidate(_image: bytes, prompt: str) -> VisionResult:
                request = json.loads(prompt)
                raw_text = str(request["raw_text"])
                return VisionResult(
                    request_id=qwen["request_id"],
                    payload={
                        "schema_version": "candidate-review/1",
                        "raw_text": raw_text,
                        "item_type": str(request["expected_type"]),
                        "normalized_text": raw_text,
                        "requires_confirmation": True,
                    },
                    usage=dict(qwen["usage"]),
                )

        return FixtureVisionProvider()

    def _block_provider_network(self, *_args, **_kwargs):
        self.provider_network_connections += 1
        raise AssertionError("sanitized Provider fixtures attempted network access")

    @staticmethod
    def _forbidden_ocr_provider(_settings: Settings):
        raise AssertionError("native vertical fixture must not construct OCR Provider")

    def _recognition(self, project_id: uuid.UUID) -> RuntimeRecognition:
        settings = Settings(storage_root=self.storage.root)
        advisor = CandidateAdvisor(
            settings,
            self.storage,
            project_id=str(project_id),
            provider_factory=lambda _settings: self._vision_provider(),
        )
        return RuntimeRecognition(
            settings,
            provider_factory=self._forbidden_ocr_provider,
            advisor=advisor,
        )

    def _run_processing(
        self,
        project: Project,
        source_file: StoredFile,
        task_key: str,
    ) -> None:
        recognition = self._recognition(project.id)
        with (
            patch.object(socket, "socket", new=self._block_provider_network),
            patch.object(
                socket,
                "create_connection",
                new=self._block_provider_network,
            ),
            patch.object(socket, "getaddrinfo", new=self._block_provider_network),
        ):
            InventoryPipeline(
                self.session,
                self.storage,
                PassingPreflight(),
                inventory_builder=recognition.build_inventory,
                candidate_snapshot_builder=recognition.build_candidate_snapshot,
            ).run(
                str(project.id),
                source_file.resource_ref,
                task_key,
            )

    def prepare_reviewed(self) -> PreparedVertical:
        project, source_file, source_bytes = self._create_processing_source()
        states = [str(ProjectState(project.state))]
        boundaries: list[str] = []

        boundaries.append("InventoryPipeline.run")
        self._run_processing(
            project,
            source_file,
            f"process:d7-t1:{project.id}",
        )
        project = self.session.get(Project, project.id, populate_existing=True)
        assert project is not None
        states.append(str(ProjectState(project.state)))
        raw = self.session.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        assert raw is not None
        assert raw.provider_call_ids == ["fixture-qwen-request-id"]
        assert any(
            candidate.get("advisor_review", {}).get("validated") is True
            for candidate in raw.candidates
        )

        review_service = ReviewService(self.session, storage=self.storage)
        boundaries.append("ReviewService.create_from_raw")
        working = review_service.create_from_raw(raw.id)
        states.append(str(ProjectState(self.session.get(Project, project.id).state)))
        acquire_lock(self.session, project.id, OPERATOR_ID)

        boundaries.append("ReviewService.apply")
        for page_number, item in enumerate(working.items, start=1):
            working = review_service.apply(
                working.id,
                expected_version=working.version,
                operator_id=OPERATOR_ID,
                command={
                    "type": "set_sip_detail_fields",
                    "item_id": str(item["item_id"]),
                    "inspection_item": str(
                        item.get("normalized_text", item["raw_text"])
                    ),
                    "inspection_standard": "per approved drawing",
                    "inspection_method": "thread gauge",
                    "key_dimension": "yes",
                    "inspection_role": "IPQC",
                    "source_page": page_number,
                },
            )
            if item.get("balloon_required") is None:
                working = review_service.apply(
                    working.id,
                    expected_version=working.version,
                    operator_id=OPERATOR_ID,
                    command={
                        "type": "set_balloon_required",
                        "item_id": str(item["item_id"]),
                        "balloon_required": True,
                    },
                )
            if item.get("requires_confirmation") is True:
                working = review_service.apply(
                    working.id,
                    expected_version=working.version,
                    operator_id=OPERATOR_ID,
                    command={
                        "type": "resolve_confirmation",
                        "item_id": str(item["item_id"]),
                        "accepted": True,
                    },
                )
        working = review_service.apply(
            working.id,
            expected_version=working.version,
            operator_id=OPERATOR_ID,
            command={
                "type": "set_sip_metadata",
                "material_code": "D7-T1-MAT",
                "material_name": "offline vertical fixture",
                "drawing_number": "D7-T1-002",
                "material": "SUS304",
                "revision": "A",
            },
        )

        boundaries.append("ReviewService.freeze_items")
        working = review_service.freeze_items(
            working.id,
            expected_version=working.version,
            operator_id=OPERATOR_ID,
        )
        boundaries.append("BalloonService.generate_formal")
        BalloonService(self.session, storage=self.storage).generate_formal(
            project.id,
            expected_version=working.version,
            operator_id=OPERATOR_ID,
        )
        boundaries.append("ReviewService.confirm")
        reviewed = review_service.confirm(
            working.id,
            expected_version=working.version,
            operator_id=OPERATOR_ID,
        )
        project = self.session.get(Project, project.id, populate_existing=True)
        assert project is not None
        states.append(str(ProjectState(project.state)))
        return PreparedVertical(
            source_bytes=source_bytes,
            raw=raw,
            working=working,
            reviewed=reviewed,
            states=tuple(states),
            boundaries=tuple(boundaries),
        )

    def run_offline(self) -> VerticalResult:
        prepared = self.prepare_reviewed()
        observed_export_states: list[str] = []

        def observing_pdf_renderer(content, balloons, font_path):
            running = self.session.scalar(
                select(ExportJob).where(
                    ExportJob.reviewed_result_id == prepared.reviewed.id,
                    ExportJob.status == "running",
                )
            )
            assert running is not None
            observed_export_states.append("exporting")
            return render_ballooned_pdf(content, balloons, font_path)

        boundaries = [*prepared.boundaries, "ExportService.create"]
        export_service = ExportService(
            self.session,
            storage=self.storage,
            pdf_renderer=observing_pdf_renderer,
        )
        export = export_service.create(prepared.reviewed.id)
        assert export.status == "success"
        observed_export_states.append("export_succeeded")
        artifacts = export_service.artifacts(export.id)
        downloads = {
            kind
            for kind in ARTIFACT_KINDS
            if export_service.download_ref(export.id, kind) is not None
        }
        with fitz.open(stream=prepared.source_bytes, filetype="pdf") as document:
            source_page_count = document.page_count
        return VerticalResult(
            source_page_count=source_page_count,
            states=(*prepared.states, *observed_export_states),
            boundaries=tuple(boundaries),
            raw_automatic_result_id=prepared.raw.id,
            review_working_copy_id=prepared.working.id,
            reviewed_result_id=prepared.reviewed.id,
            artifact_reviewed_result_ids={
                artifact.reviewed_result_id for artifact in artifacts
            },
            formal_download_kinds=downloads,
            provider_network_connections=self.provider_network_connections,
        )

    def replace_dependency_with_failure(self, failure_point: str) -> None:
        if failure_point not in FAILURE_POINTS:
            raise ValueError(f"unknown failure point: {failure_point}")
        self._failure_point = failure_point

    def export(self, reviewed_result_id: uuid.UUID) -> uuid.UUID:
        if self._failure_point is None:
            raise RuntimeError("failure dependency was not replaced")
        if self._failure_point in {"provider", "storage"}:
            return self._processing_failure(reviewed_result_id, self._failure_point)
        if self._failure_point in {"template", "font"}:
            return self._preflight_failure(reviewed_result_id, self._failure_point)
        return self._artifact_failure(reviewed_result_id, self._failure_point)

    def _processing_preflight(self, failure_point: str) -> ProcessingPreflight:
        dependency_storage = (
            FailingProbeStorage(self.storage.root)
            if failure_point == "storage"
            else self.storage
        )
        return ProcessingPreflight(
            dependency_storage,
            HealthyRedis(),
            HealthyCelery(),
            ocr_configured=True,
            vision_configured=failure_point != "provider",
        )

    def _processing_failure(
        self,
        _reviewed_result_id: uuid.UUID,
        failure_point: str,
    ) -> uuid.UUID:
        project, source_file, _source_bytes = self._create_processing_source()
        task_key = f"process:d7-t1-failure:{project.id}"
        caught: CapabilityUnavailable | None = None
        try:
            InventoryPipeline(
                self.session,
                self.storage,
                self._processing_preflight(failure_point),
                inventory_builder=build_inventory,
            ).run(
                str(project.id),
                source_file.resource_ref,
                task_key,
            )
        except CapabilityUnavailable as exc:
            caught = exc
        else:
            raise AssertionError(f"{failure_point} failure did not abort processing")
        expected = FAILURE_EVIDENCE_REQUIREMENTS[failure_point]
        assert caught is not None
        assert caught.code == expected["error_code"]
        error = self.session.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        assert error is not None
        assert error.code == caught.code
        logical_job = self.session.scalar(
            select(LogicalJob).where(
                LogicalJob.project_id == str(project.id),
                LogicalJob.logical_task_key == task_key,
            )
        )
        assert logical_job is not None
        assert logical_job.status == "failed"
        assert self.session.scalar(
            select(AutomaticResult.id).where(AutomaticResult.project_id == project.id)
        ) is None
        attempt_id = uuid.uuid4()
        self._attempts[attempt_id] = FailureAttempt(
            attempt_id=attempt_id,
            project_id=project.id,
            failure_point=failure_point,
            evidence_source="error_record",
            status_owner="logical_job",
            error_code=error.code,
            recorded_stage=error.stage,
            severity=error.severity,
            severity_source="error_record",
            error_id=error.id,
            logical_job_id=logical_job.id,
        )
        return attempt_id

    def _preflight_failure(
        self,
        reviewed_result_id: uuid.UUID,
        failure_point: str,
    ) -> uuid.UUID:
        backend_root = Path(__file__).resolve().parents[2]
        missing = self.storage.root / f"missing-{failure_point}"
        preflight = ExportPreflight(
            template_path=(
                missing
                if failure_point == "template"
                else backend_root / "assets/templates/sip-v1.xlsx"
            ),
            mapping_path=backend_root / "assets/templates/sip-v1.mapping.json",
            font_path=(
                missing
                if failure_point == "font"
                else backend_root / "assets/fonts/DejaVuSans.ttf"
            ),
            font_license_path=backend_root / "assets/fonts/LICENSE-DejaVu.txt",
        )
        caught: CapabilityUnavailable | None = None
        try:
            ExportService(
                self.session,
                storage=self.storage,
                preflight=preflight,
            ).create(reviewed_result_id)
        except CapabilityUnavailable as exc:
            caught = exc
        else:
            raise AssertionError(f"{failure_point} failure did not abort export")
        reviewed = self.session.get(ReviewedResult, reviewed_result_id)
        assert reviewed is not None
        expected = FAILURE_EVIDENCE_REQUIREMENTS[failure_point]
        assert caught is not None
        assert caught.code == expected["error_code"]
        assert self.session.scalar(
            select(ExportJob.id).where(ExportJob.project_id == reviewed.project_id)
        ) is None
        assert self.session.scalar(
            select(ExportArtifact.id)
            .join(ExportJob, ExportJob.id == ExportArtifact.export_id)
            .where(ExportJob.project_id == reviewed.project_id)
        ) is None
        attempt_id = uuid.uuid4()
        self._attempts[attempt_id] = FailureAttempt(
            attempt_id=attempt_id,
            project_id=reviewed.project_id,
            failure_point=failure_point,
            evidence_source="capability_exception",
            status_owner="capability_exception",
            error_code=caught.code,
            recorded_stage="export_preflight",
            severity=expected["error_severity"],
            severity_source="failure_policy",
        )
        return attempt_id

    def _artifact_failure(
        self,
        reviewed_result_id: uuid.UUID,
        failure_point: str,
    ) -> uuid.UUID:
        def raise_injected(*_args, **_kwargs):
            raise RuntimeError(f"injected {failure_point} failure")

        replacements = {
            "ballooned_pdf": {"pdf_renderer": raise_injected},
            "sip_excel": {"excel_renderer": raise_injected},
            "manifest": {"manifest_serializer": raise_injected},
        }
        export = ExportService(
            self.session,
            storage=self.storage,
            **replacements[failure_point],
        ).create(reviewed_result_id)
        assert export.status == "failed"
        error = self.session.get(ErrorRecord, export.error_id)
        assert error is not None
        self._attempts[export.id] = FailureAttempt(
            attempt_id=export.id,
            project_id=export.project_id,
            failure_point=failure_point,
            evidence_source="error_record",
            status_owner="export_job",
            error_code=error.code,
            recorded_stage=error.stage,
            severity=error.severity,
            severity_source="error_record",
            error_id=error.id,
            export_id=export.id,
        )
        return export.id

    def export_status(self, attempt_id: uuid.UUID) -> str:
        attempt = self._attempts[attempt_id]
        if attempt.export_id is not None:
            export = self.session.get(ExportJob, attempt.export_id)
            assert export is not None
            return export.status
        if attempt.logical_job_id is not None:
            logical_job = self.session.get(LogicalJob, attempt.logical_job_id)
            assert logical_job is not None
            return logical_job.status
        if attempt.evidence_source == "capability_exception" and attempt.error_code:
            return "failed"
        raise AssertionError("failure attempt has no application status evidence")

    def successful_exports(self, attempt_id: uuid.UUID) -> list[uuid.UUID]:
        attempt = self._attempts[attempt_id]
        return list(
            self.session.scalars(
                select(ExportJob.id).where(
                    ExportJob.project_id == attempt.project_id,
                    ExportJob.status == "success",
                )
            )
        )

    def formal_downloads(self, attempt_id: uuid.UUID) -> list[str]:
        attempt = self._attempts[attempt_id]
        export_ids = list(
            self.session.scalars(
                select(ExportJob.id).where(
                    ExportJob.project_id == attempt.project_id
                )
            )
        )
        service = ExportService(self.session, storage=self.storage)
        return [
            resource_ref
            for export_id in export_ids
            for kind in ARTIFACT_KINDS
            if (resource_ref := service.download_ref(export_id, kind)) is not None
        ]

    def published_refs(self, attempt_id: uuid.UUID) -> list[str]:
        attempt = self._attempts[attempt_id]
        return list(
            self.session.scalars(
                select(ExportArtifact.published_ref)
                .join(ExportJob, ExportJob.id == ExportArtifact.export_id)
                .where(
                    ExportJob.project_id == attempt.project_id,
                    ExportArtifact.published_ref.is_not(None),
                )
            )
        )

    def processing_result_counts(self, attempt_id: uuid.UUID) -> dict[str, int]:
        project_id = self._attempts[attempt_id].project_id
        models = {
            "automatic_results": AutomaticResult,
            "review_working_copies": ReviewWorkingCopy,
            "reviewed_results": ReviewedResult,
            "export_jobs": ExportJob,
        }
        return {
            name: int(
                self.session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.project_id == project_id)
                )
                or 0
            )
            for name, model in models.items()
        }

    def failure_evidence(self, attempt_id: uuid.UUID) -> dict[str, str]:
        attempt = self._attempts[attempt_id]
        error = (
            self.session.get(ErrorRecord, attempt.error_id)
            if attempt.error_id is not None
            else None
        )
        project = self.session.get(Project, attempt.project_id)
        assert project is not None
        return {
            "project_id": str(attempt.project_id),
            "project_state": str(ProjectState(project.state)),
            "evidence_source": attempt.evidence_source,
            "status_owner": attempt.status_owner,
            "error_code": error.code if error is not None else attempt.error_code,
            "recorded_stage": (
                error.stage if error is not None else attempt.recorded_stage
            ),
            "error_severity": (
                error.severity if error is not None else attempt.severity
            ),
            "severity_source": attempt.severity_source,
        }

    def export_error(self, attempt_id: uuid.UUID) -> dict[str, str]:
        attempt = self._attempts[attempt_id]
        evidence = self.failure_evidence(attempt_id)
        return {
            "stage": attempt.failure_point,
            "severity": evidence["error_severity"],
            "recorded_stage": evidence["recorded_stage"],
        }


@pytest.fixture
def vertical_system(db_session: Session, tmp_path: Path) -> VerticalSystem:
    return VerticalSystem(db_session, LocalFileStorage(tmp_path / "storage"))


@pytest.fixture
def frozen_reviewed_result(vertical_system: VerticalSystem) -> ReviewedResult:
    return vertical_system.prepare_reviewed().reviewed


def _load_harness_module(filename: str, module_name: str) -> ModuleType:
    path = ROOT / ".agent/harness/scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failure_proof_policy() -> dict[str, object]:
    return {
        "formal_success_forbidden_when": ["fatal", "blocking"],
        "failure_proof": {
            "mode": "failure",
            "scope": "task",
            "task_id": "D7-T1",
            "contract_id": "P0-ACC-007",
            "selector": "phase://failure/no-silent-success",
            "test_path": "backend/tests/e2e/test_no_silent_success.py",
            "report_ref": "reports/no-silent-success.json",
            "junit_ref": "reports/no-silent-success.junit.xml",
            "failure_points": list(FAILURE_EVIDENCE_REQUIREMENTS),
            "zero_count_properties": [
                "successful_exports",
                "formal_downloads",
                "published_refs",
            ],
            "allowed_error_severities": ["fatal", "blocking"],
            "evidence_requirements": FAILURE_EVIDENCE_REQUIREMENTS,
        },
    }


def _failure_proof_case(point: str) -> dict[str, str]:
    return {
        "test_name": f"test_p0_acc_007_no_silent_success[{point}]",
        "failure_point": point,
        "export_status": "failed",
        "successful_exports": "0",
        "formal_downloads": "0",
        "published_refs": "0",
        **FAILURE_EVIDENCE_REQUIREMENTS[point],
    }


def _write_junit(
    path: Path,
    cases: list[dict[str, str]],
    *,
    failures: int = 0,
) -> None:
    suites = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(
        suites,
        "testsuite",
        tests=str(len(cases)),
        failures=str(failures),
        errors="0",
        skipped="0",
    )
    for case in cases:
        test_case = ElementTree.SubElement(
            suite,
            "testcase",
            name=case["test_name"],
        )
        properties = ElementTree.SubElement(test_case, "properties")
        for name, value in case.items():
            if name != "test_name":
                ElementTree.SubElement(
                    properties,
                    "property",
                    name=name,
                    value=value,
                )
    ElementTree.ElementTree(suites).write(path, encoding="unicode")


def _failure_proof_inputs(
    tmp_path: Path,
    *,
    result_state: str = "passed",
    exit_code: int = 0,
    include_junit: bool = True,
) -> tuple[ModuleType, dict, dict, dict, dict, Path]:
    receipt = _load_harness_module(
        "generate-receipt.py",
        f"d7_t1_receipt_{uuid.uuid4().hex}",
    )
    run_id = "20260722T000000000000Z-00000000"
    run_dir = tmp_path / ".agent/harness/runs" / run_id
    reports = run_dir / "reports"
    reports.mkdir(parents=True)
    cases = [
        _failure_proof_case(point) for point in FAILURE_EVIDENCE_REQUIREMENTS
    ]
    report_ref = "reports/no-silent-success.json"
    junit_ref = "reports/no-silent-success.junit.xml"
    report = {
        "schema_version": "failure-proof/1",
        "run_id": run_id,
        "selector": "phase://failure/no-silent-success",
        "command": [
            "/controlled/python",
            "-m",
            "pytest",
            "backend/tests/e2e/test_no_silent_success.py",
            "-q",
        ],
        "exit_code": exit_code,
        "result_state": result_state,
        "junit_ref": junit_ref if include_junit else None,
        "pytest_summary": (
            {"tests": 7, "failures": 0, "errors": 0, "skipped": 0}
            if result_state == "passed"
            else None
        ),
        "failure_points": list(FAILURE_EVIDENCE_REQUIREMENTS),
        "cases": cases,
        "validation_errors": (
            [] if result_state == "passed" else ["controlled proof failure"]
        ),
    }
    (run_dir / report_ref).write_text(json.dumps(report), encoding="utf-8")
    if include_junit:
        _write_junit(run_dir / junit_ref, cases)
    result = {
        "run_id": run_id,
        "p0_contract_id": "P0-ACC-007",
        "command": "phase://failure/no-silent-success",
        "exit_code": exit_code,
        "result_state": result_state,
        "artifact_refs": [report_ref, *([junit_ref] if include_junit else [])],
    }
    run = {
        "run_id": run_id,
        "mode": "failure",
        "scope": "task",
        "task_id": "D7-T1",
        "selected_contract_ids": ["P0-ACC-007"],
    }
    contracts = {
        "P0-ACC-007": {
            "blocking_level": "fatal",
            "verification_selector": "phase://failure/no-silent-success",
        }
    }
    return receipt, run, {"P0-ACC-007": result}, contracts, _failure_proof_policy(), run_dir


@pytest.mark.parametrize(
    "mutation",
    ("missing", "malformed", "mismatched", "tampered"),
)
def test_p0_acc_007_receipt_rejects_invalid_junit(
    tmp_path: Path,
    mutation: str,
) -> None:
    receipt, run, results, contracts, policy, run_dir = _failure_proof_inputs(
        tmp_path
    )
    junit_path = run_dir / "reports/no-silent-success.junit.xml"
    if mutation == "missing":
        junit_path.unlink()
    elif mutation == "malformed":
        junit_path.write_text("<not-junit", encoding="utf-8")
    else:
        tree = ElementTree.parse(junit_path)
        if mutation == "mismatched":
            suite = tree.find(".//testsuite")
            assert suite is not None
            suite.set("tests", "6")
        else:
            published_ref = next(
                item
                for item in tree.findall(".//property")
                if item.attrib.get("name") == "published_refs"
            )
            published_ref.set("value", "1")
        tree.write(junit_path, encoding="unicode")

    with pytest.raises(ValueError, match="JUnit|missing"):
        receipt._validate_failure_proof(
            tmp_path,
            run,
            results,
            contracts,
            policy,
        )


def test_p0_acc_007_failed_proof_remains_receiptable(tmp_path: Path) -> None:
    receipt, run, results, contracts, policy, _run_dir = _failure_proof_inputs(
        tmp_path,
        result_state="failed",
        exit_code=1,
        include_junit=False,
    )

    receipt._validate_failure_proof(
        tmp_path,
        run,
        results,
        contracts,
        policy,
    )


def test_p0_acc_007_failed_selector_run_is_sealed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_harness_module(
        "run-p0.py",
        f"d7_t1_runner_{uuid.uuid4().hex}",
    )
    runs = tmp_path / "runs"
    mirror = {
        "contract_definition_hash": "0" * 64,
        "status_projection_hash": "1" * 64,
        "contracts": [
            {
                "p0_contract_id": "P0-ACC-007",
                "task_id": "D7-T1",
                "verification_selector": "phase://failure/no-silent-success",
            }
        ],
    }
    identity = {
        "algorithm": "sha256",
        "digest": "2" * 64,
        "components": ["controlled"],
    }
    receipt_stub = SimpleNamespace(
        provider_network_enabled=lambda: False,
        check_contract_authority=lambda _root: None,
        load_policies=lambda _root: {},
        validate_schema=lambda *_args: None,
        code_identity=lambda _root: identity,
        config_identity=lambda *_args: identity,
        input_identity=lambda *_args: identity,
        policy_versions=lambda _policies: {},
        build_receipt=lambda *_args: {"overall_verdict": "failed"},
    )
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "RUNS", runs)
    monkeypatch.setattr(runner, "MIRROR_PATH", tmp_path / "mirror.json")
    monkeypatch.setattr(runner, "BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(runner, "_receipt_module", lambda: receipt_stub)
    monkeypatch.setattr(
        runner,
        "_load_json",
        lambda path: mirror if path == runner.MIRROR_PATH else {"bindings": []},
    )
    monkeypatch.setattr(runner, "_git_revision", lambda: "controlled")
    monkeypatch.setattr(
        runner,
        "_execute_selector",
        lambda _selector, _mode: {
            "exit_code": 1,
            "result_state": "failed",
            "started_at": "2026-07-22T00:00:00Z",
            "completed_at": "2026-07-22T00:00:01Z",
            "output": "controlled failure",
        },
    )

    run_id, verdict = runner.run_task("failure", "task", "D7-T1")
    run_dir = runs / run_id
    try:
        assert verdict == "failed"
        assert (run_dir / "receipt.json").is_file()
        write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        assert not run_dir.stat().st_mode & write_bits
        assert not (run_dir / "receipt.json").stat().st_mode & write_bits
    finally:
        for path in sorted(run_dir.rglob("*"), reverse=True):
            path.chmod(0o755 if path.is_dir() else 0o644)
        run_dir.chmod(0o755)


def test_p0_acc_007_offline_vertical_chain_uses_public_service_boundaries(
    vertical_system,
) -> None:
    """P0-ACC-007 proves the sanitized offline chain reaches atomic success."""
    result = vertical_system.run_offline()

    assert result.source_page_count == 2
    assert result.states == (
        "processing",
        "ready_for_edit",
        "editing",
        "reviewed",
        "exporting",
        "export_succeeded",
    )
    assert result.boundaries == (
        "InventoryPipeline.run",
        "ReviewService.create_from_raw",
        "ReviewService.apply",
        "ReviewService.freeze_items",
        "BalloonService.generate_formal",
        "ReviewService.confirm",
        "ExportService.create",
    )
    assert len(
        {
            result.raw_automatic_result_id,
            result.review_working_copy_id,
            result.reviewed_result_id,
        }
    ) == 3
    assert result.artifact_reviewed_result_ids == {result.reviewed_result_id}
    assert result.formal_download_kinds == {
        "ballooned_pdf",
        "sip_excel",
        "manifest",
    }
    assert result.provider_network_connections == 0
