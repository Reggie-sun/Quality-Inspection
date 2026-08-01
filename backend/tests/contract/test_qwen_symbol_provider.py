from __future__ import annotations

import base64
import hashlib
import json
import zlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from openai import APIConnectionError, APITimeoutError
from openai.types.completion_usage import CompletionUsage
from PIL import Image

import app.candidates.symbol_review as symbol_review
from app.candidates.symbol_review import (
    VISUAL_ADAPTER_VERSION,
    VISUAL_PROMPT_VERSION,
    VISUAL_SCHEMA_VERSION,
    visual_cache_key,
    visual_review_prompt,
)
from app.pdf.gdt_frames import GdtCellObservation, GdtFrameObservation
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import PROPOSAL_RULE_VERSION
from app.providers.qwen_vl import (
    QwenVisionProvider,
    VisualSymbolInputError,
    VisualSymbolMetadataError,
    VisualSymbolProviderError,
    canonicalize_visual_png,
    validate_visual_request_metadata,
)
from app.providers.base import LocalizedProviderFailure


_VISUAL_TOOL_NAME = "submit_visual_symbol_review"


@pytest.mark.parametrize(
    ("provider_error", "failure_category"),
    (
        (
            APITimeoutError(
                request=httpx.Request("POST", "https://qwen.example/v1")
            ),
            "timeout",
        ),
        (
            TimeoutError("private timeout detail"),
            "timeout",
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://qwen.example/v1")
            ),
            "transport",
        ),
        (ConnectionError("private connection detail"), "transport"),
        (OSError("private socket detail"), "transport"),
    ),
)
def test_qwen_candidate_provider_localizes_transport_failures(
    provider_error: Exception,
    failure_category: str,
) -> None:
    class FailingCompletions:
        def create(self, **_kwargs):
            raise provider_error

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=FailingCompletions())
        )
    )

    with pytest.raises(LocalizedProviderFailure) as raised:
        provider.review_candidate(_png(text=None), "safe prompt")

    assert raised.value.failure_category == failure_category
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_qwen_candidate_provider_localizes_malformed_response() -> None:
    class MalformedCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                id="fixture-qwen-malformed",
                choices=[SimpleNamespace(message=SimpleNamespace(content="{"))],
                usage={"total_tokens": 4},
            )

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=MalformedCompletions())
        )
    )

    with pytest.raises(LocalizedProviderFailure) as raised:
        provider.review_candidate(_png(text=None), "safe prompt")

    assert raised.value.failure_category == "schema"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def _png_chunk(kind: bytes, content: bytes) -> bytes:
    return (
        len(content).to_bytes(4, "big")
        + kind
        + content
        + (zlib.crc32(kind + content) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def _png_header(width: int, height: int) -> bytes:
    return (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )


def _png(
    width: int = 32,
    height: int = 24,
    *,
    text: bytes | None = b"note\x00synthetic",
) -> bytes:
    scanlines = (b"\x00" + b"\x00" * (width * 3)) * height
    chunks = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", _png_header(width, height))
    )
    if text is not None:
        chunks += _png_chunk(b"tEXt", text)
    return (
        chunks
        + _png_chunk(b"IDAT", zlib.compress(scanlines))
        + _png_chunk(b"IEND", b"")
    )


def _text_observation(
    observation_id: str,
    raw_text: str,
    *,
    observation_level: str,
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native",
        observation_level=observation_level,
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=0,
        bbox_pdf=(20.0, 20.0, 40.0, 30.0),
        bbox_normalized=(0.2, 0.2, 0.4, 0.3),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )


def _visual_observation(
    observation_id: str,
    bbox_pdf: tuple[float, float, float, float],
    associated_text_observation_ids: tuple[str, ...],
) -> VisualObservation:
    return VisualObservation(
        observation_id=observation_id,
        source_type="visual",
        observation_level="annotation_context",
        page_index=0,
        bbox_pdf=bbox_pdf,
        bbox_normalized=bbox_pdf,
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256="a" * 64,
        associated_text_observation_ids=associated_text_observation_ids,
    )


def _visual_tool_call(
    arguments: object,
    *,
    name: str = _VISUAL_TOOL_NAME,
    call_type: str = "function",
) -> SimpleNamespace:
    return SimpleNamespace(
        type=call_type,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def test_qwen_visual_symbol_sampling_temperature_is_pinned_to_zero() -> None:
    class SamplingCompletions:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                id="fixture-qwen-sampling",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(
                                    json.dumps(
                                        {
                                            "schema_version": (
                                                "visual-symbol-review/3"
                                            ),
                                            "detections": [],
                                            "gdt_frames": [],
                                        }
                                    )
                                )
                            ],
                        )
                    )
                ],
                usage={"total_tokens": 4},
            )

    completions = SamplingCompletions()
    QwenVisionProvider(
        SimpleNamespace(chat=SimpleNamespace(completions=completions))
    ).review_symbols(_png(text=None), "safe prompt")

    sampling_keys = {
        "temperature",
        "top_p",
        "seed",
        "frequency_penalty",
        "presence_penalty",
        "logprobs",
    }
    assert {
        key: value
        for key, value in completions.calls[0].items()
        if key in sampling_keys
    } == {"temperature": 0}
    assert VISUAL_SCHEMA_VERSION == "visual-symbol-review/3"


