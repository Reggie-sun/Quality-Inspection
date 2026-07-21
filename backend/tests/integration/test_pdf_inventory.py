from pathlib import Path

import pymupdf

from app.pdf.inventory import build_inventory


def test_multi_page_inventory_preserves_order(tmp_path: Path) -> None:
    """P0-REC-002: multi-page inventory preserves zero-based source order."""
    pdf_path = tmp_path / "multi-page.pdf"
    document = pymupdf.open()
    first = document.new_page(width=595.0, height=842.0)
    first.insert_text((72.0, 96.0), "FIRST PAGE DIMENSION 25")
    second = document.new_page(width=1191.0, height=842.0)
    second.insert_text((72.0, 96.0), "SECOND PAGE DIMENSION 50")
    document.save(pdf_path)
    document.close()

    inventory = build_inventory(pdf_path)

    assert [page.page_index for page in inventory] == [0, 1]
    assert [(page.width, page.height) for page in inventory] == [
        (595.0, 842.0),
        (1191.0, 842.0),
    ]
    assert "FIRST PAGE" in " ".join(
        observation.raw_text for observation in inventory[0].observations
    )
    assert "SECOND PAGE" in " ".join(
        observation.raw_text for observation in inventory[1].observations
    )
