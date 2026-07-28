# Engineering Drawing Symbol Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不新增第二条 candidate/result path 的前提下，让 current source 中与 native text 相邻的工程图 vector symbols 进入稳定 visual observations，经 bounded Qwen Advisor 和确定性本地 validator 投影为可审核 candidate、reference/non-inspection 或 actionable ambiguity，并在 D7-T3 前用 sanitized fixture 与 sealed current-PDF live evidence 证明没有静默漏检。

**Architecture:** `PageInventory` 以 additive `VisualObservation` 保存确定性的局部视觉事实；`candidate_snapshot_from_inventory()` 保留现有 text seeds，并把 visual IDs 加入 Coverage Ledger；现有 `CandidateAdvisor` 仍是唯一 Vision integration Owner，通过一个统一的每页 16-call scheduler 先处理 visual batches、再处理 text-review routes；Qwen 只返回 `visual-symbol-review/1` allowlisted detections，本地 validator 才能修改 candidate/coverage；working copy、source-review commands、frontend workbench 和 immutable result path 全部复用现有实现。

**Tech Stack:** Python 3.11、PyMuPDF 1.25+、Pydantic、JSON Schema、FastAPI、Celery、SQLAlchemy、OpenAI-compatible Qwen API、pytest、React 19、TypeScript 5.8、Vitest、Playwright、Chrome DevTools MCP、P0 Harness

---

## Status And Execution Boundary

- Design source:
  `docs/superpowers/specs/2026-07-27-engineering-drawing-symbol-recognition-design.md`。
- Design status: 用户已接受 commit `6920958` 中的
  `2026-07-28 Hybrid Proposal-Gate Amendment`；exact rule correction 已提交为
  `09f70df`，完整 overlays/zooms 和 Quality Owner gate 已于 `2026-07-28`
  按 exact evidence 关闭。
- Plan status: **approved subordinate implementation detail**。本文件不是第二份
  current plan；task ordering、scope 和 execution authorization 仍只来自下述唯一
  current plan。
- Current implementation plan 仍是
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`。
- Selected lane: `Heavy`，因为本变更修改 `PDF-007`、candidate recall/coverage、
  Provider schema、failure veto、frontend source projection 和 final live receipt。
- Current ordering: 已验证的 D7-T2 manual-balloon residual 保持完成；本能力必须作为
  同一 current plan 的 D7-T2 in-place closure amendment，在 D7-T3 final receipt
  之前完成。
- Execution progress: Task 0 activation commit 是 `994cbe4`；SR-1 sealed input
  contract commit 是 `d3fac79`；SR-2 deterministic observations commit 是
  `bb035bc`；SR-3 Provider contract commit 是 `90bfb43`。SR-4 Steps 1-7 已在当前
  七文件 working diff 中验证，但尚未 commit；Step 8 真实源 preflight 暴露
  `19/22 > 16/page` 后已 fail closed。SR-2A bounded feasibility 又以
  `capacity_feasibility_unproven` 完成且没有 code commit。SR-2B Step 1 exact
  rule correction 已提交为 `09f70df`，Steps 2-4 的 evidence、Quality Owner
  approval 和 stable-contract closure 已完成；当前唯一 next step 是本文件下述
  `SR-2C Step 1`，但本 approval turn 在该 step 前停止。不得重复 SR-1～SR-3、
  执行已退休的 SR-2A
  packing-only Steps 2-6、提交 SR-4、进入 SR-5 或调用 Provider。
- Live-label gate: Quality Owner approved manifest 已 seal 于 literal run
  `20260727T085747865239Z-5aa3e8d3`，staging 从 bytes 机械验证 200% overlay、
  `unlabeled_target_count=0`、九类 positive families 与九类 negative families。
  该 run 只关闭 input gate，不是 production GREEN、task receipt 或 Provider
  authorization。
- `.agent/EXECUTION_STATUS.md` 在本计划写作时不存在。执行者不得为绕过这一事实而
  发明 status；如后续由其他批准任务创建，只记录已经验证的结果。
- 若执行时存在与本计划无关的未提交改动，必须保护这些改动并逐文件 stage around
  them；不得使用 `git add .`，不得覆盖、清理或把它们带入 task commit。

## Proposal V3 Context-Compaction Recovery Amendment — 2026-07-28

本节是同一 current plan Task 8 Step 6 的 subordinate detail，不建立第二份 current
plan。historical SR-2B/SR-2C v2 design、approval、code 和 artifacts 保持
immutable；本节只拥有最新 live evidence 暴露的三个 proposal-overlap gaps。

- Selected lane: `Heavy`。
- Selected plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`。
- Single proposal Owner:
  `backend/app/pdf/visual_observations.py::build_page_visual_observations()`。
- Selection evidence: sealed run
  `20260728T095023589634Z-740b6624` 的 source/manifest、79/124 observations 和
  13/16 batches exact，但 `P1-P16`、`P2-P18`、`P2-P27` 的 proposal overlap
  仅为 `0.156364 / 0.032575 / 0.368643`。no-write v3 calibration 得到
  80/125 observations、13/16 official batches、56/56 positives `>=0.5`，
  frozen-negative overlap 保持 `4 any / 3 >=0.5`。
- Exact rule: 使用 accepted design 中 canonical
  `visual-observation/3` / `visual-proposal-gate/2` bytes，SHA-256 必须 exact 为
  `8b7b67f4e303c7cfb7648c9dc2b11530198216f4799ee485f49199f0e99a8cfa`。
  任何 byte、threshold、comparison、branch order 或 digest 不一致都 fail closed。
- Old path action: retire v2 “所有 `12 pt` 邻域 selected items 总是共同决定 bbox”
  和 “base context 超过 1% cap 时没有 compact proof path”这两个假设；preserve
  original item selection、base branches、dedup/order、priority、stable
  first-fit、crop limits、Coverage Veto 和 CandidateAdvisor ownership。不得保留
  v2 fallback/shadow path。

- [ ] **V3 Step 1: Commit only the frozen docs amendment**

  只允许本 design、本 subordinate plan 和唯一 current plan。不得修改
  `MAIN_CONTRACT_MATRIX.md`、production/test/frontend、sealed artifacts 或
  `.agent/EXECUTION_STATUS.md`。

- [ ] **V3 Step 2: Run the exact renderer twice without repository writes**

  renderer 只能写入两个 `mktemp -d -p /tmp` 目录，不 import/construct/call
  Provider。开始前 exact 验证 source SHA、sealed manifest SHA、rule bytes/digest、
  clean index 和 expected repository dirty set。两轮各输出且只输出：

  - `page-1-proposal-v3-overlay-200pct.png`
  - `page-2-proposal-v3-overlay-200pct.png`
  - `zoom-recovered-proposal-gaps.png`
  - `zoom-core-symbol-representatives.png`
  - `zoom-gdt-and-boxed-datum.png`
  - `zoom-revision-and-n5.png`
  - `zoom-frozen-negative-overlaps.png`
  - `proposal-v3-gate-report.json`

  八个文件必须逐 byte identical。report 必须记录 renderer SHA、source/manifest/
  rule identity、148/244 raw contexts、132/203 base-area contexts、80/125 final
  observations、13/16 official batches、每页 sorted-newline observation-ID digest、
  ordered batch-membership digest、reason counts、56/56 positive exact overlap、
  16 frozen-negative risks、exact-once、all crop/member/pixel/area limits、
  repeatability 和 Provider construction/calls=0；不得包含 source path、raw text、
  token、crop bytes 或 Provider payload。

- [ ] **V3 Step 3: Stop for an exact Quality Owner visual verdict**

  向用户提供两页完整 overlay、五张 zoom、report 和全部 SHA-256，并明确提示所有
  retained frozen-negative overlaps。只有用户在看到本轮 exact artifacts 后明确
  给出 approval，才允许写 canonical v3 verdict；overlap count、旧 v2 approval、
  “继续”或测试通过均不等于本 gate verdict。

- [ ] **V3 Step 4: After approval, close docs/contract and authorize TDD**

  approval commit 才允许修改本 design、本 subordinate plan、唯一 current plan 和
  `docs/contracts/MAIN_CONTRACT_MATRIX.md`，只绑定 exact verdict/artifact digests。
  随后新的 proposal-only TDD/code commit 才可修改
  `backend/app/pdf/visual_observations.py`、
  `backend/tests/unit/pdf/test_visual_observations.py` 和直接 cache-version consumer
  tests；不得修改 Provider、prompt v4、projection、evaluator、frontend 或 `main`。
  fresh Provider/live run 仍需后续单独 amendment。

## SR-2C Cache Contract-Test Ownership Amendment — 2026-07-28

- Selected lane: `Heavy`。
- Selected plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
  仍是唯一 current plan；本文件仍是 approved subordinate implementation detail。
- Selection evidence: SR-2C Step 4 按 approved single-source contract 删除
  `symbol_review.py::VISUAL_PROPOSAL_VERSION` 后，Step 5 的 `128` 个 focused tests
  通过，但既有
  `backend/tests/contract/test_qwen_symbol_provider.py` 仍 import 该已退休 symbol，
  导致独立 Step 7 review 的 collection probe 以 `ImportError`、`0 tests collected`
  fail closed。恢复 alias 会直接违反 design 中的 single proposal Owner 和
  `assert not hasattr(symbol_review, "VISUAL_PROPOSAL_VERSION")`。
- Validation action: `amend`，不是 `replan`。目标、production Owner、stable cache
  identity、Provider boundary 和 SR-4 七文件 ownership 全部不变；只把这个直接
  cache consumer test 加入 SR-2C allowed paths、focused checks 和 proposal commit。
  test 必须直接 import `PROPOSAL_RULE_VERSION`，baseline 使用 current v2，variation
  使用 legacy v1，继续证明旧 cache bytes miss。
- Writer ownership and order: 当前父 agent 是 plan、该 contract test 和所有现有
  working diff 的唯一 writer；reviewer 保持只读且不得 nested delegation。先提交
  本 docs-only amendment，再修 contract test、重跑 contract test 与 Step 5 matrix、
  重新执行 Step 7 review，最后由 Step 8 精确提交三个 proposal-owned files。
- Next verification:
  `test_qwen_visual_symbol_schema_and_cache_identity` 必须从 collection RED 转 GREEN；
  SR-2C Step 5 matrix 加 contract test 后全绿；index/dirty ownership、current-source
  `79/124`、batch `13/16`、Provider construction/calls=`0` 均保持。

## Historical SR-4 Step 8 Capacity Closure Amendment — 2026-07-28

用户批准过本次原地 amendment。它的 bounded feasibility 阶段已完成但没有取得
certificate；本节现只保留当时的 problem boundary 和执行证据，不再授权下述
packing-only production change。

- Selected lane: `Heavy`。当前第一阶段保持全部稳定 crop/proposal/call contracts
  不变，但若 feasibility 证明需要替换 frozen stable-first-fit 算法，必须先在本
  design/plan 中冻结新算法，再进入 production TDD。
- Selected plan:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
  仍是唯一 current plan；本文件仍只是 subordinate implementation detail。
- Selection evidence: sealed run
  `20260727T085747865239Z-5aa3e8d3` 的 exact source SHA-256
  `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`
  在当前冻结 proposal/crop/priority/first-fit 实现下产生：
  - page 0: `132` observations，natural order `17` batches，priority order `19`;
  - page 1: `203` observations，natural order `19` batches，priority order `22`.
  两页都超过 `16/page`；完整 pack 重放可重复，Provider calls 为 `0`。merge
  rejection 主要命中 `7.5%` area 与 `1536px` side，`32`-member cap 命中为 `0`。
- Validation action: bounded search 已执行并 fail closed：
  - page 0: `depth=76`、`expanded=248890`、`frontier=4096`；
  - page 1: `depth=72`、`expanded=249792`、`frontier=4096`。
  两页结果均为 `capacity_feasibility_unproven`，Provider construction/calls=`0`。
  这不是数学不可行证明，但 packing-only Step 2～6 已退休。SR-4 仍停在 Task 4
  Step 8；不提交当前七个 SR-4 code files，不进入 SR-5，不构造或调用 Provider。
- Writer ownership and order: 当前父 agent 是三份 amendment docs 与后续
  feasibility/TDD 的唯一 writer。任何 explorer/reviewer 均只读、不得 nested
  delegation。现有七个 SR-4 modified files 继续由父 agent 独占；不得让第二个
  writer 修改 `symbol_review.py` 或其 coupled tests。
- Old path action: stable-first-fit、priority、bbox/dedup 和 crop limits 保持不变。
  “只替换 packing primitive”不再是 executable next step；proposal admission
  correction 由下述 SR-2B/SR-2C 唯一拥有。
- Unchanged contract: 全部 `132/203` observation IDs 必须各出现恰好一次；
  `7.5%` page area、`300 DPI`、每边 `<=1536px`、每 crop `<=32`
  observations、`16` calls/page、visual-first、Coverage Veto、九类 positive /
  negative evaluation、sealed manifest 和 fail-closed errors 全部不变。
- Allowed paths and next verification are superseded by SR-2B/SR-2C below。
- Rollback: 本 historical amendment commit 是 `8e0c625`；没有 SR-2A code commit。
  sealed input run、manifest、diagnostic evidence 和 Provider-call audit 保留。

## Hybrid Proposal-Gate Correction Amendment — 2026-07-28

本 amendment 落实 accepted design commit `6920958`。它不创建第二份 current plan、
第二个 proposal Owner、第二个 candidate/result path、fallback、shadow path 或新的
Provider policy。

- Single proposal Owner:
  `backend/app/pdf/visual_observations.py::build_page_visual_observations()`。
  `inventory.py` 只持久化 Owner output；`automatic_result.py`、`symbol_review.py`
  和 `advisor.py` 只能消费 retained observations，不得二次 filter、merge、rank
  或按剩余 Provider slots truncate。
- Old path action: retire “每个 geometry-qualified native line 都形成
  `VisualObservation`”和本文件原 SR-2A packing-only Steps 2～6；preserve
  provisional context extent/gap/area、retained bbox、dedup/order、stable
  first-fit、priority、crop limits、Coverage Veto 和 `CandidateAdvisor` 唯一 final
  write ownership。
- Execution order:
  `SR-4 Steps 1-7 → SR-2A completed-unproven → SR-2B → SR-2C →
  SR-4 Steps 8-9`。SR-2B 是 docs/evidence gate；SR-2C 是 TDD/code gate。任一 gate
  未通过都不得进入后一步。
- Writer boundary: 当前父 agent 仍是唯一 writer。read-only explorer/reviewer
  不得修改文件或 nested delegation。现有 SR-4 七文件继续由父 agent 独占并保留，
  只在 SR-4 Step 9 一起 commit。
- Provider boundary: SR-2B/SR-2C 全程 Provider construction/calls 必须为 `0`。
  exact rule、full overlays、Quality Owner verdict、v2 TDD、current-source
  no-write preflight 与独立 review 全部通过前，不得开始 SR-4 Step 8 或任何 paid/live
  Provider action。

### Exact Rule Reproduction Correction

首次逐字执行 commit `e795744` 中的 SR-2B renderer 时，机械 gate 正确 fail
closed：page 0 / page 1 只得到 `62 / 105` retained observations、
`21/26 / 28/30` positive overlap，而不是冻结的 `79 / 124` 和
`26/26 / 30/30`。root cause 是 plan transcription 的两处不一致：

- 历史 calibration 使用 `sum(bool(style["dashes"]))`。PyMuPDF solid pattern
  `"[] 0"` 也为 truthy；plan 后来把 feature 误写为排除 solid 的
  `dash_count`，却沿用了历史 counts/digests。
- 冻结 observation-ID digests 使用
  `sha256("\n".join(sorted(ids)).encode("utf-8"))`；renderer 却改为 ordered
  JSON-list digest。

在原 wide branch 的其余全部前置条件内，历史 truthy-style count 与 selected
canonical `item_count > 3` 的命中集合 exact 相同：page 0 均命中 `23`，page 1
均命中 `39`；真正的 non-solid dash count 两页均命中 `0`。因此修正是对历史
candidate 的 exact reproduction，不是按 labels 调 threshold。冻结后的 wide
branch 名为 `geometry_wide_multi_item`；canonical rule SHA-256 为
`ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7`。

仅应用上述两项修正的 fresh no-write reproduction 已 exact 恢复：

- page 0: `132 provisional / 79 retained / 13 batches`，
  reason counts `21 compact / 23 wide-multi-item / 3 filled /
  32 short-token / 53 rejected`；
- page 1: `203 provisional / 124 retained / 16 batches`，
  reason counts `18 compact / 39 wide-multi-item / 6 filled /
  61 short-token / 79 rejected`；
- positive overlap `26/26 / 30/30`，全部四个冻结 ID/batch digests、
  repeatability、exact-once 和 limits 均通过；
- frozen-negative overlap 仍只是一项人工复核风险，不是 approval；Provider
  construction/calls=`0`，sealed manifest、production/test files 和现有七文件
  dirty set 均未改。

当前父 agent 是 SR-2B docs-only correction/approval closure 的唯一 writer。
unchanged contract 仍是 existing source/manifest identity、全部
crop/budget/coverage/fail-closed semantics 和 Quality Owner gate。Step 1
correction commit `09f70df` 后已完成两次 Step 2 renderer；Quality Owner 在完整
artifacts 和 retained-overlap 风险提示后明确批准，Step 4 只绑定 docs/stable
contract。本 turn 不进入 SR-2C。

## Problem Boundary

### Single Owner

`backend/app/candidates/advisor.py::CandidateAdvisor` 是唯一 Vision integration
Owner，也是唯一可在本地 validator 通过后写 automatic raw candidate/coverage 的
组件。既有 Review aggregate 仍只执行 Quality Owner 显式
`promote_source` / `ignore_source` working-copy commands；该人工 override 不建立第二个
automatic Vision Owner。

`backend/app/candidates/symbol_review.py` 是纯 contract/validation/projection helper：
它可以返回 immutable decisions，但不得持久化、创建 `AutomaticResult`、修改
working copy 或调用 Provider。该拆分用于避免已经约 700 行的 `advisor.py` 继续
膨胀，不建立第二个 Advisor。

### Old Paths

- Preserve:
  `backend/app/processing/automatic_result.py::candidate_snapshot_from_inventory()`
  的 deterministic text candidate path。
- Preserve:
  `CandidateAdvisor` 现有 `text_review` route、text cache 和 fail-closed Provider
  policy。
- Replace:
  `_route_objects()` 中“按排序取每页前 16 个并静默跳过剩余 route”的局部预算逻辑，
  改为同一 Owner 内的 unified scheduler。
- New inside existing Owner:
  `visual_symbol` route、visual batch crop、strict response schema 和 local projection。
- Forbidden:
  second candidate writer、second result path、bridge、shadow、dual-write、fallback、
  feature flag、full-page Vision、global drawing clustering、Provider-owned disposition。

### Unchanged Contracts

- `CandidateType` 不新增 `counterbore`、roughness、GD&T 或 revision enum。
- `CoarseType` 不新增 symbol kind；roughness/GD&T 继续使用既有四字段
  `CoarseCandidate`。
- `raw_text` 保留 source bytes 的文字语义；canonical `Φ/深/⌴/∥/⊥/⏥` 只进入
  `normalized_text`，或进入既有 coarse `raw_text` 的受控图形转写。
- `Φ` 不等于 `hole`；`feature_kind` 保持 `unknown` 并要求人工确认。
- Coverage Ledger 仍是唯一 completeness Veto Gate。
- `ReviewService.create_from_raw()`、existing promote/ignore commands、freeze、
  balloon、confirm 和 export 顺序不变。
- qualifying `revision_marker` 的 automatic Owner decision 固定为
  `non_inspection + candidate_id=null + requires_confirmation=true`。只有 Quality
  Owner 显式执行既有 `promote_source` 并提供全部 manual fields 后才可创建 manual
  item；`ignore_source` 确认 non-inspection。Provider、validator、automatic
  processing 和 frontend inference 均不得调用或模拟该 override。
- 已有 `AutomaticResult`、working copy 和 reviewed result 不原地补写；current source
  用新 project upload 产生新 result。
- fixture tests 必须 `external_calls=0`；live Provider call 只能发生在已 seal 的
  current-source run。

### Fixed Failure Semantics

