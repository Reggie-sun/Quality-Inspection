# Structured Geometric Tolerance Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把工程图 feature-control frame 从三类视觉 subtype + 四字段 coarse fallback，升级为可追溯、可审核、可持久化、可通过 API/UI/export 消费的结构化几何公差候选。

**Architecture:** PDF inventory 新增 versioned `GdtFrameObservation`，native vector 与 raster page 都提交相同的有序 frame/cell evidence；现有 Qwen visual call 升级为 `visual-symbol-review/3`，只提供 symbol/cell signal。唯一业务 Owner `GeometricToleranceNormalizer` 在 candidate domain 内验证并生成 typed `GeometricToleranceCandidate`；review、API、frontend 和 export 只消费该 canonical payload，不解析 `raw_text`。历史 `geometric_tolerance` coarse JSONB 迁移为 typed `unknown`，不猜测 subtype。

**Tech Stack:** Python 3.11、Pydantic、PyMuPDF、Pillow、Qwen VL、JSON Schema、SQLAlchemy、Alembic、PostgreSQL JSONB、FastAPI/OpenAPI、pytest、TypeScript、React、Vitest、Playwright、Micromamba `qi-p0`

## Global Constraints

- Selected lane: `Heavy`，因为本计划改变稳定 candidate/OpenAPI schema、JSONB data shape、Provider response contract，并跨 PDF、candidate、review、API、frontend、export data-integrity boundary。
- Plan status: `selected as the current plan for this execution`。本文件不覆盖 `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`，也不改变 current P0 contract matrix、public runtime config 或 production deployment；GDT-10 isolated verification runtime 的 frozen recognition identity 由本计划的 timeout amendment 明确约束。
- Design source: `docs/superpowers/specs/2026-08-01-structured-geometric-tolerance-recognition-design.md`。
- GDT-10 timeout design source: `docs/superpowers/specs/2026-08-01-provider-timeout-retry-and-partial-failure-design.md`。
- Current-state source: `docs/superpowers/audits/2026-08-01-geometric-tolerance-recognition-current-state.md`。
- Live evidence source: `docs/superpowers/audits/evidence/2026-08-01-geometric-tolerance-live-receipt.json`。
- Execution activation: 用户必须明确将本文件选为唯一 current plan，并点名从 `GDT-1` 开始；不得与七天 P0 task 并行执行。
- Execution worktree: 激活时先使用 `superpowers:using-git-worktrees` 创建独立 worktree；不得直接在有无关 dirty files 的 `main` 写入。
- Baseline: 本计划基于 `main@3efe3eb2fa60c2fe112dc866b7de2114ee87b6d6` 和 Alembic head `0012_recognition_preview`；执行前若 main/head 已变化，先做 overlap gate 并 amend 文件路径/revision，不得盲写第二个 `0013`。
- Single semantic Owner: `backend/app/candidates/geometric_tolerance.py::GeometricToleranceNormalizer`。
- Signal Providers: PDF frame proposal、OCR、Qwen VL 只提交 evidence/confidence；不得提交 final subtype/value/datum graph、review status 或 export 语义。
- Canonical shape: `frames[] -> segments[]` 是唯一层级；top-level `tolerance_type`、`tolerance_symbol`、`tolerance_value`、`datum_references` 只由 `frames[0].segments[0]` 派生。
- v1 standards decision: `standard_context="unspecified"`，保留原始 glyph/token，不静默解释 GB/ISO/ASME 差异。
- v1 glyph decision: 接受 `▱` 作为 flatness input alias，canonical symbol 固定为 `⏥`，原图 glyph 保留在 evidence/raw text。
- v1 modifier set: `maximum_material_condition`、`least_material_condition`、`regardless_of_feature_size`、`unknown`；diameter zone 使用独立 boolean。
- Advanced modifier decision: projected zone、tangent plane、free state、statistical tolerance 不进入 v1；遇到时输出 `unknown` + review required。
- Failure boundary: frame/cell/value/datum/modifier/composite 任一不确定时 fail closed，产生 typed `unknown` 或 Coverage ambiguity，不产生新的 GD&T `CoarseCandidate`。
- No frontend parser: frontend 不得从 `raw_text`、glyph 或 Provider diagnostic 重建 subtype、value、datum 或 modifier。
- No new dependency: raster v1 使用已有 Pillow；不得引入 OpenCV、第二个 Vision Provider、shadow pipeline 或 feature flag。
- Persistence: canonical candidate 继续进入现有 JSONB columns，但写入前必须通过 exact Pydantic model；本计划包含 `automatic-result/3`、`reviewed-result/3` 和 Alembic JSONB migration。
- Historical rule: 旧 `coarse_type="geometric_tolerance"` 迁移为 typed `tolerance_type="unknown"`，保留 `raw_text`/coordinates/source IDs 并强制人工确认；migration 不从旧文本推断 subtype。
- Unchanged contracts: Coverage exact-once、Provider non-owner、review/freeze/export 只消费同一 reviewed result、PDF coordinates、blocking/fatal 不转 success。
- Writer ownership: 一个 write-capable executor 严格按 `GDT-1 -> GDT-10`；`backend/app/candidates/symbol_review.py`、`backend/app/processing/automatic_result.py`、review schemas/service、OpenAPI snapshot 和 frontend API types 不允许并发 writer。
- Review gates: `GDT-5`、`GDT-6`、`GDT-8` 和 `GDT-10` 后各做一次独立 read-only reviewer gate；reviewer 不修改文件。
- Commit discipline: 每个 Task 只 stage 该 Task 的明确文件并单独 commit；禁止 `git add .`。
- `github-oss-fusion`: execution 在 `GDT-2` 开始前使用一次，只研究 license-safe frame/cell segmentation、OCR token association 和 GD&T test corpus patterns；不得复制大段实现或扩展本计划 scope。

## Plan Selection Record

- Selected lane: `Heavy`。
- Selected plan: 本文件由用户显式选为 current plan，并在独立 worktree 中执行。
- Selection evidence: 用户显式调用本 plan 的 `superpowers:executing-plans`。
- Prior validation action: `amend` for GDT-10 Step 4/5，已补齐 registration/pause/resume 与 literal run-ID evidence sequence。
- Current validation action: `replan` only for the GDT-10 Provider timeout boundary。两次 authenticated timeout 已证明这不是可继续重跑规避的偶发 Harness noise；stable failure/retry/runtime identity 必须先由独立 design spec 冻结，再修改 GDT-10，不重写 GDT-1..9。
- Problem boundary: 只修正 GDT-10 isolated live project 的 recognition identity preflight 和 localized Provider timeout proof；不改 GD&T domain schema、normalizer、API、frontend、export 或 current-four semantics。
- Single owner: `CandidateAdvisor`/`ProductionRetryCoordinator` 继续唯一拥有 `production_uncertainty` visual retry authorization 和 localized failure disposition；Provider wrapper 只分类，`ReviewService` 只保留 Owner-committed failure entry，Harness 只做 activation preflight。现有 legacy sequential schema retry 不属于 GDT-10 isolated path，本 amendment 不重构它。
- Old path action: retire GDT-10 中“继承 `legacy_high_recall` default 后直接进入 paid processing”的未验证 activation path，并替换 `ReviewService._review_coverage()` 把 localized Provider failure 静默改成 `non_inspection` 的 generic default；不删除仍有 consumer 的 global legacy mode，也不改变普通 `visual_no_detection` default。
- Writer ownership and order: 一个 writer 先按 GDT-10A 增补 Harness、localized timeout/transport 和 review-projection RED，再最小修改 `run-p0.py` 与 `ReviewService`；只有 integration RED 证明 CandidateAdvisor evidence 缺口时才允许修改 `advisor.py`。最后派发独立 read-only reviewer。
- Unchanged contract: current P0 contract matrix、public runtime config、production deployment、`timeout=60.0`、SDK `max_retries=0`、现有 wall/call budget、schema-only single retry、literal run-ID validation 和 authenticated Provider/no-synthetic requirement 均不改变。
- Focused verification command: `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_live_run_contract.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_symbol_recognition_pipeline.py -k 'runtime_identity or provider_failure or owner_committed_discriminator' -q`。
- Next verification: 先完成 GDT-10A offline tests/reviewer，并等待 `docs/superpowers/specs/2026-08-01-compose-worktree-runtime-isolation-design.md` 与 `docs/superpowers/plans/2026-08-01-compose-worktree-runtime-isolation.md` 合入本 branch、通过其 topology/runtime completion contract；随后由 GDT-10A zero-paid preflight 直接证明 API/worker current worktree `/3` hashes、database exact `0013`、`production_uncertainty`、`symbol-uncertainty-router/1` 和 exact model。未满足前不得再次运行 `make verify-p0-live`。

### GDT-10A Continuation Record — 2026-08-01

