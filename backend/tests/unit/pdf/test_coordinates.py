import pytest

from app.pdf.coordinates import PageTransform


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_render_round_trip_error_budget(rotation: int) -> None:
    """P0-REC-006F: PDF/render matrices preserve the coordinate round trip."""
    transform = PageTransform(
        width=1190.55,
        height=841.89,
        rotation=rotation,
        scale=2.0,
    )
    source = (23.25, 51.5)

    render = transform.pdf_to_render_point(source)
    restored = transform.render_to_pdf_point(render)

    assert restored == pytest.approx(source, abs=0.5)
    assert transform.apply_matrix(transform.pdf_to_render_matrix, source) == pytest.approx(
        render,
        abs=1.0,
    )
    assert transform.apply_matrix(transform.render_to_pdf_matrix, render) == pytest.approx(
        source,
        abs=0.5,
    )


def test_bbox_is_normalized_and_clipped_to_cropbox() -> None:
    """P0-REC-006C: CropBox-relative boxes are clipped and normalized."""
    transform = PageTransform(
        width=100.0,
        height=50.0,
        rotation=0,
        scale=2.0,
        crop_x=10.0,
        crop_y=20.0,
    )

    bbox_pdf = transform.clip_bbox((5.0, 18.0, 115.0, 75.0))

    assert bbox_pdf == (0.0, 0.0, 100.0, 50.0)
    assert transform.normalize_bbox(bbox_pdf) == (0.0, 0.0, 1.0, 1.0)


def test_inverted_bbox_is_rejected_before_clipping() -> None:
    """P0-REC-006C: invalid source boxes cannot become clipped facts."""
    transform = PageTransform(width=100.0, height=50.0, rotation=0, scale=1.0)

    with pytest.raises(ValueError, match="inverted"):
        transform.clip_bbox((80.0, 10.0, 20.0, 30.0))


@pytest.mark.parametrize("rotation", [-90, 45, 360])
def test_invalid_rotation_is_rejected(rotation: int) -> None:
    """P0-REC-006F: only PDF quarter-turn rotations are accepted."""
    with pytest.raises(ValueError, match="rotation"):
        PageTransform(width=100.0, height=50.0, rotation=rotation, scale=1.0)
