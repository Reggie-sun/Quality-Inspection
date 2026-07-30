"""Add technical requirement persistence.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0008"
down_revision: str | None = "0007"
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
    op.add_column("automatic_results", _empty_requirements_column())
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
