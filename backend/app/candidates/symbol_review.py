from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, cast, get_args

import jsonschema
import pymupdf

from app.candidates.coverage import Disposition
from app.candidates.grouping import group_observations
from app.candidates.parser import NUMBER, normalize_text, parse_annotation
from app.candidates.schemas import Candidate, stable_candidate_id
from app.pdf.coordinates import BBox
from app.pdf.schemas import PageInventory, TextObservation, VisualObservation
from app.pdf.visual_observations import (
    PROPOSAL_RULE_VERSION,
    VisualBatch,
    VisualGeometryContext,
    VisualObservationBlockingError,
    pack_visual_batches,
)


SCHEMA_PATH = (
    Path(__file__).parents[1] / "providers/visual_symbol_review.schema.json"
)
VISUAL_PROMPT_VERSION = "visual-symbol-prompt/4"
VISUAL_SCHEMA_VERSION = "visual-symbol-review/2"
VISUAL_ADAPTER_VERSION = "qwen-openai-compatible/5"
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
VISUAL_SCHEMA_DIAGNOSTIC_VERSION = "visual-symbol-schema-diagnostic/1"
_VISUAL_SCHEMA_DIAGNOSTIC_FIELDS = {
    "schema_version",
    "validator",
    "instance_path",
    "schema_path",
    "instance_type",
    "required_member",
    "schema_sha256",
}
_SAFE_SCHEMA_VALIDATORS = frozenset(
    {
        "additionalProperties",
        "const",
        "enum",
        "maxItems",
        "maximum",
        "minItems",
        "minimum",
        "minLength",
        "pattern",
        "required",
        "type",
        "uniqueItems",
    }
)
_SAFE_INSTANCE_PATH_MEMBERS = frozenset(
    {
        "associated_text_observation_ids",
        "bbox_normalized",
        "confidence_signal",
        "detections",
        "schema_version",
        "symbol_kind",
        "visual_observation_id",
    }
)
_SAFE_SCHEMA_PATH_MEMBERS = frozenset(
    {
        "additionalProperties",
        "associated_text_observation_ids",
        "bbox_normalized",
        "confidence_signal",
        "const",
        "detections",
        "enum",
        "items",
        "maxItems",
        "maximum",
        "minItems",
        "minimum",
        "minLength",
        "pattern",
        "properties",
        "required",
        "schema_version",
        "symbol_kind",
        "type",
        "uniqueItems",
        "visual_observation_id",
    }
)
_SAFE_INSTANCE_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
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
VisualSymbolParserFailureStage = Literal[
    "json_invalid",
    "schema_invalid",
    "local_schema_invalid",
]
VisualSymbolFailureStage = Literal[
    "message_shape_invalid",
    "message_content_invalid",
    "tool_calls_shape_invalid",
    "tool_call_count_invalid",
    "tool_call_shape_invalid",
    "tool_call_type_invalid",
    "tool_name_invalid",
    "tool_arguments_type_invalid",
    "tool_arguments_json_invalid",
    "tool_arguments_schema_invalid",
    "local_schema_invalid",
]
VISUAL_SYMBOL_FAILURE_STAGES = frozenset(
    get_args(VisualSymbolFailureStage)
)


@dataclass(frozen=True)
class ValidatedSymbolDetection:
    visual_observation_id: str
    symbol_kind: SymbolKind
    bbox_pdf: BBox
    associated_text_observation_ids: tuple[str, ...]
    confidence_signal: float


@dataclass(frozen=True)
class RejectedSymbolDetection:
    visual_observation_id: str
    rejection_code: Literal[
        "visual_bbox_invalid",
        "visual_source_mismatch",
        "visual_duplicate_detection",
    ]


@dataclass(frozen=True)
class VisualReviewDecision:
    observation_id: str
    disposition: Disposition
    source_location_ids: tuple[str, ...]
    coordinates: BBox
    candidate_id: str | None
    existing_candidate_index: int | None
    candidate_envelope: dict[str, Any] | None
    requires_confirmation: bool
    symbol_kinds: tuple[SymbolKind, ...]
    rejection_code: str | None
    confidence_signal: float | None = None


@dataclass(frozen=True)
class DeduplicatedSymbolGroup:
    detection: ValidatedSymbolDetection
    visual_observation_ids: tuple[str, ...]


