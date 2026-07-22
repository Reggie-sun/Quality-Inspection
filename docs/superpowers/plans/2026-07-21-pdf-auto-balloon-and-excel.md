# PDF Auto-Balloon and SIP Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在七天内交付一个内部可真实试用的纵向闭环：处理当前四份工程 PDF，生成可追溯候选，完成人工审核和气泡调整，并从同一 `reviewed_result` 原子地产出带气泡 PDF、固定 SIP Excel 和 manifest。

**Architecture:** 采用模块化单体；FastAPI 和 concurrency=1 的 Celery Worker 共享 PostgreSQL、Redis 与同一受控 FileStorage，React/PDF.js/SVG 只编辑 working copy，正式编号、PDF 绘制和三产物导出由后端确定性 Owner 完成。长期语义只由 `docs/contracts/MAIN_CONTRACT_MATRIX.md` 拥有；P0 选择只由 `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md` 拥有；`.agent/harness/contracts/*.json` 只能由 P0 Markdown 生成，run/receipt 只保存执行证据和当前版本结论。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、PostgreSQL、Redis、Celery、PyMuPDF、openpyxl、httpx、React、TypeScript、Vite、PDF.js、SVG、pytest、Vitest、Playwright、Docker Compose、Micromamba。

---

## Source Of Truth And Execution Selection

- Global stable contracts: `docs/contracts/MAIN_CONTRACT_MATRIX.md`（69 个长期 global contract IDs）。
- P0 traceability: `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`（111 个细粒度 P0 IDs；101 global mappings + 10 implementation-only）。
- Approved scope: `docs/superpowers/specs/2026-07-21-pdf-auto-balloon-and-excel-design.md`, Section 10.1。
- Selected lane: `Heavy`；本计划建立 runtime entry/config、PostgreSQL schema 和跨服务 data-integrity boundary。
- Selected plan: 本文件；执行时只能把本文件作为 current plan，并按 Day 1 → Day 7 顺序推进。
- Selection evidence: 用户明确要求 contract-first、Harness-first、Day 1～Day 7 的 `superpowers:writing-plans` 输出。
- Validation action: `continue`；每个 task 必须先看到预期失败，再写最小实现，再运行 focused gate。
- Writer ownership and order: 一次只允许一个 writer 修改同一 task 的 file group；reviewer 只读。父 agent 在每个 task 后复查 diff、tests 和 contract IDs。
- First implementation verification: Day 1 `D1-T1` 创建 Harness 后运行 `python .agent/harness/scripts/check-contracts.py`；当前 planning turn 不提前创建或执行该脚本。

### Pre-execution ownership record

- Problem boundary: 只实现 current-four 的 upload → automatic → review → balloon → fixed export vertical slice。
- First-PDF owner: `JS26032501-1-03-036#上下座B#A1.pdf`（hash `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec`）是唯一 first vertical checkpoint；其闭环未通过前不得把其余三份的横向 fan-out 当成进展替代。
- Final Owners: page inventory、candidate/coverage、review aggregate、numbering、placement、export orchestrator，职责按 global main contract 固定；P0 traceability 只把它们绑定到 task/selector。
- Old path: 新仓库无业务旧路径；不得创建 bridge、shadow、dual-write 或 legacy fallback。
- Unchanged contract: Provider 不是正式语义 Owner；frontend 不产生 formal result；三产物不允许部分发布；P1/P2 全部保持未实现。
- Focused verification: 每个 task 的最后一个 test command；Day 7 使用 current-four live receipt 收口。

### Day 2 continuation amendment — 2026-07-21

本节是对同一 current plan 的原地修订，不创建第二套 plan。修订依据是 D1-T1～D1-T3 的实际接口、当前 `a859fb8` 后继 worktree、fresh D1 task receipts，以及 `0715095` 已带入的 approved design spec。

- Selected lane: `Heavy`。
- Selected plan: 本文件，仍是唯一 current implementation plan。
- Selection evidence: `run-p0.py` 当前只支持 task scope 并在 selector 结束后立即 seal；`generate-receipt.py` 的 input identity 尚未绑定 Provider fixture bytes；`LogicalJob` 尚无 successful result ref；Alembic metadata 与 schema test 仍只登记 D1 models/tables。
- Validation action: `amend` 后 `continue`；Owner、stable contracts 和 Day 2 顺序不变，只修订实际接口、allowed paths 和验证闭环。
- Writer ownership and order: 父 agent 是唯一 writer，严格按 `D2-T1 → D2-T2 → D2-T3`；explorer/reviewer 只读，同一 file group 不并发写。
- Problem boundary: 只完成 current-four identity/page inventory、fixture-only Provider adapters、processing preflight/state/error/idempotent inventory；不实现 candidate、review、balloon、export 或其他 D3+ 能力。
- Old path: 新仓库仍无业务旧路径；不得引入 bridge、shadow、dual-write 或 legacy fallback。D1 Harness/FileStorage/idempotency 只做向后兼容的最小接口补齐。
- Unchanged contracts: Provider 仍只是 OCR Signal / Vision Advisor；fixture 不产生 network/付费调用；PDF bytes、完整 base64、credential、Authorization 和宿主机路径不进入仓库、日志、manifest 或 receipt；`scanned` 只进入 unsupported routing；fatal/blocking 不得形成 formal success。
- Rollback: 每个 task 只 revert 本 task commit；D2-T3 migration rollback 到 `0001` 后第一项验证为 `micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py -q`。
- First next verification: `micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_coordinates.py backend/tests/unit/pdf/test_classification.py backend/tests/unit/pdf/test_inventory.py backend/tests/integration/test_pdf_inventory.py -q`，预期因 `app.pdf` 实现缺失而 collection FAIL。

| Task | Single integration Owner | Actual-interface delta | Allowed paths | Next task gate |
| --- | --- | --- | --- | --- |
| `D2-T1` | Page inventory Owner；coordinate/classification 是其受约束子 Owner | 给 `run-p0.py` 增加 seal 前的受控 input-artifact hook；current-four manifest bytes 进入 run input identity；补齐 span/line、routing、coordinate 与 staging privacy tests | `backend/app/pdf/**`; `backend/tests/unit/pdf/**`; `backend/tests/integration/test_pdf_inventory.py`; `backend/tests/contract/harness/test_contract_architecture.py`; `.agent/harness/scripts/{run-p0.py,generate-receipt.py,stage-current-four.py}`; status projection 与 generated mirror/bindings | focused PDF tests + live current-four registration + D2-T1 task receipt closure |
| `D2-T2` | Provider-port Owner；concrete adapters 只能产生 Signal/Advisor 结果 | fixture envelope 增加 sanitized payload；D2-T2 fixture bytes 进入 receipt input identity；call record 只持久化脱敏 metadata/resource refs | `backend/app/providers/**`; `backend/tests/contract/{conftest.py,test_tencent_ocr_provider.py,test_qwen_vl_provider.py,test_provider_call_records.py}`; `.agent/harness/fixtures/providers/**`; `.agent/harness/schemas/provider-fixture.schema.json`; `.agent/harness/scripts/{generate-receipt.py,run-provider-contracts.py}`; Harness identity regression test；status projection 与 generated mirror/bindings | fixture schema/secret scan + provider-contract tests + zero-call D2-T2 task receipt closure |
| `D2-T3` | Processing pipeline Owner；Capability Veto、Project state、Error repository 和 Job idempotency 保持各自 final boundary | `LogicalJob` 增加 successful `result_ref`；FileStorage 增加受控 resolve/read/delete/probe 接口；Alembic metadata/schema assertion 登记 D2 models/tables；补齐 task Harness closure | `backend/app/{capabilities,processing,errors}/**`; `backend/app/projects/state.py`; `backend/app/jobs/idempotency.py`; `backend/app/storage/local.py`; `backend/app/celery_app.py`; `backend/alembic/env.py`; `backend/alembic/versions/0002_processing.py`; D2-T3 focused tests及必要 D1 storage/schema regression；status projection 与 generated mirror/bindings | migration + active/failure path integration tests + D2-T3 task receipt closure |

三个 task 都必须执行全局 `Per-task Harness closure`：focused tests → pre-run mirror/bindings/check → task run → 记录 literal run ID → 只依据该 sealed run 投影该 task 的 Markdown `current_status` → regenerate mirror/bindings/check → `generate-receipt.py --check-run <literal-run-id>`。D2-T1 首次 closure 的唯一 task phase 是 focused tests 后执行的 live current-four registration run；Day 2 最终 refresh 则必须通过 `--current-four-run <literal-registration-run-id>` 复用其中已 seal、schema-valid 的 manifest，不能使用无 current-four identity 的裸 runner。因为 executable identity 是全仓 allowlist，后续 task 会使先前 task receipt stale；D2-T3 最终代码稳定并完成 review 后，必须在同一最终 executable state 重新运行 D2-T1、D2-T2、D2-T3 task phases，并逐一用 literal run ID 校验，最终交付只报告这组三个 fresh/passed receipts。

### Day 3 continuation selection — 2026-07-21

- Selected lane: `Heavy`。
- Selected plan: 本文件，仍是唯一 current implementation plan；本次只执行 `D3-T1`，在 `D3-T2` 前停止。
- Selection evidence: branch `feature/d1-t1-contract-harness` 在 `5573597` clean；D2-T1～D2-T3 已分别由 fresh/passed task receipts `20260721T130805437356Z-e52457ee`、`20260721T130819985433Z-dae6310e`、`20260721T130836658610Z-27e7b074` 收口；D3-T1 的 14 个 P0 rows 仍为 `not_run`。
- Validation action: `continue`；先执行四个 table-driven candidate test 文件的 RED，再做最小实现，最后完成全局 `Per-task Harness closure`。
- Writer ownership and order: 父 agent 是唯一 writer；explorer/reviewer 只读，不得修改 workspace 或扩大到 `D3-T2`。
- Problem boundary and Owner: candidate semantics 是唯一业务 Owner；deterministic parser、ordered grouping、technical-requirement disposition 和 four-field complex fallback 只在该 Owner 内提交 D3-T1 语义。
- Old path: 当前没有 candidate 业务旧路径；本 task 新建 canonical modules，不引入 bridge、shadow、dual-write、duplicate resolver 或第二 final Owner。
- Unchanged contracts: Provider 不是正式语义 Owner；`Φ` 保持 `unknown + requires_confirmation`；GD&T、roughness、weld 只保留 `raw_text / coordinates / coarse_type / requires_confirmation`；identical text 不构成跨 view 自动合并；coverage、automatic-result freeze 和 migration 保持未实现。
- Rollback and failure boundary: 只 revert 本 task commit；rollback 后第一项验证为 backend 全量测试，确认 Day 2 baseline 未受影响。unsupported deterministic annotation 必须显式失败，复杂类型和非可执行技术文本不得被提升为完整正式语义。
- Next verification: `micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_parser.py backend/tests/unit/candidates/test_grouping.py backend/tests/unit/candidates/test_disposition.py backend/tests/unit/candidates/test_complex_fallback.py -q`，预期因 `app.candidates` 实现缺失而 collection FAIL。

### Day 3 completion continuation — 2026-07-21

- Selected lane: `Heavy`。
- Selected plan: 本文件，仍是唯一 current implementation plan；只执行剩余 `D3-T2` 并形成 `D4-T1` readiness，不执行任何 D4 task。
- Selection evidence: branch `feature/d1-t1-contract-harness` 在 `778f7d8` clean；fresh backend baseline 为 181 passed；`D3-T1` 的 14 行已 passed，literal receipt `20260721T143049061302Z-2a55d6f2` 当前有效；`D3-T2` 的 4 行仍为 `not_run`。
- Validation action: `amend` 后 `continue`。Owner、stable contract 和 task 顺序不变；实际接口要求把 D2 临时的 inventory-only success 替换为 coverage-checked automatic-result success，并同步 metadata/schema/idempotency assertions。
- Writer ownership and order: 父 agent 是唯一 writer；explorer/reviewer 严格只读。先 RED tests，再最小实现和 migration，最后在同一最终 executable state 刷新 `D3-T1` 与 `D3-T2` 两条 task receipts。
- Problem boundary and Owners: Coverage Owner/Veto Gate 唯一提交 coverage verdict；Duplicate Advisor 只产生 `possible_duplicate + requires_confirmation` relation；Automatic-result Owner 只在 coverage blocking 为零时持久化 immutable raw result。Provider、inventory、frontend 和 reviewer 都不是该 final Owner。
- Old path action: `InventoryPipeline.run()` 当前 `_store_inventory() -> complete_logical_job(inventory_ref)` 是 D2 临时 finalization，本 task 选择 `replace`；inventory asset 继续作为 immutable input evidence，但 logical task 的 formal result 改为 automatic-result identity，不保留 dual final Owner。
- Actual-interface delta and allowed paths: 除 D3-T2 原列文件外，允许最小修改 `backend/alembic/env.py`、`backend/tests/integration/test_schema.py` 与 `backend/tests/integration/test_task_idempotency.py`，分别登记新 metadata、证明 0003 exact schema/trigger、把 D2 inventory-only 临时成功断言收敛到 D3 automatic-result success；不得触碰 review、balloon、export 或 D4 files。
- Unchanged contracts: identical text 不自动合并；ambiguous 可审核但 incomplete/duplicate disposition 为 blocking；blocking failure 不插入 automatic result、不进入 `ready_for_edit`；raw automatic result 的 UPDATE/DELETE 均由数据库 trigger 阻断；D4 working copy 只能引用 raw result，不能原地修改它。
- Rollback and failure boundary: 只 revert 本 task commit；migration rollback 为 `0003 -> 0002`，实际发生 rollback 后第一项验证是 `micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py -q`。coverage blocking 必须形成 structured error，且 logical job 不得成功。
- Next verification: `micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_coverage.py backend/tests/integration/test_result_layers.py -q`，预期因 D3-T2 modules 缺失而 collection FAIL。

### Day 4 continuation selection — 2026-07-21

- Selected lane: `Heavy`。
- Selected plan: 本文件，仍是唯一 current implementation plan；严格按 `D4-T1 → D4-T2 → D4-T3` 完成 Day 4，并在 `D5-T1` 前停止。
- Selection evidence: branch `feature/d1-t1-contract-harness` 在 `4ef0998` clean；fresh backend baseline 为同一 201 selectors（Compose-network DB 中 199 passed，宿主机 Docker CLI 上 2 passed）；Alembic current/head 均为 `0003`，`alembic check` 无待生成 migration；全部 Day 4 rows 仍为 `not_run`。
- Validation action: `amend` 后 `continue`。Owner、stable contracts、task IDs、selectors 和顺序不变；只补充当前 exact metadata/schema、同一未发布 Day 4 migration 的增量执行，以及 localhost workbench smoke 所需的实际入口文件。
- Writer ownership and order: 父 agent 是唯一 writer；explorer/reviewer 严格只读。每个 task 都先 RED、再最小实现、focused gate、task Harness closure、独立 review 和独立 commit；D4 最终 executable state 再刷新 D4-T1～D4-T3 receipts。
- Problem boundary and Owners: `D4-T1` 由 Review aggregate 唯一提交 working-copy command 语义，Operation audit repository 只持久化同事务摘要；`D4-T2` 由 Review aggregate 提交 version/freeze，Review lock service 只拥有 active-editor lease，Review freeze Veto Gate 只阻断，router 只执行已提交 contract；`D4-T3` 的 PDF workspace、overlay、review panel 和 mutation client 都是 frontend executor，不产生 formal review 语义或 `ReviewedResult`。
- Old path action: 当前没有 review/workbench 业务旧路径；新建 canonical modules，不引入 bridge、shadow、dual-write、autosave、frontend formal result 或第二 final Owner。`AutomaticResult` 保持 immutable input Owner，working copy 只引用其 identity。
- Actual-interface delta and allowed paths: `D4-T1` 除原列文件外，允许最小修改 `backend/alembic/env.py`、`backend/tests/integration/test_schema.py` 和 `backend/app/audit/operations.py`，只用于登记 Review metadata、证明 `0004` exact schema 和复用同事务 operation summary；其中 `backend/app/audit/operations.py` 只有 RED 证明现有字段不足时才修改。`D4-T2` 允许最小修改 `backend/app/review/schemas.py` 以承载 router request/response contracts，并修改 `backend/tests/integration/test_review_operations.py`、`backend/tests/integration/test_review_working_copy.py`、`backend/tests/integration/test_operator_audit.py`，只用于让既有 command tests 取得 D4-T2 新增的 active editor lease；不得放宽原 D4-T1 assertions。`D4-T3` 允许最小修改 `frontend/src/main.tsx`，只用于挂载已计划的 `InspectionWorkbench` 以执行 localhost browser smoke；允许新增 `frontend/src/components/workbench/InspectionWorkbench.test.tsx`，只用于证明一个 pending command 在显式 Save 前不会被后续操作静默覆盖；允许修改仓库 `.gitignore`，且仅加入 `frontend/node_modules/` 与 `frontend/dist/`，避免依赖安装和 build artifacts 污染正式 task diff。其余 allowed paths 仍以三个 task 原列文件为准。
- Migration execution: `D4-T1` 的 schema RED 一次性锁定尚未发布的最终 Day 4 persistence shape：`review_working_copies`（含 item-set freeze 持久字段）与 `review_locks`；同一个 `0004_review.py` 在 D4-T1 生成并应用。该 persistence-only reservation 不实现 D4-T2 lock/freeze service/router 语义，D4-T2 仍必须先看到行为 RED。禁止原地改写已应用 `0004`、创建 `0005` 或把 D5 `ReviewedResult` 提前进入 schema；最终必须证明 upgrade/head/check 与 exact-schema assertions。
- Unchanged contracts: 每条 command 同事务只递增一次 working-copy version 并写一条 operation record；stale write 不覆盖；freeze blockers 仅为 `coverage_blocking / unresolved_confirmation / balloon_required_unconfirmed`；item-set freeze 后 project 仍为 `editing` 且不创建 `ReviewedResult`；Save 不 freeze；PDF/render/viewport state 不写回 PDF coordinates；Provider 不调用，credential 不读取或输出；`.agent/EXECUTION_STATUS.md` 保持缺失，不在 Day 4 发明。
- Rollback and failure boundary: 每个 task 只 revert 本 task commit；D4 schema rollback 为 `0004 -> 0003`，实际发生 rollback 后第一项验证是 `micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py -q`。transaction/version/lock/freeze 任一冲突都必须显式失败，不得转为 warning 或 formal success。
- First next verification: `micromamba run -n qi-p0 pytest backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_result_layers.py -q`，预期因 `app.review` modules 缺失而 collection FAIL。

### Day 5 continuation selection amendment — 2026-07-22

本节是对同一 current plan 的最小原地修订，不创建 `D5-T0`、第二份 plan 或独立 frontend 支线。

- Selected lane: `Heavy`。
- Selected plan: 本文件，仍是唯一 current implementation plan；严格按 `D5-T1 → D5-T2 → D5-T3` 完成 Day 5，并在 `D6-T1` 前停止。
- Selection evidence: branch `feature/d1-t1-contract-harness` 在 `fa5d967`；fresh baseline 为 Compose-network backend `256 passed + 2 deselected`、host topology `2 passed`、frontend `10 passed`、production build passed，contract drift/conflict/missing 均为 0。当前 `frontend/src/main.tsx` 仍注入硬编码 fixture、`pdfDocument={null}` 与固定失败 `onSave`；backend 只有 health/review routes，没有 project bootstrap 或受控 source-PDF delivery；D7-T2 已要求 runner 提供可执行 `QI_P0_PROJECT_URL`。目标、Owners 和 stable contracts 未变，因此 validation action 是 `amend` 后 `continue`，不是 `replan`。
- Problem boundary and single Owners: `D5-T1` 只由 Numbering Owner 与 Placement Owner 提交确定性编号/位置；`D5-T2` 只由 Balloon command service、Balloon validator Veto Gate 与 Review freeze Owner 提交 balloon mutation、formal validation 和 immutable `ReviewedResult`；`D5-T3` 的 project/workbench projection、PDF.js、selection 和 UI 仍是 read projection/Executor，不产生 formal business result。Project bootstrap 只投影现有 Project、Review aggregate、AutomaticResult/FileStorage 与 Balloon Owner 已提交的事实。
- Old path action: `frontend/src/main.tsx` 的 demo fixture、null PDF 和 fixed-failure Save 在 `D5-T3` 选择 `replace/remove`；真实 project bootstrap 成为唯一入口。不得保留 fixture/live bridge、shadow render、dual Save、fallback fixture 或 frontend-side `ReviewedResult`。
- Actual-interface delta and allowed paths: `D5-T1` 保持原列 `backend/app/balloons/{__init__,schemas,numbering,placement}.py` 与两个 focused unit test。`D5-T2` 保持原列 balloon/review/main/migration/tests，并最小增加 `backend/app/review/{router,schemas}.py`、`backend/alembic/env.py`、`backend/tests/integration/{test_balloon_api,test_schema}.py`，只用于 confirm/balloon routes、0005 metadata/exact-schema/immutability 和 API failure contracts。`D5-T3` 允许最小增加或修改 `backend/app/projects/router.py`、`backend/app/main.py`、`backend/tests/integration/test_project_workbench_api.py`，只提供不泄露宿主机 path 或 `resource_ref` 的 workbench bootstrap/source-PDF read surface；frontend 允许原列文件，以及 `frontend/src/api/{client,types}.ts`、`frontend/src/main.tsx`、`frontend/src/features/{review,balloons}/**`、`frontend/src/components/workbench/{ProjectWorkbenchApp,InspectionWorkbench}.tsx`、`frontend/src/components/pdf/{PdfWorkspace,OverlayLayer}.tsx`、`frontend/src/components/review/ReviewPanel.tsx`、对应 focused tests 和 `frontend/vite.config.ts`。三个 task 均允许更新本文件、D5 Markdown status projection 与 generated mirror/bindings；Harness scripts/policy/schema 不改变。
- Real wiring checks: 页面必须从 URL 中的真实 `project_id` 与明确 `operator_id` bootstrap working copy，取得并续持 review lock，始终用 response 中的 current `expected_version`；source PDF 只能由同源受控 API 交给 PDF.js，payload/DOM/URL 不得出现宿主机 path 或 `resource_ref`。Save 只调用 review command；Freeze Items、generate、move/delete/rebuild/reorder/renumber、Confirm 分别调用 canonical API。candidate/item、source、balloon 和右侧 review row 通过同一 item/source/balloon relation 双向定位；drag 必须先用 inverse screen CTM 得到 render coordinates，再应用当前页 `render_to_pdf_matrix` 得到并 POST PDF coordinates，且必须覆盖 rotated-page test。Confirm 只能消费 backend-validated final balloons，并由 backend 创建 immutable `ReviewedResult`。
- Writer ownership and order: 父 agent 是唯一 writer；explorer/reviewer 严格只读。每个 task 都先 RED、再最小实现、focused gate、task Harness closure、独立 review 和指定独立 commit；不得并发写同一 file group。既有未跟踪 `__pycache__/` 不删除、不修改、不 stage。
- Rollback and failure boundary: 每个 task 只 revert 本 task commit；0005 实际 rollback 为 `0005 → 0004`，若发生 rollback，第一项验证是 `micromamba run -n qi-p0 alembic -c backend/alembic.ini current` 后运行 `backend/tests/integration/test_schema.py`。version/lock/item-freeze/balloon-validation/project/PDF identity 任一失败必须显式返回 structured failure，不得回退 demo fixture、冻结失败内容或形成 formal success。
- Next verification: `micromamba run -n qi-p0 pytest backend/tests/unit/balloons/test_numbering.py backend/tests/unit/balloons/test_layout.py -q`，预期因 `app.balloons` modules 缺失而 collection FAIL。

