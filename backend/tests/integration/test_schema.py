from sqlalchemy import inspect

from app.db import engine


def test_core_migration_creates_only_planned_tables() -> None:
    """P0-RUN-002E and P0-RES-006 limit schema to the planned D2 tables."""
    tables = set(inspect(engine).get_table_names())

    assert tables == {
        "alembic_version",
        "projects",
        "stored_files",
        "operation_records",
        "logical_jobs",
        "error_records",
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
