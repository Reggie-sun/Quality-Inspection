from __future__ import annotations

import base64
import json
import re
import zlib
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

import jsonschema
from PIL import Image, UnidentifiedImageError

from app.providers.base import VisionResult
from app.candidates.symbol_review import (
    VisualSymbolSchemaError,
    parse_visual_symbol_json,
)


SCHEMA_PATH = Path(__file__).with_name("candidate_review.schema.json")
SYSTEM_PROMPT = "Review one engineering annotation crop. Output JSON only."
VISUAL_SYSTEM_PROMPT = (
    "Review local engineering drawing symbol contexts. Output JSON only."
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


class CandidateSchemaError(ValueError):
    pass


class VisualSymbolInputError(ValueError):
    pass


class VisualSymbolMetadataError(ValueError):
    pass


class VisualSymbolProviderError(RuntimeError):
    def __init__(self, *, request_id: str, usage: dict[str, int]) -> None:
        super().__init__("visual symbol response violates frozen schema")
        self.request_id, self.usage = validate_visual_request_metadata(
            request_id,
            usage,
        )


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
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
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
        request_id = getattr(completion, "id", None)
        if not isinstance(request_id, str) or not request_id.strip():
            raise CandidateSchemaError("candidate response is missing request ID")
        try:
            content = completion.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise CandidateSchemaError(
                "candidate response is missing message content"
            ) from exc
        if not isinstance(content, str):
            raise CandidateSchemaError("candidate response content must be JSON text")
        return VisionResult(
            request_id=request_id,
            payload=parse_candidate_json(content),
            usage=_usage_dict(completion.usage),
        )

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        canonical_image = canonicalize_visual_png(image)
        if canonicalize_visual_png(canonical_image) != canonical_image:
            raise VisualSymbolInputError(
                "visual symbol input must be one bounded PNG crop"
            )
        data_url = "data:image/png;base64," + base64.b64encode(
            canonical_image
        ).decode("ascii")
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
                            "text": prompt + "\nOutput in JSON format.",
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )
        request_id, usage = validate_visual_request_metadata(
            getattr(completion, "id", None),
            getattr(completion, "usage", None),
        )
        try:
            content = completion.choices[0].message.content
            if not isinstance(content, str):
                raise TypeError("content")
            payload = parse_visual_symbol_json(content)
        except (
            AttributeError,
            IndexError,
            TypeError,
            VisualSymbolSchemaError,
        ):
            raise VisualSymbolProviderError(
                request_id=request_id,
                usage=usage,
            ) from None
        return VisionResult(
            request_id=request_id,
            payload=payload,
            usage=usage,
        )