- Selected lane: `Heavy`。
- Selected plan: `docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md`；不新建 roadmap。
- Selection evidence: 用户在 feature `2b1d8c25d40086462c278b0c5f634f15f0d284e0` 显式批准继续 GDT-10A Steps 1–9，并指定先解决 main `713fb527bb2b3c64386d51c0c8ed8b5697f367f9` 在 `backend/app/review/service.py` 和 `backend/tests/integration/test_review_working_copy.py` 的 overlap。当前 main 为 `b8c6517fa375cefa3d226fdceed4c6fd376ae467`，merge-base 为 `066a42a1871e0222ece6adfcc24fda742629e2f8`，启动时 worktree clean。
- Validation action: `continue`。不 merge/rebase 已大幅分叉且拥有不同 `0013` migration 的整个 main；先只融合 `713fb52` 与 overlap 直接相关的 backend formal-readiness owner 链，然后继续 GDT-10A。
- Problem boundary: 保留 main 的 coverage normalization、malformed-entry fail-closed、optional material normalization 和 API projection 行为；同时保留 feature 的 typed GD&T item/command union、`automatic-result/2` legacy-GDT rejection、`EditGeometricTolerance` 处理和 `visual-symbol-review/3` projection。
- Allowed overlap paths: `backend/app/review/schemas.py`、`backend/app/review/router.py`、`backend/app/projects/router.py`、`backend/app/review/service.py`、`backend/tests/integration/test_review_working_copy.py`、`backend/tests/integration/test_review_freeze.py`、`backend/tests/integration/test_project_workbench_api.py`、`backend/tests/contract/snapshots/api-v1.openapi.json`。前三者是 `713fb52` formal-readiness 行为的直接 runtime dependency；后三个 test/contract 文件是 source-only normalization、malformed fail-closed 和 optional `material` contract 的直接 regression dependency。不带入其 frontend 冲突、其他 main 历史或任一 migration。
- Old path action: `replace` overlap 中会将 malformed source-only coverage 静默解决或在 projection/freeze 前跳过 normalization 的 feature-side 旧路径；保留 ordinary `visual_no_detection -> non_inspection + system_default`，GDT-10A 随后只为 allowlisted localized Provider failure 增加例外。
- Unchanged contract: `timeout=60.0`、SDK `max_retries=0`、page/project/call budgets、production schema-only single retry、public runtime default、legacy sequential retry、structured-GD&T semantics 和本窗口 no-paid-live 边界均不改变。
- Writer ownership and order: 当前父 agent 是 overlap 和 GDT-10A 唯一 writer；`code_mapper` explorer 与后续 reviewer 严格只读；`backend/app/candidates/advisor.py` 只有在 Step 3 RED 证明 Owner 缺口时才允许修改。
- Next verification: 先运行 overlap RED，证明当前 feature 缺少 formal normalization；融合后运行 `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_geometric_tolerance_pipeline.py -q` 与 focused OpenAPI contract gate，然后进入 GDT-10A Step 1 `runtime_identity` RED。
- Overlap validation amendment: 首轮宽一层的 review regression 得到 `2 failed, 113 passed`；两个 failure 均是 feature 保留了 `713fb52` 之前的旧预期，分别要求 source-only entry 阻断 freeze 和 workbench 暴露 `manual_review_count=3`。Validation action 为 `amend`：只把 `test_review_freeze.py` 和 `test_project_workbench_api.py` 的对应 `713fb52` 断言纳入 allowed paths，然后重跑同一 regression set。
- Full-backend overlap residual: GDT-10A Step 7 首轮得到 `1716 passed, 2 failed`。`test_balloon_validation.py` 的 unresolved source fixture 缺少 `candidate_id`，仍停留在 `713fb52` 前的旧 shape；将该测试文件加入 overlap allowed paths，只同步 main 已验证的单字段 fixture。
- Compose prerequisite integration: feature 已有 `63be9ad` 的 `Makefile`/Compose project、network 和 volume isolation runtime 实现，但缺少 main `e38c806` 的 `backend/tests/integration/test_runtime_topology.py`、`docs/superpowers/specs/2026-08-01-compose-worktree-runtime-isolation-design.md`、`docs/superpowers/plans/2026-08-01-compose-worktree-runtime-isolation.md` 和 operator isolation guidance。Validation action 为 `amend`：以独立 prerequisite commit 补齐这些文件，不放入 GDT-10A implementation commit，不修改当前 branch 的 `127.0.0.1:5173` public tunnel invariant，不停止、替换或删除任一现有 runtime/volume。
- Compose prerequisite next verification: 运行 isolation plan 的 focused topology test、两个 Compose config checks 和 Makefile dry runs；然后只读验证 main/feature project/network/volume identity 不同、当前 local health/projects 和 public `qa.srj666.com` health/list 可用。如果 runtime 不是已有安全 Owner，停在 zero-paid gate，不自行 rebuild/recreate。

## Status

- Date: `2026-08-01`
- Status: `GDT-10 Step 4 blocked pending GDT-10A timeout-boundary implementation and separate Compose runtime isolation`
- Execution order: `GDT-1 -> GDT-2 -> GDT-3 -> GDT-4 -> GDT-5 -> GDT-6 -> GDT-7 -> GDT-8 -> GDT-9 -> GDT-10`
- Current blocker: after the external main-worktree writer formally handed off and stayed quiet for 60 seconds, API/worker were restored to the exact worktree `/3` identity；health passed、database was `0013`、all 12 host/API/worker hashes matched and all Provider controls were present without exposing values。The single repository-owned run generated current-four registration `20260801T071155661189Z-0acc0a66`、symbol registration `20260801T071202897748Z-f7514006` and full-P0 run `20260801T071203401727Z-09cb5cc6`。Sample 1 completed `18` authenticated `/3` request/response/cache/call records, then the 19th crop remained without request/response/call evidence；the crop-to-failure interval was `60.236s`, matching the unchanged `timeout=60.0`。Full run state is `failed` with `live_start_failed:RuntimeError`。No symbol report、typed Case A/B、pause identity or full-P0 receipt was sealed；Step 5 was not started。Thirty seconds after the Harness failure, main-worktree `make dev-local-api` independently recreated API as `/2`, so current topology is again main API `/2` + worktree worker `/3`
- Worktree: `.worktrees/structured-geometric-tolerance-recognition`
- Commits: `e1193fc`, `1a58f05`, `e4dab49`, `81e716f`, `494b8b6`, `23453cd`, `be70226`, `5c21fd7`, `6bbaf90`, `b548191`, `4150ce8`, `5f4cfbf`, `bd75be6`, `1ba4c83`。

## Execution Verification

- Migration convergence: isolated PostgreSQL upgrade `0012 -> 0013` leaves zero legacy GDT rows in `automatic_results`、`review_working_copies` and `reviewed_results`；downgrade restores the old coarse shape for all three layers。
- Rollback-first: previous application commit `6bbaf90` served the known workbench GET successfully against the isolated `0012` database；database was restored to `0013` afterward。
- Contract/static: `check-contracts.py`、OpenAPI breaking gate (`0` changes)、frontend `api:check`、contract architecture gate and `git diff --check` passed；production coarse-writer search returned no matches。
- Tests: offline backend full suite `1647 passed`；frontend full suite `26 files / 278 tests passed`；frontend production build passed；GDT backend/frontend offline E2E passed earlier in GDT-9。
- Live activation amendment: focused Harness RED reproduced target/CLI、false credential coverage、typed Case A/B、run-bound crop、malformed nested policy and stale API runtime identity gaps；focused contract file is `62 passed`，final Harness contract suite is `174 passed`，Ruff/diff checks pass，and final independent reviewer verdict is `accept`。Fresh registration runs `20260801T054718154038Z-b4e4b0de` and `20260801T054725654107Z-01c1bb35` were generated only by Harness。Full-P0 run `20260801T054726079099Z-83f03a78` made `28` authenticated Qwen calls with well-formed source/crop/model/prompt/schema hashes and matching crop bytes, but the stale `/2` API runtime produced `0` structured GDT candidates against `7` approved GDT labels；the evaluator matched only one perpendicularity label, Case A/B were absent, and no formal symbol report/receipt was sealed。After adding the exact 12-file runtime guard, `make verify-p0-live` exits `2` before run creation with `Compose API runtime identity does not match current worktree` and run directory count remains `17 -> 17`。
- Live runtime convergence: temporary worktree `.env` symlink was removed after the authorized Compose rebuild；API health passed and API/worker each matched all 12 current GDT runtime hashes。Fresh `make verify-p0-live` passed `69` global / `111` P0 contract mapping and generated exactly three Harness runs (`17 -> 20`)。Sample 1 source bytes match manifest SHA `58b9cf08...`；`12` authenticated `/3` call records have nonempty Provider request IDs and exact model/prompt/schema identity, all `12` request-bound crop hashes match bytes, and one 13th run-bound crop remains without request/response/call evidence after a 60-second timeout。Full run `20260801T061734601479Z-7a7c7f3d` is `failed` with `live_start_failed:RuntimeError` and `sample 1 application upload/process failed`；this is not accepted risk or Step 4 success。
- Post-run runtime recurrence: final read-only check found API container `dbaae635f952` recreated from `/home/reggie/vscode_folder/Quality_Inspection/compose.yaml` after the failed run；it reports `visual-symbol-review/2` and fails the exact API identity guard。Worker `f3adcef47eea` remains the worktree `/3` deployment。No second deployment or live run was attempted against this mixed topology。
- Mid-run runtime recurrence: authorized retry passed API health、database `0013`、API/worker `/3`、exact 12-file equality and Provider set/unset checks。Exactly one `make verify-p0-live` passed `69` global / `111` P0 contract mapping and generated three Harness runs (`20 -> 23`)。Before sample 1 completed, API was recreated from `/home/reggie/vscode_folder/Quality_Inspection/compose.yaml`；the run-bound `docker compose exec api` returned `137` and full run `20260801T063642486237Z-bbcb7b3d` failed closed。Harness artifacts are preserved by `5f4cfbf`；they contain no samples、symbol report、typed Case A/B、pause evidence or full-P0 receipt。Worker remained this worktree `/3`；current API is main-worktree `/2`。
- Recurrent Provider timeout: after an observed 60-second external-writer quiet window, API/worker were rebuilt from this worktree and preflight again proved health、database `0013`、both `/3` schemas、exact 12/12 host/API/worker hashes and required Provider set/unset controls。Exactly one repository-owned `make verify-p0-live` generated three fresh Harness runs and kept both container IDs stable through command exit。Full run `20260801T071203401727Z-09cb5cc6` completed `18` authenticated request/response/cache/call records with `visual-symbol-prompt/4` and `visual-symbol-review/3` identity, then wrote a 19th crop without its matching records；Harness failed `60.236s` later with `CandidateAdvisorFailure: Visual symbol Advisor call failed`。This matches the unchanged `backend/app/providers/runtime.py` `timeout=60.0` and is the second confirmed Provider-timeout recurrence。Evidence is preserved by `1ba4c83`；Step 4 did not reach pause and Step 5 was not run。
- Post-timeout runtime recurrence: the timeout failure was sealed at `15:20:12+08:00` before main-worktree `make dev-local-api` started at `15:20:42+08:00`。That later command recreated API from `/home/reggie/vscode_folder/Quality_Inspection` as `/2` at `15:23:11+08:00` while worker remained this worktree `/3`。It did not cause the timeout, but it reconfirms that the shared Compose project lacks an exclusive owner for any future live window。
- Timeout root-cause decision: the failing stack entered the `legacy_high_recall` sequential visual branch even though the symbol canary contract requires `production_uncertainty`。The existing production path already persists localized `provider_timeout` and preserves siblings as `partial_review_required`。Automatic timeout retry is rejected: `timeout=60.0` already exceeds the `45.0s` page wall budget, and a no-response attempt has no Provider request ID proving it is safe to resubmit。The approved design is `docs/superpowers/specs/2026-08-01-provider-timeout-retry-and-partial-failure-design.md`。
- Environment note: `make test-backend` could not create its fresh Docker network because Docker reported `all predefined address pools have been fully subnetted`；the equivalent full backend suite ran against the isolated PostgreSQL and passed。
- Remaining completion gate: implement and independently review GDT-10A，including working-copy failure preservation；then merge and complete the named Compose worktree-isolation prerequisite。Only a zero-paid preflight proving isolated API/worker `/3` hashes + `production_uncertainty` + exact router/model + database `0013` may authorize a fresh current-four run。A localized timeout may preserve AutomaticResult/project phase as `partial_review_required` but does not satisfy Step 4 unless typed Case A/B、all non-GD&T results and `visual_qa_pending:first-pdf-balloons` are present。

## Rollback Contract

- Code rollback unit: revert 本计划 commits 的逆序集合，不 reset/rewrite unrelated history。
- Data rollback: 在 isolated database 先验证 revision `0013_structured_gdt` 的 downgrade 将 typed GD&T 安全降为 old coarse `raw_text + coordinates + coarse_type + requires_confirmation`；production rollback 前必须另有数据库 snapshot/backup authority。
- First verification after rollback: `GET /api/v1/projects/9b9911d1-e64e-47a3-b8e5-539aa466dd40/workbench` 必须成功且 old client 可读取所有 items；随后运行 `make test-backend`，最后运行 frontend focused tests。
- Rollback veto: 如果 migration downgrade 会丢失 reviewed edits 且没有 verified snapshot，停止 rollback 并报告 blocker；不得用 warning 把数据风险转成 success。

