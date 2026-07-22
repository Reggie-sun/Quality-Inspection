from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jsonschema

from app.providers.base import VisionResult


SCHEMA_PATH = Path(__file__).with_name("candidate_review.schema.json")
SYSTEM_PROMPT = "Review one engineering annotation crop. Output JSON only."


class CandidateSchemaError(ValueError):
    pass


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