| Failure | Required result |
| --- | --- |
| Unknown vector opcode、NaN/Inf 或无法 canonicalize 的 style | visual proposal blocking；不调用 Provider |
| 单个 padded observation 超过 crop 限制 | `visual_crop_oversize`；无 `AutomaticResult`/working copy |
| visual batches 每页超过 16 | `symbol_route_budget_exhausted`；不得截断后成功 |
| Provider unavailable、request、root schema 或 cache/audit failure | 现有 `vision_provider_call_failed` / `candidate_advisor` fail-closed path |
| detection source/bbox/duplicate/projection invalid | 原 candidate bytes 不变；该 visual observation 变为 actionable `ambiguous`，只保存脱敏 rejection code |
| visual observation 没有 detection | `ambiguous + requires_confirmation=true + visual_no_detection` |
| text-review routes 超过 visual 后的剩余 slots | 保留现有 object，不写假 provenance；不是 visual success |
| visual coverage 缺 source/coordinates/disposition 或出现重复 primary disposition | `coverage_blocking`；无 formal result |

## OSS Research Decision

本计划已按 `github-oss-fusion` 做 license-safe 调研，只吸收结构和测试思想，不复制
外部实现：

- PyMuPDF:
  官方 `Page.get_drawings()`/drawing path contract 与 upstream drawing tests 证明
  vector geometry 应按 path item、style、close-path 和 bbox 做 deterministic
  serialization；`cluster_drawings()` 面向 tables/charts，不能作为本任务的全局
  symbol detector。融合：golden canonical bytes、close-path/style/non-finite
  regressions。跳过：任何 upstream source copy；当前 dependency 的 AGPL/commercial
  license 边界不因本任务扩大。
- Docling:
  `StandardPdfPipeline` 和 threaded pipeline tests 展示了 stage-specific failure
  envelope、bounded queues/batches、options identity 与 repeated-run equivalence。
  融合：visual proposal / scheduling / provider / projection 分阶段失败，batch
  identity 进入 cache，重复运行比较 exact output。跳过：引入 Docling、PyTorch、
  layout/OCR pipeline 或第二套 document owner。
- Deepdoctection 仅作为额外架构对照阅读；它是广义 Document AI pipeline，不适合
  current P0 的窄 symbol lane，因此不引入 dependency、component graph 或 annotation
  owner。

## Final File Map

### Create

- `backend/app/pdf/visual_observations.py`
- `backend/app/candidates/symbol_review.py`
- `backend/app/providers/visual_symbol_review.schema.json`
- `backend/tests/helpers/__init__.py`
- `backend/tests/helpers/symbol_fixture.py`
- `backend/tests/unit/pdf/test_visual_observations.py`
- `backend/tests/unit/candidates/test_symbol_advisor.py`
- `backend/tests/contract/test_qwen_symbol_provider.py`
- `backend/tests/integration/test_symbol_recognition_pipeline.py`
- `backend/tests/e2e/test_symbol_recognition.py`
- `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json`
- `.agent/harness/schemas/visual-symbol-eval.schema.json`
- `.agent/harness/schemas/visual-symbol-annotation-verdict.schema.json`
- `.agent/harness/scripts/stage-symbol-eval.py`
- `.agent/harness/scripts/symbol_eval.py`
- `backend/tests/contract/harness/test_symbol_eval_contract.py`

### Modify

- `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- `.agent/harness/contracts/p0-contracts.json`（generated）
- `.agent/harness/contracts/global-contract-bindings.json`（generated）
- `.agent/harness/policy/provider-call-policy.yaml`
- `.agent/harness/policy/p0-acceptance-policy.yaml`
- `.agent/harness/schemas/live-run-evidence.schema.json`
- `.agent/harness/scripts/check-contracts.py`
- `.agent/harness/scripts/generate-receipt.py`
- `.agent/harness/scripts/live_evidence_policy.py`
- `.agent/harness/scripts/run-p0.py`
- `.agent/harness/scripts/run-provider-contracts.py`
- `backend/tests/contract/harness/test_contract_architecture.py`
- `backend/tests/contract/harness/test_live_run_contract.py`
- `backend/app/pdf/schemas.py`
- `backend/app/pdf/inventory.py`
- `backend/app/processing/automatic_result.py`
- `backend/app/candidates/advisor.py`
- `backend/app/candidates/coverage.py`
- `backend/app/providers/base.py`
- `backend/app/providers/qwen_vl.py`
- `backend/app/processing/runtime_recognition.py`
- `backend/app/processing/pipeline.py`
- `backend/app/processing/tasks.py`
- `backend/app/review/service.py`
- `backend/app/projects/router.py`
- `backend/tests/contract/test_provider_call_records.py`
- `backend/tests/integration/test_error_records.py`
- `backend/tests/integration/test_processing_entry_task.py`
- `backend/tests/integration/test_project_workbench_api.py`
- `backend/tests/integration/test_result_layers.py`
- `backend/tests/integration/test_review_operations.py`
- `backend/tests/integration/test_review_working_copy.py`
- `backend/tests/integration/test_task_idempotency.py`
- `frontend/src/api/types.ts`
- `frontend/src/components/review/ReviewPanel.tsx`
- `frontend/src/components/review/ReviewPanel.test.tsx`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- `frontend/src/components/pdf/PdfWorkspace.tsx`
- `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`
- existing PDF/candidate/provider/pipeline/result regression tests only where an additive
  assertion is required; existing expectations不得改宽、skip 或删除。

### Explicitly Out Of Scope

- database migration 或新 table；
- new API endpoint、visual-only review command 或 frontend recognition logic；
- OCR behavior、page classification thresholds、balloon/export semantics；
- full-page/fixed-tile Vision；
- standalone symbols without nearby native line；
- additional symbol families、accuracy threshold platform 或 configurable thresholds；
- source PDF、live labels、screenshots、Provider response body 或 credentials 入 Git。

## Required Test Matrix

下面 32 项必须逐项存在；parameterization 只能覆盖同一 ID 内的 allowlisted variants，
不能合并跨 layer 的 ID。

| Task | IDs | Count |
| --- | --- | ---: |
| Task 2 | PDF-01～PDF-05 | 5 |
| Task 3 | ADV-01～ADV-02、PROV-01～PROV-02 | 4 |
| Task 4 | ADV-03～ADV-09、COV-01～COV-04 | 11 |
| Task 5 | INT-01～INT-06 | 6 |
| Task 6 | FE-01～FE-03 | 3 |
| Task 7 | E2E-01～E2E-02 | 2 |
| Task 8 | LIVE-01 | 1 |
| **Total** |  | **32** |

SR-2C 不新增 logical ID；它扩展 PDF-01/PDF-02/PDF-03 的 proposal semantics，并添加
一个 supporting cache-version regression。required total 必须继续 exact `32`。

## Task 0: Activate One Current Plan — Completed At `994cbe4`

- [x] 用户已批准本 subordinate implementation proposal。
- [x] commit `994cbe4` 已在唯一 current plan 中记录 problem boundary、single Owner、
  old-path action、`SR-1 → SR-8` ordering、live-label/literal-run-ID gate、exact allowed
  paths、rollback 和 focused verification。
- [x] activation 保持 `D7-T3` 在 `SR-8` 之后，未改写 prior sealed receipts，也未创建
  第二份 current plan、status registry、candidate/result path 或产品 Owner。
- [x] Option A contract clarification 已激活为 `SR-1` 前置语义。

Task 0 是历史完成记录，不得重跑、重新追加同名 amendment 或再次提交 activation
commit。执行从 Task 1 / `SR-1` contract/Harness RED 继续。

## Task 1: Amend Contract Owners And Seal The Live Evaluation Input

**Files:**

- Modify:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Modify:
  `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- Modify: `.agent/harness/contracts/p0-contracts.json`（generated）
- Modify: `.agent/harness/contracts/global-contract-bindings.json`（generated）
- Modify: `.agent/harness/policy/provider-call-policy.yaml`
- Create: `.agent/harness/schemas/visual-symbol-eval.schema.json`
- Create:
  `.agent/harness/schemas/visual-symbol-annotation-verdict.schema.json`
- Create: `.agent/harness/scripts/stage-symbol-eval.py`
- Modify: `.agent/harness/scripts/check-contracts.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Modify: `.agent/harness/scripts/run-p0.py`
- Create:
  `backend/tests/contract/harness/test_symbol_eval_contract.py`
- Modify:
  `backend/tests/contract/harness/test_contract_architecture.py`
- Modify:
  `backend/tests/contract/harness/test_live_run_contract.py`

### Step 1: Write RED Harness tests

- [ ] Add tests with these exact names:
  - `test_symbol_eval_schema_is_closed_and_current_source_bound`
  - `test_stage_symbol_eval_rejects_wrong_hash_bbox_or_family_set`
  - `test_symbol_eval_revision_marker_is_positive_noninspection_only`
  - `test_stage_symbol_eval_rejects_missing_or_duplicate_only_negative_family_coverage`
  - `test_symbol_eval_rejects_negative_family_on_positive_label`
  - `test_symbol_eval_requires_negative_family_on_frozen_negative_label`
  - `test_symbol_eval_artifacts_exclude_paths_pdf_bytes_and_screenshots`
  - `test_symbol_eval_loader_requires_literal_sealed_run_id`
  - `test_symbol_annotation_verdict_requires_exact_overlay_review`
  - `test_symbol_eval_byte_change_stales_input_identity`

The test bodies must use existing
`backend/tests/contract/harness/harness_test_support.py` helpers, a synthetic two-page PDF
with the wrong hash for negative cases, and a schema-valid manifest object. They must never
read the real current source. The literal-run loader test must also prove registration executes
no business selector、project mutation or Provider call. The contract cases must distinguish a
valid `symbol_kinds=["revision_marker"]`、`expected_disposition="non_inspection"` label from
`symbol_kinds=["frozen_negative"]` with
`negative_family="revision_table_or_invalid_marker"`; they must reject a missing negative family,
nine labels that repeat only one negative family, `negative_family` on any positive label, and
every frozen-negative label that omits `negative_family`.

- [ ] Run RED:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

Expected: FAIL because the two schemas、staging script、artifact allowlist and literal-run
loader do not exist.

### Step 2: Amend the Markdown Owners first

- [ ] Apply these semantic deltas without turning partial long-term contracts into false full
  P0 claims:

| Contract | Amendment |
| --- | --- |
| `PDF-007` | Add stable visual observation ID/bbox/geometry hash/text relations; current enforcement becomes `P0` only for the fixed current-scope proposal |
| `CAND-001` | Recall-first seeds may consume locally validated visual observations; keep `P0-partial` because not all future symbol families are implemented |
| `CAND-004` | Advisor scope includes local candidate or suspicious visual-observation crop; Provider still owns no disposition |
| `CAND-005` | Expected coverage includes visual IDs; unscheduled/budget-overflow visual observations are blocking |
| `CAND-006` | Ambiguous visual source remains locatable, promotable and ignorable |
| `ITEM-002` | Separate source `raw_text` from visual-assisted `normalized_text`; keep Decimal/source rules |
| `ITEM-003` | Reassert `feature_kind=unknown` for visual diameter and four-field coarse fallback |

- [ ] Amend `P0-REC-005`、`P0-REC-009` and `P0-REC-010` in place:
  - task becomes `D7-T2`;
  - status becomes `pending`;
  - selectors name both existing text tests and the exact new symbol tests;
  - implementation note says existing passed text proof remains valid but does not satisfy the
    visual delta.
- [ ] Do not modify any generated JSON by hand.

### Step 3: Define exact sealed artifacts

- [ ] Create `visual-symbol-eval.schema.json` with:
  - root `additionalProperties=false`;
  - `schema_version="visual-symbol-eval/1"`;
  - exact source SHA-256
    `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`;
  - `annotation_owner_role="quality_owner"` and `annotation_status="approved"`;
  - exactly two pages with unique non-negative `page_index`;
  - unique non-blank `label_id`;
  - positive-area four-number `bbox_pdf`;
  - sorted, unique `symbol_kinds` from the nine-kind allowlist plus
    `frozen_negative`;
  - exact disposition/projection enums from the design spec;
  - `revision_marker` is the ninth evaluation-positive family, requires
    pre-manual-command `expected_disposition="non_inspection"` and
    `expected_projection=null`, cannot coexist with `frozen_negative`, and is never
    automatically projected as an inspection item; a later explicit Quality Owner
    `promote_source` is outside live symbol evaluation;
  - conditional `negative_family` enum in this exact order:
    1. `part_or_hole_geometry`
    2. `hatch_center_or_cross`
    3. `dimension_leader_or_section_line`
    4. `view_or_section_label`
    5. `revision_table_or_invalid_marker`
    6. `datum_like_letter_or_table_cell`
    7. `watermark_logo_title_or_signoff`
    8. `isometric_hole_slot_or_edge`
    9. `ordinary_text_number_material_or_requirement`
  - `frozen_negative` cannot coexist with another kind;
  - `negative_family` is required when and only when
    `symbol_kinds` exact equal `["frozen_negative"]`; every positive label must omit it;
  - root、page and label objects keep `additionalProperties=false`.
- [ ] Create `visual-symbol-annotation-verdict.schema.json` with a closed object requiring:
  `schema_version` const `visual-symbol-annotation-verdict/1`;
  `annotation_owner_role` const `quality_owner`;
  `overlay_scale_percent` const `200`;
  `unlabeled_target_count` const `0`;
  script-derived `negative_family_count` const `9`;
  `manifest_sha256` matching `^[0-9a-f]{64}$`; and `recorded_at` using JSON Schema
  `format: date-time`.

- [ ] Set artifact names to:
  - `artifacts/visual-symbol-eval.json`
  - `artifacts/visual-symbol-annotation-verdict.json`
- [ ] Extend Harness input identity and schema inventory to bind both exact bytes.
- [ ] Extend `provider-call-policy.yaml` with
  `max_vision_calls_per_page: 16`; keep OCR and existing per-candidate fields.

### Step 4: Implement the staging command

- [ ] `stage-symbol-eval.py` accepts only the required `--source` PDF path、
  required `--manifest` JSON path、required `--mode live` and optional literal open
  `--run-id`; it rejects positional arguments and all other flags.

- [ ] Before writing an artifact, verify:
  - both inputs are real regular non-symlink files and do not change during read;
  - source header、exact SHA-256、two-page count and page bbox;
  - JSON Schema plus unique labels、bbox bounds、kind order、projection/disposition
    compatibility;
  - every one of the nine current positive families appears at least once;
  - the distinct manifest `negative_family` set exact equals the complete nine-value enum and
    every negative family has at least one label; missing-family or duplicate-family-only
    coverage fails regardless of total negative-label count;
  - output canonical JSON has no path、PDF bytes、base64、credential or screenshot field.
- [ ] Create the annotation verdict from the Quality Owner's fixed CLI confirmations
  `overlay_scale_percent=200` and `unlabeled_target_count=0`. Compute
  `negative_family_count=9` and per-negative-family counts only from the mechanically validated
  manifest; do not accept a human-entered or CLI-entered count as coverage proof and do not infer
  any value from model output.
- [ ] Extend `run-p0.py` with
  `register_live_input_artifacts(task_id="D7-T2", artifacts=...)`. It must reuse the existing
  Harness preflight、run schema、input identity、artifact validation、sealing and receipt
  code, record only `phase://live/symbol-eval-registration`, and execute no business selector、
  project mutation or Provider call. Do not create another run/receipt implementation.
- [ ] If no `--run-id` is supplied, call that canonical registration entry with the two input
  artifacts. If it is supplied, accept only the existing literal run ID regex and one open,
  unsealed D7-T2 live staging run; still pass through the same registration validation.
- [ ] Set all sealed run members read-only using the existing run sealing path; do not invent
  a second receipt implementation.

### Step 5: Generate mirrors and verify GREEN

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py -q
```

Expected: generated mirrors exactly match Markdown Owners; contract drift/conflict/missing are
zero; selected Harness tests PASS.

### Step 6: Quality Owner seals the real manifest

- [ ] Stop unless the Quality Owner supplies an approved manifest and confirms only
  `overlay_scale_percent=200` and `unlabeled_target_count=0` after the overlay review. Staging,
  not the Quality Owner, validates label IDs and derives total/per-family counts from manifest
  bytes.
- [ ] The operator sets local shell variables to real files without writing their values into
  Git or the plan:

```bash
test -f "$QI_SYMBOL_SOURCE_PDF"
test -f "$QI_SYMBOL_EVAL_MANIFEST"
micromamba run -n qi-p0 python \
  .agent/harness/scripts/stage-symbol-eval.py \
  --mode live \
  --source "$QI_SYMBOL_SOURCE_PDF" \
  --manifest "$QI_SYMBOL_EVAL_MANIFEST"
```

Expected: output contains one literal `run_id`, exact source hash verification, total label
count, per-positive-family counts, manifest-derived per-negative-family counts,
`unlabeled_target_count=0`, script-derived `negative_family_count=9`, and a sealed verdict. It
must not print either host path、screenshot data or PDF bytes.

- [ ] Copy the emitted literal run ID into the activated current-plan amendment. Do not record
  `latest` or an environment-variable alias. Production GREEN is blocked until this edit is
  committed.

### Step 7: Commit only Task 1

```bash
git add \
  docs/contracts/MAIN_CONTRACT_MATRIX.md \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md \
  .agent/harness/contracts/p0-contracts.json \
  .agent/harness/contracts/global-contract-bindings.json \
  .agent/harness/policy/provider-call-policy.yaml \
  .agent/harness/schemas/visual-symbol-eval.schema.json \
  .agent/harness/schemas/visual-symbol-annotation-verdict.schema.json \
  .agent/harness/scripts/stage-symbol-eval.py \
  .agent/harness/scripts/check-contracts.py \
  .agent/harness/scripts/generate-receipt.py \
  .agent/harness/scripts/run-p0.py \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py
git commit -m "test: seal symbol recognition acceptance"
```

## Task 2: Build Deterministic Visual Observations — Completed At `bb035bc`

本 task 记录 v1 baseline。SR-2C 只 supersede 下述
`PROPOSAL_RULE_VERSION="visual-observation/1"`、不检查 line text 和 unconditional
admission；canonical geometry、public fields、bbox/dedup/order、reconstruction 和
stable-first-fit 仍保持。不得重跑 Task 2 或把这些 historical v1 instructions 当成
current next step。

**Required test IDs:** PDF-01～PDF-05

**Files:**

- Create: `backend/tests/helpers/__init__.py`
- Create: `backend/tests/helpers/symbol_fixture.py`
- Create: `backend/tests/unit/pdf/test_visual_observations.py`
- Create: `backend/app/pdf/visual_observations.py`
- Modify: `backend/app/pdf/schemas.py`
- Modify: `backend/app/pdf/inventory.py`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/tests/unit/pdf/test_inventory.py`

### Step 1: Create the deterministic sanitized fixture

- [ ] `build_symbol_fixture(tmp_path)` generates, in the test temp directory only, a two-page
  vector PDF plus an independent manifest with:

| Family | Positive regions |
| --- | ---: |
| diameter | 4 |
| depth | 3 |
| counterbore | 2 |
| surface roughness | 3 |
| GD&T parallelism/perpendicularity/flatness | 3 |
| datum reference | 2 |
| revision marker | 2 |
| frozen negative regions | 12 |

- [ ] Use PyMuPDF drawing primitives and `insert_text()`; target symbols、native text and
  negative geometry must use separate helper functions.
- [ ] The 12 frozen negative regions collectively cover all nine exact `negative_family` enum
  values at least once. A closed triangle with one valid inner revision token is a positive
  `revision_marker/non_inspection`; revision-table cells and triangle-like geometry that fails
  that validator use `revision_table_or_invalid_marker`. Color is not a classifier.
- [ ] Return `(pdf_path, manifest)`; production code must never import this helper or read the
  manifest.
- [ ] Bind fixture identity to helper SHA-256、`symbol-fixture/1` and PyMuPDF version.
- [ ] Assert repeated generation produces identical PDF SHA-256、page boxes and manifest.

### Step 2: Write all five PDF RED tests

- [ ] Add tests with these exact names:
  - `test_visual_observation_id_and_order_are_stable`
  - `test_small_nearby_path_items_form_text_adjacent_context`
  - `test_large_distant_or_page_geometry_is_rejected`
  - `test_visual_bbox_round_trip_and_union`
  - `test_visual_batches_use_stable_first_fit`

- [ ] Test PDF-01 compares exact observation IDs、order、bbox、geometry SHA and associated
  text IDs across two runs.
