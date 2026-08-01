import pytest

from app.candidates.coverage import CoverageEntry, check_coverage
from app.candidates.routing_evidence import routing_decision_sha256
from app.candidates.symbol_routing import RoutingDecision


@pytest.mark.parametrize(
    ("entries", "expected_ids", "blocking_count", "coverage_checked"),
    (
        (
            [
                CoverageEntry(
                    "o1",
                    "candidate",
                    "page-0:o1",
                    (1, 2, 3, 4),
                    candidate_id="candidate-1",
                ),
                CoverageEntry(
                    "o2",
                    "reference_context",
                    "page-0:o2",
                    (5, 6, 7, 8),
                ),
                CoverageEntry(
                    "o3",
                    "non_inspection",
                    "page-0:o3",
                    (9, 10, 11, 12),
                ),
            ],
            {"o1", "o2", "o3"},
            0,
            True,
        ),
        (
            [
                CoverageEntry(
                    "o1",
                    "candidate",
                    "page-0:o1",
                    (1, 2, 3, 4),
                    candidate_id="candidate-1",
                )
            ],
            {"o1", "o2"},
            1,
            False,
        ),
        (
            [
                CoverageEntry(
                    "o1",
                    "candidate",
                    "page-0:o1",
                    (1, 2, 3, 4),
                    candidate_id="candidate-1",
                ),
                CoverageEntry(
                    "o1",
                    "ambiguous",
                    "page-1:o1",
                    (5, 6, 7, 8),
                ),
            ],
            {"o1"},
            1,
            False,
        ),
    ),
)
def test_every_suspicious_observation_has_complete_disposition(
    entries: list[CoverageEntry],
    expected_ids: set[str],
    blocking_count: int,
    coverage_checked: bool,
) -> None:
    """P0-REC-009: every expected observation has one complete ownership row."""
    report = check_coverage(entries, expected_observation_ids=expected_ids)

    assert report.blocking_count == blocking_count
    assert report.coverage_checked is coverage_checked


@pytest.mark.parametrize(
    ("incomplete", "expected_blocking"),
    (
        (CoverageEntry("o2", None, "source-2", (5, 6, 7, 8)), 1),
        (CoverageEntry("o2", "candidate", None, (5, 6, 7, 8)), 1),
        (CoverageEntry("o2", "candidate", "source-2", None), 1),
        (
            CoverageEntry("o2", "candidate", "source-2", (5, 6, 7, 8)),
            1,
        ),
    ),
)
def test_ambiguous_is_reviewable_but_incomplete_is_blocking(
    incomplete: CoverageEntry,
    expected_blocking: int,
) -> None:
    """P0-REC-010: ambiguity is reviewable; incomplete ownership vetoes freeze."""
    ambiguous = CoverageEntry(
        "o1",
        "ambiguous",
        "source-1",
        (1, 2, 3, 4),
    )

    report = check_coverage(
        [ambiguous, incomplete],
        expected_observation_ids={"o1", "o2"},
    )

    assert report.review_required_count == 1
    assert report.blocking_count == expected_blocking
    assert report.coverage_checked is False


def test_confirmation_is_reviewable_without_becoming_blocking() -> None:
    """CAND-006: a complete candidate may require review and still be freezeable."""
    report = check_coverage(
        [
            CoverageEntry(
                "o1",
                "candidate",
                "source-1",
                (1, 2, 3, 4),
                candidate_id="candidate-1",
                requires_confirmation=True,
            )
        ],
        expected_observation_ids={"o1"},
    )

    assert report.review_required_count == 1
    assert report.blocking_count == 0
    assert report.coverage_checked is True


def test_rule_disposition_evidence_is_serialized_without_changing_legacy_rows() -> None:
    ruled = CoverageEntry(
        "o1",
        "non_inspection",
        "source-1",
        (1, 2, 3, 4),
        disposition_reason="exact_metadata_label",
        disposition_rule_version="p0-a1-v1",
    )
    legacy = CoverageEntry(
        "o2",
        "ambiguous",
        "source-2",
        (5, 6, 7, 8),
        requires_confirmation=True,
    )

    assert ruled.to_dict()["disposition_reason"] == "exact_metadata_label"
    assert ruled.to_dict()["disposition_rule_version"] == "p0-a1-v1"
    assert "disposition_reason" not in legacy.to_dict()
    assert "disposition_rule_version" not in legacy.to_dict()