## Planning Preparation Stage — Completed Before Day 1

本阶段是 `superpowers:writing-plans` 产物，不是 implementation task：

1. 已创建 `docs/contracts/MAIN_CONTRACT_MATRIX.md`，以 Sections 1～9 为来源沉淀 69 个长期契约；其中不含 Day、task、selector、current-four、具体 Provider 或运行命令。
2. 已将原 111 条细粒度 P0 行迁移为 `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`，保持 111 IDs 唯一；101 行映射 global contract，10 行显式标记 implementation-only，0 行待确认。
3. 已固定 global → P0 → generated mirror → generated bindings → policy → scripts → immutable run → receipt 的单向事实链。
4. 当前没有创建 `.agent/harness/` 文件，没有实现业务代码，也没有执行 test/live Provider；111 行状态均为 `not_run`。

## Stage-Gated External Preconditions

外部 gate 只阻塞依赖它的阶段，不得把 Day 6/7 的材料提前变成 Day 1 全局 blocker，也不得用 mock success 越过：

### Before D1-T1

1. 当前 checkout 存在未跟踪的 `AGENTS.md`、`.agent/`、`.ai-native/` 和既有 bootstrap plan。它们属于另一项进行中工作；本计划不得顺手 stage/commit。创建 isolated worktree 前，必须确认目标 worktree 能读取同一规则，或先由原 Owner 完成其独立提交。
2. 使用 `superpowers:using-git-worktrees` 建立 isolated worktree；不得在当前 dirty `main` 上实施业务代码。

### Before D2-T1 Input Registration

3. 当前四份源 PDF 可由执行者只读访问，basename/hash/page facts 与 P0 traceability 的 Frozen Current-Four Identity 一致，并已获准用于内部验证。此时只要求源可访问；schema-valid run registration 由 `D2-T1` 新建的脚本完成。

### Before D6-T1 Formal Export

4. 质量 Owner 明确确认唯一 SIP template、mapping 和 capacity。当前候选 `检验记录标准表.xlsx` 不能在未确认时冒充正式模板。
5. 确认 balloon font 文件与 license；候选为 DejaVu Sans，登记 hash 后才可进入 export preflight。

### Before D7-T2 Full-P0 Live Run

6. 腾讯 OCR 与 qwen live credentials 仅通过服务端环境注入；仓库只提交脱敏 fixtures。缺 credentials 不阻塞此前 fixture/provider-contract tasks。
7. `D2-T1` 已生成 current-four identity manifest；真实 PDF bytes/宿主机路径未写入仓库，D7 会原地复核 identity 后通过受控 FileStorage upload。
8. 质量人员可完成 first-PDF 与其余三份的实际 review/balloon verdict；无人值守结果不能伪造 human pass。

### First-PDF-First Execution Rule

从 `D2-T1` 起，first PDF 是每个新业务阶段的默认纵向 checkpoint：先在当前已具备的 fixture/integration 能力下推进其 inventory → candidates → review → balloons → export，不以其余三份的批量局部成功替代该链。`D7-T2` 在同一 full-p0 run 中先让 first PDF 完整通过 live upload、automatic、human review、balloon、export 和 consistency；任一阶段失败即停止 fan-out 并记为 blocked/failed，只有它通过后才按 manifest 顺序执行其余三份。该规则不新增 task、contract 或 P1/P2 scope。

## Scope And Rollback

P0 明确排除 Provider 通用 cache、preview pipeline、autosave contract、完整 trace/error UI、通用 lineage/stage/artifact 治理、RBAC/SSO、通用 Excel 模板引擎、LibreOffice 自动 smoke、纯扫描正式支持、准确率 threshold、回归集和盲测平台。

每个 task 单独 commit。若 task 失败，优先 `git revert <task-commit>`；数据库 schema task 的 rollback 是：

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini downgrade base
micromamba run -n qi-p0 pytest backend/tests/integration/test_schema.py -q
```

预期：migration 表回到 base，业务表不存在，schema rollback test 通过。只有本计划新建且明确标记 disposable 的 Compose volume 才允许由执行者删除；不得删除宿主机样例、模板、其他项目 volume 或当前 dirty checkout。

## File Map

### Root and planned project Harness

| File | Responsibility |
| --- | --- |
| `.gitignore` | 排除 secret env、build/test cache 和 `.agent/harness/runs/*`；只保留目录约定文件 |
| `.env.example` | 只列 config key，不放 secret value |
| `environment.yml` | Micromamba Python 3.11/Node 22 开发环境 |
| `compose.yaml` | 五个 P0 runtime services 与共享 volume |
| `Makefile` | 精确 offline/live verification 入口 |
| `.agent/harness/README.md` | 四层 Owner、目录边界、fixture/live 和 immutable run 约定 |
| `.agent/harness/policy/{harness-policy,p0-acceptance-policy,provider-call-policy,failure-severity-policy}.yaml` | 状态、severity、freshness、current-four、调用预算和总体 verdict 规则 |
| `.agent/harness/contracts/p0-contracts.json` | 由 P0 Markdown 生成的 111-row 机器镜像 |
| `.agent/harness/contracts/global-contract-bindings.json` | 由 mirror 生成的 global → primary/related-business/related-implementation 三类 P0 反向索引；禁止手工双写或把 related 冒充 enforcement |
| `.agent/harness/schemas/*.schema.json` | contract、binding、run、result、receipt、manifest 和 Provider fixture schema |
| `.agent/harness/fixtures/` | 默认脱敏 Provider/manifests/expected fixtures；业务 tests 仍在 backend/frontend 目录 |
| `.agent/harness/scripts/` | 生成/检查 mirror、编排测试、current-four、Provider、coordinates、export 和 receipt |
| `.agent/harness/runs/<run-id>/` | 每次运行的不可变 `run.json/receipt.json/contract-results.json/logs/reports/artifacts`，默认 Git ignored |
| `.agent/harness/baselines/` | 经明确批准后才进入 Git 的脱敏 baseline；不保存真实 PDF |

### Backend foundation

| File group | Responsibility |
| --- | --- |
| `backend/pyproject.toml`, `backend/Dockerfile`, `backend/alembic.ini`, `backend/alembic/*` | Python dependencies、image、migration entry |
| `backend/app/config.py`, `db.py`, `main.py`, `celery_app.py` | typed config、DB、FastAPI、single-worker queue |
| `backend/app/projects/{models,schemas,state,router}.py` | project identity/state/upload API |
| `backend/app/storage/{models,local}.py` | metadata 与 same-filesystem atomic FileStorage |
| `backend/app/audit/operations.py` | simple operator operation summary |
| `backend/app/jobs/idempotency.py` | stable logical-task claim/result |
| `backend/app/capabilities/service.py` | processing/export preflight Veto Gate |

### Recognition and review

| File group | Responsibility |
| --- | --- |
| `backend/app/pdf/{schemas,coordinates,classification,inventory}.py` | page inventory 和 coordinate truth |
| `backend/app/providers/{base,tencent_ocr,qwen_vl,fixtures}.py` | Provider ports/adapters，非正式 Owner |
| `backend/app/processing/{pipeline,tasks}.py` | staged processing orchestration 与 raw freeze |
| `backend/app/candidates/{schemas,parser,grouping,disposition,complex_fallback,duplicates,coverage}.py` | deterministic candidates 与 coverage Owner |
| `backend/app/review/{models,schemas,locks,service,router}.py` | working copy、commands、version、freeze |

### Balloons and export

| File group | Responsibility |
| --- | --- |
| `backend/app/balloons/{schemas,numbering,placement,service,validator,renderer}.py` | suggested/formal numbering、layout、commands、formal PDF |
| `backend/app/exports/{template_registry,excel,naming,manifest,validators,service,router}.py` | fixed SIP、three-artifact staging、success Owner |
| `backend/assets/templates/sip-v1.xlsx`, `sip-v1.mapping.json` | 经外部 gate 确认后的单一 binary template 与固定 mapping |
| `backend/assets/fonts/DejaVuSans.ttf`, `LICENSE-DejaVu.txt` | 经 gate 登记的 balloon font asset |

### Frontend

| File group | Responsibility |
| --- | --- |
| `frontend/package.json`, `package-lock.json`, `Dockerfile`, Vite/TS configs | React build/test/runtime |
| `frontend/src/api/{client,types}.ts` | stable HTTP types/client |
| `frontend/src/components/pdf/{PdfWorkspace,OverlayLayer}.tsx` | PDF.js page/zoom/pan 与 SVG overlays |
| `frontend/src/components/review/ReviewPanel.tsx` | explicit review commands |
| `frontend/src/components/balloons/BalloonOverlay.tsx` | drag/delete/rebuild/reorder UI |
| `frontend/src/components/workbench/{InspectionWorkbench,selection}.tsx` | left/right composition、selection、save/freeze |
| `frontend/e2e/p0-workbench.spec.ts` | real browser vertical-flow checks |

### Test layout

| Directory | Purpose |
| --- | --- |
| `backend/tests/unit/` | pure storage/coordinate/parser/numbering/layout/export rules |
| `backend/tests/contract/` | Provider/API/schema/log-redaction contracts |
| `backend/tests/integration/` | PostgreSQL/Redis/Celery/FileStorage/API/export |
| `backend/tests/e2e/` | offline/failure vertical flows |
| `.agent/harness/fixtures/providers/` | sanitized Provider JSON/crops used by backend contract tests; fixture mode is default |
| `frontend/src/**/*.test.ts(x)` | component/state tests |
| `frontend/e2e/` | Playwright live browser checks |

## Harness Design

### Authority and minimum scope

Harness 不是 global contract Owner，也不承载 backend/frontend 业务测试。它只做五件事：生成契约镜像、按 policy 选择已有 tests、编排 fixture/live phases、保存 immutable run evidence、生成 receipt。禁止在 P0 建 Web 后台、通用 DAG、分布式调度、自动根因、长期查询平台、完整成本仪表盘、通用契约编辑器或 baseline 审批系统。

固定单向关系：

```text
P0 Markdown Traceability Matrix
→ generate-contract-mirror.py
→ p0-contracts.json
→ generate-global-bindings.py
→ global-contract-bindings.json
```

`check-contracts.py` 必须从 Markdown 重新解析并比较生成结果；JSON 漂移直接失败，不允许 JSON → Markdown 回写。

### Policy and evidence

- Contract result 只允许 `passed / failed / blocked / not_run`。
- Severity 只允许 `fatal / blocking / review_required / warning / informational`；P0 总体 passed 要求所有 policy-declared blocking contracts 为 passed。
- Receipt scope 只允许 `task / full-p0`：task receipt 只裁决选中 task，永远不能声明 formal P0 passed；只有 full-p0 receipt 可给正式结论。
- `blocked` 可如实记录任一 contract 的执行期阻塞，但 full-p0 passed 的 `blocked_allowed_contract_ids` 与 `not_run_allowed_contract_ids` 都为空；111 条当前 P0 均须 passed。
- Mirror 保留 `current_status`，但 canonical `contract_definition_hash` 排除且只排除该 evidence projection；`status_projection_hash` 单独记录。Receipt freshness 绑定 definition/executable-content/policy/config/input identity，不因合法 status projection 更新或只提交该 projection 而自失效；Git revision 仅作诊断记录。
- Fixture 是默认模式，不产生付费调用；live 必须显式传 `live` 和 `--input-set current-four`，并应用 Provider call/budget/retry 上限。
- Stale receipt、`latest` pointer、旧 run、docs claim 或 test count 不能证明当前版本。
- 每次命令先创建唯一 `.agent/harness/runs/<run-id>/`，写入 code/config/input identity；目录完成后只读，任何可变 latest 指针都不能替代该目录。
- `latest` 或 `latest-successful` 只能是指针/摘要，不能替代具体 run 目录。
- 每个 pytest/Vitest/Playwright case 在 docstring/title 中包含至少一个 `P0-*` ID；普通 selector 是 exact argv command。`phase://<mode>/<phase>` 是唯一非 shell selector，由当前 `run-p0.py` 进程内部 dispatch 到当前 open run，禁止 subprocess 递归或创建 child run。

### Validation layers

1. `unit`：coordinates、parsers、grouping、coverage、numbering、placement、Excel safety。
2. `provider-contract`：脱敏 Provider fixtures；默认不产生付费调用。
3. `integration`：FastAPI + PostgreSQL + Redis + Celery + shared storage，覆盖 version/lock/idempotency。
4. `frontend`：Vitest component/state；Playwright 验证真实 viewport 与操作。
5. `export`：重新打开文件，核对 cell/image/page/hash/count/all-or-nothing。
6. `live-e2e`：current-four 逐份执行 processing → review → balloon → export，保存 contract results、receipt 与人工 verdict。

### Per-task Harness closure

`D1-T1` 创建 Harness 本身。其后每个业务 task 必须按以下单向闭环完成，不能跳步或等到 Day 7 集中补接线：

1. 在 P0 Markdown 中确认该 `task_id` 的全部 `p0_contract_id`、selector 与 implementation reason；如实现后的 exact selector 变化，先只改这里。
2. 运行 `generate-contract-mirror.py` 和 `generate-global-bindings.py`，再运行 `check-contracts.py`，证明 Markdown → mirror → bindings 无 drift。
3. focused backend/frontend tests 通过后，执行下表唯一 task phase；该 phase 创建独立 run-id、contract results 和 task receipt。
4. 只依据该 sealed run 更新相应 `current_status`，随后重新生成 mirror/bindings 并再次运行 `check-contracts.py`。
5. 重新校验 task receipt：definition/executable identity 不变，允许且只允许 `status_projection_hash` 变化；若 requirement、Owner、task、tier、selector、blocking、policy 或 executable content 变化，则旧 run 作废并重跑该 task phase。

| Task | Exact Harness phase command after focused tests |
| --- | --- |
| `D1-T2` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D1-T2` |
| `D1-T3` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D1-T3` |
| `D2-T1` | `python .agent/harness/scripts/stage-current-four.py --mode live --source-root "$QI_CURRENT_FOUR_SOURCE_ROOT"` |
| `D2-T2` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T2` |
| `D2-T3` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T3` |
| `D3-T1` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D3-T1` |
| `D3-T2` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D3-T2` |
| `D4-T1` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D4-T1` |
| `D4-T2` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D4-T2` |
| `D4-T3` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D4-T3` |
| `D5-T1` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D5-T1` |
| `D5-T2` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D5-T2` |
| `D5-T3` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D5-T3` |
| `D6-T1` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D6-T1` |
| `D6-T2` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D6-T2` |
| `D6-T3` | `python .agent/harness/scripts/run-p0.py fixture --scope task --task D6-T3` |

Common pre-phase sync commands before every row above:

```bash
python .agent/harness/scripts/generate-contract-mirror.py
python .agent/harness/scripts/generate-global-bindings.py
python .agent/harness/scripts/check-contracts.py
```

The executor records the run ID printed by the selected row. After projecting that sealed run into `current_status`, run the same three sync commands again and validate the task receipt with `python .agent/harness/scripts/generate-receipt.py --check-run <literal-run-id>`; never resolve `<literal-run-id>` through a mutable `latest` pointer.

## Seven-Day Delivery Map

| Day | Task IDs | Working, testable increment |
| --- | --- | --- |
| Day 1 | `D1-T1`～`D1-T3` | 契约 Harness、可启动五服务 spine、DB/FileStorage/operation/idempotency foundation |
| Day 2 | `D2-T1`～`D2-T3` | current-four page inventory、Provider fixture adapters、processing/raw-result flow |
| Day 3 | `D3-T1`～`D3-T2` | supported candidate types、complex fallback、coverage-ready candidates |
| Day 4 | `D4-T1`～`D4-T3` | review aggregate/lock/freeze API 与可编辑 PDF/table workbench |
| Day 5 | `D5-T1`～`D5-T3` | deterministic balloons、commands、UI interaction 与 reviewed freeze closure |
| Day 6 | `D6-T1`～`D6-T3` | formal PDF、fixed SIP Excel、manifest、all-or-nothing export |
| Day 7 | `D7-T1`～`D7-T3` | failure injection、四样例 live E2E、independent review 与 rollback proof |

## Day 1 — Contract Harness And Runnable Spine

### Task D1-T1: Build The Minimal Contract Mirror, Policy And Immutable-Run Skeleton

**Files:**

- Modify: `.gitignore`
- Create: `.agent/harness/README.md`
- Create: `.agent/harness/policy/harness-policy.yaml`
- Create: `.agent/harness/policy/p0-acceptance-policy.yaml`
- Create: `.agent/harness/policy/provider-call-policy.yaml`
- Create: `.agent/harness/policy/failure-severity-policy.yaml`
- Create: `.agent/harness/schemas/p0-contracts.schema.json`
- Create: `.agent/harness/schemas/global-contract-bindings.schema.json`
- Create: `.agent/harness/schemas/run.schema.json`
- Create: `.agent/harness/schemas/contract-result.schema.json`
- Create: `.agent/harness/schemas/receipt.schema.json`
- Create: `.agent/harness/schemas/current-four-manifest.schema.json`
- Create: `.agent/harness/schemas/provider-fixture.schema.json`
- Create: `.agent/harness/scripts/generate-contract-mirror.py`
- Create: `.agent/harness/scripts/generate-global-bindings.py`
- Create: `.agent/harness/scripts/check-contracts.py`
- Create: `.agent/harness/scripts/run-p0.py`
- Create: `.agent/harness/scripts/generate-receipt.py`
- Generate: `.agent/harness/contracts/p0-contracts.json`
- Generate: `.agent/harness/contracts/global-contract-bindings.json`
- Create: `.agent/harness/fixtures/README.md`
- Create: `.agent/harness/fixtures/manifests/README.md`
- Create: `.agent/harness/fixtures/expected/README.md`
- Create: `.agent/harness/runs/.gitkeep`
- Create: `.agent/harness/baselines/README.md`
- Test: `backend/tests/contract/harness/test_contract_architecture.py`

- [ ] **Step 1: Write the failing one-way-authority and run-layout test**

```python
# backend/tests/contract/harness/test_contract_architecture.py
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TRACE = ROOT / "docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md"
GLOBAL = ROOT / "docs/contracts/MAIN_CONTRACT_MATRIX.md"
HARNESS = ROOT / ".agent/harness"


def test_contract_mirror_is_generated_from_the_only_p0_markdown_source() -> None:
    result = subprocess.run(
        [sys.executable, str(HARNESS / "scripts/check-contracts.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    mirror = json.loads((HARNESS / "contracts/p0-contracts.json").read_text())
    assert len(mirror["contracts"]) == 111
    assert mirror["source"] == str(TRACE.relative_to(ROOT))
    assert mirror["global_source"] == str(GLOBAL.relative_to(ROOT))
    assert all(row["current_status"] in {"passed", "failed", "blocked", "not_run"} for row in mirror["contracts"])


def test_run_schema_requires_immutable_evidence_members() -> None:
    schema = json.loads((HARNESS / "schemas/run.schema.json").read_text())
    required = set(schema["required"])
    assert {
        "run_id", "mode", "scope", "code_identity", "git_revision_at_start", "config_identity", "input_identity",
        "contract_definition_hash", "status_projection_hash_at_start", "started_at",
    } <= required
```

- [ ] **Step 2: Run the contract test and observe the expected missing-Harness failure**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_contract_architecture.py -q
```

Expected: FAIL because `.agent/harness/scripts/check-contracts.py` and schemas do not exist. This is the only expected failure; do not create business services in this task.

- [ ] **Step 3: Add the minimal README, policy and schema contracts**

`.agent/harness/README.md` must state the four Owners verbatim:

```text
docs/contracts/MAIN_CONTRACT_MATRIX.md
  owns long-term stable system semantics

docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md
  owns current P0 selection, task and selector mapping

.agent/harness/contracts/p0-contracts.json
  is a generated executable mirror, never an independent editable truth

.agent/harness/runs/<run-id>/
  owns evidence for one code/config/input execution
```

The initial policies are deliberately narrow:

```yaml
# .agent/harness/policy/harness-policy.yaml
schema_version: harness-policy/1
default_mode: fixture
allowed_modes: [fixture, failure, live]
receipt_scopes: [task, full-p0]
formal_p0_scope: full-p0
result_states: [passed, failed, blocked, not_run]
contract_definition_excludes: [current_status]
status_projection_affects_freshness: false
run_directory: .agent/harness/runs
immutable_after_completion: true
receipt_freshness_hours: 24
latest_pointer_is_evidence: false
```

```yaml
# .agent/harness/policy/p0-acceptance-policy.yaml
schema_version: p0-acceptance-policy/1
required_input_set: current-four
required_sample_count: 4
required_contract_count: 111
allowed_overall_verdicts: [passed, failed, blocked]
task_scope:
  formal_p0_verdict_allowed: false
full_p0_scope:
  formal_p0_verdict_allowed: true
  blocked_allowed_contract_ids: []
  not_run_allowed_contract_ids: []
passed_requires:
  fatal: passed
  blocking: passed
  not_run_count: 0
  stale_receipt_count: 0
  human_trial_verdict: passed
fixture_can_satisfy_live_contracts: false
```

```yaml
# .agent/harness/policy/provider-call-policy.yaml
schema_version: provider-call-policy/1
fixture:
  external_calls_allowed: false
live:
  explicit_flag_required: true
  max_retries_per_call: 2
  max_crop_expansions: 1
  max_ocr_calls_per_page: 16
  max_vision_calls_per_candidate: 2
  max_total_estimated_cost_cny: 50
  budget_exceeded_result: blocked
