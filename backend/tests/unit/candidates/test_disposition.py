import pytest

from app.candidates.disposition import classify_technical_requirement


@pytest.mark.parametrize(
    "text",
    [
        "检查外观，不得有裂纹",
        "测量倒角，尺寸应为1×45°",
    ],
)
def test_executable_general_requirement(text: str) -> None:
    """P0-REC-007K: explicit executable checks become unballooned global items."""
    candidate = classify_technical_requirement(text, source_id=f"source:{text}")

    assert candidate is not None
    assert candidate.item_type == "general_requirement"
    assert candidate.scope == "global_requirement"
    assert candidate.balloon_required is False
    assert candidate.raw_text == text


@pytest.mark.parametrize(
    "text",
    ["技术要求", "详见图纸", "一般说明", "检查外观", "不得有裂纹"],
)
def test_non_executable_text_is_not_an_inspection_item(text: str) -> None:
    """P0-REC-007K: headings and vague references do not masquerade as items."""
    assert classify_technical_requirement(text, source_id=f"source:{text}") is None


def test_executable_requirement_requires_source_identity() -> None:
    """P0-REC-007K: accepted requirements require stable source identity."""
    with pytest.raises(TypeError, match="source_id"):
        classify_technical_requirement("检查外观，不得有裂纹")


@pytest.mark.parametrize("source_id", ["", "   "])
def test_executable_requirement_rejects_blank_source_identity(
    source_id: str,
) -> None:
    """P0-REC-007K: blank source identity cannot seed an accepted requirement."""
    with pytest.raises(ValueError, match="source_id"):
        classify_technical_requirement(
            "检查外观，不得有裂纹",
            source_id=source_id,
        )


def test_identical_requirements_at_distinct_sources_keep_distinct_identity() -> None:
    """P0-REC-007K / CAND-003: text alone cannot determine candidate identity."""
    text = "检查外观，不得有裂纹"

    first = classify_technical_requirement(
        text,
        (1, 2, 3, 4),
        source_id="view-1:observation-7",
    )
    second = classify_technical_requirement(
        text,
        (1, 2, 3, 4),
        source_id="view-2:observation-3",
    )

    assert first is not None
    assert second is not None
    assert first.candidate_id != second.candidate_id
