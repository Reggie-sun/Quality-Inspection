from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import jsonschema
import pymupdf

from app.pdf.coordinates import BBox


SCHEMA_PATH = (
    Path(__file__).parents[1] / "providers/visual_symbol_review.schema.json"
)
VISUAL_PROMPT_VERSION = "visual-symbol-prompt/1"
VISUAL_SCHEMA_VERSION = "visual-symbol-review/1"
VISUAL_ADAPTER_VERSION = "qwen-openai-compatible/1"
VISUAL_PROPOSAL_VERSION = "visual-observation/1"
VISUAL_CACHE_SCHEMA_VERSION = "visual-symbol-advisor-cache/1"
VISUAL_REQUEST_SCHEMA_VERSION = "visual-symbol-call-request/1"
VISUAL_CACHE_FIELDS = {
    "cache_schema_version",
    "provider",
    "request_id",
    "identity",
    "response",
    "response_sha256",
    "usage",
}
VISUAL_IDENTITY_FIELDS = {
    "source_sha256",
    "visual_observation_ids",
    "crop_bbox_pdf",
    "crop_sha256",
    "model",
    "prompt_version",
    "schema_version",
    "adapter_version",
    "proposal_version",
    "pymupdf_version",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_USAGE_COUNTER = re.compile(r"^[a-z][a-z0-9_]{0,31}_tokens$")
_FORBIDDEN_EVIDENCE_KEY = re.compile(
    r"authorization|api[_-]?key|secret|credential|bearer",
    re.IGNORECASE,
)

SymbolKind = Literal[
    "diameter",
    "depth",
    "counterbore",
    "surface_roughness",
    "gdt_parallelism",
    "gdt_perpendicularity",
    "gdt_flatness",
    "datum_reference",
    "revision_marker",
]


@dataclass(frozen=True)
class ValidatedSymbolDetection:
    visual_observation_id: str
    symbol_kind: SymbolKind
    bbox_pdf: BBox
    associated_text_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class RejectedSymbolDetection:
    visual_observation_id: str
    rejection_code: Literal[
        "visual_bbox_invalid",
        "visual_source_mismatch",
        "visual_duplicate_detection",
    ]


class VisualSymbolSchemaError(ValueError):
    pass


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def visual_cache_identity(
    *,
    source_sha256: str,
    visual_observation_ids: Sequence[str],
    crop_bbox_pdf: BBox,
    crop_sha256: str,
    model: str,
    prompt_version: str = VISUAL_PROMPT_VERSION,
    schema_version: str = VISUAL_SCHEMA_VERSION,
    adapter_version: str = VISUAL_ADAPTER_VERSION,
    proposal_version: str = VISUAL_PROPOSAL_VERSION,
    pymupdf_version: str = pymupdf.VersionBind,
) -> dict[str, object]:
    values = tuple(float(value) for value in crop_bbox_pdf)
    ids = tuple(visual_observation_ids)
    if (
        _SHA256_RE.fullmatch(source_sha256) is None
        or _SHA256_RE.fullmatch(crop_sha256) is None
        or len(values) != 4
        or not all(math.isfinite(value) for value in values)
        or values[2] <= values[0]
        or values[3] <= values[1]
        or not ids
        or len(set(ids)) != len(ids)
        or any(not isinstance(value, str) or not value.strip() for value in ids)
        or any(
            not isinstance(value, str) or not value.strip()
            for value in (
                model,
                prompt_version,
                schema_version,
                adapter_version,
                proposal_version,
                pymupdf_version,
            )
        )
    ):
        raise ValueError("visual symbol cache identity is invalid")
    return {
        "source_sha256": source_sha256,
        "visual_observation_ids": list(ids),
        "crop_bbox_pdf": list(values),
        "crop_sha256": crop_sha256,
        "model": model,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "adapter_version": adapter_version,
        "proposal_version": proposal_version,
        "pymupdf_version": pymupdf_version,
    }


def visual_cache_key(**identity_arguments: Any) -> str:
    identity = visual_cache_identity(**identity_arguments)
    return hashlib.sha256(_json_bytes(identity)).hexdigest()


def visual_review_prompt(visual_observation_ids: Sequence[str]) -> str:
    return json.dumps(
        {
            "task": "review_local_engineering_drawing_symbol_contexts",
            "prompt_version": VISUAL_PROMPT_VERSION,
            "schema_version": VISUAL_SCHEMA_VERSION,
            "visual_observation_ids": list(visual_observation_ids),
            "constraints": [
                "use_only_listed_visual_observation_ids",
                "return_frozen_schema_only",
                "requires_confirmation_must_be_true",
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def build_visual_cache_envelope(
    *,
    request_id: str,
    identity: Mapping[str, Any],
    response: Mapping[str, Any],
    usage: Mapping[str, int],
) -> dict[str, Any]:
    validated_response = parse_visual_symbol_json(response)
    normalized_usage = {
        str(key): value
        for key, value in usage.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    if (
        not isinstance(request_id, str)
        or not request_id.strip()
        or set(identity) != VISUAL_IDENTITY_FIELDS
        or len(normalized_usage) != len(usage)
    ):
        raise ValueError("visual symbol cache envelope is invalid")
    return {
        "cache_schema_version": VISUAL_CACHE_SCHEMA_VERSION,
        "provider": "qwen-vl",
        "request_id": request_id,
        "identity": dict(identity),
        "response": validated_response,
        "response_sha256": hashlib.sha256(
            _json_bytes(validated_response)
        ).hexdigest(),
        "usage": normalized_usage,
    }


def build_visual_failure_envelope() -> dict[str, str]:
    return {
        "schema_version": "visual-symbol-call-failure/1",
        "error_code": "visual_schema_invalid",
    }


def build_visual_request_evidence(
    *,
    crop_ref: str,
    crop_sha256: str,
    usage: Mapping[str, int],
) -> dict[str, Any]:
    if (
        not isinstance(crop_ref, str)
        or not crop_ref.startswith("asset://")
        or any(character.isspace() for character in crop_ref)
        or "\\" in crop_ref
        or "/../" in crop_ref
        or not isinstance(crop_sha256, str)
        or _SHA256_RE.fullmatch(crop_sha256) is None
        or not isinstance(usage, Mapping)
        or any(
            not isinstance(key, str)
            or _SAFE_USAGE_COUNTER.fullmatch(key) is None
            or _FORBIDDEN_EVIDENCE_KEY.search(key) is not None
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in usage.items()
        )
    ):
        raise ValueError("visual symbol request evidence is invalid")
    return {
        "schema_version": VISUAL_REQUEST_SCHEMA_VERSION,
        "crop_ref": crop_ref,
        "crop_sha256": crop_sha256,
        "usage": dict(usage),
    }


def parse_visual_request_evidence(
    payload: Mapping[str, Any],
    *,
    expected_crop_ref: str,
    expected_crop_sha256: str,
    expected_usage: Mapping[str, int],
) -> dict[str, Any]:
    try:
        rebuilt = build_visual_request_evidence(
            crop_ref=payload["crop_ref"],
            crop_sha256=payload["crop_sha256"],
            usage=payload["usage"],
        )
        if (
            set(payload)
            != {
                "schema_version",
                "crop_ref",
                "crop_sha256",
                "usage",
            }
            or payload["schema_version"] != VISUAL_REQUEST_SCHEMA_VERSION
            or rebuilt != dict(payload)
            or payload["crop_ref"] != expected_crop_ref
            or payload["crop_sha256"] != expected_crop_sha256
            or payload["usage"] != dict(expected_usage)
        ):
            raise ValueError("request evidence mismatch")
    except (KeyError, TypeError, ValueError):
        raise ValueError("visual symbol request evidence is invalid") from None
    return rebuilt


def canonical_visual_response_bytes(
    response: Mapping[str, Any],
) -> bytes:
    return _json_bytes(parse_visual_symbol_json(response))


def parse_visual_cache_envelope(
    payload: Mapping[str, Any],
    *,
    expected_identity: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, int]]:
    try:
        if (
            set(payload) != VISUAL_CACHE_FIELDS
            or payload["cache_schema_version"] != VISUAL_CACHE_SCHEMA_VERSION
            or payload["provider"] != "qwen-vl"
            or not isinstance(payload["request_id"], str)
            or not payload["request_id"].strip()
            or not isinstance(payload["identity"], Mapping)
            or set(payload["identity"]) != VISUAL_IDENTITY_FIELDS
            or dict(payload["identity"]) != dict(expected_identity)
            or not isinstance(payload["response"], Mapping)
            or not isinstance(payload["response_sha256"], str)
            or payload["response_sha256"]
            != hashlib.sha256(_json_bytes(payload["response"])).hexdigest()
            or not isinstance(payload["usage"], Mapping)
        ):
            raise ValueError("cache values")
        response = parse_visual_symbol_json(payload["response"])
        usage = {
            str(key): value
            for key, value in payload["usage"].items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        if len(usage) != len(payload["usage"]):
            raise ValueError("cache usage")
    except (KeyError, TypeError, ValueError, VisualSymbolSchemaError):
        raise ValueError("visual symbol cache envelope is invalid") from None
    return payload["request_id"], response, usage


def parse_visual_symbol_json(
    content: str | Mapping[str, Any],
) -> dict[str, Any]:
    payload: Any = None
    invalid = False
    try:
        payload = json.loads(content) if isinstance(content, str) else dict(content)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(payload)
        if any(
            not math.isfinite(float(value))
            for detection in payload["detections"]
            for value in detection["bbox_normalized"]
        ):
            raise ValueError("non-finite bbox")
    except (
        json.JSONDecodeError,
        jsonschema.SchemaError,
        jsonschema.ValidationError,
        OSError,
        TypeError,
        ValueError,
    ):
        invalid = True
    if invalid or not isinstance(payload, dict):
        raise VisualSymbolSchemaError(
            "visual symbol response violates frozen schema"
        )
    return payload


def _page_bbox(normalized: Sequence[float], crop: BBox) -> BBox:
    width = crop[2] - crop[0]
    height = crop[3] - crop[1]
    return (
        crop[0] + float(normalized[0]) * width,
        crop[1] + float(normalized[1]) * height,
        crop[0] + float(normalized[2]) * width,
        crop[1] + float(normalized[3]) * height,
    )


def validate_symbol_detections(
    payload: Mapping[str, Any],
    *,
    visual_observation_ids: Sequence[str],
    text_allowlists: Mapping[str, Collection[str]],
    crop_bbox_pdf: BBox,
) -> tuple[
    tuple[ValidatedSymbolDetection, ...],
    tuple[RejectedSymbolDetection, ...],
]:
    """Convert one schema-valid Provider response into stable typed decisions."""
    current_ids = frozenset(visual_observation_ids)
    detections = payload.get("detections")
    if not isinstance(detections, list):
        raise VisualSymbolSchemaError(
            "visual symbol response violates frozen schema"
        )
    counts = Counter(
        str(item["visual_observation_id"])
        for item in detections
        if isinstance(item, Mapping)
    )
    accepted: list[ValidatedSymbolDetection] = []
    rejected: list[tuple[float, float, int, RejectedSymbolDetection]] = []
    seen: set[tuple[str, str, tuple[float, ...]]] = set()

    for detection in detections:
        visual_id = str(detection["visual_observation_id"])
        normalized = tuple(float(value) for value in detection["bbox_normalized"])
        bbox_pdf = _page_bbox(normalized, crop_bbox_pdf)
        kind = str(detection["symbol_kind"])
        associated_ids = tuple(
            str(value)
            for value in detection["associated_text_observation_ids"]
        )
        if (
            normalized[2] <= normalized[0]
            or normalized[3] <= normalized[1]
            or crop_bbox_pdf[2] <= crop_bbox_pdf[0]
            or crop_bbox_pdf[3] <= crop_bbox_pdf[1]
            or bbox_pdf[0] < crop_bbox_pdf[0]
            or bbox_pdf[1] < crop_bbox_pdf[1]
            or bbox_pdf[2] > crop_bbox_pdf[2]
            or bbox_pdf[3] > crop_bbox_pdf[3]
        ):
            rejected.append(
                (
                    bbox_pdf[1],
                    bbox_pdf[0],
                    len(rejected),
                    RejectedSymbolDetection(
                        visual_id,
                        "visual_bbox_invalid",
                    ),
                )
            )
            continue
        if (
            visual_id not in current_ids
            or counts[visual_id] > 4
            or not set(associated_ids).issubset(
                set(text_allowlists.get(visual_id, ()))
            )
        ):
            rejected.append(
                (
                    bbox_pdf[1],
                    bbox_pdf[0],
                    len(rejected),
                    RejectedSymbolDetection(
                        visual_id,
                        "visual_source_mismatch",
                    ),
                )
            )
            continue
        duplicate_key = (
            visual_id,
            kind,
            tuple(round(value, 3) for value in normalized),
        )
        if duplicate_key in seen:
            rejected.append(
                (
                    bbox_pdf[1],
                    bbox_pdf[0],
                    len(rejected),
                    RejectedSymbolDetection(
                        visual_id,
                        "visual_duplicate_detection",
                    ),
                )
            )
            continue
        seen.add(duplicate_key)
        accepted.append(
            ValidatedSymbolDetection(
                visual_observation_id=visual_id,
                symbol_kind=cast(SymbolKind, kind),
                bbox_pdf=bbox_pdf,
                associated_text_observation_ids=associated_ids,
            )
        )

    accepted.sort(
        key=lambda item: (
            item.bbox_pdf[1],
            item.bbox_pdf[0],
            item.visual_observation_id,
            item.symbol_kind,
        )
    )
    rejected.sort(key=lambda item: item[:3])
    return tuple(accepted), tuple(item[3] for item in rejected)
