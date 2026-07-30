from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

import jsonschema
from openai import APIConnectionError, APITimeoutError
from PIL import Image, UnidentifiedImageError

from app.providers.base import LocalizedProviderFailure, VisionResult
from app.candidates.symbol_review import (
    VISUAL_SCHEMA_VERSION,
    VISUAL_SYMBOL_FAILURE_STAGES,
    VisualSymbolFailureStage,
    VisualSymbolSchemaError,
    parse_visual_symbol_json,
    validate_visual_schema_diagnostic,
)


SCHEMA_PATH = Path(__file__).with_name("candidate_review.schema.json")
SYSTEM_PROMPT = "Review one engineering annotation crop. Output JSON only."
VISUAL_SYSTEM_PROMPT = (
    "Review local engineering drawing symbol contexts. "
    "Call the reporting function exactly once."
)
VISUAL_TOOL_NAME = "submit_visual_symbol_review"
VISUAL_SCHEMA_PATH = Path(__file__).with_name(
    "visual_symbol_review.schema.json"
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_VISUAL_PNG_SIDE = 1536
_MAX_VISUAL_PNG_BYTES = 8 * 1024 * 1024
_SAFE_VISUAL_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FORBIDDEN_METADATA = re.compile(
    r"authorization|api[_-]?key|secret|credential|bearer",
    re.IGNORECASE,
)
_SAFE_USAGE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}_tokens$")
_MISSING_RESPONSE_MEMBER = object()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_DIAGNOSTIC_VERSION = "visual-symbol-provider-diagnostic/1"


class CandidateSchemaError(ValueError):
    pass


class VisualSymbolInputError(ValueError):
    pass


class VisualSymbolMetadataError(ValueError):
    pass


