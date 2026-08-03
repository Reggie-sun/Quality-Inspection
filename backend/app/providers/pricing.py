from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any


PRICING_SNAPSHOT_PATH = Path(__file__).with_name(
    "provider_pricing_gdt10d_v1.json"
)
_MICRO_CNY = Decimal("0.000001")
_MILLION = Decimal(1_000_000)
_EXPECTED_ROOT_KEYS = {
    "schema_version",
    "snapshot_id",
    "currency",
    "retrieved_date",
    "content_sha256",
    "tencent_ocr",
    "qwen_vision",
}
_EXPECTED_OCR_KEYS = {
    "provider",
    "operation",
    "source_url",
    "api_source_url",
    "billing_unit",
    "cny_per_submission",
}
_EXPECTED_QWEN_KEYS = {
    "provider",
    "model",
    "region",
    "source_url",
    "billing_unit",
    "max_prompt_tokens",
    "max_completion_tokens",
    "tiers",
}
_EXPECTED_TIER_KEYS = {
    "max_prompt_tokens",
    "input_cny_per_million",
    "output_cny_per_million",
}
_EXPECTED_TIERS = (
    (32_768, Decimal("1"), Decimal("10")),
    (131_072, Decimal("1.5"), Decimal("15")),
    (260_096, Decimal("3"), Decimal("30")),
)


@dataclass(frozen=True)
class QwenPricingTier:
    max_prompt_tokens: int
    input_cny_per_million: Decimal
    output_cny_per_million: Decimal


@dataclass(frozen=True)
class QwenVisionPricing:
    provider: str
    model: str
    region: str
    source_url: str
    billing_unit: str
    max_prompt_tokens: int
    max_completion_tokens: int
    tiers: tuple[QwenPricingTier, ...]


@dataclass(frozen=True)
class TencentOcrPricing:
    provider: str
    operation: str
    source_url: str
    api_source_url: str
    billing_unit: str
    cny_per_submission: Decimal


@dataclass(frozen=True)
class ProviderPricingSnapshot:
    schema_version: str
    snapshot_id: str
    currency: str
    retrieved_date: str
    content_sha256: str
    ocr: TencentOcrPricing
    qwen: QwenVisionPricing


