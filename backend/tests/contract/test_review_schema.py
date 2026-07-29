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
        {
            "type": "promote_source",
            "observation_id": "observation-1",
            "raw_text": "  M6 通  ",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
        {
            "type": "ignore_source",
            "observation_id": "observation-1",
        },
        {
            "type": "ignore_sources",
            "observation_ids": ["observation-1", "observation-2"],
        },
    ],
)
def test_review_command_union_accepts_only_planned_commands(
    command: dict[str, object],
) -> None:
    parsed = parse_review_command(command)

    assert parsed.type == command["type"]
    if parsed.type == "promote_source":
        assert parsed.raw_text == "M6 通"


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "auto_accepted"),
        ("acceptance_source", "provider"),
        (
            "confidence_decision",
            {
                "band": "high",
                "review_disposition": "auto_accepted",
                "policy_version": "candidate-confidence/1",
                "evidence_codes": ["typed_schema_complete"],
            },
        ),
    ],
)
def test_review_commands_cannot_overwrite_confidence_provenance(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        parse_review_command(
            {"type": "keep", "item_id": "i1", field: value}
        )


@pytest.mark.parametrize(
    "command",
    [
        {
            "type": "promote_source",
            "observation_id": "observation-1",
            "raw_text": "   ",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 0,
        },
        {
            "type": "promote_source",
            "observation_id": "observation-1",
            "raw_text": "M6 通",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
        },
        {
            "type": "ignore_source",
            "observation_id": "source-only",
            "accepted": False,
        },
    ],
)
def test_source_review_commands_require_exact_fields(
    command: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        parse_review_command(command)


@pytest.mark.parametrize(
    "observation_ids",
    [[], [""], ["observation-1", "observation-1"]],
)
def test_ignore_sources_requires_unique_nonblank_targets(
    observation_ids: list[str],
) -> None:
    with pytest.raises(ValidationError):
        parse_review_command(
            {
                "type": "ignore_sources",
                "observation_ids": observation_ids,
            }
        )


def test_promote_source_rejects_coordinates_as_extra_field() -> None:
    command = {
        "type": "promote_source",
        "observation_id": "observation-1",
        "raw_text": "M6 通",
        "item_type": "thread",
        "scope": "local_feature",
        "balloon_required": True,
        "page_index": 0,
        "coordinates": (1, 2, 3, 4),
    }

    with pytest.raises(ValidationError) as exc_info:
        parse_review_command(command)

    assert any(
        error["loc"][-1] == "coordinates" and error["type"] == "extra_forbidden"
        for error in exc_info.value.errors()
    )


def test_promote_source_rejects_negative_page_index() -> None:
    command = {
        "type": "promote_source",
        "observation_id": "observation-1",
        "raw_text": "M6 通",
        "item_type": "thread",
        "scope": "local_feature",
        "balloon_required": True,
        "page_index": -1,
    }

    with pytest.raises(ValidationError) as exc_info:
        parse_review_command(command)

    assert any(
        error["loc"][-1] == "page_index"
        and error["type"] == "greater_than_equal"
        for error in exc_info.value.errors()
    )


def test_sip_detail_remarks_are_optional_and_bounded() -> None:
    command = {
        "type": "set_sip_detail_fields",
        "item_id": "item-1",
        "inspection_item": "直径",
        "inspection_standard": "按图纸",
        "inspection_method": "卡尺",
        "key_dimension": "是",
        "inspection_role": "IPQC",
        "source_page": 1,
    }
    parsed = parse_review_command(command)
    assert parsed.remarks == ""

    with pytest.raises(ValidationError):
        parse_review_command({**command, "remarks": "注" * 2001})
