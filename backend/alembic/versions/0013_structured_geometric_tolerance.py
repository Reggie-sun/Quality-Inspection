"""Persist structured geometric tolerance candidates and version result layers.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GDT_PAYLOAD = """
jsonb_build_object(
    'candidate_id', candidate->>'candidate_id',
    'item_type', 'geometric_tolerance',
    'schema_version', 'geometric-tolerance-candidate/1',
    'raw_text', COALESCE(candidate->'payload'->>'raw_text', ''),
    'normalized_text', COALESCE(candidate->'payload'->>'raw_text', ''),
    'tolerance_type', 'unknown',
    'tolerance_symbol', NULL,
    'tolerance_value', NULL,
    'diameter_modifier', false,
    'modifiers', '[]'::jsonb,
    'datum_references', '[]'::jsonb,
    'frames', '[]'::jsonb,
    'standard_context', 'unspecified',
    'coordinates', candidate->'payload'->'coordinates',
    'source_location_ids', COALESCE(candidate->'source_location_ids', '[]'::jsonb),
    'evidence_ref', 'legacy://geometric-tolerance',
    'requires_confirmation', true
)
"""

_GDT_REVIEW_FIELDS = """
jsonb_build_object(
    'item_type', 'geometric_tolerance',
    'schema_version', 'geometric-tolerance-candidate/1',
    'normalized_text', COALESCE(item->>'raw_text', ''),
    'tolerance_type', 'unknown',
    'tolerance_symbol', NULL,
    'tolerance_value', NULL,
    'diameter_modifier', false,
    'modifiers', '[]'::jsonb,
    'datum_references', '[]'::jsonb,
    'frames', '[]'::jsonb,
    'standard_context', 'unspecified',
    'evidence_ref', 'legacy://geometric-tolerance',
    'requires_confirmation', true
)
"""

_COARSE_PAYLOAD = """
jsonb_build_object(
    'raw_text', candidate->'payload'->'raw_text',
    'coordinates', candidate->'payload'->'coordinates',
    'coarse_type', 'geometric_tolerance',
    'requires_confirmation', true
)
"""

_COARSE_REVIEW_FIELDS = """
jsonb_build_object(
    'raw_text', item->'raw_text',
    'coordinates', item->'coordinates',
    'coarse_type', 'geometric_tolerance',
    'requires_confirmation', true
)
"""


def _mutate_immutable_results(statements: Sequence[str]) -> None:
    triggers = {
        "automatic_results": "prevent_automatic_result_update_delete",
        "reviewed_results": "prevent_reviewed_result_update_delete",
    }
    for table, trigger in triggers.items():
        op.execute(
            sa.text(
                f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"
            )
        )
    try:
        for statement in statements:
            op.execute(sa.text(statement))
    finally:
        for table, trigger in triggers.items():
            op.execute(
                sa.text(
                    f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"
                )
            )


def upgrade() -> None:
    _mutate_immutable_results(
        (
            f"""
            UPDATE automatic_results
            SET candidates = (
                SELECT COALESCE(jsonb_agg(
                    CASE
                        WHEN candidate->'payload'->>'coarse_type'
                            = 'geometric_tolerance'
                        THEN jsonb_set(candidate, '{{payload}}', {_GDT_PAYLOAD})
                        ELSE candidate
                    END
                    ORDER BY ordinal
                ), '[]'::jsonb)
                FROM jsonb_array_elements(candidates)
                    WITH ORDINALITY AS elements(candidate, ordinal)
            ),
            schema_version = 'automatic-result/3'
            WHERE schema_version = 'automatic-result/2'
            """,
            f"""
            UPDATE review_working_copies
            SET items = (
                SELECT COALESCE(jsonb_agg(
                    CASE
                        WHEN item->>'coarse_type' = 'geometric_tolerance'
                        THEN (item - 'coarse_type') || {_GDT_REVIEW_FIELDS}
                        ELSE item
                    END
                    ORDER BY ordinal
                ), '[]'::jsonb)
                FROM jsonb_array_elements(items)
                    WITH ORDINALITY AS elements(item, ordinal)
            )
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements(items) AS elements(item)
                WHERE item->>'coarse_type' = 'geometric_tolerance'
            )
            """,
            f"""
            UPDATE reviewed_results
            SET items = (
                SELECT COALESCE(jsonb_agg(
                    CASE
                        WHEN item->>'coarse_type' = 'geometric_tolerance'
                        THEN (item - 'coarse_type') || {_GDT_REVIEW_FIELDS}
                        ELSE item
                    END
                    ORDER BY ordinal
                ), '[]'::jsonb)
                FROM jsonb_array_elements(items)
                    WITH ORDINALITY AS elements(item, ordinal)
            ),
            schema_version = 'reviewed-result/3'
            """,
        )
    )


def downgrade() -> None:
    _mutate_immutable_results(
        (
            f"""
            UPDATE automatic_results
            SET candidates = (
                SELECT COALESCE(jsonb_agg(
                    CASE
                        WHEN candidate->'payload'->>'item_type'
                            = 'geometric_tolerance'
                        THEN jsonb_set(candidate, '{{payload}}', {_COARSE_PAYLOAD})
                        ELSE candidate
                    END
                    ORDER BY ordinal
                ), '[]'::jsonb)
                FROM jsonb_array_elements(candidates)
                    WITH ORDINALITY AS elements(candidate, ordinal)
            ),
            schema_version = 'automatic-result/2'
            WHERE schema_version = 'automatic-result/3'
            """,
            f"""
            UPDATE review_working_copies
            SET items = (
                SELECT COALESCE(jsonb_agg(
                    CASE
                        WHEN item->>'item_type' = 'geometric_tolerance'
                        THEN (
                            item
                            - 'item_type'
                            - 'schema_version'
                            - 'normalized_text'
                            - 'tolerance_type'
                            - 'tolerance_symbol'
                            - 'tolerance_value'
                            - 'diameter_modifier'
                            - 'modifiers'
                            - 'datum_references'
                            - 'frames'
                            - 'standard_context'
                            - 'evidence_ref'
                        ) || {_COARSE_REVIEW_FIELDS}
                        ELSE item
                    END
                    ORDER BY ordinal
                ), '[]'::jsonb)
                FROM jsonb_array_elements(items)
                    WITH ORDINALITY AS elements(item, ordinal)
            )
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements(items) AS elements(item)
                WHERE item->>'item_type' = 'geometric_tolerance'
            )
            """,
            f"""
            UPDATE reviewed_results
            SET items = (
                SELECT COALESCE(jsonb_agg(
                    CASE
                        WHEN item->>'item_type' = 'geometric_tolerance'
                        THEN (
                            item
                            - 'item_type'
                            - 'schema_version'
                            - 'normalized_text'
                            - 'tolerance_type'
                            - 'tolerance_symbol'
                            - 'tolerance_value'
                            - 'diameter_modifier'
                            - 'modifiers'
                            - 'datum_references'
                            - 'frames'
                            - 'standard_context'
                            - 'evidence_ref'
                        ) || {_COARSE_REVIEW_FIELDS}
                        ELSE item
                    END
                    ORDER BY ordinal
                ), '[]'::jsonb)
                FROM jsonb_array_elements(items)
                    WITH ORDINALITY AS elements(item, ordinal)
            ),
            schema_version = 'reviewed-result/2'
            WHERE schema_version = 'reviewed-result/3'
            """,
        )
    )
