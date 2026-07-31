from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.exports.sip_workbook_contract import (
    NUMERIC_DETAIL_FIELDS,
    NUMERIC_METADATA_FIELDS,
    TEXT_DETAIL_FIELDS,
    TEXT_METADATA_FIELDS,
)

SIP_TEMPLATE_ID = "sip-v1"
APPROVED_TEMPLATE_VERSION = "3"
APPROVED_TEMPLATE_SHA256 = (
    "b5a1ffac7cadba1cf1faac7ae6866be9482aca5fcd70fee24f385dbca854eea3"
)
APPROVED_MAPPING_VERSION = "3"
APPROVED_MAPPING_SHA256 = (
    "bd0ed776123deaf2d043fbc0b816991f1560cfd4fb053ed2f69307864ab545e6"
)

_REQUIRED_TOP_LEVEL_FIELDS = {
    "template_id",
    "template_version",
    "template_sha256",
    "mapping_version",
    "sheet",
    "capacity",
    "metadata_cells",
    "detail_columns",
    "measurement_column",
    "result_column",
    "image_sheet",
    "image_anchor",
    "protected_ranges",
    "signoff_ranges",
}
_REQUIRED_METADATA_FIELDS = NUMERIC_METADATA_FIELDS | TEXT_METADATA_FIELDS
_REQUIRED_DETAIL_FIELDS = NUMERIC_DETAIL_FIELDS | TEXT_DETAIL_FIELDS


class AssetHashMismatch(RuntimeError):
    pass


class TemplateHashMismatch(AssetHashMismatch):
    pass


class MappingHashMismatch(AssetHashMismatch):
    pass


class InvalidTemplateRegistration(RuntimeError):
    pass


