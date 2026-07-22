from app.balloons.numbering import (
    NumberableItem,
    assign_numbers,
    assign_formal_numbers,
    assign_suggested_numbers,
)


def _items() -> list[NumberableItem]:
    return [
        NumberableItem("i2", True, 1, (20, 10, 30, 20), "B"),
        NumberableItem("general", False, 0, (0, 0, 0, 0), "G"),
        NumberableItem("i1", True, 0, (10, 10, 20, 20), "A"),
    ]


def test_suggested_numbers_are_stable_and_contiguous() -> None:
    """P0-BAL-001: suggested numbering is repeatable and contiguous."""
    first = assign_suggested_numbers(_items())
    second = assign_suggested_numbers(list(reversed(_items())))

    assert first == second
    assert [(item.item_id, item.number) for item in first] == [
        ("i1", 1),
        ("i2", 2),
    ]


def test_default_start_is_one() -> None:
    """P0-BAL-003: formal numbering starts at one by default."""
    assert assign_numbers(_items())[0].number == 1


def test_formal_sequence_has_no_gap_or_duplicate() -> None:
    """P0-BAL-004: formal numbering is unique and gap-free."""
    result = assign_formal_numbers(_items())

    assert [(item.item_id, item.number) for item in result] == [
        ("i1", 1),
        ("i2", 2),
    ]
    assert [item.number for item in result] == list(range(1, len(result) + 1))


def test_general_requirements_do_not_consume_numbers() -> None:
    """P0-BAL-005: non-balloon requirements never consume a number."""
    result = assign_formal_numbers(_items())

    assert {item.item_id for item in result} == {"i1", "i2"}
