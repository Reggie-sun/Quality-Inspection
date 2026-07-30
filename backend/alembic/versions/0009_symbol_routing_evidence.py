"""Persist immutable symbol routing evidence and project-local cache.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


IMMUTABLE_TABLES = (
    "symbol_routing_decisions",
    "symbol_escalation_attempt_events",
    "symbol_escalation_outcomes",
    "visual_symbol_cache_entries",
)


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def _jsonb() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def _timestamps() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "symbol_routing_decisions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("visual_observation_id", sa.String(256), nullable=False),
        sa.Column("escalation_group_id", sa.String(64), nullable=True),
        sa.Column(
            "escalation_group_member_index",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("local_resolution_ref", sa.String(512), nullable=True),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("router_version", sa.String(64), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("local_resolution_reason_codes", _jsonb(), nullable=False),
        sa.Column("escalation_reason_codes", _jsonb(), nullable=False),
        sa.Column("block_reason_codes", _jsonb(), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("decision_sha256", sa.String(64), nullable=False),
        _timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "visual_observation_id",
            name="uq_symbol_routing_decision_observation",
        ),
    )
    op.create_table(
        "visual_symbol_cache_entries",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("cache_schema_version", sa.String(64), nullable=False),
        sa.Column("identity_sha256", sa.String(64), nullable=False),
        sa.Column("identity", _jsonb(), nullable=False),
        sa.Column("response", _jsonb(), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("producer_request_id", sa.String(256), nullable=False),
        sa.Column("producer_call_record_ref", sa.String(512), nullable=False),
        sa.Column("producer_provenance", _jsonb(), nullable=False),
        sa.Column("provenance_sha256", sa.String(64), nullable=False),
        _timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "cache_key",
            name="uq_visual_symbol_cache_project_key",
        ),
    )
    op.create_table(
        "symbol_escalation_attempt_events",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("escalation_group_id", sa.String(64), nullable=False),
        sa.Column("routing_decision_sha256", sa.String(64), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("event_code", sa.String(48), nullable=False),
        sa.Column("cache_entry_id", _uuid(), nullable=True),
        sa.Column("provider_request_id", sa.String(256), nullable=True),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        _timestamps(),
        sa.ForeignKeyConstraint(
            ["cache_entry_id"],
            ["visual_symbol_cache_entries.id"],
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "escalation_group_id",
            "attempt_index",
            "event_code",
            name="uq_symbol_escalation_attempt_event",
        ),
        sa.UniqueConstraint(
            "project_id",
            "event_sha256",
            name="uq_symbol_escalation_attempt_hash",
        ),
    )
    op.create_table(
        "symbol_escalation_outcomes",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("escalation_group_id", sa.String(64), nullable=False),
        sa.Column("routing_decision_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("outcome_code", sa.String(32), nullable=False),
        sa.Column("observation_outcomes", _jsonb(), nullable=False),
        sa.Column("attempt_event_sha256s", _jsonb(), nullable=False),
        sa.Column("terminal", sa.Boolean(), nullable=False),
        sa.Column("outcome_sha256", sa.String(64), nullable=False),
        _timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "escalation_group_id",
            name="uq_symbol_escalation_outcome_group",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_symbol_routing_evidence_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END;
        $$
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER prevent_{table}_update_delete
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION reject_symbol_routing_evidence_mutation()
            """
        )


def downgrade() -> None:
    for table in reversed(IMMUTABLE_TABLES):
        op.execute(
            f"DROP TRIGGER prevent_{table}_update_delete ON {table}"
        )
    op.execute("DROP FUNCTION reject_symbol_routing_evidence_mutation()")
    op.drop_table("symbol_escalation_outcomes")
    op.drop_table("symbol_escalation_attempt_events")
    op.drop_table("visual_symbol_cache_entries")
    op.drop_table("symbol_routing_decisions")