class VisualSymbolProviderError(RuntimeError):
    def __init__(
        self,
        *,
        request_id: str,
        usage: dict[str, int],
        failure_stage: VisualSymbolFailureStage,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__("visual symbol response violates frozen schema")
        if (
            not isinstance(failure_stage, str)
            or failure_stage not in VISUAL_SYMBOL_FAILURE_STAGES
        ):
            raise ValueError(
                "visual symbol failure stage is invalid"
            ) from None
        self.request_id, self.usage = validate_visual_request_metadata(
            request_id,
            usage,
        )
        self.failure_stage = failure_stage
        self.failure_category = "schema"
        self.diagnostic = self._validated_diagnostic(diagnostic)

    @staticmethod
    def _validated_diagnostic(
        diagnostic: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if diagnostic is None:
            return None
        document = dict(diagnostic)
        arguments_sha256 = document.get("arguments_sha256")
        schema_validation = document.get("schema_validation")
        if (
            set(document)
            != {
                "schema_version",
                "arguments_sha256",
                "schema_validation",
            }
            or document.get("schema_version") != _PROVIDER_DIAGNOSTIC_VERSION
            or not isinstance(arguments_sha256, str)
            or _SHA256_RE.fullmatch(arguments_sha256) is None
            or not isinstance(schema_validation, Mapping)
        ):
            raise ValueError(
                "visual symbol provider diagnostic is invalid"
            ) from None
        return {
            "schema_version": _PROVIDER_DIAGNOSTIC_VERSION,
            "arguments_sha256": arguments_sha256,
            "schema_validation": validate_visual_schema_diagnostic(
                schema_validation
            ),
        }


def _response_member(value: Any, name: str) -> Any:
    try:
        return getattr(value, name)
    except (AttributeError, IndexError, TypeError):
        return _MISSING_RESPONSE_MEMBER


def parse_candidate_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(instance=payload, schema=schema)
    except (
        json.JSONDecodeError,
        jsonschema.SchemaError,
        jsonschema.ValidationError,
        OSError,
        TypeError,
    ) as exc:
        raise CandidateSchemaError("candidate response failed frozen schema") from exc
    if not isinstance(payload, dict):
        raise CandidateSchemaError("candidate response must be one JSON object")
    return payload


def _usage_dict(usage: Any) -> dict[str, int]:
    if isinstance(usage, Mapping):
        raw = dict(usage)
    elif hasattr(usage, "model_dump"):
        raw = usage.model_dump()
    else:
        raw = {}
    return {
        str(key): int(value)
        for key, value in raw.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _visual_symbol_tool() -> dict[str, Any]:
    schema = json.loads(VISUAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError("visual symbol response schema must be one object")
    return {
        "type": "function",
        "function": {
            "name": VISUAL_TOOL_NAME,
            "description": (
                "Return the frozen visual symbol review object for this crop."
            ),
            "parameters": schema,
        },
    }


def _normalize_qwen_native_visual_payload(
    arguments: str,
) -> str | dict[str, Any]:
    try:
        payload = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return arguments
    if not isinstance(payload, dict):
        return arguments
    detections = payload.get("detections")
    if not isinstance(detections, list):
        return payload
    if "schema_version" not in payload:
        payload["schema_version"] = VISUAL_SCHEMA_VERSION
    for detection in detections:
        if not isinstance(detection, dict):
            continue
        bbox = detection.get("bbox_normalized")
        if (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(type(value) is int for value in bbox)
            and all(0 <= value <= 1000 for value in bbox)
            and any(value > 1 for value in bbox)
        ):
            detection["bbox_normalized"] = [
                value / 1000
                for value in bbox
            ]
    return payload


def canonicalize_visual_png(image: bytes) -> bytes:
    if (
        not isinstance(image, bytes)
        or len(image) < 57
        or len(image) > _MAX_VISUAL_PNG_BYTES
        or image[:8] != _PNG_SIGNATURE
    ):
        raise VisualSymbolInputError(
            "visual symbol input must be one bounded PNG crop"
        )
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    position = len(_PNG_SIGNATURE)
    seen_ihdr = False
    seen_idat = False
    seen_iend = False
    while position < len(image):
        if len(image) - position < 12:
            break
        chunk_length = int.from_bytes(image[position : position + 4], "big")
        chunk_type = image[position + 4 : position + 8]
        chunk_end = position + 12 + chunk_length
        if (
            len(chunk_type) != 4
            or not all(
                65 <= value <= 90 or 97 <= value <= 122
                for value in chunk_type
            )
            or chunk_end > len(image)
        ):
            break
        chunk_data = image[position + 8 : position + 8 + chunk_length]
        expected_crc = int.from_bytes(
            image[position + 8 + chunk_length : chunk_end],
            "big",
        )
        if expected_crc != zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF:
            break
        if not seen_ihdr:
            if chunk_type != b"IHDR" or chunk_length != 13:
                break
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            if (
                width <= 0
                or height <= 0
                or width > _MAX_VISUAL_PNG_SIDE
                or height > _MAX_VISUAL_PNG_SIDE
                or bit_depth not in valid_depths.get(color_type, set())
                or chunk_data[10] != 0
                or chunk_data[11] != 0
                or chunk_data[12] not in (0, 1)
            ):
                break
            seen_ihdr = True
        elif chunk_type == b"IHDR":
            break
        elif chunk_type == b"IDAT":
            seen_idat = True
        elif chunk_type == b"IEND":
            if seen_iend or chunk_length != 0:
                break
            seen_iend = True
            position = chunk_end
            break
        position = chunk_end
    if (
        not seen_ihdr
        or not seen_idat
        or not seen_iend
        or position != len(image)
    ):
        raise VisualSymbolInputError(
            "visual symbol input must be one bounded PNG crop"
        )
    try:
        with Image.open(BytesIO(image)) as decoded:
            if (
                decoded.format != "PNG"
                or decoded.size != (width, height)
                or decoded.mode
                not in {"1", "L", "LA", "P", "RGB", "RGBA"}
            ):
                raise ValueError("unsupported PNG")
            decoded.load()
            target_mode = (
                "RGBA"
                if "A" in decoded.getbands()
                or "transparency" in decoded.info
                else "RGB"
            )
            clean = decoded.convert(target_mode)
            output = BytesIO()
            clean.save(output, format="PNG", compress_level=9)
            canonical = output.getvalue()
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError):
        raise VisualSymbolInputError(
            "visual symbol input must be one bounded PNG crop"
        ) from None
    if len(canonical) > _MAX_VISUAL_PNG_BYTES:
        raise VisualSymbolInputError(
            "visual symbol input must be one bounded PNG crop"
        )
    return canonical


def validate_visual_request_metadata(
    request_id: Any,
    usage: Any,
) -> tuple[str, dict[str, int]]:
    if (
        not isinstance(request_id, str)
        or _SAFE_VISUAL_REQUEST_ID.fullmatch(request_id) is None
        or _FORBIDDEN_METADATA.search(request_id) is not None
    ):
        raise VisualSymbolMetadataError(
            "visual symbol response metadata is invalid"
        )
    if isinstance(usage, Mapping):
        raw_usage = dict(usage)
    elif hasattr(usage, "model_dump"):
        raw_usage = usage.model_dump()
    else:
        raw_usage = {}
    if not isinstance(raw_usage, Mapping) or any(
        not isinstance(key, str)
        or _FORBIDDEN_METADATA.search(key) is not None
        for key in raw_usage
    ):
        raise VisualSymbolMetadataError(
            "visual symbol response metadata is invalid"
        )
    counters: dict[str, int] = {}
    for key, value in raw_usage.items():
        if _SAFE_USAGE_KEY.fullmatch(key) is not None:
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise VisualSymbolMetadataError(
                    "visual symbol response metadata is invalid"
                )
            counters[key] = value
            continue
        if key in {
            "completion_tokens_details",
            "prompt_tokens_details",
        }:
            continue
        raise VisualSymbolMetadataError(
            "visual symbol response metadata is invalid"
        )
    return request_id, counters


class QwenVisionProvider:
    def __init__(self, client: Any, model: str = "qwen3-vl-plus") -> None:
        self._client = client
        self._model = model

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        localized_failure_category: str | None = None
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                            {
                                "type": "text",
                                "text": prompt + "\nOutput in JSON format.",
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
        except (APITimeoutError, TimeoutError):
            localized_failure_category = "timeout"
        except (APIConnectionError, ConnectionError, OSError):
            localized_failure_category = "transport"
        if localized_failure_category is not None:
            raise LocalizedProviderFailure(localized_failure_category)
        schema_failure = False
        try:
            request_id = getattr(completion, "id", None)
            if not isinstance(request_id, str) or not request_id.strip():
                raise CandidateSchemaError(
                    "candidate response is missing request ID"
                )
            try:
                content = completion.choices[0].message.content
            except (AttributeError, IndexError, TypeError) as exc:
                raise CandidateSchemaError(
                    "candidate response is missing message content"
                ) from exc
            if not isinstance(content, str):
                raise CandidateSchemaError(
                    "candidate response content must be JSON text"
                )
            return VisionResult(
                request_id=request_id,
                payload=parse_candidate_json(content),
                usage=_usage_dict(completion.usage),
            )
        except CandidateSchemaError:
            schema_failure = True
        if schema_failure:
            raise LocalizedProviderFailure("schema")
        raise AssertionError("candidate schema failure was not raised")

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        canonical_image = canonicalize_visual_png(image)
        if canonicalize_visual_png(canonical_image) != canonical_image:
            raise VisualSymbolInputError(
                "visual symbol input must be one bounded PNG crop"
            )
        data_url = "data:image/png;base64," + base64.b64encode(
            canonical_image
        ).decode("ascii")
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": VISUAL_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    },
                ],
                tools=[_visual_symbol_tool()],
                tool_choice={
                    "type": "function",
                    "function": {"name": VISUAL_TOOL_NAME},
                },
                parallel_tool_calls=False,
                temperature=0,
                extra_body={"enable_thinking": False},
            )
        except (APITimeoutError, TimeoutError):
            raise LocalizedProviderFailure("timeout") from None
        except (APIConnectionError, ConnectionError, OSError):
            raise LocalizedProviderFailure("transport") from None
        request_id, usage = validate_visual_request_metadata(
            getattr(completion, "id", None),
            getattr(completion, "usage", None),
        )
        choices = _response_member(completion, "choices")
        if not isinstance(choices, (list, tuple)) or not choices:
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="message_shape_invalid",
            ) from None
        message = _response_member(choices[0], "message")
        content = _response_member(message, "content")
        if (
            message is _MISSING_RESPONSE_MEMBER
            or content is _MISSING_RESPONSE_MEMBER
        ):
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="message_shape_invalid",
            ) from None
        if content not in (None, ""):
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="message_content_invalid",
            ) from None

        tool_calls = _response_member(message, "tool_calls")
        if not isinstance(tool_calls, (list, tuple)):
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="tool_calls_shape_invalid",
            ) from None
        if len(tool_calls) != 1:
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="tool_call_count_invalid",
            ) from None

        tool_call = tool_calls[0]
        tool_call_type = _response_member(tool_call, "type")
        function = _response_member(tool_call, "function")
        function_name = _response_member(function, "name")
        arguments = _response_member(function, "arguments")
        if any(
            value is _MISSING_RESPONSE_MEMBER
            for value in (
                tool_call_type,
                function,
                function_name,
                arguments,
            )
        ):
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="tool_call_shape_invalid",
            ) from None
        if tool_call_type != "function":
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="tool_call_type_invalid",
            ) from None
        if function_name != VISUAL_TOOL_NAME:
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="tool_name_invalid",
            ) from None
        if not isinstance(arguments, str):
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage="tool_arguments_type_invalid",
            ) from None

        parser_failure_stage = None
        parser_diagnostic = None
        try:
            payload = parse_visual_symbol_json(
                _normalize_qwen_native_visual_payload(arguments)
            )
        except VisualSymbolSchemaError as exc:
            parser_failure_stage = exc.failure_stage
            parser_diagnostic = exc.diagnostic
        if parser_failure_stage is not None:
            failure_stage: VisualSymbolFailureStage
            if parser_failure_stage == "json_invalid":
                failure_stage = "tool_arguments_json_invalid"
            elif parser_failure_stage == "schema_invalid":
                failure_stage = "tool_arguments_schema_invalid"
            else:
                failure_stage = "local_schema_invalid"
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
                failure_stage=failure_stage,
                diagnostic=(
                    {
                        "schema_version": _PROVIDER_DIAGNOSTIC_VERSION,
                        "arguments_sha256": hashlib.sha256(
                            arguments.encode("utf-8", errors="surrogatepass")
                        ).hexdigest(),
                        "schema_validation": parser_diagnostic,
                    }
                    if (
                        failure_stage == "tool_arguments_schema_invalid"
                        and parser_diagnostic is not None
                    )
                    else None
                ),
            ) from None
        return VisionResult(
            request_id=request_id,
            payload=payload,
            usage=usage,
        )
