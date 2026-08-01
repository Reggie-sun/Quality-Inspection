from __future__ import annotations

from types import MappingProxyType


NUMERIC_METADATA_FIELDS = frozenset(
    {"toleranced_count", "page_count", "detail_count"}
)
NUMERIC_DETAIL_FIELDS = frozenset(
    {"number", "source_page", "upper_limit", "lower_limit"}
)
TEXT_METADATA_FIELDS = frozenset(
    {"source_filename", "inspection_date", "unit", "general_tolerance_note"}
)
TEXT_DETAIL_FIELDS = frozenset(
    {"type_label", "basic_size", "tolerance"}
)
TYPE_FILL_COLORS = MappingProxyType(
    {
        "线性": "E5334E",
        "直径": "178BFF",
        "半径": "22B14C",
        "粗糙度": "C23ACF",
        "角度": "F39C3D",
        "螺纹": "009688",
        "技术要求": "6B7280",
        "复合": "B7791F",
    }
)


def expected_result_formula(row: int) -> str:
    if isinstance(row, bool) or not isinstance(row, int) or row < 1:
        raise ValueError("result formula row must be a positive integer")
    return (
        f'=IF(H{row}="","",IF(OR(F{row}="",G{row}=""),"",'
        f'IF(AND(ISNUMBER(H{row}),H{row}<=F{row},H{row}>=G{row}),"OK","NG")))'
    )
