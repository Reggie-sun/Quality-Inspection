from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

import pytest

from app.capabilities.service import CapabilityUnavailable, ExportPreflight


def _approved_asset_paths(tmp_path: Path) -> dict[str, Path]:
    backend_root = Path(__file__).resolve().parents[2]
    paths = {
        "template": tmp_path / "sip-v1.xlsx",
        "mapping": tmp_path / "sip-v1.mapping.json",
        "font": tmp_path / "DejaVuSans.ttf",
        "license": tmp_path / "LICENSE-DejaVu.txt",
    }
    copyfile(backend_root / "assets/templates/sip-v1.xlsx", paths["template"])
    copyfile(
        backend_root / "assets/templates/sip-v1.mapping.json",
        paths["mapping"],
    )
    copyfile(backend_root / "assets/fonts/DejaVuSans.ttf", paths["font"])
    copyfile(backend_root / "assets/fonts/LICENSE-DejaVu.txt", paths["license"])
    return paths


def _preflight(paths: dict[str, Path]) -> ExportPreflight:
    return ExportPreflight(
        template_path=paths["template"],
        mapping_path=paths["mapping"],
        font_path=paths["font"],
        font_license_path=paths["license"],
    )


def test_p0_run_004_approved_export_assets_pass_preflight(tmp_path: Path) -> None:
    """P0-RUN-004 accepts only the fully registered template/font asset set."""
    registration = _preflight(_approved_asset_paths(tmp_path)).check()

    assert registration.template_id == "sip-v1"
    assert registration.sheet == "尺寸质量检测表"
    assert registration.image_sheet == "气泡图"


@pytest.mark.parametrize(
    ("missing_key", "expected_code"),
    (
        ("template", "export_template_unavailable"),
        ("mapping", "export_template_mapping_unavailable"),
        ("font", "export_font_unavailable"),
        ("license", "export_font_license_unavailable"),
    ),
)
def test_p0_run_004_missing_asset_is_a_structured_blocker(
    tmp_path: Path,
    missing_key: str,
    expected_code: str,
) -> None:
    """P0-RUN-004 blocks before an export job can enter running."""
    paths = _approved_asset_paths(tmp_path)
    paths[missing_key].unlink()

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == expected_code


def test_p0_run_004_template_hash_drift_is_a_structured_blocker(
    tmp_path: Path,
) -> None:
    """P0-RUN-004 recomputes the controlled workbook hash for every check."""
    paths = _approved_asset_paths(tmp_path)
    paths["template"].write_bytes(b"changed-template")

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == "export_template_hash_mismatch"


def test_p0_run_004_mapping_byte_drift_is_a_structured_blocker(
    tmp_path: Path,
) -> None:
    """P0-RUN-004 binds the approved mapping bytes, not only their semantics."""
    paths = _approved_asset_paths(tmp_path)
    paths["mapping"].write_bytes(paths["mapping"].read_bytes() + b"\n")

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == "export_template_mapping_hash_mismatch"


def test_p0_run_004_font_hash_drift_is_a_structured_blocker(
    tmp_path: Path,
) -> None:
    """P0-RUN-004 recomputes the approved balloon-font hash for every check."""
    paths = _approved_asset_paths(tmp_path)
    paths["font"].write_bytes(b"changed-font")

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == "export_font_hash_mismatch"


def test_p0_run_004_font_license_hash_drift_is_a_structured_blocker(
    tmp_path: Path,
) -> None:
    """P0-RUN-004 recomputes the approved redistribution-license hash."""
    paths = _approved_asset_paths(tmp_path)
    paths["license"].write_bytes(b"changed-license")

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == "export_font_license_hash_mismatch"


def test_p0_run_004_registered_sheet_mapping_drift_is_a_structured_blocker(
    tmp_path: Path,
) -> None:
    """P0-RUN-004 rejects a changed registered sheet before workbook use."""
    paths = _approved_asset_paths(tmp_path)
    mapping = json.loads(paths["mapping"].read_text(encoding="utf-8"))
    mapping["sheet"] = "未登记的检验表"
    paths["mapping"].write_text(json.dumps(mapping), encoding="utf-8")

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == "export_template_mapping_hash_mismatch"


def test_p0_run_004_missing_required_mapping_field_is_a_structured_blocker(
    tmp_path: Path,
) -> None:
    """P0-RUN-004 rejects incomplete fixed mappings before export starts."""
    paths = _approved_asset_paths(tmp_path)
    mapping = json.loads(paths["mapping"].read_text(encoding="utf-8"))
    mapping["metadata_cells"].pop("source_filename")
    paths["mapping"].write_text(json.dumps(mapping), encoding="utf-8")

    with pytest.raises(CapabilityUnavailable) as error:
        _preflight(paths).check()

    assert error.value.code == "export_template_registration_invalid"
