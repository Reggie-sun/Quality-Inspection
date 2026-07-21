from dataclasses import replace

import pytest

from app.candidates.duplicates import (
    DuplicateCandidate,
    suggest_cross_view_duplicates,
)


@pytest.mark.parametrize(
    ("right_text", "right_view", "expected_pairs"),
    (
        ("M6", "view-b", [("candidate-a", "candidate-b")]),
        ("M8", "view-b", []),
        ("M6", "view-a", []),
    ),
)
def test_cross_view_match_is_suggestion_only(
    right_text: str,
    right_view: str,
    expected_pairs: list[tuple[str, str]],
) -> None:
    """P0-REC-008D: text equality only creates a confirmation relation."""
    candidates = [
        DuplicateCandidate("candidate-a", "M6", "view-a", "candidate"),
        DuplicateCandidate(
            "candidate-b",
            right_text,
            right_view,
            "ambiguous",
        ),
    ]
    before = [replace(candidate) for candidate in candidates]

    relations = suggest_cross_view_duplicates(candidates)

    assert [
        (relation.left_candidate_id, relation.right_candidate_id)
        for relation in relations
    ] == expected_pairs
    assert all(
        relation.relation_type == "possible_duplicate"
        and relation.requires_confirmation is True
        for relation in relations
    )
    assert candidates == before
    assert [candidate.candidate_id for candidate in candidates] == [
        "candidate-a",
        "candidate-b",
    ]
    assert [candidate.disposition for candidate in candidates] == [
        "candidate",
        "ambiguous",
    ]


def test_duplicate_suggestions_are_stable_and_do_not_collapse_candidates() -> None:
    """CAND-007: all cross-view pairs remain distinct and deterministically ordered."""
    candidates = [
        DuplicateCandidate("candidate-c", "M6", "view-c", "candidate"),
        DuplicateCandidate("candidate-a", "M6", "view-a", "candidate"),
        DuplicateCandidate("candidate-b", "M6", "view-b", "candidate"),
    ]

    relations = suggest_cross_view_duplicates(candidates)

    assert [
        (relation.left_candidate_id, relation.right_candidate_id)
        for relation in relations
    ] == [
        ("candidate-a", "candidate-b"),
        ("candidate-a", "candidate-c"),
        ("candidate-b", "candidate-c"),
    ]
    assert len(candidates) == 3