```

```yaml
# .agent/harness/policy/failure-severity-policy.yaml
schema_version: failure-severity-policy/1
levels: [fatal, blocking, review_required, warning, informational]
formal_success_forbidden_when: [fatal, blocking]
review_required_must_be_resolved_before: reviewed_result
warning_requires_record: true
informational_affects_verdict: false
```

The seven JSON Schemas are Draft 2020-12, set `additionalProperties: false` on stable objects, and require the fields named in the user architecture. In particular:

- `p0-contracts.schema.json` requires all 12 Markdown columns, including `stable_p0_requirement`, `owner`, `current_status` and `implementation_reason`；mirror 不能丢掉业务文本再形成缩减版第二语义。
- `global-contract-bindings.schema.json` requires `global_contract_id` and sorted unique `primary_p0_contract_ids/related_business_p0_contract_ids/related_implementation_p0_contract_ids`.
- `run.schema.json` requires scope、executable-content/config/input identities、diagnostic Git revision、`contract_definition_hash`、start-time status projection hash and run timestamps. `code_identity` hashes executable/test/Harness/policy/schema/dependency content, not the commit object or status-only projection bytes.
- `contract-result.schema.json` requires contract ID, command, exit code, result state, timestamps and artifact refs.
- `receipt.schema.json` requires run ID, receipt scope, policy versions, `contract_definition_hash`, informational `status_projection_hash`, freshness, per-severity counts and overall verdict；task scope 不得把 overall verdict 解释为 formal P0 verdict。
- `current-four-manifest.schema.json` requires exactly four ordered unique basename/hash/opaque-ref entries and declared page metadata, makes the first checkpoint explicit, and forbids host source paths or embedded PDF bytes.
- `provider-fixture.schema.json` requires provider/adapter/schema versions, sanitized request/response refs and `contains_secret=false`.

- [ ] **Step 4: Implement deterministic generators, drift checking and the minimal task runner**

`generate-contract-mirror.py` parses only the P0 Markdown table, validates all referenced global IDs against the global matrix, emits all 12 columns as sorted canonical JSON to a same-directory temporary file, and atomically replaces `p0-contracts.json`. It calculates `contract_definition_hash` from all columns except `current_status`, and a separate `status_projection_hash`; `--check` compares generated bytes without writing.

`generate-global-bindings.py` reads only `p0-contracts.json`, emits separate sorted buckets for business primary、business related and implementation-only related IDs, and supports the same write/`--check` modes. Related buckets never count as direct enforcement. No script reads bindings to modify the Markdown source.

`Current Enforcement Stage=P0/P0-partial` 表示该 coarse global contract 属于当前 P0 enforcement boundary；primary binding 才表示某条 P0 requirement 的直接 enforcement。只有 typed-related binding 时，只能声明当前 P0 对该 global contract 提供支撑或边界证据，不能把它解释成整条长期 contract 已被直接、完整执行。`check-contracts.py` 对这类行检查可见性与 typed coverage，但 receipt 必须按 binding type 报告，不能把 related evidence 升格为 primary pass。

`check-contracts.py` performs, in order:

1. JSON Schema validation;
2. 111 P0 IDs / 111 unique;
3. 101 mapped business rows / 10 implementation-only / 0 unclassified;
4. valid global IDs and non-empty implementation reasons;
5. non-empty task, tier, selector, blocking level and current status;
6. exact Markdown ↔ mirror byte equality;
7. exact mirror → bindings equality;
8. no P1/P2 global row selected or related into a P0 task;
9. every `P0/P0-partial` global row has at least one primary or typed related binding, without collapsing relation types.

`run-p0.py fixture --scope task --task Dn-Tn` creates a new timestamp-plus-random-suffix run ID before invoking the selectors for that literal task. It writes `run.json` first, creates `logs/`, `reports/` and `artifacts/`, de-duplicates identical command selectors while still emitting one result per P0 ID, internally dispatches any `phase://` selector into the same open run, then writes `contract-results.json` and `receipt.json` and marks the run directory read-only. Fixture mode rejects any network-enabled Provider configuration. D1 only needs task selection and evidence collection; current-four/full-p0 orchestration is extended in D7, not generalized into a DAG.

Generate the two machine files, then run checks:

```bash
python .agent/harness/scripts/generate-contract-mirror.py
python .agent/harness/scripts/generate-global-bindings.py
python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_contract_architecture.py -q
```

Expected:

```text
global_contracts=69
p0_contracts=111
mapped=101
implementation_only=10
unclassified=0
duplicate=0
missing_task=0
missing_selector=0
mirror_drift=0
bindings_drift=0
unbound_p0_stage_global=0
binding_relation_conflict=0
definition_hash_stable_under_status_only_change=1
```

- [ ] **Step 5: Verify ignore rules and commit only the minimal Harness skeleton**

`.gitignore` must ignore `.agent/harness/runs/*` while retaining `.agent/harness/runs/.gitkeep`. It must not ignore `policy/contracts/schemas/fixtures/scripts/baselines`.

```bash
python .agent/harness/scripts/check-contracts.py
git check-ignore .agent/harness/runs/example/run.json
git check-ignore -v .agent/harness/contracts/p0-contracts.json && exit 1 || true
git diff --check
```

Expected: example run is ignored; contracts are tracked; checks pass.

```bash
git add .gitignore .agent/harness/README.md .agent/harness/policy .agent/harness/contracts .agent/harness/schemas .agent/harness/scripts/generate-contract-mirror.py .agent/harness/scripts/generate-global-bindings.py .agent/harness/scripts/check-contracts.py .agent/harness/scripts/run-p0.py .agent/harness/scripts/generate-receipt.py .agent/harness/fixtures/README.md .agent/harness/fixtures/manifests/README.md .agent/harness/fixtures/expected/README.md .agent/harness/runs/.gitkeep .agent/harness/baselines/README.md backend/tests/contract/harness/test_contract_architecture.py
git commit -m "test: establish minimal P0 contract harness"
```

### Task D1-T2: Scaffold The Five-Service Runtime And Shared Volume

**Files:**

