"""Add the Day 4 review working copy and editor lock persistence.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_working_copies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("numbering_stale", sa.Boolean(), nullable=False),
        sa.Column("items_frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_frozen_by", sa.String(length=128), nullable=True),
        sa.Column("items_frozen_version", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["raw_result_id"], ["automatic_results.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            name="uq_review_working_copies_project_id",
        ),
        sa.UniqueConstraint(
            "raw_result_id",
            name="uq_review_working_copies_raw_result_id",
        ),
    )
    op.create_table(
        "review_locks",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("review_locks")
    op.drop_table("review_working_copies")