- [ ] PDF-02 proves individual path width/height `<=96 pt` and both-axis gap `<=12 pt`.
- [ ] PDF-03 includes a part outline、dimension line、hatch、title border and a context whose
  union exceeds 1% page; all are absent from visual observations.
- [ ] PDF-04 round-trips existing `PageTransform` and checks exact source bbox union.
- [ ] PDF-05 runs exact 300-DPI packing and asserts stable batch membership、crop bbox、call
  order on the deterministic fixture. The separate Task 4 preflight owns the `V<=16` proof for
  both current-source pages.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py -q
```

Expected: FAIL because `VisualObservation` and the visual builder do not exist. If the real
sealed manifest is not yet available, stop here; RED is the only permitted production-code
boundary.

### Step 3: Add the additive inventory type

- [ ] Add this exact dataclass and defaulted page field:

```python
from typing import Literal


@dataclass(frozen=True)
class VisualObservation:
    observation_id: str
    source_type: Literal["visual"]
    observation_level: Literal["annotation_context"]
    page_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox
    proposal_kind: Literal["text_adjacent_vector_context"]
    geometry_sha256: str
    associated_text_observation_ids: tuple[str, ...]
```

Add `visual_observations: tuple[VisualObservation, ...] = ()` after the current
`PageInventory` non-default fields so dataclass construction remains valid. Existing callers
that omit it must remain byte-for-byte equivalent after JSON conversion.

### Step 4: Implement canonical geometry and proposal rules

下述 v1 rule 是 commit `bb035bc` 的 historical implementation record；SR-2C
完成后，version、text-shape feature 和 admission condition 由 SR-2B/SR-2C exact
rule 取代，其余 bullets 保持不变。

- [ ] In `visual_observations.py`, freeze:

```python
PROPOSAL_RULE_VERSION = "visual-observation/1"
MAX_PATH_ITEM_EXTENT_PT = 96.0
MAX_AXIS_GAP_PT = 12.0
MAX_CONTEXT_PAGE_AREA_RATIO = 0.01
HASH_QUANTUM = Decimal("0.001")
```

- [ ] Canonicalize each PyMuPDF path item as
  `opcode + ordered point/rect/quad coordinates`.
- [ ] Include `width/dashes/lineCap/lineJoin/color/fill`; missing values serialize as JSON
  `null`.
- [ ] Convert finite numeric values with
  `Decimal(str(value)).quantize(HASH_QUANTUM, ROUND_HALF_EVEN)` and remove negative zero.
- [ ] Permit color/fill only as null or 1～4 finite components; collapse ASCII whitespace in
  string dashes; permit line cap/join only as integer or integer array.
- [ ] Raise a typed blocking error for unknown opcode、non-finite coordinate or invalid style.
  Never skip the bad primitive.
- [ ] Sort path items by
  `(bbox.y0, bbox.x0, bbox.y1, bbox.x1, canonical_path_bytes)`.
- [ ] For every non-blank native line, select only individual path items meeting both
  `<=96 pt` extent and `<=12 pt` gap on both axes. Do not inspect the line text.
- [ ] Reject empty and `>1%` page union contexts.
- [ ] Associated IDs are the line plus native spans whose `parent_region_id` equals the line
  ID, sorted by ID.
- [ ] Deduplicate exact geometry digests, then IoU `>=0.8` proposals with identical associated
  IDs by retaining stable sort first.
- [ ] Compute the 24-char ID from:

```text
visual-observation/1
+ source_sha256
+ page_index
+ proposal_kind
+ bbox rounded to 0.001 PDF point
+ geometry_sha256
+ sorted associated text IDs
```

- [ ] Sort final observations by
  `(page_index, bbox.y0, bbox.x0, proposal_kind, observation_id)`.
- [ ] `inventory.py::build_inventory()` computes source SHA-256 once, builds native text first,
  then passes each page plus native observations to the visual builder. It must not call
  `cluster_drawings()`.
- [ ] The same module returns an internal, non-persisted `VisualGeometryContext` alongside each
  observation, containing only canonical path items needed by the local datum/revision
  validator. `PageInventory.to_dict()` persists only the frozen `VisualObservation` fields.
- [ ] Expose one pure reconstruction function that reopens the same source page, rebuilds these
  contexts with the same source hash/rule/version, and verifies reconstructed observation IDs
  exactly equal inventory IDs. `CandidateAdvisor` uses this function; a missing/extra ID or
  geometry-hash mismatch is a blocking proposal error. Do not add canonical path bytes to
  API、DB or inventory JSON.
- [ ] Add a priority-neutral
  `pack_visual_batches(page, ordered_observations)` pure function implementing exact
  padding、7.5% page area、300-DPI pixel preflight、1536-pixel side、32-observation stable
  first-fit and `visual_crop_oversize`. Task 4 owns priority ordering and the shared 16-call
  schedule, not a second packing implementation.

### Step 5: Add visual expected coverage without creating candidates

- [ ] Keep `_selected_observations()` text-only.
- [ ] Add a separate stable `selected_visual_observations(pages)` helper.
- [ ] After deterministic text candidate construction, append one initial
  `CoverageEntry(disposition="ambiguous", requires_confirmation=True)` per visual observation
  and add every visual ID to `CandidateSnapshot.expected_observation_ids`.
- [ ] Do not create a visual candidate in `automatic_result.py`; only `CandidateAdvisor` may
  replace this initial disposition.

### Step 6: Verify GREEN and regressions

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_coordinates.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_coverage.py -q
```

Expected: PDF-01～PDF-05 and existing inventory/OCR/coverage tests PASS; no current text
observation ID or candidate payload changes.

### Step 7: Commit only Task 2

```bash
git add \
  backend/tests/helpers/__init__.py \
  backend/tests/helpers/symbol_fixture.py \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/app/pdf/visual_observations.py \
  backend/app/pdf/schemas.py \
  backend/app/pdf/inventory.py \
  backend/app/processing/automatic_result.py \
  backend/tests/unit/pdf/test_inventory.py
git commit -m "feat: build deterministic visual observations"
```

## Task 3: Freeze The Visual Provider Contract And Cache Envelope

**Required test IDs:** ADV-01、ADV-02、PROV-01、PROV-02

**Files:**

- Create: `backend/app/providers/visual_symbol_review.schema.json`
- Create: `backend/app/candidates/symbol_review.py`
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/providers/qwen_vl.py`
- Modify: `backend/app/candidates/advisor.py`
- Create: `backend/tests/contract/test_qwen_symbol_provider.py`
- Create:
  `.agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json`
- Modify: `.agent/harness/scripts/run-provider-contracts.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Create: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/contract/test_provider_call_records.py`

### Step 1: Add the sanitized Provider fixture

- [ ] The committed fixture uses `provider-fixture/1`, `qwen-vl`,
  `visual-symbol-review/1`, opaque `fixture://` refs, a synthetic request ID and a JSON content
  value containing only two fake observation IDs.
- [ ] It must not contain a real crop、base64、host path、project ID、current-source text or
  credential-shaped value.
- [ ] Add it to `run-provider-contracts.py` and `generate-receipt.py` controlled-file identity.

### Step 2: Write the four RED tests

- [ ] ADV-01
  `test_visual_symbol_response_accepts_only_exact_schema`:
  exact fixture parses; missing required field、extra root/detection field and
  `requires_confirmation=false` raise `VisualSymbolSchemaError`.
- [ ] ADV-02
  `test_visual_symbol_response_rejects_invalid_identity_or_shape`:
  unknown observation ID、bbox outside `[0,1]`、non-positive bbox、unknown text source、
  duplicate detection tuple、more than four detections for one observation and unknown kind
  cannot yield an accepted detection or mutate a candidate.
- [ ] PROV-01
  `test_qwen_visual_symbol_schema_and_cache_identity`:
  Qwen request has one local crop, JSON-only non-thinking mode, exact prompt/schema version;
  cache key changes when crop hash、source hash、visual IDs、model、prompt、schema、adapter、
  proposal rule or PyMuPDF version changes.
- [ ] PROV-02
  `test_qwen_visual_symbol_records_are_redacted_on_success_and_failure`:
  success and invalid-schema call records include only request/response resource refs、hashes、
  versions、request ID、duration and usage; serialized records and raised messages exclude
  crop bytes、base64、SDK body、private path、credential and model explanation.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  -k "visual_symbol_response or qwen_visual_symbol" -q
```

Expected: FAIL because the schema、parser、Provider method and visual cache envelope are absent.

### Step 3: Freeze the JSON Schema

- [ ] Create a Draft 2020-12 schema with root and detection
  `additionalProperties=false`.
- [ ] Root fields:
  - `schema_version` const `visual-symbol-review/1`;
  - `detections`, array, maximum 128.
- [ ] Detection required fields:
  - `visual_observation_id`: non-blank string;
  - `symbol_kind`: enum of
    `diameter/depth/counterbore/surface_roughness/gdt_parallelism/`
    `gdt_perpendicularity/gdt_flatness/datum_reference/revision_marker`;
  - `bbox_normalized`: exactly four numbers in `[0,1]`;
  - `associated_text_observation_ids`: unique string array;
  - `requires_confirmation`: const `true`.
- [ ] Do not add confidence、transcription、item type、disposition、nominal、tolerance、
  feature kind or explanation fields.

### Step 4: Add pure response and decision types

- [ ] In `symbol_review.py`, define exact immutable boundaries:

```python
SymbolKind = Literal[
    "diameter",
    "depth",
    "counterbore",
    "surface_roughness",
    "gdt_parallelism",
    "gdt_perpendicularity",
    "gdt_flatness",
    "datum_reference",
    "revision_marker",
]


@dataclass(frozen=True)
class ValidatedSymbolDetection:
    visual_observation_id: str
    symbol_kind: SymbolKind
    bbox_pdf: BBox
    associated_text_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class RejectedSymbolDetection:
    visual_observation_id: str
    rejection_code: Literal[
        "visual_bbox_invalid",
        "visual_source_mismatch",
        "visual_duplicate_detection",
    ]
```

- [ ] `parse_visual_symbol_json()` validates the exact JSON Schema and raises
  `VisualSymbolSchemaError("visual symbol response violates frozen schema")` without echoing
  content.
- [ ] When the SDK returned a non-blank request ID but content is schema-invalid,
  `QwenVisionProvider.review_symbols()` raises a typed safe exception carrying only request ID
  and numeric usage; it must not attach or stringify the raw content.
- [ ] `validate_symbol_detections()` receives the current batch identities、per-observation
  text allowlists and crop→page transform. It:
  - converts normalized bbox to page coordinates;
  - rejects non-positive or crop-external bbox;
  - enforces current-batch visual IDs and text allowlist subsets;
  - permits at most four detections per observation;
  - rejects duplicate `(observation ID, kind, bbox rounded to 0.001)` tuples;
  - returns stable accepted/rejected tuples sorted by page reading order;
  - never returns Provider payload dictionaries to callers.

### Step 5: Extend the existing Provider port

- [ ] Add `review_symbols(image: bytes, prompt: str) -> VisionResult` to the existing Vision
  Provider protocol; keep `review_candidate()` unchanged for text routes.
- [ ] `QwenVisionProvider.review_symbols()` uses:

```text
system: Review local engineering drawing symbol contexts. Output JSON only.
user: one bounded PNG image + the canonical prompt + "Output in JSON format."
response_format: {"type": "json_object"}
extra_body: {"enable_thinking": false}
```

- [ ] It returns `VisionResult` only after `parse_visual_symbol_json()` succeeds and the SDK
  request ID is non-blank.
- [ ] It never accepts a full PDF or page image.

### Step 6: Add the visual cache/call-record envelope

下述 `visual-observation/1` cache component 是 commit `90bfb43` 的 historical
identity。SR-2C 必须将它改为从 proposal Owner 单一引用
`PROPOSAL_RULE_VERSION="visual-observation/2"`；不得保留第二个 version literal。

- [ ] Keep existing text cache bytes and `candidate-advisor-cache/1` untouched.
- [ ] Use a separate path pattern
  `projects/{safe_project_id}/provider-cache/qwen-symbol/{cache_key}.json` with
  `visual-symbol-advisor-cache/1`.
- [ ] Cache identity includes:

```text
source_sha256
visual observation IDs in stable order
crop_bbox_pdf
crop_sha256
model
visual-symbol-prompt/1
visual-symbol-review/1
qwen-openai-compatible/1
visual-observation/1
PyMuPDF version
```

- [ ] Cache hit requires an existing matching Provider call audit record; invalid bytes、
  missing audit、hash/version/schema mismatch raise sanitized `CandidateAdvisorFailure`.
- [ ] On a real call, persist crop and validated response through
  `LocalFileStorage.write_verified()` and `ProviderCallRecord`; do not put either body into
  DB、logs or coverage.
- [ ] On an invalid-schema call, persist a canonical sanitized failure response containing only
  `schema_version="visual-symbol-call-failure/1"` and
  `error_code="visual_schema_invalid"`, then persist the same allowlisted call record with the
  safe request ID/usage and that failure response ref. Raise the blocking
  `CandidateAdvisorFailure` afterward. Never persist the invalid Provider body.

### Step 7: Verify GREEN and existing text Provider behavior

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_advisor.py -q
micromamba run -n qi-p0 python \
  .agent/harness/scripts/run-provider-contracts.py
```

Expected: ADV-01、ADV-02、PROV-01、PROV-02 PASS; existing candidate-review fixture and text
cache tests still PASS; Harness reports `external_calls=0`.

### Step 8: Commit only Task 3

```bash
git add \
  backend/app/providers/visual_symbol_review.schema.json \
  backend/app/candidates/symbol_review.py \
  backend/app/providers/base.py \
  backend/app/providers/qwen_vl.py \
  backend/app/candidates/advisor.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json \
  .agent/harness/scripts/run-provider-contracts.py \
  .agent/harness/scripts/generate-receipt.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/contract/test_provider_call_records.py
git commit -m "feat: freeze visual symbol advisor contract"
```

## Task 4: Add Unified Scheduling, Local Projection And Coverage Writes

**Required test IDs:** ADV-03～ADV-09、COV-01～COV-04

**Files:**

- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/app/candidates/advisor.py`
- Modify: `backend/app/candidates/coverage.py`
- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py`
- Modify: `backend/tests/unit/candidates/test_coverage.py`
- Modify: `backend/tests/unit/candidates/test_advisor.py`

### Step 1: Write seven projection/scheduler RED tests

- [ ] ADV-03 `test_diameter_enriches_existing_candidate`:
  candidate ID and raw text remain unchanged; normalized text contains `Φ`;
  `feature_kind="unknown"`、confirmation true、visual+text source union and bbox union.
- [ ] ADV-04 `test_depth_uses_same_crop_typed_value_or_stays_ambiguous`:
  one same-crop typed value updates/projects; missing、two distinct values or conflict leaves
  original candidate unchanged and visual coverage ambiguous.
- [ ] ADV-05 `test_counterbore_maps_to_stable_composite`:
  only `{counterbore,diameter,depth}` maps; canonical `⌴`; ordered diameter/depth
  sub-requirements; no new public enum.
- [ ] ADV-06
  `test_surface_roughness_maps_to_four_field_coarse_candidate`:
  exact `raw_text/coordinates/coarse_type/requires_confirmation` field set and exactly one
  associated decimal value.
- [ ] ADV-07 `test_gdt_kinds_map_to_four_field_coarse_candidate`:
  parameterize parallelism/perpendicularity/flatness to `∥/⊥/⏥`; exact four fields; one
  tolerance token and allowlisted datum letters only.
- [ ] ADV-08 `test_reference_revision_and_no_detection_dispositions`:
  validated boxed datum becomes reference/no item; exact triangle+inner token revision becomes
  recoverable non-inspection; invalid revision and no detection remain actionable ambiguous.
- [ ] ADV-09
  `test_unified_scheduler_is_deterministic_and_blocks_visual_overflow`:
  exact visual priorities、stable first-fit、visual-first order and text remainder; 17 visual
  batches raise `symbol_route_budget_exhausted`; excess text route remains unchanged without
  provenance.

### Step 2: Write four coverage RED tests

- [ ] COV-01 `test_visual_candidate_has_one_complete_coverage_entry`:
  exactly one primary disposition、candidate ID、visual source、coordinates and text lineage.
- [ ] COV-02
  `test_visual_reference_noninspection_and_ambiguous_are_distinct`:
  disposition and confirmation flags follow the frozen table and do not overwrite each other.
- [ ] COV-03 `test_visual_missing_source_coordinates_or_conflict_blocks`:
  missing source、missing bbox、missing disposition、unexecuted visual batch and duplicate
  visual primary entries are blocking.
- [ ] COV-04 `test_visual_confirmation_cannot_be_downgraded`:
  candidate projection and Provider response cannot clear confirmation; only locally validated
  datum reference may be false.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py -q
```

Expected: the 11 new tests FAIL because schedule、mapping and final writes are absent.

### Step 3: Apply exact visual priority and unified schedule

- [ ] Reuse Task 2 observations、packer and exact constants:
  - padding
    `min(24, max(6, ceil(0.10 * max(union.width, union.height))))` PDF points;
  - max crop area `7.5%` page;
  - render scale `300/72`;
  - precomputed pixel dimensions use `ceil` and each side `<=1536`;
  - max 32 observations per batch.
- [ ] Do not reimplement stable first-fit in candidate code. Pass the exact priority-ordered
  observations to `pack_visual_batches()`; propagate `visual_crop_oversize`.
- [ ] Exact route priority:
  0 for parser-failed numeric/thread text, 1 for existing confirmation candidate, 2 for all
  other visual contexts. Tie-break is
  `(page_index,bbox.y0,bbox.x0,proposal_kind,observation_id)`.
- [ ] Let `V` be visual batch count per page:
  - `V>16` raises `symbol_route_budget_exhausted` before any call;
  - execute all `V` visual calls first;
  - select at most `16-V` existing text routes using the old stable text sort;
  - do not create an “unreviewed” visual state.
- [ ] Render each crop at exact 300 DPI after scheduling; do not downscale.
- [ ] Expose a pure
  `plan_visual_batches(pages, snapshot) -> tuple[tuple[VisualBatch, ...], ...]` function used
  by `CandidateAdvisor` and the current-source preflight. The outer tuple follows page order;
  the inner tuple follows call order. It must not construct Provider、render crop or mutate
  snapshot.

### Step 4: Implement deterministic local projections

- [ ] Add immutable decision boundary:

```python
@dataclass(frozen=True)
class VisualReviewDecision:
    observation_id: str
    disposition: Disposition
    source_location_ids: tuple[str, ...]
    coordinates: BBox
    candidate_id: str | None
    existing_candidate_index: int | None
    candidate_envelope: dict[str, Any] | None
    requires_confirmation: bool
    symbol_kinds: tuple[SymbolKind, ...]
    rejection_code: str | None