- Create: `environment.yml`
- Create: `.env.example`
- Create: `backend/pyproject.toml`
- Create: `backend/Dockerfile`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/app/celery_app.py`
- Create: `frontend/package.json`
- Create: `frontend/Dockerfile`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `compose.yaml`
- Create: `Makefile`
- Test: `backend/tests/integration/test_runtime_topology.py`

- [ ] **Step 1: Write the failing topology test**

```python
# backend/tests/integration/test_runtime_topology.py
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class RuntimeTopologyTest(unittest.TestCase):
    def test_compose_has_exact_p0_services(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "config", "--services"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            set(result.stdout.split()),
            {"postgres", "redis", "api", "worker", "frontend"},
        )
        rendered = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "config"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("--concurrency=1", rendered)
        self.assertEqual(rendered.count("qi_storage:/data"), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the topology test and verify it fails**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
python3 -m unittest backend.tests.integration.test_runtime_topology -v
```

Expected: FAIL because `compose.yaml` does not exist.

- [ ] **Step 3: Add reproducible backend/frontend environments**

```yaml
# environment.yml
name: qi-p0
channels:
  - conda-forge
dependencies:
  - python=3.11
  - nodejs=22
  - pip
```

```toml
# backend/pyproject.toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "quality-inspection"
version = "0.1.0"
requires-python = ">=3.11,<3.12"
dependencies = [
  "alembic>=1.14,<2",
  "celery[redis]>=5.4,<6",
  "fastapi>=0.115,<1",
  "httpx>=0.28,<1",
  "jsonschema>=4.23,<5",
  "openai>=1.60,<3",
  "openpyxl>=3.1,<4",
  "pillow>=11,<13",
  "psycopg[binary]>=3.2,<4",
  "pydantic-settings>=2.7,<3",
  "pymupdf>=1.25,<2",
  "python-multipart>=0.0.20,<1",
  "redis>=5,<7",
  "sqlalchemy>=2.0,<3",
  "tencentcloud-sdk-python>=3,<4",
  "uvicorn[standard]>=0.34,<1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<10",
  "pytest-asyncio>=0.25,<1",
  "pytest-cov>=6,<8",
  "respx>=0.22,<1",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers"
```

```json
// frontend/package.json
{
  "name": "quality-inspection-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "tsc -b && vite build",
    "test": "vitest",
    "e2e": "playwright test"
  },
  "dependencies": {
    "pdfjs-dist": "^4.10.38",
    "react": "^19.1.0",
    "react-dom": "^19.1.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.53.0",
    "@testing-library/react": "^16.3.0",
    "@types/react": "^19.1.0",
    "@types/react-dom": "^19.1.0",
    "@vitejs/plugin-react": "^4.4.1",
    "jsdom": "^26.1.0",
    "typescript": "^5.8.3",
    "vite": "^6.1.0",
    "vitest": "^3.1.0"
  }
}
```

Run:

```bash
micromamba env create -f environment.yml -y
micromamba run -n qi-p0 python -m pip install -e 'backend[dev]'
micromamba run -n qi-p0 npm --prefix frontend install --package-lock-only
```

Expected: environment `qi-p0` exists; editable backend install succeeds; `frontend/package-lock.json` is generated.

- [ ] **Step 4: Add typed config, health app, worker and exact Compose topology**

```python
# backend/app/config.py
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QI_", extra="ignore")

    database_url: str = "postgresql+psycopg://qi:qi@postgres:5432/qi"
    redis_url: str = "redis://redis:6379/0"
    storage_root: Path = Path("/data")
    operator_header: str = "X-QI-Operator"
    tencent_secret_id: str | None = Field(default=None, repr=False)
    tencent_secret_key: str | None = Field(default=None, repr=False)
    tencent_region: str = "ap-guangzhou"
    qwen_api_key: str | None = Field(default=None, repr=False)
    qwen_workspace_id: str | None = None
    qwen_model: str = "qwen3-vl-plus"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# backend/app/main.py
from fastapi import FastAPI


app = FastAPI(title="Quality Inspection", version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app_name": "quality-inspection"}
```

```python
# backend/app/celery_app.py
from celery import Celery

from app.config import get_settings


settings = get_settings()
celery_app = Celery("quality_inspection", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)
```

```yaml
# compose.yaml
name: quality-inspection
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: qi
      POSTGRES_USER: qi
      POSTGRES_PASSWORD: qi
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qi -d qi"]
      interval: 2s
      timeout: 2s
      retries: 30
    volumes:
      - qi_postgres:/var/lib/postgresql/data
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "no"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 2s
      retries: 30
  api:
    build: ./backend
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    env_file:
      - path: .env
        required: false
    environment:
      QI_STORAGE_ROOT: /data
    ports:
      - "8000:8000"
    volumes:
      - qi_storage:/data
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
  worker:
    build: ./backend
    command: ["celery", "-A", "app.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]
    env_file:
      - path: .env
        required: false
    environment:
      QI_STORAGE_ROOT: /data
    volumes:
      - qi_storage:/data
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - api
volumes:
  qi_postgres:
    name: quality_inspection_postgres_dev
  qi_storage:
    name: quality_inspection_storage_dev
```

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# frontend/Dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--port", "3000"]
```

```html
<!-- frontend/index.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Quality Inspection</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// frontend/src/main.tsx
import React from "react";
import { createRoot } from "react-dom/client";


function App() {
  return <main><h1>Quality Inspection</h1></main>;
}


const root = document.getElementById("root");
if (!root) throw new Error("missing #root");
createRoot(root).render(<App />);
```

```makefile
# Makefile
.PHONY: check-contracts test-backend test-frontend verify-p0-offline verify-p0-live

check-contracts:
	python .agent/harness/scripts/check-contracts.py

test-backend:
	micromamba run -n qi-p0 pytest backend/tests -q

test-frontend:
	micromamba run -n qi-p0 npm --prefix frontend test -- --run

verify-p0-offline: check-contracts
	micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture

verify-p0-live: check-contracts
	micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py live --scope full-p0 --input-set current-four
```

`.env.example` must contain only these non-secret examples and blank secret keys:

```dotenv
QI_DATABASE_URL=postgresql+psycopg://qi:qi@postgres:5432/qi
QI_REDIS_URL=redis://redis:6379/0
QI_STORAGE_ROOT=/data
QI_TENCENT_SECRET_ID=
QI_TENCENT_SECRET_KEY=
QI_TENCENT_REGION=ap-guangzhou
QI_QWEN_API_KEY=
QI_QWEN_WORKSPACE_ID=
QI_QWEN_MODEL=qwen3-vl-plus
```

- [ ] **Step 5: Run static/runtime smoke and commit**

Run:

```bash
docker compose config --quiet
micromamba run -n qi-p0 pytest backend/tests/integration/test_runtime_topology.py -q
docker compose up -d --build postgres redis api worker frontend
curl --fail --silent http://localhost:8000/api/v1/health
```

Expected: topology test PASS; health returns `{"status":"ok","app_name":"quality-inspection"}`.

Commit:

```bash
git add environment.yml .env.example backend/pyproject.toml backend/Dockerfile backend/app/__init__.py backend/app/config.py backend/app/main.py backend/app/celery_app.py frontend/package.json frontend/package-lock.json frontend/Dockerfile frontend/index.html frontend/src/main.tsx compose.yaml Makefile
git commit -m "build: scaffold P0 runtime spine"
```

### Task D1-T3: Add Core Persistence, Atomic Storage, Audit And Idempotency

**Files:**

- Create: `backend/app/db.py`
- Create: `backend/app/projects/models.py`
- Create: `backend/app/projects/state.py`
- Create: `backend/app/storage/models.py`
- Create: `backend/app/storage/local.py`
- Create: `backend/app/audit/operations.py`
- Create: `backend/app/jobs/idempotency.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Generate: `backend/alembic/versions/0001_core.py`
- Test: `backend/tests/unit/storage/test_local.py`
- Test: `backend/tests/integration/test_storage.py`
- Test: `backend/tests/integration/test_schema.py`
- Test: `backend/tests/integration/test_operator_audit.py`
- Test: `backend/tests/integration/test_task_idempotency.py`

- [ ] **Step 1: Write failing storage and duplicate-job tests**

```python
# backend/tests/unit/storage/test_local.py
from hashlib import sha256

import pytest

from app.storage.local import HashMismatch, LocalFileStorage


def test_atomic_write_publishes_verified_bytes(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    payload = b"engineering-pdf"
    stored = storage.write_verified("projects/p1/source.pdf", payload, sha256(payload).hexdigest())
    assert stored.path.read_bytes() == payload
    assert stored.size_bytes == len(payload)
    assert not list(tmp_path.rglob("*.tmp"))


def test_hash_or_size_mismatch_rejects_publish(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(HashMismatch):
        storage.write_verified("projects/p1/source.pdf", b"bad", "0" * 64)
    assert not (tmp_path / "projects/p1/source.pdf").exists()
```

```python
# backend/tests/integration/test_storage.py
import json
import subprocess

from app.storage.models import StoredFile


def _storage_volume(service: dict) -> str:
    return next(mount["source"] for mount in service["volumes"] if mount["target"] == "/data")


def test_api_and_worker_share_storage_root() -> None:
    rendered = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(rendered.stdout)["services"]
    assert _storage_volume(services["api"]) == _storage_volume(services["worker"])


def test_database_persists_only_file_metadata() -> None:
    columns = {column.name for column in StoredFile.__table__.columns}
    assert {"resource_ref", "sha256", "size_bytes", "mime_type", "created_at"} <= columns
    assert "path" not in columns
```

```python
# backend/tests/integration/test_task_idempotency.py
from app.jobs.idempotency import claim_logical_job


def test_duplicate_delivery_returns_the_same_job(db_session) -> None:
    first = claim_logical_job(db_session, project_id="p1", logical_task_key="process:sha256")
    second = claim_logical_job(db_session, project_id="p1", logical_task_key="process:sha256")
    assert second.id == first.id
```

- [ ] **Step 2: Run focused tests and verify missing modules**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/storage/test_local.py backend/tests/integration/test_storage.py backend/tests/integration/test_task_idempotency.py -q
```

Expected: collection FAIL for missing `app.storage.local` and `app.jobs.idempotency`.

- [ ] **Step 3: Implement the DB base, atomic storage and minimal core models**

```python
# backend/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
```

```python
# backend/app/storage/local.py
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class HashMismatch(ValueError):
    pass


@dataclass(frozen=True)
class StoredWrite:
    resource_ref: str
    path: Path
    sha256: str
    size_bytes: int


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_verified(self, relative_path: str, content: bytes, expected_sha256: str) -> StoredWrite:
        target = (self.root / relative_path).resolve()
        if self.root not in target.parents:
            raise ValueError("resource path escapes storage root")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_sha256:
            raise HashMismatch(f"expected {expected_sha256}, got {digest}")
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if temp.stat().st_size != len(content):
                raise HashMismatch("stored byte count changed")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return StoredWrite(
            resource_ref=f"asset://{relative_path}",
            path=target,
            sha256=digest,
            size_bytes=len(content),
        )
```

Core SQLAlchemy models must use these exact uniqueness boundaries:

```python
# backend/app/jobs/idempotency.py
from __future__ import annotations

import uuid

from sqlalchemy import String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base


class LogicalJob(Base):
    __tablename__ = "logical_jobs"
    __table_args__ = (UniqueConstraint("project_id", "logical_task_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_task_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)


def claim_logical_job(session: Session, *, project_id: str, logical_task_key: str) -> LogicalJob:
    existing = session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == project_id,
            LogicalJob.logical_task_key == logical_task_key,
        )
    )
    if existing is not None:
        return existing
    job = LogicalJob(project_id=project_id, logical_task_key=logical_task_key)
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return session.scalar(
            select(LogicalJob).where(
                LogicalJob.project_id == project_id,
                LogicalJob.logical_task_key == logical_task_key,
            )
        )
    return job
```

`Project`, `StoredFile` and `OperationRecord` use these complete declarations; no RBAC/user tables:

```python
# backend/app/projects/models.py
import uuid

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(32), default="processing", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
```

```python
# backend/app/storage/models.py
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StoredFile(Base):
    __tablename__ = "stored_files"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_ref: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# backend/app/audit/operations.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OperationRecord(Base):
    __tablename__ = "operation_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    command: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    before_version: Mapped[int] = mapped_column(Integer, nullable=False)
    after_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Generate and apply migration, then run storage/schema/audit/idempotency tests**

```bash
docker compose up -d postgres redis
micromamba run -n qi-p0 alembic -c backend/alembic.ini revision --autogenerate -m core --rev-id 0001
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest \
  backend/tests/unit/storage/test_local.py \
  backend/tests/integration/test_storage.py \
  backend/tests/integration/test_schema.py \
  backend/tests/integration/test_operator_audit.py \
  backend/tests/integration/test_task_idempotency.py -q
```

Expected: migration creates only `projects/stored_files/operation_records/logical_jobs` plus Alembic version; all tests PASS.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add backend/app/db.py backend/app/projects/models.py backend/app/projects/state.py backend/app/storage/models.py backend/app/storage/local.py backend/app/audit/operations.py backend/app/jobs/idempotency.py backend/alembic.ini backend/alembic/env.py backend/alembic/versions/0001_core.py backend/tests/unit/storage/test_local.py backend/tests/integration/test_storage.py backend/tests/integration/test_schema.py backend/tests/integration/test_operator_audit.py backend/tests/integration/test_task_idempotency.py
git commit -m "feat: add atomic storage and core persistence"
```

## Day 2 — Page Inventory And Provider Boundaries

### Task D2-T1: Freeze Current-Four Inputs And Build Coordinate-Safe Page Inventory

**Files:**

- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Create: `.agent/harness/scripts/stage-current-four.py`
- Create: `backend/app/pdf/__init__.py`
- Create: `backend/app/pdf/schemas.py`
- Create: `backend/app/pdf/coordinates.py`
- Create: `backend/app/pdf/classification.py`
- Create: `backend/app/pdf/inventory.py`
- Modify after sealed run: `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md` (`D2-T1` status cells only)
- Generate: `.agent/harness/contracts/p0-contracts.json`
- Generate/check: `.agent/harness/contracts/global-contract-bindings.json`
- Test: `backend/tests/contract/harness/test_contract_architecture.py`
- Test: `backend/tests/unit/pdf/test_coordinates.py`
- Test: `backend/tests/unit/pdf/test_classification.py`
- Test: `backend/tests/unit/pdf/test_inventory.py`
- Test: `backend/tests/integration/test_pdf_inventory.py`

- [ ] **Step 1: Write failing coordinate, routing, inventory and Harness input-artifact tests**

```python
# backend/tests/unit/pdf/test_coordinates.py
import pytest

from app.pdf.coordinates import PageTransform


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_render_round_trip_error_budget(rotation: int) -> None:
    transform = PageTransform(width=1190.55, height=841.89, rotation=rotation, scale=2.0)
    source = (23.25, 51.5)
    render = transform.pdf_to_render_point(source)
    restored = transform.render_to_pdf_point(render)
    assert restored == pytest.approx(source, abs=0.5)
```

```python
# backend/tests/unit/pdf/test_classification.py
from app.pdf.classification import PageSignals, classify_page


def test_vector_hybrid_and_scanned_routing() -> None:
    assert classify_page(PageSignals(900, 20, 0.0, 400)).page_type == "vector"
    assert classify_page(PageSignals(900, 20, 0.95, 400)).page_type == "hybrid"
    assert classify_page(PageSignals(0, 0, 1.0, 0)).page_type == "scanned"
```

- [ ] **Step 2: Run tests and verify missing PDF modules**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_coordinates.py backend/tests/unit/pdf/test_classification.py -q
```

Expand this red command to include `backend/tests/unit/pdf/test_inventory.py`, `backend/tests/integration/test_pdf_inventory.py` and the focused new Harness artifact/input-identity cases in `test_contract_architecture.py`. The tests must cover clipped CropBox coordinates、PDF/render round trip、`vector/hybrid/scanned/ambiguous` routing、scanned unsupported status、serializable evidence、span/line raw+normalized text、0-based page order、rotated direction and native/OCR non-overwrite. Expected: collection FAIL for missing `app.pdf.coordinates` / `classification` / `inventory`, while pre-existing Harness tests remain green.

- [ ] **Step 3: Implement stable schemas, transforms, classification and native inventory**

```python
# backend/app/pdf/coordinates.py
from dataclasses import dataclass


Point = tuple[float, float]
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class PageTransform:
    width: float
    height: float
    rotation: int
    scale: float

    def __post_init__(self) -> None:
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("rotation must be 0, 90, 180 or 270")
        if self.width <= 0 or self.height <= 0 or self.scale <= 0:
            raise ValueError("page dimensions and scale must be positive")

    def pdf_to_render_point(self, point: Point) -> Point:
        x, y = point
        if self.rotation == 0:
            rx, ry = x, y
        elif self.rotation == 90:
            rx, ry = self.height - y, x
        elif self.rotation == 180:
            rx, ry = self.width - x, self.height - y
        else:
            rx, ry = y, self.width - x
        return rx * self.scale, ry * self.scale

    def render_to_pdf_point(self, point: Point) -> Point:
        rx, ry = point[0] / self.scale, point[1] / self.scale
        if self.rotation == 0:
            return rx, ry
        if self.rotation == 90:
            return ry, self.height - rx
        if self.rotation == 180:
            return self.width - rx, self.height - ry
        return self.width - ry, rx

    def clip_bbox(self, bbox: BBox) -> BBox:
        x0, y0, x1, y1 = bbox
        clipped = (
            max(0.0, min(x0, self.width)),
            max(0.0, min(y0, self.height)),
            max(0.0, min(x1, self.width)),
            max(0.0, min(y1, self.height)),
        )
        if clipped[0] > clipped[2] or clipped[1] > clipped[3]:
            raise ValueError("bbox has inverted bounds")
        return clipped

    @property
    def pdf_to_render_matrix(self) -> tuple[float, float, float, float, float, float]:
        s, w, h = self.scale, self.width, self.height
        return {
            0: (s, 0.0, 0.0, s, 0.0, 0.0),
            90: (0.0, s, -s, 0.0, h * s, 0.0),
            180: (-s, 0.0, 0.0, -s, w * s, h * s),
            270: (0.0, -s, s, 0.0, 0.0, w * s),
        }[self.rotation]

    @property
    def render_to_pdf_matrix(self) -> tuple[float, float, float, float, float, float]:
        inverse = 1.0 / self.scale
        return {
            0: (inverse, 0.0, 0.0, inverse, 0.0, 0.0),
            90: (0.0, -inverse, inverse, 0.0, 0.0, self.height),
            180: (-inverse, 0.0, 0.0, -inverse, self.width, self.height),
            270: (0.0, inverse, -inverse, 0.0, self.width, 0.0),
        }[self.rotation]
```

```python
# backend/app/pdf/classification.py
from dataclasses import dataclass


@dataclass(frozen=True)
class PageSignals:
    native_char_count: int
    native_span_count: int
    max_image_coverage: float
    vector_drawing_count: int


@dataclass(frozen=True)
class Classification:
    page_type: str
    confidence: float
    evidence: dict[str, float | int]
    rule_version: str = "v0.1"


def classify_page(signals: PageSignals) -> Classification:
    if signals.native_char_count >= 20 and signals.max_image_coverage >= 0.8:
        page_type, confidence = "hybrid", 0.9
    elif signals.native_char_count >= 20 and (signals.vector_drawing_count > 0 or signals.max_image_coverage < 0.8):
        page_type, confidence = "vector", 0.9
    elif signals.native_char_count < 20 and signals.max_image_coverage >= 0.8:
        page_type, confidence = "scanned", 0.95
    else:
        page_type, confidence = "ambiguous", 0.5
    return Classification(page_type, confidence, signals.__dict__)
```

```python
# backend/app/pdf/schemas.py
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TextObservation:
    observation_id: str
    source_type: str
    raw_text: str
    normalized_text: str
    page_index: int
    bbox_pdf: tuple[float, float, float, float]
    direction: tuple[float, float]
    confidence: float | None
    parent_region_id: str | None = None


@dataclass(frozen=True)
class PageInventory:
    page_index: int
    width: float
    height: float
    rotation: int
    page_type: str
    classification_evidence: dict[str, float | int]
    pdf_to_render_matrix: tuple[float, ...]
    render_to_pdf_matrix: tuple[float, ...]
    observations: tuple[TextObservation, ...]

    def to_dict(self) -> dict:
        return asdict(self)
```

```python
# backend/app/pdf/inventory.py
from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

import pymupdf

from app.pdf.classification import PageSignals, classify_page
from app.pdf.coordinates import PageTransform
from app.pdf.schemas import PageInventory, TextObservation


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def build_inventory(pdf_path: Path, render_scale: float = 2.0) -> tuple[PageInventory, ...]:
    document = pymupdf.open(pdf_path)
    pages: list[PageInventory] = []
    for page_index, page in enumerate(document):
        crop = page.cropbox
        transform = PageTransform(crop.width, crop.height, page.rotation, render_scale)
        text_dict = page.get_text("dict", sort=False)
        observations: list[TextObservation] = []
        span_count = 0
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line_index, line in enumerate(block.get("lines", [])):
                direction = tuple(line.get("dir", (1.0, 0.0)))
                for span_index, span in enumerate(line.get("spans", [])):
                    raw = span.get("text", "")
                    if not raw.strip():
                        continue
                    bbox = transform.clip_bbox(tuple(float(value) for value in span["bbox"]))
                    seed = f"{page_index}:{line_index}:{span_index}:{raw}:{bbox}".encode()
                    observations.append(
                        TextObservation(
                            observation_id=hashlib.sha256(seed).hexdigest()[:24],
                            source_type="native",
                            raw_text=raw,
                            normalized_text=_normalize(raw),
                            page_index=page_index,
                            bbox_pdf=bbox,
                            direction=(float(direction[0]), float(direction[1])),
                            confidence=None,
                        )
                    )
                    span_count += 1
        image_coverage = max(
            (rect.width * rect.height / (crop.width * crop.height) for image in page.get_images(full=True) for rect in page.get_image_rects(image)),
            default=0.0,
        )
        signals = PageSignals(sum(len(item.raw_text) for item in observations), span_count, image_coverage, len(page.get_drawings()))
        classification = classify_page(signals)
        pages.append(
            PageInventory(
                page_index=page_index,
                width=crop.width,
                height=crop.height,
                rotation=page.rotation,
                page_type=classification.page_type,
                classification_evidence=classification.evidence,
                pdf_to_render_matrix=transform.pdf_to_render_matrix,
                render_to_pdf_matrix=transform.render_to_pdf_matrix,
                observations=tuple(observations),
            )
        )
    return tuple(pages)
```

The implementation must normalize non-zero CropBox offsets before clipping, preserve `bbox_normalized`, keep both line- and span-level native records, serialize direction vector plus angle, and keep `source_type=native` records immutable when later OCR observations are appended. `scanned` is represented as unsupported routing and `ambiguous` follows hybrid processing with `review_required`; neither may masquerade as a supported vector result.

- [ ] **Step 4: Implement the private current-four staging command and pre-seal hook**

`.agent/harness/scripts/stage-current-four.py` is a live-only identity registrar. It accepts four repeated `--source` arguments or one `--source-root`, resolves exactly the frozen basenames from the P0 traceability matrix, reads the sources in place, validates SHA-256/size/page metadata, and writes only basename、opaque `external-input://sha256/...` ref、identity、page facts and ordered first-checkpoint metadata to `artifacts/current-four-manifest.json` in a new run. It never records the host source path, copies PDF bytes into `.agent/harness/runs/`, writes a reusable manifest, or overwrites a mutable receipt pointer. Actual upload later passes the original bytes through application FileStorage outside the repository checkout.

The actual D1 runner seals immediately, so this task adds one narrow `run_task(..., input_artifacts=...)` hook. The hook accepts only validated relative artifact names, writes the supplied bytes before selector execution, includes `artifacts/current-four-manifest.json` in `input_identity`, and seals it with the normal task run. The CLI adds only `--current-four-run <literal-registration-run-id>` for later D2-T1 refreshes: it rejects `latest` aliases, loads the schema-valid manifest from that sealed registration run, copies those bytes into the new run before selectors, and never reopens host PDF paths. `generate-receipt.py --check-run <literal-run-id>` must recompute that identity from the new run's sealed artifact. No generic artifact DAG, mutable pointer or alternate run layout is introduced. Do not execute registration until Step 5 focused tests and contract sync have passed.

- [ ] **Step 5: Run focused tests, close the task Harness, review and commit**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/pdf backend/tests/integration/test_pdf_inventory.py -q
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_contract_architecture.py -q
micromamba run -n qi-p0 python .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 python .agent/harness/scripts/stage-current-four.py --mode live --source-root "$QI_CURRENT_FOUR_SOURCE_ROOT"
git status --short .agent/harness/runs
```

`QI_CURRENT_FOUR_SOURCE_ROOT` is injected only into the execution shell from the already verified external source location. Its value is not written to the repository, selector log, run metadata, manifest or receipt.

Expected: focused tests pass first; registration then reports `registered=4 pages=6 hashes=verified first_checkpoint=58b9cf08...` plus one non-empty generated run ID and a passed D2-T1 live task receipt. The immutable run contains the manifest but no PDF bytes or host paths, and no second initial D2-T1 task phase is created. Copy this exact registration/task run ID. Change only the nine `D2-T1` `current_status` cells from `not_run` to the sealed results, regenerate mirror/bindings, rerun `check-contracts.py`, then run:

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/generate-receipt.py --check-run <literal-registration-run-id>
```

Expected: `receipt_valid=1 scope=task overall_verdict=passed`; Git shows no run artifact other than the tracked `.gitkeep` convention. Complete focused read-only review before staging; any executable/test fix invalidates the run and requires repeating this closure.

```bash
git add .agent/harness/scripts/run-p0.py .agent/harness/scripts/generate-receipt.py .agent/harness/scripts/stage-current-four.py .agent/harness/contracts/p0-contracts.json .agent/harness/contracts/global-contract-bindings.json docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md backend/app/pdf backend/tests/contract/harness/test_contract_architecture.py backend/tests/unit/pdf backend/tests/integration/test_pdf_inventory.py
git commit -m "feat: add coordinate-safe PDF inventory"
```

### Task D2-T2: Implement Narrow OCR And Vision Provider Adapters

**Files:**

- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/tencent_ocr.py`
- Create: `backend/app/providers/qwen_vl.py`
- Create: `backend/app/providers/call_records.py`
- Create: `backend/app/providers/candidate_review.schema.json`
- Modify: `.agent/harness/schemas/provider-fixture.schema.json`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Create: `.agent/harness/fixtures/providers/tencent-ocr/general-accurate-v1.json`
- Create: `.agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json`
- Create: `.agent/harness/scripts/run-provider-contracts.py`
- Modify after sealed run: `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md` (`D2-T2` status cells only)
- Generate: `.agent/harness/contracts/p0-contracts.json`
- Generate/check: `.agent/harness/contracts/global-contract-bindings.json`
- Test: `backend/tests/contract/harness/test_contract_architecture.py`
- Create: `backend/tests/contract/conftest.py`
- Test: `backend/tests/contract/test_tencent_ocr_provider.py`
- Test: `backend/tests/contract/test_qwen_vl_provider.py`
- Test: `backend/tests/contract/test_provider_call_records.py`

- [ ] **Step 1: Write failing normalized-provider contract tests**

```python
# backend/tests/contract/test_tencent_ocr_provider.py
from app.providers.tencent_ocr import normalize_response


def test_normalizes_text_polygon_angle_and_request_id(tencent_fixture) -> None:
    result = normalize_response(tencent_fixture)
    assert result.request_id == "fixture-request-id"
    assert result.observations[0].raw_text == "M6深10"
    assert result.observations[0].confidence == 97.5
    assert result.observations[0].polygon
```

```python
# backend/tests/contract/test_qwen_vl_provider.py
import pytest

from app.providers.qwen_vl import CandidateSchemaError, parse_candidate_json


def test_rejects_json_that_does_not_match_frozen_schema() -> None:
    with pytest.raises(CandidateSchemaError):
        parse_candidate_json('{"item_type":"thread"}')
```

- [ ] **Step 2: Run and verify both provider modules are missing**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_tencent_ocr_provider.py backend/tests/contract/test_qwen_vl_provider.py -q
```

Include `backend/tests/contract/test_provider_call_records.py` in the red run. Add a valid Qwen schema case、exact Tencent/Qwen request-shape assertions、a fixture-mode network tripwire and a redacted FileStorage round trip. Expected: collection FAIL for missing provider modules/call-record implementation; no test may attempt network access.

- [ ] **Step 3: Define provider ports and implement official request shapes**

```python
# backend/app/providers/base.py
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OcrObservation:
    raw_text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    angle: float


@dataclass(frozen=True)
class OcrResult:
    request_id: str
    observations: tuple[OcrObservation, ...]


@dataclass(frozen=True)
class VisionResult:
    request_id: str
    payload: dict
    usage: dict[str, int]


class OcrProvider(Protocol):
    def recognize_png(self, image: bytes) -> OcrResult: ...


class VisionLlmProvider(Protocol):
    def review_candidate(self, image: bytes, prompt: str) -> VisionResult: ...
```

`TencentOcrProvider` must use `GeneralAccurateOCRRequest` with this exact payload, confirmed against the official API:

```python
request.from_json_string(
    json.dumps(
        {
            "ImageBase64": base64.b64encode(image).decode("ascii"),
            "ConfigID": "OCR",
            "WordsType": "2",
            "IsWords": False,
            "EnableDetectSplit": True,
        }
    )
)
```

`QwenVisionProvider` must call the Beijing OpenAI-compatible endpoint with explicit non-thinking JSON output:

```python
completion = client.chat.completions.create(
    model="qwen3-vl-plus",
    messages=[
        {"role": "system", "content": "Review one engineering annotation crop. Output JSON only."},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt + "\nOutput in JSON format."},
            ],
        },
    ],
    response_format={"type": "json_object"},
    extra_body={"enable_thinking": False},
)
```

`parse_candidate_json()` must run `json.loads()` and `jsonschema.validate()` against `candidate_review.schema.json`; invalid JSON/schema raises `CandidateSchemaError` and never returns a candidate.

- [ ] **Step 4: Persist only redacted call metadata and run provider tests**

`ProviderCallRecord` must persist only `provider/request_id/model/prompt_version/schema_version/duration_ms/retry_count/input_image_count/estimated_cost/logical_task_reused/request_ref/response_ref`; its serializer must reject keys matching `authorization|api[_-]?key|secret|base64` case-insensitively. `logical_task_reused` only records idempotent reuse of the same job key; it does not create a cross-run Provider cache.

The D1 `provider-fixture.schema.json` is metadata-only. Extend that single schema with one required sanitized `payload` object while preserving `additionalProperties=false`; `run-provider-contracts.py` must recursively reject secret-bearing keys and full base64-like payloads before tests consume `fixture["payload"]`. It owns only fixture schema/network-call gating and must not create a second receipt or selector runner. Add the two Provider fixture files to D2-T2 fixture-mode `input_identity`, so changing their bytes makes an old D2-T2 receipt stale. The call-record persistence helper writes only the redacted JSON record through `LocalFileStorage`; raw SDK bodies remain fixture/diagnostic input and are not copied into the record.

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_tencent_ocr_provider.py backend/tests/contract/test_qwen_vl_provider.py backend/tests/contract/test_provider_call_records.py -q
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_contract_architecture.py -q
micromamba run -n qi-p0 python .agent/harness/scripts/run-provider-contracts.py fixture --task D2-T2
micromamba run -n qi-p0 python .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T2
```

Expected: all fixture tests and the D2-T2 receipt PASS; Provider call count is zero; fixture JSON passes `provider-fixture.schema.json` and contains no secret-bearing keys. Copy the exact printed run ID, change only the four `D2-T2` `current_status` cells from `not_run` to the sealed results, regenerate mirror/bindings, rerun `check-contracts.py`, and validate:

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/generate-receipt.py --check-run <literal-D2-T2-run-id>
```

Expected: `receipt_valid=1 scope=task overall_verdict=passed`. Complete focused read-only review; repeat the closure after any executable/test/fixture/schema fix.

- [ ] **Step 5: Commit Provider boundaries and fixtures**

```bash
git add backend/app/providers .agent/harness/schemas/provider-fixture.schema.json .agent/harness/fixtures/providers .agent/harness/scripts/generate-receipt.py .agent/harness/scripts/run-provider-contracts.py .agent/harness/contracts/p0-contracts.json .agent/harness/contracts/global-contract-bindings.json docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md backend/tests/contract/harness/test_contract_architecture.py backend/tests/contract/conftest.py backend/tests/contract/test_tencent_ocr_provider.py backend/tests/contract/test_qwen_vl_provider.py backend/tests/contract/test_provider_call_records.py
git commit -m "feat: add OCR and vision provider contracts"
```

### Task D2-T3: Add Capability Preflight, State Errors And Idempotent Inventory Job

**Files:**

- Create: `backend/app/capabilities/service.py`
- Create: `backend/app/processing/pipeline.py`
- Create: `backend/app/processing/tasks.py`
- Create: `backend/app/errors/models.py`
- Modify: `backend/app/projects/state.py`
- Modify: `backend/app/jobs/idempotency.py`
- Modify: `backend/app/storage/local.py`
- Modify: `backend/app/celery_app.py`
- Modify: `backend/alembic/env.py`
- Generate: `backend/alembic/versions/0002_processing.py`
- Modify after sealed run: `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md` (`D2-T3` status cells only)
- Generate: `.agent/harness/contracts/p0-contracts.json`
- Generate/check: `.agent/harness/contracts/global-contract-bindings.json`
- Test: `backend/tests/integration/test_processing_preflight.py`
- Test: `backend/tests/integration/test_processing_state.py`
- Test: `backend/tests/integration/test_task_idempotency.py`
- Test: `backend/tests/integration/test_error_records.py`
- Test: `backend/tests/integration/test_schema.py`
- Test: `backend/tests/unit/storage/test_local.py`

- [ ] **Step 1: Write failing preflight and state-transition tests**

```python
# backend/tests/integration/test_processing_preflight.py
import pytest

from app.capabilities.service import CapabilityUnavailable, ProcessingPreflight


def test_missing_qwen_config_blocks_new_processing(storage, redis_client) -> None:
    preflight = ProcessingPreflight(storage, redis_client, ocr_configured=True, vision_configured=False)
    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()
    assert error.value.code == "vision_provider_unavailable"
```

```python
# backend/tests/integration/test_processing_state.py
import pytest

from app.projects.state import InvalidTransition, ProjectState, transition


def test_blocking_error_cannot_transition_to_ready_or_success() -> None:
    with pytest.raises(InvalidTransition):
        transition(ProjectState.PROCESSING_FAILED, ProjectState.READY_FOR_EDIT)
```

- [ ] **Step 2: Run and verify capability/state implementations are absent**

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_processing_preflight.py backend/tests/integration/test_processing_state.py -q
```

Include `test_task_idempotency.py`, `test_error_records.py`, the new D2 schema assertion and focused `LocalFileStorage` read/delete/probe tests in the red run. Expected: collection FAIL for missing `app.capabilities.service` / processing/error models and failing assertions for the absent successful result ref / D2 schema.

- [ ] **Step 3: Implement fail-closed preflight and explicit state graph**

```python
# backend/app/projects/state.py
from enum import StrEnum


class ProjectState(StrEnum):
    PROCESSING = "processing"
    READY_FOR_EDIT = "ready_for_edit"
    EDITING = "editing"
    REVIEWED = "reviewed"
    EXPORTING = "exporting"
    EXPORT_SUCCEEDED = "export_succeeded"
    PROCESSING_FAILED = "processing_failed"
    EXPORT_FAILED = "export_failed"
    UNSUPPORTED_INPUT = "unsupported_input"


ALLOWED = {
    ProjectState.PROCESSING: {ProjectState.READY_FOR_EDIT, ProjectState.PROCESSING_FAILED, ProjectState.UNSUPPORTED_INPUT},
    ProjectState.READY_FOR_EDIT: {ProjectState.EDITING},
    ProjectState.EDITING: {ProjectState.REVIEWED},
    ProjectState.REVIEWED: {ProjectState.EXPORTING},
    ProjectState.EXPORTING: {ProjectState.EXPORT_SUCCEEDED, ProjectState.EXPORT_FAILED},
    ProjectState.EXPORT_FAILED: {ProjectState.EXPORTING},
}


class InvalidTransition(ValueError):
    pass


def transition(current: ProjectState, target: ProjectState) -> ProjectState:
    if target not in ALLOWED.get(current, set()):
        raise InvalidTransition(f"{current} -> {target} is not allowed")
    return target
```

`ProcessingPreflight.check()` must perform, in order: write/read/delete a probe below the configured FileStorage root; `redis.ping()`; `celery_app.control.inspect(timeout=1).ping()` containing at least one worker; non-empty OCR config; non-empty vision config. It raises `CapabilityUnavailable(code, detail)` at the first failed capability and must not call either paid Provider.

- [ ] **Step 4: Implement and test the idempotent inventory task**

`inventory_project(project_id, source_ref, logical_task_key)` must:

1. call `claim_logical_job`;
2. return the existing successful inventory reference on duplicate delivery;
3. run preflight before reading the PDF;
4. persist page inventory and structured errors;
5. keep project state `processing` until Day 3 candidate/coverage closes the automatic result;
6. mark unsupported scanned input as `unsupported_input`, not `processing_failed`.

The actual D1 `LogicalJob` has only `id/project_id/logical_task_key/status`; add a nullable `result_ref` and a compare-safe success update so duplicate completed delivery returns that exact ref without rebuilding inventory. The actual D1 `LocalFileStorage` only writes; add minimal root-confined `resolve_resource_ref`、`read_bytes`、`delete` and non-persistent `probe` methods, and use those methods rather than rebuilding storage path rules in processing. `ErrorRecord` stores the stable `project_id/code/message/severity/stage/location_ref/cause_category` envelope. `0002_processing.py` adds structured error persistence plus `logical_jobs.result_ref`; `backend/alembic/env.py` must register the D2 model and `test_schema.py` must assert the exact post-0002 table/column set. `celery_app` must explicitly include `app.processing.tasks`; merely creating the module is insufficient. No general artifact lifecycle or retry-attempt model is added.

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest backend/tests/integration/test_processing_preflight.py backend/tests/integration/test_processing_state.py backend/tests/integration/test_task_idempotency.py backend/tests/integration/test_error_records.py -q
```

Expected: all tests PASS; duplicate delivery count remains one and returns the same successful inventory ref; preflight probe leaves no file; unsupported and failure states remain distinct; no live Provider calls occur.

- [ ] **Step 5: Close D2-T3 Harness, refresh final Day 2 receipts, review and commit**

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/generate-contract-mirror.py
micromamba run -n qi-p0 python .agent/harness/scripts/generate-global-bindings.py
micromamba run -n qi-p0 python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T3
```

Expected: D2-T3 task receipt PASS. Copy the exact printed run ID, change only the four `D2-T3` `current_status` cells from `not_run` to the sealed results, regenerate mirror/bindings, rerun `check-contracts.py`, then validate `generate-receipt.py --check-run <literal-D2-T3-run-id>`. Complete independent focused review; any fix requires rerunning the affected tests and D2-T3 closure.

When executable/test content is stable after review, refresh all three task receipts on the same final content identity:

```bash
micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T1 --current-four-run <literal-registration-run-id>
micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T2
micromamba run -n qi-p0 python .agent/harness/scripts/run-p0.py fixture --scope task --task D2-T3
micromamba run -n qi-p0 python .agent/harness/scripts/generate-receipt.py --check-run <literal-final-D2-T1-run-id>
micromamba run -n qi-p0 python .agent/harness/scripts/generate-receipt.py --check-run <literal-final-D2-T2-run-id>
micromamba run -n qi-p0 python .agent/harness/scripts/generate-receipt.py --check-run <literal-final-D2-T3-run-id>
```

Expected: all three final receipts are `fresh`, `receipt_valid=1`, task-scoped and `overall_verdict=passed`; final D2-T1 input identity includes the copied current-four manifest; Provider fixture mode reports no external calls. These literal IDs, not earlier stale closure runs or a mutable pointer, are the three Day 2 IDs reported at handoff.

```bash
git add backend/app/capabilities backend/app/processing backend/app/errors backend/app/projects/state.py backend/app/jobs/idempotency.py backend/app/storage/local.py backend/app/celery_app.py backend/alembic/env.py backend/alembic/versions/0002_processing.py backend/tests/integration/test_processing_preflight.py backend/tests/integration/test_processing_state.py backend/tests/integration/test_task_idempotency.py backend/tests/integration/test_error_records.py backend/tests/integration/test_schema.py backend/tests/unit/storage/test_local.py .agent/harness/contracts/p0-contracts.json .agent/harness/contracts/global-contract-bindings.json docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md
git commit -m "feat: add idempotent processing preflight"
```

## Day 3 — Candidate Semantics And Coverage

### Task D3-T1: Parse Supported Types And Bound Complex Semantics

**Files:**

- Create: `backend/app/candidates/schemas.py`
- Create: `backend/app/candidates/parser.py`
- Create: `backend/app/candidates/grouping.py`
- Create: `backend/app/candidates/disposition.py`
- Create: `backend/app/candidates/complex_fallback.py`
- Test: `backend/tests/unit/candidates/test_parser.py`
- Test: `backend/tests/unit/candidates/test_grouping.py`
- Test: `backend/tests/unit/candidates/test_disposition.py`
- Test: `backend/tests/unit/candidates/test_complex_fallback.py`

- [ ] **Step 1: Write table-driven failing tests for every supported P0 type**

```python
# backend/tests/unit/candidates/test_parser.py
from decimal import Decimal

import pytest

from app.candidates.parser import parse_annotation


@pytest.mark.parametrize(
    ("text", "item_type", "field", "expected"),
    [
        ("25", "linear_dimension", "nominal", Decimal("25")),
        ("25±0.02", "linear_dimension", "upper_tolerance", Decimal("0.02")),
        ("Φ10贯穿", "diameter_dimension", "through", True),
        ("M6深10", "thread", "thread_depth", Decimal("10")),
        ("R5", "radius", "radius_value", Decimal("5")),
        ("45°±0.5°", "angle", "angle_value", Decimal("45")),
        ("16 × M5", "thread", "quantity", 16),
    ],
)
def test_supported_annotation_types(text, item_type, field, expected) -> None:
    candidate = parse_annotation(text)
    assert candidate.item_type == item_type
    assert getattr(candidate, field) == expected


def test_diameter_feature_kind_is_not_guessed() -> None:
    candidate = parse_annotation("Φ20")
    assert candidate.feature_kind == "unknown"
    assert candidate.requires_confirmation is True
```

```python
# backend/tests/unit/candidates/test_complex_fallback.py
from app.candidates.complex_fallback import coarse_candidate


def test_gdt_field_allowlist() -> None:
    result = coarse_candidate("⌖ 0.02 A", "geometric_tolerance", (1, 2, 3, 4))
    assert set(result.model_dump()) == {"raw_text", "coordinates", "coarse_type", "requires_confirmation"}
    assert result.requires_confirmation is True
```

- [ ] **Step 2: Run tests and verify parsing modules are absent**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_parser.py backend/tests/unit/candidates/test_complex_fallback.py -q
```

Expected: collection FAIL for missing candidate modules.

- [ ] **Step 3: Implement typed candidate schemas and Decimal-safe parsing**

```python
# backend/app/candidates/schemas.py
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    item_type: Literal[
        "linear_dimension", "diameter_dimension", "thread", "radius", "angle",
        "general_requirement", "geometric_tolerance", "roughness", "weld", "composite",
    ]
    raw_text: str
    normalized_text: str
    coordinates: tuple[float, float, float, float] | None = None
    scope: Literal["local_feature", "global_requirement"] = "local_feature"
    quantity: int | None = Field(default=None, ge=1)
    nominal: Decimal | None = None
    upper_tolerance: Decimal | None = None
    lower_tolerance: Decimal | None = None
    feature_kind: Literal["hole", "shaft", "cylindrical_feature", "unknown"] | None = None
    depth: Decimal | None = None
    through: bool | None = None
    thread_spec: str | None = None
    thread_depth: Decimal | None = None
    radius_value: Decimal | None = None
    angle_value: Decimal | None = None
    sub_requirements: list[dict] = Field(default_factory=list)
    balloon_required: bool = True
    requires_confirmation: bool = False
```

```python
# backend/app/candidates/parser.py
from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal

from app.candidates.schemas import Candidate


NUMBER = r"[0-9]+(?:\.[0-9]+)?"
QUANTITY = re.compile(rf"^(?P<quantity>[0-9]+)\s*[×xX-]\s*(?P<body>.+)$")
THREAD = re.compile(rf"^(?P<spec>M{NUMBER}(?:\s*[×xX]\s*{NUMBER})?)(?:\s*(?:深|↓)\s*(?P<depth>{NUMBER}))?(?P<through>\s*通)?$")
DIAMETER = re.compile(rf"^Φ\s*(?P<nominal>{NUMBER})(?:\s*(?:深|↓)\s*(?P<depth>{NUMBER}))?(?P<through>\s*(?:通|贯穿))?$")
RADIUS = re.compile(rf"^R\s*(?P<value>{NUMBER})$")
ANGLE = re.compile(rf"^(?P<value>{NUMBER})°(?:\s*±\s*(?P<tolerance>{NUMBER})°?)?$")
LINEAR = re.compile(rf"^(?P<value>{NUMBER})(?:\s*±\s*(?P<tolerance>{NUMBER}))?$")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("∅", "Φ").replace("ø", "Φ").replace("⌀", "Φ")
    return " ".join(normalized.split())


def _id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def parse_annotation(raw_text: str) -> Candidate:
    normalized = normalize_text(raw_text)
    quantity = None
    quantity_match = QUANTITY.match(normalized)
    if quantity_match:
        quantity = int(quantity_match.group("quantity"))
        normalized = quantity_match.group("body")
    if match := THREAD.match(normalized):
        return Candidate(
            candidate_id=_id(raw_text), item_type="thread", raw_text=raw_text,
            normalized_text=normalized, quantity=quantity, thread_spec=match.group("spec"),
            thread_depth=Decimal(match.group("depth")) if match.group("depth") else None,
            through=bool(match.group("through")),
        )
    if match := DIAMETER.match(normalized):
        return Candidate(
            candidate_id=_id(raw_text), item_type="diameter_dimension", raw_text=raw_text,
            normalized_text=normalized, quantity=quantity, nominal=Decimal(match.group("nominal")),
            feature_kind="unknown", depth=Decimal(match.group("depth")) if match.group("depth") else None,
            through=bool(match.group("through")), requires_confirmation=True,
        )
    if match := RADIUS.match(normalized):
        return Candidate(candidate_id=_id(raw_text), item_type="radius", raw_text=raw_text, normalized_text=normalized, quantity=quantity, radius_value=Decimal(match.group("value")))
    if match := ANGLE.match(normalized):
        tolerance = Decimal(match.group("tolerance")) if match.group("tolerance") else None
        return Candidate(candidate_id=_id(raw_text), item_type="angle", raw_text=raw_text, normalized_text=normalized, quantity=quantity, angle_value=Decimal(match.group("value")), upper_tolerance=tolerance, lower_tolerance=-tolerance if tolerance is not None else None)
    if match := LINEAR.match(normalized):
        tolerance = Decimal(match.group("tolerance")) if match.group("tolerance") else None
        return Candidate(candidate_id=_id(raw_text), item_type="linear_dimension", raw_text=raw_text, normalized_text=normalized, quantity=quantity, nominal=Decimal(match.group("value")), upper_tolerance=tolerance, lower_tolerance=-tolerance if tolerance is not None else None)
    raise ValueError(f"unsupported deterministic annotation: {raw_text}")
```

```python
# backend/app/candidates/complex_fallback.py
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CoarseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str
    coordinates: tuple[float, float, float, float]
    coarse_type: Literal["geometric_tolerance", "roughness", "weld", "cross_view_duplicate"]
    requires_confirmation: bool = True


def coarse_candidate(raw_text: str, coarse_type: str, coordinates: tuple[float, float, float, float]) -> CoarseCandidate:
    return CoarseCandidate(raw_text=raw_text, coarse_type=coarse_type, coordinates=coordinates)
```

- [ ] **Step 4: Implement ordered grouping and executable-requirement disposition, then run all type tests**

`group_observations()` must sort by `(page_index, direction, bbox.y0, bbox.x0, observation_id)`, group compatible adjacent lines, and create one composite candidate with ordered `sub_requirements`; it must never merge only because normalized text matches. `classify_technical_requirement()` returns `general_requirement` only for an explicit verb/check pair and always sets `scope="global_requirement"` and `balloon_required=false`.

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_parser.py backend/tests/unit/candidates/test_grouping.py backend/tests/unit/candidates/test_disposition.py backend/tests/unit/candidates/test_complex_fallback.py -q
```

Expected: every `P0-REC-007*` and `P0-REC-008*` focused case PASS; identical text in different views remains separate.

- [ ] **Step 5: Commit candidate semantics**

```bash
git add backend/app/candidates/schemas.py backend/app/candidates/parser.py backend/app/candidates/grouping.py backend/app/candidates/disposition.py backend/app/candidates/complex_fallback.py backend/tests/unit/candidates/test_parser.py backend/tests/unit/candidates/test_grouping.py backend/tests/unit/candidates/test_disposition.py backend/tests/unit/candidates/test_complex_fallback.py
git commit -m "feat: parse P0 inspection candidates"
```

### Task D3-T2: Close Coverage And Freeze Raw Automatic Results

**Files:**

- Create: `backend/app/candidates/duplicates.py`
- Create: `backend/app/candidates/coverage.py`
- Create: `backend/app/candidates/models.py`
- Create: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/processing/pipeline.py`
- Modify: `backend/app/processing/tasks.py`
- Generate: `backend/alembic/versions/0003_candidates.py`
- Test: `backend/tests/unit/candidates/test_duplicates.py`
- Test: `backend/tests/unit/candidates/test_coverage.py`
- Create: `backend/tests/integration/test_result_layers.py`
- Test: `backend/tests/e2e/test_offline_automatic_result.py`

- [ ] **Step 1: Write failing coverage and raw-immutability tests**

```python
# backend/tests/unit/candidates/test_coverage.py
from app.candidates.coverage import CoverageEntry, check_coverage


def test_ambiguous_is_reviewable_but_incomplete_is_blocking() -> None:
    ambiguous = CoverageEntry("o1", "ambiguous", "source-1", (1, 2, 3, 4))
    incomplete = CoverageEntry("o2", None, "source-2", (5, 6, 7, 8))
    report = check_coverage([ambiguous, incomplete])
    assert report.review_required_count == 1
    assert report.blocking_count == 1
    assert report.coverage_checked is False
```

```python
# backend/tests/integration/test_result_layers.py
import pytest
from sqlalchemy.exc import IntegrityError


def test_raw_result_is_immutable(raw_result, db_session) -> None:
    raw_result.payload = {"candidates": []}
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run and verify coverage/result modules are missing**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_coverage.py backend/tests/integration/test_result_layers.py -q
```

Expected: collection FAIL for missing `coverage` and `automatic_result` modules.

- [ ] **Step 3: Implement one-disposition coverage and suggestion-only duplicates**

```python
# backend/app/candidates/coverage.py
from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageEntry:
    observation_id: str
    disposition: str | None
    source_location_id: str | None
    coordinates: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class CoverageReport:
    blocking_count: int
    review_required_count: int
    coverage_checked: bool


def check_coverage(entries: list[CoverageEntry]) -> CoverageReport:
    seen: set[str] = set()
    blocking = 0
    review_required = 0
    for entry in entries:
        if entry.observation_id in seen:
            blocking += 1
        seen.add(entry.observation_id)
        if not entry.disposition or not entry.source_location_id or not entry.coordinates:
            blocking += 1
        elif entry.disposition == "ambiguous":
            review_required += 1
    return CoverageReport(blocking, review_required, blocking == 0)
```

`suggest_cross_view_duplicates()` returns relation records with `relation_type="possible_duplicate"` and `requires_confirmation=true`; it never changes disposition or candidate IDs.

- [ ] **Step 4: Persist one immutable raw result only when coverage blocking is zero**

`AutomaticResult` must store `id/project_id/source_file_id/inventory_ref/candidates JSON/coverage JSON/provider_call_ids/schema_version/created_at`; database trigger `prevent_automatic_result_update_delete` raises on UPDATE/DELETE. `build_automatic_result()` must abort with `coverage_blocking` before insert when `blocking_count>0`, otherwise insert once under the process logical-task key and transition project to `ready_for_edit`.

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_duplicates.py backend/tests/unit/candidates/test_coverage.py backend/tests/integration/test_result_layers.py backend/tests/e2e/test_offline_automatic_result.py -q
```

Expected: tests PASS; offline Provider fixtures produce one immutable raw result; coverage blocking produces no raw result and leaves a structured error.

- [ ] **Step 5: Commit coverage closure**

```bash
git add backend/app/candidates/duplicates.py backend/app/candidates/coverage.py backend/app/candidates/models.py backend/app/processing/automatic_result.py backend/app/processing/pipeline.py backend/app/processing/tasks.py backend/alembic/versions/0003_candidates.py backend/tests/unit/candidates/test_duplicates.py backend/tests/unit/candidates/test_coverage.py backend/tests/integration/test_result_layers.py backend/tests/e2e/test_offline_automatic_result.py
git commit -m "feat: freeze coverage-checked automatic results"
```

## Day 4 — Review Aggregate, Concurrency And Workbench

### Task D4-T1: Implement Working-Copy Commands And Operation Logs

**Files:**

- Create: `backend/app/review/models.py`
- Create: `backend/app/review/schemas.py`
- Create: `backend/app/review/service.py`
- Generate: `backend/alembic/versions/0004_review.py`
- Test: `backend/tests/contract/test_review_schema.py`
- Test: `backend/tests/integration/test_review_working_copy.py`
- Test: `backend/tests/integration/test_review_operations.py`
- Modify: `backend/tests/integration/test_result_layers.py`
- Modify: `backend/tests/integration/test_operator_audit.py`

- [ ] **Step 1: Write failing keep/exclude/edit/add/merge/split tests**

```python
# backend/tests/integration/test_review_operations.py
def test_simple_merge_preserves_sources_without_quantity_sum(review_service, working_copy) -> None:
    merged = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "merge", "item_ids": ["i1", "i2"], "raw_text": "M6 通"},
    )
    item = merged.items[-1]
    assert item.source_location_ids == ["s1", "s2"]
    assert item.quantity is None
    assert {entry.status for entry in merged.items if entry.item_id in {"i1", "i2"}} == {"superseded"}


def test_simple_split_preserves_source_relations(review_service, working_copy) -> None:
    split = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "split",
            "item_id": "composite-1",
            "parts": [{"raw_text": "Φ10"}, {"raw_text": "深20"}],
        },
    )
    assert [item.source_location_ids for item in split.items[-2:]] == [["s-composite"], ["s-composite"]]
```

```python
# backend/tests/integration/test_result_layers.py
def test_working_copy_is_versioned(review_service, raw_result) -> None:
    working = review_service.create_from_raw(raw_result.id)
    saved = review_service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": working.items[0]["item_id"]},
    )
    assert saved.id == working.id
    assert saved.raw_result_id == raw_result.id
    assert saved.version == working.version + 1
