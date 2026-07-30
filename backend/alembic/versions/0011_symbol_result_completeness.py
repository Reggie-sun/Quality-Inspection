"""Add immutable automatic-result recognition completeness.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automatic_results",
        sa.Column(
            "completeness",
            sa.String(length=32),
            server_default="complete",
            nullable=False,
        ),
    )
    op.add_column(
        "automatic_results",
        sa.Column(
            "recognition_mode",
            sa.String(length=40),
            server_default="legacy_high_recall",
            nullable=False,
        ),
    )
    op.add_column(
        "automatic_results",
        sa.Column(
            "router_version",
            sa.String(length=64),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "automatic_results",
        sa.Column(
            "recognition_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "automatic_results",
        sa.Column("recognition_evidence_ref", sa.String(length=512), nullable=True),
    )
    op.create_check_constraint(
        "ck_automatic_results_completeness",
        "automatic_results",
        "completeness IN ('complete', 'partial_review_required')",
    )


def downgrade() -> None:
    has_recognition_provenance = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM automatic_results WHERE "
            "completeness IS DISTINCT FROM 'complete' OR "
            "recognition_mode IS DISTINCT FROM 'legacy_high_recall' OR "
            "router_version IS DISTINCT FROM 'legacy' OR "
            "recognition_summary IS DISTINCT FROM '{}'::jsonb OR "
            "recognition_evidence_ref IS NOT NULL"
            ")"
        )
    )
    if has_recognition_provenance:
        raise RuntimeError(
            "automatic result recognition provenance exists; downgrade refused"
        )
    op.drop_constraint(
        "ck_automatic_results_completeness",
        "automatic_results",
        type_="check",
    )
    op.drop_column("automatic_results", "recognition_evidence_ref")
    op.drop_column("automatic_results", "recognition_summary")
    op.drop_column("automatic_results", "router_version")
    op.drop_column("automatic_results", "recognition_mode")
    op.drop_column("automatic_results", "completeness")
