from __future__ import annotations

import fcntl
import os
import re
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.providers.cycle_authorization import (
    ActiveCycleAuthorization,
    validate_active_cycle_authorization,
    validate_cycle_authorization_for_close,
    validate_empty_cycle_authorization_for_close,
    write_empty_cycle_terminal_from_close_bridge,
    write_terminal_from_close_bridge,
)
from app.providers.pricing import (
    ProviderPricingSnapshot,
    load_pricing_snapshot,
    ocr_submission_cost_cny,
    qwen_reservation_cny,
    qwen_usage_cost_cny,
)
from app.providers.usage_ledger_journal import (
    append_fact_exclusive,
    ensure_private_directory,
    fsync_directory,
    read_fact,
)
from app.providers.usage_ledger_permit import (
    ReservationPermit,
    issue_reservation_permit,
    process_cycle_lock,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FACT_NAME = re.compile(
    r"^(?P<index>[0-9]{6})-(?P<kind>reserved|submission-started|settled)\.json$"
)
_FORBIDDEN_ID = re.compile(
    r"authorization|api[_-]?key|secret|credential|bearer|password|cookie",
    re.IGNORECASE,
)
_RESERVATION_KEYS = {
    "schema_version",
    "fact_type",
    "cycle_id",
    "run_id",
    "project_id",
    "project_order",
    "attempt_index",
    "provider",
    "operation",
    "model",
    "page_index",
    "subject_kind",
    "subject_id",
    "retry_index",
    "crop_expansion_count",
    "reservation_cny",
    "pricing_sha256",
    "content_sha256",
}
_STARTED_KEYS = {
    "schema_version",
    "fact_type",
    "cycle_id",
    "attempt_index",
    "reservation_sha256",
    "provider",
    "operation",
    "started_at",
    "content_sha256",
}
_SETTLED_KEYS = {
    "schema_version",
    "fact_type",
    "cycle_id",
    "attempt_index",
    "submission_started_sha256",
    "state",
    "charged_cny",
    "prompt_tokens",
    "completion_tokens",
    "request_id",
    "request_id_state",
    "settled_at",
    "content_sha256",
}
class ProviderBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class LedgerEntry:
    attempt_index: int
    provider: str
    operation: str
    project_id: str
    page_index: int
    subject_kind: str
    subject_id: str
    retry_index: int
    crop_expansion_count: int
    state: str
    reservation_cny: str
    charged_cny: str


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    committed_total_cny: str
    remaining_cny: str
    reservation_count: int
    reserved_only_count: int
    submission_started_count: int
    unsettled_started_count: int
    settled_count: int
    entries: tuple[LedgerEntry, ...]


@dataclass(frozen=True)
class _ScannedAttempt:
    reservation: dict[str, Any]
    started: dict[str, Any] | None
    settled: dict[str, Any] | None
    entry: LedgerEntry


def _safe_id(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or _SAFE_ID.fullmatch(value) is None
        or _FORBIDDEN_ID.search(value) is not None
    ):
        raise ValueError(f"usage ledger {field} is invalid")
    return value


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("usage ledger amount is invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("usage ledger amount is invalid") from exc
    if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < -6:
        raise ValueError("usage ledger amount is invalid")
    return parsed


def _amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.000001')):.6f}"


class ProviderUsageLedger:
    def __init__(
        self,
        *,
        cycle_id: str,
        journal_path: Path,
        authorization_root: Path,
        project_id: str,
        pricing: ProviderPricingSnapshot,
    ) -> None:
        self._cycle_id = cycle_id
        self._journal_path = journal_path
        self._authorization_root = authorization_root
        self._project_id = project_id
        self._pricing = pricing
        self._process_lock = process_cycle_lock(journal_path)
        self._active_permits: dict[int, ReservationPermit] = {}
        self._consumed_permits: dict[int, ReservationPermit] = {}

    @classmethod
    def open(
        cls,
        *,
        cycle_id: str,
        storage_root: str | Path,
        authorization_root: str | Path,
        project_id: str,
    ) -> ProviderUsageLedger:
        safe_cycle_id = _safe_id(cycle_id, "cycle_id")
        safe_project_id = _safe_id(project_id, "project_id")
        root = Path(storage_root)
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("usage ledger storage root is invalid")
        parent = root / "provider-usage-cycles"
        journal = parent / safe_cycle_id
        ledger = cls(
            cycle_id=safe_cycle_id,
            journal_path=journal,
            authorization_root=Path(authorization_root),
            project_id=safe_project_id,
            pricing=load_pricing_snapshot(),
        )
        with ledger._process_lock:
            ensure_private_directory(parent)
            ensure_private_directory(journal)
            with ledger._os_lock():
                ledger._active_authorization()
                ledger._scan_locked()
        return ledger

    @classmethod
    def open_for_close(
        cls,
        *,
        cycle_id: str,
        storage_root: str | Path,
        authorization_root: str | Path,
        project_id: str,
    ) -> ProviderUsageLedger:
        safe_cycle_id = _safe_id(cycle_id, "cycle_id")
        safe_project_id = _safe_id(project_id, "project_id")
        root = Path(storage_root)
        parent = root / "provider-usage-cycles"
        journal = parent / safe_cycle_id
        ledger = cls(
            cycle_id=safe_cycle_id,
            journal_path=journal,
            authorization_root=Path(authorization_root),
            project_id=safe_project_id,
            pricing=load_pricing_snapshot(),
        )
        with ledger._process_lock:
            ensure_private_directory(parent)
            ensure_private_directory(journal)
            with ledger._os_lock():
                validate_cycle_authorization_for_close(
                    authorization_root=ledger._authorization_root,
                    cycle_id=ledger._cycle_id,
                    project_id=ledger._project_id,
                    pricing_sha256=ledger._pricing.content_sha256,
                )
                ledger._scan_locked(allow_terminal_authorization=True)
        return ledger

    @property
    def journal_ref(self) -> str:
        return f"asset://provider-usage-cycles/{self._cycle_id}/"

    @classmethod
    def close_without_project(
        cls,
        *,
        cycle_id: str,
        storage_root: str | Path,
        authorization_root: str | Path,
        run_id: str,
        status: str,
        quiescence_sha256: str,
    ) -> dict[str, Any]:
        safe_cycle_id = _safe_id(cycle_id, "cycle_id")
        root = Path(storage_root)
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("usage ledger storage root is invalid")
        parent = root / "provider-usage-cycles"
        journal = parent / safe_cycle_id
        ledger = cls(
            cycle_id=safe_cycle_id,
            journal_path=journal,
            authorization_root=Path(authorization_root),
            project_id="unadmitted-cycle",
            pricing=load_pricing_snapshot(),
        )
        with ledger._process_lock:
            ensure_private_directory(parent)
            ensure_private_directory(journal)
            with ledger._os_lock():
                if any(path.name != "ledger.lock" for path in journal.iterdir()):
                    raise ValueError("empty cycle ledger contains Provider state")
                validate_empty_cycle_authorization_for_close(
                    authorization_root=ledger._authorization_root,
                    cycle_id=ledger._cycle_id,
                    run_id=run_id,
                    pricing_sha256=ledger._pricing.content_sha256,
                )
                return write_empty_cycle_terminal_from_close_bridge(
                    authorization_root=authorization_root,
                    cycle_id=safe_cycle_id,
                    run_id=run_id,
                    status=status,
                    quiescence_sha256=quiescence_sha256,
                )

    @contextmanager
    def _os_lock(self) -> Iterator[None]:
        lock_path = self._journal_path / "ledger.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise ValueError("usage ledger lock is invalid") from exc
        try:
            metadata = os.fstat(fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid()
                or metadata.st_gid != os.getgid()
            ):
                raise ValueError("usage ledger lock is invalid")
            os.fsync(fd)
            fsync_directory(self._journal_path)
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _active_authorization(self) -> ActiveCycleAuthorization:
        return validate_active_cycle_authorization(
            authorization_root=self._authorization_root,
            cycle_id=self._cycle_id,
            project_id=self._project_id,
            pricing_sha256=self._pricing.content_sha256,
        )

    def _scan_locked(
        self,
        *,
        allow_terminal_authorization: bool = False,
    ) -> tuple[_ScannedAttempt, ...]:
        grouped: dict[int, dict[str, dict[str, Any]]] = {}
        for path in self._journal_path.iterdir():
            if path.name == "ledger.lock":
                if path.is_symlink() or not path.is_file():
                    raise ValueError("usage ledger journal is invalid")
                continue
            match = _FACT_NAME.fullmatch(path.name)
            if match is None or path.is_symlink() or not path.is_file():
                raise ValueError("usage ledger journal contains unexpected state")
            index = int(match.group("index"))
            kind = match.group("kind")
            grouped.setdefault(index, {})[kind] = read_fact(path)
        if grouped and sorted(grouped) != list(range(1, max(grouped) + 1)):
            raise ValueError("usage ledger journal sequence is invalid")

        attempts: list[_ScannedAttempt] = []
        total = Decimal("0")
        page_counts: dict[tuple[str, str, int], int] = {}
        subject_counts: dict[tuple[str, str, str], int] = {}
        for index in sorted(grouped):
            facts = grouped[index]
            reservation = facts.get("reserved")
            started = facts.get("submission-started")
            settled = facts.get("settled")
            if reservation is None:
                raise ValueError("usage ledger journal reservation is missing")
            self._validate_reservation(
                reservation,
                index,
                allow_terminal_authorization=allow_terminal_authorization,
            )
            if started is not None:
                self._validate_started(started, reservation, index)
            if settled is not None:
                if started is None:
                    raise ValueError("usage ledger settlement has no submission")
                self._validate_settled(settled, reservation, started, index)
            reservation_amount = _decimal(reservation["reservation_cny"])
            charged = (
                _decimal(settled["charged_cny"])
                if settled is not None
                else reservation_amount
            )
            total += charged
            page_key = (
                reservation["project_id"],
                reservation["provider"],
                reservation["page_index"],
            )
            page_counts[page_key] = page_counts.get(page_key, 0) + 1
            if page_counts[page_key] > 16:
                raise ValueError("usage ledger page budget is invalid")
            if reservation["provider"] == "qwen-vl":
                subject_key = (
                    reservation["project_id"],
                    reservation["subject_kind"],
                    reservation["subject_id"],
                )
                subject_counts[subject_key] = subject_counts.get(subject_key, 0) + 1
                if subject_counts[subject_key] > 2:
                    raise ValueError("usage ledger subject budget is invalid")
            state = (
                settled["state"]
                if settled is not None
                else "submission_started_unknown"
                if started is not None
                else "reserved_only"
            )
            attempts.append(
                _ScannedAttempt(
                    reservation=reservation,
                    started=started,
                    settled=settled,
                    entry=LedgerEntry(
                        attempt_index=index,
                        provider=reservation["provider"],
                        operation=reservation["operation"],
                        project_id=reservation["project_id"],
                        page_index=reservation["page_index"],
                        subject_kind=reservation["subject_kind"],
                        subject_id=reservation["subject_id"],
                        retry_index=reservation["retry_index"],
                        crop_expansion_count=reservation[
                            "crop_expansion_count"
                        ],
                        state=state,
                        reservation_cny=_amount(reservation_amount),
                        charged_cny=_amount(charged),
                    ),
                )
            )
        if total > Decimal("50.000000"):
            raise ValueError("usage ledger cycle budget is invalid")
        return tuple(attempts)

    def _validate_reservation(
        self,
        document: dict[str, Any],
        index: int,
        *,
        allow_terminal_authorization: bool = False,
    ) -> None:
        if (
            set(document) != _RESERVATION_KEYS
            or document.get("schema_version") != "provider-usage-reservation/1"
            or document.get("fact_type") != "reserved"
            or document.get("cycle_id") != self._cycle_id
            or document.get("attempt_index") != index
            or document.get("pricing_sha256") != self._pricing.content_sha256
        ):
            raise ValueError("usage ledger reservation is invalid")
        for field in (
            "run_id",
            "project_id",
            "provider",
            "operation",
            "model",
            "subject_kind",
            "subject_id",
        ):
            _safe_id(document.get(field), field)
        for field in (
            "project_order",
            "page_index",
            "retry_index",
            "crop_expansion_count",
        ):
            value = document.get(field)
            minimum = 1 if field == "project_order" else 0
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError("usage ledger reservation is invalid")
        if document["retry_index"] not in {0, 1} or document[
            "crop_expansion_count"
        ] not in {0, 1}:
            raise ValueError("usage ledger reservation is invalid")
        reservation = _decimal(document["reservation_cny"])
        expected = self._reservation_amount(
            document["provider"],
            document["operation"],
        )
        expected_model = (
            self._pricing.qwen.model
            if document["provider"] == "qwen-vl"
            else self._pricing.ocr.operation
        )
        validator = (
            validate_cycle_authorization_for_close
            if allow_terminal_authorization
            else validate_active_cycle_authorization
        )
        active = validator(
            authorization_root=self._authorization_root,
            cycle_id=self._cycle_id,
            project_id=document["project_id"],
            pricing_sha256=self._pricing.content_sha256,
        )
        if (
            reservation != expected
            or document["model"] != expected_model
            or document["project_id"] != active.project_id
            or document["run_id"] != active.run_id
            or document["project_order"] != active.project_order
        ):
            raise ValueError("usage ledger reservation amount is invalid")

    def _validate_started(
        self,
        document: dict[str, Any],
        reservation: dict[str, Any],
        index: int,
    ) -> None:
        if (
            set(document) != _STARTED_KEYS
            or document.get("schema_version") != "provider-usage-submission-started/1"
            or document.get("fact_type") != "submission_started"
            or document.get("cycle_id") != self._cycle_id
            or document.get("attempt_index") != index
            or document.get("reservation_sha256")
            != reservation["content_sha256"]
            or document.get("provider") != reservation["provider"]
            or document.get("operation") != reservation["operation"]
            or not isinstance(document.get("started_at"), str)
        ):
            raise ValueError("usage ledger submission-started fact is invalid")

    def _validate_settled(
        self,
        document: dict[str, Any],
        reservation: dict[str, Any],
        started: dict[str, Any],
        index: int,
    ) -> None:
        if (
            set(document) != _SETTLED_KEYS
            or document.get("schema_version") != "provider-usage-settlement/1"
            or document.get("fact_type") != "settled"
            or document.get("cycle_id") != self._cycle_id
            or document.get("attempt_index") != index
            or document.get("submission_started_sha256")
            != started["content_sha256"]
            or document.get("state")
            not in {"settled_verified", "reserved_unknown"}
            or document.get("request_id_state")
            not in {"absent", "accepted", "rejected"}
            or not isinstance(document.get("settled_at"), str)
        ):
            raise ValueError("usage ledger settlement is invalid")
        request_id = document["request_id"]
        if (request_id is not None) != (document["request_id_state"] == "accepted"):
            raise ValueError("usage ledger settlement request identity is invalid")
        if request_id is not None:
            _safe_id(request_id, "request_id")
        charged = _decimal(document["charged_cny"])
        reservation_amount = _decimal(reservation["reservation_cny"])
        if document["state"] == "reserved_unknown":
            if (
                charged != reservation_amount
                or document["prompt_tokens"] is not None
                or document["completion_tokens"] is not None
            ):
                raise ValueError("usage ledger unknown settlement is invalid")
            return
        if reservation["provider"] == "tencent-ocr":
            expected = ocr_submission_cost_cny(self._pricing)
            if (
                document["prompt_tokens"] is not None
                or document["completion_tokens"] is not None
            ):
                raise ValueError("usage ledger OCR settlement is invalid")
        else:
            expected = qwen_usage_cost_cny(
                self._pricing,
                {
                    "prompt_tokens": document["prompt_tokens"],
                    "completion_tokens": document["completion_tokens"],
                },
            )
        if expected is None or charged != expected or charged > reservation_amount:
            raise ValueError("usage ledger verified settlement is invalid")

    def _reservation_amount(self, provider: str, operation: str) -> Decimal:
        if provider == "qwen-vl" and operation in {
            "review_symbols",
            "review_candidate",
        }:
            return qwen_reservation_cny(self._pricing)
        if provider == "tencent-ocr" and operation == "GeneralAccurateOCR":
            return ocr_submission_cost_cny(self._pricing)
        raise ValueError("usage ledger provider operation is invalid")

    def reserve(
        self,
        *,
        provider: str,
        operation: str,
        page_index: int,
        subject_kind: str,
        subject_id: str,
        retry_index: int,
        crop_expansion_count: int,
    ) -> ReservationPermit:
        safe_provider = _safe_id(provider, "provider")
        safe_operation = _safe_id(operation, "operation")
        safe_subject_kind = _safe_id(subject_kind, "subject_kind")
        safe_subject_id = _safe_id(subject_id, "subject_id")
        if (
            not isinstance(page_index, int)
            or isinstance(page_index, bool)
            or page_index < 0
            or retry_index not in {0, 1}
            or crop_expansion_count not in {0, 1}
        ):
            raise ValueError("usage ledger reservation counters are invalid")
        reservation_amount = self._reservation_amount(
            safe_provider,
            safe_operation,
        )
        with self._process_lock:
            with self._os_lock():
                authorization = self._active_authorization()
                attempts = self._scan_locked()
                page_count = sum(
                    attempt.reservation["project_id"] == self._project_id
                    and attempt.reservation["provider"] == safe_provider
                    and attempt.reservation["page_index"] == page_index
                    for attempt in attempts
                )
                if page_count >= 16:
                    raise ProviderBudgetExceeded("Provider page budget exhausted")
                if safe_provider == "qwen-vl":
                    subject_attempts = [
                        attempt
                        for attempt in attempts
                        if attempt.reservation["project_id"] == self._project_id
                        and attempt.reservation["subject_kind"] == safe_subject_kind
                        and attempt.reservation["subject_id"] == safe_subject_id
                    ]
                    if len(subject_attempts) >= 2 or retry_index != len(
                        subject_attempts
                    ):
                        raise ProviderBudgetExceeded(
                            "Provider subject budget exhausted"
                        )
                elif retry_index != 0:
                    raise ValueError("OCR retry index is invalid")
                committed = sum(
                    (_decimal(attempt.entry.charged_cny) for attempt in attempts),
                    Decimal("0"),
                )
                if committed + reservation_amount > Decimal("50.000000"):
                    raise ProviderBudgetExceeded("Provider cycle budget exhausted")
                index = len(attempts) + 1
                model = (
                    self._pricing.qwen.model
                    if safe_provider == "qwen-vl"
                    else self._pricing.ocr.operation
                )
                reservation = append_fact_exclusive(
                    self._journal_path / f"{index:06d}-reserved.json",
                    {
                        "schema_version": "provider-usage-reservation/1",
                        "fact_type": "reserved",
                        "cycle_id": self._cycle_id,
                        "run_id": authorization.run_id,
                        "project_id": authorization.project_id,
                        "project_order": authorization.project_order,
                        "attempt_index": index,
                        "provider": safe_provider,
                        "operation": safe_operation,
                        "model": model,
                        "page_index": page_index,
                        "subject_kind": safe_subject_kind,
                        "subject_id": safe_subject_id,
                        "retry_index": retry_index,
                        "crop_expansion_count": crop_expansion_count,
                        "reservation_cny": _amount(reservation_amount),
                        "pricing_sha256": self._pricing.content_sha256,
                    },
                )
            permit = issue_reservation_permit(
                ledger=self,
                attempt_index=reservation["attempt_index"],
                provider=safe_provider,
                operation=safe_operation,
            )
            self._active_permits[id(permit)] = permit
            return permit

    def _consume_permit(
        self,
        permit: ReservationPermit,
        *,
        provider: str,
        operation: str,
    ) -> None:
        with self._process_lock:
            try:
                attempt_index = permit._attempt_index
                expected_provider = permit._provider
                expected_operation = permit._operation
                issuing_ledger = permit._ledger
            except AttributeError as exc:
                raise ValueError("reservation permit is invalid") from exc
            registered = self._active_permits.pop(id(permit), None)
            if (
                issuing_ledger is not self
                or registered is not permit
                or provider != expected_provider
                or operation != expected_operation
            ):
                raise ValueError("reservation permit is invalid")
            with self._os_lock():
                self._active_authorization()
                attempts = self._scan_locked()
                if not 1 <= attempt_index <= len(attempts):
                    raise ValueError("reservation permit is invalid")
                attempt = attempts[attempt_index - 1]
                if (
                    attempt.started is not None
                    or attempt.reservation["project_id"] != self._project_id
                    or attempt.reservation["provider"] != provider
                    or attempt.reservation["operation"] != operation
                ):
                    raise ValueError("reservation permit is invalid")
                append_fact_exclusive(
                    self._journal_path
                    / f"{attempt_index:06d}-submission-started.json",
                    {
                        "schema_version": "provider-usage-submission-started/1",
                        "fact_type": "submission_started",
                        "cycle_id": self._cycle_id,
                        "attempt_index": attempt_index,
                        "reservation_sha256": attempt.reservation[
                            "content_sha256"
                        ],
                        "provider": provider,
                        "operation": operation,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            self._consumed_permits[id(permit)] = permit

    def _settle(
        self,
        permit: ReservationPermit,
        *,
        state: str,
        usage: Mapping[str, object] | None,
        request_id: str | None,
        request_id_state: str,
    ) -> LedgerEntry:
        with self._process_lock:
            if self._consumed_permits.get(id(permit)) is not permit:
                raise ValueError("reservation permit is invalid")
            with self._os_lock():
                self._active_authorization()
                attempts = self._scan_locked()
                attempt = attempts[permit._attempt_index - 1]
                if attempt.started is None or attempt.settled is not None:
                    raise ValueError("reservation settlement is invalid")
                reservation = attempt.reservation
                prompt_tokens: int | None = None
                completion_tokens: int | None = None
                if state == "reserved_unknown":
                    charged = _decimal(reservation["reservation_cny"])
                elif reservation["provider"] == "qwen-vl":
                    if usage is None:
                        raise ValueError("verified usage is required")
                    calculated = qwen_usage_cost_cny(self._pricing, usage)
                    if calculated is None:
                        raise ValueError("verified usage is invalid")
                    charged = calculated
                    prompt_tokens = int(usage["prompt_tokens"])
                    completion_tokens = int(usage["completion_tokens"])
                else:
                    if usage is not None:
                        raise ValueError("OCR usage must be null")
                    charged = ocr_submission_cost_cny(self._pricing)
                if request_id_state == "accepted":
                    safe_request_id = _safe_id(request_id, "request_id")
                elif request_id is None and request_id_state in {
                    "absent",
                    "rejected",
                }:
                    safe_request_id = None
                else:
                    raise ValueError("request identity state is invalid")
                append_fact_exclusive(
                    self._journal_path
                    / f"{permit._attempt_index:06d}-settled.json",
                    {
                        "schema_version": "provider-usage-settlement/1",
                        "fact_type": "settled",
                        "cycle_id": self._cycle_id,
                        "attempt_index": permit._attempt_index,
                        "submission_started_sha256": attempt.started[
                            "content_sha256"
                        ],
                        "state": state,
                        "charged_cny": _amount(charged),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "request_id": safe_request_id,
                        "request_id_state": request_id_state,
                        "settled_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                settled = self._scan_locked()[permit._attempt_index - 1].entry
            self._consumed_permits.pop(id(permit), None)
            return settled

    def settle(
        self,
        permit: ReservationPermit,
        *,
        usage: Mapping[str, object] | None,
        request_id: str,
    ) -> LedgerEntry:
        return self._settle(
            permit,
            state="settled_verified",
            usage=usage,
            request_id=request_id,
            request_id_state="accepted",
        )

    def retain_unknown(
        self,
        permit: ReservationPermit,
        *,
        request_id_state: str,
        request_id: str | None = None,
    ) -> LedgerEntry:
        return self._settle(
            permit,
            state="reserved_unknown",
            usage=None,
            request_id=request_id,
            request_id_state=request_id_state,
        )

    def retain_unknown_if_started(
        self,
        permit: ReservationPermit,
        *,
        request_id_state: str,
        request_id: str | None = None,
    ) -> LedgerEntry | None:
        with self._process_lock:
            if self._active_permits.get(id(permit)) is permit:
                self._active_permits.pop(id(permit), None)
                return None
            if self._consumed_permits.get(id(permit)) is not permit:
                raise ValueError("reservation permit is invalid")
            return self.retain_unknown(
                permit,
                request_id_state=request_id_state,
                request_id=request_id,
            )

    def settle_available_usage(
        self,
        permit: ReservationPermit,
        *,
        usage: Mapping[str, object],
        request_id: str,
    ) -> LedgerEntry:
        if qwen_usage_cost_cny(self._pricing, usage) is None:
            return self.retain_unknown(
                permit,
                request_id_state="accepted",
                request_id=request_id,
            )
        return self.settle(
            permit,
            usage=usage,
            request_id=request_id,
        )

    def charged_cny_for_request(self, request_id: str) -> str:
        safe_request_id = _safe_id(request_id, "request_id")
        with self._process_lock:
            with self._os_lock():
                self._active_authorization()
                attempts = self._scan_locked()
        matches = tuple(
            attempt.entry.charged_cny
            for attempt in attempts
            if attempt.settled is not None
            and attempt.settled["request_id"] == safe_request_id
        )
        if len(matches) != 1:
            raise ValueError("usage ledger request identity is invalid")
        return matches[0]

    def snapshot(self) -> ProviderUsageSnapshot:
        with self._process_lock:
            with self._os_lock():
                self._active_authorization()
                attempts = self._scan_locked()
        total = sum(
            (_decimal(attempt.entry.charged_cny) for attempt in attempts),
            Decimal("0"),
        )
        return ProviderUsageSnapshot(
            committed_total_cny=_amount(total),
            remaining_cny=_amount(Decimal("50.000000") - total),
            reservation_count=len(attempts),
            reserved_only_count=sum(
                attempt.started is None for attempt in attempts
            ),
            submission_started_count=sum(
                attempt.started is not None for attempt in attempts
            ),
            unsettled_started_count=sum(
                attempt.started is not None and attempt.settled is None
                for attempt in attempts
            ),
            settled_count=sum(
                attempt.settled is not None for attempt in attempts
            ),
            entries=tuple(attempt.entry for attempt in attempts),
        )

    def close_cycle(
        self,
        *,
        run_id: str,
        status: str,
        quiescence_sha256: str,
    ) -> dict[str, Any]:
        """Close only while holding the stable ledger lock in the one-off bridge."""
        with self._process_lock:
            with self._os_lock():
                authorization = validate_cycle_authorization_for_close(
                    authorization_root=self._authorization_root,
                    cycle_id=self._cycle_id,
                    project_id=self._project_id,
                    pricing_sha256=self._pricing.content_sha256,
                )
                attempts = self._scan_locked(allow_terminal_authorization=True)
                if authorization.run_id != run_id:
                    raise ValueError("usage ledger close run identity is invalid")
                if status == "completed" and any(
                    attempt.started is None or attempt.settled is None
                    for attempt in attempts
                ):
                    raise ValueError("usage ledger incomplete attempt blocks close")
                return write_terminal_from_close_bridge(
                    authorization_root=self._authorization_root,
                    cycle_id=self._cycle_id,
                    run_id=run_id,
                    status=status,
                    quiescence_sha256=quiescence_sha256,
                )