def _visual_review(
    *,
    rejection_code: str | None = None,
    symbol_kinds: tuple[str, ...] = ("diameter",),
) -> dict[str, object]:
    return {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/3",
        "symbol_kinds": list(symbol_kinds),
        "rejection_code": rejection_code,
        "confidence_signal": (
            None if rejection_code == "visual_no_detection" else 0.98
        ),
    }


def _local_resolution_evidence(
    observation_id: str,
    *,
    requires_confirmation: bool,
) -> dict[str, object]:
    decision = RoutingDecision(
        schema_version="symbol-routing-decision/1",
        router_version="symbol-uncertainty-router/1",
        visual_observation_id=observation_id,
        input_sha256="a" * 64,
        disposition="locally_resolved",
        local_resolution_reason_codes=(
            "deterministic_geometry_complete",
            "local_projection_complete",
        ),
        escalation_reason_codes=(),
        block_reason_codes=(),
        requires_confirmation=requires_confirmation,
    )
    return {
        "schema_version": decision.schema_version,
        "router_version": decision.router_version,
        "input_sha256": decision.input_sha256,
        "decision_sha256": routing_decision_sha256(
            decision=decision,
            escalation_group_id=None,
            escalation_group_member_index=None,
            local_resolution_ref=f"sha256:{decision.input_sha256}",
        ),
        "reason_codes": list(
            decision.local_resolution_reason_codes
        ),
    }


def test_deterministic_local_visual_can_omit_provider_confidence() -> None:
    review = _visual_review(symbol_kinds=("revision_marker",))
    review["confidence_signal"] = None
    review["local_resolution_evidence"] = _local_resolution_evidence(
        "visual-local",
        requires_confirmation=True,
    )
    entry = CoverageEntry(
        "visual-local",
        "non_inspection",
        "visual-local",
        (1, 2, 3, 4),
        requires_confirmation=True,
        advisor_review=review,
    )

    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-local"},
    )

    assert report.blocking_count == 0
    assert report.review_required_count == 1


def test_forged_local_resolution_evidence_does_not_replace_confidence() -> None:
    review = _visual_review(symbol_kinds=("revision_marker",))
    review["confidence_signal"] = None
    evidence = _local_resolution_evidence(
        "visual-local",
        requires_confirmation=True,
    )
    evidence["decision_sha256"] = "b" * 64
    review["local_resolution_evidence"] = evidence
    entry = CoverageEntry(
        "visual-local",
        "non_inspection",
        "visual-local",
        (1, 2, 3, 4),
        requires_confirmation=True,
        advisor_review=review,
    )

    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-local"},
    )

    assert report.blocking_observation_ids == ("visual-local",)


def test_visual_candidate_has_one_complete_coverage_entry() -> None:
    """COV-01: one visual source owns one complete candidate disposition."""
    entry = CoverageEntry(
        "visual-1",
        "candidate",
        "visual-1",
        (1, 2, 3, 4),
        candidate_id="candidate-1",
        requires_confirmation=False,
        advisor_review=_visual_review(),
    )
    report = check_coverage(
        [entry],
        expected_observation_ids={"visual-1"},
        required_visual_observation_ids={"visual-1"},
    )
    assert report.blocking_count == 0
    assert report.review_required_count == 0
    assert report.entries == (entry,)


def test_visual_reference_noninspection_and_ambiguous_are_distinct() -> None:
    """COV-02: each noncandidate visual disposition remains distinct."""
    entries = (
        CoverageEntry(
            "visual-reference",
            "reference_context",
            "visual-reference",
            (1, 2, 3, 4),
            requires_confirmation=False,
            advisor_review=_visual_review(symbol_kinds=("datum_reference",)),
        ),
        CoverageEntry(
            "visual-revision",
            "non_inspection",
            "visual-revision",
            (5, 6, 7, 8),
            requires_confirmation=True,
            advisor_review=_visual_review(symbol_kinds=("revision_marker",)),
        ),
        CoverageEntry(
            "visual-ambiguous",
            "ambiguous",
            "visual-ambiguous",
            (9, 10, 11, 12),
            requires_confirmation=True,
            advisor_review=_visual_review(
                rejection_code="visual_no_detection",
                symbol_kinds=(),
            ),
        ),
    )
    report = check_coverage(
        entries,
        required_visual_observation_ids={
            "visual-reference",
            "visual-revision",
            "visual-ambiguous",
        },
    )
    assert report.blocking_count == 0
    assert report.review_required_count == 2
    assert tuple(entry.disposition for entry in report.entries) == (
        "reference_context",
        "non_inspection",
        "ambiguous",
    )


