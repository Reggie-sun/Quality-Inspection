from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from app.storage.local import LocalFileStorage, StoredWrite


FORBIDDEN_KEY_RE = re.compile(
    r"authorization|api[_-]?key|secret|base64",
    re.IGNORECASE,
)
RECORD_FIELDS = {
    "provider",
    "request_id",
    "model",
    "prompt_version",
    "schema_version",
    "duration_ms",
    "retry_count",
    "input_image_count",
    "estimated_cost",
    "logical_task_reused",
    "request_ref",
    "response_ref",
}
SAFE_REF_PREFIXES = ("asset://", "fixture://sanitized/")
BASE64_SEGMENT_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _is_safe_resource_ref(value: str) -> bool:
    prefix = next(
        (candidate for candidate in SAFE_REF_PREFIXES if value.startswith(candidate)),
        None,
    )
    if prefix is None:
        return False
    relative = value.removeprefix(prefix)
    path = PurePosixPath(relative)
    raw_parts = relative.split("/")
    return (
        bool(relative)
        and not path.is_absolute()
        and "\\" not in relative
        and all(
            part not in {"", ".", ".."}
            and part == part.strip()
            and not any(character.isspace() for character in part)
            and not (len(part) >= 96 and BASE64_SEGMENT_RE.fullmatch(part))
            for part in raw_parts
        )
    )


@dataclass(frozen=True)
class ProviderCallRecord:
    provider: str
    request_id: str
    model: str
    prompt_version: str
    schema_version: str
    duration_ms: int
    retry_count: int
    input_image_count: int
    estimated_cost: float | None
    logical_task_reused: bool
    request_ref: str
    response_ref: str

    def __post_init__(self) -> None:
        string_values = (
            self.provider,
            self.request_id,
            self.model,
            self.prompt_version,
            self.schema_version,
            self.request_ref,
            self.response_ref,
        )
        if any(
            not isinstance(value, str) or not value.strip()
            for value in string_values
        ):
            raise ValueError("Provider call record string fields must be non-empty")
        if not _is_safe_resource_ref(self.request_ref) or not _is_safe_resource_ref(
            self.response_ref
        ):
            raise ValueError("Provider call resource refs must use one safe ref scheme")
        counters = (self.duration_ms, self.retry_count, self.input_image_count)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counters
        ):
            raise ValueError("Provider call counters must be non-negative integers")
        if self.estimated_cost is not None and (
            isinstance(self.estimated_cost, bool)
            or not isinstance(self.estimated_cost, (int, float))
            or not math.isfinite(float(self.estimated_cost))
            or self.estimated_cost < 0
        ):
            raise ValueError("estimated_cost must be null or non-negative")
        if not isinstance(self.logical_task_reused, bool):
            raise ValueError("logical_task_reused must be boolean")


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if FORBIDDEN_KEY_RE.search(str(key)):
                raise ValueError(f"forbidden Provider call record key: {key}")
            _reject_forbidden_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_keys(nested)


def serialize_call_record(
    record: ProviderCallRecord | Mapping[str, Any],
) -> bytes:
    payload = asdict(record) if isinstance(record, ProviderCallRecord) else dict(record)
    _reject_forbidden_keys(payload)
    if set(payload) != RECORD_FIELDS:
        raise ValueError("Provider call record fields do not match the redacted allowlist")
    try:
        validated = (
            record
            if isinstance(record, ProviderCallRecord)
            else ProviderCallRecord(**payload)
        )
    except TypeError as exc:
        raise ValueError("Provider call record fields are invalid") from exc
    return json.dumps(
        asdict(validated),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def persist_call_record(
    storage: LocalFileStorage,
    relative_path: str,
    record: ProviderCallRecord,
) -> StoredWrite:
    content = serialize_call_record(record)
    return storage.write_verified(
        relative_path,
        content,
        hashlib.sha256(content).hexdigest(),
    )
