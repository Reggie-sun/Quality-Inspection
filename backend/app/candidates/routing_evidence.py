from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.candidates.models import (
    SymbolEscalationAttemptEventRecord,
    SymbolEscalationOutcomeRecord,
    SymbolRoutingDecisionRecord,
    VisualSymbolCacheEntryRecord,
)
from app.candidates.symbol_routing import (
    RoutingDecision,
    validate_routing_decision,
)


ESCALATION_ATTEMPT_SCHEMA_VERSION = "symbol-escalation-attempt/1"
ESCALATION_OUTCOME_SCHEMA_VERSION = "symbol-escalation-outcome/1"
ATTEMPT_EVENT_CODES = frozenset(
    {
        "cache_hit_valid",
        "cache_miss",
        "cache_provenance_invalid",
        "provider_unavailable",
        "provider_response_valid",
        "provider_schema_invalid",
        "provider_timeout",
        "provider_transport_failure",
        "retry_scheduled",
        "not_started_budget_exhausted",
        "cancelled_after_project_budget",
    }
)
ATTEMPT_EVENT_ORDER = {
    code: index
    for index, code in enumerate(
        (
            "cache_hit_valid",
            "cache_miss",
            "cache_provenance_invalid",
            "provider_unavailable",
            "provider_response_valid",
            "provider_schema_invalid",
            "provider_timeout",
            "provider_transport_failure",
            "retry_scheduled",
            "not_started_budget_exhausted",
            "cancelled_after_project_budget",
        )
    )
}
GROUP_OUTCOME_CODES = frozenset(
    {
        "resolved",
        "partial_unresolved",
        "unresolved",
        "budget_exhausted",
        "cancelled",
    }
)
OBSERVATION_OUTCOME_CODES = frozenset(
    {
        "cache_resolved",
        "provider_resolved",
        "provider_no_detection",
        "provider_projection_rejected",
        "provider_unavailable",
        "provider_schema_invalid",
        "provider_timeout",
        "provider_transport_failure",
        "routing_budget_exhausted",
        "cancelled_after_project_budget",
    }
)


class RoutingEvidenceConflict(RuntimeError):
    pass


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _valid_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.strip() == value
    )


@dataclass(frozen=True)
class EscalationAttemptEvent:
    schema_version: str
    escalation_group_id: str
    routing_decision_sha256: str
    attempt_index: int
    event_code: str
    cache_entry_id: uuid.UUID | None
    provider_request_id: str | None

    def __post_init__(self) -> None:
        cache_event = self.event_code in {
            "cache_hit_valid",
            "cache_provenance_invalid",
        }
        if (
            self.schema_version != ESCALATION_ATTEMPT_SCHEMA_VERSION
            or not _valid_text(self.escalation_group_id)
            or not _valid_sha256(self.routing_decision_sha256)
            or not isinstance(self.attempt_index, int)
            or isinstance(self.attempt_index, bool)
            or self.attempt_index < 0
            or self.event_code not in ATTEMPT_EVENT_CODES
            or cache_event != (self.cache_entry_id is not None)
            or (
                self.provider_request_id is not None
                and not _valid_text(self.provider_request_id)
            )
        ):
            raise ValueError("symbol escalation attempt event invalid")

    @property
    def event_sha256(self) -> str:
        payload = asdict(self)
        if self.cache_entry_id is not None:
            payload["cache_entry_id"] = str(self.cache_entry_id)
        return _canonical_sha256(payload)


@dataclass(frozen=True)
class ObservationOutcome:
    visual_observation_id: str
    outcome_code: str

    def __post_init__(self) -> None:
        if (
            not _valid_text(self.visual_observation_id)
            or self.outcome_code not in OBSERVATION_OUTCOME_CODES
        ):
            raise ValueError("symbol observation outcome invalid")


