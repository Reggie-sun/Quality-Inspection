from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from app.providers.pricing import (
    PRICING_SNAPSHOT_PATH,
    load_pricing_snapshot,
    ocr_submission_cost_cny,
    qwen_reservation_cny,
    qwen_usage_cost_cny,
)


def _canonical_hash(document: dict[str, object]) -> str:
    payload = dict(document)
    payload.pop("content_sha256", None)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _mutated_snapshot(
    tmp_path: Path,
    mutate,
    *,
    rehash: bool = True,
) -> Path:
    document = json.loads(PRICING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    mutate(document)
    if rehash:
        document["content_sha256"] = _canonical_hash(document)
    path = tmp_path / "provider-pricing.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_qwen_unknown_usage_reserves_official_maximum() -> None:
    snapshot = load_pricing_snapshot()

    assert qwen_reservation_cny(snapshot) == Decimal("1.763328")
    assert ocr_submission_cost_cny(snapshot) == Decimal("0.500000")


@pytest.mark.parametrize(
    ("usage", "expected"),
    (
        ({"prompt_tokens": 32_768, "completion_tokens": 1}, "0.032778"),
        ({"prompt_tokens": 32_769, "completion_tokens": 1}, "0.049169"),
        ({"prompt_tokens": 131_072, "completion_tokens": 1}, "0.196623"),
        ({"prompt_tokens": 131_073, "completion_tokens": 1}, "0.393249"),
        ({"prompt_tokens": 1, "completion_tokens": 0}, "0.000001"),
        ({"prompt_tokens": 1, "completion_tokens": 32_768}, "0.327681"),
        (
            {"prompt_tokens": 260_096, "completion_tokens": 32_768},
            "1.763328",
        ),
    ),
)
def test_qwen_cost_uses_prompt_tier_and_rounds_up_to_micro_cny(
    usage: dict[str, int],
    expected: str,
) -> None:
    assert qwen_usage_cost_cny(load_pricing_snapshot(), usage) == Decimal(
        expected
    )


@pytest.mark.parametrize(
    "usage",
    (
        {"total_tokens": 4},
        {"prompt_tokens": 260_097, "completion_tokens": 1},
        {"prompt_tokens": 1, "completion_tokens": 32_769},
        {"prompt_tokens": -1, "completion_tokens": 1},
        {"prompt_tokens": True, "completion_tokens": 1},
        {"prompt_tokens": 1.0, "completion_tokens": 1},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
        {"prompt_tokens": 1, "completion_tokens": 1, "unexpected": 0},
    ),
)
def test_qwen_incomplete_or_out_of_range_usage_cannot_reduce_reservation(
    usage: dict[str, object],
) -> None:
    assert qwen_usage_cost_cny(load_pricing_snapshot(), usage) is None


def test_snapshot_identity_and_dataclasses_are_frozen() -> None:
    snapshot = load_pricing_snapshot()

    assert snapshot.snapshot_id == "provider-pricing-gdt10d/1"
    assert snapshot.currency == "CNY"
    assert snapshot.retrieved_date == "2026-08-02"
    assert snapshot.qwen.model == "qwen3-vl-plus-2025-12-19"
    assert snapshot.qwen.region == "cn-beijing"
    with pytest.raises(FrozenInstanceError):
        snapshot.currency = "USD"  # type: ignore[misc]


@pytest.mark.parametrize(
    "mutate",
    (
        lambda document: document.__setitem__("extra", "forbidden"),
        lambda document: document.pop("currency"),
        lambda document: document.__setitem__("snapshot_id", "other/1"),
        lambda document: document["qwen_vision"].__setitem__(  # type: ignore[union-attr]
            "model", "other-model"
        ),
        lambda document: document["qwen_vision"].__setitem__(  # type: ignore[union-attr]
            "region", "other-region"
        ),
        lambda document: document["qwen_vision"].__setitem__(  # type: ignore[union-attr]
            "source_url", "https://example.invalid/pricing"
        ),
        lambda document: document["tencent_ocr"].__setitem__(  # type: ignore[union-attr]
            "cny_per_submission", 0.5
        ),
        lambda document: document["qwen_vision"]["tiers"][1].__setitem__(  # type: ignore[index,union-attr]
            "max_prompt_tokens", 32_768
        ),
    ),
)
def test_loader_rejects_mutated_or_malformed_snapshot(
    tmp_path: Path,
    mutate,
) -> None:
    path = _mutated_snapshot(tmp_path, mutate)

    with pytest.raises(ValueError, match="pricing snapshot"):
        load_pricing_snapshot(path)


def test_loader_rejects_hash_mismatch(tmp_path: Path) -> None:
    path = _mutated_snapshot(
        tmp_path,
        lambda document: document.__setitem__("currency", "USD"),
        rehash=False,
    )

    with pytest.raises(ValueError, match="hash"):
        load_pricing_snapshot(path)
