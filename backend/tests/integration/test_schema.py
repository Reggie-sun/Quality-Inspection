import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.db import engine


def _migration_0008() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/0010_technical_requirements.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_migration_0010_technical_requirements",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_0008_downgrade_fixture(
    connection: Connection,
    schema: str,
) -> None:
    connection.execute(text(f"CREATE SCHEMA {schema}"))
    connection.execute(text(f"SET LOCAL search_path TO {schema}"))
    connection.execute(
        text(
            "CREATE TABLE automatic_results ("
            "id integer PRIMARY KEY, "
            "technical_requirements jsonb NOT NULL DEFAULT '[]'::jsonb"
            ")"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE review_working_copies ("
            "id integer PRIMARY KEY, "
            "technical_requirements jsonb NOT NULL DEFAULT '[]'::jsonb"
            ")"
        )
    )


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
        "symbol_routing_decisions",
        "symbol_escalation_attempt_events",
        "symbol_escalation_outcomes",
        "visual_symbol_cache_entries",
        "recognition_preview_revisions",
        "recognition_preview_heads",
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
        "processing_stage",
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


def test_project_schema_has_frozen_routing_and_catalog_metadata() -> None:
    inspector = inspect(engine)

    project_columns = {
        column["name"]: column
        for column in inspector.get_columns("projects")
    }
    assert set(project_columns) == {
        "id",
        "state",
        "version",
        "recognition_mode",
        "recognition_router_version",
        "source_filename",
        "created_at",
        "last_opened_at",
    }
    mode_columns = {
        name: project_columns[name]
        for name in {"recognition_mode", "recognition_router_version"}
    }
    assert mode_columns["recognition_mode"]["nullable"] is False
    assert mode_columns["recognition_router_version"]["nullable"] is False
    assert "legacy_high_recall" in str(
        mode_columns["recognition_mode"]["default"]
    )
    assert "legacy" in str(
        mode_columns["recognition_router_version"]["default"]
    )
    assert project_columns["source_filename"]["nullable"] is True
    for name in ("created_at", "last_opened_at"):
        assert project_columns[name]["nullable"] is False
        assert "now()" in str(project_columns[name]["default"])
    checks = {
        constraint["name"]: constraint
        for constraint in inspector.get_check_constraints("projects")
    }
    assert set(checks) == {"ck_projects_recognition_mode"}
    sqltext = checks["ck_projects_recognition_mode"]["sqltext"]
    assert "legacy_high_recall" in sqltext
    assert "shadow_uncertainty" in sqltext
    assert "production_uncertainty" in sqltext
    assert "verification_high_recall" not in sqltext


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
        "technical_requirements",
        "provider_call_ids",
        "schema_version",
        "completeness",
        "recognition_mode",
        "router_version",
        "recognition_summary",
        "recognition_evidence_ref",
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


def test_symbol_routing_evidence_schema_is_exact_and_immutable() -> None:
    inspector = inspect(engine)
    expected_columns = {
        "symbol_routing_decisions": {
            "id",
            "project_id",
            "visual_observation_id",
            "escalation_group_id",
            "escalation_group_member_index",
            "local_resolution_ref",
            "schema_version",
            "router_version",
            "input_sha256",
            "disposition",
            "local_resolution_reason_codes",
            "escalation_reason_codes",
            "block_reason_codes",
            "requires_confirmation",
            "decision_sha256",
            "created_at",
        },
        "symbol_escalation_attempt_events": {
            "id",
            "project_id",
            "escalation_group_id",
            "routing_decision_sha256",
            "attempt_index",
            "event_code",
            "cache_entry_id",
            "provider_request_id",
            "event_sha256",
            "created_at",
        },
        "symbol_escalation_outcomes": {
            "id",
            "project_id",
            "escalation_group_id",
            "routing_decision_sha256",
            "schema_version",
            "outcome_code",
            "observation_outcomes",
            "attempt_event_sha256s",
            "terminal",
            "outcome_sha256",
            "created_at",
        },
        "visual_symbol_cache_entries": {
            "id",
            "project_id",
            "cache_key",
            "cache_schema_version",
            "identity_sha256",
            "identity",
            "response",
            "response_sha256",
            "producer_request_id",
            "producer_call_record_ref",
            "producer_provenance",
            "provenance_sha256",
            "created_at",
        },
    }
    for table, columns in expected_columns.items():
        assert {
            column["name"] for column in inspector.get_columns(table)
        } == columns

    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "symbol_routing_decisions"
        )
    } == {"uq_symbol_routing_decision_observation"}
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "symbol_escalation_attempt_events"
        )
    } == {
        "uq_symbol_escalation_attempt_event",
        "uq_symbol_escalation_attempt_hash",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "symbol_escalation_outcomes"
        )
    } == {"uq_symbol_escalation_outcome_group"}
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "visual_symbol_cache_entries"
        )
    } == {"uq_visual_symbol_cache_project_key"}

    with engine.connect() as connection:
        for table in expected_columns:
            triggers = set(
                connection.scalars(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE tgrelid = to_regclass(:table_name) "
                        "AND NOT tgisinternal"
                    ),
                    {"table_name": table},
                )
            )
            assert triggers == {f"prevent_{table}_update_delete"}


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
        "technical_requirements",
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


def test_technical_requirement_migration_downgrade_accepts_empty_evidence() -> None:
    schema = f"test_0008_empty_{uuid.uuid4().hex}"
    migration = _migration_0008()

    with engine.begin() as connection:
        _create_0008_downgrade_fixture(connection, schema)
        migration.op = Operations(MigrationContext.configure(connection))

        migration.downgrade()

        inspector = inspect(connection)
        assert {
            column["name"]
            for column in inspector.get_columns(
                "automatic_results",
                schema=schema,
            )
        } == {"id"}
        assert {
            column["name"]
            for column in inspector.get_columns(
                "review_working_copies",
                schema=schema,
            )
        } == {"id"}
        connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))


@pytest.mark.parametrize(
    "table_name",
    ["automatic_results", "review_working_copies"],
)
def test_technical_requirement_migration_downgrade_refuses_evidence(
    table_name: str,
) -> None:
    schema = f"test_0008_populated_{uuid.uuid4().hex}"
    migration = _migration_0008()

    with engine.begin() as connection:
        _create_0008_downgrade_fixture(connection, schema)
        connection.execute(
            text(
                f"INSERT INTO {table_name} "
                "(id, technical_requirements) "
                "VALUES (1, '[{\"requirement_id\": \"r1\"}]'::jsonb)"
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))

        with pytest.raises(
            RuntimeError,
            match="technical requirement evidence exists",
        ):
            migration.downgrade()

        inspector = inspect(connection)
        for persisted_table in (
            "automatic_results",
            "review_working_copies",
        ):
            assert {
                column["name"]
                for column in inspector.get_columns(
                    persisted_table,
                    schema=schema,
                )
            } == {"id", "technical_requirements"}
        assert connection.scalar(
            text(
                f"SELECT count(*) FROM {table_name} "
                "WHERE technical_requirements <> '[]'::jsonb"
            )
        ) == 1
        connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))


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
