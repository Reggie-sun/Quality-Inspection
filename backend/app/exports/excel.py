from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.drawing.image import Image

from app.exports.template_registry import TemplateRegistration
from app.exports.validators import (
    snapshot_registered_ranges,
    validate_sip_workbook,
)


REQUIRED_METADATA_FIELDS = {
    "material_code",
    "material_name",
    "drawing_number",
    "material",
    "revision",
}
REQUIRED_DETAIL_FIELDS = {
    "balloon_number",
    "inspection_item",
    "inspection_standard",
    "inspection_method",
    "key_dimension",
    "inspection_role",
    "source_page",
}


class CapacityExceeded(RuntimeError):
    pass


def set_untrusted_text(cell: Cell, value: object) -> None:
    cell.value = "" if value is None else str(value)
    cell.data_type = "s"


def assert_capacity(
    registration: TemplateRegistration,
    detail_count: int,
) -> None:
    if detail_count > registration.capacity:
        raise CapacityExceeded(
            f"{detail_count} details exceed capacity {registration.capacity}"
        )


def render_sip_workbook(
    template_path: Path,
    registration: TemplateRegistration,
    metadata: dict[str, object],
    reviewed_items: list[dict[str, object]],
    page_images: list[Path],
) -> bytes:
    if set(registration.metadata_cells) != REQUIRED_METADATA_FIELDS:
        raise ValueError("fixed metadata mapping is incomplete")
    if set(registration.detail_columns) != REQUIRED_DETAIL_FIELDS:
        raise ValueError("fixed detail mapping is incomplete")
    assert_capacity(registration, len(reviewed_items))

    book = load_workbook(template_path, data_only=False)
    try:
        missing_sheets = {
            registration.sheet,
            registration.image_sheet,
        } - set(book.sheetnames)
        if missing_sheets:
            raise ValueError("registered workbook sheet is missing")
        protected_snapshot = snapshot_registered_ranges(book, registration)
        sheet = book[registration.sheet]
        for field, address in registration.metadata_cells.items():
            set_untrusted_text(sheet[address], metadata[field])

        for offset, item in enumerate(reviewed_items):
            row = registration.first_row + offset
            for field, column in registration.detail_columns.items():
                value = item.get(field, "")
                if (
                    field == "balloon_number"
                    and item.get("scope") == "global_requirement"
                    and item.get("balloon_required") is False
                ):
                    value = ""
                set_untrusted_text(sheet[f"{column}{row}"], value)

        image_sheet = book[registration.image_sheet]
        anchor_cell = image_sheet[registration.image_anchor]
        for page_index, image_path in enumerate(page_images):
            image = Image(image_path)
            image.anchor = (
                f"{anchor_cell.column_letter}{anchor_cell.row + page_index * 45}"
            )
            image_sheet.add_image(image)

        output = BytesIO()
        book.save(output)
        content = output.getvalue()
    finally:
        book.close()

    validate_sip_workbook(
        content,
        registration,
        protected_snapshot=protected_snapshot,
        detail_count=len(reviewed_items),
        source_page_count=len(page_images),
    )
    return content
