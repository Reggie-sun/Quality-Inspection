"""Add immutable progressive recognition previews.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_logical_jobs_processing_stage", "logical_jobs", type_="check")
    op.create_check_constraint(
        "ck_logical_jobs_processing_stage",
        "logical_jobs",
        "processing_stage IN ('queued', 'parsing', 'recognizing', 'local_ready', 'vlm_enriching', 'preparing_review')",
    )
    op.create_table(
        "recognition_preview_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stored_files.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recognition_preview_revisions.id")),
        sa.Column("semantic_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("semantic_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("project_id", "revision", name="uq_recognition_preview_revision"),
    )
    op.create_table(
        "recognition_preview_heads",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recognition_preview_revisions.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("terminal_result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automatic_results.id")),
    )
    op.execute("""
        CREATE FUNCTION forbid_recognition_preview_revision_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'recognition preview revisions are immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER prevent_recognition_preview_revision_update_delete
        BEFORE UPDATE OR DELETE ON recognition_preview_revisions
        FOR EACH ROW EXECUTE FUNCTION forbid_recognition_preview_revision_mutation();
    """)


def downgrade() -> None:
    op.drop_table("recognition_preview_heads")
    op.drop_table("recognition_preview_revisions")
    op.execute("DROP FUNCTION forbid_recognition_preview_revision_mutation()")
    op.drop_constraint("ck_logical_jobs_processing_stage", "logical_jobs", type_="check")
    op.create_check_constraint(
        "ck_logical_jobs_processing_stage",
        "logical_jobs",
        "processing_stage IN ('queued', 'parsing', 'recognizing', 'preparing_review')",
    )
