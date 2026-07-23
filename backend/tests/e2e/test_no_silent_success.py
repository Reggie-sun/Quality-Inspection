from __future__ import annotations

import pytest

from test_offline_vertical import db_session as db_session
from test_offline_vertical import (
    frozen_reviewed_result as frozen_reviewed_result,
)
from test_offline_vertical import (
    FAILURE_EVIDENCE_REQUIREMENTS as EXPECTED_FAILURE_EVIDENCE,
)
from test_offline_vertical import vertical_system as vertical_system


@pytest.mark.parametrize(
    "failure_point",
    list(EXPECTED_FAILURE_EVIDENCE),
)
def test_p0_acc_007_no_silent_success(
    vertical_system,
    frozen_reviewed_result,
    failure_point: str,
    record_property,
) -> None:
    """P0-ACC-007 forbids formal publication after fatal/blocking failure."""
    vertical_system.replace_dependency_with_failure(failure_point)

    export_id = vertical_system.export(frozen_reviewed_result.id)

    export_status = vertical_system.export_status(export_id)
    successful_exports = vertical_system.successful_exports(export_id)
    formal_downloads = vertical_system.formal_downloads(export_id)
    published_refs = vertical_system.published_refs(export_id)
    error = vertical_system.export_error(export_id)
    evidence = vertical_system.failure_evidence(export_id)

    assert {
        key: evidence[key] for key in EXPECTED_FAILURE_EVIDENCE[failure_point]
    } == EXPECTED_FAILURE_EVIDENCE[failure_point]
    if failure_point in {"provider", "storage"}:
        assert vertical_system.processing_result_counts(export_id) == {
            "automatic_results": 0,
            "review_working_copies": 0,
            "reviewed_results": 0,
            "export_jobs": 0,
        }

    record_property("failure_point", failure_point)
    record_property("export_status", export_status)
    record_property("successful_exports", len(successful_exports))
    record_property("formal_downloads", len(formal_downloads))
    record_property("published_refs", len(published_refs))
    for name in (
        "evidence_source",
        "status_owner",
        "error_code",
        "recorded_stage",
        "error_severity",
        "severity_source",
    ):
        record_property(name, evidence[name])

    assert export_status == "failed"
    assert successful_exports == []
    assert formal_downloads == []
    assert published_refs == []
    assert error["stage"] == failure_point
    assert error["severity"] in {"fatal", "blocking"}
