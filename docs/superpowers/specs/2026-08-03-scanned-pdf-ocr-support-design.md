# Scanned PDF OCR Support Design

## Context

当前 `RuntimeRecognition` 已对纯扫描页执行 bounded Tencent OCR，并把通过非空文本、
PDF 坐标和 bbox 边界校验的结果保存为 additive `TextObservation(source_type="ocr")`。
但是页面仍保留 native classification 产生的
`processing_route="unsupported"`、`support_level="unsupported"`，随后
`InventoryPipeline` 无条件以 `unsupported_input` 终止。

2026-08-03 的真实重新识别证明了这个断点：目标 PDF 的单页 native text 为零、
image coverage 为 `1.0`，OCR 成功产生 `127` 条坐标化 observation，但 pipeline 仍在
`page_inventory` 阶段拒绝该页。source resolution、reprocess dispatch 和 OCR Provider
均已成功，因此重复调用现有路径不会改变结果。

## Goal

正式支持能够产生至少一条合法 OCR observation 的纯扫描 PDF，使其继续进入现有
candidate、coverage、Vision Advisor 和人工审核链，同时对空 OCR、无效 OCR、Provider
失败、损坏或加密输入继续 fail closed。

## Non-Goals

- 不把 OCR observation 改写成 native observation。
- 不允许 OCR Provider 提交 candidate disposition、review state 或正式检验项。
- 不新增 API、数据库 schema、runtime flag、Provider 或重试策略。
- 不对特定文件名、project ID、供应商、版式或 OCR 文本添加特判。
- 不自动确认扫描件结果；所有 promoted scanned page 都要求人工审核。
- 不改变 vector、hybrid、ambiguous、损坏或加密输入的现有路由。

## Stable Contract Delta

`PDF-008` 从“纯扫描输入只能显式 unsupported”收敛为以下 page-level routing：

1. native classification 仍先把 `native_char_count < 20` 且
   `max_image_coverage >= 0.8` 的页面分类为 `page_type="scanned"`。
2. OCR 只产生 additive observation，并逐条通过现有非空文本、PDF bbox、坐标变换和
   page identity 校验。
3. 本页至少产生一条合法 OCR observation 时，Input routing Owner 将该页提升为
   `processing_route="hybrid"`、`support_level="review_required"`、
   `review_required=true`，并清除 `unsupported_reason`。
4. 没有合法 OCR observation 时，页面继续保持
   `processing_route="unsupported"`、`support_level="unsupported"` 和
   `unsupported_reason="pure_scanned_pdf_not_supported"`。
5. 多页或 mixed PDF 按页执行相同判定；任一页面仍为 `unsupported` 时，project 继续以
   `unsupported_input` 终止，不允许部分页面伪装成完整成功。

`PDF-005` 的 bounded OCR routing、`PDF-006` 的 Native/OCR additive lineage、
`CAND-005` 的 coverage completeness 和 `PROV-002` 的 Provider trust boundary 均保持不变。

## Ownership And Components

### Native Page Classification Owner

`backend/app/pdf/classification.py::classify_page()` 继续只根据 native PDF facts 产生初始
classification。它不读取 OCR 结果，也不声明扫描页已经可处理。

### OCR Evidence Owner

`backend/app/processing/runtime_recognition.py::RuntimeRecognition.build_inventory()` 继续负责
选择 bounded regions、调用 `OcrProvider`、校验 Provider observations 并将其投影到
canonical PDF coordinates。

该方法新增唯一 post-OCR promotion seam。promotion 只消费本轮已经成功 append 的合法
OCR observations，不重新调用 Provider，不重新解析文本，也不修改原有 observation。

### Processing Veto Gate

`backend/app/processing/pipeline.py::InventoryPipeline.run()` 保持现有 gate：只要任一 page
的最终 `support_level` 仍是 `unsupported`，就记录 blocking `unsupported_input` 并终止。
它不自行推断 OCR 是否足够，也不建立第二个 promotion Owner。

## Promotion Shape

promotion 后页面必须满足：

```text
page_type = "scanned"
processing_route = "hybrid"
support_level = "review_required"
review_required = true
unsupported_reason = null
classification_rule_version = "v0.2-scanned-ocr-promotion"
classification_evidence["ocr_observation_count"] = <positive integer>
```

`classification_evidence` 中既有 native counts、image coverage 和 vector drawing count 原样
保留。新增的 `ocr_observation_count` 只证明 promotion 输入，不替代 observation payload 或
Provider receipt。

