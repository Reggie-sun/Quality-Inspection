from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import engine


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/0017_confirmed_global_requirement_acceptance.py"
)


def _migration_0017() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_migration_0017_confirmed_global_requirement_acceptance",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_review_working_copy_table(schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
        connection.execute(text(f"SET LOCAL search_path TO {schema}"))
        connection.execute(
            text(
                "CREATE TABLE review_working_copies ("
                "id uuid PRIMARY KEY, "
                "version integer NOT NULL, "
                "items jsonb NOT NULL, "
                "technical_requirements jsonb NOT NULL, "
                "updated_at timestamptz NOT NULL DEFAULT now()"
                ")"
            )
        )


def _insert_legacy_working_copy(schema: str) -> uuid.UUID:
    working_copy_id = uuid.uuid4()
    confidence_decision = {
        "band": "medium",
        "review_disposition": "review_required",
        "policy_version": "candidate-confidence/1",
        "evidence_codes": [
            "typed_schema_complete",
            "source_truth_preserved",
            "single_source_owner",
            "local_association_complete",
            "coverage_clear",
            "no_conflict",
            "semantic_confirmation_clear",
            "balloon_requirement_known",
            "source_signal_valid",
            "source_signal_medium",
        ],
    }
    items = [
        {
            "item_id": "confirmed-global",
            "scope": "global_requirement",
            "balloon_required": False,
            "status": "pending",
            "requires_confirmation": True,
            "acceptance_source": None,
            "active": True,
        },
        {
            "item_id": "confirmed-global-with-decision",
            "scope": "global_requirement",
            "balloon_required": False,
            "status": "pending",
            "requires_confirmation": True,
            "acceptance_source": None,
            "confidence_decision": confidence_decision,
            "active": True,
        },
        {
            "item_id": "suggested-global",
            "scope": "global_requirement",
            "balloon_required": False,
            "status": "pending",
            "requires_confirmation": True,
            "acceptance_source": None,
            "active": True,
        },
        {
            "item_id": "manual-global",
            "scope": "global_requirement",
            "balloon_required": False,
            "status": "pending",
            "requires_confirmation": True,
            "acceptance_source": None,
            "active": True,
        },
        {
            "item_id": "inactive-confirmed-global",
            "scope": "global_requirement",
            "balloon_required": False,
            "status": "superseded",
            "requires_confirmation": True,
            "acceptance_source": None,
            "active": False,
        },
    ]
    requirements = [
        {
            "requirement_id": "confirmed",
            "match_outcome": "global_scope",
            "generated_candidate_id": "confirmed-global",
            "review_required": False,
            "review_status": "confirmed",
        },
        {
            "requirement_id": "suggested",
            "match_outcome": "global_scope",
            "generated_candidate_id": "suggested-global",
            "review_required": True,
            "review_status": "suggested",
        },
        {
            "requirement_id": "confirmed-with-decision",
            "match_outcome": "global_scope",
            "generated_candidate_id": "confirmed-global-with-decision",
            "review_required": False,
            "review_status": "confirmed",
        },
        {
            "requirement_id": "inactive-confirmed",
            "match_outcome": "global_scope",
            "generated_candidate_id": "inactive-confirmed-global",
            "review_required": False,
            "review_status": "confirmed",
        },
    ]
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL search_path TO {schema}"))
        connection.execute(
            text(
                "INSERT INTO review_working_copies "
                "(id, version, items, technical_requirements) "
                "VALUES (:id, 7, CAST(:items AS jsonb), "
                "CAST(:technical_requirements AS jsonb))"
            ),
            {
                "id": working_copy_id,
                "items": json.dumps(items),
                "technical_requirements": json.dumps(requirements),
            },
        )
    return working_copy_id


def test_migration_is_attached_to_current_head() -> None:
    assert MIGRATION_PATH.exists()
    migration = _migration_0017()

    assert migration.revision == "0017"
    assert migration.down_revision == "0016"


def test_migration_accepts_only_confirmed_active_generated_global_items() -> None:
    schema = f"confirmed_global_{uuid.uuid4().hex}"
    _create_review_working_copy_table(schema)
    working_copy_id = _insert_legacy_working_copy(schema)
    migration = _migration_0017()

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            migration.upgrade()

            version, items = connection.execute(
                text(
                    "SELECT version, items FROM review_working_copies "
                    "WHERE id = :id"
                ),
                {"id": working_copy_id},
            ).one()

        by_id = {item["item_id"]: item for item in items}
        assert version == 8
        assert by_id["confirmed-global"]["status"] == "kept"
        assert by_id["confirmed-global"]["requires_confirmation"] is False
        assert by_id["confirmed-global"]["acceptance_source"] == "manual"
        assert by_id["confirmed-global"]["confirmation_accepted"] is True
        accepted_with_decision = by_id["confirmed-global-with-decision"]
        assert accepted_with_decision["status"] == "kept"
        assert accepted_with_decision["requires_confirmation"] is False
        assert accepted_with_decision["acceptance_source"] == "manual_override"
        assert accepted_with_decision["confidence_decision"] == {
            "band": "medium",
            "review_disposition": "review_required",
            "policy_version": "candidate-confidence/1",
            "evidence_codes": [
                "typed_schema_complete",
                "source_truth_preserved",
                "single_source_owner",
                "local_association_complete",
                "coverage_clear",
                "no_conflict",
                "semantic_confirmation_clear",
                "balloon_requirement_known",
                "source_signal_valid",
                "source_signal_medium",
            ],
        }
        assert by_id["suggested-global"]["status"] == "pending"
        assert by_id["suggested-global"]["requires_confirmation"] is True
        assert by_id["manual-global"]["status"] == "pending"
        assert by_id["manual-global"]["requires_confirmation"] is True
        assert by_id["inactive-confirmed-global"]["status"] == "superseded"
        assert by_id["inactive-confirmed-global"]["active"] is False
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


def test_migration_downgrade_refuses_confirmed_global_acceptance_truth() -> None:
    schema = f"confirmed_global_downgrade_{uuid.uuid4().hex}"
    _create_review_working_copy_table(schema)
    _insert_legacy_working_copy(schema)
    migration = _migration_0017()

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

            with pytest.raises(
                DBAPIError,
                match="confirmed global requirement acceptance blocks downgrade",
            ):
                migration.downgrade()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