## File Map

### New Files

- `backend/app/candidates/geometric_tolerance.py`: canonical models、serializer、normalizer、failure codes。
- `backend/app/candidates/gdt_evidence.py`: `visual-symbol-review/3` GD&T frame/cell evidence validator；不拥有业务语义。
- `backend/app/pdf/gdt_frames.py`: native vector frame proposal、cell ordering、frame 内 text association。
- `backend/app/pdf/gdt_raster_frames.py`: Pillow raster frame/cell proposal。
- `backend/tests/helpers/gdt_raster_fixture.py`: deterministic raster condition fixture generator and SHA manifest helper。
- `backend/alembic/versions/0013_structured_geometric_tolerance.py`: JSONB upgrade/downgrade 和 result schema version migration。
- `backend/tests/unit/candidates/test_geometric_tolerance.py`: canonical model/normalizer tests。
- `backend/tests/unit/candidates/test_gdt_evidence.py`: Provider evidence allowlist/containment tests。
- `backend/tests/unit/pdf/test_gdt_frames.py`: native vector proposal/cell/text association tests。
- `backend/tests/unit/pdf/test_gdt_raster_frames.py`: low-resolution/skew/adhesion raster tests。
- `backend/tests/contract/test_geometric_tolerance_contract.py`: Pydantic/OpenAPI/frozen schema contract tests。
- `backend/tests/integration/test_geometric_tolerance_pipeline.py`: inventory -> provider evidence -> result -> review/API round trip。
- `backend/tests/integration/test_geometric_tolerance_migration.py`: JSONB upgrade/downgrade/zero-legacy-row tests。
- `frontend/src/components/review/GeometricToleranceEditor.tsx`: structured editor；不解析 raw text。
- `frontend/src/components/review/GeometricToleranceEditor.test.tsx`: edit/validation/command tests。
- `frontend/e2e/geometric-tolerance-recognition.spec.ts`: Case A/B workbench display、edit、save、reload。

### Existing Files To Modify

- `backend/app/candidates/schemas.py`: export typed candidate union surface while preserving the existing generic `CandidateType` used by manual Add commands。
- `backend/app/candidates/complex_fallback.py`: remove GD&T from new coarse writer enum after migration adapter exists。
- `backend/app/pdf/schemas.py`: add `GdtFrameObservation`/cells to page inventory。
- `backend/app/pdf/inventory.py`: build native frame evidence。
- `backend/app/processing/pipeline.py`: write `page-inventory/2` after the frame observation schema changes。
- `backend/app/processing/runtime_recognition.py`: attach raster frame evidence without changing non-GD&T OCR ownership。
- `backend/app/providers/visual_symbol_review.schema.json`: replace `/2` with `/3` and add frozen `gdt_frames[]` evidence。
- `backend/app/candidates/symbol_review.py`: orchestrate evidence validator/normalizer；remove inline GD&T parser/projection branch。
- `backend/app/processing/automatic_result.py`: write `automatic-result/3` and route all GD&T/疑似 GD&T through normalizer。
- `backend/app/candidates/models.py`: no new column；document current JSONB typed validation boundary only if code-level type alias is needed。
- `backend/app/review/schemas.py`: exact GD&T projection and `edit_geometric_tolerance` command。
- `backend/app/review/service.py`: validate/regenerate structured edits；preserve payload across working/reviewed layers。
- `backend/app/projects/schemas.py`: expose exact working-copy item union through workbench。
- `backend/app/exports/service.py`: format from canonical GD&T fields only。
- `backend/tests/contract/snapshots/api-v1.openapi.json`: approved breaking snapshot update。
- `frontend/src/api/generated.ts`: regenerate from approved OpenAPI snapshot。
- `frontend/src/api/types.ts`: expose exact GD&T union without duplicating writable semantic fields。
- `frontend/src/copy/zhCN.ts`: subtype/modifier/datum labels。
- `frontend/src/components/workbench/inspectionItemPresentation.ts`: subtype presentation from canonical fields。
- `frontend/src/components/workbench/InspectionItemTable.tsx`: show subtype/value/datum/modifier。
- `frontend/src/components/review/ReviewPanel.tsx`: mount structured editor and use new review command。
- `frontend/src/styles/workbench.css`: reuse existing workbench tokens for frame fields。
- Existing relevant unit/integration/E2E/export tests listed in each Task。

---

### GDT-1: Freeze The Canonical Domain Contract

**Files:**

- Create: `backend/app/candidates/geometric_tolerance.py`
- Create: `backend/tests/unit/candidates/test_geometric_tolerance.py`
- Modify: `backend/app/candidates/schemas.py:10-54`
- Test: `backend/tests/unit/candidates/test_geometric_tolerance.py`

**Interfaces:**

- Consumes: `stable_candidate_id()` and existing PDF coordinates tuple。
- Produces: `ToleranceType`、`GdtModifierKind`、`GdtModifier`、`DatumReference`、`GdtSegment`、`GdtFrame`、`GeometricToleranceCandidate`、`StructuredCandidate`、`serialize_geometric_tolerance()`。

- [ ] **Step 1: Write failing Case A/B and composite contract tests**

```python
from decimal import Decimal

from app.candidates.geometric_tolerance import (
    DatumReference,
    GdtFrame,
    GdtModifier,
    GdtSegment,
    GeometricToleranceCandidate,
)


def test_parallelism_candidate_derives_first_segment_fields() -> None:
    frame = GdtFrame(
        segments=(
            GdtSegment(
                tolerance_value=Decimal("0.1"),
                diameter_modifier=False,
                modifiers=(),
                datum_references=(DatumReference(datum="A", modifiers=()),),
            ),
        )
    )
    candidate = GeometricToleranceCandidate.from_frames(
        candidate_id="case-a",
        raw_text="∥ | 0.1 | A",
        tolerance_type="parallelism",
        frames=(frame,),
        coordinates=(659.5, 388.89, 721.3, 428.49),
        source_location_ids=("visual-a", "value-a", "datum-a"),
        evidence_ref="asset://fixtures/gdt/case-a.json",
    )
    assert candidate.tolerance_symbol == "∥"
    assert candidate.tolerance_value == Decimal("0.1")
    assert [item.datum for item in candidate.datum_references] == ["A"]
    assert candidate.normalized_text == "∥ | 0.1 | A"


def test_flatness_alias_serializes_to_canonical_symbol() -> None:
    candidate = GeometricToleranceCandidate.from_frames(
        candidate_id="case-b",
        raw_text="▱ | 0.08",
        tolerance_type="flatness",
        frames=(
            GdtFrame(
                segments=(
                    GdtSegment(
                        tolerance_value=Decimal("0.08"),
                        diameter_modifier=False,
                        modifiers=(),
                        datum_references=(),
                    ),
                )
            ),
        ),
        coordinates=(667.2, 388.89, 726.3, 428.49),
        source_location_ids=("visual-b", "value-b"),
        evidence_ref="asset://fixtures/gdt/case-b.json",
    )
    assert candidate.tolerance_symbol == "⏥"
    assert candidate.normalized_text == "⏥ | 0.08"


def test_modifier_and_datum_order_are_not_set_normalized() -> None:
    segment = GdtSegment(
        tolerance_value=Decimal("0.05"),
        diameter_modifier=True,
        modifiers=(GdtModifier(kind="maximum_material_condition", raw_symbol="M"),),
        datum_references=(
            DatumReference(datum="C", modifiers=()),
            DatumReference(datum="A", modifiers=()),
            DatumReference(datum="B", modifiers=()),
        ),
    )
    assert [item.datum for item in segment.datum_references] == ["C", "A", "B"]


def test_legacy_unknown_preserves_raw_text_without_guessing_frames() -> None:
    candidate = GeometricToleranceCandidate.from_legacy_unknown(
        candidate_id="legacy",
        raw_text="∥ 0.1",
        coordinates=(1.0, 2.0, 3.0, 4.0),
        source_location_ids=("legacy-source",),
    )
    assert candidate.tolerance_type == "unknown"
    assert candidate.frames == ()
    assert candidate.tolerance_value is None
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_geometric_tolerance.py -q
```

Expected: collection fails because `app.candidates.geometric_tolerance` does not exist。

- [ ] **Step 3: Implement exact Pydantic models and one-way derived fields**

```python
class GdtModifier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: GdtModifierKind
    raw_symbol: str = Field(min_length=1)


class DatumReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    datum: str = Field(pattern=r"^[A-Z]$")
    modifiers: tuple[GdtModifier, ...] = ()


class GdtSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tolerance_value: Decimal
    diameter_modifier: bool
    modifiers: tuple[GdtModifier, ...] = ()
    datum_references: tuple[DatumReference, ...] = ()


class GdtFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    segments: tuple[GdtSegment, ...] = Field(min_length=1)
```

Implement `GeometricToleranceCandidate.from_frames()` so only it sets derived top-level fields and `normalized_text`; direct construction with mismatched fields must raise `ValidationError`。Implement `from_legacy_unknown()` as the only factory that allows `tolerance_type="unknown"` with empty `frames` and null derived value/datum fields。Keep the existing `CandidateType` unchanged because generic `Add`/`PromoteSource` cannot supply a complete GD&T frame；export `StructuredCandidate = Candidate | GeometricToleranceCandidate` for result writers。

- [ ] **Step 4: Run focused GREEN and schema negative tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_geometric_tolerance.py backend/tests/unit/candidates/test_complex_fallback.py -q
```

Expected: all pass；tests prove extra fields、negative values、empty frames、mismatched derived values are rejected。

- [ ] **Step 5: Commit GDT-1**

```bash
git add backend/app/candidates/geometric_tolerance.py backend/app/candidates/schemas.py backend/tests/unit/candidates/test_geometric_tolerance.py
git commit -m "feat(gdt): define structured candidate contract"
```

### GDT-2: Build Native Vector Frames And Associate Every In-Frame Text Line

**Files:**

- Create: `backend/app/pdf/gdt_frames.py`
- Create: `backend/tests/unit/pdf/test_gdt_frames.py`
- Modify: `backend/app/pdf/schemas.py:26-86`
- Modify: `backend/app/pdf/inventory.py:94-181`
- Modify: `backend/app/processing/pipeline.py:176-185`
- Test: `backend/tests/unit/pdf/test_gdt_frames.py`
- Test: `backend/tests/unit/pdf/test_inventory.py`

**Interfaces:**

- Consumes: `TextObservation`、PyMuPDF drawing dictionaries、`PageTransform`。
- Produces: `GdtCellObservation`、`GdtFrameObservation`、`build_page_gdt_frame_observations()`；`PageInventory.gdt_frame_observations`。

- [ ] **Step 1: Run `github-oss-fusion` for bounded prior-art research**

Search only license-safe implementations/tests for axis-aligned table cell extraction、broken-line joining、text-to-cell assignment and feature-control-frame fixtures。Record inspected repositories、licenses、fused test/algorithm ideas and skipped code in the task handoff；do not copy external implementations or add dependencies。

- [ ] **Step 2: Write RED tests for Case A and geometry negatives**

```python
def test_parallelism_frame_collects_independent_datum_line() -> None:
    observations = (
        text_line("value", "0.1", (684.0, 390.0, 702.0, 408.0)),
        text_line("datum", "A", (712.0, 390.0, 721.0, 408.0)),
    )
    frames = build_page_gdt_frame_observations(
        page_index=0,
        page_width=1190.0,
        page_height=842.0,
        source_sha256="fixture-source",
        text_observations=observations,
        drawings=feature_control_frame_drawings(),
        transform=identity_transform(),
        layout_profile_match=None,
    )
    assert len(frames) == 1
    assert frames[0].associated_text_observation_ids == ("value", "datum")
    assert len(frames[0].cells) == 3


