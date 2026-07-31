from __future__ import annotations


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


def expected_result_formula(row: int) -> str:
    if isinstance(row, bool) or not isinstance(row, int) or row < 1:
        raise ValueError("result formula row must be a positive integer")
    return (
        f'=IF(H{row}="","",IF(OR(F{row}="",G{row}=""),"",'
        f'IF(AND(ISNUMBER(H{row}),H{row}<=F{row},H{row}>=G{row}),"OK","NG")))'
    )