promotion 条件必须使用成功 append 后的 observation 集合。Provider 返回空集合、空文本、
无效 polygon、越界后退化为空 bbox，或所有 observation 均被过滤时，都不得 promotion。

## Data Flow

```text
immutable source PDF
  -> native PageInventory(page_type=scanned, support_level=unsupported)
  -> bounded page/image regions
  -> OcrProvider
  -> validated OCR TextObservations in canonical PDF coordinates
  -> append observations without replacing native facts
  -> post-OCR promotion to review_required when valid_count > 0
  -> existing InventoryPipeline unsupported gate
  -> existing candidate snapshot / coverage / Vision Advisor
  -> existing ReviewWorkingCopy bootstrap
  -> lifecycle successor promotion
```

## Failure Handling

- OCR Provider configuration或 preflight 缺失：保持现有 `ocr_provider_unavailable`。
- OCR network/adapter exception：保持现有 Provider failure 和 usage-ledger settlement 语义。
- OCR 成功但无合法 observation：页面保持 `unsupported`，最终记录
  `unsupported_input`。
- mixed PDF 中仍有 unsupported page：整个 project fail closed。
- candidate、coverage、Vision Advisor 或 review bootstrap 失败：保持现有 stage-specific
  error 与 reprocess successor failure；predecessor 继续 active。
- reprocess 成功：只有 working copy 成功创建后才 promotion successor，原 lifecycle 原子性
  不变。

## Privacy, Cost And Authorization

- 继续使用现有 bounded OCR region；不因扫描件支持而把整页发送给 Vision LLM。
- 不增加 OCR retry、crop expansion 或 Qwen attempt budget。
- Provider usage ledger、cycle authorization、pricing snapshot 和 reservation-before-submit
  规则保持不变。
- live acceptance 只允许一个新的 reprocess successor attempt；paid preflight 失败时不得
  创建 successor 或提交 Provider 请求。

## Test Design

### Unit

- 纯扫描页产生合法 OCR observation 后变为 `review_required`，同时保留
  `page_type="scanned"` 和全部 OCR observations。
- promotion 保存 positive `ocr_observation_count` 和固定 rule version。
- OCR 返回空 observations 时继续 `unsupported`，保留原 reason。
- vector/hybrid 页面 route、support level 和 native observation 顺序不变。
- mixed pages 只 promotion 有合法 OCR evidence 的 scanned page。

### Integration

- pipeline 消费 promoted scanned inventory 后不再触发 `unsupported_input`，继续创建
  automatic result 与 review working copy。
- 空 OCR scanned inventory 仍产生 blocking `unsupported_input`。
- reprocess 成功后 successor 变为 active、predecessor 变为 superseded；失败时 predecessor
  保持 active。
- contract checks 证明没有 API/schema drift，`PDF-005/006/008` 映射完整。

### Live Acceptance

在 approved public runtime 对
`ZH18030601-15#手臂滑板#A0.pdf` 的 active predecessor 执行一次重新识别：

1. zero-paid preflight 证明 API/worker code identity、database revision、credential presence、
   cycle authorization 和 runtime target 正确；
2. `POST /api/v1/projects/{project_id}/reprocess` 只发送一次并返回 `202`；
3. successor inventory 保持 `page_type="scanned"`，包含 OCR observations，且最终
   `support_level="review_required"`；
4. successor 达到 `ready_for_review`，predecessor 在此之前保持 active，成功后才变为
   superseded；
5. headed UI 进入人工审核入口，console 无新增 error；
6. 如果 paid attempt 失败，不自动 retry，并保留完整 error、usage 和 lifecycle evidence。

真实文件只作为验收样本，不参与任何 production branch 或 promotion condition。

## Rollback

回退 post-OCR promotion、相关 tests 和 `PDF-008` contract delta；不删除任何 project、
successor、Provider ledger 或 error record。rollback 后首先运行空 OCR failure-path test，
证明纯扫描页恢复为 fail closed；随后运行 vector/hybrid regression tests，证明既有支持路径
未被改变。

## Acceptance Criteria

- OCR 成功的 scanned page 可审计地进入 `review_required`，不再被 native-only
  `unsupported` classification 阻断。
- OCR 无有效结果和 mixed unsupported inputs 继续 fail closed。
- Native/OCR lineage、Provider trust boundary、budget、lifecycle atomicity 和 stable API/schema
  均保持不变。
- focused/full backend tests、contract gates、independent review 和当前真实 PDF live acceptance
  全部通过后，才允许声明正式扫描 PDF 支持完成。
