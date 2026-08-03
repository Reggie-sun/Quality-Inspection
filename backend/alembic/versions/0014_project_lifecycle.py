"""Add project lifecycle status and reprocessing lineage.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LIFECYCLE_VALUES = (
    "unlisted",
    "active",
    "reprocessing",
    "reprocess_failed",
    "superseded",
    "deleted",
)


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("lifecycle_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "predecessor_project_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "projects",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE projects SET lifecycle_status = CASE "
        "WHEN source_filename IS NULL THEN 'unlisted' ELSE 'active' END"
    )
    op.alter_column(
        "projects",
        "lifecycle_status",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'active'"),
    )
    op.create_foreign_key(
        "fk_projects_predecessor_project_id_projects",
        "projects",
        "projects",
        ["predecessor_project_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_projects_lifecycle_status",
        "projects",
        "lifecycle_status IN ("
        + ", ".join(f"'{value}'" for value in _LIFECYCLE_VALUES)
        + ")",
    )
    op.create_check_constraint(
        "ck_projects_deleted_timestamp",
        "projects",
        "(lifecycle_status = 'deleted' AND deleted_at IS NOT NULL) OR "
        "(lifecycle_status <> 'deleted' AND deleted_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_projects_predecessor_not_self",
        "projects",
        "predecessor_project_id IS NULL OR predecessor_project_id <> id",
    )
    op.create_index(
        "uq_projects_reprocessing_predecessor",
        "projects",
        ["predecessor_project_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle_status = 'reprocessing'"),
    )


def downgrade() -> None:
    lifecycle_evidence_exists = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM projects "
            "WHERE lifecycle_status NOT IN ('active', 'unlisted') "
            "OR predecessor_project_id IS NOT NULL "
            "OR deleted_at IS NOT NULL"
            ")"
        )
    )
    if lifecycle_evidence_exists:
        raise RuntimeError("project lifecycle evidence exists; downgrade refused")

    op.drop_index("uq_projects_reprocessing_predecessor", table_name="projects")
    op.drop_constraint(
        "ck_projects_predecessor_not_self",
        "projects",
        type_="check",
    )
    op.drop_constraint(
        "ck_projects_deleted_timestamp",
        "projects",
        type_="check",
    )
    op.drop_constraint(
        "ck_projects_lifecycle_status",
        "projects",
        type_="check",
    )
    op.drop_constraint(
        "fk_projects_predecessor_project_id_projects",
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "predecessor_project_id")
    op.drop_column("projects", "lifecycle_status")
