"""Add atomic formal export publication.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_working_copies",
        sa.Column(
            "sip_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column(
        "review_working_copies",
        "sip_metadata",
        server_default=None,
    )
    op.add_column(
        "reviewed_results",
        sa.Column(
            "sip_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column(
        "reviewed_results",
        "sip_metadata",
        server_default=None,
    )
    op.execute(
        """
        UPDATE review_working_copies AS working
        SET items_frozen_at = NULL,
            items_frozen_by = NULL,
            items_frozen_version = NULL
        WHERE working.items_frozen_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM reviewed_results AS reviewed
              WHERE reviewed.working_copy_id = working.id
          )
        """
    )
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "reviewed_result_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=False),
        sa.Column("renderer_version", sa.String(length=64), nullable=False),
        sa.Column("error_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_export_jobs_status",
        ),
        sa.ForeignKeyConstraint(["error_id"], ["error_records.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["reviewed_result_id"],
            ["reviewed_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_export_jobs_success_identity",
        "export_jobs",
        [
            "reviewed_result_id",
            "template_version",
            "mapping_version",
            "renderer_version",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'success'"),
    )
    op.create_table(
        "export_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("staging_ref", sa.String(length=512), nullable=False),
        sa.Column("published_ref", sa.String(length=512), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "reviewed_result_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('ballooned_pdf', 'sip_excel', 'manifest')",
            name="ck_export_artifacts_kind",
        ),
        sa.ForeignKeyConstraint(
            ["export_id"],
            ["export_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_result_id"],
            ["reviewed_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "export_id",
            "kind",
            name="uq_export_artifacts_export_kind",
        ),
    )


def downgrade() -> None:
    op.drop_table("export_artifacts")
    op.drop_index("uq_export_jobs_success_identity", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.drop_column("reviewed_results", "sip_metadata")
    op.drop_column("review_working_copies", "sip_metadata")
