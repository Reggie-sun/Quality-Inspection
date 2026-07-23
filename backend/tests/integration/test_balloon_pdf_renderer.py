from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.balloons.renderer import FrozenBalloon, render_ballooned_pdf


def _two_page_pdf_bytes() -> bytes:
    with fitz.open() as document:
        document.new_page(width=300, height=300)
        document.new_page(width=420, height=300)
        return document.tobytes()


def _approved_font_path() -> Path:
    return Path(__file__).resolve().parents[2] / "assets/fonts/DejaVuSans.ttf"


def test_p0_exp_004_renders_frozen_number_and_leader_on_original_pdf() -> None:
    """P0-EXP-004 draws reviewed formal geometry in backend PDF coordinates."""
    rendered = render_ballooned_pdf(
        _two_page_pdf_bytes(),
        [
            FrozenBalloon(
                page_index=0,
                formal_number=1,
                center_pdf=(72, 72),
                leader_target_pdf=(96, 96),
            )
        ],
        _approved_font_path(),
    )

    with fitz.open(stream=rendered, filetype="pdf") as document:
        assert "1" in document[0].get_text()
        assert len(document[0].get_drawings()) >= 2
        assert document[1].get_text() == ""


def test_page_count_matches_source() -> None:
    """P0-EXP-007I preserves every original source page in formal output."""
    source = _two_page_pdf_bytes()
    rendered = render_ballooned_pdf(
        source,
        [
            FrozenBalloon(
                page_index=1,
                formal_number=1,
                center_pdf=(72, 72),
                leader_target_pdf=(96, 96),
            )
        ],
        _approved_font_path(),
    )

    with (
        fitz.open(stream=source, filetype="pdf") as source_document,
        fitz.open(stream=rendered, filetype="pdf") as rendered_document,
    ):
        assert rendered_document.page_count == source_document.page_count == 2


def test_p0_exp_004_rendering_is_byte_deterministic_and_order_independent() -> None:
    """P0-EXP-004 gives identical frozen input one stable formal PDF identity."""
    source = _two_page_pdf_bytes()
    balloons = [
        FrozenBalloon(
            page_index=1,
            formal_number=2,
            center_pdf=(120, 120),
            leader_target_pdf=(150, 150),
        ),
        FrozenBalloon(
            page_index=0,
            formal_number=1,
            center_pdf=(72, 72),
            leader_target_pdf=(96, 96),
        ),
    ]

    first = render_ballooned_pdf(source, balloons, _approved_font_path())
    second = render_ballooned_pdf(
        source,
        list(reversed(balloons)),
        _approved_font_path(),
    )

    assert second == first


@pytest.mark.parametrize(
    "balloon",
    (
        FrozenBalloon(
            page_index=2,
            formal_number=1,
            center_pdf=(72, 72),
            leader_target_pdf=(96, 96),
        ),
        FrozenBalloon(
            page_index=0,
            formal_number=1,
            center_pdf=(5, 5),
            leader_target_pdf=(96, 96),
        ),
        FrozenBalloon(
            page_index=0,
            formal_number=1,
            center_pdf=(72, 72),
            leader_target_pdf=(500, 500),
        ),
    ),
)
def test_p0_exp_004_rejects_geometry_outside_the_original_pdf(
    balloon: FrozenBalloon,
) -> None:
    """P0-EXP-004 never emits a formal PDF from invalid frozen geometry."""
    with pytest.raises(ValueError, match="balloon page out of range|invalid balloon geometry"):
        render_ballooned_pdf(
            _two_page_pdf_bytes(),
            [balloon],
            _approved_font_path(),
        )
