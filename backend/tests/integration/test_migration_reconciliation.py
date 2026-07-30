from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql

from app.db import engine


BACKEND_PATH = Path(__file__).parents[2]
MIGRATION_PATHS = (
    BACKEND_PATH / "alembic" / "versions" / "0009_symbol_routing_evidence.py",
    BACKEND_PATH / "alembic" / "versions" / "0010_technical_requirements.py",
)


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"migration_{path.stem}",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load migration {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integrated_migration_converges_feature_only_0008_schema() -> None:
    schema = f"migration_reconcile_{uuid.uuid4().hex}"
    migration_0009, migration_0010 = (
        _load_migration(path) for path in MIGRATION_PATHS
    )
    script = ScriptDirectory.from_config(
        Config(str(BACKEND_PATH / "alembic.ini"))
    )
    assert [
        (revision.revision, revision.down_revision)
        for revision in script.iterate_revisions("0010", "0008")
    ] == [("0010", "0009"), ("0009", "0008")]
    project_id = uuid.uuid4()
    automatic_result_id = uuid.uuid4()
    working_copy_id = uuid.uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                sa.text(f'SET LOCAL search_path TO "{schema}", public')
            )
            metadata = sa.MetaData()
            projects = sa.Table(
                "projects",
                metadata,
                sa.Column(
                    "id",
                    postgresql.UUID(as_uuid=True),
                    primary_key=True,
                ),
                sa.Column("state", sa.String(32), nullable=False),
                sa.Column(
                    "version",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                ),
                schema=schema,
            )
            automatic_results = sa.Table(
                "automatic_results",
                metadata,
                sa.Column(
                    "id",
                    postgresql.UUID(as_uuid=True),
                    primary_key=True,
                ),
                sa.Column(
                    "technical_requirements",
                    postgresql.JSONB(),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
                schema=schema,
            )
            review_working_copies = sa.Table(
                "review_working_copies",
                metadata,
                sa.Column(
                    "id",
                    postgresql.UUID(as_uuid=True),
                    primary_key=True,
                ),
                sa.Column(
                    "technical_requirements",
                    postgresql.JSONB(),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
                schema=schema,
            )
            metadata.create_all(connection)
            connection.execute(
                projects.insert().values(
                    id=project_id,
                    state="processing_failed",
                    version=7,
                )
            )
            connection.execute(
                automatic_results.insert().values(
                    id=automatic_result_id,
                    technical_requirements=[{"requirement_id": "automatic"}],
                )
            )
            connection.execute(
                review_working_copies.insert().values(
                    id=working_copy_id,
                    technical_requirements=[{"requirement_id": "working"}],
                )
            )

            context = MigrationContext.configure(connection)
            operations = Operations(context)
            migration_0009.op = operations
            migration_0010.op = operations
            migration_0009.upgrade()
            migration_0010.upgrade()
            migration_0010.upgrade()

            inspector = sa.inspect(connection)
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
            }
            assert project_columns["recognition_mode"]["nullable"] is False
            assert (
                project_columns["recognition_router_version"]["nullable"] is False
            )
            assert "legacy_high_recall" in str(
                project_columns["recognition_mode"]["default"]
            )
            assert "legacy" in str(
                project_columns["recognition_router_version"]["default"]
            )

            constraints = {
                constraint["name"]: constraint["sqltext"]
                for constraint in inspector.get_check_constraints("projects")
            }
            assert set(constraints) == {"ck_projects_recognition_mode"}
            mode_constraint = constraints["ck_projects_recognition_mode"]
            assert "legacy_high_recall" in mode_constraint
            assert "shadow_uncertainty" in mode_constraint
            assert "production_uncertainty" in mode_constraint
            assert "verification_high_recall" not in mode_constraint
            assert connection.execute(
                sa.text(
                    "SELECT id, state, version, recognition_mode, "
                    "recognition_router_version "
                    "FROM projects WHERE id = :project_id"
                ),
                {"project_id": project_id},
            ).one() == (
                project_id,
                "processing_failed",
                7,
                "legacy_high_recall",
                "legacy",
            )

            assert {
                column["name"]
                for column in inspector.get_columns("automatic_results")
            } == {"id", "technical_requirements"}
            assert {
                column["name"]
                for column in inspector.get_columns("review_working_copies")
            } == {"id", "technical_requirements"}
            assert {
                "symbol_routing_decisions",
                "symbol_escalation_attempt_events",
                "symbol_escalation_outcomes",
                "visual_symbol_cache_entries",
            }.issubset(set(inspector.get_table_names()))
            assert connection.scalar(
                sa.select(automatic_results.c.technical_requirements).where(
                    automatic_results.c.id == automatic_result_id
                )
            ) == [{"requirement_id": "automatic"}]
            assert connection.scalar(
                sa.select(review_working_copies.c.technical_requirements).where(
                    review_working_copies.c.id == working_copy_id
                )
            ) == [{"requirement_id": "working"}]
        finally:
            transaction.rollback()