```

- [ ] Associated text reading order is
  `(page_index, angle % 360, bbox.y0, bbox.x0, observation_id)`.
- [ ] Only these kind sets are projectable:
  `{diameter}`、`{depth}`、`{diameter,depth}`、
  `{counterbore,diameter,depth}`、one roughness、one of three GD&T、one datum or one
  revision. All other sets return `visual_projection_conflict`.
- [ ] Diameter:
  run existing `parse_annotation()` against canonical `Φ` plus same-crop native text; retain
  source `raw_text`; set normalized symbol、unknown feature kind and confirmation.
- [ ] Depth:
  accept one same-crop typed value only; single-line uses parser output; multi-line reuses
  existing composite shape. Never choose nearest/max/provider value.
- [ ] Counterbore:
  require all three kinds and parser-valid diameter/depth sources; output existing composite
  with order 0 diameter and order 1 depth; prepend canonical `⌴` only to normalized text.
- [ ] Roughness:
  require exactly one distinct ASCII decimal token; emit only the frozen four fields.
- [ ] GD&T:
  require exactly one tolerance decimal; accept source-ordered single uppercase datum tokens;
  emit only the frozen four fields with canonical symbol.
- [ ] Datum:
  use the reconstructed canonical path items to require a locally validated boxed datum
  letter; disposition `reference_context`,
  confirmation false, no item.
- [ ] Revision:
  use the reconstructed canonical path items to require a three-straight-segment closed
  path、closure distance `<=0.5 pt`、bbox width/height in `[4,24] pt` and one
  `[A-Z0-9]{1,3}` token inside or within `2 pt`; disposition
  `non_inspection`, `candidate_id=None`, confirmation true, and no automatic item. A later
  explicit Quality Owner `promote_source` is a working-copy manual override, not a Provider or
  local-projection output.
- [ ] No detection:
  ambiguous、confirmation true、`visual_no_detection`.
- [ ] Candidate coordinates are the exact union of visual and all participating text bboxes;
  source IDs include both families in stable order.
- [ ] Existing candidate match preserves its candidate ID. New candidate ID is
  `stable_candidate_id("visual-candidate/1", *sorted_source_ids, projection_type)`.
- [ ] Existing typed depth mismatch、two primary candidates or source conflict leaves existing
  payload byte-equivalent and returns ambiguous.

### Step 5: Deduplicate and perform the only writes

- [ ] Convert Provider bboxes to page coordinates before dedupe.
- [ ] For same page/kind with
  `intersection_area / min(area_a,area_b) >= 0.8`, retain stable reading-order first and union
  source IDs. Provider response order must not affect output.
- [ ] `CandidateAdvisor.review()` is the only caller that:
  - replaces the initial visual coverage entry;
  - updates an existing candidate or appends one new envelope;
  - records Provider call IDs;
  - recomputes duplicate suggestions only when candidates changed.
- [ ] Per visual coverage `advisor_review` has the exact key set
  `route/schema_version/symbol_kinds/rejection_code`:
  `route` is `visual_symbol`; schema is `visual-symbol-review/1`; kinds are the sorted unique
  actual validated allowlist values (empty on no detection); rejection is null or one frozen
  local code from `visual_bbox_invalid`、`visual_source_mismatch`、
  `visual_duplicate_detection`、`visual_local_parse_failed`、
  `visual_projection_conflict` or `visual_no_detection`.

No model、prompt text、crop body、response、confidence or explanation is exposed.

### Step 6: Strengthen coverage completeness

- [ ] `check_coverage()` accepts the existing expected ID set plus a
  `required_visual_observation_ids` set.
- [ ] Mark blocking when a required visual ID:
  - occurs zero or more than once;
  - lacks source、coordinates or valid primary disposition;
  - has candidate disposition without candidate ID;
  - remains tagged internally as unscheduled;
  - belongs to a budget/crop failure.
- [ ] Continue counting ambiguous and confirmation-required entries as review required, not
  formal success blockers by themselves.

### Step 7: Verify GREEN and old Advisor regression

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_parser.py \
  backend/tests/unit/candidates/test_grouping.py \
  backend/tests/unit/candidates/test_complex_fallback.py \
  backend/tests/unit/candidates/test_duplicates.py -q
```

Expected: ADV-03～ADV-09 and COV-01～COV-04 PASS; all existing text parsing、grouping、
coarse fallback、dedupe and Advisor tests PASS.

### SR-2A: Bounded Packing Feasibility — Completed Without Certificate

本 gate 已执行完毕，只保留历史证据；不再包含可执行 production steps。

- [x] **Step 1: Run the frozen bounded no-write search**

  使用 priority-ordered input、canonical membership identity、beam width `4096`
  和每页最多 `250000` unique states。实际结果：

  ```text
  page=0 result=capacity_feasibility_unproven depth=76 expanded=248890 frontier=4096
  page=1 result=capacity_feasibility_unproven depth=72 expanded=249792 frontier=4096
  provider_construction=0 provider_calls=0
  ```

  该结果不是数学不可行证明，但没有产生可授权 packing change 的
  `V<=16/page` certificate。

- [x] **Step 2: Retire the packing-only production path**

  原 SR-2A Steps 2～6（freeze alternative packer、packing RED、production
  replacement、GREEN、code commit）均未执行且现已退休。没有 SR-2A code commit；
  `pack_visual_batches()` 继续使用 stable first-fit。

### SR-2B: Freeze The Exact Proposal Rule And Obtain Full Quality Owner Approval

SR-2B 是 docs/evidence gate。它不修改 production/test code，不构造 Provider，不改
existing sealed manifest bytes，也不把 current source、overlay 或 zoom image 加入 Git。

**Files:**

- Modify:
  `docs/superpowers/specs/2026-07-27-engineering-drawing-symbol-recognition-design.md`