def test_qwen_visual_symbol_failure_stage_enum_is_exhaustive_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_arguments = json.dumps(
        {
            "schema_version": "visual-symbol-review/3",
            "detections": [],
            "gdt_frames": [],
        }
    )
    private_marker = "private-marker-provider-response"
    image = _png(text=None)

    class FixedCompletions:
        def __init__(self, completion: object) -> None:
            self.completion = completion

        def create(self, **_kwargs):
            return self.completion

    def completion(message: object) -> SimpleNamespace:
        return SimpleNamespace(
            id="fixture-qwen-safe-stage",
            choices=[SimpleNamespace(message=message)],
            usage={"total_tokens": 4},
        )

    valid_tool_call = _visual_tool_call(valid_arguments)
    cases = (
        (
            SimpleNamespace(
                id="fixture-qwen-safe-stage",
                choices=[],
                usage={"total_tokens": 4},
            ),
            "message_shape_invalid",
        ),
        (
            completion(
                SimpleNamespace(tool_calls=[valid_tool_call])
            ),
            "message_shape_invalid",
        ),
        (
            completion(
                SimpleNamespace(content=None)
            ),
            "tool_calls_shape_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=private_marker,
                    tool_calls=[valid_tool_call],
                )
            ),
            "message_content_invalid",
        ),
        (
            completion(
                SimpleNamespace(content=None, tool_calls=None)
            ),
            "tool_calls_shape_invalid",
        ),
        (
            completion(
                SimpleNamespace(content=None, tool_calls=[])
            ),
            "tool_call_count_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[valid_tool_call, valid_tool_call],
                )
            ),
            "tool_call_count_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[SimpleNamespace(type="function")],
                )
            ),
            "tool_call_shape_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            type="function",
                            function=SimpleNamespace(
                                name=_VISUAL_TOOL_NAME
                            ),
                        )
                    ],
                )
            ),
            "tool_call_shape_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[
                        _visual_tool_call(
                            valid_arguments,
                            call_type="not-function",
                        )
                    ],
                )
            ),
            "tool_call_type_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[
                        _visual_tool_call(
                            valid_arguments,
                            name="wrong_visual_tool",
                        )
                    ],
                )
            ),
            "tool_name_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[
                        _visual_tool_call({"not": "json text"})
                    ],
                )
            ),
            "tool_arguments_type_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[
                        _visual_tool_call(private_marker)
                    ],
                )
            ),
            "tool_arguments_json_invalid",
        ),
        (
            completion(
                SimpleNamespace(
                    content=None,
                    tool_calls=[
                        _visual_tool_call(
                            json.dumps(
                                {
                                    "schema_version": (
                                        "visual-symbol-review/2"
                                    ),
                                    "detections": [
                                        {"private": private_marker}
                                    ],
                                }
                            )
                        )
                    ],
                )
            ),
            "tool_arguments_schema_invalid",
        ),
    )

    for provider_completion, expected_stage in cases:
        provider = QwenVisionProvider(
            SimpleNamespace(
                chat=SimpleNamespace(
                    completions=FixedCompletions(
                        provider_completion
                    )
                )
            )
        )
        with pytest.raises(VisualSymbolProviderError) as raised:
            provider.review_symbols(image, "safe-stage-prompt")
        assert raised.value.failure_stage == expected_stage
        assert raised.value.request_id == "fixture-qwen-safe-stage"
        assert raised.value.usage == {"total_tokens": 4}
        assert str(raised.value) == (
            "visual symbol response violates frozen schema"
        )
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert private_marker not in str(raised.value)

    missing_schema = tmp_path / "missing-visual-symbol.schema.json"
    monkeypatch.setattr(symbol_review, "SCHEMA_PATH", missing_schema)
    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=FixedCompletions(
                    completion(
                        SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(valid_arguments)
                            ],
                        )
                    )
                )
            )
        )
    )
    with pytest.raises(VisualSymbolProviderError) as raised:
        provider.review_symbols(image, "safe-stage-prompt")
    assert raised.value.failure_stage == "local_schema_invalid"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.parametrize(
    ("failure_kind", "expected_category"),
    (
        ("timeout", "timeout"),
        ("transport", "transport"),
        ("schema", "schema"),
    ),
)
def test_qwen_localized_failures_expose_sanitized_stable_categories(
    failure_kind: str,
    expected_category: str,
) -> None:
    """PRT-5 classifies local Provider failures without leaking raw detail."""
    private_marker = "/srv/private/customer.pdf token=do-not-leak"

    class LocalizedFailureCompletions:
        @staticmethod
        def create(**_kwargs):
            if failure_kind == "timeout":
                raise TimeoutError(private_marker)
            if failure_kind == "transport":
                raise ConnectionError(private_marker)
            return SimpleNamespace(
                id="fixture-qwen-localized-schema",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(
                                    json.dumps(
                                        {
                                            "schema_version": (
                                                "visual-symbol-review/2"
                                            ),
                                            "detections": [
                                                {"private": private_marker}
                                            ],
                                        }
                                    )
                                )
                            ],
                        )
                    )
                ],
                usage={"total_tokens": 4},
            )

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=LocalizedFailureCompletions()
            )
        )
    )
    failure: Exception | None = None
    try:
        provider.review_symbols(_png(text=None), "safe prompt")
    except Exception as exc:
        failure = exc

    assert failure is not None
    category = getattr(
        failure,
        "failure_category",
        getattr(failure, "category", None),
    )
    assert category == expected_category
    assert private_marker not in str(failure)
    assert private_marker not in repr(vars(failure))