class VisualSymbolSchemaError(ValueError):
    def __init__(
        self,
        *,
        failure_stage: VisualSymbolParserFailureStage,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__("visual symbol response violates frozen schema")
        self.failure_stage = failure_stage
        self.diagnostic = (
            None
            if diagnostic is None
            else validate_visual_schema_diagnostic(diagnostic)
        )


def _safe_json_pointer(
    path: Sequence[Any],
    *,
    safe_members: Collection[str],
) -> str | None:
    encoded: list[str] = []
    for member in path:
        if type(member) is int and 0 <= member <= 4096:
            encoded.append(str(member))
        elif isinstance(member, str) and member in safe_members:
            encoded.append(member.replace("~", "~0").replace("/", "~1"))
        else:
            return None
    return "".join(f"/{member}" for member in encoded)


def _is_safe_json_pointer(
    value: Any,
    *,
    safe_members: Collection[str],
) -> bool:
    if not isinstance(value, str):
        return False
    if value == "":
        return True
    if not value.startswith("/"):
        return False
    for member in value[1:].split("/"):
        if member in safe_members:
            continue
        if (
            member.isascii()
            and member.isdecimal()
            and (member == "0" or not member.startswith("0"))
            and int(member) <= 4096
        ):
            continue
        return False
    return True


def _safe_instance_type(value: Any) -> str | None:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return None


def validate_visual_schema_diagnostic(
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    document = dict(diagnostic)
    validator = document.get("validator")
    required_member = document.get("required_member")
    schema_sha256 = document.get("schema_sha256")
    if (
        set(document) != _VISUAL_SCHEMA_DIAGNOSTIC_FIELDS
        or document.get("schema_version") != VISUAL_SCHEMA_DIAGNOSTIC_VERSION
        or validator not in _SAFE_SCHEMA_VALIDATORS
        or not _is_safe_json_pointer(
            document.get("instance_path"),
            safe_members=_SAFE_INSTANCE_PATH_MEMBERS,
        )
        or not _is_safe_json_pointer(
            document.get("schema_path"),
            safe_members=_SAFE_SCHEMA_PATH_MEMBERS,
        )
        or document.get("instance_type") not in _SAFE_INSTANCE_TYPES
        or (
            required_member is not None
            and (
                validator != "required"
                or required_member not in _SAFE_INSTANCE_PATH_MEMBERS
            )
        )
        or not isinstance(schema_sha256, str)
        or _SHA256_RE.fullmatch(schema_sha256) is None
    ):
        raise ValueError("visual symbol schema diagnostic is invalid") from None
    return document


def _visual_schema_diagnostic(
    error: jsonschema.ValidationError,
    *,
    schema_sha256: str,
) -> dict[str, Any] | None:
    validator = error.validator
    instance_path = _safe_json_pointer(
        tuple(error.absolute_path),
        safe_members=_SAFE_INSTANCE_PATH_MEMBERS,
    )
    schema_path = _safe_json_pointer(
        tuple(error.absolute_schema_path),
        safe_members=_SAFE_SCHEMA_PATH_MEMBERS,
    )
    instance_type = _safe_instance_type(error.instance)
    if (
        not isinstance(validator, str)
        or validator not in _SAFE_SCHEMA_VALIDATORS
        or instance_path is None
        or schema_path is None
        or instance_type is None
    ):
        return None
    required_member = None
    if (
        validator == "required"
        and isinstance(error.validator_value, list)
        and isinstance(error.instance, Mapping)
    ):
        missing = [
            member
            for member in error.validator_value
            if member in _SAFE_INSTANCE_PATH_MEMBERS
            and member not in error.instance
        ]
        if len(missing) == 1:
            required_member = missing[0]
    return validate_visual_schema_diagnostic(
        {
            "schema_version": VISUAL_SCHEMA_DIAGNOSTIC_VERSION,
            "validator": validator,
            "instance_path": instance_path,
            "schema_path": schema_path,
            "instance_type": instance_type,
            "required_member": required_member,
            "schema_sha256": schema_sha256,
        }
    )


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
    proposal_version: str = PROPOSAL_RULE_VERSION,
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


def _prompt_context_bbox(
    bbox_pdf: BBox,
    crop_bbox_pdf: BBox,
) -> tuple[float, float, float, float]:
    crop_width = crop_bbox_pdf[2] - crop_bbox_pdf[0]
    crop_height = crop_bbox_pdf[3] - crop_bbox_pdf[1]
    if (
        crop_width <= 0
        or crop_height <= 0
        or bbox_pdf[2] <= bbox_pdf[0]
        or bbox_pdf[3] <= bbox_pdf[1]
        or not all(math.isfinite(value) for value in (*bbox_pdf, *crop_bbox_pdf))
    ):
        raise ValueError("visual symbol prompt context is invalid")
    values = (
        (bbox_pdf[0] - crop_bbox_pdf[0]) / crop_width,
        (bbox_pdf[1] - crop_bbox_pdf[1]) / crop_height,
        (bbox_pdf[2] - crop_bbox_pdf[0]) / crop_width,
        (bbox_pdf[3] - crop_bbox_pdf[1]) / crop_height,
    )
    if (
        values[0] < 0
        or values[1] < 0
        or values[2] > 1
        or values[3] > 1
    ):
        raise ValueError("visual symbol prompt context is invalid")
    return values


def visual_review_prompt(
    visual_observations: Sequence[VisualObservation],
    *,
    text_observations: Mapping[str, TextObservation],
    crop_bbox_pdf: BBox,
) -> str:
    visual_ids = tuple(
        observation.observation_id for observation in visual_observations
    )
    if (
        not visual_ids
        or len(set(visual_ids)) != len(visual_ids)
        or any(not identity.strip() for identity in visual_ids)
    ):
        raise ValueError("visual symbol prompt context is invalid")
    contexts: list[dict[str, Any]] = []
    for observation in visual_observations:
        associated_ids = observation.associated_text_observation_ids
        if (
            not associated_ids
            or len(set(associated_ids)) != len(associated_ids)
        ):
            raise ValueError("visual symbol prompt context is invalid")
        nearby_texts: list[dict[str, str]] = []
        for identity in associated_ids:
            text = text_observations.get(identity)
            if (
                text is None
                or text.page_index != observation.page_index
                or text.observation_level not in {"line", "span"}
                or not isinstance(text.raw_text, str)
                or not text.raw_text.strip()
            ):
                raise ValueError("visual symbol prompt context is invalid")
            nearby_texts.append(
                {
                    "observation_id": text.observation_id,
                    "observation_level": text.observation_level,
                    "raw_text": text.raw_text,
                }
            )
        contexts.append(
            {
                "visual_observation_id": observation.observation_id,
                "context_bbox_normalized": list(
                    _prompt_context_bbox(
                        observation.bbox_pdf,
                        crop_bbox_pdf,
                    )
                ),
                "associated_text_allowlist": nearby_texts,
            }
        )
    response_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return json.dumps(
        {
            "task": "review_local_engineering_drawing_symbol_contexts",
            "prompt_version": VISUAL_PROMPT_VERSION,
            "schema_version": VISUAL_SCHEMA_VERSION,
            "visual_observation_ids": list(visual_ids),
            "visual_contexts": contexts,
            "symbol_kind_guide": {
                "diameter": "Φ/∅/⌀ beside a size value",
                "depth": "depth symbol beside a depth value",
                "counterbore": (
                    "counterbore symbol used with diameter and depth"
                ),
                "surface_roughness": (
                    "surface texture symbol beside a roughness value"
                ),
                "gdt_parallelism": (
                    "parallelism symbol in a feature-control frame"
                ),
                "gdt_perpendicularity": (
                    "perpendicularity symbol in a feature-control frame"
                ),
                "gdt_flatness": "flatness symbol in a feature-control frame",
                "datum_reference": (
                    "boxed datum letter with its datum pointer"
                ),
                "revision_marker": (
                    "closed triangle containing a revision token"
                ),
            },
            "detection_reporting_contract": [
                "Judge every visual context independently.",
                (
                    "For each visible component whose kind is in "
                    "symbol_kind_guide, emit one separate detection."
                ),
                (
                    "If one context contains multiple components, emit "
                    "multiple detections and reuse that context's "
                    "visual_observation_id for every component."
                ),
                (
                    "Never substitute a kind seen only in a neighboring "
                    "visual context."
                ),
                (
                    "Emit zero detections for a context only when no "
                    "allowlisted symbol component is recognizable in that "
                    "context."
                ),
            ],
            "constraints": [
                "inspect_each_listed_visual_context",
                "use_only_listed_visual_observation_ids",
                (
                    "use_only_associated_text_observation_ids_from_the_"
                    "matching_visual_context"
                ),
                "detection_bbox_normalized_is_relative_to_the_entire_crop",
                "detection_bbox_must_have_positive_width_and_height",
                "prefer_line_level_text_when_line_and_span_duplicate_raw_text",
                "return_no_detection_for_unrecognized_or_absent_symbols",
                "match_response_schema_exactly",
                "report_one_confidence_signal_between_zero_and_one",
                "return_one_json_object_only",
            ],
            "response_schema": response_schema,
        },
        ensure_ascii=False,
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


def build_visual_failure_envelope(
    failure_stage: VisualSymbolFailureStage | str,
) -> dict[str, str]:
    if (
        not isinstance(failure_stage, str)
        or failure_stage not in VISUAL_SYMBOL_FAILURE_STAGES
    ):
        raise ValueError("visual symbol failure stage is invalid") from None
    return {
        "schema_version": "visual-symbol-call-failure/2",
        "error_code": "visual_schema_invalid",
        "failure_stage": failure_stage,
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
    json_invalid = False
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            json_invalid = True
    else:
        try:
            payload = dict(content)
        except (TypeError, ValueError):
            json_invalid = True
    if json_invalid:
        raise VisualSymbolSchemaError(
            failure_stage="json_invalid"
        ) from None

    local_schema_invalid = False
    validator: jsonschema.Draft202012Validator | None = None
    schema_sha256 = ""
    try:
        schema_bytes = SCHEMA_PATH.read_bytes()
        schema_sha256 = hashlib.sha256(schema_bytes).hexdigest()
        schema = json.loads(schema_bytes)
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
    except (
        json.JSONDecodeError,
        jsonschema.SchemaError,
        OSError,
        TypeError,
        ValueError,
    ):
        local_schema_invalid = True
    if local_schema_invalid or validator is None:
        raise VisualSymbolSchemaError(
            failure_stage="local_schema_invalid"
        ) from None

    schema_diagnostic: dict[str, Any] | None = None
    schema_validation_failed = False
    try:
        validator.validate(payload)
        if any(
            not math.isfinite(float(value))
            for detection in payload["detections"]
            for value in (
                *detection["bbox_normalized"],
                detection["confidence_signal"],
            )
        ):
            raise ValueError("non-finite bbox")
    except jsonschema.ValidationError as exc:
        schema_validation_failed = True
        schema_diagnostic = _visual_schema_diagnostic(
            exc,
            schema_sha256=schema_sha256,
        )
    except (KeyError, TypeError, ValueError):
        schema_validation_failed = True
    if schema_validation_failed:
        raise VisualSymbolSchemaError(
            failure_stage="schema_invalid",
            diagnostic=schema_diagnostic,
        ) from None
    if not isinstance(payload, dict):
        raise VisualSymbolSchemaError(
            failure_stage="schema_invalid"
        ) from None
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
            failure_stage="schema_invalid"
        ) from None
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
        confidence_signal = float(detection["confidence_signal"])
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
                confidence_signal=confidence_signal,
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


def _visual_priority(
    observation: VisualObservation,
    snapshot: Any,
    texts: Mapping[str, TextObservation],
) -> int:
    coverage = {
        entry.observation_id: entry
        for entry in getattr(snapshot, "coverage_entries", ())
    }
    associated = set(observation.associated_text_observation_ids)
    parser_failed = any(
        (
            source_id in texts
            and coverage.get(source_id) is not None
            and coverage[source_id].disposition == "ambiguous"
            and (
                re.search(r"[0-9]", texts[source_id].raw_text) is not None
                or normalize_text(texts[source_id].raw_text).startswith("M")
            )
        )
        for source_id in associated
    )
    if parser_failed:
        return 0
    confirmation_candidate = any(
        bool(candidate.get("payload", {}).get("requires_confirmation"))
        and associated.intersection(candidate.get("source_location_ids", ()))
        for candidate in getattr(snapshot, "candidates", ())
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("payload"), Mapping)
    )
    return 1 if confirmation_candidate else 2


def plan_visual_batches(
    pages: Sequence[PageInventory],
    snapshot: Any,
) -> tuple[tuple[VisualBatch, ...], ...]:
    """Purely schedule all visual observations before any Provider work."""
    planned: list[tuple[VisualBatch, ...]] = []
    for page in pages:
        texts = {
            item.observation_id: item
            for item in page.observations
        }
        ordered = sorted(
            page.visual_observations,
            key=lambda item: (
                _visual_priority(item, snapshot, texts),
                item.page_index,
                item.bbox_pdf[1],
                item.bbox_pdf[0],
                item.proposal_kind,
                item.observation_id,
            ),
        )
        batches = pack_visual_batches(page, ordered)
        if len(batches) > 16:
            raise VisualObservationBlockingError(
                "symbol_route_budget_exhausted",
                page_index=page.page_index,
            )
        planned.append(batches)
    return tuple(planned)


def deduplicate_symbol_detections(
    detections: Sequence[ValidatedSymbolDetection],
) -> tuple[ValidatedSymbolDetection, ...]:
    """Retain the stable first page-space detection for each overlap group."""
    return tuple(
        group.detection
        for group in group_symbol_detections(detections)
    )


def _overlap_fraction(left: BBox, right: BBox) -> float:
    intersection = (
        max(left[0], right[0]),
        max(left[1], right[1]),
        min(left[2], right[2]),
        min(left[3], right[3]),
    )
    intersection_area = max(0.0, intersection[2] - intersection[0]) * max(
        0.0,
        intersection[3] - intersection[1],
    )
    left_area = max(0.0, left[2] - left[0]) * max(
        0.0,
        left[3] - left[1],
    )
    right_area = max(0.0, right[2] - right[0]) * max(
        0.0,
        right[3] - right[1],
    )
    minimum = min(left_area, right_area)
    return 0.0 if minimum <= 0 else intersection_area / minimum


def group_symbol_detections(
    detections: Sequence[ValidatedSymbolDetection],
) -> tuple[DeduplicatedSymbolGroup, ...]:
    """Group same-page detections independent of Provider and batch order."""
    ordered = sorted(
        detections,
        key=lambda item: (
            item.bbox_pdf[1],
            item.bbox_pdf[0],
            item.visual_observation_id,
            item.symbol_kind,
            item.bbox_pdf,
        ),
    )
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        current = index
        while parent[current] != current:
            parent[current] = parent[parent[current]]
            current = parent[current]
        return current

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left_index, left in enumerate(ordered):
        for right_index in range(left_index + 1, len(ordered)):
            right = ordered[right_index]
            if (
                left.symbol_kind == right.symbol_kind
                and _overlap_fraction(left.bbox_pdf, right.bbox_pdf) >= 0.8
            ):
                union(left_index, right_index)

    members: dict[int, list[ValidatedSymbolDetection]] = {}
    for index, detection in enumerate(ordered):
        members.setdefault(find(index), []).append(detection)

    return tuple(
        DeduplicatedSymbolGroup(
            detection=replace(
                group[0],
                associated_text_observation_ids=tuple(
                    sorted(
                        {
                            source_id
                            for detection in group
                            for source_id in (
                                detection.associated_text_observation_ids
                            )
                        }
                    )
                ),
                confidence_signal=min(
                    detection.confidence_signal for detection in group
                ),
            ),
            visual_observation_ids=tuple(
                sorted(
                    {
                        detection.visual_observation_id
                        for detection in group
                    }
                )
            ),
        )
        for group in members.values()
    )


def _detection_value(
    detection: ValidatedSymbolDetection | Mapping[str, Any],
    field: str,
) -> Any:
    if isinstance(detection, Mapping):
        return detection[field]
    return getattr(detection, field)


def _ordered_texts(
    allowed_ids: Collection[str],
    detection_ids: Collection[str],
    text_observations: Sequence[TextObservation],
) -> tuple[TextObservation, ...]:
    allowlist = set(allowed_ids)
    selected = [
        item
        for item in text_observations
        if item.observation_id in allowlist
        and item.observation_id in detection_ids
    ]
    selected_by_id = {
        item.observation_id: item
        for item in selected
    }
    selected = [
        item
        for item in selected
        if not (
            item.observation_level == "span"
            and item.parent_region_id in selected_by_id
            and selected_by_id[item.parent_region_id].observation_level
            == "line"
            and normalize_text(item.raw_text)
            == normalize_text(
                selected_by_id[item.parent_region_id].raw_text
            )
        )
    ]
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                item.page_index,
                item.direction_angle_degrees % 360,
                item.bbox_pdf[1],
                item.bbox_pdf[0],
                item.observation_id,
            ),
        )
    )