@dataclass(frozen=True)
class TemplateRegistration:
    template_id: str
    template_version: str
    template_sha256: str
    mapping_version: str
    mapping_sha256: str
    sheet: str
    first_row: int
    last_row: int
    metadata_cells: dict[str, str]
    detail_columns: dict[str, str]
    measurement_column: str
    result_column: str
    image_sheet: str
    image_anchor: str
    protected_ranges: tuple[str, ...]
    signoff_ranges: tuple[str, ...]

    @property
    def capacity(self) -> int:
        return self.last_row - self.first_row + 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty_string(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidTemplateRegistration(f"{field} must be a non-empty string")
    return value


def _fixed_mapping(
    raw: dict[str, Any],
    field: str,
    required_fields: set[str],
) -> dict[str, str]:
    value = raw.get(field)
    if not isinstance(value, dict) or set(value) != required_fields:
        raise InvalidTemplateRegistration(
            "mapping must contain the complete fixed-field mapping"
        )
    if any(not isinstance(address, str) or not address.strip() for address in value.values()):
        raise InvalidTemplateRegistration(
            "fixed-field mapping addresses must be non-empty strings"
        )
    return dict(value)


def _ranges(raw: dict[str, Any], field: str) -> tuple[str, ...]:
    value = raw.get(field)
    if not isinstance(value, list) or any(
        not isinstance(cell_range, str) or not cell_range.strip()
        for cell_range in value
    ):
        raise InvalidTemplateRegistration(f"{field} must be a list of cell ranges")
    return tuple(value)


def load_template_registration(
    template_path: Path,
    mapping_path: Path,
) -> TemplateRegistration:
    try:
        mapping_bytes = mapping_path.read_bytes()
        raw = json.loads(mapping_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidTemplateRegistration("mapping must be readable JSON") from exc
    if not isinstance(raw, dict):
        raise InvalidTemplateRegistration(
            "mapping must be the complete sip-v1 registration"
        )
    _nonempty_string(raw, "measurement_column")
    _nonempty_string(raw, "result_column")
    if set(raw) != _REQUIRED_TOP_LEVEL_FIELDS:
        raise InvalidTemplateRegistration(
            "mapping must be the complete sip-v1 registration"
        )

    template_id = _nonempty_string(raw, "template_id")
    if template_id != SIP_TEMPLATE_ID:
        raise InvalidTemplateRegistration("only the registered sip-v1 template is allowed")

    template_version = _nonempty_string(raw, "template_version")
    mapping_version = _nonempty_string(raw, "mapping_version")
    template_sha256 = _nonempty_string(raw, "template_sha256")
    if len(template_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in template_sha256
    ):
        raise InvalidTemplateRegistration("template_sha256 must be lowercase SHA-256")

    capacity = raw.get("capacity")
    if not isinstance(capacity, dict) or set(capacity) != {"first_row", "last_row"}:
        raise InvalidTemplateRegistration("capacity must contain first_row and last_row")
    first_row = capacity["first_row"]
    last_row = capacity["last_row"]
    if (
        not isinstance(first_row, int)
        or isinstance(first_row, bool)
        or not isinstance(last_row, int)
        or isinstance(last_row, bool)
        or first_row < 1
        or last_row < first_row
    ):
        raise InvalidTemplateRegistration("invalid detail capacity")

    sheet = _nonempty_string(raw, "sheet")
    metadata_cells = _fixed_mapping(
        raw,
        "metadata_cells",
        _REQUIRED_METADATA_FIELDS,
    )
    detail_columns = _fixed_mapping(
        raw,
        "detail_columns",
        _REQUIRED_DETAIL_FIELDS,
    )
    measurement_column = _nonempty_string(raw, "measurement_column")
    result_column = _nonempty_string(raw, "result_column")
    for field, column in (
        ("measurement_column", measurement_column),
        ("result_column", result_column),
    ):
        if not _is_excel_column(column):
            raise InvalidTemplateRegistration(f"{field} must be a single Excel column")
    if measurement_column == result_column:
        raise InvalidTemplateRegistration(
            "measurement_column and result_column must not overlap"
        )
    if {measurement_column, result_column} & set(detail_columns.values()):
        raise InvalidTemplateRegistration(
            "detail_columns must not overlap measurement or result columns"
        )
    image_sheet = _nonempty_string(raw, "image_sheet")
    image_anchor = _nonempty_string(raw, "image_anchor")
    protected_ranges = _ranges(raw, "protected_ranges")
    signoff_ranges = _ranges(raw, "signoff_ranges")

    actual_mapping_sha256 = hashlib.sha256(mapping_bytes).hexdigest()
    if actual_mapping_sha256 != APPROVED_MAPPING_SHA256:
        raise MappingHashMismatch(
            "mapping hash drift: "
            f"expected {APPROVED_MAPPING_SHA256}, got {actual_mapping_sha256}"
        )
    if (
        template_version != APPROVED_TEMPLATE_VERSION
        or mapping_version != APPROVED_MAPPING_VERSION
        or template_sha256 != APPROVED_TEMPLATE_SHA256
    ):
        raise InvalidTemplateRegistration(
            "mapping identity does not match the approved sip-v1 registration"
        )

    actual_sha256 = file_sha256(template_path)
    if actual_sha256 != APPROVED_TEMPLATE_SHA256:
        raise TemplateHashMismatch(
            "template hash drift: "
            f"expected {APPROVED_TEMPLATE_SHA256}, got {actual_sha256}"
        )

    return TemplateRegistration(
        template_id=template_id,
        template_version=template_version,
        template_sha256=APPROVED_TEMPLATE_SHA256,
        mapping_version=mapping_version,
        mapping_sha256=actual_mapping_sha256,
        sheet=sheet,
        first_row=first_row,
        last_row=last_row,
        metadata_cells=metadata_cells,
        detail_columns=detail_columns,
        measurement_column=measurement_column,
        result_column=result_column,
        image_sheet=image_sheet,
        image_anchor=image_anchor,
        protected_ranges=protected_ranges,
        signoff_ranges=signoff_ranges,
    )


def _is_excel_column(value: str) -> bool:
    if not value.isascii() or not value.isupper() or not value.isalpha() or len(value) > 3:
        return False
    index = 0
    for character in value:
        index = index * 26 + ord(character) - ord("A") + 1
    return index <= 16384
