"""Accept generated global items with their confirmed requirements.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence
import json
from typing import Any

import sqlalchemy as sa
from alembic import op


revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONFIDENCE_EVIDENCE_CODE_ORDER = (
    "typed_schema_complete",
    "typed_schema_incomplete",
    "feature_kind_unknown",
    "coarse_fallback",
    "local_projection_failed",
    "source_truth_preserved",
    "normalized_value_invalid",
    "single_source_owner",
    "source_location_missing",
    "source_owner_conflict",
    "local_association_complete",
    "local_association_missing",
    "coverage_clear",
    "coverage_unchecked",
    "coverage_blocking",
    "ambiguous_source",
    "no_conflict",
    "possible_duplicate",
    "cross_view_conflict",
    "projection_conflict",
    "provider_schema_rejected",
    "semantic_confirmation_clear",
    "semantic_confirmation_required",
    "balloon_requirement_known",
    "balloon_requirement_unknown",
    "source_signal_valid",
    "source_signal_missing",
    "source_signal_invalid",
    "source_signal_high",
    "source_signal_medium",
    "source_signal_low",
)
_CONFIDENCE_DECISION_FIELDS = {
    "band",
    "review_disposition",
    "policy_version",
    "evidence_codes",
}
_DISPOSITION_BY_BAND = {
    "high": "auto_accepted",
    "medium": "review_required",
    "low": "review_required",
}


def _has_valid_confidence_decision(item: dict[str, Any]) -> bool:
    decision = item.get("confidence_decision")
    if not isinstance(decision, dict) or set(decision) != _CONFIDENCE_DECISION_FIELDS:
        return False
    band = decision.get("band")
    if band not in _DISPOSITION_BY_BAND:
        return False
    if decision.get("review_disposition") != _DISPOSITION_BY_BAND[band]:
        return False
    if decision.get("policy_version") != "candidate-confidence/1":
        return False
    evidence_codes = decision.get("evidence_codes")
    if (
        not isinstance(evidence_codes, list)
        or not evidence_codes
        or any(not isinstance(code, str) for code in evidence_codes)
        or len(set(evidence_codes)) != len(evidence_codes)
    ):
        return False
    indexes = {code: index for index, code in enumerate(_CONFIDENCE_EVIDENCE_CODE_ORDER)}
    if any(code not in indexes for code in evidence_codes):
        return False
    return [indexes[code] for code in evidence_codes] == sorted(
        indexes[code] for code in evidence_codes
    )


def _is_legacy_pending_global(
    item: dict[str, Any],
    requirements: list[dict[str, Any]],
) -> bool:
    return (
        item.get("scope") == "global_requirement"
        and item.get("balloon_required") is False
        and item.get("active", True) is True
        and (
            item.get("status") == "pending"
            or item.get("requires_confirmation") is True
        )
        and any(
            requirement.get("match_outcome") == "global_scope"
            and requirement.get("review_status") == "confirmed"
            and requirement.get("review_required") is False
            and requirement.get("generated_candidate_id") == item.get("item_id")
            for requirement in requirements
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, items, technical_requirements "
            "FROM review_working_copies FOR UPDATE"
        )
    ).mappings()
    for row in rows:
        items = row["items"]
        requirements = row["technical_requirements"]
        if not isinstance(items, list) or not isinstance(requirements, list):
            continue
        changed = False
        for item in items:
            if not isinstance(item, dict) or not _is_legacy_pending_global(
                item,
                requirements,
            ):
                continue
            valid_decision = _has_valid_confidence_decision(item)
            if not valid_decision:
                item.pop("confidence_decision", None)
            item.update(
                {
                    "status": "kept",
                    "requires_confirmation": False,
                    "acceptance_source": (
                        "manual_override" if valid_decision else "manual"
                    ),
                    "confirmation_accepted": True,
                }
            )
            changed = True
        if changed:
            connection.execute(
                sa.text(
                    "UPDATE review_working_copies "
                    "SET items = CAST(:items AS jsonb), "
                    "version = version + 1, updated_at = now() "
                    "WHERE id = :id"
                ),
                {"id": row["id"], "items": json.dumps(items)},
            )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM review_working_copies AS working
                    CROSS JOIN LATERAL jsonb_array_elements(
                        working.items
                    ) AS elements(item)
                    CROSS JOIN LATERAL jsonb_array_elements(
                        working.technical_requirements
                    ) AS requirements(requirement)
                    WHERE requirement->>'match_outcome' = 'global_scope'
                      AND requirement->>'review_status' = 'confirmed'
                      AND COALESCE(
                            (requirement->>'review_required')::boolean,
                            true
                          ) IS FALSE
                      AND requirement->>'generated_candidate_id'
                            = item->>'item_id'
                      AND item->>'status' = 'kept'
                      AND COALESCE(
                            (item->>'requires_confirmation')::boolean,
                            true
                          ) IS FALSE
                      AND item->>'acceptance_source' IN (
                            'manual',
                            'manual_override'
                          )
                      AND COALESCE(
                            (item->>'confirmation_accepted')::boolean,
                            false
                          ) IS TRUE
                ) THEN
                    RAISE EXCEPTION
                        'confirmed global requirement acceptance blocks downgrade'
                        USING ERRCODE = '23514';
                END IF;
            END;
            $$
            """
        )
    )
