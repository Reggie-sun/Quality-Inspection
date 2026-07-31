from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.exports import service as export_service
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
    return [{"number": 1}, {"number": ""}]


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

    mismatched_rows = [{"number": 2}, {"number": ""}]
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
    excel_rows = [{"number": 2}, {"number": 1}]

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
            mapping_sha256="3" * 64,
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
            mapping_sha256="3" * 64,
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


def _confirmed_dimension_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "item_id": "dimension-item",
        "item_type": "linear_dimension",
        "normalized_text": "10",
        "nominal": "10",
        "source_page": 1,
        "active": True,
        "balloon_required": False,
        "sip_detail_fields_confirmed": True,
        "inspection_item": "线性尺寸：10",
        "inspection_standard": "图纸要求",
        "inspection_method": "游标卡尺",
        "key_dimension": "否",
        "inspection_role": "IPQC",
    }
    item.update(overrides)
    return item


def test_excel_rows_project_a_linear_dimension_with_numeric_limits() -> None:
    """Catches the legacy SIP projection that omits dimension row values and limits."""
    linear = {
        "item_id": "linear-500",
        "item_type": "linear_dimension",
        "normalized_text": "500 ±0.2",
        "nominal": "500",
        "upper_tolerance": "0.2",
        "lower_tolerance": "-0.2",
        "source_page": 1,
        "active": True,
        "balloon_required": True,
        "sip_detail_fields_confirmed": True,
        "inspection_item": "线性尺寸：500 ±0.2",
        "inspection_standard": "图纸要求",
        "inspection_method": "游标卡尺",
        "key_dimension": "否",
        "inspection_role": "IPQC",
    }

    rows = ExportService._excel_rows(
        [linear],
        [{"inspection_item_id": "linear-500", "formal_number": 7}],
    )

    assert rows == [
        {
            "number": 7,
            "source_page": 1,
            "type_label": "线性",
            "basic_size": "500",
            "tolerance": "±0.2",
            "upper_limit": Decimal("500.2"),
            "lower_limit": Decimal("499.8"),
            "scope": None,
            "balloon_required": True,
        }
    ]


@pytest.mark.parametrize(
    ("item_type", "structured_fields", "expected_type", "expected_size"),
    [
        ("diameter_dimension", {"nominal": "20"}, "直径", "Φ20"),
        ("radius", {"radius_value": "35"}, "半径", "R35"),
        (None, {"coarse_type": "roughness", "raw_text": "Ra3.2"}, "粗糙度", "Ra3.2"),
        ("angle", {"angle_value": "45"}, "角度", "45°"),
        ("thread", {"thread_spec": "M10×1.5"}, "螺纹", "M10×1.5"),
        ("general_requirement", {"normalized_text": "去毛刺"}, "技术要求", "去毛刺"),
        ("composite", {"normalized_text": "Φ10 深20"}, "复合", "Φ10 深20"),
    ],
)
def test_excel_rows_project_supported_dimension_display_values(
    item_type: str | None,
    structured_fields: dict[str, object],
    expected_type: str,
    expected_size: str,
) -> None:
    """Catches a type-specific display projection that falls back to legacy SIP prose."""
    item = _confirmed_dimension_item(
        **{
            "item_type": item_type,
            "normalized_text": "",
            **structured_fields,
        }
    )

    row = ExportService._excel_rows([item], [])[0]

    assert row["type_label"] == expected_type
    assert row["basic_size"] == expected_size


def test_excel_rows_leave_limits_blank_without_structured_tolerance() -> None:
    """Catches projection that invents limits where reviewed structured tolerance is absent."""
    no_tolerance_row = ExportService._excel_rows(
        [_confirmed_dimension_item()],
        [],
    )[0]

    assert no_tolerance_row["tolerance"] == ""
    assert no_tolerance_row["upper_limit"] == ""
    assert no_tolerance_row["lower_limit"] == ""


def test_excel_rows_reject_one_sided_structured_tolerance() -> None:
    """Catches projection that silently exports an incomplete reviewed tolerance."""
    upper_only_item = _confirmed_dimension_item(upper_tolerance="0.2")

    with pytest.raises(ValueError, match="one-sided structured tolerance"):
        ExportService._excel_rows([upper_only_item], [])


@pytest.mark.parametrize(
    ("item_type", "field"),
    [
        ("linear_dimension", "nominal"),
        ("radius", "radius_value"),
        ("angle", "angle_value"),
    ],
)
def test_excel_rows_fall_back_for_non_finite_numeric_bases(
    item_type: str,
    field: str,
) -> None:
    """Catches a non-finite reviewed base leaking into a visible numeric limit."""
    item = _confirmed_dimension_item(
        item_type=item_type,
        normalized_text="已审核文本",
        upper_tolerance="0.2",
        lower_tolerance="-0.2",
        **{field: "NaN"},
    )

    row = ExportService._excel_rows([item], [])[0]

    assert row["basic_size"] == "已审核文本"
    assert row["upper_limit"] == ""
    assert row["lower_limit"] == ""