- Modify: `docs/contracts/MAIN_CONTRACT_MATRIX.md`
- Modify: `docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md`
- Modify:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`

- [x] **Step 1: Freeze one candidate rule and its feature semantics**

  所有 numeric features 先以 `Decimal("0.001")` 和 `ROUND_HALF_EVEN` snap，再比较
  string-declared thresholds。feature definitions 固定为：

  - `context_area`: associated line 与当前 selected path-item bboxes union 的 PDF
    point-square area；
  - `max_item_width` / `max_item_height`: selected path-item bbox dimensions 的 maxima；
  - `mean_item_height`: selected path-item bbox height 的 arithmetic mean；
  - `fill_count`: canonical item style 中 `fill is not None` 的 item count；
  - `item_count`: 当前 selected canonical path items 的 exact count；
  - `normalized_text`: 先把 ASCII whitespace runs collapse 为单个空格、strip、
    uppercase，再计算是否 fullmatch ASCII `[A-Z0-9]{1,3}`；不删除 internal
    whitespace。feature record 只保存 boolean，不保存 token 或 raw text。

  exact branch order 和 inclusive/exclusive boundary 为：

  ```python
  def decide(features: _ProposalFeatures) -> _ProposalDecision:
      common = (
          features.mean_item_height <= Decimal("34.000")
          and features.max_item_height > Decimal("2.000")
      )
      if (
          common
          and features.fill_count <= 1
          and features.max_item_width <= Decimal("60.000")
          and features.context_area <= Decimal("6000.000")
      ):
          return _ProposalDecision(True, "geometry_compact")
      if (
          common
          and features.fill_count <= 1
          and features.max_item_width > Decimal("60.000")
          and features.item_count > 3
      ):
          return _ProposalDecision(True, "geometry_wide_multi_item")
      if (
          common
          and features.fill_count > 1
          and features.context_area > Decimal("5800.000")
          and features.max_item_height <= Decimal("42.000")
      ):
          return _ProposalDecision(True, "geometry_filled")
      if (
          features.short_token_fullmatch
          and features.context_area <= Decimal("6000.000")
      ):
          return _ProposalDecision(True, "short_token_rescue")
      return _ProposalDecision(False, "no_admission_branch")
  ```

  canonical rule JSON 必须逐 byte 等于：

  ```json
  {"branch_order":["geometry_compact","geometry_wide_multi_item","geometry_filled","short_token_rescue"],"feature_quantum":"0.001","geometry_common":{"max_item_height_min_exclusive":"2.000","mean_item_height_max":"34.000"},"geometry_compact":{"context_area_max":"6000.000","fill_count_max":1,"max_item_width_max":"60.000"},"geometry_filled":{"context_area_min_exclusive":"5800.000","fill_count_min_exclusive":1,"max_item_height_max":"42.000"},"geometry_wide_multi_item":{"fill_count_max":1,"item_count_min_exclusive":3,"max_item_width_min_exclusive":"60.000"},"proposal_rule_version":"visual-observation/2","schema_version":"visual-proposal-gate/1","short_token_rescue":{"context_area_max":"6000.000","pattern":"[A-Z0-9]{1,3}"}}
  ```

  SHA-256 必须为
  `ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7`。
  如果重新计算不一致，停止；不得通过改 expected digest 继续。

  ```bash
  PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python - <<'PY'
  import hashlib
  import json

  rule = {
      "branch_order": [
          "geometry_compact",
          "geometry_wide_multi_item",
          "geometry_filled",
          "short_token_rescue",
      ],
      "feature_quantum": "0.001",
      "geometry_common": {
          "max_item_height_min_exclusive": "2.000",
          "mean_item_height_max": "34.000",
      },
      "geometry_compact": {
          "context_area_max": "6000.000",
          "fill_count_max": 1,
          "max_item_width_max": "60.000",
      },
      "geometry_wide_multi_item": {
          "fill_count_max": 1,
          "item_count_min_exclusive": 3,
          "max_item_width_min_exclusive": "60.000",
      },
      "geometry_filled": {
          "context_area_min_exclusive": "5800.000",
          "fill_count_min_exclusive": 1,
          "max_item_height_max": "42.000",
      },
      "proposal_rule_version": "visual-observation/2",
      "schema_version": "visual-proposal-gate/1",
      "short_token_rescue": {
          "context_area_max": "6000.000",
          "pattern": "[A-Z0-9]{1,3}",
      },
  }
  encoded = json.dumps(
      rule,
      ensure_ascii=False,
      sort_keys=True,
      separators=(",", ":"),
  ).encode("utf-8")
  assert hashlib.sha256(encoded).hexdigest() == (
      "ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7"
  )
  print("proposal_rule_sha256=ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7")
  PY
  ```

- [x] **Step 2: Generate the complete 200% evidence set without repository writes**

  创建一个 `/tmp` evidence directory。no-write calibration renderer 必须直接读取
  `QI_SYMBOL_SOURCE_PDF` 和 sealed manifest artifact，不得改写 run tree；它按 Step 1
  rule 计算 provisional contexts，在 200% raster 上用绿色实线标 retained、红色虚线
  标 rejected、蓝色标 positive label、橙色标 frozen negative，并生成一份 canonical
  `proposal-gate-report.json`。report 必须为每个 72 labels 记录 page、label ID、
  positive/negative family、所有相交 context IDs、retained/rejected disposition 和
  stable reason codes；不包含 source path、raw text、token、crop bytes 或坐标以外
  private values。

  ```bash
  QI_PROPOSAL_EVIDENCE_DIR="$(mktemp -d -p /tmp qi-symbol-proposal-v2.XXXXXX)"
  test -n "$QI_PROPOSAL_EVIDENCE_DIR"
  test -n "${QI_SYMBOL_SOURCE_PDF:-}"
  test "$(sha256sum \
    .agent/harness/runs/20260727T085747865239Z-5aa3e8d3/artifacts/visual-symbol-eval.json \
    | cut -d' ' -f1)" = \
    "0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448"
  QI_PROPOSAL_STATUS_BEFORE="$(git status --porcelain=v1)"
  ```

  使用以下完整 stdin renderer；它不 import Provider module、不写 repository：

  ```bash
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  micromamba run -n qi-p0 python - \
    "$QI_SYMBOL_SOURCE_PDF" \
    ".agent/harness/runs/20260727T085747865239Z-5aa3e8d3/artifacts/visual-symbol-eval.json" \
    "$QI_PROPOSAL_EVIDENCE_DIR" <<'PY'
  from __future__ import annotations

  import hashlib
  import json
  import re
  import sys
  from collections import Counter
  from dataclasses import replace
  from decimal import Decimal, ROUND_HALF_EVEN
  from pathlib import Path

  import pymupdf
  from PIL import Image, ImageDraw, ImageFont

  from app.candidates.symbol_review import plan_visual_batches
  from app.pdf.coordinates import PageTransform
  from app.pdf.inventory import build_inventory
  from app.pdf.schemas import PageInventory
  from app.processing.automatic_result import candidate_snapshot_from_inventory
  from app.pdf.visual_observations import (
      MAX_AXIS_GAP_PT,
      MAX_CONTEXT_PAGE_AREA_RATIO,
      MAX_PATH_ITEM_EXTENT_PT,
      _area,
      _axis_gaps,
      _canonical_path_items,
      _union_bboxes,
      reconstruct_visual_geometry_contexts,
  )

  SOURCE_SHA = "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec"
  MANIFEST_SHA = "0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448"
  RULE_SHA = "ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7"
  VERSION = "visual-observation/2"
  QUANTUM = Decimal("0.001")
  source = Path(sys.argv[1])
  manifest_path = Path(sys.argv[2])
  output = Path(sys.argv[3])
  output.mkdir(parents=True, exist_ok=True)
  assert not any(output.iterdir())
  source_bytes = source.read_bytes()
  manifest_bytes = manifest_path.read_bytes()
  assert hashlib.sha256(source_bytes).hexdigest() == SOURCE_SHA
  assert hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA
  manifest = json.loads(manifest_bytes)


  def quantized(value: int | float | Decimal) -> Decimal:
      return Decimal(str(value)).quantize(
          QUANTUM,
          rounding=ROUND_HALF_EVEN,
      )


  def number_string(value: int | float | Decimal) -> str:
      value = quantized(value)
      if value == 0:
          value = abs(value)
      return format(value, "f")


  def bbox_union(
      bboxes: tuple[tuple[float, float, float, float], ...],
  ) -> tuple[float, float, float, float]:
      return (
          min(item[0] for item in bboxes),
          min(item[1] for item in bboxes),
          max(item[2] for item in bboxes),
          max(item[3] for item in bboxes),
      )


  def bbox_area(bbox: tuple[float, float, float, float]) -> Decimal:
      return quantized(
          max(0.0, bbox[2] - bbox[0])
          * max(0.0, bbox[3] - bbox[1])
      )


  def intersects(
      left: tuple[float, float, float, float],
      right: tuple[float, float, float, float],
  ) -> bool:
      return (
          max(left[0], right[0]) < min(left[2], right[2])
          and max(left[1], right[1]) < min(left[3], right[3])
      )


  def stable_digest(value: object) -> str:
      encoded = json.dumps(
          value,
          ensure_ascii=False,
          separators=(",", ":"),
      ).encode("utf-8")
      return hashlib.sha256(encoded).hexdigest()


  def observation_id(observation: object) -> str:
      seed = json.dumps(
          [
              VERSION,
              SOURCE_SHA,
              observation.page_index,
              observation.proposal_kind,
              [number_string(value) for value in observation.bbox_pdf],
              observation.geometry_sha256,
              list(observation.associated_text_observation_ids),
          ],
          separators=(",", ":"),
      ).encode("utf-8")
      return hashlib.sha256(seed).hexdigest()[:24]


  def decision(
      *,
      raw_text: str,
      line_bbox: tuple[float, float, float, float],
      path_bboxes: tuple[tuple[float, float, float, float], ...],
      canonical_items: tuple[bytes, ...],
  ) -> tuple[bool, str]:
      items = [json.loads(item) for item in canonical_items]
      widths = tuple(quantized(item[2] - item[0]) for item in path_bboxes)
      heights = tuple(quantized(item[3] - item[1]) for item in path_bboxes)
      context_area = bbox_area(bbox_union((line_bbox, *path_bboxes)))
      mean_height = quantized(
          sum(heights, start=Decimal("0")) / Decimal(len(heights))
      )
      fill_count = sum(item["style"]["fill"] is not None for item in items)
      item_count = len(items)
      normalized = re.sub(
          r"[ \t\n\r\f\v]+",
          " ",
          raw_text,
      ).strip().upper()
      short_token = re.fullmatch(r"[A-Z0-9]{1,3}", normalized) is not None
      common = (
          mean_height <= Decimal("34.000")
          and max(heights) > Decimal("2.000")
      )
      if (
          common
          and fill_count <= 1
          and max(widths) <= Decimal("60.000")
          and context_area <= Decimal("6000.000")
      ):
          return True, "geometry_compact"
      if (
          common
          and fill_count <= 1
          and max(widths) > Decimal("60.000")
          and item_count > 3
      ):
          return True, "geometry_wide_multi_item"
      if (
          common
          and fill_count > 1
          and context_area > Decimal("5800.000")
          and max(heights) <= Decimal("42.000")
      ):
          return True, "geometry_filled"
      if short_token and context_area <= Decimal("6000.000"):
          return True, "short_token_rescue"
      return False, "no_admission_branch"


  def assert_no_hidden_pre_dedup_contexts(
      pages: tuple[PageInventory, ...],
  ) -> None:
      document = pymupdf.open(source)
      try:
          for page in pages:
              source_page = document[page.page_index]
              crop = source_page.cropbox
              transform = PageTransform(
                  width=float(crop.width),
                  height=float(crop.height),
                  rotation=int(source_page.rotation),
                  scale=1.0,
              )
              path_items = _canonical_path_items(
                  source_page.get_drawings(),
                  page_index=page.page_index,
              )
              spans = [
                  item
                  for item in page.observations
                  if item.source_type == "native"
                  and item.observation_level == "span"
              ]
              raw_signatures = []
              for line in page.observations:
                  if (
                      line.source_type != "native"
                      or line.observation_level != "line"
                      or not line.raw_text.strip()
                  ):
                      continue
                  selected = []
                  for item in path_items:
                      width = item.bbox[2] - item.bbox[0]
                      height = item.bbox[3] - item.bbox[1]
                      if (
                          width > MAX_PATH_ITEM_EXTENT_PT
                          or height > MAX_PATH_ITEM_EXTENT_PT
                      ):
                          continue
                      gap_x, gap_y = _axis_gaps(line.bbox_pdf, item.bbox)
                      if (
                          gap_x <= MAX_AXIS_GAP_PT
                          and gap_y <= MAX_AXIS_GAP_PT
                      ):
                          selected.append(item)
                  if not selected:
                      continue
                  source_union = _union_bboxes(
                      (line.bbox_pdf, *(item.bbox for item in selected))
                  )
                  if (
                      _area(source_union)
                      > page.width
                      * page.height
                      * MAX_CONTEXT_PAGE_AREA_RATIO
                  ):
                      continue
                  geometry_sha256 = hashlib.sha256(
                      b"".join(item.content for item in selected)
                  ).hexdigest()
                  associated = tuple(
                      sorted(
                          (
                              line.observation_id,
                              *(
                                  span.observation_id
                                  for span in spans
                                  if span.parent_region_id
                                  == line.observation_id
                              ),
                          )
                      )
                  )
                  raw_signatures.append(
                      (
                          tuple(
                              number_string(value)
                              for value in transform.clip_bbox(source_union)
                          ),
                          geometry_sha256,
                          associated,
                      )
                  )
              persisted_signatures = [
                  (
                      tuple(
                          number_string(value)
                          for value in item.bbox_pdf
                      ),
                      item.geometry_sha256,
                      item.associated_text_observation_ids,
                  )
                  for item in page.visual_observations
              ]
              assert len(raw_signatures) == len(persisted_signatures)
              assert sorted(raw_signatures) == sorted(persisted_signatures)
      finally:
          document.close()


  def calculate() -> tuple[
      tuple[PageInventory, ...],
      list[dict[str, object]],
  ]:
      pages = build_inventory(source)
      assert_no_hidden_pre_dedup_contexts(pages)
      contexts = {
          item.observation_id: item
          for item in reconstruct_visual_geometry_contexts(source, pages)
      }
      page_rows: list[dict[str, object]] = []
      v2_pages = []
      for page in pages:
          native = {
              item.observation_id: item
              for item in page.observations
              if item.source_type == "native"
          }
          rows: list[dict[str, object]] = []
          retained = []
          for old in page.visual_observations:
              context = contexts[old.observation_id]
              lines = [
                  native[item]
                  for item in old.associated_text_observation_ids
                  if native[item].observation_level == "line"
              ]
              assert len(lines) == 1
              keep, reason = decision(
                  raw_text=lines[0].raw_text,
                  line_bbox=context.line_bbox_pdf,
                  path_bboxes=context.path_bboxes,
                  canonical_items=context.canonical_path_items,
              )
              identity = observation_id(old)
              current = replace(old, observation_id=identity)
              if keep:
                  retained.append(current)
              rows.append(
                  {
                      "bbox_pdf": list(old.bbox_pdf),
                      "context_id": identity,
                      "reason_code": reason,
                      "retained": keep,
                  }
              )
          retained.sort(
              key=lambda item: (
                  item.page_index,
                  item.bbox_pdf[1],
                  item.bbox_pdf[0],
                  item.proposal_kind,
                  item.observation_id,
              )
          )
          page_rows.append(
              {
                  "page_index": page.page_index,
                  "provisional_count": len(page.visual_observations),
                  "retained_count": len(retained),
                  "final_retained_context_ids": [
                      item.observation_id for item in retained
                  ],
                  "contexts": rows,
              }
          )
          v2_pages.append(replace(page, visual_observations=tuple(retained)))
      v2_pages_tuple = tuple(v2_pages)
      snapshot = candidate_snapshot_from_inventory(v2_pages_tuple)
      planned = plan_visual_batches(v2_pages_tuple, snapshot)
      for page_row, page, batches in zip(
          page_rows,
          v2_pages_tuple,
          planned,
          strict=True,
      ):
          identities = [
              item.observation_id for item in page.visual_observations
          ]
          memberships = [list(batch.observation_ids) for batch in batches]
          flattened = [item for batch in memberships for item in batch]
          assert len(flattened) == len(set(flattened)) == len(identities)
          assert set(flattened) == set(identities)
          for batch in batches:
              crop = batch.crop_bbox_pdf
              crop_area = (
                  max(0.0, crop[2] - crop[0])
                  * max(0.0, crop[3] - crop[1])
              )
              assert crop_area <= page.width * page.height * 0.075
              assert batch.pixel_width <= 1536
              assert batch.pixel_height <= 1536
              assert len(batch.observation_ids) <= 32
          page_row["batch_count"] = len(batches)
          page_row["observation_id_sha256"] = hashlib.sha256(
              "\n".join(sorted(identities)).encode("utf-8")
          ).hexdigest()
          page_row["batch_membership_sha256"] = stable_digest(memberships)
          page_row["reason_counts"] = dict(
              sorted(
                  Counter(
                      row["reason_code"]
                      for row in page_row["contexts"]
                  ).items()
              )
          )
      return v2_pages_tuple, page_rows


  pages, page_rows = calculate()
  repeated_pages, repeated_rows = calculate()
  assert pages == repeated_pages
  assert page_rows == repeated_rows
  assert [
      (row["provisional_count"], row["retained_count"], row["batch_count"])
      for row in page_rows
  ] == [(132, 79, 13), (203, 124, 16)]
  assert [
      row["observation_id_sha256"] for row in page_rows
  ] == [
      "15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5",
      "4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16",
  ]
  assert [
      row["batch_membership_sha256"] for row in page_rows
  ] == [
      "dc7b19187c7346e61f9344d63197f6e815ab3f85af1c6316e2e00888ed8bf0d8",
      "8a6f8ef3f3c50f85841de792f7bbc078062d4d8c1da75beaa17768b002a50ea2",
  ]

  labels_by_page = {
      page["page_index"]: page["labels"]
      for page in manifest["pages"]
  }
  labels_by_id = {
      label["label_id"]: (page_index, label)
      for page_index, labels in labels_by_page.items()
      for label in labels
  }
  revision_ids = {
      label_id
      for label_id, (_page_index, label) in labels_by_id.items()
      if label["symbol_kinds"] == ["revision_marker"]
  }
  assert revision_ids == {
      "P1-P03", "P1-P04", "P1-P05", "P2-P08", "P2-P10", "P2-P15"
  }
  n5_ids = {"FN-12", "FN-13", "FN-14", "FN-15", "FN-16"}
  assert all(
      labels_by_id[label_id][1]["symbol_kinds"] == ["frozen_negative"]
      and labels_by_id[label_id][1]["negative_family"]
      == "revision_table_or_invalid_marker"
      for label_id in n5_ids
  )
  gdt_and_datum_kinds = {
      "gdt_parallelism",
      "gdt_perpendicularity",
      "gdt_flatness",
      "datum_reference",
  }
  gdt_and_datum_ids = {
      label_id
      for label_id, (_page_index, label) in labels_by_id.items()
      if set(label["symbol_kinds"]) <= gdt_and_datum_kinds
      and set(label["symbol_kinds"])
  }
  assert gdt_and_datum_ids == {
      "P1-P01", "P1-P07", "P1-P08", "P1-P09",
      "P1-P14", "P1-P15", "P1-P22", "P1-P23",
  }
  representative_kinds = {
      "P1-P16": "diameter",
      "P1-P10": "depth",
      "P2-P02": "counterbore",
      "P1-P02": "surface_roughness",
  }
  assert all(
      kind in labels_by_id[label_id][1]["symbol_kinds"]
      for label_id, kind in representative_kinds.items()
  )
  label_rows = []
  positive_overlap_counts = []
  for page_row in page_rows:
      page_index = page_row["page_index"]
      positive_total = 0
      positive_with_overlap = 0
      for label in labels_by_page[page_index]:
          label_bbox = tuple(label["bbox_pdf"])
          matches = [
              row
              for row in page_row["contexts"]
              if intersects(tuple(row["bbox_pdf"]), label_bbox)
          ]
          is_negative = label["symbol_kinds"] == ["frozen_negative"]
          if not is_negative:
              positive_total += 1
              if any(row["retained"] for row in matches):
                  positive_with_overlap += 1
          label_rows.append(
              {
                  "expected_disposition": label["expected_disposition"],
                  "label_id": label["label_id"],
                  "negative_family": label.get("negative_family"),
                  "page_index": page_index,
                  "rejected_context_ids": [
                      row["context_id"] for row in matches
                      if not row["retained"]
                  ],
                  "retained_context_ids": [
                      row["context_id"] for row in matches
                      if row["retained"]
                  ],
                  "symbol_kinds": label["symbol_kinds"],
              }
          )
      positive_overlap_counts.append(
          (positive_with_overlap, positive_total)
      )
  assert positive_overlap_counts == [(26, 26), (30, 30)]
  assert len(label_rows) == 72
  assert sum(
      row["symbol_kinds"] != ["frozen_negative"] for row in label_rows
  ) == 56
  assert sum(
      row["symbol_kinds"] == ["frozen_negative"] for row in label_rows
  ) == 16

  document = pymupdf.open(source)
  font = ImageFont.load_default()


  def to_pixels(
      bbox: tuple[float, float, float, float],
      *,
      page_index: int,
      scale: float,
  ) -> tuple[int, int, int, int]:
      crop = document[page_index].cropbox
      return tuple(
          round(value * scale)
          for value in (
              bbox[0] - crop.x0,
              bbox[1] - crop.y0,
              bbox[2] - crop.x0,
              bbox[3] - crop.y0,
          )
      )


  def dashed_rectangle(
      draw: ImageDraw.ImageDraw,
      bbox: tuple[int, int, int, int],
      *,
      color: str,
      width: int,
  ) -> None:
      x0, y0, x1, y1 = bbox
      for start in range(x0, x1, 14):
          draw.line((start, y0, min(start + 8, x1), y0), fill=color, width=width)
          draw.line((start, y1, min(start + 8, x1), y1), fill=color, width=width)
      for start in range(y0, y1, 14):
          draw.line((x0, start, x0, min(start + 8, y1)), fill=color, width=width)
          draw.line((x1, start, x1, min(start + 8, y1)), fill=color, width=width)


  def overlay(page_index: int, scale: float) -> Image.Image:
      page = document[page_index]
      assert page.rotation == 0
      image = page.get_pixmap(
          matrix=pymupdf.Matrix(scale, scale),
          clip=page.cropbox,
          alpha=False,
      ).pil_image().convert("RGB")
      draw = ImageDraw.Draw(image)
      for row in page_rows[page_index]["contexts"]:
          bbox = to_pixels(
              tuple(row["bbox_pdf"]),
              page_index=page_index,
              scale=scale,
          )
          if row["retained"]:
              draw.rectangle(bbox, outline="#00a000", width=max(2, round(scale)))
          else:
              dashed_rectangle(
                  draw,
                  bbox,
                  color="#d00000",
                  width=max(2, round(scale)),
              )
      for label in labels_by_page[page_index]:
          bbox = to_pixels(
              tuple(label["bbox_pdf"]),
              page_index=page_index,
              scale=scale,
          )
          color = (
              "#f08000"
              if label["symbol_kinds"] == ["frozen_negative"]
              else "#0040d0"
          )
          draw.rectangle(bbox, outline=color, width=max(3, round(scale * 1.5)))
          draw.text((bbox[0] + 2, bbox[1] + 2), label["label_id"], fill=color, font=font)
      return image


  full_overlays = {
      0: overlay(0, 2.0),
      1: overlay(1, 2.0),
  }
  full_overlays[0].save(
      output / "page-1-proposal-gate-overlay-200pct.png"
  )
  full_overlays[1].save(
      output / "page-2-proposal-gate-overlay-200pct.png"
  )
  zoom_overlays = {
      0: overlay(0, 4.0),
      1: overlay(1, 4.0),
  }


  def label_card(label_id: str) -> Image.Image:
      page_index, label = labels_by_id[label_id]
      full = zoom_overlays[page_index]
      bbox = tuple(label["bbox_pdf"])
      margin = 14.0
      crop = document[page_index].cropbox
      expanded = (
          max(crop.x0, bbox[0] - margin),
          max(crop.y0, bbox[1] - margin),
          min(crop.x1, bbox[2] + margin),
          min(crop.y1, bbox[3] + margin),
      )
      pixels = to_pixels(expanded, page_index=page_index, scale=4.0)
      content = full.crop(pixels)
      card = Image.new("RGB", (content.width, content.height + 24), "white")
      ImageDraw.Draw(card).text((4, 4), label_id, fill="black", font=font)
      card.paste(content, (0, 24))
      return card


  def contact_sheet(label_ids: tuple[str, ...], filename: str) -> None:
      cards = [label_card(label_id) for label_id in label_ids]
      columns = min(3, len(cards))
      rows = (len(cards) + columns - 1) // columns
      cell_width = max(card.width for card in cards)
      cell_height = max(card.height for card in cards)
      sheet = Image.new(
          "RGB",
          (columns * cell_width, rows * cell_height),
          "white",
      )
      for index, card in enumerate(cards):
          x = (index % columns) * cell_width
          y = (index // columns) * cell_height
          sheet.paste(card, (x, y))
      sheet.save(output / filename)


  contact_sheet(
      ("P1-P03", "P1-P04", "P1-P05", "P2-P08", "P2-P10", "P2-P15"),
      "zoom-revision-positive.png",
  )
  contact_sheet(
      ("FN-12", "FN-13", "FN-14", "FN-15", "FN-16"),
      "zoom-n5-negative.png",
  )
  contact_sheet(
      ("P1-P01", "P1-P07", "P1-P08", "P1-P09", "P1-P15", "P1-P22", "P1-P23", "P1-P14"),
      "zoom-gdt-and-boxed-datum.png",
  )
  contact_sheet(
      ("P1-P16", "P1-P10", "P2-P02", "P1-P02"),
      "zoom-core-symbol-representatives.png",
  )

  dense_candidates = []
  for page_index, labels in labels_by_page.items():
      centers = [
          (
              (label["bbox_pdf"][0] + label["bbox_pdf"][2]) / 2,
              (label["bbox_pdf"][1] + label["bbox_pdf"][3]) / 2,
          )
          for label in labels
      ]
      page = document[page_index]
      x_starts = sorted(
          {
              max(page.cropbox.x0, min(x, page.cropbox.x1 - 200.0))
              for center_x, _center_y in centers
              for x in (center_x, center_x - 200.0)
          }
      )
      y_starts = sorted(
          {
              max(page.cropbox.y0, min(y, page.cropbox.y1 - 200.0))
              for _center_x, center_y in centers
              for y in (center_y, center_y - 200.0)
          }
      )
      for y0 in y_starts:
          for x0 in x_starts:
              count = sum(
                  x0 <= center_x <= x0 + 200.0
                  and y0 <= center_y <= y0 + 200.0
                  for center_x, center_y in centers
              )
              dense_candidates.append((-count, page_index, y0, x0))
  _negative_count, dense_page, dense_y0, dense_x0 = min(dense_candidates)
  dense_full = zoom_overlays[dense_page]
  dense_bbox = (dense_x0, dense_y0, dense_x0 + 200.0, dense_y0 + 200.0)
  dense_full.crop(
      to_pixels(dense_bbox, page_index=dense_page, scale=4.0)
  ).save(output / "zoom-densest-region.png")
  document.close()

  artifact_names = (
      "page-1-proposal-gate-overlay-200pct.png",
      "page-2-proposal-gate-overlay-200pct.png",
      "zoom-revision-positive.png",
      "zoom-n5-negative.png",
      "zoom-gdt-and-boxed-datum.png",
      "zoom-core-symbol-representatives.png",
      "zoom-densest-region.png",
  )
  report = {
      "artifact_sha256": {
          name: hashlib.sha256((output / name).read_bytes()).hexdigest()
          for name in artifact_names
      },
      "labels": label_rows,
      "manifest_sha256": MANIFEST_SHA,
      "pages": page_rows,
      "proposal_rule_sha256": RULE_SHA,
      "proposal_rule_version": VERSION,
      "provider_calls": 0,
      "provider_construction": 0,
      "reviewed_frozen_negative_region_count": 16,
      "reviewed_positive_label_count": 56,
      "schema_version": "visual-proposal-gate-report/1",
  }
  (output / "proposal-gate-report.json").write_text(
      json.dumps(
          report,
          ensure_ascii=False,
          sort_keys=True,
          separators=(",", ":"),
      )
      + "\n",
      encoding="utf-8",
  )
  print(
      "page=0 provisional=132 retained=79 batches=13; "
      "page=1 provisional=203 retained=124 batches=16; "
      "positive_overlap=26/26,30/30; "
      "provider_construction=0 provider_calls=0"
  )
  PY
  test "$QI_PROPOSAL_STATUS_BEFORE" = "$(git status --porcelain=v1)"
  QI_PROPOSAL_REPORT_SHA256="$(sha256sum \
    "$QI_PROPOSAL_EVIDENCE_DIR/proposal-gate-report.json" | cut -d' ' -f1)"
  test "${#QI_PROPOSAL_REPORT_SHA256}" -eq 64
  printf 'proposal_gate_report_sha256=%s\n' \
    "$QI_PROPOSAL_REPORT_SHA256"
  ```

  exact output filenames：

  ```text
  page-1-proposal-gate-overlay-200pct.png
  page-2-proposal-gate-overlay-200pct.png
  zoom-revision-positive.png
  zoom-n5-negative.png
  zoom-gdt-and-boxed-datum.png
  zoom-core-symbol-representatives.png
  zoom-densest-region.png
  proposal-gate-report.json
  ```

  zoom membership 固定为：

  - revision positive:
    `P1-P03,P1-P04,P1-P05,P2-P08,P2-P10,P2-P15`；
  - N5 no-token triangles: `FN-12,FN-13,FN-14,FN-15,FN-16`；
  - all GD&T + boxed datum:
    `P1-P01,P1-P07,P1-P08,P1-P09,P1-P15,P1-P22,P1-P23,P1-P14`；
  - representatives:
    diameter `P1-P16`、depth `P1-P10`、counterbore `P2-P02`、
    surface roughness `P1-P02`；
  - densest region: 对两页的全部 `200pt × 200pt` sliding-window candidates 计算
    label-center count，输出唯一 global maximum；tie-break
    `(page_index,y0,x0)`。

  mechanical expected values：

  ```text
  manifest_sha256=0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448
  rule_sha256=ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7
  page=0 provisional=132 retained=79 batches=13 positive_labels_with_overlap=26/26
  page=1 provisional=203 retained=124 batches=16 positive_labels_with_overlap=30/30
  reviewed_positive_labels=56 reviewed_frozen_negative_regions=16
  provider_construction=0 provider_calls=0 repository_write_count=0
  ```

  `positive_labels_with_overlap` 只作 calibration sanity check。它不能替代 Quality
  Owner 的视觉判断；任一 frozen negative disposition、context boundary 或 dense
  area 仍必须逐图核对。renderer 必须重复运行两次并证明：

  ```text
  page=0 observation_id_sha256=15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5
  page=0 batch_membership_sha256=dc7b19187c7346e61f9344d63197f6e815ab3f85af1c6316e2e00888ed8bf0d8
  page=1 observation_id_sha256=4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16
  page=1 batch_membership_sha256=8a6f8ef3f3c50f85841de792f7bbc078062d4d8c1da75beaa17768b002a50ea2
  exact_once=true limits=true repeatable=true
  ```

  任一 count、digest、limit、label coverage 或 Provider/write count 不一致即停止。

- [x] **Step 3: Obtain an explicit Quality Owner verdict**

  向 Quality Owner 提供 Step 2 的两页完整 overlay、五张 zoom 和 report。不得只提供
  缩略图或 overlap count。Quality Owner 必须逐项确认全部 56 positives、16 frozen
  negatives、六个 token revision markers、五个 N5 triangles、全部 GD&T/boxed
  datum、四类 representatives 和 densest region。

  approval evidence 必须是 canonical JSON，字段和值完整：

  ```json
  {
    "annotation_status": "approved",
    "manifest_sha256": "0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448",
    "overlay_scale_percent": 200,
    "proposal_rule_sha256": "ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7",
    "proposal_rule_version": "visual-observation/2",
    "reviewed_frozen_negative_region_count": 16,
    "reviewed_positive_label_count": 56,
    "schema_version": "visual-proposal-gate-verdict/1",
    "unlabeled_target_count": 0
  }
  ```

  Quality Owner 收到全部 artifacts、report 和
  `FN-03/FN-04/FN-08/FN-11` retained-overlap 风险提示后明确回复“可以”。实际
  compact、sorted-key canonical approval evidence 为：

  ```json
  {"annotation_status":"approved","manifest_sha256":"0de369a4dee5c119197d973efa0368458f6f27651ef82fd5b9951a6d61cb6448","overlay_scale_percent":200,"overlay_sha256":{"page-1-proposal-gate-overlay-200pct.png":"da25c8e0f04c4468deb094bb6be9f8565fd9d855ad3b40c44bad8cb40da15202","page-2-proposal-gate-overlay-200pct.png":"8335c1e22ba02474ef9ddf7fdd111dd86cbd9ebc056cf8ce429155e62fda0ec7"},"proposal_gate_report_sha256":"13f73e1c790b277c6d317c016e1df5e41c52eb62a07d336b69b5f9d6df7152d9","proposal_rule_sha256":"ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7","proposal_rule_version":"visual-observation/2","reviewed_frozen_negative_region_count":16,"reviewed_positive_label_count":56,"schema_version":"visual-proposal-gate-verdict/1","unlabeled_target_count":0,"zoom_sha256":{"zoom-core-symbol-representatives.png":"a9773c5cab2caa24b83160dd0ce44a2cf51a2af037145affb62c9807f6fb3219","zoom-densest-region.png":"bcae9e7852bd78cee21ae5b5d5e66aaf482b375118593c8b21dde21f22dc2d0d","zoom-gdt-and-boxed-datum.png":"a0060d71ebbdd8ce2f6b594bdb4d08ab4c228cfa7a5490811cc83ce3fd55fdaa","zoom-n5-negative.png":"2a61789008b0b731378dcbf63f7c697df7710ae9a687c0a94e43381d8938ad4c","zoom-revision-positive.png":"941d8db1b45047993c1aa8bf436749f2897c6ccb37011133cd21511026293a9e"}}
  ```

  canonical verdict SHA-256 为
  `9b7a6aa061315f7e8501c348e57b21219b597a2374fb8ffca976bedc978f50ef`。
  `unlabeled_target_count=0` 从同一 sealed run 的
  `visual-symbol-annotation-verdict.json` 机械读取；该 input verdict 绑定相同
  manifest SHA 和 `overlay_scale_percent=200`。

  同一 object 还必须包含 `overlay_sha256` 的两个 exact file→digest entries 和
  `zoom_sha256` 的五个 exact file→digest entries，以及
  `proposal_gate_report_sha256`，其值必须 exact 等于 Step 2 输出的
  `QI_PROPOSAL_REPORT_SHA256`。所有 digest 从实际 bytes 计算，不能在 plan 中预填或
  猜测。Quality Owner approval 后，SR-2B Step 4 必须把 report SHA、两页 final
  retained-ID digests、batch digests 和全部 artifact digests 写入 approved design/
  plans；SR-2C 以这些 committed digests 为 stable handle，不依赖 `/tmp` path。
  report 与 images 仍不得加入 Git。若 verdict 不是 exact approval，停止并回到
  design；不得修改 production/test code、stable contract 或 Provider policy。

- [x] **Step 4: Bind the approved rule to design and stable contract, then commit docs only**

  只有 Step 3 approved 后才执行。将 Step 1 exact predicate/feature definitions、
  Step 2 actual counts、report/artifact digests 和 Step 3 verdict/digests 写回
  accepted design；本 plan 与 current plan 记录 Quality Owner evidence 已关闭。将
  `docs/contracts/MAIN_CONTRACT_MATRIX.md` 的 `PDF-007` stable requirement 改为：

  ```text
  Page inventory 保存区域、coverage、来源冲突和异常；当前固定范围内与 native text
  相邻的 visual observation 还必须保存稳定 ID、PDF bbox、geometry hash 和 text
  relations；proposal admission 必须由 Page inventory Owner 使用显式 versioned
  deterministic rule，禁止 source/page/label/Provider 特判，rule 变化必须重新完成
  Quality Owner 200% overlay 验证；低置信度区域不得直接导致已 retained 工程内容被排除。
  ```

  `PDF-007` 仍通过 existing `P0-REC-009` related-business binding 覆盖；不新增 logical
  ID，required total 保持 `32`。运行：

  ```bash
  PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python \
    .agent/harness/scripts/check-contracts.py
  git diff --check -- \
    docs/contracts/MAIN_CONTRACT_MATRIX.md \
    docs/superpowers/specs/2026-07-27-engineering-drawing-symbol-recognition-design.md \
    docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md \
    docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
  git add \
    docs/contracts/MAIN_CONTRACT_MATRIX.md \
    docs/superpowers/specs/2026-07-27-engineering-drawing-symbol-recognition-design.md \
    docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md \
    docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
  git diff --cached --check
  test "$(git diff --cached --name-only | sort)" = \
    "$(printf '%s\n' \
      docs/contracts/MAIN_CONTRACT_MATRIX.md \
      docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md \
      docs/superpowers/plans/2026-07-27-engineering-drawing-symbol-recognition.md \
      docs/superpowers/specs/2026-07-27-engineering-drawing-symbol-recognition-design.md \
      | sort)"
  git commit -m "docs: freeze approved visual proposal gate"
  ```

  Expected: contract checks PASS；cached paths exact equal the four docs；SR-4 七文件仍
  unstaged；sealed run bytes unchanged；Provider calls=`0`。

  Actual closure binds page 0
  `132 provisional / 79 retained / 13 batches` and page 1
  `203 provisional / 124 retained / 16 batches`；final observation-ID digests are
  `15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5` /
  `4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16`，
  batch-membership digests are
  `dc7b19187c7346e61f9344d63197f6e815ab3f85af1c6316e2e00888ed8bf0d8` /
  `8a6f8ef3f3c50f85841de792f7bbc078062d4d8c1da75beaa17768b002a50ea2`。
  两次 runs 的八个 artifacts 逐 byte 相同，Provider construction/calls=`0`；
  images/report 继续只存在 `/tmp`，未加入 Git。

### SR-2C: Implement The Approved Proposal Owner With TDD

只有 SR-2B docs commit 存在且 Quality Owner verdict 为 exact approval 才能开始。
本 task 扩展 existing PDF-01/PDF-02/PDF-03 semantics 和 supporting cache regression，
不新增 logical test ID，32-count 不变。

**Proposal-only commit files:**

- Modify: `backend/app/pdf/visual_observations.py`
- Modify: `backend/tests/unit/pdf/test_visual_observations.py`

**Existing SR-4 working-diff files touched but not staged in SR-2C:**

- Modify: `backend/app/candidates/symbol_review.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py`

- [ ] **Step 1: Write PDF RED tests before production edits**

  在 `backend/tests/unit/pdf/test_visual_observations.py` 增加或扩展以下 exact test
  functions：

  - `test_hybrid_proposal_gate_admits_each_geometry_branch`
  - `test_hybrid_proposal_gate_rescues_short_technical_token`
  - `test_hybrid_proposal_gate_rejects_noise_and_snaps_boundaries`
  - `test_visual_observation_v2_reconstructs_or_blocks`

  添加 `Decimal`、`PROPOSAL_RULE_VERSION`、`_ProposalFeatures`、
  `_proposal_decision` 和 `_short_token_fullmatch` imports，并使用以下完整 test
  content：

  ```python
  from decimal import Decimal

  from app.pdf.visual_observations import (
      PROPOSAL_RULE_VERSION,
      _ProposalFeatures,
      _proposal_decision,
      _short_token_fullmatch,
  )


  def _gate_features(
      **changes: object,
  ) -> _ProposalFeatures:
      features = _ProposalFeatures(
          context_area=Decimal("5000.000"),
          max_item_width=Decimal("50.000"),
          max_item_height=Decimal("10.000"),
          mean_item_height=Decimal("10.000"),
          fill_count=0,
          item_count=1,
          short_token_fullmatch=False,
      )
      return replace(features, **changes)


  @pytest.mark.parametrize(
      ("features", "reason_code"),
      (
          (_gate_features(), "geometry_compact"),
          (
              _gate_features(
                  context_area=Decimal("7000.000"),
                  max_item_width=Decimal("60.001"),
                  item_count=4,
              ),
              "geometry_wide_multi_item",
          ),
          (
              _gate_features(
                  context_area=Decimal("5800.001"),
                  max_item_width=Decimal("70.000"),
                  max_item_height=Decimal("42.000"),
                  fill_count=2,
              ),
              "geometry_filled",
          ),
      ),
  )
  def test_hybrid_proposal_gate_admits_each_geometry_branch(
      features: _ProposalFeatures,
      reason_code: str,
  ) -> None:
      decision = _proposal_decision(features)
      assert decision.retained is True
      assert decision.reason_code == reason_code


  def test_hybrid_proposal_gate_rescues_short_technical_token() -> None:
      assert _short_token_fullmatch("a1") is True
      assert _short_token_fullmatch(" A1 ") is True
      for rejected in ("A 1", "A-1", "ABCD", "Φ"):
          assert _short_token_fullmatch(rejected) is False

      decision = _proposal_decision(
          _gate_features(
              context_area=Decimal("6000.000"),
              max_item_height=Decimal("2.000"),
              mean_item_height=Decimal("35.000"),
              short_token_fullmatch=True,
          )
      )
      assert decision.retained is True
      assert decision.reason_code == "short_token_rescue"

      transform = PageTransform(
          width=200.0,
          height=200.0,
          rotation=0,
          scale=1.0,
      )
      rescued_line = TextObservation(
          observation_id="short-token-line",
          source_type="native",
          observation_level="line",
          raw_text="a1",
          normalized_text="a1",
          page_index=0,
          bbox_pdf=(20.0, 20.0, 30.0, 30.0),
          bbox_normalized=(0.1, 0.1, 0.15, 0.15),
          direction=(1.0, 0.0),
          direction_angle_degrees=0.0,
          confidence=None,
      )
      drawing = {
          "items": [
              (
                  "l",
                  pymupdf.Point(18.0, 18.0),
                  pymupdf.Point(20.0, 20.0),
              )
          ],
          "width": 1.0,
          "dashes": "[] 0",
          "lineCap": 0,
          "lineJoin": 0,
          "color": (0.0,),
          "fill": None,
          "closePath": False,
      }
      rescued, contexts = build_page_visual_observations(
          page_index=0,
          page_width=200.0,
          page_height=200.0,
          source_sha256="a" * 64,
          native_observations=(rescued_line,),
          drawings=(drawing,),
          transform=transform,
      )
      rejected, rejected_contexts = build_page_visual_observations(
          page_index=0,
          page_width=200.0,
          page_height=200.0,
          source_sha256="a" * 64,
          native_observations=(
              replace(
                  rescued_line,
                  raw_text="ordinary",
                  normalized_text="ordinary",
              ),
          ),
          drawings=(drawing,),
          transform=transform,
      )
      assert len(rescued) == len(contexts) == 1
      assert rejected == ()
      assert rejected_contexts == ()


  @pytest.mark.parametrize(
      ("features", "expected_retained", "expected_reason"),
      (
          (
              _gate_features(mean_item_height=Decimal("34.000")),
              True,
              "geometry_compact",
          ),
          (
              _gate_features(mean_item_height=Decimal("34.001")),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(max_item_height=Decimal("2.000")),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(max_item_height=Decimal("2.001")),
              True,
              "geometry_compact",
          ),
          (
              _gate_features(max_item_width=Decimal("60.000")),
              True,
              "geometry_compact",
          ),
          (
              _gate_features(context_area=Decimal("6000.000")),
              True,
              "geometry_compact",
          ),
          (
              _gate_features(context_area=Decimal("6000.001")),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(
                  context_area=Decimal("7000.000"),
                  max_item_width=Decimal("60.000"),
                  item_count=4,
              ),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(
                  context_area=Decimal("7000.000"),
                  max_item_width=Decimal("60.001"),
                  item_count=3,
              ),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(
                  context_area=Decimal("5800.001"),
                  max_item_width=Decimal("70.000"),
                  fill_count=1,
              ),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(
                  context_area=Decimal("5800.000"),
                  max_item_width=Decimal("70.000"),
                  fill_count=2,
              ),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(
                  context_area=Decimal("5800.001"),
                  max_item_width=Decimal("70.000"),
                  max_item_height=Decimal("42.000"),
                  fill_count=2,
              ),
              True,
              "geometry_filled",
          ),
          (
              _gate_features(
                  context_area=Decimal("5800.001"),
                  max_item_width=Decimal("70.000"),
                  max_item_height=Decimal("42.001"),
                  fill_count=2,
              ),
              False,
              "no_admission_branch",
          ),
          (
              _gate_features(
                  context_area=Decimal("6000.001"),
                  max_item_height=Decimal("2.000"),
                  mean_item_height=Decimal("35.000"),
                  short_token_fullmatch=True,
              ),
              False,
              "no_admission_branch",
          ),
      ),
  )
  def test_hybrid_proposal_gate_rejects_noise_and_snaps_boundaries(
      features: _ProposalFeatures,
      expected_retained: bool,
      expected_reason: str,
  ) -> None:
      decision = _proposal_decision(features)
      assert decision.retained is expected_retained
      assert decision.reason_code == expected_reason


  def test_visual_observation_v2_reconstructs_or_blocks(
      tmp_path: Path,
  ) -> None:
      pdf_path, _manifest = build_symbol_fixture(tmp_path)
      pages = build_inventory(pdf_path)
      assert PROPOSAL_RULE_VERSION == "visual-observation/2"
      assert [len(page.visual_observations) for page in pages] == [10, 9]
      first = reconstruct_visual_geometry_contexts(pdf_path, pages)
      second = reconstruct_visual_geometry_contexts(pdf_path, pages)
      assert first == second
      assert len(first) == 19

      original = pages[0].visual_observations
      tampered_sets = (
          original[1:],
          (
              *original,
              replace(original[-1], observation_id="f" * 24),
          ),
          tuple(reversed(original)),
          (
              replace(original[0], observation_id="0" * 24),
              *original[1:],
          ),
          (
              replace(original[0], geometry_sha256="0" * 64),
              *original[1:],
          ),
      )
      for tampered in tampered_sets:
          tampered_page = replace(
              pages[0],
              visual_observations=tampered,
          )
          with pytest.raises(VisualObservationBlockingError) as error:
              reconstruct_visual_geometry_contexts(
                  pdf_path,
                  (tampered_page, pages[1]),
              )
          assert error.value.code == "visual_reconstruction_mismatch"
  ```

  v2 test 必须证明 repeated IDs/order exact、same geometry/different associated text 仍不
  合并、missing/extra/order/ID/geometry tamper 继续
  `visual_reconstruction_mismatch`。既有 synthetic fixtures 必须按 approved rule
  明确构造 admission/noise facts，不得通过放宽 assertion 保留 v1 behavior。只读
  fixture preflight 已证明 approved rule 保留 existing `[10,9]` observations，因此
  不修改 `backend/tests/helpers/symbol_fixture.py` 或扩大 SR-2C file scope。

  ```bash
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  micromamba run -n qi-p0 pytest \
    backend/tests/unit/pdf/test_visual_observations.py \
    -p no:cacheprovider -q
  ```

  Expected RED: new gate/version assertions FAIL because production 仍是
  `visual-observation/1` 且没有 admission gate；existing unrelated assertions 仍 PASS。

- [ ] **Step 2: Write cache single-source RED inside the existing SR-4 diff**

  在 `backend/tests/unit/candidates/test_symbol_advisor.py` 增加
  `test_visual_cache_identity_uses_proposal_owner_version`。它必须证明 cache identity
  从 `app.pdf.visual_observations.PROPOSAL_RULE_VERSION` 读取
  `visual-observation/2`，v1 bytes 不能命中 v2 cache；并用 source inspection 或 module
  identity 证明 `symbol_review.py` 不再拥有第二个
  `VISUAL_PROPOSAL_VERSION` string assignment。

  添加 `import app.candidates.symbol_review as symbol_review`、
  `visual_cache_identity`、`visual_cache_key` 和 `PROPOSAL_RULE_VERSION` imports，
  再添加完整 test：

  ```python
  import app.candidates.symbol_review as symbol_review
  from app.candidates.symbol_review import (
      visual_cache_identity,
      visual_cache_key,
  )
  from app.pdf.visual_observations import PROPOSAL_RULE_VERSION


  def test_visual_cache_identity_uses_proposal_owner_version() -> None:
      arguments = {
          "source_sha256": "a" * 64,
          "visual_observation_ids": ("visual-001",),
          "crop_bbox_pdf": (1.0, 2.0, 10.0, 20.0),
          "crop_sha256": "b" * 64,
          "model": "qwen-vl-fixture",
      }
      current = visual_cache_identity(**arguments)
      legacy = visual_cache_identity(
          **arguments,
          proposal_version="visual-observation/1",
      )

      assert PROPOSAL_RULE_VERSION == "visual-observation/2"
      assert current["proposal_version"] == PROPOSAL_RULE_VERSION
      assert legacy["proposal_version"] == "visual-observation/1"
      assert visual_cache_key(**arguments) != visual_cache_key(
          **arguments,
          proposal_version="visual-observation/1",
      )
      assert not hasattr(symbol_review, "VISUAL_PROPOSAL_VERSION")
  ```

  ```bash
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  micromamba run -n qi-p0 pytest \
    backend/tests/unit/candidates/test_symbol_advisor.py \
    -p no:cacheprovider -q
  ```

  Expected RED: local duplicate v1 constant 仍存在，cache identity 未跟随 proposal
  Owner。该 test file 已属于 SR-4 dirty ownership，RED 后仍不得 stage/commit。

- [ ] **Step 3: Implement only the approved gate in the proposal Owner**

  在 `backend/app/pdf/visual_observations.py` 的 typing import 加入 `Literal`，将
  version/digest 和 internal types 定义为：

  ```python
  PROPOSAL_RULE_VERSION = "visual-observation/2"
  PROPOSAL_RULE_CANONICAL_JSON = (
      b'{"branch_order":["geometry_compact","geometry_wide_multi_item",'
      b'"geometry_filled","short_token_rescue"],"feature_quantum":"0.001",'
      b'"geometry_common":'
      b'{"max_item_height_min_exclusive":"2.000","mean_item_height_max":"34.000"},'
      b'"geometry_compact":{"context_area_max":"6000.000","fill_count_max":1,'
      b'"max_item_width_max":"60.000"},"geometry_filled":'
      b'{"context_area_min_exclusive":"5800.000",'
      b'"fill_count_min_exclusive":1,"max_item_height_max":"42.000"},'
      b'"geometry_wide_multi_item":{"fill_count_max":1,'
      b'"item_count_min_exclusive":3,"max_item_width_min_exclusive":"60.000"},'
      b'"proposal_rule_version":"visual-observation/2",'
      b'"schema_version":"visual-proposal-gate/1","short_token_rescue":'
      b'{"context_area_max":"6000.000","pattern":"[A-Z0-9]{1,3}"}}'
  )
  PROPOSAL_RULE_SHA256 = hashlib.sha256(
      PROPOSAL_RULE_CANONICAL_JSON
  ).hexdigest()
  if PROPOSAL_RULE_SHA256 != (
      "ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7"
  ):
      raise RuntimeError("visual proposal rule digest mismatch")

  @dataclass(frozen=True)
  class _ProposalFeatures:
      context_area: Decimal
      max_item_width: Decimal
      max_item_height: Decimal
      mean_item_height: Decimal
      fill_count: int
      item_count: int
      short_token_fullmatch: bool

  @dataclass(frozen=True)
  class _ProposalDecision:
      retained: bool
      reason_code: Literal[
          "geometry_compact",
          "geometry_wide_multi_item",
          "geometry_filled",
          "short_token_rescue",
          "no_admission_branch",
      ]


  @dataclass(frozen=True)
  class _CanonicalPathItem:
      bbox: BBox
      content: bytes
      has_fill: bool
  ```

  用一个 constructor 保持 canonical bytes 与 fill feature 同源，并让现有
  `_point_item()` 和 `re` branch 都调用它：

  ```python
  def _canonical_path_item(
      *,
      bbox: BBox,
      payload: dict[str, Any],
      style: dict[str, Any],
  ) -> _CanonicalPathItem:
      return _CanonicalPathItem(
          bbox=bbox,
          content=json.dumps(
              payload,
              sort_keys=True,
              separators=(",", ":"),
          ).encode("utf-8"),
          has_fill=style["fill"] is not None,
      )
  ```

  `_point_item()` 的 return 改为：

  ```python
  return _canonical_path_item(
      bbox=_union_bboxes(point_bboxes),
      payload=payload,
      style=style,
  )
  ```

  `_canonical_item()` 的 `opcode == "re"` branch return 改为：

  ```python
  return _canonical_path_item(
      bbox=bbox,
      payload=payload,
      style=style,
  )
  ```

  在 `_area()` 后加入完整 pure feature/decision implementation：

  ```python
  _SHORT_TOKEN = re.compile(r"[A-Z0-9]{1,3}")


  def _measure(value: int | float | Decimal, *, page_index: int) -> Decimal:
      return Decimal(_number_string(value, page_index=page_index))


  def _short_token_fullmatch(raw_text: str) -> bool:
      normalized = _ASCII_WHITESPACE.sub(" ", raw_text).strip().upper()
      return _SHORT_TOKEN.fullmatch(normalized) is not None


  def _proposal_features(
      *,
      raw_text: str,
      selected: Sequence[_CanonicalPathItem],
      source_union: BBox,
      page_index: int,
  ) -> _ProposalFeatures:
      widths = tuple(
          _measure(item.bbox[2] - item.bbox[0], page_index=page_index)
          for item in selected
      )
      heights = tuple(
          _measure(item.bbox[3] - item.bbox[1], page_index=page_index)
          for item in selected
      )
      mean_height = _measure(
          sum(heights, start=Decimal("0")) / Decimal(len(heights)),
          page_index=page_index,
      )
      return _ProposalFeatures(
          context_area=_measure(_area(source_union), page_index=page_index),
          max_item_width=max(widths),
          max_item_height=max(heights),
          mean_item_height=mean_height,
          fill_count=sum(item.has_fill for item in selected),
          item_count=len(selected),
          short_token_fullmatch=_short_token_fullmatch(raw_text),
      )


  def _proposal_decision(
      features: _ProposalFeatures,
  ) -> _ProposalDecision:
      common = (
          features.mean_item_height <= Decimal("34.000")
          and features.max_item_height > Decimal("2.000")
      )
      if (
          common
          and features.fill_count <= 1
          and features.max_item_width <= Decimal("60.000")
          and features.context_area <= Decimal("6000.000")
      ):
          return _ProposalDecision(True, "geometry_compact")
      if (
          common
          and features.fill_count <= 1
          and features.max_item_width > Decimal("60.000")
          and features.item_count > 3
      ):
          return _ProposalDecision(True, "geometry_wide_multi_item")
      if (
          common
          and features.fill_count > 1
          and features.context_area > Decimal("5800.000")
          and features.max_item_height <= Decimal("42.000")
      ):
          return _ProposalDecision(True, "geometry_filled")
      if (
          features.short_token_fullmatch
          and features.context_area <= Decimal("6000.000")
      ):
          return _ProposalDecision(True, "short_token_rescue")
      return _ProposalDecision(False, "no_admission_branch")
  ```

  在 `build_page_visual_observations()` 现有 `>1%` area guard 后、`bbox_pdf` /
  observation-ID creation 前插入：

  ```python
  decision = _proposal_decision(
      _proposal_features(
          raw_text=line.raw_text,
          selected=selected,
          source_union=source_union,
          page_index=page_index,
      )
  )
  if not decision.retained:
      continue
  ```

  其余 builder code 不改：retained bbox、geometry SHA、associated text IDs、
  proposal kind、dedup 和 final sort 保持；v2 ID seed 只通过单一
  `PROPOSAL_RULE_VERSION` 变化。rejection reason 不写 API、DB、Provider prompt、
  coverage 或 persisted inventory。不修改 `pack_visual_batches()`、crop thresholds、
  priority 或 Provider code。

- [ ] **Step 4: Remove the duplicate cache version without widening SR-2C commit**

  在现有 dirty `backend/app/candidates/symbol_review.py` 中删除本地
  `VISUAL_PROPOSAL_VERSION`，改为：

  ```python
  from app.pdf.visual_observations import (
      PROPOSAL_RULE_VERSION,
      VisualBatch,
      VisualGeometryContext,
      VisualObservationBlockingError,
      pack_visual_batches,
  )
  ```

  删除 module-level `VISUAL_PROPOSAL_VERSION` assignment，并把
  `visual_cache_identity()` 的 argument default 精确改为：

  ```python
  proposal_version: str = PROPOSAL_RULE_VERSION,
  ```

  cache identity/default 只引用 `PROPOSAL_RULE_VERSION`。对应 cache RED 在
  `test_symbol_advisor.py` 转 GREEN，但这两个文件仍与其余 SR-4 changes 一起保留
  unstaged，直到 Task 4 Step 9。

  在既有 `backend/tests/contract/test_qwen_symbol_provider.py` 中把退休 symbol 的
  import 改为直接从 proposal Owner import `PROPOSAL_RULE_VERSION`；cache baseline
  使用该 current v2，proposal-version variation 改为 legacy
  `"visual-observation/1"`。不得恢复 alias 或建立第二个 version literal Owner。

- [ ] **Step 5: Verify focused GREEN and existing PDF/Advisor behavior**

  ```bash
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  micromamba run -n qi-p0 pytest \
    backend/tests/unit/pdf/test_visual_observations.py \
    backend/tests/unit/pdf/test_inventory.py \
    backend/tests/unit/pdf/test_coordinates.py \
    backend/tests/unit/pdf/test_runtime_ocr.py \
    backend/tests/unit/candidates/test_symbol_advisor.py \
    backend/tests/unit/candidates/test_coverage.py \
    backend/tests/unit/candidates/test_advisor.py \
    backend/tests/contract/test_qwen_symbol_provider.py \
    -p no:cacheprovider -q
  ```

  Expected: PDF-01～PDF-05、ADV-03～ADV-09、COV-01～COV-04 and supporting gate/cache
  tests plus PROV-01/PROV-02 PASS；v1 cache bytes miss safely；fixture-only Provider
  contracts 保持 `external_calls=0`。

- [ ] **Step 6: Reproduce the exact current-source result with production code**

  不得在 v2 production 上重跑 pre-production renderer；该 renderer 的输入 inventory
  故意是 v1 provisional set。Quality Owner verdict 和 SR-2B docs commit 已绑定
  report SHA、exact `132/203` provisional contexts、source/rule digest 以及两页
  final retained-ID digests。production Owner 直接重算并比较这些 committed
  retained-ID digests；在相同 source/provisional/rule identity 下，这也机械固定
  rejected complement，不依赖临时 report path。

  ```bash
  test -n "${QI_SYMBOL_SOURCE_PDF:-}"
  QI_PROPOSAL_STATUS_BEFORE="$(git status --porcelain=v1)"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  micromamba run -n qi-p0 python - "$QI_SYMBOL_SOURCE_PDF" <<'PY'
  import hashlib
  import sys
  from pathlib import Path

  from app.pdf.inventory import build_inventory
  from app.pdf.visual_observations import (
      PROPOSAL_RULE_SHA256,
      PROPOSAL_RULE_VERSION,
      reconstruct_visual_geometry_contexts,
  )

  source = Path(sys.argv[1])
  assert hashlib.sha256(source.read_bytes()).hexdigest() == (
      "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec"
  )
  assert PROPOSAL_RULE_VERSION == "visual-observation/2"
  assert PROPOSAL_RULE_SHA256 == (
      "ef23fce2a747ef89b28c7bee0a5504a4135c32d42799b0f493170e8796fcffd7"
  )

  def observation_id_digest(values: list[str]) -> str:
      return hashlib.sha256(
          "\n".join(sorted(values)).encode("utf-8")
      ).hexdigest()

  pages = build_inventory(source)
  contexts = reconstruct_visual_geometry_contexts(source, pages)
  assert len(contexts) == 203
  assert [len(page.visual_observations) for page in pages] == [79, 124]
  actual_digests = [
      observation_id_digest(
          [
          item.observation_id for item in page.visual_observations
          ]
      )
      for page in pages
  ]
  assert actual_digests == [
      "15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5",
      "4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16",
  ]
  print(
      "approved_retained_digest_match=true observations=79,124 "
      "reconstruction=203 rule_version=visual-observation/2"
  )
  PY
  test "$QI_PROPOSAL_STATUS_BEFORE" = "$(git status --porcelain=v1)"
  ```

  然后运行下述 Task 4 Step 8 exact batch preflight。observation-ID set digest
  使用 lexicographically sorted IDs、单个 `\n` 连接且无尾随换行的 bytes；
  batch-membership digest 使用 stable ordered nested list 的 compact canonical
  JSON。两组 commands 合起来必须 exact：

  ```text
  page=0 observations=79 batches=13
  observation_id_sha256=15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5
  batch_membership_sha256=dc7b19187c7346e61f9344d63197f6e815ab3f85af1c6316e2e00888ed8bf0d8
  page=1 observations=124 batches=16
  observation_id_sha256=4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16
  batch_membership_sha256=8a6f8ef3f3c50f85841de792f7bbc078062d4d8c1da75beaa17768b002a50ea2
  exact_once=true limits=true repeatable=true
  provider_construction=0 provider_calls=0 repository_write_count=0
  ```

  任一 report hash、retained/rejected complement、positive/frozen-negative
  disposition、reconstruction、batch digest 或 `V>16` mismatch 即回到 design，
  不得 update golden。

- [ ] **Step 7: Obtain independent read-only review**

  reviewer 必须检查：single proposal Owner、rule/threshold exactness、no second
  filter、v2 ID/cache single source、reconstruction blocking、tests 是否命中真实
  failure、SR-4 dirty ownership 和 Provider=`0` boundary。verdict 必须为
  `accept`、`accept with concerns` 或 `reject`；blocking issue 修复后重新 review。

- [ ] **Step 8: Commit only the proposal Owner and directly coupled tests**

  ```bash
  git add \
    backend/app/pdf/visual_observations.py \
    backend/tests/unit/pdf/test_visual_observations.py \
    backend/tests/contract/test_qwen_symbol_provider.py
  git diff --cached --check
  test "$(git diff --cached --name-only | sort)" = \
    "$(printf '%s\n' \
      backend/app/pdf/visual_observations.py \
      backend/tests/contract/test_qwen_symbol_provider.py \
      backend/tests/unit/pdf/test_visual_observations.py | sort)"
  git commit -m "fix: gate visual observation proposals"
  ```

  Expected: proposal-only commit contains exactly three files。现有七个 SR-4
  files—including v2 cache single-source delta—继续 unstaged。完成后才进入下述
  Task 4 Step 8。

### Step 8: Prove the current two-page source fits the hard budget

This is a deterministic no-write/no-Provider preflight. It uses the exact source whose bytes
were sealed in Task 1 and prints only counts and digests, never its path、text、coordinates or
content.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
micromamba run -n qi-p0 python - "$QI_SYMBOL_SOURCE_PDF" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

from app.candidates.symbol_review import plan_visual_batches
from app.pdf.inventory import build_inventory
from app.processing.automatic_result import candidate_snapshot_from_inventory

source = Path(sys.argv[1])
assert hashlib.sha256(source.read_bytes()).hexdigest() == (
    "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec"
)
pages = build_inventory(source)
snapshot = candidate_snapshot_from_inventory(pages)
planned = plan_visual_batches(pages, snapshot)

def digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def observation_id_digest(values: list[str]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(values)).encode("utf-8")
    ).hexdigest()

observation_counts = tuple(len(page.visual_observations) for page in pages)
batch_counts = tuple(len(page_batches) for page_batches in planned)
id_digests = tuple(
    observation_id_digest(
        [item.observation_id for item in page.visual_observations]
    )
    for page in pages
)
batch_digests = tuple(
    digest([list(batch.observation_ids) for batch in page_batches])
    for page_batches in planned
)
assert observation_counts == (79, 124), observation_counts
assert batch_counts == (13, 16), batch_counts
assert id_digests == (
    "15f476cac29683c425b85b541ad528b38f1983fb5673871466626038ef1852f5",
    "4f082c0ce52fb649cd9c84c16b685ced29133dc12c3b37392df63767043a4e16",
), id_digests
assert batch_digests == (
    "dc7b19187c7346e61f9344d63197f6e815ab3f85af1c6316e2e00888ed8bf0d8",
    "8a6f8ef3f3c50f85841de792f7bbc078062d4d8c1da75beaa17768b002a50ea2",
), batch_digests
for page, page_batches in zip(pages, planned, strict=True):
    expected = [item.observation_id for item in page.visual_observations]
    actual = [
        observation_id
        for batch in page_batches
        for observation_id in batch.observation_ids
    ]
    assert len(actual) == len(set(actual)) == len(expected)
    assert set(actual) == set(expected)
    for batch in page_batches:
        crop = batch.crop_bbox_pdf
        crop_area = max(0.0, crop[2] - crop[0]) * max(0.0, crop[3] - crop[1])
        assert crop_area <= page.width * page.height * 0.075
        assert batch.pixel_width <= 1536 and batch.pixel_height <= 1536
        assert len(batch.observation_ids) <= 32
print(
    "observations=79,124 batches=13,16 "
    "exact_once=true limits=true provider_construction=0 provider_calls=0"
)
PY
```

Expected: the exact final line above。连续执行两次，counts/digests 必须完全一致。如果
任一 assertion 失败，停止并回到 SR-2C/design；不得调 rule、crop limits 或 expected
digests 来让 source 通过。

### Step 9: Commit only Task 4

```bash
git add \
  backend/app/candidates/symbol_review.py \
  backend/app/candidates/advisor.py \
  backend/app/candidates/coverage.py \
  backend/app/processing/automatic_result.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/unit/candidates/test_advisor.py
git diff --cached --check
test "$(git diff --cached --name-only | sort)" = \
  "$(printf '%s\n' \
    backend/app/candidates/advisor.py \
    backend/app/candidates/coverage.py \
    backend/app/candidates/symbol_review.py \
    backend/app/processing/automatic_result.py \
    backend/tests/unit/candidates/test_advisor.py \
    backend/tests/unit/candidates/test_coverage.py \
    backend/tests/unit/candidates/test_symbol_advisor.py | sort)"
git commit -m "feat: project visual symbols through candidate owner"
```

Expected: Task 4 commit contains exactly the seven long-lived SR-4 files，包括
`symbol_review.py` 的 v2 cache single-source delta；SR-2C proposal files 已在前一
commit，不得重复 stage。

## Task 5: Wire The Canonical Runtime, Failure Veto And Idempotent Result

**Required test IDs:** INT-01～INT-06

**Files:**

- Create: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/app/processing/runtime_recognition.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/processing/tasks.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_processing_entry_task.py`
- Modify: `backend/tests/integration/test_task_idempotency.py`
- Modify: `backend/tests/integration/test_result_layers.py`
- Modify: `backend/tests/integration/test_review_working_copy.py`
- Modify: `backend/tests/integration/test_review_operations.py`
- Modify: `backend/tests/integration/test_error_records.py`

### Step 1: Write all six logical integration RED tests plus one supporting regression

- [ ] INT-01
  `test_vector_fixture_builds_visual_candidate_and_working_copy`:
  sanitized PDF → native/visual inventory → injected fake Provider → candidate/coverage →
  persisted AutomaticResult → one working copy; assert source IDs and no fixture manifest input.
- [ ] INT-02
  `test_diameter_depth_and_counterbore_group_as_one_annotation`:
  each combination produces one primary candidate and one item, no duplicate visual/text item.
- [ ] INT-03
  `test_roughness_gdt_and_datum_project_without_schema_expansion`:
  roughness/GD&T use existing coarse shape; datum is coverage reference and absent from items;
  `CandidateType`/`CoarseType` sets remain unchanged.
- [ ] INT-04
  `test_visual_provider_failure_prevents_ready_for_edit`:
  parameterize unavailable、invalid root schema、invalid cache/audit、crop oversize、budget
  overflow and coverage conflict; no AutomaticResult/working copy; project failed with exact
  sanitized code/stage/category.
- [ ] INT-05
  `test_visual_no_detection_remains_actionable_source_review`:
  no-detection entry has page/bbox/source and can execute existing `promote_source` or
  `ignore_source`; it never silently enters active items before the command.
- [ ] INT-06 `test_visual_processing_replay_is_idempotent`:
  second canonical logical task call returns the first result ref; raw/working counts remain
  one; Provider call count increment is zero; a late failure cannot overwrite the winner.
- [ ] Supporting regression
  `test_revision_marker_stays_noninspection_until_explicit_promote_source`:
  assert the automatic result and initial working copy contain
  `non_inspection + candidate_id=null + requires_confirmation=true` coverage and no item for a
  qualifying revision marker; no Provider、validator、automatic processing or frontend-derived
  path promotes it. On independent working-copy branches, an explicit Quality Owner
  `promote_source` with all existing required manual fields creates exactly one manual item,
  while explicit `ignore_source` resolves confirmation with no item. This supporting regression
  is not a new logical ID; the Required Test Matrix remains exactly 32.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_symbol_recognition_pipeline.py -q
```

Expected: FAIL because canonical runtime、failure mapping and result bootstrap are not wired to
the visual decisions.

### Step 2: Wire one canonical processing path

- [ ] `RuntimeRecognition.build_inventory()` continues to call the single native inventory
  builder, which now includes visual observations. OCR behavior remains unchanged.
- [ ] `RuntimeRecognition.build_candidate_snapshot()`:
  1. builds the deterministic text+initial-visual snapshot once;
  2. attaches OCR request IDs;
  3. calls the existing `CandidateAdvisor.review()` once with source PDF and all pages;
  4. returns the Advisor result to the existing `InventoryPipeline`.
- [ ] `tasks.py::inventory_project` keeps one `CandidateAdvisor` injection and the existing
  `VISION_PROVIDER_FACTORY`; do not construct a visual-only Advisor or task.
- [ ] A fake Provider in tests implements both `review_candidate()` and `review_symbols()` but
  is injected through the same production seam.

### Step 3: Map failures without leaking details

- [ ] Root Provider/schema/cache failures remain:

```text
code=vision_provider_call_failed
stage=candidate_advisor
cause_category=transient_provider_failure
```

- [ ] `symbol_route_budget_exhausted` and `visual_crop_oversize` use:

```text
code=symbol_route_budget_exhausted or visual_crop_oversize
stage=candidate_advisor
cause_category=processing_defect
```

- [ ] Coverage incompleteness remains:

```text
code=coverage_blocking
stage=coverage
cause_category=processing_defect
```

- [ ] Error messages must be constant sanitized summaries. No source path、crop、SDK body、
  Provider content、credential or associated customer text.
- [ ] All failures happen before `build_automatic_result()` commits
  `processing → ready_for_edit`.

### Step 4: Preserve immutable raw/working layers

- [ ] `ReviewService.create_from_raw()` continues to create items only from candidate envelopes.
- [ ] It keeps visual/text `source_location_ids` and `normalized_text` in item payload.
- [ ] `_review_coverage()` strips `advisor_review` before exposing the mutable working copy,
  just as it does for text Advisor provenance, but retains the local Owner-committed
  `symbol_kinds` needed to distinguish a qualifying revision marker from no-detection; it must
  not derive that discriminator in the frontend.
- [ ] Both source-review states remain present and distinct with source、bbox、disposition and
  confirmation:
  - no-detection is `ambiguous + visual_no_detection`;
  - qualifying revision marker is
    `non_inspection + candidate_id=null + requires_confirmation=true`.
  Existing source commands may act only after an explicit Quality Owner command.
- [ ] Existing raw result immutability tests add an assertion that creating/reviewing a new
  symbol result does not mutate an old text-only result.

### Step 5: Preserve logical task winner semantics

- [ ] Cache and Provider work only occur inside the first active logical task execution.
- [ ] On replay after success, return the already persisted `job.result_ref` before rebuilding
  inventory or constructing Provider.
- [ ] If another worker commits success first, losing failure cannot alter result、project or
  job state.
- [ ] Use the existing `LogicalJob` and idempotency implementation; do not add an app-level
  symbol idempotency key.

### Step 6: Verify GREEN and runtime regressions

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_error_records.py \
  backend/tests/integration/test_processing_state.py -q
```

Expected: INT-01～INT-06 and
`test_revision_marker_stays_noninspection_until_explicit_promote_source` PASS; existing
canonical task、result-layer、review and error tests PASS; all fixture tests report no external
call. The supporting regression does not change the 32 logical-ID count.

### Step 7: Commit only Task 5

```bash
git add \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/app/processing/runtime_recognition.py \
  backend/app/processing/pipeline.py \
  backend/app/processing/tasks.py \
  backend/app/review/service.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_task_idempotency.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_review_operations.py \
  backend/tests/integration/test_error_records.py
git commit -m "feat: persist visual symbol recognition results"
```

## Task 6: Project Visual Sources And Separate Raw From Recognized Text

**Required test IDs:** FE-01～FE-03

**Files:**

- Modify: `backend/app/projects/router.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/review/ReviewPanel.tsx`
- Modify: `frontend/src/components/review/ReviewPanel.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.tsx`
- Modify: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/styles/workbench.css`

### Step 1: Write backend projection RED

- [ ] Extend
  `test_project_workbench_projects_source_only_coverage_for_review` with one visual
  observation and assert:

```json
{
  "id": "visual-observation-id",
  "item_ids": [],
  "page_index": 0,
  "bbox_pdf": [60.0, 70.0, 100.0, 90.0],
  "raw_text": "图形符号待确认",
  "source_type": "visual"
}
```

- [ ] Existing native source response adds `source_type="text"` without changing its ID、
  page、bbox or raw text.
- [ ] `advisor_review`、geometry hash、associated text IDs and Provider response are absent
  from the API.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py \
  -k "source_only_coverage" -q
```

Expected: FAIL because `_project_pages()` only indexes `observations` and source responses have
no source type.

### Step 2: Write all three frontend RED tests

- [ ] FE-01 in `ReviewPanel.test.tsx`:
  `shows raw_and_normalized_symbol_text_separately`. Render `raw_text="10"` and
  `normalized_text="Φ10"`; assert editable “图纸原文” remains `10`, read-only “识别结果”
  is `Φ10`, and no normalized field appears when both strings are equal.
- [ ] FE-02 in `InspectionItemTable.test.tsx`:
  `renders_coarse_symbol_and_confirmation`. Parameterize roughness and three GD&T coarse
  items; assert Owner-provided coarse type/canonical symbol and “需确认” are visible; unknown
  coarse type remains the existing safe empty-state label.
- [ ] FE-03 in `PdfWorkspace.test.tsx`:
  `locates_and_actions_visual_source`. Parameterize an
  `ambiguous + visual_no_detection` source and a qualifying
  `revision_marker + non_inspection` source. Selection moves to the persisted page/bbox; the UI
  respectively shows “图形符号待确认” and “修订标记（非检验）待确认”. Through
  `InspectionWorkbench.test.tsx`, only explicit Quality Owner actions emit existing
  promote/ignore commands, and no Provider response or frontend-inferred promotion is rendered.

```bash
npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
```

Expected: the three focused cases FAIL because TS types and UI distinctions are absent.

### Step 3: Add one source lookup, not one endpoint

- [ ] `_project_pages()` indexes both:
  - existing `page["observations"]` as source type `text`;
  - additive `page.get("visual_observations", [])` as source type `visual`.
- [ ] Visual source lookup uses its persisted page/bbox and constant display text
  `图形符号待确认`; it does not expose geometry/proposal/provider fields.
- [ ] `_project_items()` continues to project only coverage entries requiring confirmation and
  without candidate IDs as pending sources. Reference contexts do not enter the list; revision
  non-inspection with confirmation and ambiguous no-detection do, retaining the backend
  Owner-committed disposition and `symbol_kinds` so they remain distinguishable.
- [ ] Do not add a second workbench endpoint or database query.

### Step 4: Extend frontend API types additively

- [ ] Add `normalized_text?: string` to the existing `ReviewItem` type and
  `source_type: "text" | "visual"` to the existing `ProjectWorkbenchSource` type.

- [ ] Extend `OverlayBox` and `PendingSourceReview` with optional/stable source type propagation.
  Do not make old fixture objects invalid where the existing tests intentionally construct
  partial overlays.

### Step 5: Render Owner output without frontend inference

- [ ] `ReviewPanel`:
  - keep `raw_text` as the only editable source field;
  - if trimmed `normalized_text` is non-blank and differs, render a read-only “识别结果” row;
  - do not include normalized text in edit command fields;
  - do not derive a symbol from CSS or string matching.
- [ ] `InspectionItemTable`:
  - ambiguous no-detection label is “图形符号待确认”; qualifying revision-marker label is
    “修订标记（非检验）待确认”;
  - the promote editor still requires explicit Quality Owner action、non-blank operator text
    and existing `CandidateType`;
  - reuse existing `promote_source` and `ignore_source`; a revision-marker promotion is a human
    override from initial non-inspection, while ignore confirms non-inspection with no item;
  - frontend copy、symbol matching、CSS or model output cannot invoke or simulate either command;
  - coarse visual items display only fields already committed by backend Owner.
- [ ] `PdfWorkspace`:
  - continue using persisted bbox and page transform;
  - visual source selection/zoom follows the existing source path;
  - do not add image upload or model call.
- [ ] Add only necessary Chinese copy and scoped styles consistent with the approved information
  hierarchy; do not restore duplicate item headings.

### Step 6: Verify GREEN, full frontend and build

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_project_workbench_api.py -q
npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/workbench/ProjectWorkbenchApp.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
npm --prefix frontend run build
```

Expected: FE-01～FE-03 PASS; workbench source-only、dirty-draft、selection and build gates
PASS.

### Step 7: Run integrated browser QA

- [ ] Start the approved local/QA runtime without changing committed runtime config.
- [ ] Use Chrome DevTools MCP to verify one fixture project at desktop viewport:
  - raw and recognized values are simultaneously visible;
  - ambiguous no-detection and qualifying revision-marker noninspection are visibly distinct,
    and both source selections locate the correct page/bbox;
  - promote/ignore remain explicit Quality Owner actions guarded by unsaved-draft behavior;
  - no Provider JSON appears in DOM、network response or console;
  - no new console error or failed request.
- [ ] Save only sanitized textual observations; do not save current-source screenshot into Git.

### Step 8: Commit only Task 6

```bash
git add \
  backend/app/projects/router.py \
  backend/tests/integration/test_project_workbench_api.py \
  frontend/src/api/types.ts \
  frontend/src/components/review/ReviewPanel.tsx \
  frontend/src/components/review/ReviewPanel.test.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionWorkbench.test.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx \
  frontend/src/components/pdf/PdfWorkspace.tsx \
  frontend/src/components/pdf/PdfWorkspace.test.tsx \
  frontend/src/copy/zhCN.ts \
  frontend/src/styles/workbench.css
git commit -m "feat: review visual symbol sources"
```

## Task 7: Close Sanitized E2E And Full Regression

**Required test IDs:** E2E-01～E2E-02

**Files:**

- Create: `backend/tests/e2e/test_symbol_recognition.py`
- Modify only when an additive assertion is necessary:
  `backend/tests/e2e/test_offline_automatic_result.py`
- Modify only when an additive assertion is necessary:
  `backend/tests/e2e/test_offline_vertical.py`
- Modify only when an additive assertion is necessary:
  `backend/tests/e2e/test_no_silent_success.py`

### Step 1: Write both E2E tests through canonical seams

- [ ] E2E-01 `test_symbol_fixture_positive_flow`:
  create the sanitized PDF, upload/process through the canonical task with a frozen fake
  Provider, then compare generated candidates/coverage/working copy against the independent
  fixture manifest. Assert exact-one match for all 19 positive regions and
  `external_calls=0`.
- [ ] E2E-02 `test_symbol_fixture_negative_regions_do_not_create_items`:
  assert all 12 frozen negative regions have zero overlapping candidate/reference/item and do
  not disappear from the fixture comparison.
- [ ] The fake Provider receives only crop bytes and prompt, derives its response from the
  synthetic observation IDs included in the prompt, and never reads the expected manifest.
- [ ] Do not reuse the live current-source labels or real Provider response.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/e2e/test_symbol_recognition.py -q
```

Expected before final E2E assertions are wired: FAIL on exact positive/negative comparison.
Expected after implementation: two tests PASS and report zero external calls.

### Step 2: Run the complete focused 32-check gate

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py -q
npm --prefix frontend test -- --run \
  src/components/review/ReviewPanel.test.tsx \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/InspectionWorkbench.test.tsx \
  src/components/pdf/PdfWorkspace.test.tsx
```

Expected: all 32 required IDs are collected and PASS. Verify collection explicitly:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_visual_observations.py \
  backend/tests/unit/candidates/test_symbol_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_symbol_provider.py \
  backend/tests/integration/test_symbol_recognition_pipeline.py \
  backend/tests/e2e/test_symbol_recognition.py \
  --collect-only -q
```

Expected: each exact backend test name in the Required Test Matrix appears; frontend test names
are verified by Vitest output. A parameterized test may emit multiple cases but does not reduce
the 32 logical IDs.

### Step 3: Run explicit existing-behavior regression

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_parser.py \
  backend/tests/unit/candidates/test_grouping.py \
  backend/tests/unit/candidates/test_complex_fallback.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/contract/test_provider_call_records.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_result_layers.py \
  backend/tests/e2e/test_offline_automatic_result.py \
  backend/tests/e2e/test_offline_vertical.py \
  backend/tests/e2e/test_no_silent_success.py -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all existing suites PASS without skip/count relaxation; text-only candidate payload、
coverage、working-copy creation and export-facing result layers remain compatible.

### Step 4: Run contract, policy and privacy checks

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/run-provider-contracts.py
git diff --check
rg -n \
  "(Authorization:|BEGIN (RSA|OPENSSH) PRIVATE KEY|credential=|password=|api[_-]?key=|data:image/.+base64,|/home/|/Users/)" \
  backend/app/pdf/visual_observations.py \
  backend/app/candidates/symbol_review.py \
  backend/app/candidates/advisor.py \
  backend/app/providers/visual_symbol_review.schema.json \
  backend/tests/helpers/symbol_fixture.py \
  .agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v1.json
```

Expected: contract check and provider fixture runner exit 0; diff check is clean; `rg` returns no
match. Do not scan or print `.env` values.

### Step 5: Use the repository smoke-test skill

- [ ] Invoke `auto-feature-smoke-test` after all implementation commits, following its current
  `SKILL.md`.
- [ ] Record its commands and results in the current-plan amendment. A skipped runtime check
  must name a real blocker and cannot be treated as a pass.

### Step 6: Independent read-only review

- [ ] Use one `reviewer` agent after the code diff is complete. Its prompt must state:
  role `reviewer`; exact file/diff scope; read-only authority; no file modifications; no nested
  delegation; stop on higher-rule conflict; expected verdict/blockers/concerns/evidence/files;
  commands run or why unavailable.
- [ ] Reviewer must specifically inspect:
  - single Owner and old silent-truncation retirement;
  - no false symbol semantics or hole inference;
  - exact source/bbox/coverage lineage;
  - visual budget blocking;
  - Provider/schema/cache redaction;
  - old text route and idempotency regression;
  - test independence from expected manifests.
- [ ] Parent verifies every blocking claim directly and applies only minimal fixes with focused
  reruns. Core-behavior fixes require a second read-only review of the final diff.

### Step 7: Commit only Task 7

```bash
git add \
  backend/tests/e2e/test_symbol_recognition.py
git commit -m "test: cover symbol recognition end to end"
```

If additive assertions were required in the three existing E2E files, stage those exact files
in the same command. Do not stage any generated local run、cache、screenshot or test-results
directory.

## Task 8: Execute Sealed Current-PDF Acceptance And Hand Back To D7-T3

**Required test ID:** LIVE-01

**Files:**

- Create: `.agent/harness/scripts/symbol_eval.py`
- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Modify: `.agent/harness/scripts/live_evidence_policy.py`
- Modify: `.agent/harness/schemas/live-run-evidence.schema.json`
- Modify: `.agent/harness/policy/p0-acceptance-policy.yaml`
- Modify:
  `backend/tests/contract/harness/test_symbol_eval_contract.py`
- Modify:
  `backend/tests/contract/harness/test_live_run_contract.py`
- Modify:
  `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
- Modify: `.agent/harness/contracts/p0-contracts.json`（generated）
- Modify: `.agent/harness/contracts/global-contract-bindings.json`（generated）
- Modify:
  `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`

### Step 1: Write LIVE-01 and run RED against synthetic result objects

- [ ] Add `test_sealed_current_pdf_symbol_manifest` to
  `test_symbol_eval_contract.py`. It uses a temporary sealed artifact and synthetic actual
  result objects to prove:
  - positive candidate exact-one matching;
  - reference/non-inspection matching against the pre-manual-command Owner result;
  - a qualifying revision marker is exactly
    `non_inspection + candidate_id=null + requires_confirmation=true`;
  - degree zero and degree greater than one fail;
  - detected kind set must equal label kind set;
  - projection must equal expected projection;
  - overlap is
    `intersection_area / min(actual_visual_area, label_area) >= 0.5`;
  - any candidate overlapping `frozen_negative` at the threshold fails;
  - candidate without visual source is excluded from visual eval;
  - visual candidate without one positive edge fails.
- [ ] Add a live-run contract test proving `--symbol-eval-run` requires one literal sealed
  staging run and the full run binds both manifest and annotation-verdict bytes.

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  -k "symbol" -q
```

Expected: FAIL because the evaluator、live phase and artifact loader are absent.

### Step 2: Implement a post-result-only evaluator

- [ ] `symbol_eval.py` accepts only parsed manifest、inventory visual observations、
  raw candidates and raw coverage. It must never participate in proposal、prompt、Provider or
  candidate construction.
- [ ] Candidate visual bbox is the union of all visual IDs in `source_location_ids`.
- [ ] Detected kinds are the sorted unique union of coverage
  `advisor_review.symbol_kinds` for those visual IDs.
- [ ] Build graph edges only when page、exact kinds、exact projection and overlap threshold all
  match.
- [ ] Enforce exact degree one on both candidate-label sides, exact single match for
  reference/non-inspection labels, and zero negative overlaps.
- [ ] Return a sanitized report containing counts、label IDs、candidate IDs、dispositions、
  overlap ratios and pass/fail reasons. Do not include source text、PDF bytes、host path、
  Provider response or crop.

### Step 3: Bind the evaluator to the existing full live run

- [ ] Add CLI `--symbol-eval-run` to `run-p0.py`; it must accept the same literal run-ID regex
  used by current-four registration, reject aliases/symlinks/writable sealed paths, validate
  both schemas and recompute input identity.
- [ ] Copy exact artifact bytes into the full live run before any Provider call.
- [ ] Add one selector
  `phase://live/symbol-recognition?input_set=current-four`.
- [ ] Execute it for the first checkpoint source hash only, after automatic candidate/coverage
  persistence and before any `promote_source` / `ignore_source` command or quality-owner
  item-set acceptance.
- [ ] It loads the new project’s immutable raw result and inventory, calls only
  `symbol_eval.py`, stores a sanitized report, and blocks the run on any mismatch.
- [ ] Add live evidence fields:
  manifest SHA、verdict SHA、label/per-family counts、visual call counts per page、match counts、
  negative false-positive count and report ref.
- [ ] Enforce actual visual calls `<=16/page`; text+visual total also `<=16/page`.
- [ ] Do not reuse an old project result. The current source must be uploaded as a new project
  within the bound live run.
- [ ] Add `symbol_eval.py`、its schema/policy dependencies and selector identity to the existing
  controlled-code inventory in `generate-receipt.py`; the live receipt must bind their exact
  bytes.

### Step 4: Re-run Harness GREEN before spending Provider calls

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_contract_architecture.py \
  backend/tests/contract/harness/test_live_run_contract.py \
  backend/tests/contract/harness/test_receipt_policy.py -q
```

Expected: LIVE-01 synthetic contract cases PASS; artifact/schema/code/input identities are
closed; no network call has occurred.

### Step 5: Commit the live gate before any Provider call

```bash
git add \
  .agent/harness/scripts/symbol_eval.py \
  .agent/harness/scripts/run-p0.py \
  .agent/harness/scripts/generate-receipt.py \
  .agent/harness/scripts/live_evidence_policy.py \
  .agent/harness/schemas/live-run-evidence.schema.json \
  .agent/harness/policy/p0-acceptance-policy.yaml \
  backend/tests/contract/harness/test_symbol_eval_contract.py \
  backend/tests/contract/harness/test_live_run_contract.py
git diff --cached --check
git commit -m "test: bind live symbol recognition gate"
git show --format=%H --no-patch HEAD
```

Expected: the gate code、tests、schema and policy share one committed code identity. Record that
literal commit SHA for the run; do not execute the live selector against uncommitted gate code.

### Step 6: Materialize and execute the literal live command

- [ ] Read the exact current-four registration run ID and the exact symbol-eval staging run ID
  recorded in the activated current-plan amendment.
- [ ] Invoke `run-p0.py live --scope full-p0 --input-set current-four` with both IDs written
  literally in the shell command. Do not use `latest`、glob、command substitution or an
  environment-variable alias for either ID.
- [ ] The plan intentionally does not invent future run IDs. If either literal is absent, stop;
  this is a real evidence blocker, not a value to guess.
- [ ] Required result for the first two-page source:
  - source SHA exact match;
  - every positive label has exactly one edge;
  - every participating visual candidate has exactly one positive edge;
  - reference and pre-manual revision-marker non-inspection labels match exactly;
  - frozen-negative false positives zero;
  - no positive `visual_no_detection`;
  - no projection conflict、coverage blocking、crop oversize or budget exhaustion;
  - visual and total Vision calls at most 16 per page;
  - project uses a new raw result; old result bytes/count remain unchanged.
- [ ] Continue the existing current-four live sequence only if the first checkpoint and the
  symbol selector pass. Do not use success on the remaining three PDFs to mask a first-source
  failure.

### Step 7: Perform real browser evidence

- [ ] Through the existing authenticated/approved project workbench, use Chrome DevTools MCP
  to verify on the new project:
  - at least one diameter/depth/counterbore item shows source raw text and recognized canonical
    symbol separately;
  - one roughness/GD&T coarse item shows confirmation state;
  - one visual source can be located to the correct page/bbox and acted with the existing
    review command;
  - no Provider response is present;
  - refresh preserves result identity and does not repeat Provider calls.
- [ ] Bind sanitized browser evidence to the same run/project/result identity. Do not commit
  current-source screenshot.

### Step 8: Final receipt update without prematurely completing D7-T3

- [ ] When all checks pass:
  - change amended `P0-REC-005/009/010` statuses from `pending` to `passed`;
  - regenerate both JSON mirrors;
  - record Task SR-1～SR-8 commits、32-check result、existing regression result、live run ID、
    receipt ID and reviewer verdict in the current-plan amendment;
  - state that D7-T2 symbol closure is complete and D7-T3 may now resume.
- [ ] Do **not** mark D7-T3 complete in this task; D7-T3 still owns final receipt enforcement、
  rollback proof and overall independent review.

```bash
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python \
  .agent/harness/scripts/check-contracts.py
git diff --check -- \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
git add \
  docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md \
  .agent/harness/contracts/p0-contracts.json \
  .agent/harness/contracts/global-contract-bindings.json \
  docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
git diff --cached --check
git commit -m "docs: record live symbol recognition evidence"
```

## Rollback Plan

Rollback is an explicit current-plan action, not silent fallback:

1. Stop new uploads and do not delete sealed runs、cache or Provider call records.
2. Mark the symbol receipt failed/stale and record the blocking code in the current plan.
3. Revert Task 8 → Task 5 commits in reverse order with `git revert` and each exact commit hash
   recorded during execution.
   Do not reset、force-push or overwrite unrelated dirty files.
4. Revert SR-4 Task 4 commit first，then SR-2C proposal-only commit，then SR-2B
   exact-rule/Quality Owner docs commit。之后才可依次 revert `6920958` hybrid design、
   `8e0c625` capacity amendment、`90bfb43` SR-3 和 `bb035bc` SR-2。SR-2A 没有
   code commit，不得虚构一个 hash。
5. Revert Task 1 contract/Harness amendment only after the code commits are reverted; keep the
   immutable historical evidence directories untouched.
6. Revert Task 0 activation last, adding a note that D7-T3 remains blocked by the original
   missing-symbol defect.
7. Run the preserved text-path baseline:

```bash
micromamba run -n qi-p0 pytest \
  backend/tests/unit/pdf/test_inventory.py \
  backend/tests/unit/pdf/test_runtime_ocr.py \
  backend/tests/unit/candidates/test_parser.py \
  backend/tests/unit/candidates/test_grouping.py \
  backend/tests/unit/candidates/test_complex_fallback.py \
  backend/tests/unit/candidates/test_advisor.py \
  backend/tests/unit/candidates/test_coverage.py \
  backend/tests/contract/test_qwen_vl_provider.py \
  backend/tests/integration/test_processing_entry_task.py \
  backend/tests/integration/test_review_working_copy.py \
  backend/tests/integration/test_result_layers.py -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: old text-only baseline PASS; symbol capability is absent and D7-T3 remains explicitly
blocked. Rollback does not convert the original missing-symbol behavior into accepted success.

## Completion Checklist

- [x] User approved this subordinate implementation proposal.
- [x] Task 0 activated exactly one current plan at commit `994cbe4`; Option A clarification is
  active and Task 0 must not be repeated.
- [x] Stable contract Owners were amended before production GREEN.
- [x] Quality Owner sealed exact live labels and 200% overlay verdict before production GREEN.
- [x] Staging mechanically proved all nine positive families and all nine distinct
  `negative_family` values; `negative_family_count=9` was derived from the manifest rather than
  entered by a human.
- [x] SR-2A bounded packing search ended
  `capacity_feasibility_unproven` without a production/code commit or Provider call.
- [x] User accepted hybrid proposal-gate design commit `6920958`.
- [x] SR-2B Quality Owner approved the exact v2 rule after inspecting both 200% full overlays、
  all required zooms、all 56 positives and all 16 frozen negatives.
- [x] SR-2B recorded exact rule/overlay/zoom digests while preserving the sealed manifest bytes.
- [ ] SR-2C proves `visual-observation/2` ID/reconstruction and cache-version single source.
- [ ] Current-source production preflight repeats exact `79/124` observations、
  `13/16` batches、approved digests、all limits true and Provider calls `0`.
- [ ] All 32 required logical tests exist and pass.
- [ ] Existing text/OCR/parser/Advisor/result/frontend regression suites pass without relaxation.
- [ ] Provider contract/cache/call records are schema-bound and redacted.
- [ ] No visual observation is silently unscheduled or missing a coverage disposition.
- [ ] Current-source live result passes exact-one positive/reference/non-inspection matching and
  zero negative false positives.
- [ ] Actual visual and total Vision calls are within 16 per page.
- [ ] A new project/result was used; old immutable results remain unchanged.
- [ ] Chrome evidence proves raw/recognized separation and visual source recovery.
- [ ] `auto-feature-smoke-test` completed or reports a real blocker.
- [ ] Independent reviewer verdict is `accept` or all blocking issues were fixed and re-reviewed.
- [ ] D7-T2 symbol closure is recorded; D7-T3 is resumed, not prematurely marked complete.

## Execution Handoff

Task 0、SR-1、SR-2、SR-3 已分别完成于 `994cbe4`、`d3fac79`、`bb035bc`、
`90bfb43`。SR-4 Steps 1-7 保留在当前七文件 working diff，Step 8 已按真实 sealed
source fail closed。SR-2A 已完成为 `capacity_feasibility_unproven` 且没有 code
commit。SR-2B Step 1 exact rule/digest correction 已提交为 `09f70df`；Steps 2-4
的两次 renderer、Quality Owner approval、stable handles 和 `PDF-007` contract
binding 已完成。下一 executable step 是 `SR-2C Step 1` PDF RED，但本 approval
turn 在该 step 前停止。不得重复 Task 0 或 SR-1～SR-3、执行退休的 packing-only
steps、提交当前 SR-4、进入 SR-5、追加第二个 activation amendment 或调用 Provider。

当前父 agent 保持唯一 writer，read-only explorer/reviewer checkpoints 保持 mandatory。
SR-2B exact rule、两页 full overlays、全部 zooms 和 Quality Owner verdict 已全部
通过并形成 docs-only closure。只有 SR-2C focused GREEN、exact current-source
preflight 和 independent review 全部通过，才进入 SR-4 Step 8。