```

- [ ] **Step 2: Run and verify review modules are missing**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_result_layers.py -q
```

Expected: collection FAIL for missing `app.review` modules.

- [ ] **Step 3: Define the command union and versioned aggregate**

```python
# backend/app/review/schemas.py
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Keep(CommandBase):
    type: Literal["keep"]
    item_id: str


class Exclude(CommandBase):
    type: Literal["exclude"]
    item_id: str


class Edit(CommandBase):
    type: Literal["edit"]
    item_id: str
    fields: dict


class Add(CommandBase):
    type: Literal["add"]
    raw_text: str
    item_type: str
    coordinates: tuple[float, float, float, float]
    balloon_required: bool


class Merge(CommandBase):
    type: Literal["merge"]
    item_ids: list[str] = Field(min_length=2)
    raw_text: str


class SplitPart(BaseModel):
    raw_text: str


class Split(CommandBase):
    type: Literal["split"]
    item_id: str
    parts: list[SplitPart] = Field(min_length=2)


class ResolveConfirmation(CommandBase):
    type: Literal["resolve_confirmation"]
    item_id: str
    accepted: bool


class SetBalloonRequired(CommandBase):
    type: Literal["set_balloon_required"]
    item_id: str
    balloon_required: bool


ReviewCommand = Annotated[
    Union[Keep, Exclude, Edit, Add, Merge, Split, ResolveConfirmation, SetBalloonRequired],
    Field(discriminator="type"),
]
```

`ReviewWorkingCopy` stores `id/project_id/raw_result_id/version/items JSON/numbering_stale/created_at/updated_at`. `ReviewService.apply()` must load the current version with `SELECT ... FOR UPDATE`, reject a mismatched `expected_version`, apply exactly one typed command, increment version once, and append one `OperationRecord` in the same transaction.

- [ ] **Step 4: Implement command invariants and run full review-operation tests**

Command invariants:

```python
COMPLEX_EDITABLE_FIELDS = {"raw_text", "coordinates", "coarse_type", "requires_confirmation"}


def validate_edit(item: dict, fields: dict) -> None:
    if item["item_type"] in {"geometric_tolerance", "roughness", "weld"}:
        extra = set(fields) - COMPLEX_EDITABLE_FIELDS
        if extra:
            raise ValueError(f"complex item fields are not editable in P0: {sorted(extra)}")


def merge_quantity(_: list[dict]) -> None:
    return None
```

`exclude` marks current item inactive; `add` writes `source_type="manual"`; `merge` supersedes inputs and creates one item with all source IDs; `split` supersedes the input and creates ordered parts with the same source IDs; `set_balloon_required` sets `numbering_stale=true`; no command mutates the raw result row.

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_result_layers.py backend/tests/integration/test_operator_audit.py -q
```

Expected: all tests PASS, including raw immutability and one audit row per command.

- [ ] **Step 5: Commit review aggregate**

```bash
git add backend/app/review/models.py backend/app/review/schemas.py backend/app/review/service.py backend/alembic/versions/0004_review.py backend/tests/contract/test_review_schema.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_review_operations.py backend/tests/integration/test_result_layers.py backend/tests/integration/test_operator_audit.py
git commit -m "feat: add versioned review commands"
```

### Task D4-T2: Add Single-Editor Lock, Item-Set Freeze Veto And Review API

**Files:**

- Create: `backend/app/review/locks.py`
- Create: `backend/app/review/router.py`
- Modify: `backend/app/review/models.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/review/test_locks.py`
- Test: `backend/tests/integration/test_review_lock.py`
- Test: `backend/tests/integration/test_review_version.py`
- Test: `backend/tests/integration/test_review_freeze.py`
- Modify: `backend/tests/integration/test_result_layers.py`

- [ ] **Step 1: Write failing lock/version/freeze tests**

```python
# backend/tests/integration/test_review_freeze.py
import pytest

from app.review.service import FreezeBlocked


def test_unresolved_confirmation_blocks_freeze(review_service, working_copy) -> None:
    working_copy.items[0]["requires_confirmation"] = True
    with pytest.raises(FreezeBlocked) as error:
        review_service.freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )
    assert error.value.code == "unresolved_confirmation"
```

```python
# backend/tests/integration/test_result_layers.py
def test_item_set_freeze_does_not_create_reviewed_result(review_service, ready_working_copy) -> None:
    review_service.freeze_items(
        ready_working_copy.id,
        expected_version=ready_working_copy.version,
        operator_id="quality-1",
    )
    assert review_service.reviewed_result_for(ready_working_copy.project_id) is None
    assert review_service.get_working_copy(ready_working_copy.id).items_frozen_at is not None
```

- [ ] **Step 2: Run and verify freeze currently fails**

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_review_lock.py backend/tests/integration/test_review_version.py backend/tests/integration/test_review_freeze.py -q
```

Expected: FAIL because locks/router/freeze do not exist.

- [ ] **Step 3: Implement database-clock lock acquisition and stale-write protection**

```python
# backend/app/review/locks.py
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.review.models import ReviewLock


class LockConflict(RuntimeError):
    pass


def acquire_lock(session: Session, project_id, operator_id: str, ttl_seconds: int = 300) -> ReviewLock:
    now = session.scalar(select(func.now()))
    lock = session.scalar(select(ReviewLock).where(ReviewLock.project_id == project_id).with_for_update())
    if lock and lock.expires_at > now and lock.operator_id != operator_id:
        raise LockConflict("project already has an active editor")
    if lock is None:
        lock = ReviewLock(project_id=project_id, operator_id=operator_id, expires_at=now + timedelta(seconds=ttl_seconds))
        session.add(lock)
    else:
        lock.operator_id = operator_id
        lock.expires_at = now + timedelta(seconds=ttl_seconds)
    session.commit()
    return lock
```

All review mutations must add `WHERE version=:expected_version`; affected row count `0` maps to HTTP `409` with `error.code="review_version_conflict"`.

- [ ] **Step 4: Implement the item-set freeze boundary and API routes**

Freeze preconditions are exact:

```python
def freeze_blockers(items: list[dict], coverage: dict) -> list[str]:
    blockers: list[str] = []
    if coverage["blocking_count"]:
        blockers.append("coverage_blocking")
    if any(item["active"] and item.get("requires_confirmation") for item in items):
        blockers.append("unresolved_confirmation")
    if any(item["active"] and item.get("balloon_required") is None for item in items):
        blockers.append("balloon_required_unconfirmed")
    return blockers
```

On zero blockers, `freeze_items()` records `items_frozen_at/items_frozen_by/items_frozen_version` on the locked working copy. It rejects every later semantic item command, keeps the project in `editing`, and deliberately does **not** create `ReviewedResult`; formal balloon numbering and geometry are not final yet. Routes:

```text
POST /api/v1/projects/{project_id}/review/lock
GET  /api/v1/projects/{project_id}/review/working-copy
POST /api/v1/projects/{project_id}/review/commands
POST /api/v1/projects/{project_id}/review/freeze-items
```

Every POST requires `X-QI-Operator`; commands/freeze-items require `expected_version` in body.

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/review/test_locks.py backend/tests/integration/test_review_lock.py backend/tests/integration/test_review_version.py backend/tests/integration/test_review_freeze.py backend/tests/integration/test_result_layers.py -q
```

Expected: all tests PASS; Save never freezes the item set; freeze-items blocks further semantic edits; no `ReviewedResult` exists before Day 5 final confirm.

- [ ] **Step 5: Commit concurrency and freeze**

```bash
git add backend/app/review/locks.py backend/app/review/router.py backend/app/review/models.py backend/app/review/service.py backend/app/main.py backend/tests/unit/review/test_locks.py backend/tests/integration/test_review_lock.py backend/tests/integration/test_review_version.py backend/tests/integration/test_review_freeze.py backend/tests/integration/test_result_layers.py
git commit -m "feat: add review lock and item-set freeze"
```

### Task D4-T3: Build The PDF/Table Review Workbench

**Files:**

- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/components/pdf/PdfWorkspace.tsx`
- Create: `frontend/src/components/pdf/OverlayLayer.tsx`
- Create: `frontend/src/components/review/ReviewPanel.tsx`
- Create: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Create: `frontend/src/features/review/saveWorkingCopy.ts`
- Test: `frontend/src/components/pdf/PdfWorkspace.test.tsx`
- Test: `frontend/src/components/pdf/OverlayLayer.test.tsx`
- Test: `frontend/src/components/review/ReviewPanel.test.tsx`
- Test: `frontend/src/features/review/saveWorkingCopy.test.ts`

