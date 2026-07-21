from decimal import Decimal

import pytest

from app.candidates.parser import parse_annotation


@pytest.mark.parametrize(
    ("text", "nominal"),
    [
        ("25", Decimal("25")),
        ("12.50", Decimal("12.50")),
    ],
)
def test_linear_dimension(text: str, nominal: Decimal) -> None:
    """P0-REC-007A: deterministic parsing preserves a linear nominal."""
    candidate = parse_annotation(text)

    assert candidate.item_type == "linear_dimension"
    assert candidate.nominal == nominal
    assert candidate.raw_text == text


@pytest.mark.parametrize(
    ("text", "upper", "lower"),
    [
        ("25±0.02", Decimal("0.02"), Decimal("-0.02")),
        ("25+0.03/-0.01", Decimal("0.03"), Decimal("-0.01")),
        ("25+0.03/0", Decimal("0.03"), Decimal("0")),
        ("25+0.03/+0.01", Decimal("0.03"), Decimal("0.01")),
        ("25-0.01/-0.03", Decimal("-0.01"), Decimal("-0.03")),
    ],
)
def test_symmetric_and_asymmetric_tolerance(
    text: str,
    upper: Decimal,
    lower: Decimal,
) -> None:
    """P0-REC-007B: both tolerance forms retain Decimal values and source text."""
    candidate = parse_annotation(text)

    assert candidate.item_type == "linear_dimension"
    assert candidate.upper_tolerance == upper
    assert candidate.lower_tolerance == lower
    assert candidate.raw_text == text


@pytest.mark.parametrize("symbol", ["Φ", "⌀", "∅", "ø"])
def test_diameter_feature_kind_is_not_guessed(symbol: str) -> None:
    """P0-REC-007C: a diameter symbol alone never proves the feature is a hole."""
    candidate = parse_annotation(f"{symbol}20")

    assert candidate.item_type == "diameter_dimension"
    assert candidate.nominal == Decimal("20")
    assert candidate.feature_kind == "unknown"
    assert candidate.requires_confirmation is True


@pytest.mark.parametrize(
    ("text", "spec", "depth", "through"),
    [
        ("M6深10", "M6", Decimal("10"), False),
        ("M6×1通", "M6×1", None, True),
        ("M8贯穿", "M8", None, True),
    ],
)
def test_thread(
    text: str,
    spec: str,
    depth: Decimal | None,
    through: bool,
) -> None:
    """P0-REC-007D: thread spec, depth, and through stay on one annotation."""
    candidate = parse_annotation(text)

    assert candidate.item_type == "thread"
    assert candidate.thread_spec == spec
    assert candidate.thread_depth == depth
    assert candidate.through is through


@pytest.mark.parametrize(
    ("text", "value"),
    [("R5", Decimal("5")), ("R2.5", Decimal("2.5"))],
)
def test_radius(text: str, value: Decimal) -> None:
    """P0-REC-007E: radius annotations preserve their Decimal value."""
    candidate = parse_annotation(text)

    assert candidate.item_type == "radius"
    assert candidate.radius_value == value


@pytest.mark.parametrize(
    ("text", "value", "upper", "lower"),
    [
        ("45°", Decimal("45"), None, None),
        ("45°±0.5°", Decimal("45"), Decimal("0.5"), Decimal("-0.5")),
    ],
)
def test_angle(
    text: str,
    value: Decimal,
    upper: Decimal | None,
    lower: Decimal | None,
) -> None:
    """P0-REC-007F: angle annotations retain value and optional tolerance."""
    candidate = parse_annotation(text)

    assert candidate.item_type == "angle"
    assert candidate.angle_value == value
    assert candidate.upper_tolerance == upper
    assert candidate.lower_tolerance == lower


@pytest.mark.parametrize("text", ["", "技术要求", "25 mm"])
def test_unsupported_annotation_fails_explicitly(text: str) -> None:
    """P0-REC-007A: unsupported text cannot silently become a typed dimension."""
    with pytest.raises(ValueError, match="unsupported deterministic annotation"):
        parse_annotation(text)
