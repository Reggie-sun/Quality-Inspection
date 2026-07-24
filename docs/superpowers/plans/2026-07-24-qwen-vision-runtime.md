# Qwen Vision Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 `QwenVisionProvider` 接入唯一 canonical processing runtime，并以局部 crop、确定性 validator、真实调用记录和缓存证明 Vision Advisor 实际参与处理。

**Architecture:** `CandidateAdvisor` 位于 candidate domain，在确定性 `candidate_snapshot_from_inventory()` 之后处理有明确复核原因的对象。它只接受不改变正式 Owner 的建议，把安全 provenance 写入 immutable raw result；`InventoryPipeline` 继续拥有 coverage/failure/formal-result veto。生产任务注入一个真实 Qwen factory，测试通过同一个 seam 注入离线 fake。

**Tech Stack:** Python 3.11、FastAPI、Celery、SQLAlchemy、PyMuPDF、OpenAI Python SDK、Pydantic、JSON Schema、pytest、LocalFileStorage

---

## Problem Boundary

- Single Owner: `backend/app/candidates/advisor.py::CandidateAdvisor` 拥有 Vision routing、crop、cache 和确定性建议校验。
- Old paths to retire:
  - `backend/tests/e2e/test_offline_automatic_result.py` 手工写入 Qwen request ID；
  - `backend/tests/e2e/test_offline_vertical.py::VerticalSystem._provider_call_ids()` 与 `_fixture_snapshot()`；
  - `.agent/harness/scripts/run-p0.py::_PREPARE_PROJECT_PROGRAM` 直接构造默认 `InventoryPipeline`。
- Unchanged contracts:
  - `candidate_snapshot_from_inventory()` 仍拥有确定性初始候选；
  - `check_coverage()` 仍是 formal result 的唯一 coverage veto；
  - Provider 不提交 disposition、review state、正式编号、geometry、检测方法或导出内容；
  - review → freeze → balloon → confirm → export 顺序不变；
  - offline fixture 禁止 network。
- Focused verification:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_error_records.py -q
```

## File Structure

- Create `backend/app/candidates/advisor.py`: routing、crop、cache、validator、provenance 和脱敏 Advisor failure。
- Create `backend/tests/unit/candidates/test_advisor.py`: 纯本地 Advisor 行为。
- Modify `backend/app/providers/runtime.py`: 真实 Qwen OpenAI-compatible client factory。
- Modify `backend/app/providers/call_records.py`: 未冻结定价时允许 `estimated_cost=None`。
- Modify `backend/app/processing/runtime_recognition.py`: 保存 source path，并在确定性 snapshot 后调用 Advisor。
- Modify `backend/app/processing/tasks.py`: canonical task 注入 Qwen factory 与 CandidateAdvisor。
- Modify `backend/app/processing/pipeline.py`: 独立记录 `candidate_advisor` 失败。
- Modify `backend/app/processing/automatic_result.py`: 为 Advisor 复用稳定 observation/candidate 关系辅助函数。
- Modify `backend/app/candidates/coverage.py`: raw coverage entry 可携带不投影到工作台的安全 Advisor provenance。
- Modify `backend/app/review/service.py`: 创建 working copy 时剥离 Advisor provenance。
- Modify Provider、processing、result-layer、offline E2E 和 Harness tests：删除 request-ID 假闭环。

### Task 1: Production Qwen Factory And Nullable Cost Truth

**Files:**
- Modify: `backend/app/providers/runtime.py`
- Modify: `backend/app/providers/call_records.py`
- Modify: `backend/tests/contract/test_qwen_vl_provider.py`
- Modify: `backend/tests/contract/test_provider_call_records.py`

- [ ] **Step 1: Write failing factory and nullable-cost tests**

在 `backend/tests/contract/test_qwen_vl_provider.py` 增加：

```python
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
        "timeout": 30.0,
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
```

在 `backend/tests/contract/test_provider_call_records.py` 增加：

```python
def test_unknown_pricing_is_serialized_as_null() -> None:
    payload = json.loads(
        serialize_call_record(replace(_record(), estimated_cost=None))
    )

    assert payload["estimated_cost"] is None
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py -q
```

Expected: FAIL because `build_vision_provider`/`OpenAI` are absent and `estimated_cost=None` is rejected.

- [ ] **Step 3: Implement the minimal runtime factory**

在 `backend/app/providers/runtime.py` 增加以下 port/factory：

```python
import re