- [ ] **Step 1: Write failing viewport and explicit-save tests**

```tsx
// frontend/src/components/pdf/OverlayLayer.test.tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { OverlayLayer } from "./OverlayLayer";

test("P0-UI-004 renders candidate, source and balloon layers", () => {
  render(<OverlayLayer pageWidth={100} pageHeight={200} scale={2} candidates={[{id:"c1", bbox:[10,20,30,40]}]} sources={[{id:"s1", bbox:[40,50,60,70]}]} balloons={[{id:"b1", center:[80,90], number:1}]} />);
  expect(screen.getByTestId("candidate-c1")).toBeVisible();
  expect(screen.getByTestId("source-s1")).toBeVisible();
  expect(screen.getByTestId("balloon-b1")).toBeVisible();
});
```

```ts
// frontend/src/features/review/saveWorkingCopy.test.ts
import { expect, test, vi } from "vitest";
import { saveWorkingCopy } from "./saveWorkingCopy";

test("P0-UI-007 save sends version and operator without freezing", async () => {
  const post = vi.fn().mockResolvedValue({version: 4});
  await saveWorkingCopy(post, "p1", "quality-1", 3, {type:"keep", item_id:"i1"});
  expect(post).toHaveBeenCalledWith("/api/v1/projects/p1/review/commands", {expected_version:3, command:{type:"keep", item_id:"i1"}}, {"X-QI-Operator":"quality-1"});
  expect(post.mock.calls[0][0]).not.toContain("freeze");
});
```

- [ ] **Step 2: Run tests and verify components are missing**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/pdf/OverlayLayer.test.tsx src/features/review/saveWorkingCopy.test.ts
```

Expected: FAIL because components/functions do not exist.

- [ ] **Step 3: Implement PDF.js canvas plus PDF-coordinate SVG overlay**

```tsx
// frontend/src/components/pdf/OverlayLayer.tsx
type Box = { id: string; bbox: [number, number, number, number] };
type Balloon = { id: string; center: [number, number]; number: number };

export function OverlayLayer({pageWidth, pageHeight, scale, candidates, sources, balloons}: {pageWidth:number; pageHeight:number; scale:number; candidates:Box[]; sources:Box[]; balloons:Balloon[]}) {
  return <svg aria-label="engineering overlays" width={pageWidth * scale} height={pageHeight * scale} viewBox={`0 0 ${pageWidth} ${pageHeight}`}>
    {candidates.map(item => <rect key={item.id} data-testid={`candidate-${item.id}`} x={item.bbox[0]} y={item.bbox[1]} width={item.bbox[2]-item.bbox[0]} height={item.bbox[3]-item.bbox[1]} fill="none" stroke="#f59e0b" />)}
    {sources.map(item => <rect key={item.id} data-testid={`source-${item.id}`} x={item.bbox[0]} y={item.bbox[1]} width={item.bbox[2]-item.bbox[0]} height={item.bbox[3]-item.bbox[1]} fill="none" stroke="#3b82f6" />)}
    {balloons.map(item => <g key={item.id} data-testid={`balloon-${item.id}`}><circle cx={item.center[0]} cy={item.center[1]} r={10} fill="white" stroke="#dc2626"/><text x={item.center[0]} y={item.center[1]} textAnchor="middle" dominantBaseline="middle">{item.number}</text></g>)}
  </svg>;
}
```

`PdfWorkspace` must configure `GlobalWorkerOptions.workerSrc`, render only the selected page to canvas at `scale`, position `OverlayLayer` absolutely over that canvas, and keep `pageIndex/scale/pan` in React state. Pan changes CSS transform only; it never edits overlay data.

- [ ] **Step 4: Implement ReviewPanel and explicit Save flow, then run frontend tests**

`ReviewPanel` renders typed fields and explicit buttons for keep/exclude/edit/add/merge/split/resolve confirmation/set balloon-required. It calls `saveWorkingCopy()` only on a user action; no timer/effect may POST mutations.

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: all component tests PASS; TypeScript build succeeds; tests prove zoom/pan preserve PDF coordinates and Save does not freeze.

- [ ] **Step 5: Commit the review workbench**

```bash
git add frontend/tsconfig.json frontend/vite.config.ts frontend/vitest.config.ts frontend/src/api frontend/src/components/pdf frontend/src/components/review frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/features/review
git commit -m "feat: add PDF review workbench"
```

## Day 5 — Formal Numbering, Balloon Review And Final Freeze

### Task D5-T1: Add Deterministic Numbering And Placement

**Files:**

- Create: `backend/app/balloons/schemas.py`
- Create: `backend/app/balloons/numbering.py`
- Create: `backend/app/balloons/placement.py`
- Test: `backend/tests/unit/balloons/test_numbering.py`
- Test: `backend/tests/unit/balloons/test_layout.py`

- [ ] **Step 1: Write failing numbering and forced-collision tests**

```python
# backend/tests/unit/balloons/test_numbering.py
from app.balloons.numbering import NumberableItem, assign_numbers


def test_formal_sequence_has_no_gap_or_duplicate() -> None:
    items = [
        NumberableItem("i2", True, 1, (20, 10, 30, 20), "B"),
        NumberableItem("general", False, 0, (0, 0, 0, 0), "G"),
        NumberableItem("i1", True, 0, (10, 10, 20, 20), "A"),
    ]
    result = assign_numbers(items)
    assert [(item.item_id, item.number) for item in result] == [("i1", 1), ("i2", 2)]
```

```python
# backend/tests/unit/balloons/test_layout.py
from app.balloons.placement import PlacementInput, place_balloon


def test_forced_collision_returns_manual_required() -> None:
    result = place_balloon(
        PlacementInput(page_size=(100, 100), anchor_bbox=(45, 45, 55, 55), forbidden=((0, 0, 100, 100),)),
    )
    assert result.status == "manual_required"
    assert result.center is not None
    assert result.collision_flags
    assert result.reason == "no_valid_candidate"
```

- [ ] **Step 2: Run and verify balloon modules are missing**

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/balloons/test_numbering.py backend/tests/unit/balloons/test_layout.py -q
```

Expected: collection FAIL for missing balloon modules.

- [ ] **Step 3: Implement stable sorting and continuous numbering**

```python
# backend/app/balloons/numbering.py
from dataclasses import dataclass


@dataclass(frozen=True)
class NumberableItem:
    item_id: str
    balloon_required: bool
    page_index: int
    source_bbox: tuple[float, float, float, float]
    stable_seed: str
    direction: tuple[float, float] = (1.0, 0.0)


@dataclass(frozen=True)
class NumberedItem:
    item_id: str
    number: int


def assign_numbers(items: list[NumberableItem], start: int = 1) -> list[NumberedItem]:
    if start < 1:
        raise ValueError("start must be >= 1")
    ordered = sorted(
        (item for item in items if item.balloon_required),
        key=lambda item: (
            item.page_index,
            item.source_bbox[1],
            item.source_bbox[0],
            item.direction,
            item.stable_seed,
            item.item_id,
        ),
    )
    return [NumberedItem(item.item_id, start + index) for index, item in enumerate(ordered)]
```

- [ ] **Step 4: Implement the fixed-direction greedy scorer**

```python
# backend/app/balloons/placement.py
from dataclasses import dataclass


BBox = tuple[float, float, float, float]
DIRECTIONS = ((0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1))


@dataclass(frozen=True)
class PlacementInput:
    page_size: tuple[float, float]
    anchor_bbox: BBox
    forbidden: tuple[BBox, ...] = ()
    radius: float = 10.0
    gap: float = 18.0


@dataclass(frozen=True)
class PlacementResult:
    status: str
    center: tuple[float, float]
    collision_flags: tuple[str, ...]
    reason: str | None


def _inside(center, page_size, radius):
    return radius <= center[0] <= page_size[0]-radius and radius <= center[1] <= page_size[1]-radius


def _in_box(center, box):
    return box[0] <= center[0] <= box[2] and box[1] <= center[1] <= box[3]


def place_balloon(data: PlacementInput) -> PlacementResult:
    x0, y0, x1, y1 = data.anchor_bbox
    anchor = ((x0+x1)/2, (y0+y1)/2)
    scored = []
    for order, (dx, dy) in enumerate(DIRECTIONS):
        center = (anchor[0] + dx*data.gap, anchor[1] + dy*data.gap)
        flags = []
        if not _inside(center, data.page_size, data.radius):
            flags.append("outside_cropbox")
        if any(_in_box(center, box) for box in data.forbidden):
            flags.append("forbidden_overlap")
        scored.append((len(flags), order, center, tuple(flags)))
    score, _, center, flags = min(scored)
    if score == 0:
        return PlacementResult("placed", center, (), None)
    return PlacementResult("manual_required", center, flags, "no_valid_candidate")
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/balloons/test_numbering.py backend/tests/unit/balloons/test_layout.py -q
```

Expected: tests PASS; repeated runs serialize identical ordering/positions.

- [ ] **Step 5: Commit deterministic balloon engines**

```bash
git add backend/app/balloons/schemas.py backend/app/balloons/numbering.py backend/app/balloons/placement.py backend/tests/unit/balloons/test_numbering.py backend/tests/unit/balloons/test_layout.py
git commit -m "feat: add deterministic balloon numbering and placement"
```

### Task D5-T2: Add Balloon Commands, Validation And Immutable Reviewed Result

**Files:**

- Create: `backend/app/balloons/models.py`
- Create: `backend/app/balloons/service.py`
- Create: `backend/app/balloons/validator.py`
- Create: `backend/app/balloons/router.py`
- Modify: `backend/app/review/models.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/app/main.py`
- Generate: `backend/alembic/versions/0005_balloons.py`
- Test: `backend/tests/integration/test_balloon_service.py`
- Test: `backend/tests/integration/test_balloon_operations.py`
- Test: `backend/tests/integration/test_balloon_validation.py`
- Modify: `backend/tests/integration/test_result_layers.py`

- [ ] **Step 1: Write failing move/delete/rebuild/reorder/final-freeze tests**

```python
# backend/tests/integration/test_balloon_operations.py
def test_delete_balloon_preserves_item_and_requirement(balloon_service, frozen_items) -> None:
    balloon = balloon_service.generate(frozen_items.project_id)[0]
    balloon_service.delete(balloon.id, expected_version=1, operator_id="quality-1")
    item = balloon_service.get_item(balloon.inspection_item_id)
    assert item.active is True
    assert item.balloon_required is True
    assert balloon_service.get(balloon.id).status == "deleted"
```

```python
# backend/tests/integration/test_balloon_service.py
import pytest

from app.balloons.service import ItemSetNotFrozen


def test_formal_numbers_require_frozen_item_set(balloon_service, review_service, ready_working_copy) -> None:
    with pytest.raises(ItemSetNotFrozen):
        balloon_service.generate_formal(ready_working_copy.project_id)
    review_service.freeze_items(
        ready_working_copy.id,
        expected_version=ready_working_copy.version,
        operator_id="quality-1",
    )
    generated = balloon_service.generate_formal(ready_working_copy.project_id)
    assert [balloon.formal_number for balloon in generated] == list(range(1, len(generated) + 1))
```

```python
# backend/tests/integration/test_result_layers.py
import pytest


def test_reviewed_result_is_immutable(review_service, completed_balloon_review) -> None:
    reviewed = review_service.confirm(completed_balloon_review, operator_id="quality-1")
    with pytest.raises(Exception, match="immutable reviewed result"):
        review_service.replace_items(reviewed.id, [])
```

- [ ] **Step 2: Run and verify balloon service is absent**

```bash
micromamba run -n qi-p0 pytest backend/tests/integration/test_balloon_service.py backend/tests/integration/test_balloon_operations.py backend/tests/integration/test_result_layers.py -q
```

Expected: collection FAIL for missing balloon service/models.

- [ ] **Step 3: Implement balloon aggregate and commands**

`Balloon` stores `id/project_id/inspection_item_id/source_location_id/suggested_number/formal_number/anchor_bbox_pdf/leader_target_pdf/center_pdf/placement_status/collision_flags/status/version`. Unique active constraint: one active balloon per inspection item and one formal number per project.

Commands and effects are exact:

```python
COMMAND_EFFECTS = {
    "move": {"changes": {"center_pdf"}, "requires": {"expected_version", "operator_id"}},
    "delete": {"changes": {"status"}, "requires": {"expected_version", "operator_id"}},
    "rebuild": {"changes": {"status", "center_pdf", "placement_status"}, "requires": {"expected_version", "operator_id"}},
    "reorder": {"changes": {"sort_order"}, "requires": {"expected_version", "operator_id"}},
    "renumber": {"changes": {"formal_number"}, "requires": {"expected_version", "operator_id"}},
}
```

`delete` never changes the item. `rebuild` reuses deterministic placement. `reorder` marks numbering stale. `renumber` locks all active balloons and writes a complete continuous sequence in one transaction.

- [ ] **Step 4: Separate item-set freeze from final reviewed-result freeze**

The minimum P0 sequence is:

```text
working copy semantic edits
→ freeze reviewed item set (no more candidate/item mutations)
→ assign formal numbers and adjust balloons
→ validate balloons
→ confirm immutable reviewed_result containing items + final balloons
```

`validate_balloons()` returns blocking codes for outside CropBox, missing required balloon, duplicate/gapped number, invalid leader, unreadable number or item/balloon disconnect. `manual_required` alone is not blocking after the user moves/rebuilds it into valid geometry.

`confirm()` acquires row locks for the item-frozen working copy and every active balloon, reruns all blockers, then inserts exactly one `ReviewedResult(id/project_id/working_copy_id/working_version/items/balloons/schema_version/created_at)`. The insert, project transition `editing → reviewed`, and final operation record commit in one transaction. A database trigger rejects UPDATE/DELETE on `reviewed_results`; a duplicate confirm with the same working version returns the same result, while a different version is impossible after item freeze.

Routes:

```text
POST /api/v1/projects/{project_id}/review/freeze-items
GET  /api/v1/projects/{project_id}/balloons
POST /api/v1/projects/{project_id}/balloons/generate
POST /api/v1/projects/{project_id}/balloons/commands
POST /api/v1/projects/{project_id}/review/confirm
```

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest backend/tests/integration/test_balloon_service.py backend/tests/integration/test_balloon_operations.py backend/tests/integration/test_balloon_validation.py backend/tests/integration/test_result_layers.py -q
```

Expected: all tests PASS; final confirm stores both reviewed items and final balloon geometry in one immutable reviewed result.

- [ ] **Step 5: Commit balloon review closure**

```bash
git add backend/app/balloons/models.py backend/app/balloons/service.py backend/app/balloons/validator.py backend/app/balloons/router.py backend/app/review/models.py backend/app/review/service.py backend/app/main.py backend/alembic/versions/0005_balloons.py backend/tests/integration/test_balloon_service.py backend/tests/integration/test_balloon_operations.py backend/tests/integration/test_balloon_validation.py backend/tests/integration/test_result_layers.py
git commit -m "feat: finalize reviewed items with balloons"
```

### Task D5-T3: Add Balloon Interaction And Bidirectional Selection UI

**Files:**

- Create: `frontend/src/components/balloons/BalloonOverlay.tsx`
- Create: `frontend/src/components/balloons/BalloonToolbar.tsx`
- Create: `frontend/src/components/workbench/selection.ts`
- Create: `frontend/src/components/workbench/FreezeReviewButton.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Test: `frontend/src/components/balloons/BalloonOverlay.test.tsx`
- Test: `frontend/src/components/workbench/selection.test.tsx`
- Test: `frontend/src/components/workbench/FreezeReviewButton.test.tsx`

- [ ] **Step 1: Write failing drag/selection/confirm tests**

```tsx
// frontend/src/components/workbench/selection.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { InspectionWorkbench } from "./InspectionWorkbench";

test("P0-BAL-013 selecting a row highlights and scrolls its overlay", () => {
  render(<InspectionWorkbench fixture="one-item" />);
  fireEvent.click(screen.getByRole("row", {name:/M6/}));
  expect(screen.getByTestId("source-s1")).toHaveAttribute("data-selected", "true");
  expect(screen.getByTestId("balloon-b1")).toHaveAttribute("data-selected", "true");
});
```

- [ ] **Step 2: Run and verify UI modules are missing**

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/balloons/BalloonOverlay.test.tsx src/components/workbench/selection.test.tsx src/components/workbench/FreezeReviewButton.test.tsx
```

Expected: FAIL because balloon and final-confirm components do not exist.

- [ ] **Step 3: Implement PDF-coordinate drag and explicit commands**

`BalloonOverlay` uses SVG pointer capture. It converts client coordinates through the current SVG `getScreenCTM().inverse()` and POSTs `center_pdf`; it never saves CSS pixels. Toolbar actions call `delete/rebuild/reorder/renumber` endpoints with `expected_version` and `X-QI-Operator`.

```ts
export function clientToPdf(svg: SVGSVGElement, clientX: number, clientY: number): [number, number] {
  const matrix = svg.getScreenCTM();
  if (!matrix) throw new Error("overlay transform unavailable");
  const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
  return [point.x, point.y];
}
```

- [ ] **Step 4: Implement two-stage freeze/confirm buttons and run frontend build**

`Freeze Items` is enabled only when confirmations are resolved. `Confirm Reviewed Result` is enabled only after item freeze, continuous formal numbering and zero balloon blockers. Neither button is triggered by Save.

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: tests/build PASS; drag test asserts PDF coordinates; delete keeps row; explicit renumber removes gaps; confirm is distinct from Save.

- [ ] **Step 5: Commit balloon UI**

```bash
git add frontend/src/components/balloons frontend/src/components/workbench/selection.ts frontend/src/components/workbench/FreezeReviewButton.tsx frontend/src/components/workbench/InspectionWorkbench.tsx frontend/src/components/workbench/selection.test.tsx frontend/src/components/workbench/FreezeReviewButton.test.tsx
git commit -m "feat: add interactive balloon review"
```

## Day 6 — Controlled Export And Cross-Artifact Integrity

### Task D6-T1: Register Approved Assets And Render The Formal Ballooned PDF

**Files:**

- Create after external approval: `backend/assets/templates/sip-v1.xlsx`
- Create after external approval: `backend/assets/templates/sip-v1.mapping.json`
- Create after external approval: `backend/assets/fonts/DejaVuSans.ttf`
- Create after external approval: `backend/assets/fonts/LICENSE-DejaVu.txt`
- Create: `backend/app/exports/template_registry.py`
- Create: `backend/app/balloons/renderer.py`
- Modify: `backend/app/capabilities/service.py`
- Test: `backend/tests/unit/exports/test_template_registry.py`
- Test: `backend/tests/integration/test_balloon_pdf_renderer.py`
- Test: `backend/tests/integration/test_export_preflight.py`

- [ ] **Step 1: Resolve the two asset gates without inventing truth**

Run these read-only checks in the isolated worktree:

```bash
sha256sum '/home/reggie/文档/xwechat_files/wxid_ut5o9e1igztd22_f3a1/msg/file/2026-07/检验记录标准表.xlsx'
micromamba run -n qi-p0 python - <<'PY'
from pathlib import Path
from openpyxl import load_workbook

path = Path('/home/reggie/文档/xwechat_files/wxid_ut5o9e1igztd22_f3a1/msg/file/2026-07/检验记录标准表.xlsx')
book = load_workbook(path, read_only=False, data_only=False)
for sheet in book.worksheets:
    print(sheet.title, sheet.max_row, sheet.max_column, len(sheet.merged_cells.ranges))
PY
sha256sum /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
fc-scan --format '%{family}\n%{style}\n%{fontversion}\n' /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

Expected current evidence: template candidate hash is `5dbf2ce479ad366c163cdfc1bc94374ce5a4f62d924550774698ad3be7e1e9be`; font candidate hash is `ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280`. These hashes prove identity, not approval.

The quality Owner must supply a signed/recorded decision containing `template_id=sip-v1`, template hash, sheet, first/last detail row, every fixed field cell/column, image sheet/anchor, protected ranges and sign-off ranges. The font Owner must approve the font file and its redistribution license. If either decision is absent, stop Day 6 with `blocked`; do not copy a candidate asset and do not weaken preflight.

After approval only, copy the exact approved bytes and record their frozen hashes:

The approving Owners provide `QI_APPROVED_TEMPLATE_PATH`, `QI_APPROVED_TEMPLATE_MAPPING_PATH`, `QI_APPROVED_FONT_PATH` and `QI_APPROVED_FONT_LICENSE_PATH` as absolute paths in the execution shell. Validate them before copying:

```bash
test -n "${QI_APPROVED_TEMPLATE_PATH:-}" && test -f "$QI_APPROVED_TEMPLATE_PATH"
test -n "${QI_APPROVED_TEMPLATE_MAPPING_PATH:-}" && test -f "$QI_APPROVED_TEMPLATE_MAPPING_PATH"
test -n "${QI_APPROVED_FONT_PATH:-}" && test -f "$QI_APPROVED_FONT_PATH"
test -n "${QI_APPROVED_FONT_LICENSE_PATH:-}" && test -f "$QI_APPROVED_FONT_LICENSE_PATH"
install -D -m 0644 "$QI_APPROVED_TEMPLATE_PATH" backend/assets/templates/sip-v1.xlsx
install -D -m 0644 "$QI_APPROVED_TEMPLATE_MAPPING_PATH" backend/assets/templates/sip-v1.mapping.json
install -D -m 0644 "$QI_APPROVED_FONT_PATH" backend/assets/fonts/DejaVuSans.ttf
install -D -m 0644 "$QI_APPROVED_FONT_LICENSE_PATH" backend/assets/fonts/LICENSE-DejaVu.txt
sha256sum backend/assets/templates/sip-v1.xlsx backend/assets/fonts/DejaVuSans.ttf
```

Those four variables are gate inputs, not defaults for the implementation agent to infer. A mismatch against the approval record is a hard stop.

- [ ] **Step 2: Write failing registry, renderer and preflight tests**

```python
# backend/tests/unit/exports/test_template_registry.py
import json

import pytest

from app.exports.template_registry import AssetHashMismatch, load_template_registration


def test_p0_exp_001_registry_rejects_template_hash_drift(tmp_path) -> None:
    template = tmp_path / "sip-v1.xlsx"
    mapping = tmp_path / "sip-v1.mapping.json"
    template.write_bytes(b"changed")
    mapping.write_text(json.dumps({
        "template_id": "sip-v1",
        "template_version": "1",
        "template_sha256": "0" * 64,
        "mapping_version": "1",
        "sheet": "SIP",
        "capacity": {"first_row": 9, "last_row": 37},
        "metadata_cells": {},
        "detail_columns": {},
        "image_sheet": "Ballooned Drawing",
        "image_anchor": "A1",
        "protected_ranges": [],
        "signoff_ranges": [],
    }))
    with pytest.raises(AssetHashMismatch):
        load_template_registration(template, mapping)
```