def test_qwen_schema_failure_exposes_only_hashed_safe_diagnostic() -> None:
    private_marker = "private-marker-provider-response"
    arguments = json.dumps(
        {
            "schema_version": "visual-symbol-review/3",
            "detections": [
                {
                    "visual_observation_id": "visual-001",
                    "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
                    "associated_text_observation_ids": [private_marker],
                    "confidence_signal": 0.98,
                }
            ],
            "gdt_frames": [],
        }
    )

    class InvalidCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="fixture-qwen-schema-diagnostic",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[_visual_tool_call(arguments)],
                        )
                    )
                ],
                usage={"prompt_tokens": 3, "completion_tokens": 1},
            )

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=InvalidCompletions())
        )
    )
    with pytest.raises(VisualSymbolProviderError) as raised:
        provider.review_symbols(_png(text=None), "safe prompt")

    assert raised.value.failure_stage == "tool_arguments_schema_invalid"
    assert raised.value.diagnostic == {
        "schema_version": "visual-symbol-provider-diagnostic/1",
        "arguments_sha256": hashlib.sha256(arguments.encode()).hexdigest(),
        "schema_validation": {
            "schema_version": "visual-symbol-schema-diagnostic/1",
            "validator": "required",
            "instance_path": "/detections/0",
            "schema_path": "/properties/detections/items/required",
            "instance_type": "object",
            "required_member": "symbol_kind",
            "schema_sha256": (
                "cb4ee4ce69568b863dd8a2b5b1e96112"
                "59b2284fe47859f83246f8b6fb39767a"
            ),
        },
    }
    assert private_marker not in repr(raised.value.diagnostic)
    assert private_marker not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_qwen_native_integer_bbox_is_normalized_before_strict_schema() -> None:
    image = _png(text=None)

    def provider_for(payload: dict[str, object]) -> QwenVisionProvider:
        class FixedCompletions:
            @staticmethod
            def create(**_kwargs):
                return SimpleNamespace(
                    id="fixture-qwen-native-bbox",
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    _visual_tool_call(
                                        json.dumps(payload)
                                    )
                                ],
                            )
                        )
                    ],
                    usage={"total_tokens": 4},
                )

        return QwenVisionProvider(
            SimpleNamespace(
                chat=SimpleNamespace(completions=FixedCompletions())
            )
        )

    canonical_detection = {
        "visual_observation_id": "visual-001",
        "symbol_kind": "diameter",
        "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
        "associated_text_observation_ids": ["text-001"],
        "confidence_signal": 0.98,
    }
    canonical = {
        "schema_version": "visual-symbol-review/3",
        "detections": [canonical_detection],
        "gdt_frames": [],
    }
    assert (
        provider_for(canonical).review_symbols(image, "safe prompt").payload
        == canonical
    )

    qwen_native = {
        **canonical,
        "detections": [
            {
                **canonical_detection,
                "bbox_normalized": [100, 200, 300, 400],
            }
        ],
    }
    assert provider_for(qwen_native).review_symbols(
        image,
        "safe prompt",
    ).payload == canonical


