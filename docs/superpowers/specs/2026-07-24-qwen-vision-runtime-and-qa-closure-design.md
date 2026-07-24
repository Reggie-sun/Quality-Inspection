# Qwen Vision Runtime and QA Closure Design

**Status:** Approved in conversation on 2026-07-24

## Problem Statement

当前生产处理链只执行原生 PDF 解析和按需 OCR。仓库虽然已经存在
`QwenVisionProvider`、冻结 JSON Schema、Provider contract tests 和服务端配置，
但 canonical Celery runtime 没有 Qwen factory、没有 `review_candidate()` 调用方，
也没有 Vision crop、确定性建议校验、缓存或生产调用记录。

因此，配置存在并不代表能力已经接通。现有 offline tests 还会手工注入 Qwen
request ID，不能继续作为生产接入证据。

同时，前端 QA 仍有以下已确认风险：

- status API 没有独立的解析、识别和审核准备 projection；
- 当前检验项没有可持久化备注字段；
- PDF 页码卡片不是真实缩略图；
- “适合页面”只恢复 100%，不是 fit-to-container；
- 少数 `retryable=false` 的非输入错误使用了不准确的下一步文案；
- 极高密度图纸的候选层仍有轻微视觉拥挤。

## Goals

1. 将现有 `QwenVisionProvider` 接入 canonical processing runtime。
2. 保持 Vision LLM 为 Advisor，确定性 candidate/coverage Owner 不变。
3. 只发送必要的局部 crop，并保存可审计、脱敏、可缓存的调用事实。
4. 用后端真实状态投影解析、识别和审核准备阶段，不显示虚假百分比。
5. 增加审核项可选备注，保留到 immutable `reviewed_result`，不改变固定 SIP 模板。
6. 修复真实 PDF 缩略图、fit-to-container 和失败下一步中文文案。
7. 保持保存、冻结、气泡、确认和导出顺序不变。

## Non-Goals

- 不部署自托管 `vLLM` 服务。
- 不增加第二个 Vision Provider 或运行时 Provider 选择 UI。
- 不把整页 PDF、标题栏、签名、物料信息或完整工程文本发送给 Qwen。
- 不允许 Qwen 直接提交 disposition、review state、正式编号、geometry、检测方法或导出内容。
- 不修改 SIP Excel 固定模板、mapping 或正式导出列。
- 不重写 candidate、review、balloon 或 export 数据流。
- 不新增依赖，不修改 `frontend/package.json`。
- 不修改 sealed receipts 或 `.agent/harness/runs/`。
- 不重做气泡布局算法。

## Contract Boundaries

以下现有合同保持不变：

- `CAND-004`: Vision LLM 只按需复核局部候选，建议必须通过冻结 Schema 和确定性 validator。
- `CAND-005`: coverage Owner 是进入 automatic result 的唯一 veto gate。
- `PROV-001..005`: Provider 只提供 Signal/Advisor；secret、privacy、failure 和调用元数据边界不变。
- `PDF-002/005/006`: PDF 坐标、OCR 局部补充和 source relation 保持权威。
- `PRJ-004/005/006`: Project state、失败和 retry truth 仍由后端正式事实决定。
- `REV-002`: working copy、freeze 和 reviewed result 顺序不变。

本 successor 增加的 optional stage projection 和 `remarks` 字段必须向后兼容。
旧客户端省略这些字段时，现有 API 行为保持有效。

## Selected Architecture

### Canonical Data Flow

```text
source PDF
→ native inventory
→ optional local OCR
→ deterministic candidate snapshot
→ bounded Qwen Vision Advisor
→ deterministic suggestion validation
→ coverage veto
→ immutable automatic_result
→ review working copy
→ immutable reviewed_result
```

`candidate_snapshot_from_inventory()` 继续拥有确定性候选和 coverage 初始语义。
新增的 candidate-domain Advisor executor 只能在该 snapshot 之后运行，并把经过本地
validator 接受的建议或 provenance 返回给同一个 automatic-result Owner。

### Runtime Components