@dataclass(frozen=True)
class EscalationOutcome:
    schema_version: str
    escalation_group_id: str
    routing_decision_sha256: str
    outcome_code: str
    observation_outcomes: tuple[ObservationOutcome, ...]
    attempt_event_sha256s: tuple[str, ...]
    terminal: bool

    def __post_init__(self) -> None:
        observation_ids = tuple(
            item.visual_observation_id
            for item in self.observation_outcomes
        )
        if (
            self.schema_version != ESCALATION_OUTCOME_SCHEMA_VERSION
            or not _valid_text(self.escalation_group_id)
            or not _valid_sha256(self.routing_decision_sha256)
            or self.outcome_code not in GROUP_OUTCOME_CODES
            or not self.observation_outcomes
            or len(set(observation_ids)) != len(observation_ids)
            or not self.attempt_event_sha256s
            or any(
                not _valid_sha256(value)
                for value in self.attempt_event_sha256s
            )
            or self.terminal is not True
        ):
            raise ValueError("symbol escalation outcome invalid")
        resolved = {
            item.outcome_code
            for item in self.observation_outcomes
        }.issubset({"cache_resolved", "provider_resolved"})
        partial = any(
            item.outcome_code in {"cache_resolved", "provider_resolved"}
            for item in self.observation_outcomes
        ) and not resolved
        all_codes = {
            item.outcome_code for item in self.observation_outcomes
        }
        expected_group_code = (
            "resolved"
            if resolved
            else (
                "partial_unresolved"
                if partial
                else (
                    "budget_exhausted"
                    if all_codes == {"routing_budget_exhausted"}
                    else (
                        "cancelled"
                        if all_codes == {
                            "cancelled_after_project_budget"
                        }
                        else "unresolved"
                    )
                )
            )
        )
        if (
            self.outcome_code != expected_group_code
        ):
            raise ValueError("symbol escalation outcome invalid")

    @property
    def outcome_sha256(self) -> str:
        return _canonical_sha256(
            {
                **asdict(self),
                "observation_outcomes": [
                    asdict(value) for value in self.observation_outcomes
                ],
            }
        )


def routing_decision_sha256(
    *,
    decision: RoutingDecision,
    escalation_group_id: str | None,
    escalation_group_member_index: int | None,
    local_resolution_ref: str | None,
) -> str:
    return _canonical_sha256(
        {
            **asdict(validate_routing_decision(decision)),
            "escalation_group_id": escalation_group_id,
            "escalation_group_member_index": (
                escalation_group_member_index
            ),
            "local_resolution_ref": local_resolution_ref,
        }
    )


def routing_decision_group_sha256(
    decision_sha256s: tuple[str, ...],
) -> str:
    if (
        not decision_sha256s
        or any(not _valid_sha256(value) for value in decision_sha256s)
        or len(set(decision_sha256s)) != len(decision_sha256s)
    ):
        raise ValueError("routing decision group hashes invalid")
    return _canonical_sha256(decision_sha256s)