def test_qwen_missing_structural_schema_version_is_normalized() -> None:
    canonical = {
        "schema_version": "visual-symbol-review/3",
        "detections": [],
        "gdt_frames": [],
    }
    qwen_native = {"detections": [], "gdt_frames": []}

    class FixedCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="fixture-qwen-missing-schema-version",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(json.dumps(qwen_native))
                            ],
                        )
                    )
                ],
                usage={"total_tokens": 4},
            )

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=FixedCompletions())
        )
    )

    assert provider.review_symbols(
        _png(text=None),
        "safe prompt",
    ).payload == canonical


@pytest.mark.parametrize(
    "qwen_native",
    (
        {"schema_version": None, "detections": []},
        {"schema_version": "visual-symbol-review/3", "detections": []},
        {"schema_version": "visual-symbol-review/2"},
        {"schema_version": "visual-symbol-review/2", "detections": {}},
        {
            "schema_version": "visual-symbol-review/2",
            "detections": [],
            "unexpected": True,
        },
    ),
)
def test_qwen_structural_normalization_preserves_other_schema_failures(
    qwen_native: dict[str, object],
) -> None:
    class InvalidCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="fixture-qwen-invalid-structural-field",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(json.dumps(qwen_native))
                            ],
                        )
                    )
                ],
                usage={"total_tokens": 4},
            )

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=InvalidCompletions())
        )
    )
    with pytest.raises(VisualSymbolProviderError) as raised:
        provider.review_symbols(_png(text=None), "safe prompt")

    assert raised.value.failure_stage == "tool_arguments_schema_invalid"


@pytest.mark.parametrize(
    "bbox",
    (
        [-1, 0, 500, 800],
        [0, 0, 500, 1001],
        [0, 0, 500.5, 800],
        [0, 0.5, 500, 800],
        [False, 0, 500, 800],
        [0, 0, 500],
    ),
)
def test_qwen_native_bbox_normalization_rejects_other_invalid_forms(
    bbox: list[object],
) -> None:
    payload = {
        "schema_version": "visual-symbol-review/3",
        "detections": [
            {
                "visual_observation_id": "visual-001",
                "symbol_kind": "diameter",
                "bbox_normalized": bbox,
                "associated_text_observation_ids": ["text-001"],
                "confidence_signal": 0.98,
            }
        ],
        "gdt_frames": [],
    }

    class InvalidCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="fixture-qwen-invalid-native-bbox",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(json.dumps(payload))
                            ],
                        )
                    )
                ],
                usage={"total_tokens": 4},
            )

    provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=InvalidCompletions())
        )
    )
    with pytest.raises(VisualSymbolProviderError) as raised:
        provider.review_symbols(_png(text=None), "safe prompt")

    assert raised.value.failure_stage == "tool_arguments_schema_invalid"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_visual_prompt_requires_independent_exact_multikind_reporting() -> None:
    prompt = json.loads(
        visual_review_prompt(
            (
                _visual_observation(
                    "visual-composite-001",
                    (20.0, 40.0, 60.0, 70.0),
                    ("text-line-001",),
                ),
            ),
            text_observations={
                "text-line-001": _text_observation(
                    "text-line-001",
                    "⌴Φ20↧10",
                    observation_level="line",
                )
            },
            crop_bbox_pdf=(10.0, 20.0, 110.0, 120.0),
        )
    )

    assert prompt["prompt_version"] == "visual-symbol-prompt/4"
    assert prompt["detection_reporting_contract"] == [
        "Judge every visual context independently.",
        (
            "For each visible component whose kind is in symbol_kind_guide, "
            "emit one separate detection."
        ),
        (
            "If one context contains multiple components, emit multiple "
            "detections and reuse that context's visual_observation_id for "
            "every component."
        ),
        (
            "Never substitute a kind seen only in a neighboring visual "
            "context."
        ),
        (
            "Emit zero detections for a context only when no allowlisted "
            "symbol component is recognizable in that context."
        ),
    ]