from openai import OpenAI

from app.providers.base import OcrProvider, VisionLlmProvider
from app.providers.qwen_vl import QwenVisionProvider


VisionProviderFactory = Callable[[Settings], VisionLlmProvider]
_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def build_vision_provider(settings: Settings) -> VisionLlmProvider:
    api_key = (settings.qwen_api_key or "").strip()
    workspace_id = (settings.qwen_workspace_id or "").strip()
    model = (settings.qwen_model or "").strip()
    if (
        not api_key
        or not model
        or _WORKSPACE_ID.fullmatch(workspace_id) is None
    ):
        raise CapabilityUnavailable(
            "vision_provider_unavailable",
            "Vision Provider configuration is unavailable",
        )
    client = OpenAI(
        api_key=api_key,
        base_url=(
            f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/"
            "compatible-mode/v1"
        ),
        timeout=30.0,
        max_retries=0,
    )
    return QwenVisionProvider(client, model=model)
```

将 `ProviderCallRecord.estimated_cost` 改为 `float | None`，并把校验改为：

```python
if self.estimated_cost is not None and (
    isinstance(self.estimated_cost, bool)
    or not isinstance(self.estimated_cost, (int, float))
    or not math.isfinite(float(self.estimated_cost))
    or self.estimated_cost < 0
):
    raise ValueError("estimated_cost must be null or non-negative")
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py -q
```

Expected: all selected tests PASS; no secret value appears in pytest output.

### Task 2: Deterministic Routing And Local Crop

**Files:**
- Create: `backend/app/candidates/advisor.py`
- Create: `backend/tests/unit/candidates/test_advisor.py`
- Modify: `backend/app/candidates/coverage.py`
- Modify: `backend/app/processing/automatic_result.py`

- [ ] **Step 1: Write failing routing and crop tests**

创建 `backend/tests/unit/candidates/test_advisor.py`，先定义以下真实 PDF 和
fake Provider fixtures：

```python
from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from app.candidates.advisor import CandidateAdvisor
from app.config import Settings
from app.pdf.inventory import build_inventory
from app.processing.automatic_result import (
    CandidateSnapshot,
    candidate_snapshot_from_inventory,
)
from app.providers.base import VisionResult
from app.storage.local import LocalFileStorage


def advisor_payload(
    raw_text: str,
    item_type: str,
    normalized_text: str,
    requires_confirmation: bool,
) -> dict[str, object]:
    return {
        "schema_version": "candidate-review/1",
        "raw_text": raw_text,
        "item_type": item_type,
        "normalized_text": normalized_text,
        "requires_confirmation": requires_confirmation,
    }


class RecordingVisionProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.images: list[bytes] = []
        self.prompts: list[str] = []

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        self.images.append(image)
        self.prompts.append(prompt)
        return VisionResult(
            request_id=f"fixture-qwen-request-{len(self.images)}",
            payload=dict(self.payload),
            usage={"total_tokens": 10},
        )


class SequenceVisionProvider:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls = 0

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        del image, prompt
        payload = self.payloads[self.calls]
        self.calls += 1
        return VisionResult(
            request_id=f"fixture-qwen-request-{self.calls}",
            payload=dict(payload),
            usage={},
        )


class EchoVisionProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        self.calls.append(request)
        return VisionResult(
            request_id=f"fixture-qwen-request-{len(self.calls)}",
            payload=advisor_payload(
                raw_text=str(request["raw_text"]),
                item_type=str(request["expected_type"]),
                normalized_text=str(request["raw_text"]),
                requires_confirmation=True,
            ),
            usage={},
        )


class FailingIfCalledVisionProvider:
    def __init__(self) -> None:
        self.calls = 0

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        del image, prompt
        self.calls += 1
        raise AssertionError("cache hit constructed one external call")