class RoutingEvidenceRepository:
    """Validate and append immutable routing evidence; owns no semantics."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _group_decisions(
        self,
        *,
        project_id: uuid.UUID,
        escalation_group_id: str,
        lock: bool = True,
    ) -> tuple[SymbolRoutingDecisionRecord, ...]:
        statement = (
            select(SymbolRoutingDecisionRecord)
            .where(
                    SymbolRoutingDecisionRecord.project_id == project_id,
                    SymbolRoutingDecisionRecord.escalation_group_id
                    == escalation_group_id,
                    SymbolRoutingDecisionRecord.disposition == "escalate",
                )
            .order_by(
                SymbolRoutingDecisionRecord.escalation_group_member_index
            )
        )
        if lock:
            statement = statement.with_for_update()
        decisions = tuple(self._session.scalars(statement))
        indexes = tuple(
            record.escalation_group_member_index
            for record in decisions
        )
        if indexes != tuple(range(len(decisions))):
            raise RoutingEvidenceConflict(
                "symbol escalation group member order conflicts"
            )
        return decisions

    def _validated_group_hash(
        self,
        *,
        project_id: uuid.UUID,
        escalation_group_id: str,
        claimed_sha256: str,
    ) -> tuple[
        str,
        tuple[SymbolRoutingDecisionRecord, ...],
    ]:
        decisions = self._group_decisions(
            project_id=project_id,
            escalation_group_id=escalation_group_id,
        )
        if not decisions:
            raise RoutingEvidenceConflict(
                "symbol escalation group decisions are missing"
            )
        expected_sha256 = routing_decision_group_sha256(
            tuple(record.decision_sha256 for record in decisions)
        )
        if claimed_sha256 != expected_sha256:
            raise RoutingEvidenceConflict(
                "symbol escalation group decision hash conflicts"
            )
        return expected_sha256, decisions

    def record_decision(
        self,
        *,
        project_id: uuid.UUID,
        decision: RoutingDecision,
        escalation_group_id: str | None,
        escalation_group_member_index: int | None,
        local_resolution_ref: str | None = None,
    ) -> SymbolRoutingDecisionRecord:
        decision = validate_routing_decision(decision)
        if (
            decision.disposition == "escalate"
            and not _valid_text(escalation_group_id)
        ) or (
            decision.disposition == "escalate"
            and (
                not isinstance(escalation_group_member_index, int)
                or isinstance(escalation_group_member_index, bool)
                or escalation_group_member_index < 0
            )
        ) or (
            decision.disposition != "escalate"
            and escalation_group_member_index is not None
        ) or (
            decision.disposition != "escalate"
            and escalation_group_id is not None
        ) or (
            decision.disposition == "locally_resolved"
            and not _valid_text(local_resolution_ref)
        ) or (
            decision.disposition != "locally_resolved"
            and local_resolution_ref is not None
        ):
            raise ValueError("routing evidence references invalid")
        decision_hash = routing_decision_sha256(
            decision=decision,
            escalation_group_id=escalation_group_id,
            escalation_group_member_index=(
                escalation_group_member_index
            ),
            local_resolution_ref=local_resolution_ref,
        )
        inserted_id = self._session.scalar(
            insert(SymbolRoutingDecisionRecord)
            .values(
                id=uuid.uuid4(),
                project_id=project_id,
                visual_observation_id=decision.visual_observation_id,
                escalation_group_id=escalation_group_id,
                escalation_group_member_index=(
                    escalation_group_member_index
                ),
                local_resolution_ref=local_resolution_ref,
                schema_version=decision.schema_version,
                router_version=decision.router_version,
                input_sha256=decision.input_sha256,
                disposition=decision.disposition,
                local_resolution_reason_codes=list(
                    decision.local_resolution_reason_codes
                ),
                escalation_reason_codes=list(
                    decision.escalation_reason_codes
                ),
                block_reason_codes=list(decision.block_reason_codes),
                requires_confirmation=decision.requires_confirmation,
                decision_sha256=decision_hash,
            )
            .on_conflict_do_nothing(
                index_elements=("project_id", "visual_observation_id")
            )
            .returning(SymbolRoutingDecisionRecord.id)
        )
        del inserted_id
        record = self._session.scalar(
            select(SymbolRoutingDecisionRecord).where(
                SymbolRoutingDecisionRecord.project_id == project_id,
                SymbolRoutingDecisionRecord.visual_observation_id
                == decision.visual_observation_id,
            )
        )
        if record is None:
            raise RoutingEvidenceConflict(
                "routing decision first-writer record is missing"
            )
        if record.decision_sha256 != decision_hash:
            raise RoutingEvidenceConflict("routing decision replay conflicts")
        return record

    def load_terminal_outcome(
        self,
        *,
        project_id: uuid.UUID,
        escalation_group_id: str,
        routing_decision_sha256: str,
    ) -> EscalationOutcome | None:
        _, decisions = self._validated_group_hash(
            project_id=project_id,
            escalation_group_id=escalation_group_id,
            claimed_sha256=routing_decision_sha256,
        )
        record = self._session.scalar(
            select(SymbolEscalationOutcomeRecord).where(
                SymbolEscalationOutcomeRecord.project_id == project_id,
                SymbolEscalationOutcomeRecord.escalation_group_id
                == escalation_group_id,
            )
        )
        if record is None:
            return None
        try:
            outcome = EscalationOutcome(
                schema_version=record.schema_version,
                escalation_group_id=record.escalation_group_id,
                routing_decision_sha256=(
                    record.routing_decision_sha256
                ),
                outcome_code=record.outcome_code,
                observation_outcomes=tuple(
                    ObservationOutcome(**value)
                    for value in record.observation_outcomes
                ),
                attempt_event_sha256s=tuple(
                    record.attempt_event_sha256s
                ),
                terminal=record.terminal,
            )
            expected_observations = tuple(
                item.visual_observation_id for item in decisions
            )
            if (
                outcome.routing_decision_sha256
                != routing_decision_sha256
                or tuple(
                    item.visual_observation_id
                    for item in outcome.observation_outcomes
                )
                != expected_observations
                or outcome.attempt_event_sha256s
                != self.canonical_attempt_sha256s(
                    project_id=project_id,
                    escalation_group_id=escalation_group_id,
                    routing_decision_sha256=routing_decision_sha256,
                )
                or outcome.outcome_sha256 != record.outcome_sha256
            ):
                raise ValueError
        except Exception:
            raise RoutingEvidenceConflict(
                "symbol escalation terminal evidence conflicts"
            ) from None
        return outcome

    def append_attempt(
        self,
        *,
        project_id: uuid.UUID,
        event: EscalationAttemptEvent,
    ) -> SymbolEscalationAttemptEventRecord:
        event_hash = event.event_sha256
        existing = self._session.scalar(
            select(SymbolEscalationAttemptEventRecord).where(
                SymbolEscalationAttemptEventRecord.project_id == project_id,
                SymbolEscalationAttemptEventRecord.escalation_group_id
                == event.escalation_group_id,
                SymbolEscalationAttemptEventRecord.attempt_index
                == event.attempt_index,
                SymbolEscalationAttemptEventRecord.event_code
                == event.event_code,
            )
        )
        if existing is not None:
            if existing.event_sha256 != event_hash:
                raise RoutingEvidenceConflict(
                    "symbol escalation attempt replay conflicts"
                )
            return existing
        self._validated_group_hash(
            project_id=project_id,
            escalation_group_id=event.escalation_group_id,
            claimed_sha256=event.routing_decision_sha256,
        )
        terminal = self._session.scalar(
            select(SymbolEscalationOutcomeRecord.id).where(
                SymbolEscalationOutcomeRecord.project_id == project_id,
                SymbolEscalationOutcomeRecord.escalation_group_id
                == event.escalation_group_id,
            )
        )
        if terminal is not None:
            raise RoutingEvidenceConflict(
                "symbol escalation attempt follows terminal outcome"
            )
        if event.cache_entry_id is not None:
            cache_entry = self._session.get(
                VisualSymbolCacheEntryRecord,
                event.cache_entry_id,
            )
            if (
                cache_entry is None
                or cache_entry.project_id != project_id
            ):
                raise RoutingEvidenceConflict(
                    "symbol cache attempt project scope conflicts"
                )
        self._session.scalar(
            insert(SymbolEscalationAttemptEventRecord)
            .values(
                id=uuid.uuid4(),
                project_id=project_id,
                escalation_group_id=event.escalation_group_id,
                routing_decision_sha256=(
                    event.routing_decision_sha256
                ),
                attempt_index=event.attempt_index,
                event_code=event.event_code,
                cache_entry_id=event.cache_entry_id,
                provider_request_id=event.provider_request_id,
                event_sha256=event_hash,
            )
            .on_conflict_do_nothing()
            .returning(SymbolEscalationAttemptEventRecord.id)
        )
        record = self._session.scalar(
            select(SymbolEscalationAttemptEventRecord).where(
                SymbolEscalationAttemptEventRecord.project_id == project_id,
                SymbolEscalationAttemptEventRecord.escalation_group_id
                == event.escalation_group_id,
                SymbolEscalationAttemptEventRecord.attempt_index
                == event.attempt_index,
                SymbolEscalationAttemptEventRecord.event_code
                == event.event_code,
            )
        )
        if record is None or record.event_sha256 != event_hash:
            raise RoutingEvidenceConflict(
                "symbol escalation attempt replay conflicts"
            )
        return record

    def canonical_attempt_sha256s(
        self,
        *,
        project_id: uuid.UUID,
        escalation_group_id: str,
        routing_decision_sha256: str,
    ) -> tuple[str, ...]:
        expected_group_sha256, _ = self._validated_group_hash(
            project_id=project_id,
            escalation_group_id=escalation_group_id,
            claimed_sha256=routing_decision_sha256,
        )
        attempts = tuple(
            self._session.scalars(
                select(SymbolEscalationAttemptEventRecord).where(
                    SymbolEscalationAttemptEventRecord.project_id
                    == project_id,
                    SymbolEscalationAttemptEventRecord.escalation_group_id
                    == escalation_group_id,
                )
            )
        )
        if not attempts or any(
            record.routing_decision_sha256 != expected_group_sha256
            for record in attempts
        ):
            raise RoutingEvidenceConflict(
                "symbol escalation attempt history conflicts"
            )
        return tuple(
            record.event_sha256
            for record in sorted(
                attempts,
                key=lambda record: (
                    record.attempt_index,
                    ATTEMPT_EVENT_ORDER[record.event_code],
                    record.event_sha256,
                ),
            )
        )

    def record_terminal_outcome(
        self,
        *,
        project_id: uuid.UUID,
        outcome: EscalationOutcome,
    ) -> SymbolEscalationOutcomeRecord:
        expected_group_sha256, decisions = self._validated_group_hash(
            project_id=project_id,
            escalation_group_id=outcome.escalation_group_id,
            claimed_sha256=outcome.routing_decision_sha256,
        )
        expected_observation_ids = tuple(
            record.visual_observation_id for record in decisions
        )
        actual_observation_ids = tuple(
            item.visual_observation_id
            for item in outcome.observation_outcomes
        )
        if actual_observation_ids != expected_observation_ids:
            raise RoutingEvidenceConflict(
                "symbol escalation outcome observation set conflicts"
            )
        expected_attempt_hashes = self.canonical_attempt_sha256s(
            project_id=project_id,
            escalation_group_id=outcome.escalation_group_id,
            routing_decision_sha256=expected_group_sha256,
        )
        if outcome.attempt_event_sha256s != expected_attempt_hashes:
            raise RoutingEvidenceConflict(
                "symbol escalation outcome attempt set conflicts"
            )
        outcome_hash = outcome.outcome_sha256
        self._session.scalar(
            insert(SymbolEscalationOutcomeRecord)
            .values(
                id=uuid.uuid4(),
                project_id=project_id,
                escalation_group_id=outcome.escalation_group_id,
                routing_decision_sha256=(
                    outcome.routing_decision_sha256
                ),
                schema_version=outcome.schema_version,
                outcome_code=outcome.outcome_code,
                observation_outcomes=[
                    asdict(value)
                    for value in outcome.observation_outcomes
                ],
                attempt_event_sha256s=list(
                    outcome.attempt_event_sha256s
                ),
                terminal=outcome.terminal,
                outcome_sha256=outcome_hash,
            )
            .on_conflict_do_nothing(
                index_elements=("project_id", "escalation_group_id")
            )
            .returning(SymbolEscalationOutcomeRecord.id)
        )
        record = self._session.scalar(
            select(SymbolEscalationOutcomeRecord).where(
                SymbolEscalationOutcomeRecord.project_id == project_id,
                SymbolEscalationOutcomeRecord.escalation_group_id
                == outcome.escalation_group_id,
            )
        )
        if record is None or record.outcome_sha256 != outcome_hash:
            raise RoutingEvidenceConflict(
                "symbol escalation outcome replay conflicts"
            )
        return record