def test_visual_prompt_includes_ordered_gdt_frame_context() -> None:
    frame = GdtFrameObservation(
        observation_id="frame-a",
        page_index=0,
        bbox_pdf=(20.0, 40.0, 90.0, 60.0),
        bbox_normalized=(0.2, 0.4, 0.9, 0.6),
        cells=(
            GdtCellObservation(0, (20.0, 40.0, 40.0, 60.0), (0.2, 0.4, 0.4, 0.6)),
            GdtCellObservation(1, (40.0, 40.0, 65.0, 60.0), (0.4, 0.4, 0.65, 0.6)),
            GdtCellObservation(2, (65.0, 40.0, 90.0, 60.0), (0.65, 0.4, 0.9, 0.6)),
        ),
        associated_text_observation_ids=("text-line-001",),
        proposal_source="native_vector",
        proposal_state="complete",
        geometry_sha256="a" * 64,
    )
    prompt = json.loads(
        visual_review_prompt(
            (
                _visual_observation(
                    "visual-frame-a",
                    (20.0, 40.0, 90.0, 60.0),
                    ("text-line-001",),
                ),
            ),
            text_observations={
                "text-line-001": _text_observation(
                    "text-line-001",
                    "0.1 A",
                    observation_level="line",
                )
            },
            crop_bbox_pdf=(10.0, 20.0, 110.0, 120.0),
            gdt_frames=(frame,),
        )
    )

    assert prompt["gdt_frame_contexts"] == [
        {
            "frame_observation_id": "frame-a",
            "frame_bbox_normalized": [0.1, 0.2, 0.8, 0.4],
            "cells": [
                {"cell_index": 0, "bbox_normalized": [0.1, 0.2, 0.3, 0.4]},
                {"cell_index": 1, "bbox_normalized": [0.3, 0.2, 0.55, 0.4]},
                {"cell_index": 2, "bbox_normalized": [0.55, 0.2, 0.8, 0.4]},
            ],
            "associated_text_allowlist": [
                {
                    "observation_id": "text-line-001",
                    "observation_level": "line",
                    "raw_text": "0.1 A",
                }
            ],
        }
    ]