def _union(bboxes: Sequence[BBox]) -> BBox:
    return (
        min(item[0] for item in bboxes),
        min(item[1] for item in bboxes),
        max(item[2] for item in bboxes),
        max(item[3] for item in bboxes),
    )


def _decimal_token(text: str) -> str | None:
    normalized = normalize_text(text)
    match = re.fullmatch(rf"(?:深|↓)?\s*({NUMBER})", normalized)
    return None if match is None else match.group(1)


def _ascii_decimal_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        match.group(1)
        for match in re.finditer(
            rf"(?<![0-9A-Za-z.])({NUMBER})(?![0-9A-Za-z.])",
            text,
        )
    )


def _distinct_ascii_decimals(
    texts: Sequence[TextObservation],
) -> tuple[Decimal, ...]:
    return tuple(
        dict.fromkeys(
            Decimal(token)
            for item in texts
            for token in _ascii_decimal_tokens(item.raw_text)
        )
    )


def _gdt_datum_tokens(
    texts: Sequence[TextObservation],
) -> tuple[str, ...] | None:
    datums: list[str] = []
    for item in texts:
        for token in item.raw_text.split():
            if re.fullmatch(NUMBER, token):
                continue
            if re.fullmatch(r"[A-Z]", token):
                datums.append(token)
                continue
            return None
    return tuple(dict.fromkeys(datums))


def _typed_depth_projection(
    texts: Sequence[TextObservation],
) -> tuple[dict[str, Any], str] | None:
    try:
        if len(texts) == 1:
            parsed = parse_annotation(texts[0].raw_text)
            value = (
                parsed.depth
                if parsed.item_type == "diameter_dimension"
                else parsed.thread_depth
                if parsed.item_type == "thread"
                else None
            )
            if value is None:
                return None
        else:
            grouped = group_observations(texts)
            if len(grouped) != 1 or grouped[0].item_type != "composite":
                return None
            parsed = grouped[0]
            depth_requirements = [
                requirement
                for requirement in parsed.sub_requirements
                if requirement.get("kind") == "depth"
            ]
            if len(depth_requirements) != 1:
                return None
            value = depth_requirements[0].get("value")
            if value is None:
                return None
    except ValueError:
        return None
    return (
        parsed.model_dump(mode="json", exclude_none=True),
        str(value),
    )