def drawing_fixture(
    tmp_path: Path,
    *,
    raw_text: str,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source = tmp_path / "drawing.pdf"
    document = pymupdf.open()
    page = document.new_page(width=240, height=180)
    page.insert_text((32, 48), raw_text)
    document.save(source)
    document.close()
    pages = tuple(build_inventory(source))
    return source, pages, candidate_snapshot_from_inventory(pages)


def dense_roughness_fixture(
    tmp_path: Path,
    *,
    count: int,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source = tmp_path / "dense.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=480)
    for index in range(count):
        page.insert_text((24, 24 + index * 24), f"Ra {index + 1}.0")
    document.save(source)
    document.close()
    pages = tuple(build_inventory(source))
    return source, pages, candidate_snapshot_from_inventory(pages)


def candidate_advisor(
    tmp_path: Path,
    provider: object,
) -> CandidateAdvisor:
    return CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=lambda _settings: provider,
    )
```

然后增加：

```python
def test_clear_native_candidate_does_not_construct_provider(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="M6")
    constructed: list[str] = []
    def forbidden_factory(_settings: Settings):
        constructed.append("provider")
        raise AssertionError("clear candidate constructed the Provider")

    advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=forbidden_factory,
    )

    reviewed = advisor.review(source, pages, snapshot)

    assert reviewed == snapshot
    assert constructed == []


