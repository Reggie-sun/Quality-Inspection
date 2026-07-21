from sqlalchemy import inspect

from app.db import engine


def test_core_migration_creates_only_planned_tables() -> None:
    """P0-RUN-002E limits the D1 schema to the four planned core tables."""
    tables = set(inspect(engine).get_table_names())

    assert tables == {
        "alembic_version",
        "projects",
        "stored_files",
        "operation_records",
        "logical_jobs",
    }