@pytest.mark.parametrize(
    "entry",
    (
        CoverageEntry(
            "visual-1",
            "candidate",
            None,
            (1, 2, 3, 4),
            candidate_id="candidate-1",
            advisor_review=_visual_review(),
        ),
        CoverageEntry(
            "visual-1",
            "candidate",
            "visual-1",
            None,
            candidate_id="candidate-1",
            advisor_review=_visual_review(),
        ),
        CoverageEntry(
            "visual-1",
            None,
            "visual-1",
            (1, 2, 3, 4),
            advisor_review=_visual_review(),
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            advisor_review=None,
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            advisor_review=_visual_review(
                rejection_code="visual_projection_conflict",
            ),
        ),
    ),
)
def test_visual_missing_source_coordinates_or_conflict_blocks(
    entry: CoverageEntry,
) -> None:
    """COV-03: incomplete or unexecuted visual ownership blocks coverage."""
    entries = [entry]
    if entry.advisor_review is not None and entry.advisor_review.get(
        "rejection_code"
    ) == "visual_projection_conflict":
        entries.append(entry)
    report = check_coverage(
        entries,
        required_visual_observation_ids={"visual-1"},
    )
    assert report.blocking_count == 1
    assert report.coverage_checked is False


def test_complete_visual_candidate_may_clear_semantic_confirmation() -> None:
    """COV-04: local typed projection may clear Provider-era confirmation."""
    downgraded = CoverageEntry(
        "visual-1",
        "candidate",
        "visual-1",
        (1, 2, 3, 4),
        candidate_id="candidate-1",
        requires_confirmation=False,
        advisor_review=_visual_review(),
    )
    datum = CoverageEntry(
        "visual-2",
        "reference_context",
        "visual-2",
        (5, 6, 7, 8),
        requires_confirmation=False,
        advisor_review=_visual_review(symbol_kinds=("datum_reference",)),
    )
    report = check_coverage(
        [downgraded, datum],
        required_visual_observation_ids={"visual-1", "visual-2"},
    )
    assert report.blocking_observation_ids == ()
    assert report.review_required_count == 0


@pytest.mark.parametrize(
    "advisor_review",
    (
        None,
        _visual_review(symbol_kinds=("depth", "diameter")),
        _visual_review(symbol_kinds=("diameter", "diameter")),
        _visual_review(symbol_kinds=("unknown",)),
        {
            "route": "visual_symbol",
            "schema_version": "visual-symbol-review/1",
            "symbol_kinds": "datum_reference",
            "rejection_code": None,
        },
        {
            "route": "visual_symbol",
        "schema_version": "visual-symbol-review/3",
            "symbol_kinds": ["diameter"],
            "rejection_code": None,
        },
    ),
)
def test_malformed_visual_symbol_review_blocks_without_crashing(
    advisor_review: dict[str, object] | None,
) -> None:
    entry = CoverageEntry(
        "visual-1",
        "reference_context",
        "visual-1",
        (1, 2, 3, 4),
        requires_confirmation=False,
        advisor_review=advisor_review,
    )
    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-1"},
    )
    assert report.blocking_observation_ids == ("visual-1",)


