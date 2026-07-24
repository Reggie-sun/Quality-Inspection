"""Add logical processing stage projection.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "logical_jobs",
        sa.Column(
            "processing_stage",
            sa.String(length=32),
            server_default="queued",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_logical_jobs_processing_stage",
        "logical_jobs",
        "processing_stage IN "
        "('queued','parsing','recognizing','preparing_review')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_logical_jobs_processing_stage",
        "logical_jobs",
        type_="check",
    )
    op.drop_column("logical_jobs", "processing_stage")
