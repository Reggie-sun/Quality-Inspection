from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from PIL import Image as PillowImage

from app.exports.excel import render_sip_workbook
from app.exports.template_registry import TemplateRegistration, load_template_registration


def _approved_assets() -> tuple[Path, Path, TemplateRegistration]:
    backend_root = Path(__file__).resolve().parents[2]
    template_path = backend_root / "assets/templates/sip-v1.xlsx"
    mapping_path = backend_root / "assets/templates/sip-v1.mapping.json"
    return (
        template_path,
        mapping_path,
        load_template_registration(template_path, mapping_path),
    )


def _metadata() -> dict[str, object]:
    return {
        "material_code": "MAT-001",
        "material_name": "上座",
        "drawing_number": "JS26032501",
        "material": "SUS304",
        "revision": "A1",
    }


def _reviewed_items() -> list[dict[str, object]]:
    return [
        {
            "item_id": "item-1",
            "item_type": "dimension",
            "active": True,
            "balloon_required": True,
            "balloon_number": 1,
            "inspection_item": "已确认尺寸 Ø10 +0.1",
            "inspection_standard": "10.0 ≤ x ≤ 10.1",
            "inspection_method": "卡尺",
            "key_dimension": "是",
            "inspection_role": "IPQC",
            "source_page": 1,
            "raw_text": "=未经确认的建议值",
            "suggested_values": {
                "inspection_item": "未经确认的建议值",
                "inspection_method": "建议方法",
            },
        },
        {
            "item_id": "item-2",
            "item_type": "general_requirement",
            "scope": "global_requirement",
            "active": True,
            "balloon_required": False,
            "balloon_number": 999,
            "inspection_item": "去毛刺",
            "inspection_standard": "不得有锐边",
            "inspection_method": "目视",
            "key_dimension": "否",
            "inspection_role": "FQC",
            "source_page": 2,
        },
    ]


def _page_images(tmp_path: Path) -> tuple[list[Path], list[tuple[int, int, int]]]:
    colors = [(240, 10, 10), (10, 20, 230)]
    paths: list[Path] = []
    for page_number, color in enumerate(colors, start=1):
        path = tmp_path / f"page-{page_number}.png"
        PillowImage.new("RGB", (24, 16), color=color).save(path)
        paths.append(path)
    return paths, colors


def _render(tmp_path: Path) -> tuple[bytes, TemplateRegistration, Path]:
    template_path, _, registration = _approved_assets()
    page_images, _ = _page_images(tmp_path)
    return (
        render_sip_workbook(
            template_path,
            registration,
            _metadata(),
            _reviewed_items(),
            page_images,
        ),
        registration,
        template_path,
    )


def _registered_range_snapshot(
    workbook,
    registration: TemplateRegistration,
) -> dict[str, tuple[object, int, tuple[str, ...]]]:
    sheet = workbook[registration.sheet]
    merged_ranges = tuple(sheet.merged_cells.ranges)
    snapshot: dict[str, tuple[object, int, tuple[str, ...]]] = {}
    for cell_range in registration.protected_ranges + registration.signoff_ranges:
        min_col, min_row, max_col, max_row = range_boundaries(cell_range)
        for row in range(min_row, max_row + 1):
            for column in range(min_col, max_col + 1):
                cell = sheet.cell(row=row, column=column)
                membership = tuple(
                    sorted(
                        str(merged)
                        for merged in merged_ranges
                        if cell.coordinate in merged
                    )
                )
                snapshot[cell.coordinate] = (cell.value, cell.style_id, membership)
    return snapshot


def test_all_ballooned_pages_are_embedded_in_order(tmp_path: Path) -> None:
    """P0-EXP-005 embeds formal ballooned-PDF pages in source-page order."""
    content, registration, _ = _render(tmp_path)
    _, expected_colors = _page_images(tmp_path)
    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        images = workbook[registration.image_sheet]._images
        assert [
            (image.anchor._from.row, image.anchor._from.col) for image in images
        ] == [(1, 1), (46, 1)]
        actual_colors = []
        for image in images:
            with PillowImage.open(BytesIO(image._data())) as embedded:
                actual_colors.append(embedded.convert("RGB").getpixel((0, 0)))
        assert actual_colors == expected_colors
    finally:
        workbook.close()


def test_workbook_reopens(tmp_path: Path) -> None:
    """P0-EXP-006 requires the generated workbook to reopen with openpyxl."""
    content, registration, _ = _render(tmp_path)

    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        assert registration.sheet in workbook.sheetnames
        assert registration.image_sheet in workbook.sheetnames
    finally:
        workbook.close()


def test_general_requirement_number_is_blank(tmp_path: Path) -> None:
    """P0-EXP-007D leaves non-balloon global requirements unnumbered."""
    content, registration, _ = _render(tmp_path)
    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        detail_sheet = workbook[registration.sheet]
        assert detail_sheet["A6"].value == "1"
        assert detail_sheet["A7"].value in (None, "")
    finally:
        workbook.close()


def test_required_cells_use_confirmed_values(tmp_path: Path) -> None:
    """P0-EXP-007E exports reviewed values without rereading raw suggestions."""
    content, registration, _ = _render(tmp_path)
    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        detail_sheet = workbook[registration.sheet]
        reviewed_item = _reviewed_items()[0]
        for field, column in registration.detail_columns.items():
            assert detail_sheet[f"{column}6"].value == str(reviewed_item[field])
        assert "未经确认" not in detail_sheet["B6"].value
    finally:
        workbook.close()


def test_fixed_and_signoff_ranges_are_preserved(tmp_path: Path) -> None:
    """P0-EXP-007F preserves registered fixed/sign-off values and styles."""
    content, registration, template_path = _render(tmp_path)
    original = load_workbook(template_path, data_only=False)
    generated = load_workbook(BytesIO(content), data_only=False)
    try:
        assert _registered_range_snapshot(generated, registration) == (
            _registered_range_snapshot(original, registration)
        )
    finally:
        generated.close()
        original.close()


def test_embedded_image_count_matches_pdf_pages(tmp_path: Path) -> None:
    """P0-EXP-007G matches embedded-image count to formal PDF page count."""
    content, registration, _ = _render(tmp_path)
    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        assert len(workbook[registration.image_sheet]._images) == 2
    finally:
        workbook.close()


def test_review_cells_are_editable_and_resavable(tmp_path: Path) -> None:
    """P0-EXP-007H keeps review inputs unlocked and resavable after export."""
    content, registration, _ = _render(tmp_path)
    workbook = load_workbook(BytesIO(content), data_only=False)
    review_sheet = workbook[registration.sheet]
    assert review_sheet["D72"].protection.locked is False
    assert review_sheet["A6"].protection.locked is False
    review_sheet["D72"] = "复核员"
    resaved = BytesIO()
    workbook.save(resaved)
    workbook.close()

    reopened = load_workbook(BytesIO(resaved.getvalue()), data_only=False)
    try:
        assert reopened[registration.sheet]["D72"].value == "复核员"
    finally:
        reopened.close()
