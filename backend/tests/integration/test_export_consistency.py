from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.exports.manifest import ArtifactDigest, ExportManifest, sha256_bytes
from app.exports.models import ExportArtifact, ExportJob
from app.exports.service import (
    ExportService,
    assert_artifact_identity,
    assert_export_counts,
)


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


def test_pdf_and_excel_number_identity_does_not_depend_on_row_order() -> None:
    """P0-EXP-007C compares formal identity, not reviewed-item row order."""
    reviewed_items = [
        {"item_id": "i2", "active": True, "balloon_required": True},
        {"item_id": "i1", "active": True, "balloon_required": True},
    ]
    balloons = [
        {"inspection_item_id": "i1", "formal_number": 1},
        {"inspection_item_id": "i2", "formal_number": 2},
    ]
    excel_rows = [{"balloon_number": 2}, {"balloon_number": 1}]

    assert_export_counts(reviewed_items, balloons, excel_rows)


def test_manifest_aggregates_deterministic_confidence_provenance() -> None:
    reviewed_result_id = uuid.uuid4()
    project_id = uuid.uuid4()
    export_id = uuid.uuid4()
    reviewed_items = [
        {
            "item_id": "auto",
            "active": True,
            "acceptance_source": "confidence_policy",
            "confidence_decision": {
                "policy_version": "candidate-confidence/1",
            },
        },
        {
            "item_id": "override",
            "active": True,
            "acceptance_source": "manual_override",
            "confidence_decision": {
                "policy_version": "candidate-confidence/0",
            },
        },
        {
            "item_id": "excluded-auto",
            "active": False,
            "acceptance_source": "confidence_policy",
            "confidence_decision": {
                "policy_version": "candidate-confidence/1",
            },
        },
        {
            "item_id": "superseded-override",
            "active": False,
            "acceptance_source": "manual_override",
            "confidence_decision": {
                "policy_version": "candidate-confidence/0",
            },
        },
        {
            "item_id": "manual",
            "active": True,
            "acceptance_source": "manual",
        },
    ]

    manifest = ExportService._manifest(
        SimpleNamespace(id=export_id, project_id=project_id),
        SimpleNamespace(id=reviewed_result_id, items=reviewed_items),
        SimpleNamespace(sha256="1" * 64),
        SimpleNamespace(
            template_id="sip-v1",
            template_version="1",
            template_sha256="2" * 64,
            mapping_version="1",
        ),
        1,
        {
            "ballooned_pdf": "drawing-ballooned.pdf",
            "sip_excel": "drawing-sip.xlsx",
        },
        SimpleNamespace(sha256="4" * 64, size_bytes=41),
        SimpleNamespace(sha256="5" * 64, size_bytes=52),
        [],
    )

    assert manifest.schema_version == "export-manifest/2"
    assert manifest.confidence_policy_versions == (
        "candidate-confidence/0",
        "candidate-confidence/1",
    )
    assert manifest.auto_accepted_item_count == 1
    assert manifest.manual_override_item_count == 1


def test_manifest_legacy_only_result_has_empty_confidence_provenance() -> None:
    reviewed_result_id = uuid.uuid4()
    manifest = ExportService._manifest(
        SimpleNamespace(id=uuid.uuid4(), project_id=uuid.uuid4()),
        SimpleNamespace(
            id=reviewed_result_id,
            items=[
                {
                    "item_id": "legacy",
                    "active": True,
                    "acceptance_source": "manual",
                }
            ],
        ),
        SimpleNamespace(sha256="1" * 64),
        SimpleNamespace(
            template_id="sip-v1",
            template_version="1",
            template_sha256="2" * 64,
            mapping_version="1",
        ),
        1,
        {
            "ballooned_pdf": "drawing-ballooned.pdf",
            "sip_excel": "drawing-sip.xlsx",
        },
        SimpleNamespace(sha256="4" * 64, size_bytes=41),
        SimpleNamespace(sha256="5" * 64, size_bytes=52),
        [],
    )

    assert manifest.confidence_policy_versions == ()
    assert manifest.auto_accepted_item_count == 0
    assert manifest.manual_override_item_count == 0


def test_confidence_provenance_is_not_written_to_sip_business_rows() -> None:
    rows = ExportService._excel_rows(
        [
            {
                "item_id": "i1",
                "active": True,
                "balloon_required": False,
                "scope": "global_requirement",
                "inspection_item": "deburr",
                "inspection_standard": "no sharp edge",
                "inspection_method": "visual",
                "key_dimension": "no",
                "inspection_role": "FQC",
                "source_page": 1,
                "sip_detail_fields_confirmed": True,
                "acceptance_source": "confidence_policy",
                "confidence_decision": {
                    "policy_version": "candidate-confidence/1",
                },
            }
        ],
        [],
    )

    assert len(rows) == 1
    assert "acceptance_source" not in rows[0]
    assert "confidence_decision" not in rows[0]
    assert "confidence_policy_versions" not in rows[0]


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
        schema_version="export-manifest/2",
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
        confidence_policy_versions=("candidate-confidence/1",),
        auto_accepted_item_count=1,
        manual_override_item_count=0,
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
