"""Freeze coverage-checked automatic candidate results.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automatic_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("logical_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_ref", sa.String(length=512), nullable=False),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "provider_call_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["logical_job_id"], ["logical_jobs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_file_id"], ["stored_files.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "logical_job_id",
            name="uq_automatic_results_logical_job_id",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_automatic_result_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'automatic_results are immutable'
                USING ERRCODE = '23514';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_automatic_result_update_delete
        BEFORE UPDATE OR DELETE ON automatic_results
        FOR EACH ROW
        EXECUTE FUNCTION reject_automatic_result_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER prevent_automatic_result_update_delete "
        "ON automatic_results"
    )
    op.execute("DROP FUNCTION reject_automatic_result_mutation()")
    op.drop_table("automatic_results")
