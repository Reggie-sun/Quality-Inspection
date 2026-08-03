from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.projects import models as project_models


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/0014_project_lifecycle.py"
)


def _migration_0014() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_migration_0014_project_lifecycle",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_pre_lifecycle_projects(schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
        connection.execute(text(f"SET LOCAL search_path TO {schema}"))
        connection.execute(
            text(
                "CREATE TABLE projects ("
                "id uuid PRIMARY KEY, "
                "source_filename varchar(255) NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO projects (id, source_filename) VALUES "
                "('11111111-1111-4111-8111-111111111111', 'drawing.pdf'), "
                "('22222222-2222-4222-8222-222222222222', NULL)"
            )
        )


def test_project_lifecycle_model_defaults_catalog_projects_to_active() -> None:
    lifecycle = project_models.ProjectLifecycleStatus
    column = project_models.Project.__table__.c.lifecycle_status

    assert lifecycle.ACTIVE.value == "active"
    assert column.default.arg == lifecycle.ACTIVE
    assert str(column.server_default.arg) == "active"


def test_project_lifecycle_migration_is_attached_to_current_head() -> None:
    assert MIGRATION_PATH.exists()
    migration = _migration_0014()

    assert migration.revision == "0014"
    assert migration.down_revision == "0013"


def test_project_lifecycle_migration_backfills_and_enforces_constraints() -> None:
    schema = f"project_lifecycle_{uuid.uuid4().hex}"
    _create_pre_lifecycle_projects(schema)
    migration = _migration_0014()

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

            rows = connection.execute(
                text(
                    "SELECT source_filename, lifecycle_status "
                    "FROM projects ORDER BY source_filename NULLS LAST"
                )
            ).all()
            assert rows == [("drawing.pdf", "active"), (None, "unlisted")]

            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns(
                    "projects",
                    schema=schema,
                )
            }
            assert columns["lifecycle_status"]["nullable"] is False

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            "UPDATE projects SET predecessor_project_id = id "
                            "WHERE source_filename = 'drawing.pdf'"
                        )
                    )

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            "UPDATE projects SET lifecycle_status = 'deleted' "
                            "WHERE source_filename = 'drawing.pdf'"
                        )
                    )

            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, source_filename, lifecycle_status, predecessor_project_id) "
                    "VALUES "
                    "('33333333-3333-4333-8333-333333333333', 'v2.pdf', "
                    "'reprocessing', '11111111-1111-4111-8111-111111111111')"
                )
            )
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            "INSERT INTO projects "
                            "(id, source_filename, lifecycle_status, "
                            "predecessor_project_id) VALUES "
                            "('44444444-4444-4444-8444-444444444444', "
                            "'v3.pdf', 'reprocessing', "
                            "'11111111-1111-4111-8111-111111111111')"
                        )
                    )
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


def test_project_lifecycle_migration_downgrade_refuses_lifecycle_truth() -> None:
    schema = f"project_lifecycle_downgrade_{uuid.uuid4().hex}"
    _create_pre_lifecycle_projects(schema)
    migration = _migration_0014()

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            connection.execute(
                text(
                    "UPDATE projects SET lifecycle_status = 'deleted', "
                    "deleted_at = now() WHERE source_filename = 'drawing.pdf'"
                )
            )

            with pytest.raises(
                RuntimeError,
                match="project lifecycle evidence exists",
            ):
                migration.downgrade()

            assert {
                column["name"]
                for column in inspect(connection).get_columns(
                    "projects",
                    schema=schema,
                )
            } >= {
                "lifecycle_status",
                "predecessor_project_id",
                "deleted_at",
            }
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


def test_project_lifecycle_migration_downgrade_removes_empty_contract() -> None:
    schema = f"project_lifecycle_empty_{uuid.uuid4().hex}"
    _create_pre_lifecycle_projects(schema)
    migration = _migration_0014()

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            migration.downgrade()

            assert {
                column["name"]
                for column in inspect(connection).get_columns(
                    "projects",
                    schema=schema,
                )
            } == {"id", "source_filename"}
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
