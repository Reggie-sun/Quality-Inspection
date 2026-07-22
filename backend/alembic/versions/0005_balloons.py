"""Add formal balloons and immutable reviewed results.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "balloons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inspection_item_id", sa.String(length=128), nullable=False),
        sa.Column("source_location_id", sa.String(length=256), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("suggested_number", sa.Integer(), nullable=False),
        sa.Column("formal_number", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "anchor_bbox_pdf",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "leader_target_pdf",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "center_pdf",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("placement_status", sa.String(length=32), nullable=False),
        sa.Column(
            "collision_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_balloons_active_item",
        "balloons",
        ["project_id", "inspection_item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_balloons_active_formal_number",
        "balloons",
        ["project_id", "formal_number"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND formal_number IS NOT NULL"
        ),
    )
    op.create_table(
        "reviewed_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("working_copy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("working_version", sa.Integer(), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("balloons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["working_copy_id"],
            ["review_working_copies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "working_copy_id",
            "working_version",
            name="uq_reviewed_results_working_version",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_reviewed_result_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'immutable reviewed result'
                USING ERRCODE = '23514';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_reviewed_result_update_delete
        BEFORE UPDATE OR DELETE ON reviewed_results
        FOR EACH ROW
        EXECUTE FUNCTION reject_reviewed_result_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER prevent_reviewed_result_update_delete ON reviewed_results"
    )
    op.execute("DROP FUNCTION reject_reviewed_result_mutation()")
    op.drop_table("reviewed_results")
    op.drop_index("uq_balloons_active_formal_number", table_name="balloons")
    op.drop_index("uq_balloons_active_item", table_name="balloons")
    op.drop_table("balloons")