def test_coarse_candidate_uses_one_bounded_local_crop(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = RecordingVisionProvider(
        payload=advisor_payload(
            raw_text="Ra 3.2",
            item_type="roughness",
            normalized_text="Ra 3.2",
            requires_confirmation=True,
        )
    )
    advisor = candidate_advisor(tmp_path, provider)

    reviewed = advisor.review(source, pages, snapshot)

    assert len(provider.images) == 1
    assert provider.images[0].startswith(b"\x89PNG")
    provenance = reviewed.candidates[0]["advisor_review"]
    assert provenance["review_reason"] == "coarse_type"
    assert provenance["validated"] is True
    assert len(provenance["crop_sha256"]) == 64
    assert 6.0 <= provenance["padding_pdf"] <= 24.0
    assert provenance["crop_bbox_pdf"][0] >= 0
    assert provenance["crop_bbox_pdf"][2] <= pages[0].width


def test_page_call_cap_keeps_remaining_objects_unreviewed(tmp_path: Path) -> None:
    source, pages, snapshot = dense_roughness_fixture(tmp_path, count=17)
    provider = EchoVisionProvider()

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert len(provider.calls) == 16
    assert sum("advisor_review" in item for item in reviewed.candidates) == 16
    assert reviewed.candidates[-1]["payload"]["requires_confirmation"] is True
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_advisor.py -q
```

Expected: collection FAIL because `app.candidates.advisor` does not exist.

- [ ] **Step 3: Implement stable routed-object selection and crop rendering**

在 `backend/app/candidates/advisor.py` 定义：

```python
PROMPT_VERSION = "candidate-review-prompt/2"
SCHEMA_VERSION = "candidate-review/1"
ADAPTER_VERSION = "qwen-openai-compatible/1"
MAX_CALLS_PER_PAGE = 16
RENDER_SCALE = 2.0


class CandidateAdvisorFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class RoutedObject:
    page_index: int
    source_ids: tuple[str, ...]
    raw_text: str
    expected_type: str | None
    review_reason: str
    bbox_pdf: BBox
    candidate_index: int | None
    coverage_index: int
    requires_confirmation: bool
```

实现 `_route_objects()`：

- source observation 通过 `observation_id` 索引；
- reason 优先级固定为 `coarse_type`、`composite`、`confirmation`、`ocr_source`、`parser_failed`；
- 排序键固定为 `(page_index, bbox.y0, bbox.x0, source_ids)`；
- 每页只保留前 16 个；
- 未路由对象原样保留，不添加 provenance。

实现 prompt 为可由测试和审计稳定读取的纯 JSON：

```python
def _review_prompt(route: RoutedObject) -> str:
    return json.dumps(
        {
            "task": "review_local_engineering_annotation",
            "raw_text": route.raw_text,
            "expected_type": route.expected_type,
            "review_reason": route.review_reason,
            "constraints": [
                "do_not_translate_raw_text",
                "do_not_guess_missing_context",
                "keep_or_raise_requires_confirmation",
                "return_frozen_schema_only",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
```

实现 `_render_crop()`：

```python
def _crop_rect(page: pymupdf.Page, bbox: BBox) -> pymupdf.Rect:
    source = pymupdf.Rect(bbox)
    padding = min(24.0, max(6.0, source.height))
    crop = pymupdf.Rect(
        source.x0 - padding,
        source.y0 - padding,
        source.x1 + padding,
        source.y1 + padding,
    ) & page.rect
    if crop.is_empty or crop.get_area() <= 0:
        raise CandidateAdvisorFailure("Vision candidate crop is unavailable")
    return crop


def _render_crop(page: pymupdf.Page, crop: pymupdf.Rect) -> bytes:
    rendered = crop * page.rotation_matrix
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE),
        clip=rendered,
        alpha=False,
    )
    if pixmap.width <= 0 or pixmap.height <= 0:
        raise CandidateAdvisorFailure("Vision candidate crop is unavailable")
    return pixmap.tobytes("png")
```

`CandidateAdvisor.review()` 必须先计算 route；route 为空时直接返回原 snapshot，不能构造 Provider 或打开 PDF。

- [ ] **Step 4: Add optional raw provenance without changing coverage truth**

在 `backend/app/candidates/coverage.py` 给 `CoverageEntry` 增加：

```python
advisor_review: dict[str, object] | None = None
```

`to_dict()` 只在非空时写入：

```python
payload: dict[str, object] = {
    "observation_id": self.observation_id,
    "disposition": self.disposition,
    "source_location_id": self.source_location_id,
    "coordinates": self.coordinates,
    "candidate_id": self.candidate_id,
    "requires_confirmation": self.requires_confirmation,
}
if self.advisor_review is not None:
    payload["advisor_review"] = dict(self.advisor_review)
return payload
```

在 `backend/app/processing/automatic_result.py` 增加可复用的 observation 选择函数：

```python
def selected_observations(
    pages: Sequence[Any],
) -> tuple[TextObservation, ...]:
    return tuple(_selected_observations(pages))
```

Advisor 只使用该 helper，不重新定义另一套 observation 选择语义。

- [ ] **Step 5: Run routing/crop tests and verify GREEN**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/unit/pdf/test_coordinates.py -q
```

Expected: all selected tests PASS.

### Task 3: Validator, Cache, Call Record And Provenance

**Files:**
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_result_layers.py`

- [ ] **Step 1: Write failing validator/cache/privacy tests**

向 `backend/tests/unit/candidates/test_advisor.py` 增加：

```python
def test_validator_rejects_raw_text_or_type_drift(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = SequenceVisionProvider(
        [
            advisor_payload("Ra 6.3", "roughness", "Ra 6.3", True),
            advisor_payload("Ra 3.2", "thread", "Ra 3.2", True),
        ]
    )

    first = candidate_advisor(tmp_path, provider).review(source, pages, snapshot)
    second = candidate_advisor(
        tmp_path / "second",
        SequenceVisionProvider([provider.payloads[1]]),
    ).review(source, pages, snapshot)

    assert first.candidates[0]["payload"] == snapshot.candidates[0]["payload"]
    assert first.candidates[0]["advisor_review"]["rejection_code"] == "raw_text_mismatch"
    assert second.candidates[0]["advisor_review"]["rejection_code"] == "type_mismatch"


def test_advisor_cannot_clear_required_confirmation(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = RecordingVisionProvider(
        payload=advisor_payload("Ra 3.2", "roughness", "Ra 3.2", False)
    )

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert reviewed.candidates[0]["payload"]["requires_confirmation"] is True
    assert reviewed.candidates[0]["advisor_review"]["validated"] is False
    assert (
        reviewed.candidates[0]["advisor_review"]["rejection_code"]
        == "confirmation_downgrade"
    )


def test_ambiguous_promotion_requires_local_parser_success(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="M6 depth 10")
    provider = RecordingVisionProvider(
        payload=advisor_payload(
            "M6 depth 10",
            "thread",
            "M6深10",
            True,
        )
    )

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert reviewed.coverage_entries[0].disposition == "candidate"
    assert reviewed.coverage_entries[0].requires_confirmation is True
    assert reviewed.candidates[0]["payload"]["raw_text"] == "M6 depth 10"
    assert reviewed.candidates[0]["payload"]["thread_spec"] == "M6"


def test_cache_hit_reuses_validated_result_without_provider_call(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    first_provider = EchoVisionProvider()
    first = candidate_advisor(tmp_path, first_provider)
    second_provider = FailingIfCalledVisionProvider()
    second = candidate_advisor(tmp_path, second_provider)

    first_result = first.review(source, pages, snapshot)
    second_result = second.review(source, pages, snapshot)

    assert len(first_provider.calls) == 1
    assert second_provider.calls == 0
    assert second_result.provider_call_ids == first_result.provider_call_ids
```

向 `backend/tests/integration/test_result_layers.py` 增加断言：

```python
assert "advisor_review" in raw.candidates[0]
assert all(
    "advisor_review" not in item
    for item in working.items
)
assert all(
    "advisor_review" not in entry
    for entry in working.coverage.get("entries", [])
)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/integration/test_result_layers.py -q
```

Expected: FAIL on missing validation/cache behavior and provenance stripping.

- [ ] **Step 3: Implement deterministic acceptance**

在 `backend/app/candidates/advisor.py` 使用本地枚举：

```python
ALLOWED_SUGGESTION_TYPES = {
    "linear_dimension",
    "diameter_dimension",
    "thread",
    "radius",
    "angle",
    "general_requirement",
    "composite",
    "geometric_tolerance",
    "roughness",
    "weld",
}
REJECTION_CODES = {
    "raw_text_mismatch",
    "unknown_type",
    "type_mismatch",
    "confirmation_downgrade",
    "local_parse_failed",
}
```

实现 `_validate_suggestion(route, payload)`，严格按以下顺序返回本地 rejection code：

```python
if normalize_text(str(payload["raw_text"])) != normalize_text(route.raw_text):
    return "raw_text_mismatch"
if payload["item_type"] not in ALLOWED_SUGGESTION_TYPES:
    return "unknown_type"
if route.expected_type is not None and payload["item_type"] != route.expected_type:
    return "type_mismatch"
if route.requires_confirmation and payload["requires_confirmation"] is False:
    return "confirmation_downgrade"
```

typed/coarse candidate 只更新经 `parse_annotation()` 复核的
`normalized_text` 和单调 `requires_confirmation`；不得覆盖 numeric fields、
coordinates、source IDs 或 candidate ID。

每次 routed object 的 raw provenance 固定构造成：

```python
advisor_review = {
    "provider_role": "advisor",
    "review_reason": route.review_reason,
    "model": model,
    "prompt_version": PROMPT_VERSION,
    "schema_version": SCHEMA_VERSION,
    "page_index": route.page_index,
    "crop_bbox_pdf": list(crop_bbox_pdf),
    "padding_pdf": padding_pdf,
    "crop_sha256": crop_sha256,
    "validated": rejection_code is None,
    "rejection_code": rejection_code,
}
```

ambiguous promotion 使用：

```python
parsed = parse_annotation(str(payload["normalized_text"]))
if parsed.item_type != payload["item_type"]:
    return "type_mismatch"
promoted = parsed.model_copy(
    update={
        "candidate_id": stable_candidate_id("annotation", route.raw_text),
        "raw_text": route.raw_text,
        "coordinates": route.bbox_pdf,
        "requires_confirmation": True,
    }
)
```

- [ ] **Step 4: Implement deterministic cache and safe call artifacts**

cache key document 固定为：

```python
cache_key_document = {
    "provider_role": "advisor",
    "adapter_version": ADAPTER_VERSION,
    "model": model,
    "prompt_version": PROMPT_VERSION,
    "schema_version": SCHEMA_VERSION,
    "page_index": route.page_index,
    "crop_bbox_pdf": list(crop_bbox_pdf),
    "crop_sha256": crop_sha256,
}
```

使用
`json.dumps(cache_key_document, sort_keys=True, separators=(",", ":"))`
编码后计算 SHA-256。
文件固定为：

```text
projects/{project_id}/provider-cache/qwen/{cache_key}.json
projects/{project_id}/provider-inputs/qwen/{crop_sha256}.png
projects/{project_id}/provider-calls/qwen/{cache_key}.json
```

cache JSON allowlist 固定为：

```python
cache_payload = {
    "cache_schema_version": "candidate-advisor-cache/1",
    "provider": "qwen-vl",
    "request_id": result.request_id,
    "model": model,
    "prompt_version": PROMPT_VERSION,
    "schema_version": SCHEMA_VERSION,
    "crop_sha256": crop_sha256,
    "suggestion": result.payload,
    "usage": result.usage,
}
```

写入顺序固定为 crop → cache → call record。Call record 使用：

```python
ProviderCallRecord(
    provider="qwen-vl",
    request_id=result.request_id,
    model=model,
    prompt_version=PROMPT_VERSION,
    schema_version=SCHEMA_VERSION,
    duration_ms=duration_ms,
    retry_count=0,
    input_image_count=1,
    estimated_cost=None,
    logical_task_reused=False,
    request_ref=crop_write.resource_ref,
    response_ref=cache_write.resource_ref,
)
```

cache hit 必须重新执行冻结 Schema 和 deterministic validator；损坏 cache
抛出固定 `CandidateAdvisorFailure`，不得静默调用外网覆盖审计事实。

任何 Provider/Schema 异常统一：

```python
try:
    result = provider.review_candidate(crop_png, prompt)
except CapabilityUnavailable:
    raise
except Exception:
    raise CandidateAdvisorFailure(
        "Vision candidate Advisor call failed"
    ) from None
```

- [ ] **Step 5: Strip Advisor provenance at the review projection boundary**

在 `backend/app/review/service.py` 增加：

```python
@staticmethod
def _review_coverage(raw_coverage: dict[str, Any]) -> dict[str, Any]:
    coverage = copy.deepcopy(raw_coverage)
    for entry in coverage.get("entries", []):
        if isinstance(entry, dict):
            entry.pop("advisor_review", None)
    return coverage
```

`create_from_raw()` 使用 `_review_coverage(raw_result.coverage)`。`_current_item()`
继续只复制 `candidate["payload"]` 与 source relation，因此 candidate envelope 上的
`advisor_review` 不进入 working copy。

- [ ] **Step 6: Run tests and verify GREEN**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/integration/test_result_layers.py -q
```

Expected: all selected tests PASS; cache test records exactly one fake external call.

### Task 4: Canonical Runtime Wiring And Sanitized Failure

**Files:**
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/processing/tasks.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`
- Modify: `backend/tests/integration/test_error_records.py`

- [ ] **Step 1: Write failing canonical-call and failure tests**

在 `backend/tests/integration/test_processing_entry_task.py`：

- 保留现有 `M6` 测试并同时注入会失败的 `VISION_PROVIDER_FACTORY`，证明 clear
  deterministic native candidate 不构造 Qwen；
- 新增 `Ra 3.2` PDF 测试，fake Provider 返回相同 raw/type，断言：

```python
assert vision_calls == ["Ra 3.2"]
assert raw.provider_call_ids == ["fixture-qwen-request-id"]
assert raw.candidates[0]["advisor_review"]["validated"] is True
assert second_result_ref == first_result_ref
assert vision_calls == ["Ra 3.2"]
```

- 新增 fake Provider 抛出私密内容的测试，断言：

```python
assert raw_count == 0
assert working_count == 0
assert error.code == "vision_provider_call_failed"
assert error.stage == "candidate_advisor"
assert error.cause_category == "transient_provider_failure"
assert private_detail not in error.message
```

在 `backend/tests/integration/test_error_records.py` 增加 status projection 断言：

```python
assert response.json()["retryable"] is True
assert response.json()["error"] == {
    "code": "vision_provider_call_failed",
    "stage": "candidate_advisor",
}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_error_records.py -q
```

Expected: FAIL because production task has no Vision injection and generic failure owns the error.

- [ ] **Step 3: Wire Advisor after deterministic snapshot**

在 `RuntimeRecognition`：

```python
def __init__(
    self,
    settings: Settings,
    *,
    provider_factory: OcrProviderFactory = build_ocr_provider,
    advisor: CandidateAdvisor | None = None,
    render_scale: float = 2.0,
) -> None:
    self._settings = settings
    self._provider_factory = provider_factory
    self._render_scale = render_scale
    self._provider_call_ids: tuple[str, ...] = ()
    self._advisor = advisor
    self._source_path: Path | None = None
```

`build_inventory()` 首行保存 `self._source_path = pdf_path`。`build_candidate_snapshot()`：

```python
snapshot = replace(
    candidate_snapshot_from_inventory(pages),
    provider_call_ids=self._provider_call_ids,
)
if self._advisor is None:
    return snapshot
if self._source_path is None:
    raise RuntimeError("candidate snapshot requires one source PDF")
return self._advisor.review(self._source_path, pages, snapshot)
```

在 `tasks.py` 增加：

```python
VISION_PROVIDER_FACTORY: VisionProviderFactory = build_vision_provider
```

并构造：

```python
advisor = CandidateAdvisor(
    settings,
    storage,
    project_id=project_id,
    provider_factory=VISION_PROVIDER_FACTORY,
)
recognition = RuntimeRecognition(
    settings,
    provider_factory=OCR_PROVIDER_FACTORY,
    advisor=advisor,
)
```

- [ ] **Step 4: Give Advisor failure its own formal error**

在 `InventoryPipeline.run()` 的 `except CapabilityUnavailable` 之前增加：

```python
except CandidateAdvisorFailure:
    existing = self._record_failure(
        project,
        job,
        state=ProjectState.PROCESSING_FAILED,
        code="vision_provider_call_failed",
        message="Vision candidate Advisor call failed",
        stage="candidate_advisor",
        location_ref=None,
        cause_category="transient_provider_failure",
    )
    if existing is not None:
        return existing
    raise
```

在 `backend/app/projects/service.py`：

```python
_TRANSIENT_CAUSE_CATEGORIES = {
    "transient_dependency_unavailable",
    "transient_dispatch_failure",
    "transient_provider_failure",
}
```

并把 `"vision_provider_call_failed": "candidate_advisor"` 加入
`_SAFE_ERROR_STAGES`。

- [ ] **Step 5: Run canonical tests and verify GREEN**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_error_records.py \
  backend/tests/integration/test_project_status_api.py -q
```

Expected: all selected tests PASS; clear native PDF creates zero Vision calls; eligible
PDF creates exactly one.

### Task 5: Retire Fake Qwen Evidence And Harness Bypass

**Files:**
- Modify: `backend/tests/e2e/test_offline_automatic_result.py`
- Modify: `backend/tests/e2e/test_offline_vertical.py`
- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `backend/tests/contract/harness/test_contract_architecture.py`

- [ ] **Step 1: Write a failing Harness architecture assertion**

在 `backend/tests/contract/harness/test_contract_architecture.py` 增加：

```python
def test_live_prepare_uses_canonical_processing_task() -> None:
    source = (ROOT / ".agent/harness/scripts/run-p0.py").read_text(
        encoding="utf-8"
    )
    program = source.split('_PREPARE_PROJECT_PROGRAM = r"""', 1)[1].split(
        '"""',
        1,
    )[0]

    assert "inventory_project.run(" in program
    assert "InventoryPipeline(" not in program
```

- [ ] **Step 2: Run the assertion and verify RED**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_contract_architecture.py::test_live_prepare_uses_canonical_processing_task -q
```

Expected: FAIL because `_PREPARE_PROJECT_PROGRAM` still creates `InventoryPipeline`.

- [ ] **Step 3: Replace offline request-ID injection with the production Advisor seam**

在两个 offline E2E tests 中：

- 使用 PyMuPDF 写出真实 fixture PDF；
- 使用 `VisionResult` fake，返回与 crop source 原文一致的冻结 Schema payload；
- 用该测试的真实 `CandidateAdvisor` 实例构造
  `RuntimeRecognition(settings, advisor=advisor)`；
- `InventoryPipeline` 只注入：

```python
inventory_builder=recognition.build_inventory,
candidate_snapshot_builder=recognition.build_candidate_snapshot,
```

- 删除通过 `dataclasses.replace` 向 snapshot 手工注入 `provider_call_ids` 的调用、
  `_provider_call_ids()` 和 `_fixture_snapshot()`；
- socket/network patch 保持不变，并断言 `provider_network_connections == 0`。

`test_offline_automatic_result.py` 的正式断言改为只接受真实 fake seam 返回的 request ID：

```python
assert result.provider_call_ids == ["fixture-qwen-request-id"]
assert result.candidates[0]["advisor_review"]["validated"] is True
```

- [ ] **Step 4: Route live Harness preparation through the canonical task**

在 `_PREPARE_PROJECT_PROGRAM`：

- 删除 `ProcessingPreflight`、`InventoryPipeline` 和 `ReviewService` 的直接调用；
- seed source 后关闭 seed transaction；
- 调用：

```python
from app.processing.tasks import inventory_project

result_ref = inventory_project.run(
    str(project.id),
    source.resource_ref,
    "p0-live:" + os.environ["QI_P0_RUN_ID"] + ":" + os.environ["QI_P0_ORDER"],
)
```

- 重新查询 `AutomaticResult` 与 `ReviewWorkingCopy`；
- 断言 `result_ref == f"automatic-result://{raw.id}"`；
- 保留现有 current-four identity、coverage、page-size 和 source-relation evidence；
- 不修改 `.agent/harness/runs/` 或历史 receipt。

- [ ] **Step 5: Run offline and Harness tests**

Run:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/e2e/test_offline_vertical.py \
  backend/tests/e2e/test_no_silent_success.py \
  backend/tests/contract/harness/test_contract_architecture.py -q
```

Expected: all selected tests PASS and offline network count remains zero.

### Task 6: Qwen Runtime Verification Gate

**Files:**
- Modify only if tests reveal an in-scope defect in files listed above.
- Do not modify: `.env`, `.env.example`, `compose.yaml`, `.agent/harness/runs/`, sealed plans or receipts.

- [ ] **Step 1: Run contract and backend regression**

Run:

```bash
python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest backend/tests -q
```

Expected: contract checker reports no drift; all backend tests PASS.

- [ ] **Step 2: Confirm configuration shape without printing values**

Run a bounded Python check that returns only booleans:

```bash
micromamba run -n qi-p0 python -c '
from app.config import Settings
s = Settings()
print({
  "qwen_api_key_present": bool((s.qwen_api_key or "").strip()),
  "qwen_workspace_id_present": bool((s.qwen_workspace_id or "").strip()),
  "qwen_model_present": bool((s.qwen_model or "").strip()),
})
'
```

Expected: all three booleans are `True`; no credential value is printed.

- [ ] **Step 3: Rebuild the real stack**

Run:

```bash
docker compose up -d --build postgres redis api worker frontend
curl --fail --silent http://localhost:8000/api/v1/health
curl --fail --silent http://localhost:3001/ >/dev/null
```

Expected: both health checks exit 0. Use the port actually published by current
`compose.yaml`; do not edit the existing uncommitted compose change.

- [ ] **Step 4: Execute one bounded real PDF Advisor smoke**

Use a one-page supported PDF containing at least one eligible local annotation.
Upload through `POST /api/v1/projects`, poll status, and wait for
`ready_for_review` or a sanitized failure. Do not print the project UUID,
credential, request body, crop bytes or Provider response.

Verify from the database/storage with a count-only script:

```text
automatic_result_count = 1
qwen_provider_call_count >= 1
advisor_validated_or_rejected_count >= 1
working_copy_count = 1
```

Then repeat only the same logical task in a controlled integration check and
verify the external-call count does not increase.

- [ ] **Step 5: Inspect redacted runtime evidence**

Run:

```bash
docker compose logs --no-color --since=10m worker api
```

Inspect without copying secret-shaped values into reports. Expected:

- no `Authorization` header；
- no API key；
- no `data:image/png;base64`；
- no raw SDK response；
- no host filesystem source path；
- no unexplained traceback；
- actual Qwen call evidence is represented by count/provenance, not a fabricated ID.

- [ ] **Step 6: Review the diff without committing product code**

Run:

```bash
git diff --check
git status --short
git diff -- \
  backend/app/candidates/advisor.py \
  backend/app/candidates/coverage.py \
  backend/app/processing/automatic_result.py \
  backend/app/processing/pipeline.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/processing/tasks.py \
  backend/app/providers/call_records.py \
  backend/app/providers/runtime.py \
  backend/app/projects/service.py \
  backend/app/review/service.py \
  backend/tests \
  .agent/harness/scripts/run-p0.py
```

Expected: diff contains only Qwen runtime/provenance/test/Harness truth changes.
Do not stage yet; execute the QA-closure plan next, then use the user-mandated
final gate and commit message.
