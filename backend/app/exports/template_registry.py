from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SIP_TEMPLATE_ID = "sip-v1"
APPROVED_TEMPLATE_VERSION = "1"
APPROVED_TEMPLATE_SHA256 = (
    "8c117838e906939b76cd8158849e85b86e147d343d66e906df09794ef29e54bb"
)
APPROVED_MAPPING_VERSION = "1"
APPROVED_MAPPING_SHA256 = (
    "0ea5ef4ae76a2c2c7152046e41ebdfb0e373da949b0289bea321a9a1e4f0b6a4"
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
    "image_sheet",
    "image_anchor",
    "protected_ranges",
    "signoff_ranges",
}
_REQUIRED_METADATA_FIELDS = {
    "material_code",
    "material_name",
    "drawing_number",
    "material",
    "revision",
}
_REQUIRED_DETAIL_FIELDS = {
    "balloon_number",
    "inspection_item",
    "inspection_standard",
    "inspection_method",
    "key_dimension",
    "inspection_role",
    "source_page",
}


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
    sheet: str
    first_row: int
    last_row: int
    metadata_cells: dict[str, str]
    detail_columns: dict[str, str]
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
    if not isinstance(raw, dict) or set(raw) != _REQUIRED_TOP_LEVEL_FIELDS:
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
        sheet=sheet,
        first_row=first_row,
        last_row=last_row,
        metadata_cells=metadata_cells,
        detail_columns=detail_columns,
        image_sheet=image_sheet,
        image_anchor=image_anchor,
        protected_ranges=protected_ranges,
        signoff_ranges=signoff_ranges,
    )
