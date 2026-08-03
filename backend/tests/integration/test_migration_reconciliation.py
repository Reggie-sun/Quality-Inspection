from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

from app.db import engine


BACKEND_PATH = Path(__file__).parents[2]
MIGRATION_PATHS = (
    BACKEND_PATH / "alembic" / "versions" / "0009_symbol_routing_evidence.py",
    BACKEND_PATH / "alembic" / "versions" / "0010_technical_requirements.py",
    BACKEND_PATH / "alembic" / "versions" / "0011_symbol_result_completeness.py",
)
PROVIDER_FAILURE_MIGRATION_PATH = (
    BACKEND_PATH
    / "alembic"
    / "versions"
    / "0016_symbol_provider_failure_diagnostics.py"
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


def _create_minimal_projects_table(
    connection: sa.Connection,
    *,
    schema: str,
) -> None:
    sa.Table(
        "projects",
        sa.MetaData(),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        schema=schema,
    ).create(connection)


def _insert_legacy_symbol_routing_evidence(
    connection: sa.Connection,
    *,
    project_id: uuid.UUID,
    decision_id: uuid.UUID,
    attempt_id: uuid.UUID,
    outcome_id: uuid.UUID,
) -> None:
    connection.execute(
        sa.text("INSERT INTO projects (id) VALUES (:project_id)"),
        {"project_id": project_id},
    )
    connection.execute(
        sa.text(
            "INSERT INTO symbol_routing_decisions ("
            "id, project_id, visual_observation_id, escalation_group_id, "
            "escalation_group_member_index, local_resolution_ref, "
            "schema_version, router_version, input_sha256, disposition, "
            "local_resolution_reason_codes, escalation_reason_codes, "
            "block_reason_codes, requires_confirmation, decision_sha256"
            ") VALUES ("
            ":id, :project_id, 'visual-1', 'group-1', 0, NULL, "
            "'symbol-routing-decision/1', 'symbol-uncertainty-router/1', "
            ":input_sha, 'escalate', '[]'::jsonb, "
            "'[\"local_parse_incomplete\"]'::jsonb, '[]'::jsonb, true, "
            ":decision_sha"
            ")"
        ),
        {
            "id": decision_id,
            "project_id": project_id,
            "input_sha": "a" * 64,
            "decision_sha": "b" * 64,
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO symbol_escalation_attempt_events ("
            "id, project_id, escalation_group_id, routing_decision_sha256, "
            "attempt_index, event_code, cache_entry_id, provider_request_id, "
            "event_sha256"
            ") VALUES ("
            ":id, :project_id, 'group-1', :decision_sha, 0, 'cache_miss', "
            "NULL, NULL, :event_sha"
            ")"
        ),
        {
            "id": attempt_id,
            "project_id": project_id,
            "decision_sha": "b" * 64,
            "event_sha": "c" * 64,
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO symbol_escalation_outcomes ("
            "id, project_id, escalation_group_id, routing_decision_sha256, "
            "schema_version, outcome_code, observation_outcomes, "
            "attempt_event_sha256s, terminal, outcome_sha256"
            ") VALUES ("
            ":id, :project_id, 'group-1', :decision_sha, "
            "'symbol-escalation-outcome/1', 'unresolved', "
            "'[ {\"visual_observation_id\": \"visual-1\", "
            "\"outcome_code\": \"provider_unavailable\"} ]'::jsonb, "
            "'[\"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\"]'::jsonb, "
            "true, :outcome_sha"
            ")"
        ),
        {
            "id": outcome_id,
            "project_id": project_id,
            "decision_sha": "b" * 64,
            "outcome_sha": "d" * 64,
        },
    )


def test_provider_failure_diagnostic_migration_preserves_legacy_rows() -> None:
    schema = f"migration_provider_failure_{uuid.uuid4().hex}"
    migration_0009 = _load_migration(MIGRATION_PATHS[0])
    migration_0014 = _load_migration(PROVIDER_FAILURE_MIGRATION_PATH)
    project_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    outcome_id = uuid.uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                sa.text(f'SET LOCAL search_path TO "{schema}", public')
            )
            _create_minimal_projects_table(connection, schema=schema)
            operations = Operations(MigrationContext.configure(connection))
            migration_0009.op = operations
            migration_0014.op = operations
            migration_0009.upgrade()
            _insert_legacy_symbol_routing_evidence(
                connection,
                project_id=project_id,
                decision_id=decision_id,
                attempt_id=attempt_id,
                outcome_id=outcome_id,
            )
            trigger_state = connection.scalar(
                sa.text(
                    "SELECT tgenabled FROM pg_trigger "
                    "WHERE tgname = "
                    "'prevent_symbol_escalation_attempt_events_update_delete'"
                )
            )
            assert trigger_state == "O"

            migration_0014.upgrade()

            assert {
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "symbol_escalation_attempt_events"
                )
            } >= {"schema_version", "diagnostic", "diagnostic_sha256"}
            assert connection.execute(
                sa.text(
                    "SELECT schema_version, diagnostic, diagnostic_sha256 "
                    "FROM symbol_escalation_attempt_events WHERE id = :id"
                ),
                {"id": attempt_id},
            ).one() == ("symbol-escalation-attempt/1", None, None)

            migration_0014.downgrade()

            assert not {
                "schema_version",
                "diagnostic",
                "diagnostic_sha256",
            } & {
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "symbol_escalation_attempt_events"
                )
            }
            assert connection.scalar(
                sa.text("SELECT count(*) FROM symbol_routing_decisions")
            ) == 1
            assert connection.scalar(
                sa.text("SELECT count(*) FROM symbol_escalation_outcomes")
            ) == 1
        finally:
            transaction.rollback()