def test_table_grid_is_not_a_feature_control_frame() -> None:
    frames = build_page_gdt_frame_observations(
        page_index=0,
        page_width=1190.0,
        page_height=842.0,
        source_sha256="table-negative",
        text_observations=(text_line("title", "REV", (900.0, 20.0, 940.0, 35.0)),),
        drawings=revision_table_drawings(rows=4, columns=5),
        transform=identity_transform(),
        layout_profile_match=revision_table_layout_match(),
    )
    assert frames == ()
```

- [ ] **Step 3: Run the tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_gdt_frames.py -q
```

Expected: collection fails because `GdtFrameObservation` and builder do not exist。

- [ ] **Step 4: Implement deterministic vector frame/cell proposal**

Use these exact v1 rules:

```python
@dataclass(frozen=True)
class GdtCellObservation:
    cell_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox


@dataclass(frozen=True)
class GdtFrameObservation:
    observation_id: str
    page_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox
    cells: tuple[GdtCellObservation, ...]
    associated_text_observation_ids: tuple[str, ...]
    proposal_source: Literal["native_vector", "raster"]
    proposal_state: Literal["complete", "ambiguous"]
    geometry_sha256: str


MAX_FRAME_HEIGHT_PT = 48.0
MAX_FRAME_WIDTH_PT = 240.0
MIN_FRAME_HEIGHT_PT = 6.0
TEXT_FRAME_PADDING_PT = 1.5
MIN_TEXT_OVERLAP_RATIO = 0.5


def text_belongs_to_frame(text_bbox: BBox, frame_bbox: BBox) -> bool:
    center_x = (text_bbox[0] + text_bbox[2]) / 2
    center_y = (text_bbox[1] + text_bbox[3]) / 2
    padded = expand_bbox(frame_bbox, TEXT_FRAME_PADDING_PT)
    return point_in_bbox((center_x, center_y), padded) or (
        intersection_area(text_bbox, padded) / bbox_area(text_bbox)
        >= MIN_TEXT_OVERLAP_RATIO
    )
```

Join collinear horizontal/vertical segments with gap `<=1.5pt`; require one bounded horizontal band and at least one internal vertical separator；accept `layout_profile_match: LayoutProfileMatch | None` and reject candidates overlapping known title/revision assignments or exceeding size limits。Sort cells left-to-right and associated lines by `(cell_index, bbox_y, bbox_x, observation_level)`；include independent lines and their spans, then deduplicate exact observation IDs。Do not infer cell roles here。

- [ ] **Step 5: Integrate into inventory without changing generic visual proposals**

Add `gdt_frame_observations: tuple[GdtFrameObservation, ...] = ()` to `PageInventory` and omit it from serialized inventory when empty。Call the builder after native text/drawings extraction；keep existing `build_page_visual_observations()` unchanged for non-GD&T symbols。Bump the stored artifact to `page-inventory/2` and update inventory/idempotency contract tests；readers may still read `/1` artifacts but no `/1` writer remains。

- [ ] **Step 6: Run focused GREEN and existing visual-observation regression tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_gdt_frames.py backend/tests/unit/pdf/test_visual_observations.py backend/tests/unit/pdf/test_inventory.py backend/tests/integration/test_task_idempotency.py -q
```

Expected: Case A associates `A`；table/leader/dimension-box negatives produce no frame；existing visual observation tests remain green。

- [ ] **Step 7: Commit GDT-2**

```bash
git add backend/app/pdf/gdt_frames.py backend/app/pdf/schemas.py backend/app/pdf/inventory.py backend/app/processing/pipeline.py backend/tests/unit/pdf/test_gdt_frames.py backend/tests/unit/pdf/test_inventory.py backend/tests/integration/test_task_idempotency.py
git commit -m "feat(gdt): propose vector feature control frames"
```

### GDT-3: Add Raster Frame Evidence With Existing Pillow

**Files:**

- Create: `backend/app/pdf/gdt_raster_frames.py`
- Create: `backend/tests/unit/pdf/test_gdt_raster_frames.py`
- Create: `backend/tests/helpers/gdt_raster_fixture.py`
- Modify: `backend/app/processing/runtime_recognition.py:32-129`
- Modify: `backend/app/pdf/schemas.py`
- Test: `backend/tests/unit/pdf/test_gdt_raster_frames.py`

**Interfaces:**

- Consumes: rendered PNG bytes、`PageTransform`、OCR `TextObservation`。
- Produces: `detect_raster_gdt_frames()` returning the same `GdtFrameObservation` contract as GDT-2。

- [ ] **Step 1: Write RED tests for low-resolution, skew, broken and adhesive lines**

```python
@pytest.mark.parametrize(
    "fixture_name",
    (
        "parallelism-low-resolution.png",
        "flatness-skew-2deg.png",
        "position-broken-border.png",
        "perpendicularity-line-adhesion.png",
    ),
)
def test_raster_frame_conditions_keep_ordered_cells(fixture_name: str) -> None:
    frames = detect_raster_gdt_frames(
        png=fixture_bytes(fixture_name),
        page_index=0,
        transform=fixture_transform(),
        crop_bbox_pdf=(0.0, 0.0, 240.0, 80.0),
        text_observations=fixture_ocr_observations(fixture_name),
        source_sha256=fixture_name,
    )
    assert len(frames) == 1
    assert [cell.cell_index for cell in frames[0].cells] == list(
        range(len(frames[0].cells))
    )


def test_raster_revision_table_is_rejected() -> None:
    assert detect_raster_gdt_frames(
        png=fixture_bytes("revision-table-negative.png"),
        page_index=0,
        transform=fixture_transform(),
        crop_bbox_pdf=(0.0, 0.0, 240.0, 80.0),
        text_observations=(),
        source_sha256="revision-table-negative",
    ) == ()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_gdt_raster_frames.py -q
```

Expected: import/fixture failures identify the missing raster detector and fixture files。

- [ ] **Step 3: Add deterministic fixture generator and Pillow detector**

Generate committed PNG fixtures through a deterministic test helper, then commit the rendered bytes and manifest SHA-256。Implementation uses grayscale、adaptive local threshold derived from image median、horizontal/vertical run detection、`<=3px` broken-line joining and deskew search over `[-3,-2,-1,0,1,2,3]` degrees。Accept a frame only when outer band + ordered separators satisfy the same physical-size limits after PDF transform；reject grids with more than `6` columns or `2` stacked frames unless composite grouping is explicit。

```python
def detect_raster_gdt_frames(
    *,
    png: bytes,
    page_index: int,
    transform: PageTransform,
    crop_bbox_pdf: BBox,
    text_observations: Sequence[TextObservation],
    source_sha256: str,
) -> tuple[GdtFrameObservation, ...]:
    image = Image.open(io.BytesIO(png)).convert("L")
    deskewed, angle = select_deskew_angle(image)
    line_runs = detect_axis_runs(deskewed)
    return build_raster_frame_observations(
        line_runs=line_runs,
        deskew_angle=angle,
        page_index=page_index,
        transform=transform,
        crop_bbox_pdf=crop_bbox_pdf,
        text_observations=text_observations,
        source_sha256=source_sha256,
    )
```

- [ ] **Step 4: Integrate raster evidence without changing existing OCR budgets**

In `RuntimeRecognition.build_inventory()`, change the route gate to `inventory.processing_route == "hybrid" or inventory.page_type == "scanned"` while preserving the same maximum `16` OCR regions per page。For each existing rendered region, pass its PNG、PDF region bbox and OCR observations to the raster detector；merge observations by stable frame ID。A scanned page may gain frame evidence but remains `processing_route="unsupported"` and `review_required` until later validation, so this Task cannot convert scan evidence into formal success。If raster proposal is ambiguous, add Coverage-ready frame evidence with `proposal_state="ambiguous"` rather than marking the page supported。

- [ ] **Step 5: Run GREEN and OCR regressions**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/pdf/test_gdt_raster_frames.py backend/tests/unit/pdf/test_runtime_ocr.py -q
```

Expected: all raster positives/negatives pass and OCR call-count assertions are unchanged。

- [ ] **Step 6: Commit GDT-3**

```bash
git add backend/app/pdf/gdt_raster_frames.py backend/app/pdf/schemas.py backend/app/processing/runtime_recognition.py backend/tests/helpers/gdt_raster_fixture.py backend/tests/unit/pdf/test_gdt_raster_frames.py backend/tests/fixtures/gdt
git commit -m "feat(gdt): detect raster feature control frames"
```

### GDT-4: Upgrade The Frozen Provider Evidence Contract

**Files:**

- Create: `backend/app/candidates/gdt_evidence.py`
- Create: `backend/tests/unit/candidates/test_gdt_evidence.py`
- Create: `backend/tests/contract/test_geometric_tolerance_contract.py`
- Modify: `backend/app/providers/visual_symbol_review.schema.json`
- Modify: `backend/app/candidates/symbol_review.py:464-589,834-949`
- Modify: `backend/app/providers/qwen_vl.py`
- Test: `backend/tests/contract/test_qwen_symbol_provider.py`

**Interfaces:**

- Consumes: `GdtFrameObservation`、visual batch crop、allowlisted text IDs。
- Produces: validated `GdtFrameEvidence`/`GdtCellEvidence` with no final business disposition。

- [ ] **Step 1: Write schema RED tests**

```python
def test_visual_symbol_review_v3_accepts_ordered_gdt_cells() -> None:
    response = {
        "schema_version": "visual-symbol-review/3",
        "detections": [],
        "gdt_frames": [
            {
                "frame_observation_id": "frame-a",
                "frame_bbox_normalized": [0.1, 0.1, 0.8, 0.3],
                "tolerance_type_signal": "parallelism",
                "cells": [
                    cell(0, "symbol", "∥", []),
                    cell(1, "tolerance", "0.1", ["value-a"]),
                    cell(2, "datum", "A", ["datum-a"]),
                ],
                "confidence_signal": 0.97,
            }
        ],
    }
    validate_visual_symbol_response(response)


def test_gdt_cell_rejects_text_id_outside_frame_allowlist() -> None:
    with pytest.raises(GdtEvidenceValidationError, match="text_id_not_allowlisted"):
        validate_gdt_frame_evidence(
            provider_frame=provider_frame(text_ids=("other-page",)),
            observation=frame_observation(text_ids=("value-a", "datum-a")),
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
        )
```

