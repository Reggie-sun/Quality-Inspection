from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import fitz
from openpyxl import load_workbook
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.balloons.renderer import FrozenBalloon, render_ballooned_pdf
from app.candidates.models import AutomaticResult
from app.capabilities.service import (
    APPROVED_BALLOON_FONT_SHA256,
    ExportPreflight,
)
from app.config import get_settings
from app.errors.models import ErrorRecord
from app.exports.excel import REQUIRED_METADATA_FIELDS, render_sip_workbook
from app.exports.manifest import ArtifactDigest, ExportManifest, sha256_bytes
from app.exports.models import ExportArtifact, ExportJob
from app.exports.naming import safe_stem
from app.exports.template_registry import (
    APPROVED_MAPPING_VERSION,
    APPROVED_TEMPLATE_VERSION,
    TemplateRegistration,
)
from app.jobs.idempotency import (
    LogicalJob,
    claim_logical_job,
    claim_logical_job_failure,
    complete_logical_job,
)
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


RENDERER_VERSION = "balloon-pdf/1"
MANIFEST_SCHEMA_VERSION = "export-manifest/1"
_DETAIL_FIELDS = {
    "inspection_item",
    "inspection_standard",
    "inspection_method",
    "key_dimension",
    "inspection_role",
    "source_page",
}
_DETAIL_CONFIRMED = "sip_detail_fields_confirmed"
_ARTIFACT_KINDS = {"ballooned_pdf", "sip_excel", "manifest"}

PdfRenderer = Callable[[bytes, list[FrozenBalloon], Path], bytes]
ExcelRenderer = Callable[
    [
        Path,
        TemplateRegistration,
        dict[str, object],
        list[dict[str, object]],
        list[Path],
    ],
    bytes,
]
ManifestSerializer = Callable[[ExportManifest], bytes]


class ExportNotFound(LookupError):
    pass


class ExportInputUnavailable(RuntimeError):
    pass


class ExportInProgress(RuntimeError):
    pass


@dataclass(frozen=True)
class _SourcePdf:
    content: bytes
    sha256: str
    filename: str


def assert_export_counts(
    reviewed_items: list[dict[str, Any]],
    balloons: list[dict[str, Any]],
    excel_rows: list[dict[str, object]],
) -> None:
    active_items = [item for item in reviewed_items if item.get("active", True)]
    required = [
        item for item in active_items if item.get("balloon_required") is True
    ]
    if len(excel_rows) != len(active_items):
        raise ValueError("excel detail count mismatch")
    if len(balloons) != len(required):
        raise ValueError("balloon count mismatch")
    pdf_numbers = [balloon["formal_number"] for balloon in balloons]
    excel_numbers = [
        row["balloon_number"]
        for row in excel_rows
        if row["balloon_number"] != ""
    ]
    if sorted(pdf_numbers) != sorted(excel_numbers):
        raise ValueError("PDF and Excel balloon numbers differ")


def assert_artifact_identity(
    reviewed_result_id: uuid.UUID,
    artifacts: list[ExportArtifact],
    manifest_content: bytes,
) -> None:
    expected = str(reviewed_result_id)
    if any(str(artifact.reviewed_result_id) != expected for artifact in artifacts):
        raise ValueError("export artifacts use different reviewed results")
    try:
        payload = json.loads(manifest_content.decode("utf-8"))
        manifest_artifacts = payload["artifacts"]
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("export manifest identity is invalid") from error
    if (
        payload.get("reviewed_result_id") != expected
        or not isinstance(manifest_artifacts, list)
        or any(
            not isinstance(artifact, dict)
            or artifact.get("reviewed_result_id") != expected
            for artifact in manifest_artifacts
        )
    ):
        raise ValueError("export manifest uses a different reviewed result")


