from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Callable, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.candidates.models import VisualSymbolCacheEntryRecord
from app.candidates.symbol_review import parse_visual_symbol_json

if TYPE_CHECKING:
    from app.candidates.routing_evidence import RoutingEvidenceRepository


CACHE_IDENTITY_SCHEMA_VERSION = "visual-symbol-cache-identity/1"
CACHE_ENTRY_SCHEMA_VERSION = "visual-symbol-cache-entry/1"
CROP_CANONICALIZATION_VERSION = "qwen-visual-png/1"


class CacheWriteRejected(ValueError):
    pass


class InvalidCacheWinner(CacheWriteRejected):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


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


def _valid_asset_ref(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("asset://"):
        return False
    relative = value.removeprefix("asset://")
    path = PurePosixPath(relative)
    return (
        bool(relative)
        and not path.is_absolute()
        and "\\" not in relative
        and all(
            part not in {"", ".", ".."}
            and part == part.strip()
            and not any(character.isspace() for character in part)
            for part in relative.split("/")
        )
    )


def _valid_producer_call_ref(
    value: object,
    producer_project_id: str,
) -> bool:
    return _valid_asset_ref(value) and str(value).startswith(
        f"asset://projects/{producer_project_id}/"
        "provider-calls/qwen-symbol/"
    )


@dataclass(frozen=True)
class SymbolCacheIdentity:
    schema_version: str
    canonical_crop_sha256: str
    associated_text_sha256: str
    local_evidence_sha256s: tuple[str, ...]
    router_version: str
    proposal_version: str
    prompt_version: str
    response_schema_version: str
    adapter_version: str
    model_identity: str
    pymupdf_version: str
    crop_canonicalization_version: str

    def __post_init__(self) -> None:
        if (
            not _valid_text(self.schema_version)
            or not _valid_sha256(self.canonical_crop_sha256)
            or not _valid_sha256(self.associated_text_sha256)
            or not self.local_evidence_sha256s
            or any(
                not _valid_sha256(value)
                for value in self.local_evidence_sha256s
            )
            or len(set(self.local_evidence_sha256s))
            != len(self.local_evidence_sha256s)
            or any(
                not _valid_text(value)
                for value in (
                    self.router_version,
                    self.proposal_version,
                    self.prompt_version,
                    self.response_schema_version,
                    self.adapter_version,
                    self.model_identity,
                    self.pymupdf_version,
                    self.crop_canonicalization_version,
                )
            )
        ):
            raise ValueError("symbol cache identity invalid")

    @property
    def sha256(self) -> str:
        return _sha256(asdict(self))


@dataclass(frozen=True)
class SymbolCacheProvenance:
    identity_sha256: str
    producer_project_id: str
    producer_request_id: str
    producer_call_record_ref: str
    response_sha256: str
    created_at: datetime
    model_identity: str
    response_schema_version: str
    router_version: str
    validation_outcome: str


@dataclass(frozen=True)
class VisualSymbolCacheEntry:
    identity: SymbolCacheIdentity
    response: dict[str, object]
    response_sha256: str
    provenance: SymbolCacheProvenance | None
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class CacheConsumer:
    escalation_group_id: str
    routing_decision_sha256: str
    attempt_index: int


@dataclass(frozen=True)
class CacheLookupResult:
    hit: bool
    reason_code: str
    quarantine: bool
    response: dict[str, object] | None
    entry: VisualSymbolCacheEntry | None = None
    attempt_event_sha256s: tuple[str, ...] = ()


@dataclass(frozen=True)
class CacheStoreResult:
    inserted: bool
    entry: VisualSymbolCacheEntry


def _provenance_valid(
    identity: SymbolCacheIdentity,
    entry: VisualSymbolCacheEntry,
) -> bool:
    provenance = entry.provenance
    if provenance is None:
        return False
    try:
        uuid.UUID(provenance.producer_project_id)
    except (TypeError, ValueError, AttributeError):
        return False
    return (
        provenance.identity_sha256 == identity.sha256
        and provenance.response_sha256 == entry.response_sha256
        and _valid_text(provenance.producer_request_id)
        and _valid_producer_call_ref(
            provenance.producer_call_record_ref,
            provenance.producer_project_id,
        )
        and isinstance(provenance.created_at, datetime)
        and provenance.model_identity == identity.model_identity
        and provenance.response_schema_version
        == identity.response_schema_version
        and provenance.router_version == identity.router_version
        and provenance.validation_outcome == "schema_valid"
    )


def evaluate_cache_entry(
    *,
    expected_identity: SymbolCacheIdentity,
    entry: VisualSymbolCacheEntry,
) -> CacheLookupResult:
    if (
        expected_identity.schema_version
        != CACHE_IDENTITY_SCHEMA_VERSION
        or entry.identity.schema_version
        != CACHE_IDENTITY_SCHEMA_VERSION
        or entry.identity.sha256 != expected_identity.sha256
    ):
        return CacheLookupResult(
            hit=False,
            reason_code="cache_identity_mismatch",
            quarantine=False,
            response=None,
        )
    try:
        response = parse_visual_symbol_json(entry.response)
    except Exception:
        response = None
    if (
        response is None
        or response.get("schema_version")
        != expected_identity.response_schema_version
        or not _valid_sha256(entry.response_sha256)
        or _sha256(entry.response) != entry.response_sha256
        or not _provenance_valid(expected_identity, entry)
    ):
        return CacheLookupResult(
            hit=False,
            reason_code="cache_provenance_invalid",
            quarantine=True,
            response=None,
            entry=entry,
        )
    return CacheLookupResult(
        hit=True,
        reason_code="cache_hit_valid",
        quarantine=False,
        response=dict(response),
        entry=entry,
    )


def build_cache_entry(
    *,
    identity: SymbolCacheIdentity,
    response: Mapping[str, object],
    provenance: SymbolCacheProvenance,
    provider_event_code: str,
    schema_valid: bool,
) -> VisualSymbolCacheEntry:
    if (
        identity.schema_version != CACHE_IDENTITY_SCHEMA_VERSION
        or provider_event_code != "provider_response_valid"
        or schema_valid is not True
    ):
        raise CacheWriteRejected("provider result is not cacheable")
    try:
        validated = parse_visual_symbol_json(dict(response))
    except Exception:
        raise CacheWriteRejected("provider result is not cacheable") from None
    response_sha256 = _sha256(validated)
    entry = VisualSymbolCacheEntry(
        identity=identity,
        response=dict(validated),
        response_sha256=response_sha256,
        provenance=provenance,
    )
    if not evaluate_cache_entry(
        expected_identity=identity,
        entry=entry,
    ).hit:
        raise CacheWriteRejected("provider result provenance is invalid")
    return entry


def _identity_payload(identity: SymbolCacheIdentity) -> dict[str, object]:
    payload = asdict(identity)
    payload["local_evidence_sha256s"] = list(
        identity.local_evidence_sha256s
    )
    return payload


def _provenance_payload(
    provenance: SymbolCacheProvenance,
) -> dict[str, object]:
    payload = asdict(provenance)
    payload["created_at"] = provenance.created_at.isoformat()
    return payload


def _provenance_sha256(
    provenance: SymbolCacheProvenance,
) -> str:
    return _sha256(_provenance_payload(provenance))


def _entry_from_record(
    record: VisualSymbolCacheEntryRecord,
) -> VisualSymbolCacheEntry:
    identity_payload = dict(record.identity)
    identity_payload["local_evidence_sha256s"] = tuple(
        identity_payload.get("local_evidence_sha256s", ())
    )
    identity = SymbolCacheIdentity(**identity_payload)
    provenance_payload = dict(record.producer_provenance)
    provenance: SymbolCacheProvenance | None
    try:
        provenance_payload["created_at"] = datetime.fromisoformat(
            str(provenance_payload["created_at"])
        )
        provenance = SymbolCacheProvenance(**provenance_payload)
        if (
            record.cache_schema_version != CACHE_ENTRY_SCHEMA_VERSION
            or record.identity_sha256 != identity.sha256
            or record.producer_request_id
            != provenance.producer_request_id
            or provenance.producer_project_id
            != str(record.project_id)
            or record.producer_call_record_ref
            != provenance.producer_call_record_ref
            or record.provenance_sha256
            != _provenance_sha256(provenance)
        ):
            provenance = None
    except Exception:
        provenance = None
    return VisualSymbolCacheEntry(
        id=record.id,
        identity=identity,
        response=dict(record.response),
        response_sha256=record.response_sha256,
        provenance=provenance,
    )


class VisualSymbolCache:
    """Project-local cache Signal Provider backed by immutable DB rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def store_if_absent(
        self,
        *,
        project_id: uuid.UUID,
        entry: VisualSymbolCacheEntry,
    ) -> CacheStoreResult:
        validation = evaluate_cache_entry(
            expected_identity=entry.identity,
            entry=entry,
        )
        if not validation.hit or entry.provenance is None:
            raise CacheWriteRejected("cache entry is invalid")
        if entry.provenance.producer_project_id != str(project_id):
            raise CacheWriteRejected(
                "cache producer project does not match namespace"
            )
        entry_id = uuid.uuid4()
        inserted_id = self._session.scalar(
            insert(VisualSymbolCacheEntryRecord)
            .values(
                id=entry_id,
                project_id=project_id,
                cache_key=entry.identity.sha256,
                cache_schema_version=CACHE_ENTRY_SCHEMA_VERSION,
                identity_sha256=entry.identity.sha256,
                identity=_identity_payload(entry.identity),
                response=entry.response,
                response_sha256=entry.response_sha256,
                producer_request_id=(
                    entry.provenance.producer_request_id
                ),
                producer_call_record_ref=(
                    entry.provenance.producer_call_record_ref
                ),
                producer_provenance=_provenance_payload(
                    entry.provenance
                ),
                provenance_sha256=_provenance_sha256(entry.provenance),
            )
            .on_conflict_do_nothing(
                index_elements=("project_id", "cache_key")
            )
            .returning(VisualSymbolCacheEntryRecord.id)
        )
        record = self._session.scalar(
            select(VisualSymbolCacheEntryRecord).where(
                VisualSymbolCacheEntryRecord.project_id == project_id,
                VisualSymbolCacheEntryRecord.cache_key
                == entry.identity.sha256,
            )
        )
        if record is None:
            raise CacheWriteRejected("cache first-writer record is missing")
        try:
            winner = _entry_from_record(record)
            winner_valid = evaluate_cache_entry(
                expected_identity=entry.identity,
                entry=winner,
            ).hit
        except Exception:
            winner_valid = False
        if not winner_valid:
            raise InvalidCacheWinner(
                "cache first-writer provenance is invalid"
            )
        return CacheStoreResult(
            inserted=inserted_id == entry_id,
            entry=winner,
        )

    def lookup(
        self,
        *,
        project_id: uuid.UUID,
        identity: SymbolCacheIdentity,
        consumer: CacheConsumer | None = None,
        evidence: RoutingEvidenceRepository | None = None,
        provenance_validator: (
            Callable[[VisualSymbolCacheEntry], bool] | None
        ) = None,
    ) -> CacheLookupResult:
        record = self._session.scalar(
            select(VisualSymbolCacheEntryRecord).where(
                VisualSymbolCacheEntryRecord.project_id == project_id,
                VisualSymbolCacheEntryRecord.cache_key == identity.sha256,
            )
        )
        if record is None:
            result = CacheLookupResult(
                hit=False,
                reason_code="cache_miss",
                quarantine=False,
                response=None,
            )
        else:
            try:
                entry = _entry_from_record(record)
                result = evaluate_cache_entry(
                    expected_identity=identity,
                    entry=entry,
                )
                if result.reason_code == "cache_identity_mismatch":
                    result = CacheLookupResult(
                        hit=False,
                        reason_code="cache_provenance_invalid",
                        quarantine=True,
                        response=None,
                        entry=entry,
                    )
                if (
                    result.hit
                    and provenance_validator is not None
                    and provenance_validator(entry) is not True
                ):
                    result = CacheLookupResult(
                        hit=False,
                        reason_code="cache_provenance_invalid",
                        quarantine=True,
                        response=None,
                        entry=entry,
                    )
            except Exception:
                result = CacheLookupResult(
                    hit=False,
                    reason_code="cache_provenance_invalid",
                    quarantine=True,
                    response=None,
                )
        if (consumer is None) != (evidence is None):
            raise ValueError(
                "cache consumer and evidence repository must be paired"
            )
        if consumer is None or evidence is None:
            return result

        from app.candidates.routing_evidence import (
            ESCALATION_ATTEMPT_SCHEMA_VERSION,
            EscalationAttemptEvent,
        )

        attempt = evidence.append_attempt(
            project_id=project_id,
            event=EscalationAttemptEvent(
                schema_version=ESCALATION_ATTEMPT_SCHEMA_VERSION,
                escalation_group_id=consumer.escalation_group_id,
                routing_decision_sha256=(
                    consumer.routing_decision_sha256
                ),
                attempt_index=consumer.attempt_index,
                event_code=result.reason_code,
                cache_entry_id=record.id if record is not None else None,
                provider_request_id=None,
            ),
        )
        return replace(
            result,
            attempt_event_sha256s=(attempt.event_sha256,),
        )
