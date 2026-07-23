from __future__ import annotations

from app.exports.naming import safe_stem, unique_sheet_name


def test_safe_stem_removes_traversal_illegal_characters_and_extension() -> None:
    """P0-EXP-007K keeps export filenames inside their controlled directory."""
    result = safe_stem("../../工件:<A1>?*.xlsx")

    assert result.startswith("工件")
    assert not any(character in result for character in '<>:"/\\|?*')
    assert ".." not in result
    assert not result.endswith(".xlsx")


def test_safe_stem_applies_fallback_and_length_limit() -> None:
    """P0-EXP-007K bounds empty and oversized filename stems deterministically."""
    assert safe_stem("...", fallback="inspection") == "inspection"
    assert len(safe_stem("测" * 200 + ".pdf")) == 120


def test_unique_sheet_name_sanitizes_limits_and_deduplicates_casefold() -> None:
    """P0-EXP-007K enforces Excel's illegal-char, 31-char and duplicate rules."""
    used = {"inspection"}

    first = unique_sheet_name("Inspection", used)
    second = unique_sheet_name("检验/[明细]*?" * 5, used)
    third = unique_sheet_name("检验/[明细]*?" * 5, used)

    assert first == "Inspection_2"
    assert len(second) <= 31
    assert len(third) <= 31
    assert second.casefold() != third.casefold()
    assert not any(character in second for character in "\\/*?:[]")
    assert {first.casefold(), second.casefold(), third.casefold()} <= {
        value.casefold() for value in used
    }


def test_unique_sheet_name_removes_apostrophe_exposed_by_truncation() -> None:
    """P0-EXP-007K keeps truncation from creating an invalid trailing quote."""
    result = unique_sheet_name("A" * 30 + "'tail", set())

    assert len(result) <= 31
    assert not result.endswith("'")