class ExportService:
    def __init__(
        self,
        session: Session,
        *,
        storage: LocalFileStorage | None = None,
        preflight: Any | None = None,
        pdf_renderer: PdfRenderer = render_ballooned_pdf,
        excel_renderer: ExcelRenderer = render_sip_workbook,
        manifest_serializer: ManifestSerializer | None = None,
    ) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.session = session
        self.storage = storage or LocalFileStorage(get_settings().storage_root)
        self.template_path = backend_root / "assets/templates/sip-v1.xlsx"
        self.mapping_path = backend_root / "assets/templates/sip-v1.mapping.json"
        self.font_path = backend_root / "assets/fonts/DejaVuSans.ttf"
        self.font_license_path = backend_root / "assets/fonts/LICENSE-DejaVu.txt"
        self.preflight = preflight or ExportPreflight(
            template_path=self.template_path,
            mapping_path=self.mapping_path,
            font_path=self.font_path,
            font_license_path=self.font_license_path,
        )
        self.pdf_renderer = pdf_renderer
        self.excel_renderer = excel_renderer
        self.manifest_serializer = manifest_serializer or (
            lambda manifest: manifest.to_bytes()
        )

    def create(
        self,
        reviewed_result_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
    ) -> ExportJob:
        reviewed = self.session.get(ReviewedResult, reviewed_result_id)
        if reviewed is None:
            raise ExportNotFound(
                f"reviewed result {reviewed_result_id} was not found"
            )
        if project_id is not None and reviewed.project_id != project_id:
            raise ExportNotFound(
                f"reviewed result {reviewed_result_id} was not found"
            )

        logical_job = claim_logical_job(
            self.session,
            project_id=str(reviewed.project_id),
            logical_task_key=self._logical_task_key(reviewed.id),
        )
        existing = self._existing_export(logical_job, reviewed.id)
        if existing is not None:
            return existing

        source = self._source_pdf(reviewed)
        self.storage.probe()
        registration = self.preflight.check()
        if (
            registration.template_version != APPROVED_TEMPLATE_VERSION
            or registration.mapping_version != APPROVED_MAPPING_VERSION
        ):
            raise ExportInputUnavailable("approved export identity changed")
        frozen_balloons = self._frozen_balloons(reviewed.balloons)
        active_balloons = self._active_balloon_snapshots(reviewed.balloons)
        sip_metadata = self._sip_metadata(reviewed.sip_metadata)
        excel_rows = self._excel_rows(reviewed.items, active_balloons)
        assert_export_counts(reviewed.items, active_balloons, excel_rows)
        claimed_export = self._claim_execution(logical_job, reviewed.id)
        if claimed_export is not None:
            return claimed_export

        export = ExportJob(
            project_id=reviewed.project_id,
            reviewed_result_id=reviewed.id,
            status="running",
            template_version=registration.template_version,
            mapping_version=registration.mapping_version,
            renderer_version=RENDERER_VERSION,
        )
        self.session.add(export)
        self.session.commit()
        self.session.refresh(export)

        stage = "pdf"
        try:
            filenames = self._filenames(source.filename)

            pdf_content = self.pdf_renderer(
                source.content,
                frozen_balloons,
                self.font_path,
            )
            pdf_artifact = self._stage_artifact(
                export,
                "ballooned_pdf",
                filenames["ballooned_pdf"],
                pdf_content,
            )
            staged_pdf = self.storage.read_bytes(pdf_artifact.staging_ref)
            source_page_count = self._validate_pdf(
                source.content,
                staged_pdf,
                frozen_balloons,
            )

            stage = "excel"
            with tempfile.TemporaryDirectory(prefix="qi-export-pages-") as temp_dir:
                page_images = self._rasterize_pdf(
                    staged_pdf,
                    Path(temp_dir),
                )
                excel_content = self.excel_renderer(
                    self.template_path,
                    registration,
                    sip_metadata,
                    excel_rows,
                    page_images,
                )
            excel_artifact = self._stage_artifact(
                export,
                "sip_excel",
                filenames["sip_excel"],
                excel_content,
            )
            staged_excel = self.storage.read_bytes(excel_artifact.staging_ref)
            self._validate_excel(
                staged_excel,
                registration,
                sip_metadata,
                excel_rows,
            )

            stage = "manifest"
            manifest = self._manifest(
                export,
                reviewed,
                source,
                registration,
                source_page_count,
                filenames,
                pdf_artifact,
                excel_artifact,
                active_balloons,
            )
            manifest_content = self.manifest_serializer(manifest)
            self._validate_manifest(manifest_content, manifest)
            manifest_artifact = self._stage_artifact(
                export,
                "manifest",
                filenames["manifest"],
                manifest_content,
            )
            staged_manifest = self.storage.read_bytes(manifest_artifact.staging_ref)
            self._validate_manifest(staged_manifest, manifest)
            assert_artifact_identity(
                reviewed.id,
                [pdf_artifact, excel_artifact, manifest_artifact],
                staged_manifest,
            )

            stage = "publish"
            contents = {
                "ballooned_pdf": staged_pdf,
                "sip_excel": staged_excel,
                "manifest": staged_manifest,
            }
            artifacts = {
                "ballooned_pdf": pdf_artifact,
                "sip_excel": excel_artifact,
                "manifest": manifest_artifact,
            }
            published_refs: dict[str, str] = {}
            for kind in ("ballooned_pdf", "sip_excel", "manifest"):
                stored = self.storage.write_verified(
                    f"exports/{export.id}/{filenames[kind]}",
                    contents[kind],
                    artifacts[kind].sha256,
                )
                published_refs[kind] = stored.resource_ref

            for kind, artifact in artifacts.items():
                artifact.published_ref = published_refs[kind]
            export.status = "success"
            export.completed_at = datetime.now(timezone.utc)
            self.session.commit()

            stage = "logical_job"
            complete_logical_job(
                self.session,
                job_id=logical_job.id,
                result_ref=f"export://{export.id}",
            )
            self.session.refresh(export)
            return export
        except Exception as error:
            return self._fail(export.id, logical_job.id, stage, error)

    def get(self, export_id: uuid.UUID) -> ExportJob:
        export = self.session.get(ExportJob, export_id)
        if export is None:
            raise ExportNotFound(f"export {export_id} was not found")
        return export

    def artifacts(self, export_id: uuid.UUID) -> list[ExportArtifact]:
        self.get(export_id)
        return list(
            self.session.scalars(
                select(ExportArtifact)
                .where(ExportArtifact.export_id == export_id)
                .order_by(ExportArtifact.kind)
            )
        )

    def download_ref(self, export_id: uuid.UUID, kind: str) -> str | None:
        if kind not in _ARTIFACT_KINDS:
            return None
        return self.session.scalar(
            select(ExportArtifact.published_ref)
            .join(ExportJob, ExportJob.id == ExportArtifact.export_id)
            .where(
                ExportArtifact.export_id == export_id,
                ExportArtifact.kind == kind,
                ExportArtifact.published_ref.is_not(None),
                ExportJob.status == "success",
            )
        )

    @staticmethod
    def _logical_task_key(reviewed_result_id: uuid.UUID) -> str:
        return (
            f"export:{reviewed_result_id}:"
            f"{APPROVED_TEMPLATE_VERSION}:"
            f"{APPROVED_MAPPING_VERSION}:{RENDERER_VERSION}"
        )

    def _existing_export(
        self,
        logical_job: LogicalJob,
        reviewed_result_id: uuid.UUID,
    ) -> ExportJob | None:
        if logical_job.status == "succeeded":
            if not logical_job.result_ref or not logical_job.result_ref.startswith(
                "export://"
            ):
                raise ExportInputUnavailable(
                    "successful export job has an invalid result reference"
                )
            try:
                export_id = uuid.UUID(logical_job.result_ref.removeprefix("export://"))
            except ValueError as error:
                raise ExportInputUnavailable(
                    "successful export job has an invalid result reference"
                ) from error
            export = self.session.get(ExportJob, export_id)
            if export is None or export.status != "success":
                raise ExportInputUnavailable(
                    "successful export job has no published export"
                )
            return export
        if logical_job.status == "failed":
            return self.session.scalar(
                select(ExportJob)
                .where(
                    ExportJob.reviewed_result_id == reviewed_result_id,
                    ExportJob.status == "failed",
                )
                .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
            )
        if logical_job.status not in {"pending", "processing"}:
            raise ExportInputUnavailable("logical export job cannot run")
        return None

    def _claim_execution(
        self,
        logical_job: LogicalJob,
        reviewed_result_id: uuid.UUID,
    ) -> ExportJob | None:
        claimed_id = self.session.execute(
            update(LogicalJob)
            .where(
                LogicalJob.id == logical_job.id,
                LogicalJob.status == "pending",
                LogicalJob.result_ref.is_(None),
            )
            .values(status="processing")
            .returning(LogicalJob.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        self.session.commit()
        if claimed_id is not None:
            return None

        contender = self.session.get(
            LogicalJob,
            logical_job.id,
            populate_existing=True,
        )
        if contender is None:
            raise ExportInputUnavailable("logical export job disappeared")
        existing = self._existing_export(contender, reviewed_result_id)
        if existing is not None:
            return existing
        if contender.status == "processing":
            running = self.session.scalar(
                select(ExportJob)
                .where(
                    ExportJob.reviewed_result_id == reviewed_result_id,
                    ExportJob.status.in_(("running", "success")),
                )
                .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
            )
            if running is not None:
                return running
            raise ExportInProgress("logical export is already being generated")
        raise ExportInputUnavailable("logical export job cannot be claimed")

    def _source_pdf(self, reviewed: ReviewedResult) -> _SourcePdf:
        working = self.session.get(ReviewWorkingCopy, reviewed.working_copy_id)
        if working is None or working.project_id != reviewed.project_id:
            raise ExportInputUnavailable("reviewed source working copy is unavailable")
        raw = self.session.get(AutomaticResult, working.raw_result_id)
        if raw is None or raw.project_id != reviewed.project_id:
            raise ExportInputUnavailable("reviewed automatic result is unavailable")
        source = self.session.get(StoredFile, raw.source_file_id)
        if source is None or source.mime_type != "application/pdf":
            raise ExportInputUnavailable("reviewed source PDF is unavailable")
        try:
            content = self.storage.read_bytes(source.resource_ref)
        except (OSError, ValueError) as error:
            raise ExportInputUnavailable(
                "reviewed source PDF is unavailable"
            ) from error
        digest = sha256_bytes(content)
        if digest != source.sha256 or len(content) != source.size_bytes:
            raise ExportInputUnavailable("reviewed source PDF identity changed")
        relative = source.resource_ref.removeprefix("asset://")
        filename = PurePosixPath(relative).name
        return _SourcePdf(content=content, sha256=digest, filename=filename)

    @staticmethod
    def _active_balloon_snapshots(
        balloons: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        active = [
            balloon
            for balloon in balloons
            if balloon.get("status", "active") == "active"
        ]
        return sorted(active, key=lambda value: int(value["formal_number"]))

    @classmethod
    def _frozen_balloons(
        cls,
        balloons: list[dict[str, Any]],
    ) -> list[FrozenBalloon]:
        frozen: list[FrozenBalloon] = []
        for balloon in cls._active_balloon_snapshots(balloons):
            frozen.append(
                FrozenBalloon(
                    page_index=int(balloon["page_index"]),
                    formal_number=int(balloon["formal_number"]),
                    center_pdf=tuple(balloon["center_pdf"]),  # type: ignore[arg-type]
                    leader_target_pdf=tuple(  # type: ignore[arg-type]
                        balloon["leader_target_pdf"]
                    ),
                )
            )
        return frozen

    @staticmethod
    def _excel_rows(
        reviewed_items: list[dict[str, Any]],
        balloons: list[dict[str, Any]],
    ) -> list[dict[str, object]]:
        balloon_numbers = {
            str(balloon["inspection_item_id"]): balloon["formal_number"]
            for balloon in balloons
        }
        rows: list[dict[str, object]] = []
        for item in reviewed_items:
            if not item.get("active", True):
                continue
            missing = _DETAIL_FIELDS - set(item)
            invalid = {
                field
                for field in _DETAIL_FIELDS
                if field in item
                and (
                    (
                        not isinstance(item[field], int)
                        or isinstance(item[field], bool)
                        or item[field] < 1
                    )
                    if field == "source_page"
                    else (
                        not isinstance(item[field], str)
                        or not item[field].strip()
                    )
                )
            }
            if item.get(_DETAIL_CONFIRMED) is not True or missing or invalid:
                raise ValueError(
                    "reviewed item has incomplete confirmed export fields: "
                    f"{sorted(missing | invalid)}"
                )
            item_id = str(item["item_id"])
            required = item.get("balloon_required") is True
            if required and item_id not in balloon_numbers:
                raise ValueError("reviewed item is missing its formal balloon")
            row: dict[str, object] = {
                "balloon_number": balloon_numbers.get(item_id, ""),
                **{field: item[field] for field in sorted(_DETAIL_FIELDS)},
                "scope": item.get("scope"),
                "balloon_required": required,
            }
            rows.append(row)
        return rows

    @staticmethod
    def _sip_metadata(metadata: dict[str, Any]) -> dict[str, object]:
        missing = REQUIRED_METADATA_FIELDS - set(metadata)
        extra = set(metadata) - REQUIRED_METADATA_FIELDS
        invalid = {
            field
            for field in REQUIRED_METADATA_FIELDS & set(metadata)
            if not isinstance(metadata[field], str) or not metadata[field].strip()
        }
        if missing or extra or invalid:
            raise ValueError(
                "reviewed result has incomplete confirmed SIP metadata"
            )
        return {field: metadata[field] for field in sorted(REQUIRED_METADATA_FIELDS)}

    @staticmethod
    def _filenames(source_filename: str) -> dict[str, str]:
        stem = safe_stem(source_filename)
        return {
            "ballooned_pdf": f"{stem}-ballooned.pdf",
            "sip_excel": f"{stem}-sip.xlsx",
            "manifest": f"{stem}-manifest.json",
        }

    def _stage_artifact(
        self,
        export: ExportJob,
        kind: str,
        filename: str,
        content: bytes,
    ) -> ExportArtifact:
        digest = sha256_bytes(content)
        stored = self.storage.write_verified(
            f"exports/.staging/{export.id}/{filename}",
            content,
            digest,
        )
        artifact = ExportArtifact(
            export_id=export.id,
            kind=kind,
            staging_ref=stored.resource_ref,
            published_ref=None,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            reviewed_result_id=export.reviewed_result_id,
        )
        self.session.add(artifact)
        self.session.commit()
        self.session.refresh(artifact)
        return artifact

    @staticmethod
    def _validate_pdf(
        source_pdf: bytes,
        rendered_pdf: bytes,
        balloons: list[FrozenBalloon],
    ) -> int:
        try:
            with fitz.open(stream=source_pdf, filetype="pdf") as source:
                source_page_count = source.page_count
            with fitz.open(stream=rendered_pdf, filetype="pdf") as rendered:
                if rendered.page_count != source_page_count:
                    raise ValueError("ballooned PDF page count changed")
                for balloon in balloons:
                    if str(balloon.formal_number) not in rendered[
                        balloon.page_index
                    ].get_text():
                        raise ValueError("ballooned PDF formal number is unreadable")
        except (RuntimeError, ValueError) as error:
            raise ValueError("ballooned PDF validation failed") from error
        return source_page_count

    @staticmethod
    def _rasterize_pdf(content: bytes, target: Path) -> list[Path]:
        paths: list[Path] = []
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                for page_index, page in enumerate(document):
                    image_path = target / f"page-{page_index + 1:04d}.png"
                    page.get_pixmap(dpi=150, alpha=False).save(image_path)
                    paths.append(image_path)
        except RuntimeError as error:
            raise ValueError("ballooned PDF rasterization failed") from error
        return paths

    @staticmethod
    def _validate_excel(
        content: bytes,
        registration: TemplateRegistration,
        metadata: dict[str, object],
        rows: list[dict[str, object]],
    ) -> None:
        from io import BytesIO

        try:
            workbook = load_workbook(BytesIO(content), data_only=False)
        except (OSError, ValueError) as error:
            raise ValueError("staged SIP workbook cannot be reopened") from error
        try:
            sheet = workbook[registration.sheet]
            for field, address in registration.metadata_cells.items():
                if sheet[address].value != str(metadata[field]):
                    raise ValueError("staged SIP metadata differs from review")
            for offset, row in enumerate(rows):
                target_row = registration.first_row + offset
                for field, column in registration.detail_columns.items():
                    expected = row[field]
                    if (
                        field == "balloon_number"
                        and row.get("scope") == "global_requirement"
                        and row.get("balloon_required") is False
                    ):
                        expected = ""
                    actual = sheet[f"{column}{target_row}"].value
                    if actual != (str(expected) if expected != "" else None):
                        raise ValueError("staged SIP detail differs from review")
        finally:
            workbook.close()

    @staticmethod
    def _manifest(
        export: ExportJob,
        reviewed: ReviewedResult,
        source: _SourcePdf,
        registration: TemplateRegistration,
        source_page_count: int,
        filenames: dict[str, str],
        pdf_artifact: ExportArtifact,
        excel_artifact: ExportArtifact,
        balloons: list[dict[str, Any]],
    ) -> ExportManifest:
        active_items = [
            item for item in reviewed.items if item.get("active", True)
        ]
        required = [
            item for item in active_items if item.get("balloon_required") is True
        ]
        return ExportManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            export_id=str(export.id),
            project_id=str(export.project_id),
            reviewed_result_id=str(reviewed.id),
            input_pdf_sha256=source.sha256,
            template_id=registration.template_id,
            template_version=registration.template_version,
            template_sha256=registration.template_sha256,
            mapping_version=registration.mapping_version,
            font_sha256=APPROVED_BALLOON_FONT_SHA256,
            renderer_version=RENDERER_VERSION,
            reviewed_item_count=len(active_items),
            balloon_required_count=len(required),
            balloon_count=len(balloons),
            source_page_count=source_page_count,
            artifacts=(
                ArtifactDigest(
                    kind="ballooned_pdf",
                    filename=filenames["ballooned_pdf"],
                    sha256=pdf_artifact.sha256,
                    size_bytes=pdf_artifact.size_bytes,
                    reviewed_result_id=str(reviewed.id),
                ),
                ArtifactDigest(
                    kind="sip_excel",
                    filename=filenames["sip_excel"],
                    sha256=excel_artifact.sha256,
                    size_bytes=excel_artifact.size_bytes,
                    reviewed_result_id=str(reviewed.id),
                ),
            ),
        )

    @staticmethod
    def _validate_manifest(content: bytes, expected: ExportManifest) -> None:
        if content != expected.to_bytes():
            raise ValueError("export manifest identity changed")

    def _fail(
        self,
        export_id: uuid.UUID,
        logical_job_id: uuid.UUID,
        stage: str,
        error: Exception,
    ) -> ExportJob:
        self.session.rollback()
        export = self.session.get(ExportJob, export_id, populate_existing=True)
        if export is None:
            raise ExportNotFound(f"export {export_id} was not found") from error
        artifacts = list(
            self.session.scalars(
                select(ExportArtifact).where(ExportArtifact.export_id == export_id)
            )
        )
        for artifact in artifacts:
            artifact.published_ref = None
        record = ErrorRecord(
            project_id=export.project_id,
            code="export_artifact_failed",
            message=f"formal export failed during {stage}",
            severity="fatal",
            stage=f"export_{stage}"[:64],
            location_ref=f"export://{export.id}",
            cause_category=type(error).__name__[:64],
        )
        self.session.add(record)
        self.session.flush()
        export.status = "failed"
        export.error_id = record.id
        export.completed_at = datetime.now(timezone.utc)
        claim_logical_job_failure(self.session, job_id=logical_job_id)
        self.session.commit()
        self.session.refresh(export)
        return export