- [ ] **Step 2: Run contract tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/test_geometric_tolerance_contract.py backend/tests/unit/candidates/test_gdt_evidence.py -q
```

Expected: `/2` schema rejects `gdt_frames` and evidence models are missing。

- [ ] **Step 3: Freeze `visual-symbol-review/3`**

Require top-level `schema_version`、`detections`、`gdt_frames`。Each `gdt_frames[]` exact fields:

```json
{
  "frame_observation_id": "frame-a",
  "frame_bbox_normalized": [0.1, 0.1, 0.8, 0.3],
  "tolerance_type_signal": "parallelism",
  "cells": [
    {
      "cell_index": 0,
      "cell_role": "symbol",
      "bbox_normalized": [0.1, 0.1, 0.2, 0.3],
      "raw_token": "∥",
      "associated_text_observation_ids": [],
      "confidence_signal": 0.97
    }
  ],
  "confidence_signal": 0.97
}
```

Freeze role enum `symbol|tolerance|modifier|datum|separator|unknown` and tolerance signal enum from the design。`additionalProperties=false` at every object。`raw_token` is evidence, not final canonical text。

- [ ] **Step 4: Implement local containment/order/allowlist validation**

`validate_gdt_frame_evidence()` must verify frame ID exists in current batch、frame/cell bboxes stay within crop/frame、cell indexes are unique and contiguous、text IDs belong to the frame allowlist、datum/modifier raw tokens are one constrained glyph/token、and provider frame count does not exceed input frames。Return an explicit rejection code; never repair or reorder Provider output silently。

- [ ] **Step 5: Update prompt and Provider cache identity**

Prompt each frame with its ordered local cell boxes and allowlisted text observations；require empty `gdt_frames` when no frame is present。Keep `temperature=0`。Schema version/hash is already part of cache identity；tests must prove `/2` cache entries cannot satisfy `/3` requests and are recomputed rather than read through。

- [ ] **Step 6: Run focused GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/test_geometric_tolerance_contract.py backend/tests/unit/candidates/test_gdt_evidence.py backend/tests/contract/test_qwen_symbol_provider.py -q
```

Expected: valid ordered frame passes；out-of-frame bbox、unknown ID、duplicate index、extra key、`/2` reuse all fail with exact codes。

- [ ] **Step 7: Commit GDT-4**

```bash
git add backend/app/candidates/gdt_evidence.py backend/app/providers/visual_symbol_review.schema.json backend/app/candidates/symbol_review.py backend/app/providers/qwen_vl.py backend/tests/unit/candidates/test_gdt_evidence.py backend/tests/contract/test_geometric_tolerance_contract.py backend/tests/contract/test_qwen_symbol_provider.py
git commit -m "feat(gdt): validate frame cell evidence"
```

### GDT-5: Normalize Frame Evidence And Replace New Coarse Writes

**Files:**

- Modify: `backend/app/candidates/geometric_tolerance.py`
- Modify: `backend/app/candidates/symbol_review.py:1992-2544`
- Modify: `backend/app/processing/automatic_result.py:193-244,590-625`
- Modify: `backend/app/candidates/complex_fallback.py:8-33`
- Modify: `backend/tests/unit/candidates/test_geometric_tolerance.py`
- Modify: `backend/tests/unit/candidates/test_symbol_advisor.py:1550-1685`
- Modify: `backend/tests/unit/candidates/test_complex_fallback.py`
- Test: `backend/tests/unit/candidates/test_local_symbol_resolution.py`

**Interfaces:**

- Consumes: validated `GdtFrameEvidence` and `GdtFrameObservation` source provenance。
- Produces: `GeometricToleranceNormalizer.normalize() -> GeometricToleranceCandidate | GdtNormalizationFailure`。

- [ ] **Step 1: Write RED normalizer tests for complete, unknown and composite frames**

```python
def test_normalizer_builds_parallelism_with_datum_a() -> None:
    result = GeometricToleranceNormalizer().normalize(
        evidence=evidence(
            tolerance_type="parallelism",
            cells=(("symbol", "∥"), ("tolerance", "0.1"), ("datum", "A")),
        ),
        observation=frame_observation_case_a(),
        evidence_ref="asset://fixtures/gdt/case-a-evidence.json",
    )
    assert isinstance(result, GeometricToleranceCandidate)
    assert result.tolerance_type == "parallelism"
    assert result.tolerance_value == Decimal("0.1")
    assert [datum.datum for datum in result.datum_references] == ["A"]


def test_unknown_modifier_fails_closed_without_coarse_candidate() -> None:
    result = GeometricToleranceNormalizer().normalize(
        evidence=evidence(
            tolerance_type="position",
            cells=(("symbol", "⌖"), ("tolerance", "0.1"), ("modifier", "P")),
        ),
        observation=frame_observation_position(),
        evidence_ref="asset://fixtures/gdt/unknown-modifier.json",
    )
    assert result.code == "gdt_modifier_unknown"
    assert result.typed_unknown is not None
    assert result.typed_unknown.item_type == "geometric_tolerance"
    assert result.typed_unknown.tolerance_type == "unknown"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_geometric_tolerance.py backend/tests/unit/candidates/test_symbol_advisor.py -k 'gdt or geometric_tolerance' -q
```

Expected: new normalizer tests fail and old tests still expect four-field coarse candidates。

- [ ] **Step 3: Implement grammar and canonical mapping**

`GeometricToleranceNormalizer` validates exact ordered grammar:

```text
symbol -> tolerance value -> zero or more tolerance modifiers -> zero or more ordered datum cells
```

Support all v1 tolerance types from the design。Parse decimals with `Decimal`；map `▱` and `⏥` input to flatness/`⏥` output；map `M/L/S` to frozen modifier kinds；preserve duplicate/order-sensitive datum evidence and reject invalid datum token。Multiple frame/segment cells must remain in `frames[] -> segments[]`。Return exact failure codes from the design。

- [ ] **Step 4: Replace visual and text GD&T producers**

In `symbol_review.py`, delete `_distinct_ascii_decimals()`/`_gdt_datum_tokens()` only after all non-GD&T callers are confirmed absent；replace the `kinds[0].startswith("gdt_")` coarse branch with the normalizer call。In `automatic_result.py`, route any supported glyph or `looks_like_gdt_frame_text()` input through the same normalizer；text-only incomplete input becomes typed `unknown` + confirmation。Remove `geometric_tolerance` from the new `CoarseType` writer enum。

- [ ] **Step 5: Add exact-once Coverage outcomes**

Each frame produces exactly one of `candidate`、`reference_context`、`ambiguous`、`fatal`。Persist normalizer failure codes and all frame/cell source IDs；do not store Provider raw response inside candidate payload。

- [ ] **Step 6: Run focused GREEN and prove no new coarse producer**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/unit/candidates/test_geometric_tolerance.py backend/tests/unit/candidates/test_symbol_advisor.py backend/tests/unit/candidates/test_complex_fallback.py backend/tests/unit/candidates/test_local_symbol_resolution.py -q
rg -n 'coarse_type.?=.?("|\x27)geometric_tolerance|coarse_candidate\([^\n]*geometric_tolerance' backend/app
```

Expected: tests pass；`rg` returns no production writer。Historical reader references are not introduced until GDT-6。

- [ ] **Step 7: Independent behavior/ownership review**

Reviewer verdict must confirm Case A/B root causes are fixed at the correct owners、Provider remains signal-only、all new GD&T paths converge on one normalizer、and no hidden raw-text fallback writes final subtype。

- [ ] **Step 8: Commit GDT-5**

```bash
git add backend/app/candidates/geometric_tolerance.py backend/app/candidates/symbol_review.py backend/app/processing/automatic_result.py backend/app/candidates/complex_fallback.py backend/tests/unit/candidates/test_geometric_tolerance.py backend/tests/unit/candidates/test_symbol_advisor.py backend/tests/unit/candidates/test_complex_fallback.py backend/tests/unit/candidates/test_local_symbol_resolution.py
git commit -m "feat(gdt): normalize structured frame candidates"
```

### GDT-6: Version Persistence, Migrate JSONB And Type The OpenAPI Surface

**Files:**

- Create: `backend/alembic/versions/0013_structured_geometric_tolerance.py`
- Create: `backend/tests/integration/test_geometric_tolerance_migration.py`
- Modify: `backend/app/processing/automatic_result.py:54-55,809-881`
- Modify: `backend/app/review/schemas.py:219-251`
- Modify: `backend/app/review/service.py:513-590`
- Modify: `backend/app/projects/schemas.py:117-132`
- Modify: `backend/tests/contract/snapshots/api-v1.openapi.json`
- Modify: `frontend/src/api/generated.ts`
- Test: `backend/tests/contract/test_openapi_contract.py`
- Test: `backend/tests/integration/test_result_layers.py`

**Interfaces:**

- Consumes: typed candidate model from GDT-1/GDT-5。
- Produces: `automatic-result/3`、`reviewed-result/3`、exact `ReviewItemProjection` union、migration `0012_recognition_preview <-> 0013_structured_gdt`。

- [ ] **Step 1: Write RED migration tests using isolated PostgreSQL**

```python
def test_upgrade_converts_legacy_gdt_to_typed_unknown(connection: Connection) -> None:
    seed_automatic_result(
        connection,
        schema_version="automatic-result/2",
        candidate_payload={
            "raw_text": "∥ 0.1",
            "coordinates": [1.0, 2.0, 3.0, 4.0],
            "coarse_type": "geometric_tolerance",
            "requires_confirmation": True,
        },
    )
    upgrade_to("0013_structured_gdt")
    payload = load_only_candidate(connection)
    assert payload["item_type"] == "geometric_tolerance"
    assert payload["tolerance_type"] == "unknown"
    assert payload["raw_text"] == "∥ 0.1"
    assert payload["frames"] == []
    assert payload["requires_confirmation"] is True


def test_downgrade_restores_old_coarse_shape(connection: Connection) -> None:
    seed_structured_parallelism(connection)
    downgrade_to("0012_recognition_preview")
    payload = load_only_candidate(connection)
    assert set(payload) == {
        "raw_text",
        "coordinates",
        "coarse_type",
        "requires_confirmation",
    }
```

- [ ] **Step 2: Write RED OpenAPI assertions**

Assert `ReviewWorkingCopyProjection.items` and `ReviewedResultResponse.items` reference an exact union containing `GeometricToleranceReviewItem` with required `tolerance_type`、`frames`、`source_location_ids` and derived fields。Assert the snapshot no longer exposes these items as unconstrained `object`。

- [ ] **Step 3: Run RED checks**

Run:

```bash
make test-backend
API_CONTRACT_BASE_REF=3efe3eb2fa60c2fe112dc866b7de2114ee87b6d6 make check-api-contracts
```

Expected: migration/OpenAPI tests fail for missing revision、`automatic-result/3` and exact item schemas。

- [ ] **Step 4: Implement reversible JSONB migration**

Upgrade `automatic_results.candidates`、`review_working_copies.items` and `reviewed_results.items`。For every old GD&T coarse payload, preserve envelope metadata/source IDs and replace only payload semantics with typed `unknown`、empty `frames`、`standard_context="unspecified"`、same raw text/coordinates、confirmation required。Do not parse symbol/value/datum。Update applicable schema version columns to `/3`。Downgrade converts typed GD&T to four-field coarse using `raw_text` and coordinates only。

- [ ] **Step 5: Add versioned read/write models**

Make `/3` the only new writer。During this Task only, `/2` is a marked compatibility reader:

```text
[REMOVAL_CANDIDATE] automatic-result/2 GD&T coarse reader
  reason: database migration may not yet have run on every environment
  owner: GeometricToleranceNormalizer and automatic-result/3
  real_consumer: pre-0013 automatic_results/review rows
  trigger: GDT-10 proves zero /2 GD&T rows after upgrade and downgrade proof passes
  deadline: end of GDT-10 in this development cycle
  last_verification: GDT-6 isolated migration test