def test_provider_failure_diagnostic_downgrade_refuses_v2_evidence() -> None:
    schema = f"migration_provider_failure_v2_{uuid.uuid4().hex}"
    migration_0009 = _load_migration(MIGRATION_PATHS[0])
    migration_0014 = _load_migration(PROVIDER_FAILURE_MIGRATION_PATH)
    project_id = uuid.uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                sa.text(f'SET LOCAL search_path TO "{schema}", public')
            )
            _create_minimal_projects_table(connection, schema=schema)
            operations = Operations(MigrationContext.configure(connection))
            migration_0009.op = operations
            migration_0014.op = operations
            migration_0009.upgrade()
            connection.execute(
                sa.text("INSERT INTO projects (id) VALUES (:project_id)"),
                {"project_id": project_id},
            )
            migration_0014.upgrade()
            diagnostic = (
                '{"schema_version":"visual-symbol-provider-failure/1",'
                '"failure_category":"rate_limited"}'
            )
            attempt_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO symbol_escalation_attempt_events ("
                    "id, project_id, escalation_group_id, "
                    "routing_decision_sha256, attempt_index, event_code, "
                    "cache_entry_id, provider_request_id, event_sha256, "
                    "schema_version, diagnostic, diagnostic_sha256"
                    ") VALUES ("
                    ":id, :project_id, 'group-1', :decision_sha, 0, "
                    "'provider_rate_limited', NULL, NULL, :event_sha, "
                    "'symbol-escalation-attempt/2', CAST(:diagnostic AS jsonb), "
                    ":diagnostic_sha"
                    ")"
                ),
                {
                    "id": attempt_id,
                    "project_id": project_id,
                    "decision_sha": "a" * 64,
                    "event_sha": "b" * 64,
                    "diagnostic": diagnostic,
                    "diagnostic_sha": "c" * 64,
                },
            )
            before = connection.execute(
                sa.text(
                    "SELECT schema_version, diagnostic::text, "
                    "diagnostic_sha256, event_sha256 "
                    "FROM symbol_escalation_attempt_events WHERE id = :id"
                ),
                {"id": attempt_id},
            ).one()

            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError) as raised:
                migration_0014.downgrade()
            assert raised.value.orig.sqlstate == "23514"
            savepoint.rollback()

            assert {
                "schema_version",
                "diagnostic",
                "diagnostic_sha256",
            }.issubset(
                {
                    column["name"]
                    for column in sa.inspect(connection).get_columns(
                        "symbol_escalation_attempt_events"
                    )
                }
            )
            assert connection.execute(
                sa.text(
                    "SELECT schema_version, diagnostic::text, "
                    "diagnostic_sha256, event_sha256 "
                    "FROM symbol_escalation_attempt_events WHERE id = :id"
                ),
                {"id": attempt_id},
            ).one() == before
        finally:
            transaction.rollback()


