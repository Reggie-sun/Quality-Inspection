from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.candidates.complex_fallback import coarse_candidate
from app.candidates.schemas import Candidate


def _assert_four_field_fallback(raw_text: str, coarse_type: str) -> None:
    result = coarse_candidate(raw_text, coarse_type, (1, 2, 3, 4))

    assert set(result.model_dump()) == {
        "raw_text",
        "coordinates",
        "coarse_type",
        "requires_confirmation",
    }
    assert result.raw_text == raw_text
    assert result.coarse_type == coarse_type
    assert result.requires_confirmation is True

    with pytest.raises(ValidationError):
        Candidate(
            candidate_id="candidate-1",
            item_type=coarse_type,
            raw_text=raw_text,
            normalized_text=raw_text,
            nominal=Decimal("123"),
        )


@pytest.mark.parametrize("raw_text", ["⌖ 0.02 A", "⌒ 0.01 A B"])
def test_gdt_field_allowlist(raw_text: str) -> None:
    """P0-REC-008A: GD&T fallback exposes exactly four coarse fields."""
    _assert_four_field_fallback(raw_text, "geometric_tolerance")


@pytest.mark.parametrize("raw_text", ["Ra 3.2", "其余表面 Ra 6.3"])
def test_roughness_field_allowlist(raw_text: str) -> None:
    """P0-REC-008B: roughness fallback exposes exactly four coarse fields."""
    _assert_four_field_fallback(raw_text, "roughness")


@pytest.mark.parametrize("raw_text", ["角焊缝 5", "焊缝连续且无裂纹"])
def test_weld_field_allowlist(raw_text: str) -> None:
    """P0-REC-008C: weld fallback exposes exactly four coarse fields."""
    _assert_four_field_fallback(raw_text, "weld")
