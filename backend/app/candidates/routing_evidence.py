from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import cast

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
from app.providers.base import (
    ProviderFailureCategory,
    ProviderFailureFact,
    ProviderFailureOrigin,
    ProviderRequestIdState,
    classify_provider_failure_request_id,
)


ESCALATION_ATTEMPT_SCHEMA_VERSION_V1 = "symbol-escalation-attempt/1"
ESCALATION_ATTEMPT_SCHEMA_VERSION_V2 = "symbol-escalation-attempt/2"
ESCALATION_ATTEMPT_SCHEMA_VERSION = ESCALATION_ATTEMPT_SCHEMA_VERSION_V1
ESCALATION_OUTCOME_SCHEMA_VERSION = "symbol-escalation-outcome/1"
PROVIDER_FAILURE_EVENT_CODES = frozenset(
    {
        "provider_schema_invalid",
        "provider_timeout",
        "provider_transport_failure",
        "provider_authentication_failed",
        "provider_request_rejected",
        "provider_rate_limited",
        "provider_service_failure",
        "provider_metadata_invalid",
        "provider_unclassified_failure",
    }
)
ADVISOR_BOUNDARY_FAILURE_EVENT_CODES = frozenset(
    {
        "provider_factory_failed",
        "provider_contract_failure",
        "advisor_result_missing",
    }
)
PROJECT_FAILURE_CANCELLATION_EVENT_CODE = (
    "not_started_after_project_failure"
)
PROJECT_FAILURE_CANCELLATION_OUTCOME_CODE = (
    "cancelled_after_project_failure"
)
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
    | PROVIDER_FAILURE_EVENT_CODES
    | ADVISOR_BOUNDARY_FAILURE_EVENT_CODES
    | {PROJECT_FAILURE_CANCELLATION_EVENT_CODE}
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
            "provider_authentication_failed",
            "provider_request_rejected",
            "provider_rate_limited",
            "provider_service_failure",
            "provider_metadata_invalid",
            "provider_unclassified_failure",
            "provider_factory_failed",
            "provider_contract_failure",
            "advisor_result_missing",
            "retry_scheduled",
            "not_started_budget_exhausted",
            "cancelled_after_project_budget",
            PROJECT_FAILURE_CANCELLATION_EVENT_CODE,
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
    | PROVIDER_FAILURE_EVENT_CODES
    | ADVISOR_BOUNDARY_FAILURE_EVENT_CODES
    | {PROJECT_FAILURE_CANCELLATION_OUTCOME_CODE}
)

