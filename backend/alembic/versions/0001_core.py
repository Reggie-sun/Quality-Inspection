"""Create the D1 core persistence tables.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "logical_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("logical_task_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "logical_task_key"),
    )
    op.create_table(
        "operation_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", sa.String(length=128), nullable=False),
        sa.Column("command", sa.String(length=64), nullable=False),
        sa.Column("target_ids", sa.JSON(), nullable=False),
        sa.Column("before_version", sa.Integer(), nullable=False),
        sa.Column("after_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operator_id ~ '[^[:space:]]'",
            name="ck_operation_records_operator_id_nonblank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_operation_records_project_id"),
        "operation_records",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "stored_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_ref", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_ref"),
    )


def downgrade() -> None:
    op.drop_table("stored_files")
    op.drop_table("projects")
    op.drop_index(
        op.f("ix_operation_records_project_id"),
        table_name="operation_records",
    )
    op.drop_table("operation_records")
    op.drop_table("logical_jobs")
