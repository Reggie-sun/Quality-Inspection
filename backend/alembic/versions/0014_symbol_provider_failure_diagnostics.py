"""Version symbol Provider failure diagnostics without mutating evidence.

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


def upgrade() -> None:
    op.add_column(
        "symbol_escalation_attempt_events",
        sa.Column(
            "schema_version",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'symbol-escalation-attempt/1'"),
        ),
    )
    op.add_column(
        "symbol_escalation_attempt_events",
        sa.Column(
            "diagnostic",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "symbol_escalation_attempt_events",
        sa.Column("diagnostic_sha256", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_symbol_attempt_diagnostic_version",
        "symbol_escalation_attempt_events",
        "(schema_version = 'symbol-escalation-attempt/1' "
        "AND diagnostic IS NULL AND diagnostic_sha256 IS NULL) OR "
        "(schema_version = 'symbol-escalation-attempt/2' "
        "AND diagnostic IS NOT NULL "
        "AND diagnostic_sha256 ~ '^[0-9a-f]{64}$')",
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM symbol_escalation_attempt_events
                    WHERE schema_version = 'symbol-escalation-attempt/2'
                       OR diagnostic IS NOT NULL
                       OR diagnostic_sha256 IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'symbol escalation v2 evidence blocks downgrade'
                        USING ERRCODE = '23514';
                END IF;
            END;
            $$
            """
        )
    )
    op.drop_constraint(
        "ck_symbol_attempt_diagnostic_version",
        "symbol_escalation_attempt_events",
        type_="check",
    )
    op.drop_column(
        "symbol_escalation_attempt_events",
        "diagnostic_sha256",
    )
    op.drop_column("symbol_escalation_attempt_events", "diagnostic")
    op.drop_column("symbol_escalation_attempt_events", "schema_version")