```python
# backend/tests/integration/test_balloon_pdf_renderer.py
import fitz

from app.balloons.renderer import FrozenBalloon, render_ballooned_pdf


def test_page_count_matches_source(two_page_pdf_bytes, approved_font_path) -> None:
    rendered = render_ballooned_pdf(
        two_page_pdf_bytes,
        [FrozenBalloon(page_index=0, formal_number=1, center_pdf=(72, 72), leader_target_pdf=(96, 96))],
        approved_font_path,
    )
    with fitz.open(stream=rendered, filetype="pdf") as document:
        assert document.page_count == 2
        assert "1" in document[0].get_text()
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/exports/test_template_registry.py backend/tests/integration/test_balloon_pdf_renderer.py backend/tests/integration/test_export_preflight.py -q
```

Expected: collection FAIL for missing `template_registry` and `renderer`.

- [ ] **Step 3: Implement the single-template registry and hash Veto Gate**

```python
# backend/app/exports/template_registry.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AssetHashMismatch(RuntimeError):
    pass


class InvalidTemplateRegistration(RuntimeError):
    pass


@dataclass(frozen=True)
class TemplateRegistration:
    template_id: str
    template_version: str
    template_sha256: str
    mapping_version: str
    sheet: str
    first_row: int
    last_row: int
    metadata_cells: dict[str, str]
    detail_columns: dict[str, str]
    image_sheet: str
    image_anchor: str
    protected_ranges: tuple[str, ...]
    signoff_ranges: tuple[str, ...]

    @property
    def capacity(self) -> int:
        return self.last_row - self.first_row + 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_template_registration(template_path: Path, mapping_path: Path) -> TemplateRegistration:
    raw: dict[str, Any] = json.loads(mapping_path.read_text(encoding="utf-8"))
    required = {
        "template_id", "template_version", "template_sha256", "mapping_version",
        "sheet", "capacity", "metadata_cells", "detail_columns", "image_sheet",
        "image_anchor", "protected_ranges", "signoff_ranges",
    }
    if set(raw) != required or raw["template_id"] != "sip-v1":
        raise InvalidTemplateRegistration("mapping must be the complete sip-v1 registration")
    actual = _sha256(template_path)
    if actual != raw["template_sha256"]:
        raise AssetHashMismatch(f"template hash drift: expected {raw['template_sha256']}, got {actual}")
    first = int(raw["capacity"]["first_row"])
    last = int(raw["capacity"]["last_row"])
    if first < 1 or last < first:
        raise InvalidTemplateRegistration("invalid detail capacity")
    return TemplateRegistration(
        template_id=raw["template_id"], template_version=raw["template_version"],
        template_sha256=raw["template_sha256"], mapping_version=raw["mapping_version"],
        sheet=raw["sheet"], first_row=first, last_row=last,
        metadata_cells=dict(raw["metadata_cells"]), detail_columns=dict(raw["detail_columns"]),
        image_sheet=raw["image_sheet"], image_anchor=raw["image_anchor"],
        protected_ranges=tuple(raw["protected_ranges"]), signoff_ranges=tuple(raw["signoff_ranges"]),
    )
```

`backend/app/capabilities/service.py` computes both file hashes at request time. Missing asset, hash drift, absent license file, missing registered sheet or missing required mapping field returns a structured blocker and prevents the export job from entering `running`.

- [ ] **Step 4: Implement deterministic backend PDF rendering**

```python
# backend/app/balloons/renderer.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class FrozenBalloon:
    page_index: int
    formal_number: int
    center_pdf: tuple[float, float]
    leader_target_pdf: tuple[float, float]


def render_ballooned_pdf(source_pdf: bytes, balloons: list[FrozenBalloon], font_path: Path) -> bytes:
    with fitz.open(stream=source_pdf, filetype="pdf") as document:
        by_page: dict[int, list[FrozenBalloon]] = {}
        for balloon in balloons:
            by_page.setdefault(balloon.page_index, []).append(balloon)
        for page_index, page_balloons in sorted(by_page.items()):
            if page_index < 0 or page_index >= document.page_count:
                raise ValueError(f"balloon page out of range: {page_index}")
            page = document[page_index]
            page.insert_font(fontname="QIBalloon", fontfile=str(font_path))
            for balloon in sorted(page_balloons, key=lambda item: item.formal_number):
                center = fitz.Point(*balloon.center_pdf)
                target = fitz.Point(*balloon.leader_target_pdf)
                radius = 12.0
                circle = fitz.Rect(center.x - radius, center.y - radius, center.x + radius, center.y + radius)
                if not page.rect.contains(circle) or not page.rect.contains(target):
                    raise ValueError(f"invalid balloon geometry: {balloon.formal_number}")
                page.draw_line(center, target, color=(0, 0, 0), width=0.8, overlay=True)
                page.draw_circle(center, radius, color=(0, 0, 0), width=0.8, overlay=True)
                remaining = page.insert_textbox(
                    circle,
                    str(balloon.formal_number),
                    fontname="QIBalloon",
                    fontsize=9,
                    align=fitz.TEXT_ALIGN_CENTER,
                    color=(0, 0, 0),
                    overlay=True,
                )
                if remaining < 0:
                    raise ValueError(f"balloon number does not fit: {balloon.formal_number}")
        return document.tobytes(garbage=4, deflate=True)
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/exports/test_template_registry.py backend/tests/integration/test_balloon_pdf_renderer.py backend/tests/integration/test_export_preflight.py -q
```

Expected: tests PASS; renderer preserves source page count and writes readable formal numbers; preflight rejects every unregistered or drifted asset.

- [ ] **Step 5: Commit approved assets and PDF export boundary**

```bash
git add backend/app/exports/template_registry.py backend/app/balloons/renderer.py backend/app/capabilities/service.py backend/tests/unit/exports/test_template_registry.py backend/tests/integration/test_balloon_pdf_renderer.py backend/tests/integration/test_export_preflight.py backend/assets/templates/sip-v1.xlsx backend/assets/templates/sip-v1.mapping.json backend/assets/fonts/DejaVuSans.ttf backend/assets/fonts/LICENSE-DejaVu.txt
git commit -m "feat: register export assets and render ballooned PDF"
```

If either asset gate is unresolved, do not run this commit command; report D6-T1 blocked with the exact missing decision.

### Task D6-T2: Generate And Validate The Fixed SIP Workbook

**Files:**

- Create: `backend/app/exports/excel.py`
- Create: `backend/app/exports/naming.py`
- Create: `backend/app/exports/validators.py`
- Test: `backend/tests/unit/exports/test_excel_mapping.py`
- Test: `backend/tests/unit/exports/test_excel_safety.py`
- Test: `backend/tests/unit/exports/test_naming.py`
- Test: `backend/tests/integration/test_excel_export.py`

- [ ] **Step 1: Write failing mapping, capacity, formula and naming tests**

```python
# backend/tests/unit/exports/test_excel_safety.py
from openpyxl import Workbook, load_workbook

from app.exports.excel import set_untrusted_text


def test_untrusted_prefixes_are_escaped_as_text(tmp_path) -> None:
    path = tmp_path / "safe.xlsx"
    book = Workbook()
    for row, value in enumerate(("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)"), start=1):
        set_untrusted_text(book.active.cell(row=row, column=1), value)
    book.save(path)
    reopened = load_workbook(path, data_only=False)
    for row in range(1, 5):
        cell = reopened.active.cell(row=row, column=1)
        assert cell.data_type == "s"
```

```python
# backend/tests/unit/exports/test_excel_mapping.py
import pytest

from app.exports.excel import REQUIRED_DETAIL_FIELDS, CapacityExceeded, assert_capacity


def test_all_fixed_fields_are_mapped(approved_registration) -> None:
    assert set(approved_registration.detail_columns) == REQUIRED_DETAIL_FIELDS


def test_capacity_overflow_is_blocking(approved_registration) -> None:
    with pytest.raises(CapacityExceeded):
        assert_capacity(approved_registration, approved_registration.capacity + 1)
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/exports/test_excel_mapping.py backend/tests/unit/exports/test_excel_safety.py backend/tests/unit/exports/test_naming.py backend/tests/integration/test_excel_export.py -q
```

Expected: collection FAIL for missing Excel executor and naming modules.

- [ ] **Step 2: Implement the fixed field/capacity and untrusted-text rules**

```python
# backend/app/exports/excel.py
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.drawing.image import Image

from app.exports.template_registry import TemplateRegistration


REQUIRED_METADATA_FIELDS = {"material_code", "material_name", "drawing_number", "material", "revision"}
REQUIRED_DETAIL_FIELDS = {
    "balloon_number", "inspection_item", "inspection_standard", "inspection_method",
    "key_dimension", "inspection_role", "source_page",
}


class CapacityExceeded(RuntimeError):
    pass


def set_untrusted_text(cell: Cell, value: object) -> None:
    cell.value = "" if value is None else str(value)
    cell.data_type = "s"


def assert_capacity(registration: TemplateRegistration, detail_count: int) -> None:
    if detail_count > registration.capacity:
        raise CapacityExceeded(f"{detail_count} details exceed capacity {registration.capacity}")


def render_sip_workbook(
    template_path: Path,
    registration: TemplateRegistration,
    metadata: dict[str, object],
    reviewed_items: list[dict],
    page_images: list[Path],
) -> bytes:
    if set(registration.metadata_cells) != REQUIRED_METADATA_FIELDS:
        raise ValueError("fixed metadata mapping is incomplete")
    if set(registration.detail_columns) != REQUIRED_DETAIL_FIELDS:
        raise ValueError("fixed detail mapping is incomplete")
    assert_capacity(registration, len(reviewed_items))
    book = load_workbook(template_path, data_only=False)
    if registration.sheet not in book.sheetnames or registration.image_sheet not in book.sheetnames:
        raise ValueError("registered workbook sheet is missing")
    sheet = book[registration.sheet]
    for field, address in registration.metadata_cells.items():
        set_untrusted_text(sheet[address], metadata[field])
    for offset, item in enumerate(reviewed_items):
        row = registration.first_row + offset
        for field, column in registration.detail_columns.items():
            value = item.get(field, "")
            if field == "balloon_number" and item.get("item_type") == "global_requirement":
                value = ""
            set_untrusted_text(sheet[f"{column}{row}"], value)
    image_sheet = book[registration.image_sheet]
    anchor_cell = image_sheet[registration.image_anchor]
    start_row = anchor_cell.row
    start_column = anchor_cell.column_letter
    for page_index, image_path in enumerate(page_images):
        image = Image(image_path)
        image.anchor = f"{start_column}{start_row + page_index * 45}"
        image_sheet.add_image(image)
    output = BytesIO()
    book.save(output)
    return output.getvalue()
```

`page_images` is produced from the just-rendered formal ballooned PDF at a fixed 150 DPI and passed in source page order. It is not rendered independently from the original PDF.

- [ ] **Step 3: Implement deterministic filename and sheet-name safety**

```python
# backend/app/exports/naming.py
from __future__ import annotations

import re
from pathlib import Path


ILLEGAL_FILE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ILLEGAL_SHEET = re.compile(r"[\\/*?:\[\]]")


def safe_stem(value: str, fallback: str = "inspection") -> str:
    stem = Path(value).name.rsplit(".", 1)[0]
    stem = ILLEGAL_FILE.sub("_", stem).strip(" .")
    return (stem or fallback)[:120]


def unique_sheet_name(value: str, used: set[str]) -> str:
    base = ILLEGAL_SHEET.sub("_", value).strip("'") or "Sheet"
    base = base[:31]
    candidate = base
    suffix = 2
    while candidate.casefold() in {name.casefold() for name in used}:
        marker = f"_{suffix}"
        candidate = f"{base[:31-len(marker)]}{marker}"
        suffix += 1
    used.add(candidate)
    return candidate
```

- [ ] **Step 4: Add reopen, protected-range, editability and image-count validators**

Before writing, `validators.py` snapshots `protected_ranges` and `signoff_ranges` as `(coordinate, value, style_id, merged_membership)`. After writing and reopening with `data_only=False`, it asserts the snapshots are unchanged, all detail cells have `data_type="s"`, the workbook can be saved and reopened a second time, and `len(image_sheet._images) == source_page_count`. Use `openpyxl` only for the fixed approved mapping; do not add a generic template DSL.

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/exports/test_excel_mapping.py backend/tests/unit/exports/test_excel_safety.py backend/tests/unit/exports/test_naming.py backend/tests/integration/test_excel_export.py -q
```

Expected: tests PASS for all 13 fixed output fields, overflow rejection, blank global-requirement number, reviewed-only values, formula safety, protected/sign-off preservation, ordered image embedding, reopen and resave.

- [ ] **Step 5: Commit the fixed SIP executor**

```bash
git add backend/app/exports/excel.py backend/app/exports/naming.py backend/app/exports/validators.py backend/tests/unit/exports/test_excel_mapping.py backend/tests/unit/exports/test_excel_safety.py backend/tests/unit/exports/test_naming.py backend/tests/integration/test_excel_export.py
git commit -m "feat: generate controlled SIP workbooks"
```

### Task D6-T3: Publish Three Artifacts Through One Export Owner

**Files:**

- Create: `backend/app/exports/models.py`
- Create: `backend/app/exports/schemas.py`
- Create: `backend/app/exports/manifest.py`
- Create: `backend/app/exports/service.py`
- Create: `backend/app/exports/router.py`
- Create: `.agent/harness/scripts/verify-export-consistency.py`
- Modify: `backend/app/main.py`
- Generate: `backend/alembic/versions/0006_exports.py`
- Test: `backend/tests/unit/exports/test_manifest.py`
- Test: `backend/tests/integration/test_export_consistency.py`
- Test: `backend/tests/integration/test_export_atomicity.py`

- [ ] **Step 1: Write failing manifest, consistency and partial-publication tests**

```python
# backend/tests/integration/test_export_atomicity.py
import pytest


@pytest.mark.parametrize("failure_point", ["pdf", "excel", "manifest", "publish"])
def test_no_artifact_is_downloadable_after_subartifact_failure(export_service_factory, reviewed_result, failure_point) -> None:
    export_service = export_service_factory(failing_executor=failure_point)
    export = export_service.create(reviewed_result.id)
    assert export.status == "failed"
    for kind in ("ballooned_pdf", "sip_excel", "manifest"):
        assert export_service.download_ref(export.id, kind) is None
```

```python
# backend/tests/integration/test_export_consistency.py
def test_artifacts_share_reviewed_result_id(completed_export) -> None:
    assert completed_export.pdf.reviewed_result_id == completed_export.reviewed_result_id
    assert completed_export.excel.reviewed_result_id == completed_export.reviewed_result_id
    assert completed_export.manifest["reviewed_result_id"] == str(completed_export.reviewed_result_id)
```

Run:

```bash
micromamba run -n qi-p0 pytest backend/tests/unit/exports/test_manifest.py backend/tests/integration/test_export_consistency.py backend/tests/integration/test_export_atomicity.py -q
```

Expected: collection FAIL for missing export aggregate/orchestrator.

- [ ] **Step 2: Implement the versioned manifest schema**

```python
# backend/app/exports/manifest.py
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ArtifactDigest:
    kind: str
    filename: str
    sha256: str
    size_bytes: int
    reviewed_result_id: str


@dataclass(frozen=True)
class ExportManifest:
    schema_version: str
    export_id: str
    project_id: str
    reviewed_result_id: str
    input_pdf_sha256: str
    template_id: str
    template_version: str
    template_sha256: str
    mapping_version: str
    font_sha256: str
    renderer_version: str
    reviewed_item_count: int
    balloon_required_count: int
    balloon_count: int
    source_page_count: int
    artifacts: tuple[ArtifactDigest, ...]

    def to_bytes(self) -> bytes:
        payload = asdict(self)
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
```

Manifest lists only the PDF and Excel digests because including its own digest would be recursive. The database `ExportArtifact` row records the manifest hash after serialization.

- [ ] **Step 3: Implement the one-owner staging and publication transaction**

`ExportJob` has `id/project_id/reviewed_result_id/status/error_id/created_at/completed_at`; `ExportArtifact` has `export_id/kind/staging_ref/published_ref/sha256/size_bytes/reviewed_result_id`. One unique constraint covers `(export_id, kind)` and another covers one successful export per `(reviewed_result_id, template_version, mapping_version, renderer_version)`.

The service sequence is exact:

```text
claim logical export key
→ preflight template/font/storage/reviewed-result
→ create status=running
→ write ballooned PDF to exports/.staging/{export_id}/
→ reopen/validate PDF
→ rasterize that PDF in page order
→ write fixed SIP Excel to the same staging prefix
→ reopen/validate Excel
→ run count/number/reviewed-result cross-checks
→ write and parse manifest
→ copy verified bytes to exports/{export_id}/
→ in one DB transaction set all published_ref values and status=success
```

On any exception, set `status=failed`, persist one structured error with artifact scope, and leave all `published_ref` values null. Download lookup always joins `ExportJob.status == "success"`; staging refs are never returned by the API.

- [ ] **Step 4: Add cross-artifact Veto Gates and API routes**

The final validator blocks unless all conditions hold:

```python
def assert_export_counts(reviewed_items: list[dict], balloons: list[dict], excel_rows: list[dict]) -> None:
    active_items = [item for item in reviewed_items if item["active"]]
    required = [item for item in active_items if item["balloon_required"]]
    if len(excel_rows) != len(active_items):
        raise ValueError("excel detail count mismatch")
    if len(balloons) != len(required):
        raise ValueError("balloon count mismatch")
    pdf_numbers = [item["formal_number"] for item in balloons]
    excel_numbers = [row["balloon_number"] for row in excel_rows if row["balloon_number"] != ""]
    if pdf_numbers != excel_numbers:
        raise ValueError("PDF and Excel balloon numbers differ")
```

Routes:

```text
POST /api/v1/projects/{project_id}/exports
GET  /api/v1/exports/{export_id}
GET  /api/v1/exports/{export_id}/downloads/{ballooned_pdf|sip_excel|manifest}
```

Run:

```bash
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
micromamba run -n qi-p0 pytest backend/tests/unit/exports/test_manifest.py backend/tests/integration/test_export_consistency.py backend/tests/integration/test_export_atomicity.py -q
python .agent/harness/scripts/check-contracts.py
python .agent/harness/scripts/verify-export-consistency.py fixture --task D6-T3
python .agent/harness/scripts/run-p0.py fixture --scope task --task D6-T3
```

Expected: tests PASS; success exposes exactly three downloads; test-only executor replacement exposes zero on failure; every artifact references the same immutable reviewed result. Production service inputs contain no failure flag.

- [ ] **Step 5: Commit the export Owner**

```bash
git add backend/app/exports/models.py backend/app/exports/schemas.py backend/app/exports/manifest.py backend/app/exports/service.py backend/app/exports/router.py backend/app/main.py backend/alembic/versions/0006_exports.py .agent/harness/scripts/verify-export-consistency.py backend/tests/unit/exports/test_manifest.py backend/tests/integration/test_export_consistency.py backend/tests/integration/test_export_atomicity.py
git commit -m "feat: publish atomic three-artifact exports"
```

## Day 7 — Failure Proof, Current-Four Live Run And Policy Verdict

### Task D7-T1: Close Failure Injection Through The Existing Harness

**Files:**

- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/generate-receipt.py`
- Modify: `.agent/harness/policy/failure-severity-policy.yaml`
- Create: `backend/tests/e2e/test_offline_vertical.py`
- Create: `backend/tests/e2e/test_no_silent_success.py`
- Test: `backend/tests/e2e/test_offline_vertical.py`
- Test: `backend/tests/e2e/test_no_silent_success.py`

- [ ] **Step 1: Write failing offline-chain and dependency-boundary failure tests**

```python
# backend/tests/e2e/test_no_silent_success.py
import pytest


@pytest.mark.parametrize(
    "failure_point",
    ["provider", "storage", "template", "font", "ballooned_pdf", "sip_excel", "manifest"],
)
def test_p0_acc_007_no_silent_success(vertical_system, frozen_reviewed_result, failure_point) -> None:
    vertical_system.replace_dependency_with_failure(failure_point)
    export_id = vertical_system.export(frozen_reviewed_result.id)
    assert vertical_system.export_status(export_id) == "failed"
    assert vertical_system.formal_downloads(export_id) == []
    error = vertical_system.export_error(export_id)
    assert error["stage"] == failure_point
    assert error["severity"] in {"fatal", "blocking"}
```

`backend/tests/e2e/test_offline_vertical.py` uses a synthetic two-page PDF plus sanitized Harness Provider fixtures, calls the actual public service boundaries, and asserts:

```text
processing → ready_for_edit → editing → reviewed → exporting → export_succeeded
raw_automatic_result.id != review_working_copy.id != reviewed_result.id
all formal artifacts reference one reviewed_result_id
fixture mode opens zero Provider network connections
```

- [ ] **Step 2: Run focused tests and observe missing failure orchestration**

```bash
micromamba run -n qi-p0 pytest backend/tests/e2e/test_offline_vertical.py backend/tests/e2e/test_no_silent_success.py -q
```

Expected: tests FAIL because the vertical fixture and dependency replacement boundary are not complete.

- [ ] **Step 3: Implement test-only failure replacement and Harness failure mode**

Failure injection exists only through test dependency replacement. Production API/service inputs never accept `inject_failure` or a hidden query flag.

`run-p0.py failure --scope task --task D7-T1` must:

1. create a new run ID and `run.json` before test execution;
2. select `P0-ACC-007` and its `phase://failure/no-silent-success` selector from `p0-contracts.json`;
3. internally dispatch that phase, run the registered backend E2E command and attach evidence to the same open run; it must not invoke `run-p0.py` as a child;
4. save command, exit code, timestamps and structured error evidence;
5. emit one `contract-results.json` entry for `P0-ACC-007`;
6. call `generate-receipt.py` under the checked-in policies;
7. seal the run directory.

No failure test may leave `published_ref` or a normal download visible.

- [ ] **Step 4: Run failure and fixture phases, then inspect immutable evidence**

```bash
python .agent/harness/scripts/check-contracts.py
python .agent/harness/scripts/run-p0.py failure --scope task --task D7-T1
```

Expected: the command prints one schema-valid run ID containing exactly one `P0-ACC-007` result plus `run.json`, `contract-results.json`, `receipt.json` and the declared `logs/reports/artifacts` directories. Test-only dependency failure passes the contract by proving application failure is explicit; no nested run is created and the task-scope receipt is `passed` without claiming formal P0 passed.

- [ ] **Step 5: Commit failure proof code, never run output**

```bash
git status --short .agent/harness/runs
git add .agent/harness/scripts/run-p0.py .agent/harness/scripts/generate-receipt.py .agent/harness/policy/failure-severity-policy.yaml backend/tests/e2e/test_offline_vertical.py backend/tests/e2e/test_no_silent_success.py
git commit -m "test: prove P0 failures cannot publish"
```

