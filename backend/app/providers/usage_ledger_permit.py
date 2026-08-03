from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


_REGISTRY_GUARD = threading.Lock()
_CYCLE_LOCKS: dict[str, threading.RLock] = {}
_PERMIT_SENTINEL = object()


class ReservationPermit:
    __slots__ = ("_ledger", "_attempt_index", "_provider", "_operation")

    def __init__(
        self,
        sentinel: object = None,
        *,
        ledger: Any = None,
        attempt_index: int = 0,
        provider: str = "",
        operation: str = "",
    ) -> None:
        if sentinel is not _PERMIT_SENTINEL or ledger is None:
            raise TypeError("reservation permit cannot be constructed")
        self._ledger = ledger
        self._attempt_index = attempt_index
        self._provider = provider
        self._operation = operation

    def __copy__(self) -> ReservationPermit:
        raise TypeError("reservation permit cannot be copied")

    def __deepcopy__(self, _memo: dict[int, object]) -> ReservationPermit:
        raise TypeError("reservation permit cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("reservation permit cannot be serialized")

    def consume_for_adapter(self, *, provider: str, operation: str) -> None:
        try:
            ledger = self._ledger
        except AttributeError as exc:
            raise ValueError("reservation permit is invalid") from exc
        ledger._consume_permit(self, provider=provider, operation=operation)


def issue_reservation_permit(
    *,
    ledger: Any,
    attempt_index: int,
    provider: str,
    operation: str,
) -> ReservationPermit:
    return ReservationPermit(
        _PERMIT_SENTINEL,
        ledger=ledger,
        attempt_index=attempt_index,
        provider=provider,
        operation=operation,
    )


def process_cycle_lock(path: Path) -> threading.RLock:
    key = str(path.absolute())
    with _REGISTRY_GUARD:
        lock = _CYCLE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _CYCLE_LOCKS[key] = lock
        return lock
