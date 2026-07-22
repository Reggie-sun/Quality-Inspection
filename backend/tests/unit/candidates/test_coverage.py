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
