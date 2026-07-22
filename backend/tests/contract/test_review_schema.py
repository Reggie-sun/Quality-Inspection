from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.review.schemas import parse_review_command, validate_edit_fields


def test_complex_item_rejects_extra_semantic_fields() -> None:
    """P0-REV-008: coarse review items expose only the four P0 fields."""
    with pytest.raises(
        ValueError,
        match="complex item fields are not editable",
    ):
        validate_edit_fields(
            {"coarse_type": "roughness"},
            {"nominal": "3.2"},
        )

    validate_edit_fields(
        {"coarse_type": "roughness"},
        {
            "raw_text": "Ra 1.6",
            "coordinates": (1, 2, 3, 4),
            "coarse_type": "roughness",
            "requires_confirmation": False,
        },
    )


@pytest.mark.parametrize("field", ["candidate_id", "balloon_required"])
def test_typed_edit_rejects_identity_and_balloon_fields(field: str) -> None:
    with pytest.raises(ValueError, match="not editable"):
        validate_edit_fields(
            {"item_type": "thread"},
            {field: "replacement" if field == "candidate_id" else False},
        )


@pytest.mark.parametrize(
    "command",
    [
        {"type": "keep", "item_id": "i1"},
        {"type": "exclude", "item_id": "i1"},
        {"type": "edit", "item_id": "i1", "fields": {"raw_text": "M6"}},
        {
            "type": "add",
            "raw_text": "M6 通",
            "item_type": "thread",
            "coordinates": (1, 2, 3, 4),
            "scope": "local_feature",
            "balloon_required": True,
        },
        {"type": "merge", "item_ids": ["i1", "i2"], "raw_text": "M6 通"},
        {
            "type": "split",
            "item_id": "i1",
            "parts": [{"raw_text": "Φ10"}, {"raw_text": "深20"}],
        },
        {"type": "resolve_confirmation", "item_id": "i1", "accepted": True},
        {
            "type": "set_balloon_required",
            "item_id": "i1",
            "balloon_required": False,
        },
    ],
)
def test_review_command_union_accepts_only_planned_commands(
    command: dict[str, object],
) -> None:
    parsed = parse_review_command(command)

    assert parsed.type == command["type"]


@pytest.mark.parametrize(
    "command",
    [
        {
            "type": "add",
            "raw_text": "M6",
            "item_type": "thread",
            "coordinates": (1, 2, 3, 4),
            "balloon_required": True,
        },
        {
            "type": "add",
            "raw_text": "M6",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
        },
    ],
)
def test_manual_add_requires_explicit_coordinates_and_scope(
    command: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        parse_review_command(command)


def test_review_commands_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        parse_review_command({"type": "keep", "item_id": "i1", "quiet": True})