Expected: ignored run outputs are absent from the staged set.

### Task D7-T2: Execute One Current-Four Live Run With Browser And Human Evidence

**Files:**

- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `.agent/harness/scripts/stage-current-four.py`
- Create: `.agent/harness/scripts/record-human-verdict.py`
- Create: `backend/tests/contract/harness/test_live_run_contract.py`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/p0-workbench.spec.ts`
- Runtime only: `.agent/harness/runs/$QI_P0_RUN_ID/`

- [ ] **Step 1: Write failing live-run identity and browser-flow tests**

```python
# backend/tests/contract/harness/test_live_run_contract.py
import json


def test_live_run_contains_exact_current_four_and_no_missing_phase(live_run_dir) -> None:
    run = json.loads((live_run_dir / "run.json").read_text())
    manifest = json.loads((live_run_dir / "artifacts/current-four-manifest.json").read_text())
    results = json.loads((live_run_dir / "contract-results.json").read_text())
    assert run["mode"] == "live"
    assert run["scope"] == "full-p0"
    assert len(manifest["files"]) == 4
    assert len({row["sha256"] for row in manifest["files"]}) == 4
    assert manifest["files"][0]["sha256"].startswith("58b9cf08")
    assert all("source_path" not in row for row in manifest["files"])
    assert run["phases"] == ["process", "candidates", "review", "balloons", "export", "consistency"]
    assert len(results["contracts"]) == 111
    assert len({row["p0_contract_id"] for row in results["contracts"]}) == 111
    assert run.get("child_run_ids", []) == []
```

```ts
// frontend/e2e/p0-workbench.spec.ts
import { expect, test } from "@playwright/test";

test("P0-ACC-003 P0-ACC-004 performs explicit review and balloon operations", async ({ page }) => {
  const projectUrl = process.env.QI_P0_PROJECT_URL;
  if (!projectUrl) throw new Error("QI_P0_PROJECT_URL is required");
  await page.goto(projectUrl);
  await page.getByRole("button", { name: "Keep" }).first().click();
  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel("Inspection standard").fill("human-reviewed trial value");
  await page.getByRole("button", { name: "Add Inspection Item" }).click();
  await page.getByLabel("New inspection item").fill("manual current-four trial item");
  await page.getByLabel("Requires confirmation").check();
  await page.getByRole("button", { name: "Add Item" }).click();
  await page.getByRole("button", { name: "Resolve Confirmation" }).last().click();
  await page.getByRole("button", { name: "Exclude" }).last().click();
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: "Freeze Items" }).click();
  await page.getByRole("button", { name: "Generate Balloons" }).click();
  await page.getByTestId("balloon-overlay").first().dragTo(page.getByTestId("balloon-drop-target"));
  await page.getByRole("button", { name: "Delete Balloon" }).first().click();
  await page.getByRole("button", { name: "Rebuild Balloon" }).first().click();
  await page.getByRole("button", { name: "Renumber" }).click();
  await expect(page.getByText("Numbering valid")).toBeVisible();
});
```

- [ ] **Step 2: Run contract discovery and observe live orchestration is incomplete**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_live_run_contract.py -q
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
```

Expected: backend test FAIL because no live run fixture/orchestration exists; Playwright discovery succeeds only after its config exists.

- [ ] **Step 3: Extend the minimal runner with bounded current-four phases**

`run-p0.py live --scope full-p0 --input-set current-four` is the only formal live entry. It must fail before creating a paid task unless all conditions hold:

- explicit `live` mode and `current-four` input set;
- `QI_CURRENT_FOUR_SOURCE_ROOT` points to the known source directory;
- server-side credentials/config pass preflight without being printed;
- template/font gates are approved;
- Provider call policy and total budget are loaded;
- executable-content identity、diagnostic Git revision、config hashes、`contract_definition_hash` and start-time `status_projection_hash` are captured.

The runner creates one run ID and keeps it open until all evidence is complete. `stage-current-four.py` attaches the identity manifest to that run without copying PDFs or creating a child run. The runner then:

1. loads all 111 mirror rows and groups identical ordinary command selectors so each command runs once while producing one result per mapped P0 ID;
2. executes all registered unit/provider-contract/integration/frontend/export/failure selectors inside the same run identity and captures their logs/exit codes;
3. resolves `phase://failure/no-silent-success` and all `phase://live/*` selectors by internal dispatch, never by invoking another runner;
4. executes the live sample chain below, first completing the fixed first-PDF checkpoint and stopping on failure, then processing the remaining three in manifest order;
5. writes exactly 111 unique results before receipt evaluation.

The live sample chain is:

```text
process
→ candidates
→ browser review and balloons
→ human verdict
→ final reviewed_result
→ export
→ independent consistency verification
→ contract result aggregation
→ receipt generation
```

For each sample it records source hash/page facts, project/result/export IDs, phase state, P0 contract IDs, command/HTTP/browser evidence, artifact refs and verdict. The first sample must complete every arrow before any phase starts for sample two. `record-human-verdict.py` requires a non-empty operator ID/note and explicit answers for `candidates_are_editable` and `not_false_success` for all four samples; it cannot prefill affirmative values.

Playwright is invoked once per project with runner-supplied `QI_P0_PROJECT_URL`. Merge or split is exercised only where the data exposes an applicable operation; inapplicability is recorded, not fabricated.

- [ ] **Step 4: Start the stack and execute the explicit live run**

```bash
export QI_CURRENT_FOUR_SOURCE_ROOT='/home/reggie/文档/xwechat_files/wxid_ut5o9e1igztd22_f3a1/msg/attach/93a055933fee8f63da748e2314c2e233/2026-07/Rec/17d107a16f0cf6e9/F'
docker compose up -d --build postgres redis api worker frontend
micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
curl --fail --silent http://localhost:8000/api/v1/health
QI_P0_RUN_ID="$(python .agent/harness/scripts/run-p0.py live --scope full-p0 --input-set current-four --print-run-id-only)"
test -n "$QI_P0_RUN_ID"
test -f ".agent/harness/runs/$QI_P0_RUN_ID/run.json"
test -f ".agent/harness/runs/$QI_P0_RUN_ID/contract-results.json"
test -f ".agent/harness/runs/$QI_P0_RUN_ID/receipt.json"
```

Expected: the command remains within Provider policy, first closes the fixed first PDF then processes exactly the remaining three frozen identities/six total pages, records actual browser operations and human answers, produces three validated artifacts per sample, writes exactly 111 unique contract results, creates no nested run, and seals one immutable run. A negative human answer, budget exhaustion, missing selector/phase, stale input or any blocking result makes the receipt failed/blocked.

- [ ] **Step 5: Commit live orchestration code and keep evidence ignored**

```bash
git status --short .agent/harness/runs
git add .agent/harness/scripts/run-p0.py .agent/harness/scripts/stage-current-four.py .agent/harness/scripts/record-human-verdict.py backend/tests/contract/harness/test_live_run_contract.py frontend/playwright.config.ts frontend/e2e/p0-workbench.spec.ts
git commit -m "test: add current-four live acceptance run"
```

Do not stage source PDFs, credentials, human notes, generated exports, run directories or receipts. A sanitized summary enters `baselines/` only after an explicit later approval.

### Task D7-T3: Enforce Final Receipt, Rollback Proof And Independent Review

**Files:**

- Modify: `.agent/harness/scripts/generate-receipt.py`
- Create: `.agent/harness/scripts/summarize-run.py`
- Create: `backend/tests/contract/harness/harness_test_support.py`
- Create: `backend/tests/contract/harness/test_receipt_policy.py`
- Modify after fresh evidence only: `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`

- [ ] **Step 1: Write failing stale/not-run/code-mismatch receipt tests**

```python
# backend/tests/contract/harness/test_receipt_policy.py
from datetime import UTC, datetime, timedelta

import pytest

from harness_test_support import ReceiptRejected, evaluate_receipt


@pytest.mark.parametrize("defect", ["stale", "not_run", "code_mismatch", "missing_current_four", "blocking_failed"])
def test_defective_evidence_cannot_produce_passed_receipt(valid_run_evidence, defect) -> None:
    evidence = valid_run_evidence.with_defect(defect)
    with pytest.raises(ReceiptRejected):
        evaluate_receipt(evidence)
```

- [ ] **Step 2: Run and then implement exact policy evaluation**

```bash
micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_receipt_policy.py -q
```

Expected before implementation: FAIL because strict receipt evaluation support is missing.

`generate-receipt.py` must reject a passed verdict unless:

1. `run.json`, `contract-results.json` and all referenced artifacts validate against checked-in schemas;
2. executable-content/config/input identities and `contract_definition_hash` match the completed run and no executable/definition/source changed during execution；Git revision is diagnostic, and `status_projection_hash` is recorded but status-only drift/commit is not stale;
3. receipt age is within policy freshness;
4. exactly 111 unique P0 results exist;
5. every fatal/blocking contract is `passed` and `not_run_count=0`;
6. current-four has exactly four frozen hashes and every required live phase;
7. every sample has an affirmative human trial verdict;
8. PDF/Excel/manifest are present, hash-valid and bound to one reviewed result per sample;
9. failure proof `P0-ACC-007` is passed;
10. the mirror and typed bindings still match the two Markdown Owners, with no primary/related relation collapse and no unbound P0-stage global.

`summarize-run.py --run-id` prints counts and artifact refs only; it never edits policy, contracts, run evidence or receipt.

- [ ] **Step 3: Run a migration rollback drill against one dedicated disposable database**

```bash
docker compose exec -T postgres createdb -U qi qi_p0_rollback
QI_DATABASE_URL=postgresql+psycopg://qi:qi@localhost:5432/qi_p0_rollback   micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
QI_DATABASE_URL=postgresql+psycopg://qi:qi@localhost:5432/qi_p0_rollback   micromamba run -n qi-p0 alembic -c backend/alembic.ini downgrade base
QI_DATABASE_URL=postgresql+psycopg://qi:qi@localhost:5432/qi_p0_rollback   micromamba run -n qi-p0 alembic -c backend/alembic.ini upgrade head
docker compose exec -T postgres dropdb -U qi qi_p0_rollback
```

Expected: upgrade/downgrade/upgrade pass; only `qi_p0_rollback` is deleted. Normal runtime data, source files and run evidence remain untouched.

- [ ] **Step 4: Run the complete fresh gate and update trace status only from that run**

The standalone pytest/frontend/build commands below are fail-fast prechecks only and are not receipt evidence. The subsequent full-p0 runner re-executes every registered selector under its single run identity and is the sole source of the 111 contract results.

```bash
python .agent/harness/scripts/check-contracts.py
micromamba run -n qi-p0 pytest backend/tests -q
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
QI_FINAL_RUN_ID="$(python .agent/harness/scripts/run-p0.py live --scope full-p0 --input-set current-four --print-run-id-only)"
test -n "$QI_FINAL_RUN_ID"
python .agent/harness/scripts/generate-receipt.py --check-run "$QI_FINAL_RUN_ID"
python .agent/harness/scripts/summarize-run.py --run-id "$QI_FINAL_RUN_ID"
git diff --check
```

Expected summary:

```text
contracts=111
passed=111
failed=0
blocked=0
not_run=0
stale=0
current_four=4
artifacts_per_sample=3
overall_verdict=passed
```

Only after this output may the executor change affected `current_status` values in the P0 traceability matrix, regenerate `p0-contracts.json` and typed bindings, and rerun `check-contracts.py` plus `generate-receipt.py --check-run "$QI_FINAL_RUN_ID"`. That second check must prove `contract_definition_hash` and executable-content identity are unchanged while only `status_projection_hash` changed; a later commit containing only those projections may change diagnostic Git revision without staling the receipt. Any executable、requirement、Owner、task、tier、selector、blocking or policy change invalidates the receipt and requires a new full run. The run directory remains the evidence Owner; the Markdown status is only its current projection.

After editing only `current_status`, run:

```bash
python .agent/harness/scripts/generate-contract-mirror.py
python .agent/harness/scripts/generate-global-bindings.py
python .agent/harness/scripts/check-contracts.py
python .agent/harness/scripts/generate-receipt.py --check-run "$QI_FINAL_RUN_ID"
```

Expected: mirror/bindings are synchronized, the status projection changes, the definition hash remains identical to the run, and the same receipt still validates without mutating the sealed run.

- [ ] **Step 5: Request independent review, resolve blockers and commit the final gate**

Use `superpowers:requesting-code-review` with a read-only reviewer. Require a verdict on global/P0/mirror authority, Owner uniqueness, raw/working/reviewed separation, item-set/final-confirm order, coordinates, Provider trust, formula/path safety, all-or-nothing publication, current-four evidence, receipt freshness and P1/P2 exclusion.

Verify every blocking claim directly. If code or policy changes, discard the previous verdict for release purposes and create a new full live run before updating status.

```bash
git add .agent/harness/scripts/generate-receipt.py .agent/harness/scripts/summarize-run.py backend/tests/contract/harness/harness_test_support.py backend/tests/contract/harness/test_receipt_policy.py docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md .agent/harness/contracts/p0-contracts.json .agent/harness/contracts/global-contract-bindings.json
git commit -m "test: enforce immutable P0 release evidence"
```

Do not declare P0 complete when the reviewer rejects, an external gate is unresolved, a human verdict is negative, any blocking result is not passed, the receipt is stale, or any required command was not run.

## Architecture Reference Decisions

- Adopt the normalized PDF-coordinate/overlay separation and browser interaction test shape from [react-pdf-highlighter](https://github.com/agentcooper/react-pdf-highlighter) (MIT); keep our persisted Owner in backend PDF coordinates rather than copying its frontend state model.
- Use documented [PyMuPDF](https://github.com/pymupdf/PyMuPDF) page drawing, text insertion and reopen validation APIs. Its AGPL/commercial licensing must be resolved before proprietary distribution; no upstream source code is copied.
- [Docling](https://github.com/docling-project/docling) was inspected and skipped for P0 because its broad document pipeline would duplicate the narrow page-inventory/candidate Owners and expand scope.
- Tencent adapter tests pin the official `GeneralAccurateOCR` parameters `ConfigID=OCR`, `WordsType="2"`, `IsWords=false`, `EnableDetectSplit=true` from the [Tencent API contract](https://cloud.tencent.com/document/api/866/34937).
- Qwen adapter tests pin the official OpenAI-compatible image request shape, explicit JSON instruction/`response_format={"type":"json_object"}` and `enable_thinking=false` behavior from [Qwen-VL compatibility](https://help.aliyun.com/zh/model-studio/qwen-vl-compatible-with-openai) and [structured output](https://help.aliyun.com/zh/model-studio/qwen-structured-output).

## Plan Self-Review

### Writing-Plan Architecture Diff

- 新增 69 条长期 global contracts，并将 111 条 Section 10.1 P0 atoms 重构为独立 traceability matrix；二者不再混写。
- Day 1 提前建立最小 `.agent/harness/` 骨架：policy、schema、单向生成的 mirror/bindings、contract checker、run/receipt 约定和 ignored immutable runs。
- Bindings 明确拆成 primary、related-business、related-implementation；receipt 绑定排除 `current_status` 的 definition hash，避免 status projection 更新让当前 run 自失效。
- current-four staging 与 coordinate tests 在 `D2-T1`，Provider contract fixtures 在 `D2-T2`，export consistency 在 `D6-T3`；业务 pytest/frontend tests 始终留在原测试目录。
- `D1-T2` 至 `D6-T3` 的每个业务任务都在本任务结束时完成 contract 引用、测试 selector、mirror regeneration、`check-contracts.py` 和 focused Harness phase，不把接线集中拖到 Day 7。
- Day 7 只通过显式 live/full-p0 mode 创建独立 run ID；同一 runner 执行全部普通 selectors、内部 dispatch Harness phases、先闭合 first PDF，再聚合 111 条 result 并按 policy 生成 receipt。可变 latest pointer、nested run 和旧 receipt 都不能充当本次证据。
- 仍是 20 个 implementation tasks，保留第一份 PDF 的纵向链路和 Day 1～Day 7 依赖；没有把任何 P1/P2 contract 加入七天 P0。

Before execution handoff, run these docs-only checks:

```bash
python3 - <<'PY'
import re
from collections import Counter
from pathlib import Path

tick = chr(96)
global_path = Path("docs/contracts/MAIN_CONTRACT_MATRIX.md")
p0_path = Path("docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md")
plan_path = Path("docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md")
global_text = global_path.read_text(encoding="utf-8")
p0_text = p0_path.read_text(encoding="utf-8")
plan = plan_path.read_text(encoding="utf-8")

global_line = re.compile(
    r"^\| "
    + re.escape(tick)
    + r"(?P<id>(?:SYS|PRJ|PDF|CAND|ITEM|REV|BAL|EXP|PROV|DIAG)-\d{3})"
    + re.escape(tick)
    + r" \|"
)
global_lines = [line for line in global_text.splitlines() if global_line.match(line)]
global_rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in global_lines]
global_ids = [row[0].strip(tick) for row in global_rows]
global_domains = Counter(row[1].strip(tick) for row in global_rows)
global_stages = Counter(row[10].strip(tick) for row in global_rows)
stage_by_global = {row[0].strip(tick): row[10].strip(tick) for row in global_rows}
defined_rules = set(
    re.findall(r"^\| " + re.escape(tick) + r"((?:CR|BR)-[A-Z]+)" + re.escape(tick) + r" \|", global_text, re.M)
)
assert len(global_rows) == 69
assert len(set(global_ids)) == 69
assert all(len(row) == 11 for row in global_rows)
assert global_domains == {
    "SYS": 7, "PRJ": 8, "PDF": 8, "CAND": 7, "ITEM": 7,
    "REV": 6, "BAL": 7, "EXP": 9, "PROV": 5, "DIAG": 5,
}
assert global_stages == {"P0": 37, "P0-partial": 24, "P1": 4, "P2": 4}
assert all(row[7].strip(tick).startswith("CR-") for row in global_rows)
assert all(row[8].strip(tick).startswith("BR-") for row in global_rows)
assert all(
    set(re.findall(r"(?:CR|BR)-[A-Z]+", row[7] + " " + row[8])) <= defined_rules
    for row in global_rows
)

p0_lines = [line for line in p0_text.splitlines() if line.startswith("| " + tick + "P0-")]
p0_rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in p0_lines]
p0_ids = [row[0].strip(tick) for row in p0_rows]
p0_domains = Counter(contract_id.split("-")[1] for contract_id in p0_ids)
expected_p0_domains = {
    "RUN": 14, "REC": 28, "REV": 13, "BAL": 14,
    "UI": 8, "EXP": 19, "RES": 8, "ACC": 7,
}
assert len(p0_rows) == 111
assert len(set(p0_ids)) == 111
assert all(len(row) == 12 for row in p0_rows)
assert p0_domains == expected_p0_domains

implementation_only = []
business = []
bound_globals = set()
task_matches = list(re.finditer(r"^### Task (D[1-7]-T[1-3]):", plan, re.M))
task_sections = {}
for index, match in enumerate(task_matches):
    end = task_matches[index + 1].start() if index + 1 < len(task_matches) else plan.index(
        "## Architecture Reference Decisions", match.end()
    )
    task_sections[match.group(1)] = plan[match.start():end]

for row in p0_rows:
    global_id = row[1].strip(tick)
    is_implementation_only = row[2].strip(tick) == "true"
    related = row[3].strip(tick)
    related_ids = set(re.findall(r"(?:SYS|PRJ|PDF|CAND|ITEM|REV|BAL|EXP|PROV|DIAG)-\d{3}", related))
    task = row[6].strip(tick)
    selector = row[8].strip(tick)
    status = row[10].strip(tick)
    reason = row[11].strip()
    assert "### Task " + task + ":" in plan
    assert selector and selector != "—"
    assert status in {"passed", "failed", "blocked", "not_run"}
    assert related_ids <= set(stage_by_global)
    assert all(stage_by_global[item] not in {"P1", "P2", "designed-not-enforced"} for item in related_ids)
    bound_globals.update(related_ids)
    pytest_target = re.search(r"pytest\s+([^ ]+)", selector)
    npm_target = re.search(r"npm --prefix frontend test -- --run\s+([^ ]+)", selector)
    python_target = re.search(r"python\s+(\.agent/harness/scripts/[^ ]+)", selector)
    selector_targets = []
    if pytest_target:
        selector_targets.append(pytest_target.group(1).split("::")[0])
    if npm_target:
        selector_targets.append("frontend/" + npm_target.group(1))
    if python_target:
        selector_targets.append(python_target.group(1))
    assert all(target in task_sections[task] for target in selector_targets)
    assert "run-" + "p0.py" not in selector
    if is_implementation_only:
        assert global_id == "null"
        assert related not in {"", "[]", "—"}
        assert reason not in {"", "—"}
        implementation_only.append(row)
    else:
        assert global_id in stage_by_global
        assert stage_by_global[global_id] not in {"P1", "P2", "designed-not-enforced"}
        bound_globals.add(global_id)
        business.append(row)

assert len(implementation_only) == 10
assert len(business) == 101
required_bound_globals = {item for item, stage in stage_by_global.items() if stage in {"P0", "P0-partial"}}
assert required_bound_globals <= bound_globals
root_harness_pattern = r"(?m)(?<![A-Za-z0-9_./])" + "har" + "ness/"
assert re.search(root_harness_pattern, plan) is None
assert "." + "agent/" + "har" + "ness/tests/" not in plan
assert "artifacts/" + "input/" not in plan
assert "First-PDF-First Execution Rule" in plan
assert "JS26032501-1-03-036#上下座B#A1.pdf" in plan
assert chr(167) not in global_text + p0_text + plan
forbidden = (
    "TO" + "DO",
    "T" + "BD",
    "FIX" + "ME",
    "implement " + "later",
    "appropriate error " + "handling",
    "Similar " + "to",
)
assert not any(token.casefold() in plan.casefold() for token in forbidden)
print(
    "global=69 p0=111 mapped=101 implementation_only=10 "
    "unclassified=0 unbound_p0_stage_global=0 selector_targets_missing=0 "
    "p1_p2_task_leak=0 root_harness_paths=0"
)
PY
git diff --check -- docs/contracts/MAIN_CONTRACT_MATRIX.md docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md
```

Self-review verdict is `ready_for_execution_with_external_gates`:

- global matrix 不依赖七天任务，P0 matrix 不再被称作 Main Contract Matrix；
- `p0-contracts.json` 只有 P0 Markdown 一个可编辑来源，bindings 只能生成；
- `.agent/harness/` 不承载业务测试，所有 Harness scripts 都在 `.agent/harness/scripts/`；
- P1/P2 没有进入 20 个 P0 tasks，111 条 P0 ID 全部保留；
- Day 1 只建立最小骨架，第一份 PDF 纵向链路和 Section 10 唯一实施范围保持不变；
- template approval、font/license approval、live Provider credentials 和 human trial 仍是执行期外部 gates，不能由计划或旧 receipt 代替。