@pytest.mark.parametrize("non_finite", ["NaN", "Infinity", "-Infinity"])
def test_excel_rows_reject_non_finite_structured_tolerances(
    non_finite: str,
) -> None:
    """Catches a non-finite tolerance raising Decimal internals or reaching a row."""
    item = _confirmed_dimension_item(
        nominal="10",
        upper_tolerance=non_finite,
        lower_tolerance="-0.2",
    )

    with pytest.raises(ValueError):
        ExportService._excel_rows([item], [])


@pytest.mark.parametrize(
    ("upper", "lower", "expected_tolerance", "expected_upper", "expected_lower"),
    [
        ("0.05", "0.01", "+0.05/+0.01", Decimal("10.05"), Decimal("10.01")),
        ("-0.01", "-0.05", "-0.01/-0.05", Decimal("9.99"), Decimal("9.95")),
        ("0.03", "-0.02", "+0.03/-0.02", Decimal("10.03"), Decimal("9.98")),
        ("-0.03", "0.01", None, None, None),
        ("-0.2", "0.2", None, None, None),
    ],
)
def test_excel_rows_enforce_structured_tolerance_range_order(
    upper: str,
    lower: str,
    expected_tolerance: str | None,
    expected_upper: Decimal | None,
    expected_lower: Decimal | None,
) -> None:
    """Catches an inverted range, including reversed symmetric values, reaching export."""
    item = _confirmed_dimension_item(
        nominal="10",
        upper_tolerance=upper,
        lower_tolerance=lower,
    )

    if expected_tolerance is None:
        with pytest.raises(ValueError, match="inverted structured tolerance"):
            ExportService._excel_rows([item], [])
        return

    row = ExportService._excel_rows([item], [])[0]
    assert row["tolerance"] == expected_tolerance
    assert row["upper_limit"] == expected_upper
    assert row["lower_limit"] == expected_lower


def test_general_tolerance_note_projects_only_controlled_frozen_standards() -> None:
    """Catches a header note that reads arbitrary or unfrozen requirement text."""
    assert export_service._general_tolerance_note(
        [
            {
                "active": True,
                "technical_requirement_refs": ["tr-1"],
                "inspection_standard": "GB/T 1804-m",
            }
        ]
    ) == "【未注公差标准】未注线性尺寸公差按 GB/T 1804-m 级执行"
    assert export_service._general_tolerance_note(
        [
            {
                "active": True,
                "technical_requirement_refs": ["tr-1"],
                "inspection_standard": "GB/T 1804-f",
            },
            {
                "active": True,
                "technical_requirement_refs": ["tr-2"],
                "inspection_standard": "GB/T 1184-k",
            },
        ]
    ) == (
        "【未注公差标准】未注线性尺寸公差按 GB/T 1804-f 级执行；"
        "未注形位公差按 GB/T 1184-k 级执行"
    )
    assert export_service._general_tolerance_note(
        [{"active": True, "technical_requirement_refs": []}]
    ) == "【未注公差标准】未确认"
    assert export_service._general_tolerance_note(
        [
            {
                "active": True,
                "technical_requirement_refs": ["tr-1"],
                "inspection_standard": "ISO 2768-m",
            },
            {
                "active": False,
                "technical_requirement_refs": ["tr-2"],
                "inspection_standard": "GB/T 1804-f",
            },
        ]
    ) == "【未注公差标准】未确认"
    with pytest.raises(ValueError, match="conflicting general tolerance standards"):
        export_service._general_tolerance_note(
            [
                {
                    "active": True,
                    "technical_requirement_refs": ["tr-1"],
                    "inspection_standard": "GB/T 1804-f",
                },
                {
                    "active": True,
                    "technical_requirement_refs": ["tr-2"],
                    "inspection_standard": "GB/T 1804-m",
                },
            ]
        )


def test_sip_metadata_keeps_the_frozen_five_field_shape() -> None:
    """Catches a v3 export that mutates rollback-compatible review metadata."""
    metadata = {
        "material_code": "MAT-001",
        "material_name": "上座",
        "drawing_number": "JS26032501",
        "material": "SUS304",
        "revision": "A1",
    }

    assert ExportService._sip_metadata(metadata) == metadata
    with pytest.raises(ValueError, match="incomplete confirmed SIP metadata"):
        ExportService._sip_metadata(
            {key: value for key, value in metadata.items() if key != "revision"}
        )
    with pytest.raises(ValueError, match="incomplete confirmed SIP metadata"):
        ExportService._sip_metadata(metadata | {"unit": "mm / 按项目"})


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
        mapping_sha256="3" * 64,
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