def test_qwen_visual_symbol_schema_and_cache_identity() -> None:
    """PROV-01: the visual request and every cache identity dimension are frozen."""
    fixture = json.loads(
        (
            Path(__file__).parents[3]
            / ".agent/harness/fixtures/providers/qwen-vl/"
            "visual-symbol-review-v2.json"
        ).read_text(encoding="utf-8")
    )
    qwen_symbol_fixture = fixture["payload"]
    fixture_response = json.loads(qwen_symbol_fixture["arguments"])
    fixture_response["schema_version"] = VISUAL_SCHEMA_VERSION
    fixture_response["gdt_frames"] = []
    qwen_symbol_fixture = {
        **qwen_symbol_fixture,
        "arguments": json.dumps(
            fixture_response,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    assert (
        fixture["adapter_version"]
        == VISUAL_ADAPTER_VERSION
        == "qwen-openai-compatible/5"
    )

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                id=qwen_symbol_fixture["request_id"],
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(
                                    qwen_symbol_fixture["arguments"]
                                )
                            ],
                        )
                    )
                ],
                usage=qwen_symbol_fixture["usage"],
            )

    completions = FakeCompletions()
    private_marker = b"private-marker-%PDF"
    image = _png(text=b"review\x00" + private_marker)
    texts = {
        "text-line-001": _text_observation(
            "text-line-001",
            "Φ20",
            observation_level="line",
        ),
        "text-span-001": _text_observation(
            "text-span-001",
            "Φ20",
            observation_level="span",
        ),
        "text-line-002": _text_observation(
            "text-line-002",
            "Ra 3.2",
            observation_level="line",
        ),
        "unrelated-text": _text_observation(
            "unrelated-text",
            "must-not-leave-the-allowlist",
            observation_level="line",
        ),
    }
    visuals = (
        _visual_observation(
            "visual-001",
            (20.0, 40.0, 40.0, 60.0),
            ("text-line-001", "text-span-001"),
        ),
        _visual_observation(
            "visual-002",
            (60.0, 80.0, 90.0, 110.0),
            ("text-line-002",),
        ),
    )
    prompt = visual_review_prompt(
        visuals,
        text_observations=texts,
        crop_bbox_pdf=(10.0, 20.0, 110.0, 120.0),
    )
    response_schema = json.loads(
        (
            Path(__file__).parents[2]
            / "app/providers/visual_symbol_review.schema.json"
        ).read_text(encoding="utf-8")
    )
    expected_prompt = {
        "task": "review_local_engineering_drawing_symbol_contexts",
        "prompt_version": "visual-symbol-prompt/4",
        "schema_version": "visual-symbol-review/3",
        "visual_observation_ids": ["visual-001", "visual-002"],
        "visual_contexts": [
            {
                "visual_observation_id": "visual-001",
                "context_bbox_normalized": [0.1, 0.2, 0.3, 0.4],
                "associated_text_allowlist": [
                    {
                        "observation_id": "text-line-001",
                        "observation_level": "line",
                        "raw_text": "Φ20",
                    },
                    {
                        "observation_id": "text-span-001",
                        "observation_level": "span",
                        "raw_text": "Φ20",
                    },
                ],
            },
            {
                "visual_observation_id": "visual-002",
                "context_bbox_normalized": [0.5, 0.6, 0.8, 0.9],
                "associated_text_allowlist": [
                    {
                        "observation_id": "text-line-002",
                        "observation_level": "line",
                        "raw_text": "Ra 3.2",
                    },
                ],
            },
        ],
        "gdt_frame_contexts": [],
        "symbol_kind_guide": {
            "diameter": "Φ/∅/⌀ beside a size value",
            "depth": "depth symbol beside a depth value",
            "counterbore": "counterbore symbol used with diameter and depth",
            "surface_roughness": "surface texture symbol beside a roughness value",
            "gdt_parallelism": "parallelism symbol in a feature-control frame",
            "gdt_perpendicularity": (
                "perpendicularity symbol in a feature-control frame"
            ),
            "gdt_flatness": "flatness symbol in a feature-control frame",
            "datum_reference": "boxed datum letter with its datum pointer",
            "revision_marker": "closed triangle containing a revision token",
        },
        "detection_reporting_contract": [
            "Judge every visual context independently.",
            (
                "For each visible component whose kind is in "
                "symbol_kind_guide, emit one separate detection."
            ),
            (
                "If one context contains multiple components, emit multiple "
                "detections and reuse that context's visual_observation_id "
                "for every component."
            ),
            (
                "Never substitute a kind seen only in a neighboring visual "
                "context."
            ),
            (
                "Emit zero detections for a context only when no allowlisted "
                "symbol component is recognizable in that context."
            ),
        ],
        "constraints": [
            "inspect_each_listed_visual_context",
            "use_only_listed_visual_observation_ids",
            (
                "use_only_associated_text_observation_ids_from_the_matching_"
                "visual_context"
            ),
            "emit_empty_gdt_frames_when_no_frame_is_present",
            "use_only_ordered_gdt_frame_cells_and_allowlisted_text_ids",
            "detection_bbox_normalized_is_relative_to_the_entire_crop",
            "detection_bbox_must_have_positive_width_and_height",
            "prefer_line_level_text_when_line_and_span_duplicate_raw_text",
            "return_no_detection_for_unrecognized_or_absent_symbols",
            "match_response_schema_exactly",
            "report_one_confidence_signal_between_zero_and_one",
            "return_one_json_object_only",
        ],
        "response_schema": response_schema,
    }
    assert json.loads(prompt) == expected_prompt
    assert "must-not-leave-the-allowlist" not in prompt
    assert prompt == json.dumps(
        expected_prompt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = QwenVisionProvider(
        SimpleNamespace(chat=SimpleNamespace(completions=completions))
    ).review_symbols(image, prompt)

    sent_data_url = completions.calls[0]["messages"][1]["content"][0][
        "image_url"
    ]["url"]
    assert sent_data_url.startswith("data:image/png;base64,")
    sent_image = base64.b64decode(
        sent_data_url.removeprefix("data:image/png;base64,")
    )
    assert private_marker not in sent_image
    assert b"%PDF" not in sent_image
    assert sent_image != image
    assert canonicalize_visual_png(sent_image) == sent_image
    with Image.open(BytesIO(image)) as original, Image.open(
        BytesIO(sent_image)
    ) as canonical:
        original.load()
        canonical.load()
        assert canonical.format == "PNG"
        assert canonical.size == original.size == (32, 24)
        assert canonical.info == {}
        assert canonical.convert("RGBA").tobytes() == original.convert(
            "RGBA"
        ).tobytes()
    data_url = "data:image/png;base64," + base64.b64encode(sent_image).decode(
        "ascii"
    )
    assert completions.calls == [
        {
            "model": "qwen3-vl-plus",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Review local engineering drawing symbol contexts. "
                        "Call the reporting function exactly once."
                    ),
                },
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
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": _VISUAL_TOOL_NAME,
                        "description": (
                            "Return the frozen visual symbol review object "
                            "for this crop."
                        ),
                        "parameters": response_schema,
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": _VISUAL_TOOL_NAME},
            },
            "parallel_tool_calls": False,
            "temperature": 0,
            "extra_body": {"enable_thinking": False},
        }
    ]
    assert (
        completions.calls[0]["messages"][1]["content"][1]["text"]
        == prompt
    )
    assert result.payload == json.loads(qwen_symbol_fixture["arguments"])
    request_id, sdk_usage = validate_visual_request_metadata(
        "fixture-sdk-usage",
        CompletionUsage(
            prompt_tokens=20,
            completion_tokens=16,
            total_tokens=36,
        ),
    )
    assert request_id == "fixture-sdk-usage"
    assert sdk_usage == {
        "completion_tokens": 16,
        "prompt_tokens": 20,
        "total_tokens": 36,
    }

    baseline = {
        "source_sha256": "a" * 64,
        "visual_observation_ids": ("visual-001", "visual-002"),
        "crop_bbox_pdf": (10.0, 20.0, 30.0, 40.0),
        "crop_sha256": "b" * 64,
        "model": "qwen3-vl-plus",
        "prompt_version": VISUAL_PROMPT_VERSION,
        "schema_version": VISUAL_SCHEMA_VERSION,
        "adapter_version": VISUAL_ADAPTER_VERSION,
        "proposal_version": PROPOSAL_RULE_VERSION,
        "pymupdf_version": "1.26.0",
    }
    first = visual_cache_key(**baseline)
    variations = {
        "source_sha256": "c" * 64,
        "visual_observation_ids": ("visual-002", "visual-001"),
        "crop_bbox_pdf": (10.0, 20.0, 30.0, 41.0),
        "crop_sha256": "d" * 64,
        "model": "qwen3-vl-max",
        "prompt_version": "visual-symbol-prompt/2",
        "schema_version": "visual-symbol-review/1",
        "adapter_version": "qwen-openai-compatible/1",
        "proposal_version": "visual-observation/1",
        "pymupdf_version": "1.27.0",
    }
    assert len(first) == 64
    assert all(
        visual_cache_key(**(baseline | {field: value})) != first
        for field, value in variations.items()
    )

    invalid_body = "private-path credential model-explanation"

    class InvalidCompletions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="fixture-qwen-invalid-symbol",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _visual_tool_call(invalid_body)
                            ],
                        )
                    )
                ],
                usage={"total_tokens": 4},
            )

    invalid_provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=InvalidCompletions())
        )
    )
    with pytest.raises(VisualSymbolProviderError) as raised:
        invalid_provider.review_symbols(image, prompt)
    assert raised.value.request_id == "fixture-qwen-invalid-symbol"
    assert raised.value.usage == {"total_tokens": 4}
    assert raised.value.__cause__ is None
    assert invalid_body not in str(raised.value)

    invalid_tool_messages = (
        SimpleNamespace(content=None, tool_calls=[]),
        SimpleNamespace(
            content=None,
            tool_calls=[
                _visual_tool_call(qwen_symbol_fixture["arguments"]),
                _visual_tool_call(qwen_symbol_fixture["arguments"]),
            ],
        ),
        SimpleNamespace(
            content=None,
            tool_calls=[
                _visual_tool_call(
                    qwen_symbol_fixture["arguments"],
                    name="wrong_visual_tool",
                )
            ],
        ),
        SimpleNamespace(
            content=None,
            tool_calls=[
                _visual_tool_call(
                    qwen_symbol_fixture["arguments"],
                    call_type="not-function",
                )
            ],
        ),
        SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(type="function")],
        ),
        SimpleNamespace(
            content=None,
            tool_calls=[_visual_tool_call({"not": "json text"})],
        ),
        SimpleNamespace(
            content=qwen_symbol_fixture["arguments"],
            tool_calls=[],
        ),
        SimpleNamespace(
            content="unexpected explanation",
            tool_calls=[
                _visual_tool_call(qwen_symbol_fixture["arguments"])
            ],
        ),
    )
    for invalid_message in invalid_tool_messages:
        class InvalidToolCompletions:
            @staticmethod
            def create(**_kwargs):
                return SimpleNamespace(
                    id="fixture-qwen-invalid-tool",
                    choices=[SimpleNamespace(message=invalid_message)],
                    usage={"total_tokens": 4},
                )

        invalid_tool_provider = QwenVisionProvider(
            SimpleNamespace(
                chat=SimpleNamespace(
                    completions=InvalidToolCompletions()
                )
            )
        )
        with pytest.raises(VisualSymbolProviderError) as tool_error:
            invalid_tool_provider.review_symbols(image, prompt)
        assert tool_error.value.request_id == "fixture-qwen-invalid-tool"
        assert tool_error.value.usage == {"total_tokens": 4}
        assert tool_error.value.__cause__ is None

    class NeverCompletions:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            raise AssertionError("invalid visual input reached the client")

    missing_idat = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", _png_header(32, 24))
        + _png_chunk(b"IEND", b"")
    )
    raw_between_chunks = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", _png_header(32, 24))
        + b"%PDF-arbitrary-bytes"
        + _png_chunk(b"IEND", b"")
    )
    bad_crc = bytearray(_png())
    bad_crc[-1] ^= 0x01
    invalid_idat = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", _png_header(32, 24))
        + _png_chunk(b"IDAT", b"not-compressed-image-data")
        + _png_chunk(b"IEND", b"")
    )
    for unsafe_image in (
        b"%PDF-1.7",
        b"arbitrary-image-bytes",
        _png(width=1537),
        _png(height=1537),
        missing_idat,
        raw_between_chunks,
        bytes(bad_crc),
        invalid_idat,
        _png() + b"trailing-data",
    ):
        never = NeverCompletions()
        with pytest.raises(
            VisualSymbolInputError,
            match="^visual symbol input must be one bounded PNG crop$",
        ):
            QwenVisionProvider(
                SimpleNamespace(
                    chat=SimpleNamespace(completions=never)
                )
            ).review_symbols(unsafe_image, prompt)
        assert never.calls == 0

    valid_content = qwen_symbol_fixture["arguments"]

    def metadata_provider(request_id: str, usage: dict) -> QwenVisionProvider:
        class MetadataCompletions:
            @staticmethod
            def create(**_kwargs):
                return SimpleNamespace(
                    id=request_id,
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    _visual_tool_call(valid_content)
                                ],
                            )
                        )
                    ],
                    usage=usage,
                )

        return QwenVisionProvider(
            SimpleNamespace(
                chat=SimpleNamespace(completions=MetadataCompletions())
            )
        )

    for unsafe_request_id in (
        "request/with/slash",
        "request with whitespace",
        "secret-request-id",
    ):
        with pytest.raises(
            VisualSymbolMetadataError,
            match="^visual symbol response metadata is invalid$",
        ) as metadata_error:
            metadata_provider(
                unsafe_request_id,
                {"total_tokens": 4},
            ).review_symbols(image, prompt)
        assert unsafe_request_id not in str(metadata_error.value)

    for unsafe_usage in (
        {"api_key": 1},
        {"secret_tokens": 1},
        {"total_tokens": -1},
        {"total_tokens": "1"},
    ):
        with pytest.raises(
            VisualSymbolMetadataError,
            match="^visual symbol response metadata is invalid$",
        ) as metadata_error:
            metadata_provider(
                "fixture-safe-request-id",
                unsafe_usage,
            ).review_symbols(image, prompt)
        assert not any(
            key in str(metadata_error.value)
            for key in unsafe_usage
        )