def test_integrated_migration_converges_feature_only_0008_schema() -> None:
    schema = f"migration_reconcile_{uuid.uuid4().hex}"
    migration_0009, migration_0010 = (
        _load_migration(path) for path in MIGRATION_PATHS[:2]
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


def test_symbol_result_completeness_downgrade_removes_legacy_defaults() -> None:
    schema = f"migration_legacy_completeness_{uuid.uuid4().hex}"
    migration_0011 = _load_migration(MIGRATION_PATHS[-1])
    result_id = uuid.uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                sa.text(f'SET LOCAL search_path TO "{schema}", public')
            )
            sa.Table(
                "automatic_results",
                sa.MetaData(),
                sa.Column(
                    "id",
                    postgresql.UUID(as_uuid=True),
                    primary_key=True,
                ),
                schema=schema,
            ).create(connection)
            migration_0011.op = Operations(
                MigrationContext.configure(connection)
            )
            migration_0011.upgrade()
            connection.execute(
                sa.text("INSERT INTO automatic_results (id) VALUES (:id)"),
                {"id": result_id},
            )
            assert connection.execute(
                sa.text(
                    "SELECT completeness, recognition_mode, router_version, "
                    "recognition_summary, recognition_evidence_ref "
                    "FROM automatic_results WHERE id = :id"
                ),
                {"id": result_id},
            ).one() == (
                "complete",
                "legacy_high_recall",
                "legacy",
                {},
                None,
            )

            migration_0011.downgrade()

            assert {
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "automatic_results"
                )
            } == {"id"}
        finally:
            transaction.rollback()


def test_symbol_result_completeness_downgrade_refuses_provenance_loss() -> None:
    schema = f"migration_completeness_{uuid.uuid4().hex}"
    migration_0011 = _load_migration(MIGRATION_PATHS[-1])
    result_id = uuid.uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                sa.text(f'SET LOCAL search_path TO "{schema}", public')
            )
            sa.Table(
                "automatic_results",
                sa.MetaData(),
                sa.Column(
                    "id",
                    postgresql.UUID(as_uuid=True),
                    primary_key=True,
                ),
                schema=schema,
            ).create(connection)

            operations = Operations(MigrationContext.configure(connection))
            migration_0011.op = operations
            migration_0011.upgrade()
            connection.execute(
                sa.text(
                    "INSERT INTO automatic_results ("
                    "id, completeness, recognition_mode, router_version, "
                    "recognition_summary, recognition_evidence_ref"
                    ") VALUES ("
                    ":id, 'partial_review_required', "
                    "'production_uncertainty', "
                    "'symbol-uncertainty-router/1', "
                    "CAST(:summary AS jsonb), :evidence_ref"
                    ")"
                ),
                {
                    "id": result_id,
                    "summary": '{"schema_version":"symbol-recognition-summary/1",'
                    '"unresolved_roi_count":1}',
                    "evidence_ref": "symbol-routing-evidence://project",
                },
            )

            with pytest.raises(RuntimeError, match="downgrade refused"):
                migration_0011.downgrade()

            inspector = sa.inspect(connection)
            assert {
                "completeness",
                "recognition_mode",
                "router_version",
                "recognition_summary",
                "recognition_evidence_ref",
            }.issubset(
                {
                    column["name"]
                    for column in inspector.get_columns("automatic_results")
                }
            )
            assert connection.execute(
                sa.text(
                    "SELECT completeness, recognition_mode, router_version, "
                    "recognition_summary, recognition_evidence_ref "
                    "FROM automatic_results WHERE id = :id"
                ),
                {"id": result_id},
            ).one() == (
                "partial_review_required",
                "production_uncertainty",
                "symbol-uncertainty-router/1",
                {"schema_version": "symbol-recognition-summary/1", "unresolved_roi_count": 1},
                "symbol-routing-evidence://project",
            )
        finally:
            transaction.rollback()
