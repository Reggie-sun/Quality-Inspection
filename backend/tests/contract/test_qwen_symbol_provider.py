from __future__ import annotations

import base64
import json
import zlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.completion_usage import CompletionUsage
from PIL import Image

from app.candidates.symbol_review import (
    VISUAL_ADAPTER_VERSION,
    VISUAL_PROMPT_VERSION,
    VISUAL_PROPOSAL_VERSION,
    VISUAL_SCHEMA_VERSION,
    visual_cache_key,
    visual_review_prompt,
)
from app.providers.qwen_vl import (
    QwenVisionProvider,
    VisualSymbolInputError,
    VisualSymbolMetadataError,
    VisualSymbolProviderError,
    canonicalize_visual_png,
    validate_visual_request_metadata,
)


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


def test_qwen_visual_symbol_schema_and_cache_identity() -> None:
    """PROV-01: the visual request and every cache identity dimension are frozen."""
    fixture = json.loads(
        (
            Path(__file__).parents[3]
            / ".agent/harness/fixtures/providers/qwen-vl/"
            "visual-symbol-review-v1.json"
        ).read_text(encoding="utf-8")
    )
    qwen_symbol_fixture = fixture["payload"]

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
                            content=qwen_symbol_fixture["content"]
                        )
                    )
                ],
                usage=qwen_symbol_fixture["usage"],
            )

    completions = FakeCompletions()
    private_marker = b"private-marker-%PDF"
    image = _png(text=b"review\x00" + private_marker)
    prompt = visual_review_prompt(("visual-001", "visual-002"))
    assert json.loads(prompt) == {
        "task": "review_local_engineering_drawing_symbol_contexts",
        "prompt_version": "visual-symbol-prompt/1",
        "schema_version": "visual-symbol-review/1",
        "visual_observation_ids": ["visual-001", "visual-002"],
        "constraints": [
            "use_only_listed_visual_observation_ids",
            "return_frozen_schema_only",
            "requires_confirmation_must_be_true",
        ],
    }
    assert prompt == (
        '{"constraints":["use_only_listed_visual_observation_ids",'
        '"return_frozen_schema_only","requires_confirmation_must_be_true"],'
        '"prompt_version":"visual-symbol-prompt/1",'
        '"schema_version":"visual-symbol-review/1",'
        '"task":"review_local_engineering_drawing_symbol_contexts",'
        '"visual_observation_ids":["visual-001","visual-002"]}'
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
                        "Output JSON only."
                    ),
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
    assert (
        completions.calls[0]["messages"][1]["content"][1]["text"]
        == prompt + "\nOutput in JSON format."
    )
    assert result.payload == json.loads(qwen_symbol_fixture["content"])
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
        "proposal_version": VISUAL_PROPOSAL_VERSION,
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
        "schema_version": "visual-symbol-review/2",
        "adapter_version": "qwen-openai-compatible/2",
        "proposal_version": "visual-observation/2",
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
                        message=SimpleNamespace(content=invalid_body)
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

    valid_content = qwen_symbol_fixture["content"]

    def metadata_provider(request_id: str, usage: dict) -> QwenVisionProvider:
        class MetadataCompletions:
            @staticmethod
            def create(**_kwargs):
                return SimpleNamespace(
                    id=request_id,
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=valid_content)
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
