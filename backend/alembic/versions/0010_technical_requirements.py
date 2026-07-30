"""Add technical requirement persistence.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _empty_requirements_column() -> sa.Column:
    return sa.Column(
        "technical_requirements",
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    project_columns = {
        column["name"] for column in inspector.get_columns("projects")
    }
    if "recognition_mode" not in project_columns:
        op.add_column(
            "projects",
            sa.Column(
                "recognition_mode",
                sa.String(length=40),
                server_default="legacy_high_recall",
                nullable=False,
            ),
        )
    if "recognition_router_version" not in project_columns:
        op.add_column(
            "projects",
            sa.Column(
                "recognition_router_version",
                sa.String(length=64),
                server_default="legacy",
                nullable=False,
            ),
        )

    project_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("projects")
    }
    if "ck_projects_recognition_mode" not in project_constraints:
        op.create_check_constraint(
            "ck_projects_recognition_mode",
            "projects",
            "recognition_mode IN "
            "('legacy_high_recall','shadow_uncertainty',"
            "'production_uncertainty')",
        )

    automatic_result_columns = {
        column["name"]
        for column in inspector.get_columns("automatic_results")
    }
    if "technical_requirements" not in automatic_result_columns:
        op.add_column("automatic_results", _empty_requirements_column())

    working_copy_columns = {
        column["name"]
        for column in inspector.get_columns("review_working_copies")
    }
    if "technical_requirements" not in working_copy_columns:
        op.add_column("review_working_copies", _empty_requirements_column())


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.scalar(
        sa.text(
            "SELECT "
            "(SELECT count(*) FROM automatic_results "
            " WHERE technical_requirements <> '[]'::jsonb) + "
            "(SELECT count(*) FROM review_working_copies "
            " WHERE technical_requirements <> '[]'::jsonb)"
        )
    )
    if int(populated or 0) != 0:
        raise RuntimeError(
            "technical requirement evidence exists; schema downgrade refused"
        )
    op.drop_column("review_working_copies", "technical_requirements")
    op.drop_column("automatic_results", "technical_requirements")