```

The adapter may convert legacy coarse only to typed `unknown`；it must not infer subtype。

- [ ] **Step 6: Type review/workbench responses and regenerate client**

Define `GeometricToleranceReviewItem` plus explicit existing typed/coarse projection models；use a union instead of `dict[str, Any]`。Regenerate snapshot/client:

```bash
(cd backend && micromamba run -n qi-p0 python -m app.contracts.openapi --baseline tests/contract/snapshots/api-v1.openapi.json --write)
npm --prefix frontend run api:generate
```

- [ ] **Step 7: Run isolated migration, result-layer and API contract GREEN**

Run:

```bash
make test-backend
API_CONTRACT_BASE_REF=3efe3eb2fa60c2fe112dc866b7de2114ee87b6d6 make check-api-contracts
```

Expected: upgrade/downgrade、result layers、OpenAPI breaking gate and generated client checks pass。

- [ ] **Step 8: Independent data-contract review**

Reviewer must inspect JSONB upgrade/downgrade、version writers/readers、OpenAPI exactness and absence of inferred legacy subtype。Any second final writer or irreversible downgrade without snapshot gate is blocking。

- [ ] **Step 9: Commit GDT-6**

```bash
git add backend/alembic/versions/0013_structured_geometric_tolerance.py backend/app/processing/automatic_result.py backend/app/review/schemas.py backend/app/review/service.py backend/app/projects/schemas.py backend/tests/integration/test_geometric_tolerance_migration.py backend/tests/integration/test_result_layers.py backend/tests/contract/test_openapi_contract.py backend/tests/contract/snapshots/api-v1.openapi.json frontend/src/api/generated.ts
git commit -m "feat(gdt): persist typed candidates and expose API contract"
```

### GDT-7: Add Structured Review Commands And Round-Trip Validation

**Files:**

- Modify: `backend/app/review/schemas.py:40-193,253-280`
- Modify: `backend/app/review/service.py:651-670,1399-1415`
- Create: `backend/tests/integration/test_geometric_tolerance_pipeline.py`
- Modify: `backend/tests/integration/test_review_working_copy.py`
- Modify: `backend/tests/integration/test_project_workbench_api.py`
- Test: `backend/tests/contract/test_openapi_contract.py`

**Interfaces:**

- Consumes: `GdtFrame` exact request models and existing versioned review commands。
- Produces: `EditGeometricTolerance(type="edit_geometric_tolerance")` and save/reload-safe typed items。

- [ ] **Step 1: Write RED edit/save/reload tests**

```python
def test_edit_geometric_tolerance_regenerates_derived_fields(
    review_service: ReviewService,
) -> None:
    working = seeded_parallelism_working_copy(review_service)
    updated = review_service.apply(
        working.id,
        expected_version=working.version,
        operator_id="gdt-reviewer",
        command=EditGeometricTolerance(
                type="edit_geometric_tolerance",
                item_id="case-a",
                tolerance_type="parallelism",
                frames=(
                    GdtFrame(
                        segments=(
                            GdtSegment(
                                tolerance_value=Decimal("0.12"),
                                diameter_modifier=False,
                                modifiers=(),
                                datum_references=(
                                    DatumReference(datum="B", modifiers=()),
                                ),
                            ),
                        ),
                    ),
                ),
                standard_context="unspecified",
            ).model_dump(mode="json"),
    )
    item = item_by_id(updated.items, "case-a")
    assert item["normalized_text"] == "∥ | 0.12 | B"
    assert item["tolerance_value"] == "0.12"
    assert item["datum_references"][0]["datum"] == "B"
```

Add negative tests proving generic `Edit.fields` cannot modify derived GD&T fields、extra modifier kinds fail、stale version remains `409`、and API GET after command returns the same frames/order。

- [ ] **Step 2: Run RED integration tests**

Run:

```bash
make test-backend
```

Expected: new command is absent and working-copy items remain opaque/unvalidated。

- [ ] **Step 3: Implement exact command and service handler**

Add `EditGeometricTolerance` to `ReviewCommand` union with exact `tolerance_type`、`frames`、`standard_context` fields。Handler loads the current typed item、calls the same `GeometricToleranceCandidate.from_frames()` factory、preserves candidate/source/coordinates/evidence IDs、sets `acceptance_source="manual"` and writes the existing audit event。Generic `Edit` must reject GD&T semantic fields。

- [ ] **Step 4: Run GREEN and OpenAPI regeneration/check**

Run:

```bash
make test-backend
npm --prefix frontend run api:generate
API_CONTRACT_BASE_REF=3efe3eb2fa60c2fe112dc866b7de2114ee87b6d6 make check-api-contracts
```

Expected: review/API round trip passes and generated command type contains `edit_geometric_tolerance`。

- [ ] **Step 5: Commit GDT-7**

```bash
git add backend/app/review/schemas.py backend/app/review/service.py backend/tests/integration/test_geometric_tolerance_pipeline.py backend/tests/integration/test_review_working_copy.py backend/tests/integration/test_project_workbench_api.py backend/tests/contract/snapshots/api-v1.openapi.json frontend/src/api/generated.ts
git commit -m "feat(gdt): support structured review edits"
```

### GDT-8: Render And Edit Structured GD&T In The Workbench

**Files:**

- Create: `frontend/src/components/review/GeometricToleranceEditor.tsx`
- Create: `frontend/src/components/review/GeometricToleranceEditor.test.tsx`
- Modify: `frontend/src/api/types.ts:78-122`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/components/workbench/inspectionItemPresentation.ts`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx:258-325`
- Modify: `frontend/src/components/review/ReviewPanel.tsx:155-171,619-645`
- Modify: `frontend/src/styles/workbench.css`
- Modify: related existing component tests

**Interfaces:**

- Consumes: generated `GeometricToleranceReviewItem` and `EditGeometricTolerance` command。
- Produces: subtype/value/modifier/datum presentation and structured editor draft；no raw parser。

- [ ] **Step 1: Write RED presentation and editor tests**

```tsx
it("renders parallelism value and datum A from typed fields", () => {
  render(
    <InspectionItemTable
      items={[parallelismItem({ value: "0.1", datums: ["A"] })]}
      balloons={[]}
      filter="all"
      selectedItemId={null}
      selectedSourceId={null}
      onSelectItem={() => undefined}
      onSelectSource={() => undefined}
    />,
  );
  expect(screen.getByText("平行度")).toBeInTheDocument();
  expect(screen.getByText("0.1")).toBeInTheDocument();
  expect(screen.getByText("基准 A")).toBeInTheDocument();
});


it("submits ordered structured fields without parsing raw_text", async () => {
  const onCommand = vi.fn();
  render(<GeometricToleranceEditor item={parallelismItem()} onCommand={onCommand} />);
  await userEvent.clear(screen.getByLabelText("公差值"));
  await userEvent.type(screen.getByLabelText("公差值"), "0.12");
  await userEvent.clear(screen.getByLabelText("基准 1"));
  await userEvent.type(screen.getByLabelText("基准 1"), "B");
  await userEvent.click(screen.getByRole("button", { name: "保存几何公差" }));
  expect(onCommand).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "edit_geometric_tolerance",
      tolerance_type: "parallelism",
    }),
  );
});
```

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/inspectionItemPresentation.test.ts src/components/workbench/InspectionItemTable.test.tsx src/components/review/GeometricToleranceEditor.test.tsx src/components/review/ReviewPanel.test.tsx
```

Expected: component/import failures identify missing typed presentation/editor。

- [ ] **Step 3: Use generated types and add canonical labels**

Define `GeometricToleranceReviewItem` from generated OpenAPI components；`ReviewItem` becomes the exact union used by workbench。Add Chinese subtype labels for all v1 enum values、modifier labels for M/L/S/unknown and datum prefix。Do not add a symbol/raw-text lookup map that reconstructs semantics。

- [ ] **Step 4: Implement list presentation and structured editor**

`inspectionItemPresentation()` reads `item.tolerance_type`。`InspectionItemTable` shows subtype、canonical value、diameter/modifiers and ordered datum list。`GeometricToleranceEditor` edits a local `frames[]` draft, validates decimal/datum tokens client-side for feedback, and submits only the exact new command；backend remains authoritative。For typed unknown/empty frames, show raw text + “未确认几何公差” and require manual completion。

- [ ] **Step 5: Run focused/full frontend tests and build**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/inspectionItemPresentation.test.ts src/components/workbench/InspectionItemTable.test.tsx src/components/review/GeometricToleranceEditor.test.tsx src/components/review/ReviewPanel.test.tsx
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
```

Expected: focused/full tests and build pass；existing chunk-size warning may remain but no new TypeScript error。

- [ ] **Step 6: Independent frontend semantic review**

Reviewer must confirm UI never parses `raw_text`、datum order is preserved、unknown does not masquerade as known subtype、save/reload uses API payload and old generic “几何公差” remains only for migrated unknown。

- [ ] **Step 7: Commit GDT-8**

```bash
git add frontend/src/api/types.ts frontend/src/copy/zhCN.ts frontend/src/components/workbench/inspectionItemPresentation.ts frontend/src/components/workbench/InspectionItemTable.tsx frontend/src/components/review/GeometricToleranceEditor.tsx frontend/src/components/review/ReviewPanel.tsx frontend/src/styles/workbench.css frontend/src/components/workbench/inspectionItemPresentation.test.ts frontend/src/components/workbench/InspectionItemTable.test.tsx frontend/src/components/review/GeometricToleranceEditor.test.tsx frontend/src/components/review/ReviewPanel.test.tsx
git commit -m "feat(gdt): render and edit structured tolerances"
```

### GDT-9: Preserve Structured Semantics Through Export And Offline E2E

**Files:**

- Modify: `backend/app/exports/service.py:80-155`
- Modify: `backend/tests/integration/test_excel_export.py`
- Modify: `backend/tests/helpers/symbol_fixture.py`
- Modify: `backend/tests/e2e/test_symbol_recognition.py`
- Create: `frontend/e2e/geometric-tolerance-recognition.spec.ts`
- Modify: `frontend/playwright.config.ts` only if the new file requires an already-existing project selection; do not add a new browser project。

**Interfaces:**

- Consumes: frozen `reviewed-result/3` typed items。
- Produces: deterministic SIP/Excel display text and frozen-provider/backend/frontend E2E proof。

- [ ] **Step 1: Write RED export tests**

```python
def test_excel_formats_structured_parallelism_without_raw_text_parsing() -> None:
    workbook = export_reviewed_items(
        [structured_parallelism(value="0.1", datums=("A",))]
    )
    row = sip_row(workbook, item_id="case-a")
    assert row.inspection_item == "平行度 | 0.1 | 基准 A"


