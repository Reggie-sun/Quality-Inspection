import json

from app.pdf.classification import PageSignals, classify_page


def test_vector_hybrid_and_scanned_routing() -> None:
    """P0-REC-001: supported and unsupported page routes remain explicit."""
    vector = classify_page(PageSignals(900, 20, 0.0, 400))
    hybrid = classify_page(PageSignals(900, 20, 0.95, 400))
    scanned = classify_page(PageSignals(0, 0, 1.0, 0))

    assert (vector.page_type, vector.processing_route, vector.support_level) == (
        "vector",
        "native",
        "supported",
    )
    assert (hybrid.page_type, hybrid.processing_route, hybrid.support_level) == (
        "hybrid",
        "hybrid",
        "supported",
    )
    assert (scanned.page_type, scanned.processing_route, scanned.support_level) == (
        "scanned",
        "unsupported",
        "unsupported",
    )
    assert scanned.unsupported_reason == "pure_scanned_pdf_not_supported"


def test_ambiguous_routes_as_hybrid_but_requires_review() -> None:
    """P0-REC-001: ambiguous pages cannot masquerade as supported vector pages."""
    classification = classify_page(PageSignals(10, 1, 0.45, 0))

    assert classification.page_type == "ambiguous"
    assert classification.processing_route == "hybrid"
    assert classification.support_level == "review_required"
    assert classification.review_required is True
    assert classification.unsupported_reason is None


def test_classification_evidence_is_serializable() -> None:
    """P0-REC-006E: page classification includes serializable evidence."""
    classification = classify_page(PageSignals(900, 20, 0.0, 400))

    encoded = json.dumps(classification.evidence, sort_keys=True)

    assert classification.rule_version == "v0.1"
    assert classification.confidence > 0
    assert "native_char_count" in encoded
    assert classification.to_dict()["page_type"] == "vector"