- `backend/app/providers/runtime.py`
  - 增加 `VisionProviderFactory` 和 `build_vision_provider()`。
  - 使用当前 `QI_QWEN_API_KEY`、`QI_QWEN_WORKSPACE_ID` 和 `QI_QWEN_MODEL`。
  - 构造
    `https://{workspace_id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
    OpenAI-compatible base URL。
  - 配置缺失或 workspace 格式非法时抛出脱敏 `CapabilityUnavailable`。
- `backend/app/candidates/advisor.py`
  - 拥有 routing、crop request、cache key、suggestion validation 和 provenance。
  - 不拥有正式 disposition、coverage verdict 或 review state。
- `backend/app/processing/runtime_recognition.py`
  - 每个 Celery task 使用一个实例。
  - 先建立 inventory，再把 source path、pages 和 deterministic snapshot 交给 Advisor executor。
  - 合并 OCR 与 Vision 的真实 request IDs。
- `backend/app/processing/pipeline.py`
  - 仍拥有编排、failure recording、coverage veto 和 automatic-result freeze。
  - 对 Vision transport/schema failure 记录脱敏 `candidate_advisor` stage。

## Advisor Routing

### Eligible Inputs

按 page、Y、X、稳定 source ID 排序，只复核以下局部事实：

1. `coarse_type` 为 `geometric_tolerance`、`roughness` 或 `weld`；
2. `item_type="composite"`；
3. 当前候选 `requires_confirmation=true`；
4. source observation 来自 OCR；
5. 确定性 parser 未形成候选、coverage disposition 为 `ambiguous`。

明确、单行、确定性 parser 已完整处理且不需要确认的普通尺寸不得调用 Qwen。

每页最多发起 16 个 Vision review。达到上限后，其余对象保持原结果并标记
`requires_confirmation`；不得把未调用显示为已由模型复核。16 是本 successor 的
成本和隐私保护实现上限，不是新的业务语义 Owner。

### Crop Rules

- crop 只由关联 observation 的 PDF bbox union 产生。
- 四边 padding 为 `clamp(annotation_height, 6pt, 24pt)`。
- crop 必须裁剪到当前 page CropBox。
- render scale 固定为 2。
- 不允许 fallback 为整页截图。
- 当前版本不自动扩大 crop；上下文不足时保持人工确认。
- 保存 page index、candidate/source IDs、crop bbox、padding、PNG SHA-256 和受控 asset ref。
- 浏览器、API projection、日志和 manifest 不暴露 asset ref、request ID 或内部 ID。

## Cache and Call Records

cache key 使用排序 JSON 后计算 SHA-256，至少包含：

- provider role 和 adapter version；
- model；
- Prompt version；
- Schema version；
- page index；
- crop bbox；
- crop SHA-256。

缓存只保存冻结 Schema 已验证的 suggestion、request ID、model、Prompt/Schema
版本和 usage summary。不得保存 API key、Authorization、完整 base64、SDK raw body
或 reasoning-like 内容。

cache hit 复用原始 request ID 和 validated suggestion，不产生新的付费调用。
页面刷新、审核编辑、移动气泡、重新编号和导出不得触发 Vision 调用。

`ProviderCallRecord.estimated_cost` 允许为 `null`。没有已冻结计价版本时不得写死
`0` 冒充零成本。

## Deterministic Acceptance

冻结 JSON Schema 只证明响应结构有效，不能直接证明业务建议可接受。validator
必须执行以下检查：

1. suggestion `raw_text` 与 source 原文经 NFKC 和空白归一化后相同；
2. suggestion `item_type` 必须属于本地允许集合；
3. 已有 typed candidate 的 suggestion type 必须与当前 type 相同；
4. coarse candidate 的 suggestion type 必须与当前 `coarse_type` 相同；
5. suggestion 不得包含 geometry、disposition、review、numbering、method 或 export 字段；
6. `requires_confirmation` 只能保持或升级，Advisor 不能自行解除人工确认。

对于已有 typed candidate，validator 可以采用经过再次本地解析且类型一致的
`normalized_text`，但必须保留原始文本、坐标和现有 typed numeric fields。

对于 deterministic parser 失败的 ambiguous observation，只有当：

- suggestion raw text 匹配；
- `parse_annotation(suggestion.normalized_text)` 成功；
- parser 结果类型与 suggestion type 相同；

才允许创建新的 candidate。该 candidate 必须保留原始 raw text 和 source bbox，
并强制 `requires_confirmation=true`。否则原 observation 保持 ambiguous。

每个 routed object 保存一个 optional `advisor_review`。对象字段固定为：

- `provider_role="advisor"`；
- 命中本地枚举的 `review_reason`；
- 实际 `model`、`prompt_version` 和 `schema_version`；
- 零起始 `page_index`；
- 四个有限数字组成的 `crop_bbox_pdf`；
- 当前 PNG 内容计算得到的 64 位小写十六进制 `crop_sha256`；
- boolean `validated`；
- validator 接受时为 `null`、拒绝时为本地枚举值的 `rejection_code`。

该对象属于 immutable raw automatic result provenance。Review working copy 不得把它
变成正式业务字段，workbench API 不投影内部 refs 或 request IDs。

## Failure Semantics

- 配置缺失：`vision_provider_unavailable / preflight / retryable=false`。
- Qwen transport、timeout、response shape 或 JSON Schema failure：
  `vision_provider_call_failed / candidate_advisor / retryable=true`。
- Schema 合法但确定性业务 validator 拒绝：处理继续，保留原候选或 ambiguous，
  并要求人工确认；这不是 Provider outage。
- 任何 Provider failure 都使用脱敏 ErrorRecord，不保存或返回 SDK message、URL、
  payload、credential、路径或 traceback。
- failed processing 不创建新的 automatic result、working copy、reviewed result 或 export。

## Processing Stage Projection

新增 Alembic revision `0007`，为 `logical_jobs` 增加：

```text
processing_stage varchar(32) not null default 'queued'
```

允许值：

- `queued`
- `parsing`
- `recognizing`
- `preparing_review`

stage transition：

```text
project accepted → queued
task claimed and preflight begins → parsing
inventory stored and candidate/Advisor work begins → recognizing
automatic_result committed and review bootstrap begins → preparing_review
working copy exists → phase=ready_for_review, response stage=null
```

`ProjectStatusResponse` 增加 optional `stage`。`phase` 和 `workbench_ready` 的现有
含义不变。`stage` 只投影未完成任务的内部阶段：queued phase 返回 `queued`，
processing phase 返回其当前 stage；ready/failed phase 返回 `null`。前端只根据
该字段显示阶段文字，不推断百分比。

## Review Remarks

`set_sip_detail_fields` 增加 optional `remarks: string`：

- 默认空字符串；
- 最大 2000 个字符；
- 空值合法，不参与 SIP confirmation blocker；
- 与其他 SIP detail fields 一起保存、取消和清理；
- freeze 后不可修改；
- 复制到 immutable `reviewed_result.items`；
- 不进入当前固定 SIP Excel detail mapping。

前端在当前检验项详情显示“备注（可选）”多行输入。保存沿用现有 explicit save
command，取消恢复服务端 baseline；不得显示自动保存。

## PDF Workspace

### Real Thumbnails

- 每个 page button 使用该 `PdfDocumentLike` 的独立 canvas 渲染真实页面缩略图。
- 缩略图保持页面比例，最长边受现有侧栏尺寸约束。
- PDF 尚未加载或单页缩略图渲染失败时显示中文页码 fallback，不阻断主画布。
- 当前页仍使用 `aria-current="page"`，button 保持中文 accessible name。

### Fit-to-Container

“适合页面”读取 `.pdf-scroll-frame` 的真实 content box 和当前 unscaled viewport，
计算：

```text
min((available_width - 24) / page_width,
    (available_height - 24) / page_height)