def test_excel_keeps_composite_frame_segment_order() -> None:
    workbook = export_reviewed_items([structured_composite_position()])
    assert sip_row(workbook, item_id="composite").inspection_item == (
        "位置度 | ⌀0.10 M | A | B | C / ⌀0.20 | A | B"
    )
```

- [ ] **Step 2: Write RED frozen-provider and browser E2E cases**

Backend E2E must assert Case A/B typed payloads from inventory to working copy；frontend E2E intercepts the exact workbench payload, verifies “平行度/0.1/基准 A” and “平面度/0.08”, edits A -> B, saves, reloads and verifies the returned command/payload。Add modifier/composite and typed unknown cases。

- [ ] **Step 3: Run RED**

Run:

```bash
make test-backend
micromamba run -n qi-p0 npm --prefix frontend run e2e -- geometric-tolerance-recognition.spec.ts
```

Expected: export still falls through generic composite/raw formatting and E2E fixtures still expect coarse candidates。

- [ ] **Step 4: Format export from canonical fields only**

Add `format_geometric_tolerance(item)` that consumes `tolerance_type`、`frames` and canonical labels。It must not inspect glyphs in `raw_text` or Provider evidence。Keep the same reviewed result, numbering and SIP row ownership。

- [ ] **Step 5: Upgrade fixtures and frozen responses**

Replace simplified single rectangle GDT fixture with real three-cell vector frames for Case A/B and a two-segment composite frame。Frozen `/3` Provider responses must reference exact frame/cell/text IDs。Keep existing non-GD&T positives/negatives unchanged。

- [ ] **Step 6: Run GREEN**

Run:

```bash
make test-backend
micromamba run -n qi-p0 npm --prefix frontend run e2e -- geometric-tolerance-recognition.spec.ts
```

Expected: export and both E2E layers pass；no synthetic result is reported as live proof。

- [ ] **Step 7: Commit GDT-9**

```bash
git add backend/app/exports/service.py backend/tests/integration/test_excel_export.py backend/tests/helpers/symbol_fixture.py backend/tests/e2e/test_symbol_recognition.py frontend/e2e/geometric-tolerance-recognition.spec.ts frontend/playwright.config.ts
git commit -m "test(gdt): close export and offline e2e"
```

### GDT-10: Retire Compatibility, Prove Rollback And Seal Live Evidence

**Files:**

- Modify: `backend/app/processing/automatic_result.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_geometric_tolerance_migration.py`
- Modify: `.agent/harness/scripts/run-p0.py` only after the plan is explicitly activated for the symbol-recognition current-four contract。
- Modify: `.agent/harness/scripts/live_evidence_policy.py` with the same activation, only to validate typed Case A/B and sealed Provider identity hashes in the symbol report。
- Modify: `backend/tests/contract/harness/test_live_run_contract.py` only with the same activation。
- Modify: `backend/tests/integration/test_symbol_recognition_pipeline.py` only to freeze the existing production localized-timeout/no-retry/partial-result contract。
- Modify: `backend/app/review/service.py` only to preserve Owner-committed localized Provider failure coverage instead of applying the generic system default。
- Modify: `backend/tests/integration/test_review_working_copy.py` to lock failure preservation and unchanged no-detection default。
- Modify: `Makefile` only to invoke repository-owned current input registration/full-live pause activation；do not add implicit `latest` selection。
- Modify: `.agent/bug-memory.md` to record and close the confirmed live-target regression。
- Generate under: `.agent/harness/runs/` only through the existing Harness command；never choose a run ID or hand-write run evidence。
- Modify: this plan Status/verification section after evidence is sealed。

**Interfaces:**

- Consumes: all previous Tasks、isolated migration proof、current-four approved inputs and headed workbench runtime。
- Produces: zero legacy GD&T writer/reader rows, rollback proof, sealed live/API/UI/export evidence and final independent review verdict。

- [ ] **Step 1: Prove migration convergence and remove the marked `/2` GD&T adapter**

In an isolated database, seed `/2` automatic/review/reviewed rows, upgrade to `0013`, then query:

```sql
SELECT COUNT(*)
FROM automatic_results ar,
LATERAL jsonb_array_elements(ar.candidates) candidate
WHERE candidate->'payload'->>'coarse_type' = 'geometric_tolerance';
```

Run equivalent queries for working/reviewed `items`。Expected count is `0` in all tables。Remove the GDT-specific `/2` compatibility adapter and its mark；keep unrelated general `/1` compatibility outside this plan unchanged。

- [ ] **Step 2: Prove downgrade and first rollback verification in isolated runtime**

Downgrade `0013 -> 0012`, start the previous application commit against the downgraded isolated DB, and first call the known workbench GET。Then run `make test-backend` and focused frontend tests。Record commands/result in the plan closeout；do not run against production without separate deployment/backup authority。

- [ ] **Step 3: Run full static/contract/test gates**

Run:

```bash
python .agent/harness/scripts/check-contracts.py
API_CONTRACT_BASE_REF=3efe3eb2fa60c2fe112dc866b7de2114ee87b6d6 make check-api-contracts
make test-backend
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
git diff --check
rg -n 'coarse_type.?=.?("|\x27)geometric_tolerance|coarse_candidate\([^\n]*geometric_tolerance' backend/app
```

Expected: all gates pass；final `rg` returns no production writer or compatibility reader for GD&T coarse semantics。

#### GDT-10A: Bind Recognition Identity And Freeze Localized Timeout Semantics

**Design source:**

- `docs/superpowers/specs/2026-08-01-provider-timeout-retry-and-partial-failure-design.md`

**Runtime prerequisite:**

- Merge `docs/superpowers/specs/2026-08-01-compose-worktree-runtime-isolation-design.md` and `docs/superpowers/plans/2026-08-01-compose-worktree-runtime-isolation.md` into this branch before live。
- The isolation owner is checkout/worktree root identity；its completion proof must include distinct main/feature Compose project、network and volume identities，unchanged main data identities，port-conflict fail-closed behavior，focused topology tests and runtime/public smoke。
- Required prerequisite commands are the isolation plan's `micromamba run -n qi-p0 pytest backend/tests/integration/test_runtime_topology.py -q`、two Compose config checks and runtime health/project-list checks。GDT-10A does not edit or stage those files。
- During the eventual GDT live window，this worktree's project must be the exclusive owner of the configured API/frontend ports；another project may not be stopped、recreated or overwritten implicitly。

**Problem boundary:**

- Single owner: `CandidateAdvisor`/`ProductionRetryCoordinator` own `production_uncertainty` retry and localized disposition；`ReviewService` only preserves that decision。
- Old activation path: GDT-10 live project inherits unchecked `legacy_high_recall` and reaches paid processing before mode mismatch is observable。
- Old review path: `ReviewService._review_coverage()` applies generic `system_default` to localized Provider failures and silently changes them to `non_inspection`。
- Replacement: zero-paid API/worker/hash/database recognition preflight，existing production localized-failure path，and working-copy preservation of the Owner-committed failure stage。
- Unchanged: `timeout=60.0`、SDK `max_retries=0`、production schema-only single retry、page/project/call budgets、public runtime default、legacy sequential retry behavior、ordinary `visual_no_detection` default and all GDT semantics。

**Files:**

- Modify: `.agent/harness/scripts/run-p0.py`
- Modify: `backend/tests/contract/harness/test_live_run_contract.py`
- Modify: `backend/tests/integration/test_symbol_recognition_pipeline.py`
- Modify: `backend/app/review/service.py`
- Modify: `backend/tests/integration/test_review_working_copy.py`
- Modify: `backend/app/candidates/advisor.py` only if the focused integration RED proves the documented production path is not already satisfied；do not refactor or modify legacy behavior otherwise。

**Interfaces:**

- Consumes: API/worker code hashes、`Settings.symbol_recognition_mode`、`symbol_routing_identity()`、model identity、PostgreSQL Alembic revision and CandidateAdvisor coverage entry。
- Produces: zero-paid exact runtime preflight；timeout/transport attempt event/outcome with no fabricated Provider identity；sibling-preserving `AutomaticResult.completeness`/project phase；working-copy `ambiguous + requires_confirmation` coverage。

- [ ] **Step 1: Write RED Harness runtime-identity tests**

Add contract cases around `preflight_full_p0_live()` proving:

```python
def test_full_live_rejects_mixed_runtime_before_run_or_paid_work(...) -> None:
    observed = {
        "api": {
            "mode": "legacy_high_recall",
            "router": "legacy",
            "model": "qwen3-vl-plus-2025-12-19",
            "hashes": current_hashes(),
        },
        "worker": {
            "mode": "production_uncertainty",
            "router": "symbol-uncertainty-router/1",
            "model": "qwen3-vl-plus-2025-12-19",
            "hashes": stale_hashes(),
        },
        "database_revision": "0012",
    }
    with pytest.raises(ValueError, match="runtime identity"):
        preflight_with_runtime_identity(observed)
    assert harness_run_directories() == before
    assert registration_calls == []
    assert provider_calls == []
```

Add isolated cases for API/worker mode、model、router、each of the 12 code hashes、missing container、invalid JSON and database revision mismatch，plus one exact success case。Do not assert or print credential、database URL or environment values。

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_live_run_contract.py -k 'runtime_identity' -q
```

Expected: RED because current preflight validates only API file hashes，not worker hashes、mode/model/router or database revision。

- [ ] **Step 2: Write RED working-copy failure-preservation tests**

In `test_review_working_copy.py`，call `ReviewService._review_coverage()` with the exact production failure shape:

```python
{
    "observation_id": "visual-timeout",
    "disposition": "ambiguous",
    "source_location_id": "visual-timeout",
    "coordinates": [1, 2, 3, 4],
    "candidate_id": None,
    "requires_confirmation": True,
    "advisor_review": {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/3",
        "failure_stage": "provider_timeout",
    },
}
```

Assert the projected entry retains `disposition="ambiguous"`、`requires_confirmation=true`、coordinates/source ID and a safe top-level `failure_stage="provider_timeout"`，with `review_required_count=1` and no raw exception。Parameterize `provider_timeout|provider_transport_failure|provider_schema_invalid`。Keep the existing `visual_no_detection -> non_inspection + system_default` test unchanged and GREEN。

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_review_working_copy.py -k 'provider_failure or owner_committed_discriminator' -q
```

Expected: localized Provider case is RED because current generic default silently resolves it；ordinary no-detection remains GREEN。

- [ ] **Step 3: Strengthen production localized-failure characterization**

Extend `test_one_localized_provider_failure_preserves_every_sibling_as_partial` for `failure_family in {"timeout", "transport"}` to assert:

- failed ROI Provider method is invoked exactly once；
- attempt event is the exact safe failure stage with `attempt_index=0` and null `provider_request_id`；
- terminal outcome is `unresolved` with the corresponding observation outcome；
- no call record、request/response artifact、cache winner or retry artifact exists for the failed timeout/transport crop；
- successful/cache siblings、technical requirements、Coverage coordinates and candidates remain intact；
- `AutomaticResult.completeness="partial_review_required"` and `ProjectService.status().phase="partial_review_required"`；do not add a duplicate working-copy completeness field；
- exception text/path/token is absent from persisted and returned evidence。

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_symbol_recognition_pipeline.py -k 'localized_provider_failure' -q
```

