from __future__ import annotations

import json
import uuid

import pytest

from app.exports.manifest import ArtifactDigest, ExportManifest, sha256_bytes
from app.exports.models import ExportArtifact, ExportJob
from app.exports.service import assert_artifact_identity, assert_export_counts


def _reviewed_items() -> list[dict[str, object]]:
    return [
        {
            "item_id": "i1",
            "active": True,
            "balloon_required": True,
        },
        {
            "item_id": "i2",
            "active": True,
            "balloon_required": False,
        },
        {
            "item_id": "excluded",
            "active": False,
            "balloon_required": True,
        },
    ]


def _balloons() -> list[dict[str, object]]:
    return [{"inspection_item_id": "i1", "formal_number": 1}]


def _excel_rows() -> list[dict[str, object]]:
    return [{"balloon_number": 1}, {"balloon_number": ""}]


def test_logical_detail_count_matches_reviewed_items() -> None:
    """P0-EXP-007A matches Excel details to active reviewed items exactly."""
    assert_export_counts(_reviewed_items(), _balloons(), _excel_rows())

    with pytest.raises(ValueError, match="excel detail count mismatch"):
        assert_export_counts(_reviewed_items(), _balloons(), _excel_rows()[:1])


def test_balloon_count_matches_required_items() -> None:
    """P0-EXP-007B matches balloons to active balloon-required items."""
    assert_export_counts(_reviewed_items(), _balloons(), _excel_rows())

    with pytest.raises(ValueError, match="balloon count mismatch"):
        assert_export_counts(_reviewed_items(), [], _excel_rows())


def test_pdf_and_excel_numbers_match() -> None:
    """P0-EXP-007C vetoes divergent PDF and Excel formal numbers."""
    assert_export_counts(_reviewed_items(), _balloons(), _excel_rows())

    mismatched_rows = [{"balloon_number": 2}, {"balloon_number": ""}]
    with pytest.raises(ValueError, match="PDF and Excel balloon numbers differ"):
        assert_export_counts(_reviewed_items(), _balloons(), mismatched_rows)


def test_artifacts_share_reviewed_result_id() -> None:
    """P0-RES-004 binds all three formal artifacts to one reviewed result."""
    reviewed_result_id = uuid.uuid4()
    project_id = uuid.uuid4()
    export_id = uuid.uuid4()
    job = ExportJob(
        id=export_id,
        project_id=project_id,
        reviewed_result_id=reviewed_result_id,
        status="success",
        template_version="1",
        mapping_version="1",
        renderer_version="balloon-pdf/1",
    )
    pdf = ExportArtifact(
        export_id=export_id,
        kind="ballooned_pdf",
        staging_ref="asset://exports/.staging/pdf",
        published_ref="asset://exports/pdf",
        sha256="4" * 64,
        size_bytes=41,
        reviewed_result_id=reviewed_result_id,
    )
    excel = ExportArtifact(
        export_id=export_id,
        kind="sip_excel",
        staging_ref="asset://exports/.staging/excel",
        published_ref="asset://exports/excel",
        sha256="5" * 64,
        size_bytes=52,
        reviewed_result_id=reviewed_result_id,
    )
    manifest = ExportManifest(
        schema_version="export-manifest/1",
        export_id=str(export_id),
        project_id=str(project_id),
        reviewed_result_id=str(reviewed_result_id),
        input_pdf_sha256="1" * 64,
        template_id="sip-v1",
        template_version="1",
        template_sha256="2" * 64,
        mapping_version="1",
        font_sha256="3" * 64,
        renderer_version="balloon-pdf/1",
        reviewed_item_count=2,
        balloon_required_count=1,
        balloon_count=1,
        source_page_count=1,
        artifacts=(
            ArtifactDigest(
                kind=pdf.kind,
                filename="drawing-ballooned.pdf",
                sha256=pdf.sha256,
                size_bytes=pdf.size_bytes,
                reviewed_result_id=str(pdf.reviewed_result_id),
            ),
            ArtifactDigest(
                kind=excel.kind,
                filename="drawing-sip.xlsx",
                sha256=excel.sha256,
                size_bytes=excel.size_bytes,
                reviewed_result_id=str(excel.reviewed_result_id),
            ),
        ),
    )
    manifest_row = ExportArtifact(
        export_id=export_id,
        kind="manifest",
        staging_ref="asset://exports/.staging/manifest",
        published_ref="asset://exports/manifest",
        sha256=sha256_bytes(manifest.to_bytes()),
        size_bytes=len(manifest.to_bytes()),
        reviewed_result_id=reviewed_result_id,
    )

    assert job.reviewed_result_id == reviewed_result_id
    assert_artifact_identity(
        reviewed_result_id,
        [pdf, excel, manifest_row],
        manifest.to_bytes(),
    )
    assert {
        pdf.reviewed_result_id,
        excel.reviewed_result_id,
        manifest_row.reviewed_result_id,
    } == {reviewed_result_id}
    assert json.loads(manifest.to_bytes())["reviewed_result_id"] == str(
        reviewed_result_id
    )

    manifest_row.reviewed_result_id = uuid.uuid4()
    with pytest.raises(ValueError, match="different reviewed results"):
        assert_artifact_identity(
            reviewed_result_id,
            [pdf, excel, manifest_row],
            manifest.to_bytes(),
        )
