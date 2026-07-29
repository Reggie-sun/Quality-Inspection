"""Freeze symbol recognition mode and router identity per project.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "recognition_mode",
            sa.String(length=40),
            server_default="legacy_high_recall",
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "recognition_router_version",
            sa.String(length=64),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_projects_recognition_mode",
        "projects",
        "recognition_mode IN "
        "('legacy_high_recall','shadow_uncertainty',"
        "'production_uncertainty')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_projects_recognition_mode",
        "projects",
        type_="check",
    )
    op.drop_column("projects", "recognition_router_version")
    op.drop_column("projects", "recognition_mode")
