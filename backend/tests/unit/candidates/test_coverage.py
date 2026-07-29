import pytest

from app.candidates.coverage import CoverageEntry, check_coverage


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


def _visual_review(
    *,
    rejection_code: str | None = None,
    symbol_kinds: tuple[str, ...] = ("diameter",),
) -> dict[str, object]:
    return {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/1",
        "symbol_kinds": list(symbol_kinds),
        "rejection_code": rejection_code,
    }


def test_visual_candidate_has_one_complete_coverage_entry() -> None:
    """COV-01: one visual source owns one complete candidate disposition."""
    entry = CoverageEntry(
        "visual-1",
        "candidate",
        "visual-1",
        (1, 2, 3, 4),
        candidate_id="candidate-1",
        requires_confirmation=True,
        advisor_review=_visual_review(),
    )
    report = check_coverage(
        [entry],
        expected_observation_ids={"visual-1"},
        required_visual_observation_ids={"visual-1"},
    )
    assert report.blocking_count == 0
    assert report.review_required_count == 1
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


def test_visual_confirmation_cannot_be_downgraded() -> None:
    """COV-04: only a locally validated datum reference can clear review."""
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
    assert report.blocking_observation_ids == ("visual-1",)


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
            requires_confirmation=True,
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