@pytest.mark.parametrize(
    "entry",
    (
        CoverageEntry(
            "visual-1",
            "candidate",
            "visual-1",
            (1, 2, 3, 4),
            candidate_id="candidate-1",
            requires_confirmation=False,
            advisor_review=_visual_review(
                symbol_kinds=("datum_reference",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "candidate",
            "visual-1",
            (1, 2, 3, 4),
            candidate_id="candidate-1",
            requires_confirmation=True,
            advisor_review=_visual_review(
                rejection_code="visual_projection_conflict",
            ),
        ),
        CoverageEntry(
            "visual-1",
            "reference_context",
            "visual-1",
            (1, 2, 3, 4),
            candidate_id="candidate-1",
            requires_confirmation=False,
            advisor_review=_visual_review(
                symbol_kinds=("datum_reference",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "reference_context",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(
                symbol_kinds=("datum_reference",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "non_inspection",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=False,
            advisor_review=_visual_review(
                symbol_kinds=("revision_marker",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(rejection_code=None),
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(
                rejection_code="visual_no_detection",
                symbol_kinds=("diameter",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "candidate",
            "other-source",
            (1, 2, 3, 4),
            candidate_id="candidate-1",
            requires_confirmation=True,
            advisor_review=_visual_review(),
        ),
        CoverageEntry(
            "visual-1",
            "candidate",
            "visual-1",
            (1, 2, 1, 4),
            candidate_id="candidate-1",
            requires_confirmation=True,
            advisor_review=_visual_review(),
        ),
        CoverageEntry(
            "visual-1",
            "candidate",
            "visual-1",
            (1, 2, float("nan"), 4),
            candidate_id="candidate-1",
            requires_confirmation=True,
            advisor_review=_visual_review(),
        ),
    ),
)
def test_illegal_visual_semantic_matrix_combination_blocks(
    entry: CoverageEntry,
) -> None:
    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-1"},
    )

    assert report.blocking_observation_ids == ("visual-1",)


@pytest.mark.parametrize(
    "entry",
    (
        CoverageEntry(
            "visual-1",
            "candidate",
            "visual-1",
            (1, 2, 3, 4),
            candidate_id="candidate-1",
            requires_confirmation=True,
            advisor_review=_visual_review(),
        ),
        CoverageEntry(
            "visual-1",
            "reference_context",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=False,
            advisor_review=_visual_review(
                symbol_kinds=("datum_reference",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "non_inspection",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(
                symbol_kinds=("revision_marker",),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(
                rejection_code="visual_projection_conflict",
            ),
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(
                rejection_code="visual_no_detection",
                symbol_kinds=(),
            ),
        ),
        CoverageEntry(
            "visual-1",
            "ambiguous",
            "visual-1",
            (1, 2, 3, 4),
            requires_confirmation=True,
            advisor_review=_visual_review(
                rejection_code="visual_bbox_invalid",
                symbol_kinds=(),
            ),
        ),
    ),
)
def test_valid_visual_semantic_matrix_is_reviewable_not_blocking(
    entry: CoverageEntry,
) -> None:
    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-1"},
    )

    assert report.blocking_count == 0
    assert report.review_required_count == int(
        entry.disposition == "ambiguous" or entry.requires_confirmation
    )


@pytest.mark.parametrize(
    "rejection_code",
    (
        "gdt_frame_not_found",
        "gdt_projection_conflict",
        "gdt_frame_segmentation_ambiguous",
        "gdt_composite_truncated",
        "gdt_value_missing",
        "gdt_datum_association_ambiguous",
    ),
)
def test_gdt_projection_failure_is_reviewable_not_coverage_blocking(
    rejection_code: str,
) -> None:
    review = _visual_review(
        rejection_code=rejection_code,
        symbol_kinds=("gdt_perpendicularity",),
    )
    review["confidence_signal"] = None
    entry = CoverageEntry(
        "visual-gdt",
        "ambiguous",
        "visual-gdt",
        (1, 2, 3, 4),
        requires_confirmation=True,
        advisor_review=review,
    )

    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-gdt"},
    )

    assert report.blocking_observation_ids == ()
    assert report.review_required_count == 1
    assert report.coverage_checked is True


@pytest.mark.parametrize(
    "symbol_kinds",
    (
        (),
        ("diameter",),
        ("gdt_parallelism", "gdt_perpendicularity"),
    ),
)
def test_gdt_projection_rejection_requires_single_gdt_kind(
    symbol_kinds: tuple[str, ...],
) -> None:
    review = _visual_review(
        rejection_code="gdt_frame_not_found",
        symbol_kinds=symbol_kinds,
    )
    review["confidence_signal"] = None
    entry = CoverageEntry(
        "visual-gdt",
        "ambiguous",
        "visual-gdt",
        (1, 2, 3, 4),
        requires_confirmation=True,
        advisor_review=review,
    )

    report = check_coverage(
        [entry],
        required_visual_observation_ids={"visual-gdt"},
    )

    assert report.blocking_observation_ids == ("visual-gdt",)
    assert report.coverage_checked is False
