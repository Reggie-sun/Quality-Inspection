import base64
import json
from types import SimpleNamespace

import pytest

from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.providers.qwen_vl import (
    CandidateSchemaError,
    QwenVisionProvider,
    parse_candidate_json,
)
from app.providers.runtime import build_vision_provider


def test_rejects_invalid_or_schema_incomplete_json() -> None:
    """P0-REC-005: invalid Advisor JSON never becomes a candidate suggestion."""
    with pytest.raises(CandidateSchemaError):
        parse_candidate_json("not-json")
    with pytest.raises(CandidateSchemaError):
        parse_candidate_json('{"item_type":"thread"}')


def test_valid_fixture_matches_frozen_advisor_schema(qwen_fixture: dict) -> None:
    """P0-REC-005: sanitized Qwen fixture satisfies the frozen Advisor schema."""
    payload = parse_candidate_json(qwen_fixture["content"])

    assert payload == {
        "schema_version": "candidate-review/1",
        "raw_text": "M6深10",
        "item_type": "thread",
        "normalized_text": "M6 depth 10",
        "requires_confirmation": True,
    }


def test_candidate_schema_rejects_formal_owner_fields(qwen_fixture: dict) -> None:
    """P0-REC-005: Advisor output cannot own formal disposition or review state."""
    payload = json.loads(qwen_fixture["content"])
    payload["disposition"] = "keep"

    with pytest.raises(CandidateSchemaError):
        parse_candidate_json(json.dumps(payload))


def test_qwen_request_shape_is_exact(qwen_fixture: dict) -> None:
    """P0-REC-005: Qwen adapter pins non-thinking JSON-only crop review."""

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                id=qwen_fixture["request_id"],
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=qwen_fixture["content"])
                    )
                ],
                usage=SimpleNamespace(
                    model_dump=lambda: dict(qwen_fixture["usage"])
                ),
            )

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    image = b"\x89PNG\r\ncontrolled-candidate-crop"
    prompt = "Classify this local annotation."

    result = QwenVisionProvider(client).review_candidate(image, prompt)

    data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    assert completions.calls == [
        {
            "model": "qwen3-vl-plus",
            "messages": [
                {
                    "role": "system",
                    "content": "Review one engineering annotation crop. Output JSON only.",
                },
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
            "response_format": {"type": "json_object"},
            "extra_body": {"enable_thinking": False},
        }
    ]
    assert result.request_id == qwen_fixture["request_id"]
    assert result.payload == json.loads(qwen_fixture["content"])
    assert result.usage == qwen_fixture["usage"]


def test_qwen_response_requires_non_empty_request_id(qwen_fixture: dict) -> None:
    """P0-REC-005: incomplete Advisor responses fail before returning a result."""

    class MissingIdCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id=None,
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=qwen_fixture["content"])
                    )
                ],
                usage=qwen_fixture["usage"],
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=MissingIdCompletions())
    )

    with pytest.raises(CandidateSchemaError, match="request ID"):
        QwenVisionProvider(client).review_candidate(b"controlled", "Review")


def test_runtime_factory_builds_beijing_workspace_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("app.providers.runtime.OpenAI", FakeOpenAI)
    provider = build_vision_provider(
        Settings(
            qwen_api_key="test-only-key",
            qwen_workspace_id="ws-test-123",
            qwen_model="qwen3-vl-plus",
        )
    )

    assert isinstance(provider, QwenVisionProvider)
    assert captured == {
        "api_key": "test-only-key",
        "base_url": (
            "https://ws-test-123.cn-beijing.maas.aliyuncs.com/"
            "compatible-mode/v1"
        ),
        "timeout": 60.0,
        "max_retries": 0,
    }


@pytest.mark.parametrize(
    "workspace_id",
    (None, "", ".invalid", "invalid.example.com", "invalid/path"),
)
def test_runtime_factory_rejects_missing_or_unsafe_workspace(
    workspace_id: str | None,
) -> None:
    with pytest.raises(
        CapabilityUnavailable,
        match="Vision Provider configuration is unavailable",
    ):
        build_vision_provider(
            Settings(
                qwen_api_key="test-only-key",
                qwen_workspace_id=workspace_id,
            )
        )
