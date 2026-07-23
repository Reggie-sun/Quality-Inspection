from sqlalchemy import inspect, text

from app.db import engine


def test_core_migration_creates_only_planned_tables() -> None:
    """P0-RES-001/002/003 limit schema to planned persistence Owners."""
    tables = set(inspect(engine).get_table_names())

    assert tables == {
        "alembic_version",
        "projects",
        "stored_files",
        "operation_records",
        "logical_jobs",
        "error_records",
        "automatic_results",
        "review_working_copies",
        "review_locks",
        "balloons",
        "reviewed_results",
        "export_jobs",
        "export_artifacts",
    }


def test_processing_migration_has_exact_owned_columns() -> None:
    """P0-RUN-010 and P0-RES-006 add only result ref and error envelope."""
    inspector = inspect(engine)

    assert {column["name"] for column in inspector.get_columns("logical_jobs")} == {
        "id",
        "project_id",
        "logical_task_key",
        "status",
        "result_ref",
    }
    assert {column["name"] for column in inspector.get_columns("error_records")} == {
        "id",
        "project_id",
        "code",
        "message",
        "severity",
        "stage",
        "location_ref",
        "cause_category",
    }


def test_automatic_result_schema_and_immutability_trigger() -> None:
    """P0-RES-001 freezes the exact raw-result fields once per logical job."""
    inspector = inspect(engine)

    assert {
        column["name"]
        for column in inspector.get_columns("automatic_results")
    } == {
        "id",
        "project_id",
        "source_file_id",
        "logical_job_id",
        "inventory_ref",
        "candidates",
        "coverage",
        "provider_call_ids",
        "schema_version",
        "created_at",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("automatic_results")
    } == {"uq_automatic_results_logical_job_id"}
    with engine.connect() as connection:
        triggers = set(
            connection.scalars(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'automatic_results'::regclass "
                    "AND NOT tgisinternal"
                )
            )
        )
    assert triggers == {"prevent_automatic_result_update_delete"}


def test_review_schema_has_exact_current_persistence_shape() -> None:
    """P0-RES-002/EXP-002 persist review state plus fixed SIP metadata."""
    inspector = inspect(engine)

    assert {
        column["name"]
        for column in inspector.get_columns("review_working_copies")
    } == {
        "id",
        "project_id",
        "raw_result_id",
        "version",
        "items",
        "coverage",
        "sip_metadata",
        "numbering_stale",
        "items_frozen_at",
        "items_frozen_by",
        "items_frozen_version",
        "created_at",
        "updated_at",
    }
    assert {
        column["name"] for column in inspector.get_columns("review_locks")
    } == {
        "project_id",
        "operator_id",
        "expires_at",
    }


def test_balloon_and_reviewed_result_schema_is_exact() -> None:
    """P0-RES-003/BAL-005/EXP-002 persist final reviewed export facts."""
    inspector = inspect(engine)

    assert {column["name"] for column in inspector.get_columns("balloons")} == {
        "id",
        "project_id",
        "inspection_item_id",
        "source_location_id",
        "page_index",
        "suggested_number",
        "formal_number",
        "sort_order",
        "anchor_bbox_pdf",
        "leader_target_pdf",
        "center_pdf",
        "placement_status",
        "collision_flags",
        "status",
        "version",
    }
    indexes = {
        index["name"]: index for index in inspector.get_indexes("balloons")
    }
    assert set(indexes) == {
        "uq_balloons_active_item",
        "uq_balloons_active_formal_number",
    }
    assert all(index["unique"] for index in indexes.values())

    assert {
        column["name"] for column in inspector.get_columns("reviewed_results")
    } == {
        "id",
        "project_id",
        "working_copy_id",
        "working_version",
        "items",
        "balloons",
        "sip_metadata",
        "schema_version",
        "created_at",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("reviewed_results")
    } == {"uq_reviewed_results_working_version"}
    with engine.connect() as connection:
        triggers = set(
            connection.scalars(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'reviewed_results'::regclass "
                    "AND NOT tgisinternal"
                )
            )
        )
    assert triggers == {"prevent_reviewed_result_update_delete"}


def test_export_schema_has_atomic_publication_shape() -> None:
    """P0-EXP-009 persists one success gate for all three artifacts."""
    inspector = inspect(engine)

    assert {column["name"] for column in inspector.get_columns("export_jobs")} == {
        "id",
        "project_id",
        "reviewed_result_id",
        "status",
        "template_version",
        "mapping_version",
        "renderer_version",
        "error_id",
        "created_at",
        "completed_at",
    }
    job_indexes = {
        index["name"]: index for index in inspector.get_indexes("export_jobs")
    }
    assert set(job_indexes) == {"uq_export_jobs_success_identity"}
    assert job_indexes["uq_export_jobs_success_identity"]["unique"] is True
    assert job_indexes["uq_export_jobs_success_identity"]["column_names"] == [
        "reviewed_result_id",
        "template_version",
        "mapping_version",
        "renderer_version",
    ]
    success_predicate = str(
        job_indexes["uq_export_jobs_success_identity"]["dialect_options"][
            "postgresql_where"
        ]
    )
    assert "status" in success_predicate
    assert "'success'" in success_predicate

    assert {
        column["name"] for column in inspector.get_columns("export_artifacts")
    } == {
        "id",
        "export_id",
        "kind",
        "staging_ref",
        "published_ref",
        "sha256",
        "size_bytes",
        "reviewed_result_id",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("export_artifacts")
    } == {"uq_export_artifacts_export_kind"}