def _multiline_diameter_depth_projection(
    texts: Sequence[TextObservation],
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    diameter_texts = [
        item
        for item in texts
        if _decimal_token(item.raw_text) is not None
        and not normalize_text(item.raw_text).startswith(("深", "↓"))
    ]
    depth_texts = [
        item
        for item in texts
        if normalize_text(item.raw_text).startswith(("深", "↓"))
        and _decimal_token(item.raw_text) is not None
    ]
    if len(diameter_texts) != 1 or len(depth_texts) != 1:
        rejection_code = (
            "visual_projection_conflict"
            if len(diameter_texts) > 1 or len(depth_texts) > 1
            else "visual_local_parse_failed"
        )
        return None, None, rejection_code

    diameter = diameter_texts[0]
    canonical_primary = normalize_text(diameter.raw_text)
    if not canonical_primary.startswith("Φ"):
        canonical_primary = f"Φ{canonical_primary}"
    typed_texts = tuple(
        replace(
            item,
            raw_text=canonical_primary,
            normalized_text=canonical_primary,
        )
        if item.observation_id == diameter.observation_id
        else item
        for item in texts
    )
    try:
        grouped = group_observations(typed_texts)
    except ValueError:
        return None, None, "visual_local_parse_failed"
    if len(grouped) != 1 or grouped[0].item_type != "composite":
        return None, None, "visual_local_parse_failed"

    payload = grouped[0].model_dump(mode="json", exclude_none=True)
    requirements = payload.get("sub_requirements")
    if (
        not isinstance(requirements, list)
        or len(requirements) != 2
        or [item.get("kind") for item in requirements]
        != ["diameter_dimension", "depth"]
    ):
        return None, None, "visual_local_parse_failed"
    requirements[0]["raw_text"] = diameter.raw_text
    payload["raw_text"] = "\n".join(item.raw_text for item in texts)
    return payload, str(requirements[1]["value"]), None


def _same_decimal(left: Any, right: str) -> bool:
    try:
        return Decimal(str(left)) == Decimal(right)
    except (ArithmeticError, ValueError):
        return False


def _enrich_existing_depth(
    existing: Mapping[str, Any],
    *,
    value: str,
    coordinates: BBox,
) -> dict[str, Any] | None:
    payload = deepcopy(existing.get("payload"))
    if not isinstance(payload, dict):
        return None
    item_type = payload.get("item_type")
    if item_type == "diameter_dimension":
        field = "depth"
    elif item_type == "thread":
        field = "thread_depth"
    elif item_type == "composite":
        requirements = payload.get("sub_requirements")
        if not isinstance(requirements, list):
            return None
        depth_requirements = [
            requirement
            for requirement in requirements
            if isinstance(requirement, dict)
            and requirement.get("kind") == "depth"
        ]
        if len(depth_requirements) > 1:
            return None
        if depth_requirements:
            prior = depth_requirements[0].get("value")
            if prior is not None:
                if not _same_decimal(prior, value):
                    return None
            else:
                depth_requirements[0]["value"] = value
                if not _append_normalized_depth(payload, value):
                    return None
        else:
            requirements.append(
                {
                    "order": len(requirements),
                    "kind": "depth",
                    "raw_text": f"深{value}",
                    "value": value,
                }
            )
            if not _append_normalized_depth(payload, value):
                return None
        payload["coordinates"] = coordinates
        return payload
    else:
        return None
    prior = payload.get(field)
    if prior is not None:
        if not _same_decimal(prior, value):
            return None
    else:
        payload[field] = value
        if not _append_normalized_depth(payload, value):
            return None
    payload["coordinates"] = coordinates
    return payload


def _append_normalized_depth(
    payload: dict[str, Any],
    value: str,
) -> bool:
    current = str(
        payload.get("normalized_text") or payload.get("raw_text") or ""
    )
    if not current:
        return True
    existing_values = re.findall(
        rf"(?:深|↓)\s*({NUMBER})(?![0-9.])",
        normalize_text(current),
    )
    if existing_values:
        return all(_same_decimal(existing, value) for existing in existing_values)
    separator = "\n" if "\n" in current else " "
    payload["normalized_text"] = f"{current}{separator}深 {value}"
    return True


def _existing_accepts_diameter(
    existing: Mapping[str, Any],
    projected: Mapping[str, Any],
) -> bool:
    existing_payload = existing.get("payload")
    return (
        isinstance(existing_payload, Mapping)
        and existing_payload.get("item_type")
        in {"linear_dimension", "diameter_dimension"}
        and projected.get("item_type") == "diameter_dimension"
        and projected.get("nominal") is not None
        and _same_decimal(
            existing_payload.get("nominal"),
            str(projected["nominal"]),
        )
    )


def _existing_accepts_diameter_depth_composite(
    existing: Mapping[str, Any],
    projected: Mapping[str, Any],
    *,
    depth_value: str,
) -> bool:
    existing_payload = existing.get("payload")
    projected_requirements = projected.get("sub_requirements")
    if (
        not isinstance(existing_payload, Mapping)
        or not isinstance(projected_requirements, list)
        or not projected_requirements
        or not isinstance(projected_requirements[0], Mapping)
    ):
        return False
    nominal = projected_requirements[0].get("nominal")
    if nominal is None:
        return False

    item_type = existing_payload.get("item_type")
    if item_type in {"linear_dimension", "diameter_dimension"}:
        if not _same_decimal(existing_payload.get("nominal"), str(nominal)):
            return False
        prior_depth = existing_payload.get("depth")
        return prior_depth is None or _same_decimal(
            prior_depth,
            depth_value,
        )
    if item_type != "composite":
        return False

    requirements = existing_payload.get("sub_requirements")
    if not isinstance(requirements, list):
        return False
    primaries = [
        requirement
        for requirement in requirements
        if isinstance(requirement, Mapping)
        and requirement.get("kind") == "diameter_dimension"
    ]
    depths = [
        requirement
        for requirement in requirements
        if isinstance(requirement, Mapping)
        and requirement.get("kind") == "depth"
    ]
    return (
        len(primaries) == 1
        and _same_decimal(primaries[0].get("nominal"), str(nominal))
        and len(depths) <= 1
        and (
            not depths
            or _same_decimal(depths[0].get("value"), depth_value)
        )
    )


def _associated_candidate_indexes(
    candidates: Sequence[Mapping[str, Any]],
    source_ids: Collection[str],
) -> tuple[int, ...]:
    current = set(source_ids)
    return tuple(
        index
        for index, candidate in enumerate(candidates)
        if current.intersection(candidate.get("source_location_ids", ()))
    )


def _candidate_bbox(candidate: Mapping[str, Any]) -> BBox | None:
    payload = candidate.get("payload")
    coordinates = (
        payload.get("coordinates")
        if isinstance(payload, Mapping)
        else None
    )
    if (
        not isinstance(coordinates, (list, tuple))
        or len(coordinates) != 4
    ):
        return None
    try:
        bbox = cast(BBox, tuple(float(value) for value in coordinates))
    except (TypeError, ValueError):
        return None
    if (
        not all(math.isfinite(value) for value in bbox)
        or bbox[2] <= bbox[0]
        or bbox[3] <= bbox[1]
    ):
        return None
    return bbox


def _geometry_depth_primary_indexes(
    candidates: Sequence[Mapping[str, Any]],
    *,
    observation: VisualObservation,
    text_by_id: Mapping[str, TextObservation],
) -> tuple[int, ...]:
    indexes: list[int] = []
    for index, candidate in enumerate(candidates):
        payload = candidate.get("payload")
        source_ids = candidate.get("source_location_ids")
        bbox = _candidate_bbox(candidate)
        if (
            not isinstance(payload, Mapping)
            or payload.get("item_type")
            not in {"thread", "diameter_dimension", "composite"}
            or not isinstance(source_ids, (list, tuple))
            or not source_ids
            or bbox is None
            or _overlap_fraction(bbox, observation.bbox_pdf) < 0.5
            or any(
                not isinstance(source_id, str)
                or source_id not in text_by_id
                or text_by_id[source_id].page_index
                != observation.page_index
                for source_id in source_ids
            )
        ):
            continue
        indexes.append(index)
    return tuple(indexes)


def _envelope(
    *,
    payload: dict[str, Any],
    source_ids: tuple[str, ...],
    projection_type: str,
    existing: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    candidate_id = (
        str(existing["candidate_id"])
        if existing is not None
        else stable_candidate_id(
            "visual-candidate/1",
            *sorted(source_ids),
            projection_type,
        )
    )
    if "candidate_id" in payload:
        payload["candidate_id"] = candidate_id
    return candidate_id, {
        "candidate_id": candidate_id,
        "payload": payload,
        "source_location_ids": list(source_ids),
    }


def _projection_requires_confirmation(payload: Mapping[str, Any]) -> bool:
    if "coarse_type" in payload:
        return True
    try:
        candidate = Candidate.model_validate(payload)
    except (TypeError, ValueError):
        return True
    if candidate.feature_kind == "unknown":
        return True
    return any(
        isinstance(requirement, Mapping)
        and requirement.get("feature_kind") == "unknown"
        for requirement in candidate.sub_requirements
    )


def _ambiguous(
    observation: VisualObservation,
    *,
    source_ids: tuple[str, ...],
    coordinates: BBox,
    kinds: tuple[SymbolKind, ...],
    rejection_code: str,
    existing_index: int | None = None,
    confidence_signal: float | None = None,
) -> VisualReviewDecision:
    return VisualReviewDecision(
        observation.observation_id,
        "ambiguous",
        source_ids,
        coordinates,
        None,
        existing_index,
        None,
        True,
        kinds,
        rejection_code,
        confidence_signal,
    )


def _canonical_items(
    context: VisualGeometryContext | None,
) -> tuple[dict[str, Any], ...]:
    if context is None:
        return ()
    parsed: list[dict[str, Any]] = []
    for content in context.canonical_path_items:
        try:
            item = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ()
        if not isinstance(item, dict):
            return ()
        parsed.append(item)
    return tuple(parsed)


def _line_segments(
    items: Sequence[Mapping[str, Any]],
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...] | None:
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for item in items:
        if item.get("opcode") != "l":
            continue
        coordinates = item.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            return None
        try:
            start = (
                float(coordinates[0][0]),
                float(coordinates[0][1]),
            )
            end = (
                float(coordinates[1][0]),
                float(coordinates[1][1]),
            )
        except (IndexError, TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (*start, *end)):
            return None
        segments.append((start, end))
    return tuple(segments)


def _cluster_vertices(
    segments: Sequence[
        tuple[tuple[float, float], tuple[float, float]]
    ],
) -> tuple[
    tuple[tuple[float, float], ...],
    tuple[tuple[int, int], ...],
]:
    vertices: list[tuple[float, float]] = []
    edges: list[tuple[int, int]] = []
    for segment in segments:
        endpoints: list[int] = []
        for endpoint in segment:
            vertex_index = next(
                (
                    index
                    for index, vertex in enumerate(vertices)
                    if math.dist(endpoint, vertex) <= 0.5
                ),
                None,
            )
            if vertex_index is None:
                vertices.append(endpoint)
                vertex_index = len(vertices) - 1
            endpoints.append(vertex_index)
        edges.append(tuple(sorted(endpoints)))
    return tuple(vertices), tuple(edges)


def _rectangle_bbox(
    segments: Sequence[
        tuple[tuple[float, float], tuple[float, float]]
    ],
) -> BBox | None:
    if len(segments) != 4 or any(
        math.dist(start, end) <= 0.5
        or (
            not math.isclose(start[0], end[0], abs_tol=0.5)
            and not math.isclose(start[1], end[1], abs_tol=0.5)
        )
        for start, end in segments
    ):
        return None
    vertices, edges = _cluster_vertices(segments)
    if (
        len(vertices) != 4
        or len(set(edges)) != 4
        or any(left == right for left, right in edges)
        or any(
            sum(vertex in edge for edge in edges) != 2
            for vertex in range(4)
        )
    ):
        return None
    bbox = (
        min(point[0] for point in vertices),
        min(point[1] for point in vertices),
        max(point[0] for point in vertices),
        max(point[1] for point in vertices),
    )
    if bbox[2] - bbox[0] <= 0.5 or bbox[3] - bbox[1] <= 0.5:
        return None
    corners = (
        (bbox[0], bbox[1]),
        (bbox[2], bbox[1]),
        (bbox[2], bbox[3]),
        (bbox[0], bbox[3]),
    )
    if any(
        not any(math.dist(vertex, corner) <= 0.5 for vertex in vertices)
        for corner in corners
    ):
        return None
    return bbox


def _triangle_segment_sets(
    segments: Sequence[
        tuple[tuple[float, float], tuple[float, float]]
    ],
) -> tuple[
    tuple[
        tuple[tuple[float, float], tuple[float, float]],
        ...,
    ],
    ...,
]:
    vertices, edges = _cluster_vertices(segments)
    edge_set = {
        edge
        for edge in edges
        if edge[0] != edge[1]
    }
    neighbors: dict[int, set[int]] = {
        index: set()
        for index in range(len(vertices))
    }
    for left, right in edge_set:
        neighbors[left].add(right)
        neighbors[right].add(left)
    cycles: set[tuple[tuple[int, int], ...]] = set()
    for vertex, adjacent in neighbors.items():
        for left, right in combinations(sorted(adjacent), 2):
            closing = tuple(sorted((left, right)))
            if closing not in edge_set:
                continue
            cycles.add(
                tuple(
                    sorted(
                        (
                            tuple(sorted((vertex, left))),
                            tuple(sorted((vertex, right))),
                            closing,
                        )
                    )
                )
            )
    return tuple(
        tuple((vertices[left], vertices[right]) for left, right in cycle)
        for cycle in sorted(cycles)
    )


def _rectangle_segment_sets(
    segments: Sequence[
        tuple[tuple[float, float], tuple[float, float]]
    ],
) -> tuple[
    tuple[
        tuple[tuple[float, float], tuple[float, float]],
        ...,
    ],
    ...,
]:
    vertices, edges = _cluster_vertices(segments)
    edge_set = {
        edge
        for edge in edges
        if edge[0] != edge[1]
    }
    neighbors: dict[int, set[int]] = {
        index: set()
        for index in range(len(vertices))
    }
    for left, right in edge_set:
        neighbors[left].add(right)
        neighbors[right].add(left)
    cycles: set[tuple[tuple[int, int], ...]] = set()
    for vertex, adjacent in neighbors.items():
        for left, right in combinations(sorted(adjacent), 2):
            for opposite in sorted(
                neighbors[left].intersection(neighbors[right])
            ):
                if opposite == vertex:
                    continue
                cycles.add(
                    tuple(
                        sorted(
                            (
                                tuple(sorted((vertex, left))),
                                tuple(sorted((left, opposite))),
                                tuple(sorted((opposite, right))),
                                tuple(sorted((right, vertex))),
                            )
                        )
                    )
                )
    return tuple(
        tuple((vertices[left], vertices[right]) for left, right in cycle)
        for cycle in sorted(cycles)
    )


def _contains_token(box: BBox, token: TextObservation) -> bool:
    return (
        box[0] <= token.bbox_pdf[0] + 2
        and box[1] <= token.bbox_pdf[1] + 2
        and box[2] >= token.bbox_pdf[2] - 2
        and box[3] >= token.bbox_pdf[3] - 2
    )


def _valid_datum_geometry(
    context: VisualGeometryContext | None,
    texts: Sequence[TextObservation],
) -> bool:
    tokens = [
        item
        for item in texts
        if re.fullmatch(r"[A-Z]", normalize_text(item.raw_text))
    ]
    if len(tokens) != 1:
        return False
    token = tokens[0]
    items = _canonical_items(context)
    lines = _line_segments(items)
    if lines is None:
        return False
    boxes: set[tuple[float, float, float, float]] = set()
    for item in items:
        coordinates = item.get("coordinates")
        if (
            item.get("opcode") != "re"
            or not isinstance(coordinates, list)
            or len(coordinates) != 4
        ):
            continue
        try:
            box = cast(BBox, tuple(float(value) for value in coordinates))
        except (TypeError, ValueError):
            return False
        if (
            not all(math.isfinite(value) for value in box)
            or box[2] <= box[0]
            or box[3] <= box[1]
        ):
            return False
        if _contains_token(box, token):
            boxes.add(tuple(round(value, 3) for value in box))
    for line_set in _rectangle_segment_sets(lines):
        box = _rectangle_bbox(line_set)
        if box is not None and _contains_token(box, token):
            boxes.add(tuple(round(value, 3) for value in box))
    return len(boxes) == 1


def _revision_triangle(
    segments: Sequence[
        tuple[tuple[float, float], tuple[float, float]]
    ],
    token: TextObservation,
) -> tuple[tuple[float, float], ...] | None:
    if len(segments) != 3 or any(
        math.dist(start, end) <= 0.5
        for start, end in segments
    ):
        return None
    vertices, edges = _cluster_vertices(segments)
    if (
        len(vertices) != 3
        or len(set(edges)) != 3
        or any(left == right for left, right in edges)
        or any(
            sum(vertex in edge for edge in edges) != 2
            for vertex in range(3)
        )
    ):
        return None
    bbox = (
        min(point[0] for point in vertices),
        min(point[1] for point in vertices),
        max(point[0] for point in vertices),
        max(point[1] for point in vertices),
    )
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    triangle_area = abs(
        vertices[0][0]
        * (vertices[1][1] - vertices[2][1])
        + vertices[1][0]
        * (vertices[2][1] - vertices[0][1])
        + vertices[2][0]
        * (vertices[0][1] - vertices[1][1])
    ) / 2
    token_bbox = token.bbox_pdf
    token_center = (
        (token_bbox[0] + token_bbox[2]) / 2,
        (token_bbox[1] + token_bbox[3]) / 2,
    )
    if not (
        4 <= width <= 24
        and 4 <= height <= 24
        and triangle_area > 0.01
        and bbox[0] - 2 <= token_center[0] <= bbox[2] + 2
        and bbox[1] - 2 <= token_center[1] <= bbox[3] + 2
    ):
        return None
    return tuple(
        sorted(
            (round(x, 3), round(y, 3))
            for x, y in vertices
        )
    )


def _valid_revision_geometry(
    context: VisualGeometryContext | None,
    texts: Sequence[TextObservation],
) -> bool:
    tokens = [
        item
        for item in texts
        if re.fullmatch(r"[A-Z0-9]{1,3}", normalize_text(item.raw_text))
    ]
    lines = _line_segments(_canonical_items(context))
    if lines is None or len(tokens) != 1:
        return False
    triangles = {
        triangle
        for line_set in _triangle_segment_sets(lines)
        if (
            triangle := _revision_triangle(line_set, tokens[0])
        )
        is not None
    }
    return len(triangles) == 1


def project_visual_observation(
    *,
    observation: VisualObservation,
    detections: Sequence[ValidatedSymbolDetection | Mapping[str, Any]],
    text_observations: Sequence[TextObservation],
    candidates: Sequence[Mapping[str, Any]],
    geometry_context: VisualGeometryContext | None,
    source_observations: Sequence[VisualObservation] = (),
) -> VisualReviewDecision:
    """Project one validated visual response through deterministic local rules."""
    visual_sources = tuple(
        sorted(
            {
                item.observation_id: item
                for item in (observation, *source_observations)
            }.values(),
            key=lambda item: (
                item.page_index,
                item.bbox_pdf[1],
                item.bbox_pdf[0],
                item.proposal_kind,
                item.observation_id,
            ),
        )
    )
    current = [
        item
        for item in detections
        if str(_detection_value(item, "visual_observation_id"))
        == observation.observation_id
    ]
    raw_confidence_signals = tuple(
        (
            item.get("confidence_signal")
            if isinstance(item, Mapping)
            else item.confidence_signal
        )
        for item in current
    )
    confidence_signal = (
        min(float(value) for value in raw_confidence_signals)
        if raw_confidence_signals
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and 0 <= float(value) <= 1
            for value in raw_confidence_signals
        )
        else None
    )
    kind_counts = Counter(
        str(_detection_value(item, "symbol_kind"))
        for item in current
    )
    kinds = tuple(
        sorted(
            {
                cast(SymbolKind, str(_detection_value(item, "symbol_kind")))
                for item in current
            }
        )
    )
    associated_ids = {
        str(source_id)
        for item in current
        for source_id in _detection_value(
            item,
            "associated_text_observation_ids",
        )
    }
    local_text_ids = {
        source_id
        for visual in visual_sources
        for source_id in visual.associated_text_observation_ids
    }
    text_by_id = {
        item.observation_id: item
        for item in text_observations
    }
    texts = _ordered_texts(
        local_text_ids,
        associated_ids,
        text_observations,
    )
    source_ids = (
        *(item.observation_id for item in visual_sources),
        *(item.observation_id for item in texts),
    )
    detection_bboxes = [
        cast(BBox, tuple(_detection_value(item, "bbox_pdf")))
        for item in current
    ]
    coordinates = _union(
        (
            *detection_bboxes,
            *(item.bbox_pdf for item in texts),
        )
        if detection_bboxes
        else tuple(item.bbox_pdf for item in visual_sources)
    )
    if not current:
        return _ambiguous(
            observation,
            source_ids=tuple(
                item.observation_id for item in visual_sources
            ),
            coordinates=_union(
                tuple(item.bbox_pdf for item in visual_sources)
            ),
            kinds=(),
            rejection_code="visual_no_detection",
        )
    if any(count > 1 for count in kind_counts.values()):
        return _ambiguous(
            observation,
            source_ids=source_ids,
            coordinates=coordinates,
            kinds=kinds,
            rejection_code="visual_projection_conflict",
        )

    projectable = {
        ("diameter",),
        ("depth",),
        ("depth", "diameter"),
        ("counterbore", "depth", "diameter"),
        ("surface_roughness",),
        ("gdt_parallelism",),
        ("gdt_perpendicularity",),
        ("gdt_flatness",),
        ("datum_reference",),
        ("revision_marker",),
    }
    if kinds not in projectable:
        return _ambiguous(
            observation,
            source_ids=source_ids,
            coordinates=coordinates,
            kinds=kinds,
            rejection_code="visual_projection_conflict",
        )
    visual_ids = {
        item.observation_id for item in visual_sources
    }
    text_source_ids = tuple(
        source_id
        for source_id in source_ids
        if source_id not in visual_ids
    )
    indexes = _associated_candidate_indexes(candidates, text_source_ids)
    geometry_associated = False
    depth_primary_associated = False
    if kinds == ("depth",):
        typed_indexes = tuple(
            index
            for index in indexes
            if isinstance(candidates[index].get("payload"), Mapping)
            and candidates[index]["payload"].get("item_type")
            in {"thread", "diameter_dimension", "composite"}
        )
        if typed_indexes:
            indexes = typed_indexes
            depth_primary_associated = bool(indexes)
        else:
            indexes = _geometry_depth_primary_indexes(
                candidates,
                observation=observation,
                text_by_id=text_by_id,
            )
            geometry_associated = bool(indexes)
            depth_primary_associated = geometry_associated
    if len(indexes) > 1:
        return _ambiguous(
            observation,
            source_ids=source_ids,
            coordinates=coordinates,
            kinds=kinds,
            rejection_code="visual_projection_conflict",
        )
    existing_index = indexes[0] if indexes else None
    existing = (
        candidates[existing_index] if existing_index is not None else None
    )
    existing_text_source_ids: set[str] = set()
    if existing is not None:
        existing_source_ids = {
            str(source_id)
            for source_id in existing.get("source_location_ids", ())
        }
        existing_text_source_ids = existing_source_ids.difference(
            visual_ids
        )
        permitted_text_ids = {
            *local_text_ids,
            *(
                existing_text_source_ids
                if geometry_associated
                else ()
            ),
        }
        if (
            not existing_source_ids.issubset(
                {*visual_ids, *permitted_text_ids}
            )
            or any(
                source_id not in text_by_id
                or text_by_id[source_id].page_index
                != observation.page_index
                for source_id in existing_text_source_ids
            )
        ):
            return _ambiguous(
                observation,
                source_ids=source_ids,
                coordinates=coordinates,
                kinds=kinds,
                rejection_code="visual_projection_conflict",
                existing_index=existing_index,
            )
        participating_ids = {
            *text_source_ids,
            *existing_source_ids,
        }
        participating_texts = tuple(
            sorted(
                (
                    item
                    for item in text_observations
                    if item.observation_id in participating_ids
                ),
                key=lambda item: (
                    item.page_index,
                    item.direction_angle_degrees % 360,
                    item.bbox_pdf[1],
                    item.bbox_pdf[0],
                    item.observation_id,
                ),
            )
        )
        source_ids = (
            *(item.observation_id for item in visual_sources),
            *(item.observation_id for item in participating_texts),
        )
        coordinates = _union(
            (
                coordinates,
                *(item.bbox_pdf for item in participating_texts),
            )
        )

    if kinds == ("datum_reference",):
        if not _valid_datum_geometry(geometry_context, texts):
            return _ambiguous(
                observation,
                source_ids=source_ids,
                coordinates=coordinates,
                kinds=kinds,
                rejection_code="visual_local_parse_failed",
            )
        return VisualReviewDecision(
            observation.observation_id,
            "reference_context",
            source_ids,
            coordinates,
            None,
            existing_index,
            None,
            False,
            kinds,
            None,
            confidence_signal,
        )
    if kinds == ("revision_marker",):
        if not _valid_revision_geometry(geometry_context, texts):
            return _ambiguous(
                observation,
                source_ids=source_ids,
                coordinates=coordinates,
                kinds=kinds,
                rejection_code="visual_local_parse_failed",
            )
        return VisualReviewDecision(
            observation.observation_id,
            "non_inspection",
            source_ids,
            coordinates,
            None,
            existing_index,
            None,
            True,
            kinds,
            None,
            confidence_signal,
        )

    payload: dict[str, Any] | None = None
    projection_rejection_code = "visual_local_parse_failed"
    projection_type = "+".join(kinds)
    raw_text = "\n".join(item.raw_text for item in texts)

    if kinds == ("diameter",):
        if len(texts) != 1:
            payload = None
            if len(texts) > 1:
                projection_rejection_code = "visual_projection_conflict"
        else:
            try:
                parsed = parse_annotation(
                    normalize_text(texts[0].raw_text)
                    if normalize_text(texts[0].raw_text).startswith("Φ")
                    else f"Φ{normalize_text(texts[0].raw_text)}"
                )
            except ValueError:
                payload = None
            else:
                payload = parsed.model_dump(mode="json", exclude_none=True)
                payload.update(
                    raw_text=texts[0].raw_text,
                    coordinates=coordinates,
                    feature_kind="unknown",
                )
                if existing is not None:
                    original = deepcopy(existing.get("payload"))
                    if (
                        not isinstance(original, dict)
                        or not _existing_accepts_diameter(
                            existing,
                            payload,
                        )
                    ):
                        payload = None
                        projection_rejection_code = (
                            "visual_projection_conflict"
                        )
                    else:
                        original.update(payload)
                        original["raw_text"] = existing["payload"]["raw_text"]
                        original["coordinates"] = coordinates
                        payload = original
    elif kinds == ("depth", "diameter"):
        if len(texts) == 1:
            source = normalize_text(texts[0].raw_text)
            if not source.startswith("Φ"):
                source = f"Φ{source}"
            try:
                candidate = parse_annotation(source)
            except ValueError:
                candidate = None
            else:
                if (
                    candidate.item_type == "diameter_dimension"
                    and candidate.depth is not None
                ):
                    if existing is not None:
                        payload = _enrich_existing_depth(
                            existing,
                            value=str(candidate.depth),
                            coordinates=coordinates,
                        )
                        if payload is None:
                            projection_rejection_code = (
                                "visual_projection_conflict"
                            )
                    else:
                        payload = candidate.model_dump(
                            mode="json",
                            exclude_none=True,
                        )
                        payload.update(
                            raw_text=raw_text,
                            coordinates=coordinates,
                        )
        else:
            projected, depth_value, rejection_code = (
                _multiline_diameter_depth_projection(texts)
            )
            if rejection_code is not None:
                projection_rejection_code = rejection_code
            elif (
                projected is not None
                and depth_value is not None
                and (
                    existing is None
                    or _existing_accepts_diameter_depth_composite(
                        existing,
                        projected,
                        depth_value=depth_value,
                    )
                )
            ):
                payload = projected
                payload.update(
                    coordinates=coordinates,
                )
            elif projected is not None:
                projection_rejection_code = "visual_projection_conflict"
    elif kinds == ("depth",):
        explicit_depth_values = tuple(
            value
            for item in texts
            if (
                (
                    depth_primary_associated
                    and item.observation_id
                    not in existing_text_source_ids
                )
                or normalize_text(item.raw_text).startswith(("深", "↓"))
            )
            if (value := _decimal_token(item.raw_text)) is not None
        )
        typed_projection = _typed_depth_projection(texts)
        typed_values = (
            (typed_projection[1],)
            if typed_projection is not None
            else ()
        )
        distinct = tuple(
            dict.fromkeys((*explicit_depth_values, *typed_values))
        )
        if existing is not None and len(distinct) == 1:
            payload = _enrich_existing_depth(
                existing,
                value=distinct[0],
                coordinates=coordinates,
            )
            if payload is None:
                projection_rejection_code = "visual_projection_conflict"
        elif existing is None and typed_projection is not None:
            payload = typed_projection[0]
            payload.update(
                coordinates=coordinates,
            )
        elif len(distinct) > 1:
            projection_rejection_code = "visual_projection_conflict"
    elif kinds == ("counterbore", "depth", "diameter"):
        diameter_texts = [
            item
            for item in texts
            if _decimal_token(item.raw_text) is not None
            and not normalize_text(item.raw_text).startswith(("深", "↓"))
        ]
        depth_texts = [
            item
            for item in texts
            if normalize_text(item.raw_text).startswith(("深", "↓"))
            and _decimal_token(item.raw_text) is not None
        ]
        diameter_value: str | None = None
        depth_value: str | None = None
        diameter_raw: str | None = None
        depth_raw: str | None = None
        if len(diameter_texts) == 1 and len(depth_texts) == 1:
            diameter_value = _decimal_token(diameter_texts[0].raw_text)
            depth_value = _decimal_token(depth_texts[0].raw_text)
            diameter_raw = diameter_texts[0].raw_text
            depth_raw = depth_texts[0].raw_text
        elif len(texts) == 1:
            compact = re.fullmatch(
                rf"({NUMBER})\s+({NUMBER})",
                normalize_text(texts[0].raw_text),
            )
            if compact is not None:
                diameter_value, depth_value = compact.groups()
                diameter_raw, depth_raw = compact.groups()
        else:
            if len(diameter_texts) > 1 or len(depth_texts) > 1:
                projection_rejection_code = "visual_projection_conflict"
        if (
            diameter_value is not None
            and depth_value is not None
            and diameter_raw is not None
            and depth_raw is not None
        ):
            try:
                diameter_candidate = parse_annotation(f"Φ{diameter_value}")
            except ValueError:
                payload = None
            else:
                payload = {
                    "candidate_id": "",
                    "item_type": "composite",
                    "raw_text": raw_text,
                    "normalized_text": "⌴"
                    + "\n".join(normalize_text(item.raw_text) for item in texts),
                    "coordinates": coordinates,
                    "scope": "local_feature",
                    "quantity": None,
                    "sub_requirements": [
                        {
                            "order": 0,
                            "kind": "diameter_dimension",
                            "raw_text": diameter_raw,
                            "nominal": str(diameter_candidate.nominal),
                            "feature_kind": "unknown",
                        },
                        {
                            "order": 1,
                            "kind": "depth",
                            "raw_text": depth_raw,
                            "value": depth_value,
                        },
                    ],
                    "balloon_required": True,
                }
                if (
                    existing is not None
                    and not _existing_accepts_diameter_depth_composite(
                        existing,
                        payload,
                        depth_value=str(depth_value),
                    )
                ):
                    payload = None
                    projection_rejection_code = (
                        "visual_projection_conflict"
                    )
    elif kinds == ("surface_roughness",):
        roughness_values = _distinct_ascii_decimals(texts)
        if len(roughness_values) == 1:
            payload = {
                "raw_text": raw_text,
                "coordinates": coordinates,
                "coarse_type": "roughness",
            }
    elif kinds[0].startswith("gdt_"):
        tolerances = _distinct_ascii_decimals(texts)
        datums = _gdt_datum_tokens(texts)
        if len(tolerances) == 1 and datums is not None:
            symbols = {
                "gdt_parallelism": "∥",
                "gdt_perpendicularity": "⊥",
                "gdt_flatness": "⏥",
            }
            payload = {
                "raw_text": f"{symbols[kinds[0]]} {raw_text}",
                "coordinates": coordinates,
                "coarse_type": "geometric_tolerance",
            }
        elif len(tolerances) > 1:
            projection_rejection_code = "visual_projection_conflict"

    if payload is None:
        return _ambiguous(
            observation,
            source_ids=source_ids,
            coordinates=coordinates,
            kinds=kinds,
            rejection_code=projection_rejection_code,
            existing_index=existing_index,
        )
    requires_confirmation = _projection_requires_confirmation(payload)
    payload["requires_confirmation"] = requires_confirmation
    candidate_id, envelope = _envelope(
        payload=payload,
        source_ids=source_ids,
        projection_type=projection_type,
        existing=existing,
    )
    envelope["source_truth_preserved"] = not requires_confirmation
    return VisualReviewDecision(
        observation.observation_id,
        "candidate",
        source_ids,
        coordinates,
        candidate_id,
        existing_index,
        envelope,
        requires_confirmation,
        kinds,
        None,
        confidence_signal,
    )


def _visual_reading_key(
    observation: VisualObservation,
) -> tuple[int, float, float, str, str]:
    return (
        observation.page_index,
        observation.bbox_pdf[1],
        observation.bbox_pdf[0],
        observation.proposal_kind,
        observation.observation_id,
    )


def _merge_existing_candidate_decisions(
    decisions: Sequence[VisualReviewDecision],
    *,
    candidates: Sequence[Mapping[str, Any]],
    visual_by_id: Mapping[str, VisualObservation],
) -> tuple[VisualReviewDecision, ...]:
    merged_decisions = list(decisions)
    indexes_by_candidate: dict[int, list[int]] = {}
    for decision_index, decision in enumerate(merged_decisions):
        if decision.existing_candidate_index is not None:
            indexes_by_candidate.setdefault(
                decision.existing_candidate_index,
                [],
            ).append(decision_index)

    for candidate_index, decision_indexes in indexes_by_candidate.items():
        projection_indexes: dict[tuple[str, ...], list[int]] = {}
        for decision_index in decision_indexes:
            decision = merged_decisions[decision_index]
            projection_indexes.setdefault(
                decision.source_location_ids,
                [],
            ).append(decision_index)
        if len(projection_indexes) <= 1:
            continue

        ordered_indexes = sorted(
            decision_indexes,
            key=lambda index: _visual_reading_key(
                visual_by_id[merged_decisions[index].observation_id]
            ),
        )
        source_ids = tuple(
            dict.fromkeys(
                (
                    *(
                        source_id
                        for source_id in (
                            visual.observation_id
                            for visual in sorted(
                                (
                                    visual_by_id[source_id]
                                    for index in ordered_indexes
                                    for source_id in merged_decisions[
                                        index
                                    ].source_location_ids
                                    if source_id in visual_by_id
                                ),
                                key=_visual_reading_key,
                            )
                        )
                    ),
                    *(
                        source_id
                        for index in ordered_indexes
                        for source_id in merged_decisions[
                            index
                        ].source_location_ids
                        if source_id not in visual_by_id
                    ),
                )
            )
        )
        coordinates = _union(
            tuple(
                merged_decisions[index].coordinates
                for index in ordered_indexes
            )
        )
        representatives = [
            next(
                (
                    merged_decisions[index]
                    for index in indexes
                    if merged_decisions[index].candidate_envelope is not None
                ),
                merged_decisions[indexes[0]],
            )
            for indexes in projection_indexes.values()
        ]
        base_candidate = candidates[candidate_index]
        base_payload = base_candidate.get("payload")
        candidate_id = str(base_candidate.get("candidate_id", ""))
        compatible = (
            isinstance(base_payload, Mapping)
            and bool(candidate_id)
            and all(
                decision.disposition == "candidate"
                and decision.rejection_code is None
                and decision.candidate_id == candidate_id
                and isinstance(decision.candidate_envelope, Mapping)
                and isinstance(
                    decision.candidate_envelope.get("payload"),
                    Mapping,
                )
                for decision in representatives
            )
        )
        merged_payload = deepcopy(base_payload) if compatible else None
        changed_values: dict[str, Any] = {}
        if compatible and isinstance(merged_payload, dict):
            for decision in representatives:
                envelope = cast(
                    Mapping[str, Any],
                    decision.candidate_envelope,
                )
                payload = cast(Mapping[str, Any], envelope["payload"])
                for key, value in payload.items():
                    if key == "coordinates" or value == base_payload.get(key):
                        continue
                    if key in changed_values and changed_values[key] != value:
                        compatible = False
                        break
                    changed_values[key] = deepcopy(value)
                if not compatible:
                    break
        else:
            compatible = False

        if compatible and isinstance(merged_payload, dict):
            merged_payload.update(changed_values)
            merged_payload["coordinates"] = coordinates
            merged_requires_confirmation = any(
                decision.requires_confirmation
                for decision in representatives
            )
            merged_payload["requires_confirmation"] = (
                merged_requires_confirmation
            )
            merged_signals = tuple(
                decision.confidence_signal
                for decision in representatives
                if decision.confidence_signal is not None
            )
            merged_confidence_signal = (
                min(merged_signals) if merged_signals else None
            )
            envelope = {
                "candidate_id": candidate_id,
                "payload": merged_payload,
                "source_location_ids": list(source_ids),
                "source_truth_preserved": not merged_requires_confirmation,
            }
            primary_index = ordered_indexes[0]
            for decision_index in decision_indexes:
                merged_decisions[decision_index] = replace(
                    merged_decisions[decision_index],
                    source_location_ids=source_ids,
                    coordinates=coordinates,
                    requires_confirmation=merged_requires_confirmation,
                    confidence_signal=merged_confidence_signal,
                    candidate_envelope=(
                        envelope
                        if decision_index == primary_index
                        else None
                    ),
                )
            continue

        for decision_index in decision_indexes:
            merged_decisions[decision_index] = replace(
                merged_decisions[decision_index],
                disposition="ambiguous",
                source_location_ids=source_ids,
                coordinates=coordinates,
                candidate_id=None,
                candidate_envelope=None,
                requires_confirmation=True,
                rejection_code="visual_projection_conflict",
            )

    return tuple(merged_decisions)


def project_visual_page(
    *,
    visual_observations: Sequence[VisualObservation],
    detections: Sequence[ValidatedSymbolDetection],
    rejection_codes: Mapping[str, str],
    text_observations: Sequence[TextObservation],
    candidates: Sequence[Mapping[str, Any]],
    geometry_contexts: Mapping[str, VisualGeometryContext],
) -> tuple[VisualReviewDecision, ...]:
    """Project one page only after every batch response has been validated."""
    ordered_visuals = tuple(sorted(visual_observations, key=_visual_reading_key))
    visual_by_id = {
        observation.observation_id: observation
        for observation in ordered_visuals
    }
    parent = {
        observation.observation_id: observation.observation_id
        for observation in ordered_visuals
    }

    def find(identity: str) -> str:
        current = identity
        while parent[current] != current:
            parent[current] = parent[parent[current]]
            current = parent[current]
        return current

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        left_key = _visual_reading_key(visual_by_id[left_root])
        right_key = _visual_reading_key(visual_by_id[right_root])
        if left_key <= right_key:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    groups = group_symbol_detections(detections)
    for group in groups:
        identities = [
            identity
            for identity in group.visual_observation_ids
            if identity in visual_by_id
        ]
        for identity in identities[1:]:
            union(identities[0], identity)

    components: dict[str, list[VisualObservation]] = {}
    for observation in ordered_visuals:
        components.setdefault(find(observation.observation_id), []).append(
            observation
        )

    decisions: list[VisualReviewDecision] = []
    for component in sorted(
        components.values(),
        key=lambda items: _visual_reading_key(min(items, key=_visual_reading_key)),
    ):
        sources = tuple(sorted(component, key=_visual_reading_key))
        source_ids = {
            observation.observation_id for observation in sources
        }
        owner = sources[0]
        component_groups = [
            group
            for group in groups
            if source_ids.intersection(group.visual_observation_ids)
        ]
        component_rejections = sorted(
            {
                rejection_codes[identity]
                for identity in source_ids
                if identity in rejection_codes
            }
        )
        if component_rejections:
            component_kinds = tuple(
                sorted(
                    {
                        group.detection.symbol_kind
                        for group in component_groups
                    }
                )
            )
            primary = _ambiguous(
                owner,
                source_ids=tuple(
                    observation.observation_id for observation in sources
                ),
                coordinates=_union(
                    tuple(
                        observation.bbox_pdf for observation in sources
                    )
                ),
                kinds=component_kinds,
                rejection_code=component_rejections[0],
            )
        else:
            merged_detections = tuple(
                replace(
                    group.detection,
                    visual_observation_id=owner.observation_id,
                    associated_text_observation_ids=tuple(
                        sorted(
                            {
                                *group.detection.associated_text_observation_ids,
                            }
                        )
                    ),
                )
                for group in component_groups
            )
            primary = project_visual_observation(
                observation=owner,
                detections=merged_detections,
                text_observations=text_observations,
                candidates=candidates,
                geometry_context=next(
                    (
                        geometry_contexts[source.observation_id]
                        for source in sources
                        if source.observation_id in geometry_contexts
                    ),
                    None,
                ),
                source_observations=sources,
            )
        decisions.append(primary)
        for alias in sources[1:]:
            decisions.append(
                replace(
                    primary,
                    observation_id=alias.observation_id,
                    candidate_envelope=None,
                )
            )
    decisions = list(
        _merge_existing_candidate_decisions(
            decisions,
            candidates=candidates,
            visual_by_id=visual_by_id,
        )
    )
    return tuple(
        sorted(
            decisions,
            key=lambda decision: _visual_reading_key(
                visual_by_id[decision.observation_id]
            ),
        )
    )
