from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from shutil import copyfile

import pytest
from openpyxl import Workbook, load_workbook

from app.exports.template_registry import (
    AssetHashMismatch,
    InvalidTemplateRegistration,
    load_template_registration,
)


def _complete_mapping(template_bytes: bytes) -> dict[str, object]:
    return {
        "template_id": "sip-v1",
        "template_version": "2",
        "template_sha256": sha256(template_bytes).hexdigest(),
        "mapping_version": "2",
        "sheet": "SIP检验记录",
        "capacity": {"first_row": 6, "last_row": 517},
        "metadata_cells": {
            "material_code": "B2",
            "material_name": "D2",
            "drawing_number": "F2",
            "material": "B3",
            "revision": "D3",
        },
        "detail_columns": {
            "balloon_number": "A",
            "inspection_item": "B",
            "inspection_standard": "C",
            "inspection_method": "D",
            "key_dimension": "E",
            "inspection_role": "F",
            "source_page": "G",
        },
        "image_sheet": "气泡图",
        "image_anchor": "B2",
        "protected_ranges": [
            "A1:H1",
            "A2",
            "C2",
            "E2",
            "A3",
            "C3",
            "A4:H4",
            "A5:H5",
            "A518:H518",
        ],
        "signoff_ranges": [
            "A519:B522",
            "C519:D522",
            "E519:F522",
            "G519:H522",
        ],
    }


def _write_registration(
    tmp_path: Path,
    template_bytes: bytes,
    mapping: dict[str, object],
) -> tuple[Path, Path]:
    template_path = tmp_path / "sip-v1.xlsx"
    mapping_path = tmp_path / "sip-v1.mapping.json"
    template_path.write_bytes(template_bytes)
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    return template_path, mapping_path


def _copy_approved_registration(tmp_path: Path) -> tuple[Path, Path]:
    backend_root = Path(__file__).resolve().parents[3]
    template_path = tmp_path / "sip-v1.xlsx"
    mapping_path = tmp_path / "sip-v1.mapping.json"
    copyfile(backend_root / "assets/templates/sip-v1.xlsx", template_path)
    copyfile(backend_root / "assets/templates/sip-v1.mapping.json", mapping_path)
    return template_path, mapping_path


def test_p0_exp_001_loads_the_approved_single_template_registration() -> None:
    """P0-EXP-001 binds the approved template bytes to the complete sip-v1 map."""
    backend_root = Path(__file__).resolve().parents[3]
    registration = load_template_registration(
        backend_root / "assets/templates/sip-v1.xlsx",
        backend_root / "assets/templates/sip-v1.mapping.json",
    )

    assert registration.template_id == "sip-v1"
    assert registration.template_version == "2"
    assert registration.template_sha256 == (
        "6a946e9279a489f845e94f08d0ecb5917829a20378bba85cccc9171e50b16720"
    )
    assert registration.mapping_version == "2"
    assert registration.sheet == "SIP检验记录"
    assert registration.capacity == 512
    assert registration.image_sheet == "气泡图"
    assert registration.image_anchor == "B2"


def test_p0_exp_003_approved_template_has_fixed_current_four_print_capacity() -> None:
    """P0-EXP-003 keeps 512 fixed rows readable without moving the sign-off body."""
    backend_root = Path(__file__).resolve().parents[3]
    template_path = backend_root / "assets/templates/sip-v1.xlsx"
    registration = load_template_registration(
        template_path,
        backend_root / "assets/templates/sip-v1.mapping.json",
    )
    workbook = load_workbook(template_path, data_only=False)
    try:
        sheet = workbook[registration.sheet]
        assert (registration.first_row, registration.last_row) == (6, 517)
        assert sheet.max_row == 522
        assert str(sheet.print_area) == "'SIP检验记录'!$A$1:$H$522"
        assert sheet.print_title_rows == "$1:$5"
        assert sheet.page_setup.fitToHeight == 16
        assert [entry.id for entry in sheet.row_breaks.brk] == list(
            range(37, 517, 32)
        )
        assert "G517:H517" in {str(value) for value in sheet.merged_cells.ranges}
        assert sheet["A518"].value == (
            "备注：正式数据必须来自同一份已冻结 reviewed_result。"
        )
        assert all(
            sheet[f"{column}517"].protection.locked is False
            for column in "ABCDEFG"
        )
    finally:
        workbook.close()


def test_p0_exp_001_registry_rejects_template_hash_drift(tmp_path: Path) -> None:
    """P0-EXP-001 fails closed when registered bytes no longer match their hash."""
    template_path, mapping_path = _copy_approved_registration(tmp_path)
    template_path.write_bytes(b"changed-template-bytes")

    with pytest.raises(AssetHashMismatch, match="template hash drift"):
        load_template_registration(template_path, mapping_path)


def test_p0_exp_001_rejects_joint_template_and_mapping_replacement(
    tmp_path: Path,
) -> None:
    """P0-EXP-001 anchors identity outside the two mutually editable assets."""
    _, mapping_path = _copy_approved_registration(tmp_path)
    template_path = tmp_path / "replacement.xlsx"
    workbook = Workbook()
    workbook.active.title = "SIP检验记录"
    workbook.create_sheet("气泡图")
    workbook.save(template_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping["template_sha256"] = sha256(template_path.read_bytes()).hexdigest()
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(AssetHashMismatch, match="mapping hash drift"):
        load_template_registration(template_path, mapping_path)


def test_p0_exp_001_registry_rejects_missing_fixed_mapping_field(
    tmp_path: Path,
) -> None:
    """P0-EXP-001 refuses an incomplete fixed-field registration."""
    template_bytes = b"approved-template-bytes"
    mapping = _complete_mapping(template_bytes)
    detail_columns = dict(mapping["detail_columns"])
    detail_columns.pop("source_page")
    mapping["detail_columns"] = detail_columns
    template_path, mapping_path = _write_registration(
        tmp_path,
        template_bytes,
        mapping,
    )

    with pytest.raises(
        InvalidTemplateRegistration,
        match="complete fixed-field mapping",
    ):
        load_template_registration(template_path, mapping_path)


def test_p0_exp_001_registry_rejects_any_template_id_other_than_sip_v1(
    tmp_path: Path,
) -> None:
    """P0-EXP-001 keeps P0 on its one approved template identity."""
    template_bytes = b"approved-template-bytes"
    mapping = _complete_mapping(template_bytes)
    mapping["template_id"] = "unregistered-template"
    template_path, mapping_path = _write_registration(
        tmp_path,
        template_bytes,
        mapping,
    )

    with pytest.raises(InvalidTemplateRegistration, match="sip-v1"):
        load_template_registration(template_path, mapping_path)