```

结果限制在 `0.1..4`，同时把 pan 恢复为 `(0, 0)`。容器没有可测尺寸时保持当前
scale，不伪造 100%。用户后续手动缩放仍使用现有按钮。

### Density Polish

只调整同一区域的候选 marker 默认透明度、hover/focus/selected 强调和缩略图占用，
保证选中项、来源和正式气泡仍清楚。不得删除候选、隐藏 collision 状态或修改
balloon placement。

## Error Copy

前端下一步文案按错误类别生成：

- invalid/unsupported input：重新选择符合支持范围的 PDF；
- retryable dependency/dispatch failure：重新处理或选择其他文件；
- non-retryable configuration/processing failure：重新选择 PDF；若文件有效，联系管理员检查服务配置；
- unknown terminal failure：说明没有生成正式结果，并给出重新选择和联系管理员的路径。

`retryable` 只控制是否显示“重新处理”，不再单独决定所有中文说明。

## Harness and Evidence Truth

- 删除 offline tests 中手工注入 Qwen request ID 的替代路径。
- offline provider tests 必须通过同一个 injectable production Advisor seam。
- current P0 Harness 的 project preparation 不能直接调用绕过 `RuntimeRecognition`
  的默认 `InventoryPipeline`。
- fixture 模式继续禁止 network。
- live Vision evidence 必须来自当前 code/config/input identity，并只报告实际调用。
- 不修改历史 receipt 或 `.agent/harness/runs/`。

## Test Strategy

### Backend

- Provider factory：base URL、model、缺配置、workspace validation 和 secret redaction。
- Advisor unit：routing、page call cap、crop bounds/hash、cache hit、typed acceptance、
  coarse rejection、ambiguous deterministic promotion、confirmation monotonicity。
- Processing integration：canonical task 调用 fake Vision Provider；同一 logical job
  不重复调用；request IDs/provenance 进入 automatic result。
- Failure integration：transport/schema failure 写入 sanitized `candidate_advisor`
  ErrorRecord，无 formal result。
- Status API：四个 stage projection、failure 和 ready precedence。
- Review API：remarks save/cancel/freeze/reviewed-result immutability。
- Migration：upgrade 到 `0007`，schema test 包含新 column。
- Offline E2E/Harness：走 production seam，fixture 模式保持 `external_calls=0`。

### Frontend

- 真实缩略图调用每一页的 `getPage()` 和 `render()`。
- 缩略图单页失败不破坏主画布。
- fit 使用真实容器尺寸、保持比例并归零 pan。
- status stage 分别显示解析、识别和审核准备。
- remarks 保存与取消 payload 正确。
- terminal error guidance 按 code/retryable 组合显示。

### Runtime

- 对一个真实支持范围内 PDF 执行裸根上传闭环。
- 数据库证明 automatic result 有至少一个真实 Qwen request ID/provenance。
- Worker 日志无 credential、base64、SDK raw body、内部路径或未解释异常。
- Chrome 验证真实缩略图、fit、阶段中文、备注保存和原有 review/balloon/export 顺序。

## Rollback

如果新版本在 migration 后无法安全运行：

1. 回退应用代码到 migration 前版本；
2. 仅在确认旧应用不再写 `processing_stage` 后执行 `alembic downgrade 0006`；
3. 第一项验证是旧版 health check 和一个不产生 Provider 调用的项目 status 请求；
4. 不删除既有 automatic/reviewed/export 结果或 Provider cache artifacts。

正常完成路径不执行 downgrade。

## Acceptance Criteria

- canonical production task 对 eligible local candidate 真实调用 Qwen。
- clear deterministic candidate 不产生 Qwen 调用。
- 同一 cache key 不重复产生外部调用。
- Qwen 建议无法越过 deterministic validator。
- Provider transport/schema failure 不形成 formal success。
- status API 和中文 UI 展示真实解析、识别、审核准备阶段，无百分比。
- 备注可保存、取消、冻结并进入 reviewed result，但不改变 SIP Excel。
- 页码侧栏展示真实缩略图；fit-to-container 使用真实容器尺寸。
- retryable=false 非输入错误不再要求用户“重新选择有效 PDF”。
- 无新增依赖、无内部 ID/credential/raw Provider 内容泄漏。
- frontend tests、backend tests、production build、contract check 和当前真实 Chrome smoke 通过。