_PROVIDER_FAILURE_CLASSIFICATION = {
    "timeout": ("provider_timeout", "roi_localized", None),
    "transport": ("provider_transport_failure", "roi_localized", None),
    "schema": ("provider_schema_invalid", "roi_localized", None),
    "authentication": (
        "provider_authentication_failed",
        "project_blocking",
        "invalid_configuration",
    ),
    "request_rejected": (
        "provider_request_rejected",
        "project_blocking",
        "processing_defect",
    ),
    "rate_limited": (
        "provider_rate_limited",
        "project_blocking",
        "transient_provider_failure",
    ),
    "service_failure": (
        "provider_service_failure",
        "project_blocking",
        "transient_provider_failure",
    ),
    "metadata_invalid": (
        "provider_metadata_invalid",
        "project_blocking",
        "processing_defect",
    ),
    "unclassified": (
        "provider_unclassified_failure",
        "project_blocking",
        "processing_defect",
    ),
}
_PROVIDER_DIAGNOSTIC_KEYS = frozenset(
    {
        "schema_version",
        "failure_category",
        "failure_stage",
        "scope",
        "origin",
        "http_status",
        "request_id_state",
        "pipeline_cause_category",
        "retry_decision",
    }
)
_ADVISOR_BOUNDARY_DIAGNOSTIC_KEYS = frozenset(
    {
        "schema_version",
        "failure_stage",
        "scope",
        "pipeline_cause_category",
        "provider_work_started",
    }
)
_RETRY_CONTROL_DIAGNOSTIC_KEYS = frozenset(
    {
        "schema_version",
        "retry_reason",
        "authorization_owner",
        "failure_event_sha256",
    }
)
_SCHEDULER_STOP_DIAGNOSTIC_KEYS = frozenset(
    {
        "schema_version",
        "stop_reason",
        "blocking_event_sha256",
        "provider_work_started",
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


def validate_provider_failure_diagnostic(
    document: Mapping[str, object],
) -> None:
    category = document.get("failure_category")
    origin = document.get("origin")
    http_status = document.get("http_status")
    request_id_state = document.get("request_id_state")
    expected = (
        _PROVIDER_FAILURE_CLASSIFICATION.get(category)
        if isinstance(category, str)
        else None
    )
    if (
        set(document) != _PROVIDER_DIAGNOSTIC_KEYS
        or document.get("schema_version")
        != "visual-symbol-provider-failure/1"
        or expected is None
        or (
            document.get("failure_stage"),
            document.get("scope"),
            document.get("pipeline_cause_category"),
        )
        != expected
        or document.get("retry_decision")
        not in {"not_authorized", "authorized_schema_retry"}
        or (
            document.get("retry_decision") == "authorized_schema_retry"
            and category != "schema"
        )
    ):
        raise ValueError("Provider failure diagnostic is invalid")
    try:
        ProviderFailureFact(
            category=cast(ProviderFailureCategory, category),
            origin=cast(ProviderFailureOrigin, origin),
            http_status=cast(int | None, http_status),
            provider_request_id=(
                "accepted-request-id"
                if request_id_state == "accepted"
                else None
            ),
            request_id_state=cast(
                ProviderRequestIdState,
                request_id_state,
            ),
        )
    except (TypeError, ValueError):
        raise ValueError("Provider failure diagnostic is invalid") from None


def validate_advisor_boundary_failure_diagnostic(
    document: Mapping[str, object],
) -> None:
    failure_stage = document.get("failure_stage")
    expected_work_started = {
        "provider_factory_failed": False,
        "provider_contract_failure": True,
        "advisor_result_missing": True,
    }.get(failure_stage) if isinstance(failure_stage, str) else None
    if (
        set(document) != _ADVISOR_BOUNDARY_DIAGNOSTIC_KEYS
        or document.get("schema_version")
        != "visual-symbol-advisor-boundary-failure/1"
        or expected_work_started is None
        or document.get("scope") != "project_blocking"
        or document.get("pipeline_cause_category") != "processing_defect"
        or document.get("provider_work_started") is not expected_work_started
    ):
        raise ValueError("Advisor boundary failure diagnostic is invalid")


def validate_retry_control_diagnostic(
    document: Mapping[str, object],
) -> None:
    if (
        set(document) != _RETRY_CONTROL_DIAGNOSTIC_KEYS
        or document.get("schema_version") != "visual-symbol-retry-control/1"
        or document.get("retry_reason") != "schema_invalid"
        or document.get("authorization_owner")
        != "production_retry_coordinator"
        or not _valid_sha256(document.get("failure_event_sha256"))
    ):
        raise ValueError("Retry control diagnostic is invalid")


def validate_scheduler_stop_diagnostic(
    document: Mapping[str, object],
) -> None:
    stop_reason = document.get("stop_reason")
    if (
        set(document) != _SCHEDULER_STOP_DIAGNOSTIC_KEYS
        or document.get("schema_version")
        != "visual-symbol-scheduler-stop/1"
        or not isinstance(stop_reason, str)
        or stop_reason
        not in {
            "project_blocking_provider_failure",
            "project_blocking_advisor_boundary_failure",
        }
        or not _valid_sha256(document.get("blocking_event_sha256"))
        or document.get("provider_work_started") is not False
    ):
        raise ValueError("Scheduler stop diagnostic is invalid")


@dataclass(frozen=True)
class ProviderFailureDiagnostic:
    schema_version: str
    failure_category: str
    failure_stage: str
    scope: str
    origin: str
    http_status: int | None
    request_id_state: str
    pipeline_cause_category: str | None
    retry_decision: str

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_provider_failure_diagnostic(document)
        return document


@dataclass(frozen=True)
class AdvisorBoundaryFailureDiagnostic:
    schema_version: str
    failure_stage: str
    scope: str
    pipeline_cause_category: str
    provider_work_started: bool

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_advisor_boundary_failure_diagnostic(document)
        return document


@dataclass(frozen=True)
class RetryControlDiagnostic:
    schema_version: str
    retry_reason: str
    authorization_owner: str
    failure_event_sha256: str

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_retry_control_diagnostic(document)
        return document


@dataclass(frozen=True)
class SchedulerStopDiagnostic:
    schema_version: str
    stop_reason: str
    blocking_event_sha256: str
    provider_work_started: bool

    def as_dict(self) -> dict[str, object]:
        document = asdict(self)
        validate_scheduler_stop_diagnostic(document)
        return document


def _validate_attempt_diagnostic(
    event: EscalationAttemptEvent,
) -> None:
    document = event.diagnostic
    if not isinstance(document, Mapping):
        raise ValueError("symbol escalation attempt event invalid")
    schema_version = document.get("schema_version")
    try:
        if schema_version == "visual-symbol-provider-failure/1":
            validate_provider_failure_diagnostic(document)
            if document.get("failure_stage") != event.event_code:
                raise ValueError
            request_id_state = document.get("request_id_state")
            ProviderFailureFact(
                category=cast(
                    ProviderFailureCategory,
                    document.get("failure_category"),
                ),
                origin=cast(
                    ProviderFailureOrigin,
                    document.get("origin"),
                ),
                http_status=cast(int | None, document.get("http_status")),
                provider_request_id=event.provider_request_id,
                request_id_state=cast(
                    ProviderRequestIdState,
                    request_id_state,
                ),
            )
        elif schema_version == "visual-symbol-advisor-boundary-failure/1":
            validate_advisor_boundary_failure_diagnostic(document)
            if (
                document.get("failure_stage") != event.event_code
                or event.provider_request_id is not None
            ):
                raise ValueError
        elif schema_version == "visual-symbol-retry-control/1":
            validate_retry_control_diagnostic(document)
            if event.event_code != "retry_scheduled":
                raise ValueError
            if event.provider_request_id is not None and (
                classify_provider_failure_request_id(
                    event.provider_request_id
                )[1]
                != "accepted"
            ):
                raise ValueError
        elif schema_version == "visual-symbol-scheduler-stop/1":
            validate_scheduler_stop_diagnostic(document)
            if (
                event.event_code != PROJECT_FAILURE_CANCELLATION_EVENT_CODE
                or event.provider_request_id is not None
            ):
                raise ValueError
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("symbol escalation attempt event invalid") from None


def _is_schema_retry_pair_member(event: EscalationAttemptEvent) -> bool:
    return event.event_code == "retry_scheduled" or (
        isinstance(event.diagnostic, Mapping)
        and event.diagnostic.get("schema_version")
        == "visual-symbol-provider-failure/1"
        and event.diagnostic.get("retry_decision")
        == "authorized_schema_retry"
    )


def _validate_schema_retry_pair(
    failure_event: EscalationAttemptEvent,
    retry_event: EscalationAttemptEvent,
) -> None:
    failure_diagnostic = failure_event.diagnostic
    retry_diagnostic = retry_event.diagnostic
    if (
        failure_event.schema_version
        != ESCALATION_ATTEMPT_SCHEMA_VERSION_V2
        or failure_event.event_code != "provider_schema_invalid"
        or not isinstance(failure_diagnostic, Mapping)
        or failure_diagnostic.get("retry_decision")
        != "authorized_schema_retry"
        or retry_event.schema_version
        != ESCALATION_ATTEMPT_SCHEMA_VERSION_V2
        or retry_event.event_code != "retry_scheduled"
        or not isinstance(retry_diagnostic, Mapping)
        or failure_event.escalation_group_id
        != retry_event.escalation_group_id
        or failure_event.routing_decision_sha256
        != retry_event.routing_decision_sha256
        or failure_event.attempt_index != retry_event.attempt_index
        or failure_event.provider_request_id
        != retry_event.provider_request_id
        or retry_diagnostic.get("failure_event_sha256")
        != failure_event.event_sha256
        or ATTEMPT_EVENT_ORDER["provider_schema_invalid"]
        >= ATTEMPT_EVENT_ORDER["retry_scheduled"]
    ):
        raise RoutingEvidenceConflict("schema retry evidence conflicts")


@dataclass(frozen=True)
class EscalationAttemptEvent:
    schema_version: str
    escalation_group_id: str
    routing_decision_sha256: str
    attempt_index: int
    event_code: str
    cache_entry_id: uuid.UUID | None
    provider_request_id: str | None
    diagnostic: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        cache_event = self.event_code in {
            "cache_hit_valid",
            "cache_provenance_invalid",
        }
        if (
            self.schema_version
            not in {
                ESCALATION_ATTEMPT_SCHEMA_VERSION_V1,
                ESCALATION_ATTEMPT_SCHEMA_VERSION_V2,
            }
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
        if self.schema_version == ESCALATION_ATTEMPT_SCHEMA_VERSION_V1:
            if self.diagnostic is not None:
                raise ValueError("symbol escalation attempt event invalid")
        else:
            _validate_attempt_diagnostic(self)

    @property
    def diagnostic_sha256(self) -> str | None:
        if self.schema_version == ESCALATION_ATTEMPT_SCHEMA_VERSION_V1:
            return None
        return _canonical_sha256(dict(self.diagnostic or {}))

    @property
    def event_sha256(self) -> str:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "escalation_group_id": self.escalation_group_id,
            "routing_decision_sha256": self.routing_decision_sha256,
            "attempt_index": self.attempt_index,
            "event_code": self.event_code,
            "cache_entry_id": (
                None
                if self.cache_entry_id is None
                else str(self.cache_entry_id)
            ),
            "provider_request_id": self.provider_request_id,
        }
        if self.schema_version == ESCALATION_ATTEMPT_SCHEMA_VERSION_V2:
            diagnostic = dict(self.diagnostic or {})
            payload["diagnostic"] = diagnostic
            payload["diagnostic_sha256"] = self.diagnostic_sha256
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
                        if all_codes
                        in (
                            {"cancelled_after_project_budget"},
                            {PROJECT_FAILURE_CANCELLATION_OUTCOME_CODE},
                        )
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
        if _is_schema_retry_pair_member(event):
            raise RoutingEvidenceConflict(
                "schema retry evidence requires pair writer"
            )
        return self._append_attempt_record(
            project_id=project_id,
            event=event,
        )

    def _validate_scheduler_stop_reference(
        self,
        *,
        project_id: uuid.UUID,
        event: EscalationAttemptEvent,
    ) -> None:
        diagnostic = event.diagnostic
        if (
            not isinstance(diagnostic, Mapping)
            or diagnostic.get("schema_version")
            != "visual-symbol-scheduler-stop/1"
        ):
            return
        blocking = self._session.scalar(
            select(SymbolEscalationAttemptEventRecord).where(
                SymbolEscalationAttemptEventRecord.project_id == project_id,
                SymbolEscalationAttemptEventRecord.event_sha256
                == diagnostic.get("blocking_event_sha256"),
            )
        )
        blocking_diagnostic = (
            None if blocking is None else blocking.diagnostic
        )
        expected_schema = {
            "project_blocking_provider_failure": (
                "visual-symbol-provider-failure/1"
            ),
            "project_blocking_advisor_boundary_failure": (
                "visual-symbol-advisor-boundary-failure/1"
            ),
        }.get(diagnostic.get("stop_reason"))
        if (
            not isinstance(blocking_diagnostic, Mapping)
            or blocking_diagnostic.get("schema_version") != expected_schema
            or blocking_diagnostic.get("scope") != "project_blocking"
        ):
            raise RoutingEvidenceConflict(
                "scheduler stop evidence conflicts"
            )

    @staticmethod
    def _attempt_record_matches(
        record: SymbolEscalationAttemptEventRecord,
        event: EscalationAttemptEvent,
    ) -> bool:
        expected_diagnostic = (
            None
            if event.diagnostic is None
            else dict(event.diagnostic)
        )
        return (
            record.event_sha256 == event.event_sha256
            and record.schema_version == event.schema_version
            and record.diagnostic == expected_diagnostic
            and record.diagnostic_sha256 == event.diagnostic_sha256
        )

    def _append_attempt_record(
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
            if not self._attempt_record_matches(existing, event):
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
        self._validate_scheduler_stop_reference(
            project_id=project_id,
            event=event,
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
                schema_version=event.schema_version,
                diagnostic=(
                    None
                    if event.diagnostic is None
                    else dict(event.diagnostic)
                ),
                diagnostic_sha256=event.diagnostic_sha256,
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
        if record is None or not self._attempt_record_matches(record, event):
            raise RoutingEvidenceConflict(
                "symbol escalation attempt replay conflicts"
            )
        return record

    def record_failure_terminal(
        self,
        *,
        project_id: uuid.UUID,
        event: EscalationAttemptEvent,
        outcome_code: str,
        observation_outcomes: tuple[ObservationOutcome, ...],
    ) -> str:
        if _is_schema_retry_pair_member(event):
            raise RoutingEvidenceConflict(
                "schema retry evidence requires pair writer"
            )
        if (
            event.schema_version
            != ESCALATION_ATTEMPT_SCHEMA_VERSION_V2
            or event.event_code
            not in (
                PROVIDER_FAILURE_EVENT_CODES
                | ADVISOR_BOUNDARY_FAILURE_EVENT_CODES
                | {PROJECT_FAILURE_CANCELLATION_EVENT_CODE}
            )
        ):
            raise RoutingEvidenceConflict(
                "failure terminal evidence conflicts"
            )
        attempt = self.append_attempt(
            project_id=project_id,
            event=event,
        )
        attempt_sha256s = self.canonical_attempt_sha256s(
            project_id=project_id,
            escalation_group_id=event.escalation_group_id,
            routing_decision_sha256=event.routing_decision_sha256,
        )
        self.record_terminal_outcome(
            project_id=project_id,
            outcome=EscalationOutcome(
                schema_version=ESCALATION_OUTCOME_SCHEMA_VERSION,
                escalation_group_id=event.escalation_group_id,
                routing_decision_sha256=event.routing_decision_sha256,
                outcome_code=outcome_code,
                observation_outcomes=observation_outcomes,
                attempt_event_sha256s=attempt_sha256s,
                terminal=True,
            ),
        )
        return attempt.event_sha256

    def record_schema_retry(
        self,
        *,
        project_id: uuid.UUID,
        failure_event: EscalationAttemptEvent,
    ) -> str:
        retry_event = EscalationAttemptEvent(
            schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION_V2,
            escalation_group_id=failure_event.escalation_group_id,
            routing_decision_sha256=(
                failure_event.routing_decision_sha256
            ),
            attempt_index=failure_event.attempt_index,
            event_code="retry_scheduled",
            cache_entry_id=None,
            provider_request_id=failure_event.provider_request_id,
            diagnostic=RetryControlDiagnostic(
                schema_version="visual-symbol-retry-control/1",
                retry_reason="schema_invalid",
                authorization_owner="production_retry_coordinator",
                failure_event_sha256=failure_event.event_sha256,
            ).as_dict(),
        )
        _validate_schema_retry_pair(failure_event, retry_event)
        failure_attempt = self._append_attempt_record(
            project_id=project_id,
            event=failure_event,
        )
        self._append_attempt_record(
            project_id=project_id,
            event=retry_event,
        )
        return failure_attempt.event_sha256

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
