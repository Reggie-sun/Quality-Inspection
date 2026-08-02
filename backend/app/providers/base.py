from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol


LOCALIZED_PROVIDER_FAILURE_CATEGORIES = frozenset(
    {"timeout", "transport", "schema", "unavailable"}
)

ProviderFailureCategory = Literal[
    "timeout",
    "transport",
    "schema",
    "authentication",
    "request_rejected",
    "rate_limited",
    "service_failure",
    "metadata_invalid",
    "unclassified",
]
ProviderFailureOrigin = Literal[
    "sdk_timeout",
    "sdk_connection",
    "sdk_http_status",
    "response_metadata",
    "response_schema",
    "provider_boundary",
]
ProviderRequestIdState = Literal["absent", "accepted", "rejected"]

_SAFE_PROVIDER_FAILURE_REQUEST_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)
_FORBIDDEN_PROVIDER_FAILURE_REQUEST_ID = re.compile(
    r"authorization|api[_-]?key|secret|credential|bearer|"
    r"token|password|passwd|cookie|session",
    re.IGNORECASE,
)
_FACT_ORIGINS_BY_CATEGORY = {
    "timeout": {"sdk_timeout", "sdk_http_status"},
    "transport": {"sdk_connection"},
    "schema": {"response_schema"},
    "authentication": {"sdk_http_status"},
    "request_rejected": {"sdk_http_status"},
    "rate_limited": {"sdk_http_status"},
    "service_failure": {"sdk_http_status"},
    "metadata_invalid": {"response_metadata"},
    "unclassified": {"provider_boundary"},
}


def provider_failure_category_for_http_status(
    status: int,
) -> ProviderFailureCategory:
    if status == 408:
        return "timeout"
    if status in {401, 403}:
        return "authentication"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "service_failure"
    return "request_rejected"


def classify_provider_failure_request_id(
    value: object,
) -> tuple[str | None, ProviderRequestIdState]:
    if value is None:
        return None, "absent"
    if (
        isinstance(value, str)
        and _SAFE_PROVIDER_FAILURE_REQUEST_ID.fullmatch(value)
        and not _FORBIDDEN_PROVIDER_FAILURE_REQUEST_ID.search(value)
    ):
        return value, "accepted"
    return None, "rejected"


@dataclass(frozen=True)
class ProviderFailureFact:
    category: ProviderFailureCategory
    origin: ProviderFailureOrigin
    http_status: int | None
    provider_request_id: str | None
    request_id_state: ProviderRequestIdState

    def __post_init__(self) -> None:
        if (
            self.category not in _FACT_ORIGINS_BY_CATEGORY
            or self.origin not in _FACT_ORIGINS_BY_CATEGORY[self.category]
            or self.request_id_state not in {"absent", "accepted", "rejected"}
        ):
            raise ValueError("Provider failure fact is invalid")
        if self.origin == "sdk_http_status":
            if (
                not isinstance(self.http_status, int)
                or isinstance(self.http_status, bool)
                or not 400 <= self.http_status <= 599
                or self.category
                != provider_failure_category_for_http_status(self.http_status)
            ):
                raise ValueError("Provider failure fact is invalid")
        elif self.http_status is not None:
            raise ValueError("Provider failure fact is invalid")
        if (self.provider_request_id is not None) != (
            self.request_id_state == "accepted"
        ):
            raise ValueError("Provider failure fact is invalid")
        if self.request_id_state == "accepted" and (
            classify_provider_failure_request_id(self.provider_request_id)
            != (self.provider_request_id, "accepted")
        ):
            raise ValueError("Provider failure fact is invalid")


class ClassifiedProviderFailure(RuntimeError):
    def __init__(self, fact: ProviderFailureFact) -> None:
        if not isinstance(fact, ProviderFailureFact):
            raise ValueError("Provider failure fact is invalid")
        super().__init__("visual symbol Provider request failed")
        self.fact = fact


class LocalizedProviderFailure(RuntimeError):
    def __init__(self, failure_category: str) -> None:
        if failure_category not in LOCALIZED_PROVIDER_FAILURE_CATEGORIES:
            raise ValueError("localized Provider failure category is invalid")
        super().__init__("visual symbol Provider request failed")
        self.failure_category = failure_category


@dataclass(frozen=True)
class OcrObservation:
    raw_text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    angle: float


@dataclass(frozen=True)
class OcrResult:
    request_id: str
    observations: tuple[OcrObservation, ...]


@dataclass(frozen=True)
class VisionResult:
    request_id: str
    payload: dict[str, Any]
    usage: dict[str, int]


class OcrProvider(Protocol):
    def recognize_png(self, image: bytes) -> OcrResult: ...


class VisionLlmProvider(Protocol):
    def review_candidate(self, image: bytes, prompt: str) -> VisionResult: ...

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult: ...