def _mapping(
    value: object,
    expected_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ValueError("provider pricing snapshot fields are invalid")
    return dict(value)


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("provider pricing snapshot integer is invalid")
    return value


def _strict_decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("provider pricing snapshot Decimal is invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("provider pricing snapshot Decimal is invalid") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("provider pricing snapshot Decimal is invalid")
    return parsed


def _reject_floats(value: object) -> None:
    if isinstance(value, float):
        raise ValueError("provider pricing snapshot cannot contain float")
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_floats(nested)


def _canonical_content_hash(document: Mapping[str, Any]) -> str:
    content = dict(document)
    content.pop("content_sha256", None)
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_pricing_snapshot(
    path: str | Path | None = None,
) -> ProviderPricingSnapshot:
    snapshot_path = PRICING_SNAPSHOT_PATH if path is None else Path(path)
    try:
        raw = json.loads(
            snapshot_path.read_text(encoding="utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("provider pricing snapshot number is invalid")
            ),
        )
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("provider pricing snapshot is invalid") from exc
    root = _mapping(raw, _EXPECTED_ROOT_KEYS)
    _reject_floats(root)
    content_sha256 = root["content_sha256"]
    if (
        not isinstance(content_sha256, str)
        or len(content_sha256) != 64
        or content_sha256 != _canonical_content_hash(root)
    ):
        raise ValueError("provider pricing snapshot hash is invalid")

    ocr_document = _mapping(root["tencent_ocr"], _EXPECTED_OCR_KEYS)
    qwen_document = _mapping(root["qwen_vision"], _EXPECTED_QWEN_KEYS)
    raw_tiers = qwen_document["tiers"]
    if not isinstance(raw_tiers, list) or len(raw_tiers) != 3:
        raise ValueError("provider pricing snapshot tiers are invalid")
    tiers = tuple(
        QwenPricingTier(
            max_prompt_tokens=_strict_int(tier["max_prompt_tokens"]),
            input_cny_per_million=_strict_decimal(
                tier["input_cny_per_million"]
            ),
            output_cny_per_million=_strict_decimal(
                tier["output_cny_per_million"]
            ),
        )
        for tier in (
            _mapping(item, _EXPECTED_TIER_KEYS) for item in raw_tiers
        )
    )
    tier_literals = tuple(
        (
            tier.max_prompt_tokens,
            tier.input_cny_per_million,
            tier.output_cny_per_million,
        )
        for tier in tiers
    )
    if tier_literals != _EXPECTED_TIERS:
        raise ValueError("provider pricing snapshot tiers are invalid")

    if (
        root["schema_version"] != "provider-pricing-snapshot/1"
        or root["snapshot_id"] != "provider-pricing-gdt10d/1"
        or root["currency"] != "CNY"
        or root["retrieved_date"] != "2026-08-02"
        or ocr_document["provider"] != "tencent-ocr"
        or ocr_document["operation"] != "GeneralAccurateOCR"
        or ocr_document["source_url"]
        != "https://cloud.tencent.com/document/product/866/17619"
        or ocr_document["api_source_url"]
        != "https://cloud.tencent.com/document/product/866/34937"
        or ocr_document["billing_unit"] != "submission"
        or qwen_document["provider"] != "qwen-vl"
        or qwen_document["model"] != "qwen3-vl-plus-2025-12-19"
        or qwen_document["region"] != "cn-beijing"
        or qwen_document["source_url"]
        != "https://help.aliyun.com/zh/model-studio/qwen3-vl-plus"
        or qwen_document["billing_unit"] != "million_tokens"
        or _strict_int(qwen_document["max_prompt_tokens"]) != 260_096
        or _strict_int(qwen_document["max_completion_tokens"]) != 32_768
    ):
        raise ValueError("provider pricing snapshot identity is invalid")

    return ProviderPricingSnapshot(
        schema_version=root["schema_version"],
        snapshot_id=root["snapshot_id"],
        currency=root["currency"],
        retrieved_date=root["retrieved_date"],
        content_sha256=content_sha256,
        ocr=TencentOcrPricing(
            provider=ocr_document["provider"],
            operation=ocr_document["operation"],
            source_url=ocr_document["source_url"],
            api_source_url=ocr_document["api_source_url"],
            billing_unit=ocr_document["billing_unit"],
            cny_per_submission=_strict_decimal(
                ocr_document["cny_per_submission"]
            ),
        ),
        qwen=QwenVisionPricing(
            provider=qwen_document["provider"],
            model=qwen_document["model"],
            region=qwen_document["region"],
            source_url=qwen_document["source_url"],
            billing_unit=qwen_document["billing_unit"],
            max_prompt_tokens=qwen_document["max_prompt_tokens"],
            max_completion_tokens=qwen_document["max_completion_tokens"],
            tiers=tiers,
        ),
    )


def _round_up_micro_cny(value: Decimal) -> Decimal:
    return value.quantize(_MICRO_CNY, rounding=ROUND_CEILING)


def qwen_reservation_cny(snapshot: ProviderPricingSnapshot) -> Decimal:
    qwen = snapshot.qwen
    tier = qwen.tiers[-1]
    return _round_up_micro_cny(
        (
            Decimal(qwen.max_prompt_tokens) * tier.input_cny_per_million
            + Decimal(qwen.max_completion_tokens)
            * tier.output_cny_per_million
        )
        / _MILLION
    )


def qwen_usage_cost_cny(
    snapshot: ProviderPricingSnapshot,
    usage: Mapping[str, object],
) -> Decimal | None:
    if not isinstance(usage, Mapping):
        return None
    if set(usage) not in (
        {"prompt_tokens", "completion_tokens"},
        {"prompt_tokens", "completion_tokens", "total_tokens"},
    ):
        return None
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in usage.values()
    ):
        return None
    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    if not isinstance(prompt_tokens, int) or not isinstance(
        completion_tokens, int
    ):
        return None
    total_tokens = usage.get("total_tokens")
    if total_tokens is not None and total_tokens != prompt_tokens + completion_tokens:
        return None
    qwen = snapshot.qwen
    if (
        prompt_tokens > qwen.max_prompt_tokens
        or completion_tokens > qwen.max_completion_tokens
    ):
        return None
    tier = next(
        (
            candidate
            for candidate in qwen.tiers
            if prompt_tokens <= candidate.max_prompt_tokens
        ),
        None,
    )
    if tier is None:
        return None
    return _round_up_micro_cny(
        (
            Decimal(prompt_tokens) * tier.input_cny_per_million
            + Decimal(completion_tokens) * tier.output_cny_per_million
        )
        / _MILLION
    )


def ocr_submission_cost_cny(snapshot: ProviderPricingSnapshot) -> Decimal:
    return _round_up_micro_cny(snapshot.ocr.cny_per_submission)