Expected: CandidateAdvisor/AutomaticResult behavior should remain GREEN；new exact call-count/artifact/project-phase assertions expose any real gap。If RED，change only the exact owning seam and do not add timeout/transport retry。

- [ ] **Step 4: Preserve localized Provider failure through review projection**

In `ReviewService._review_coverage()`，recognize only the exact allowlisted advisor-review shape with `route="visual_symbol"`、`schema_version="visual-symbol-review/3"` and one of the three localized failure stages。Copy only `failure_stage` to the projected entry before removing `advisor_review`，and exclude that entry from the generic system-default conversion。Do not preserve arbitrary Provider metadata。Do not change regular no-detection、technical-requirement or candidate coverage handling。

- [ ] **Step 5: Implement zero-paid API/worker/hash/database preflight**

In `run-p0.py`，replace the API-only helper with one bounded `_require_compose_runtime_identity()` called by `preflight_full_p0_live()` before registration/run creation/source upload。For both `api` and `worker`，compare every `LIVE_API_GDT_RUNTIME_PATHS` SHA against current worktree bytes and compare this exact sanitized identity:

```python
EXPECTED_RECOGNITION_IDENTITY = {
    "mode": "production_uncertainty",
    "router": "symbol-uncertainty-router/1",
    "model": "qwen3-vl-plus-2025-12-19",
}
```

Then query only `SELECT version_num FROM alembic_version` through the current Compose `postgres` service and require exact `0013`。The container programs may import `get_settings()` and `symbol_routing_identity()` but must output only hashes/mode/router/model；the database command may output only revision。Any missing container、nonzero exit、invalid/extra/missing field or mismatch raises `ValueError("Compose runtime identity does not match GDT-10 live contract")`。Do not output database URL、mutate container env/project rows or run migration inside preflight。

- [ ] **Step 6: Run focused GREEN and retry invariants**

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_live_run_contract.py -k 'runtime_identity' -q
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_review_working_copy.py -k 'provider_failure or owner_committed_discriminator' -q
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_symbol_recognition_pipeline.py -k 'localized_provider_failure or actual_primary_wall_blocks_retry' -q
rg -n 'timeout=60\.0|max_retries=0' backend/app/providers/runtime.py
rg -n 'MAX_VISUAL_PAGE_WALL_SECONDS = 45\.0|MAX_VISUAL_PROJECT_WALL_SECONDS = 90\.0' backend/app/candidates/symbol_escalation_contracts.py
git diff --check
```

Expected: focused tests pass；timeout/transport use zero retry；production schema invalid remains the only `ProductionRetryCoordinator`-authorized retry；legacy sequential retry remains unchanged；all four runtime/budget constants are unchanged。

- [ ] **Step 7: Run full offline regression gates**

```bash
python .agent/harness/scripts/check-contracts.py
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness -q
make test-backend
git diff --check
```

No live Provider command is allowed in this step。

- [ ] **Step 8: Independent timeout-boundary review**

Reviewer must return `accept|accept with concerns|reject` and verify production single retry Owner、zero timeout/transport retry、no fabricated Provider identity、working-copy failure preservation、unchanged no-detection default、legacy activation retirement、API/worker/hash/database preflight ordering、privacy、budget invariants and false-success boundary。Any new production retry outside `ProductionRetryCoordinator`、mode/hash/DB check after paid work、silent failure-to-non-inspection conversion or partial-to-success conversion is blocking。

- [ ] **Step 9: Commit GDT-10A implementation only**

```bash
git add .agent/harness/scripts/run-p0.py backend/tests/contract/harness/test_live_run_contract.py backend/tests/integration/test_symbol_recognition_pipeline.py backend/app/review/service.py backend/tests/integration/test_review_working_copy.py
git add backend/app/candidates/advisor.py  # only when Step 3 proved a real implementation gap
git commit -m "fix(gdt): bind live timeout disposition"
```

The approved spec/plan amendment is committed separately before implementation。Do not stage Compose isolation files、generated run evidence or unrelated dirty artifacts in the implementation commit。

- [ ] **Step 4: Run current-four live Provider evidence only after explicit live authorization**

Run the repository-owned command:

```bash
make verify-p0-live
```

The command must first perform zero-paid runtime/source/contract preflight，including exact API/worker current-worktree hashes、`production_uncertainty` + router/model、database `0013` and the named Compose-isolation proof；then create fresh Harness-owned current-four and symbol-input registration runs from exact current sources plus the unique Git-HEAD-approved annotation bytes，并把 literal generated IDs 传入 unchanged full-live start path。Step 4 success means current authenticated Provider calls、sealed source/crop/model/prompt/schema identity hashes、typed Case A/B、all existing non-GD&T symbol results and `execution_state=visual_qa_pending:first-pdf-balloons`。A localized timeout may yield a valid partial result but is not Step 4 success if any required acceptance evidence is absent。A final receipt is not expected before headed QA；any failure remains an exact blocker and is not converted to accepted risk。

- [ ] **Step 5: Run headed workbench QA and export proof**

Only after the Step 4 pause evidence above passes, use Chrome MCP or the repository `browse` skill on the exact paused run/project and separately record:

- API payload for Case A/B；
- list labels/value/datum；
- structured edit A -> B；
- save + reload persistence；
- freeze gate behavior；
- PDF/Excel export from the same reviewed result。

Do not treat API proof as headed UI proof。Do not acquire/overwrite another operator's review lock；if lock ownership conflicts, stop with the exact project/operator/expiry metadata but no credential values。

After the run-bound `design-qa.md` passes, resume that same literal run ID。Only the resumed current-four/full-P0 run may generate the final `receipt.json` required for GDT-10 completion；do not start a replacement run or select `latest`。

- [ ] **Step 6: Final independent review**

Reviewer output must include verdict、blocking/non-blocking issues、active Owner inventory、old path removal evidence、migration/downgrade evidence、Case A/B live proof、frontend no-parser proof、export same-reviewed-result proof and test commands。Any remaining second Owner、coarse writer、unsealed live evidence or failed current-four contract blocks completion。

- [ ] **Step 7: Update plan closeout and commit GDT-10**

Update Status from `proposed` to the actual execution state only after every required gate。Record commits、exact test counts、run ID、receipt paths、review verdict、remaining risk and rollback evidence。

```bash
git add backend/app/processing/automatic_result.py backend/app/review/service.py backend/tests/integration/test_geometric_tolerance_migration.py .agent/harness/scripts/run-p0.py backend/tests/contract/harness/test_live_run_contract.py docs/superpowers/plans/2026-08-01-structured-geometric-tolerance-recognition.md
git commit -m "feat(gdt): close structured recognition rollout"
```

## Spec Coverage Matrix

| Design requirement | Plan owner |
| --- | --- |
| Single candidate-domain semantic Owner | GDT-1, GDT-5, GDT-10 |
| Old coarse writer replacement and historical data retirement | GDT-5, GDT-6, GDT-10 |
| Canonical `frames[] -> segments[]` contract | GDT-1 |
| Full v1 subtype enum, `▱ -> ⏥`, decimal strings | GDT-1, GDT-5 |
| M/L/S/unknown, diameter zone, ordered datum references | GDT-1, GDT-5 |
| Composite/multi-layer structure | GDT-1, GDT-5, GDT-9 |
| Native vector frame/cell proposal and independent-line association | GDT-2 |
| Hybrid/scanned raster frame evidence and degradation fixtures | GDT-3 |
| Frozen Provider evidence, allowlist and local validation | GDT-4 |
| Failure codes, typed unknown and Coverage exact-once | GDT-5 |
| JSONB versioning, migration, downgrade and exact OpenAPI | GDT-6 |
| Structured review editing and API reload | GDT-7 |
| Frontend subtype/value/datum/modifier presentation without raw parser | GDT-8 |
| Same-reviewed-result export and frozen/offline E2E | GDT-9 |
| Legacy zero-count, rollback-first proof, authorized live and headed UI | GDT-10 |
| Provider timeout ownership, zero-retry boundary and isolated recognition identity | GDT-10A |

## Self-Review Record

- Spec coverage: every Goals、Target Data Contract、Recognition Architecture、Persistence/API、Frontend、Failure Semantics、Compatibility、Test Matrix and Acceptance Criteria section maps to at least one Task above。
- Scope decision: one vertical plan is retained because every layer consumes the same canonical frame contract；splitting backend/frontend plans would allow schema drift and prevent an independently testable end-to-end deliverable。
- Placeholder scan: no unresolved task、file、command、type or expected-result placeholder remains；generated Harness run IDs are intentionally produced only by the repository command。
- Type consistency: generic `CandidateType` remains unchanged；new result union is `StructuredCandidate`；inventory/provider/result/review versions progress as `/2`、`/3`、`/3`、`/3`；migration revision is `0013_structured_gdt`；frontend consumes the generated `edit_geometric_tolerance` command。
- Old-path convergence: all new GD&T inputs reach `GeometricToleranceNormalizer`；legacy coarse payloads become typed unknown；the temporary `/2` adapter has a real consumer、trigger、deadline and explicit removal in GDT-10。
- Rollback: isolated downgrade and workbench GET are ordered before broader tests；production rollback remains vetoed without snapshot/backup authority。
- Verification separation: unit、contract、integration、offline E2E、live Provider、headed UI and export evidence are each explicit and are not treated as interchangeable。
- Timeout boundary: `60s` Provider timeout is not retried against a `45s` page wall budget；GDT-10 uses the existing production localized partial path and rejects legacy mode before paid work。

## Completion Contract

本计划只有同时满足以下条件才可报告完成：

- typed candidate、frame/cell evidence、Provider `/3`、normalizer、JSONB `/3`、review/API、frontend、export 全部落地；
- Case A 精确得到 parallelism、`0.1`、datum A；Case B 精确得到 flatness、`0.08`；
- M/L/S、diameter zone、datum order、composite/multi-layer、typed unknown 都有 tests；
- native vector、hybrid/raster、low-resolution、skew、broken/adhesive line 和 negative table fixtures 通过；
- no frontend/raw-text semantic parser；
- no new GD&T coarse writer，marked `/2` GD&T adapter 已删除，数据库 legacy count 为 zero；
- upgrade/downgrade 和 rollback-first workbench GET 已验证；
- focused/full backend、frontend、OpenAPI、build、offline E2E、authorized live current-four、headed UI、export proof 全部实际运行；
- independent reviewer verdict 为 `accept`；
- current P0 contract matrix、public runtime config 或 production deployment 未经额外授权不改变；GDT-10 isolated verification runtime 必须显式证明 `production_uncertainty` identity。
