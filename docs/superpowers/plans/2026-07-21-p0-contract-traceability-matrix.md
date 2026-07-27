# P0 Contract Traceability Matrix

**Status:** Execution in progress; D6-T2 complete, D6-T3 next

**Date:** 2026-07-22

**Owner:** 当前七天 P0 实施选择、任务与验证映射

**Global contract source:** `docs/contracts/MAIN_CONTRACT_MATRIX.md`

**Implementation plan:** `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`

本文件保留 design spec Section 10.1 拆出的 111 个细粒度 P0 ID。它回答当前 P0 选择了哪些 global contracts、如何细化、由哪个 task 实现、用什么 selector 验证以及当前是否执行；它不拥有全局长期语义。

## Authority And Generation Chain

```text
Global Main Contract Matrix
→ this P0 Markdown Traceability Matrix
→ .agent/harness/contracts/p0-contracts.json
→ .agent/harness/contracts/global-contract-bindings.json
→ policy
→ scripts
→ immutable runs/<run-id>/
→ receipt.json
```

- 本文件是 `p0-contracts.json` 唯一的人类可编辑生成来源。
- `p0-contracts.json` 是机器镜像，不允许手工形成语义分叉。
- `global-contract-bindings.json` 只能从镜像生成，是反向索引，不是第二事实来源。
- policy 只裁决结果；scripts 只选择、执行和收集既有 backend/frontend tests。
- run 目录保存某次不可变证据；receipt 只说明该 run 是否满足当前 P0。
- `passed` 只投影已有sealed task receipt；本次visual acceptance replan改变定义的BAL/UI/ACC行重置为 `not_run`，必须由更新后的D7-T2/full-p0 live evidence重新证明。
- `current_status` 是 run evidence 的人类可读 projection，不属于 contract definition；receipt freshness 使用排除该列的 `contract_definition_hash`，同时记录但不以 `status_projection_hash` 判 stale。

## Reclassification Rules

1. 业务语义行必须有一个有效 `global_contract_id`。
2. 纯实现选择使用 `implementation_only=true`、`global_contract_id=null`，并填写 reason 与 `related_global_contract_ids[]`。
3. 多个 P0 行可细化同一 global contract；business row 的 primary global ID 表示直接 enforcement，related IDs 只表示支撑关系；不得用 P0 行反向改变 global contract。
4. P1/P2 global contracts 不产生七天 task 或 selector。
5. `blocking_level` 描述违反该 P0 requirement 对 verdict 的最高影响；即使需求本身要求产生 review-required 状态，对该需求的错误实现仍会阻止 P0 passed。
6. `current_status` 只允许 `passed/failed/blocked/not_run`，且只能由具体 run evidence 推导；计划编辑不能改成 passed。
7. 生成镜像必须保留全部 12 列；定义 digest 排除且只排除 `current_status`，其余 requirement/Owner/task/tier/selector/blocking 等变化都使旧 receipt stale。

## Reclassification Summary

| Metric | Count |
| --- | ---: |
| P0 rows | 111 |
| Business rows mapped to global contracts | 101 |
| Implementation-only rows | 10 |
| Unmapped / needs human classification | 0 |
| Duplicate P0 IDs | 0 |
| Rows missing task | 0 |
| Rows missing selector | 0 |
| P0/P0-partial global rows without typed binding | 0 |
| P1/P2 rows selected or related into P0 tasks | 0 |

| P0 Domain | Count |
| --- | ---: |
| RUN | 14 |
| REC | 28 |
| REV | 13 |
| BAL | 14 |
| UI | 8 |
| EXP | 19 |
| RES | 8 |
| ACC | 7 |

## P0 Contract Rows

Each table uses the same columns:

- `p0_contract_id`
- `global_contract_id`
- `implementation_only`
- `related_global_contract_ids[]`
- `stable_p0_requirement`
- `owner`
- `task_id`
- `tier`
- `verification_selector`
- `blocking_level`
- `current_status`
- `implementation_reason`

### RUN — Runtime

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-RUN-001` | `null` | `true` | `[PRJ-003, PRJ-007]` | 运行拓扑恰为一个 FastAPI service、一个 concurrency=1 Celery Worker service、一个 React frontend、PostgreSQL、Redis 和一个共享 FileStorage volume | Runtime composition | `D1-T2` | integration | `pytest backend/tests/integration/test_runtime_topology.py::test_compose_has_exact_p0_services -q` | `blocking` | `passed` | 精确 service 数量、当前 runtime topology 与 Worker concurrency=1 是七天实现选择。 |
| `P0-RUN-002A` | `null` | `true` | `[SYS-002, PRJ-003]` | API 与 Worker 解析到同一个受控存储根目录 | FileStorage | `D1-T3` | integration | `pytest backend/tests/integration/test_storage.py::test_api_and_worker_share_storage_root -q` | `blocking` | `passed` | API/Worker 共享同一本地目录是当前 FileStorage 部署选择；长期契约只固定受控 resource_ref、完整性与可见性。 |
| `P0-RUN-002B` | `SYS-002` | `false` | `[]` | 写入先落在目标目录同一文件系统内的临时路径 | FileStorage | `D1-T3` | unit | `pytest backend/tests/unit/storage/test_local.py::test_write_starts_in_same_filesystem_temp_path -q` | `blocking` | `passed` | — |
| `P0-RUN-002C` | `SYS-002` | `false` | `[]` | 发布前校验内容 SHA-256 与字节数 | FileStorage | `D1-T3` | unit | `pytest backend/tests/unit/storage/test_local.py::test_hash_or_size_mismatch_rejects_publish -q` | `fatal` | `passed` | — |
| `P0-RUN-002D` | `SYS-002` | `false` | `[]` | 校验后使用原子重命名；中断或失败不产生正式引用 | FileStorage | `D1-T3` | unit | `pytest backend/tests/unit/storage/test_local.py::test_atomic_replace_is_the_only_publish_step -q` | `fatal` | `passed` | — |
| `P0-RUN-002E` | `SYS-002` | `false` | `[]` | PostgreSQL 只保存文件引用、hash、size、MIME type 和 created-at 基础元数据 | File metadata repository | `D1-T3` | integration | `pytest backend/tests/integration/test_storage.py::test_database_persists_only_file_metadata -q` | `blocking` | `passed` | — |
| `P0-RUN-003` | `PRJ-006` | `false` | `[]` | 提交处理前检查 shared storage、Redis/Celery 和已配置 OCR/LLM Provider；任一 unavailable 都拒绝新任务 | Capability Veto Gate | `D2-T3` | integration | `pytest backend/tests/integration/test_processing_preflight.py -q` | `blocking` | `passed` | — |
| `P0-RUN-004` | `PRJ-006` | `false` | `[]` | 提交导出前检查受控 template 与 balloon font 的路径/hash；失败拒绝导出 | Capability Veto Gate | `D6-T1` | integration | `pytest backend/tests/integration/test_export_preflight.py -q` | `blocking` | `passed` | — |
| `P0-RUN-005` | `REV-004` | `false` | `[]` | 每个写命令记录非空 `operator_id`，不引入身份/RBAC 平台 | Operation audit repository | `D1-T3` | integration | `pytest backend/tests/integration/test_operator_audit.py -q` | `blocking` | `passed` | — |
| `P0-RUN-006` | `REV-003` | `false` | `[]` | 一个项目同时最多一个 active editor | Review lock service | `D4-T2` | integration | `pytest backend/tests/integration/test_review_lock.py::test_second_editor_is_rejected -q` | `blocking` | `passed` | — |
| `P0-RUN-007` | `REV-003` | `false` | `[SYS-001]` | working-copy 写请求必须携带 PostgreSQL `expected_version`；stale write 返回 conflict 且不覆盖当前值 | Review aggregate | `D4-T2` | integration | `pytest backend/tests/integration/test_review_version.py -q` | `blocking` | `passed` | — |
| `P0-RUN-008` | `REV-003` | `false` | `[]` | editor lock 到期后可由下一 operator 获取；未到期不可抢占 | Review lock service | `D4-T2` | unit | `pytest backend/tests/unit/review/test_locks.py::test_lock_expiry_uses_database_clock -q` | `blocking` | `passed` | — |
| `P0-RUN-009` | `PRJ-005` | `false` | `[PRJ-002]` | 项目保存简化 processing/error state；fatal/blocking 不可转换成 formal success | Project state machine | `D2-T3` | integration | `pytest backend/tests/integration/test_processing_state.py -q` | `fatal` | `passed` | — |
| `P0-RUN-010` | `PRJ-004` | `false` | `[]` | 同一 `logical_task_key` 重投最多创建一个 raw result 或 formal export result | Job idempotency service | `D2-T3` | integration | `pytest backend/tests/integration/test_task_idempotency.py -q` | `blocking` | `passed` | — |

### REC — PDF And Recognition

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-REC-001` | `PDF-008` | `false` | `[]` | 当前范围 `vector`/`hybrid` 页面可进入正式处理；`scanned` 只返回 unsupported routing | Input routing Owner | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_classification.py -q` | `blocking` | `passed` | — |
| `P0-REC-002` | `PDF-001` | `false` | `[]` | 多页 PDF 逐页处理并保留稳定 page index/order | Page inventory | `D2-T1` | integration | `pytest backend/tests/integration/test_pdf_inventory.py::test_multi_page_inventory_preserves_order -q` | `blocking` | `passed` | — |
| `P0-REC-003` | `PDF-006` | `false` | `[]` | PyMuPDF native text/coordinate/direction 是首选 observation；OCR 不覆盖 native fact | Page inventory | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_inventory.py::test_native_observation_remains_authoritative -q` | `blocking` | `passed` | — |
| `P0-REC-004` | `null` | `true` | `[PDF-005, PDF-006, PROV-001, PROV-003]` | 腾讯 `GeneralAccurateOCR` 只接收缺失/异常局部 crop，并保存独立 OCR observation | OCR Signal Provider adapter | `D2-T2` | provider-contract | `pytest backend/tests/contract/test_tencent_ocr_provider.py -q` | `blocking` | `passed` | 当前具体 OCR 厂商、API、SDK 与参数是 adapter 实现选择；局部补充和 observation 分离由相关 global contracts 拥有。 |
| `P0-REC-005` | `null` | `true` | `[SYS-003, CAND-004, PROV-001, PROV-002, PROV-003]` | `qwen3-vl-plus` 只复核局部 candidate crop，输出必须通过冻结 JSON Schema；Provider 不拥有正式 disposition | Vision Advisor adapter | `D2-T2` | provider-contract | `pytest backend/tests/contract/test_qwen_vl_provider.py -q` | `blocking` | `passed` | 当前具体 Vision LLM、endpoint 与 request shape 是 adapter 实现选择；Advisor 边界与 schema 校验由相关 global contracts 拥有。 |
| `P0-REC-006A` | `PDF-004` | `false` | `[]` | inventory 保存 span/line 级 native raw/normalized text | Page inventory | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_inventory.py::test_span_and_line_text_round_trip -q` | `blocking` | `passed` | — |
| `P0-REC-006B` | `PDF-001` | `false` | `[]` | 每个 observation 保存 0-based page index | Page inventory | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_inventory.py::test_observation_has_page_index -q` | `blocking` | `passed` | — |
| `P0-REC-006C` | `PDF-002` | `false` | `[]` | 每个 observation 保存以未旋转 CropBox 左上为原点的 clipped `bbox_pdf` | Coordinate transform | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_coordinates.py::test_bbox_is_normalized_and_clipped_to_cropbox -q` | `blocking` | `passed` | — |
| `P0-REC-006D` | `PDF-004` | `false` | `[]` | 每个 native observation 保存方向向量/角度 | Page inventory | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_inventory.py::test_rotated_text_preserves_direction -q` | `blocking` | `passed` | — |
| `P0-REC-006E` | `PDF-003` | `false` | `[]` | 每页保存 classification 与 evidence | Page classification | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_classification.py::test_classification_evidence_is_serializable -q` | `blocking` | `passed` | — |
| `P0-REC-006F` | `PDF-002` | `false` | `[]` | 保存 PDF/render 双向矩阵；往返误差不超过 0.5 PDF point 和 1 pixel | Coordinate transform | `D2-T1` | unit | `pytest backend/tests/unit/pdf/test_coordinates.py::test_pdf_render_round_trip_error_budget -q` | `blocking` | `passed` | — |
| `P0-REC-007A` | `CAND-001` | `false` | `[]` | 解析普通线性尺寸 | Deterministic candidate parser | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_parser.py::test_linear_dimension -q` | `blocking` | `passed` | — |
| `P0-REC-007B` | `CAND-001` | `false` | `[]` | 解析 `±` 对称公差与上下偏差，并保留原始字符串 | Deterministic candidate parser | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_parser.py::test_symmetric_and_asymmetric_tolerance -q` | `blocking` | `passed` | — |
| `P0-REC-007C` | `ITEM-003` | `false` | `[]` | 解析直径/孔；`Φ` 不得自动等同 `hole`，允许 `unknown` + confirmation | Deterministic candidate parser | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_parser.py::test_diameter_feature_kind_is_not_guessed -q` | `blocking` | `passed` | — |
| `P0-REC-007D` | `CAND-001` | `false` | `[]` | 解析 `M` thread spec/depth/through | Deterministic candidate parser | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_parser.py::test_thread -q` | `blocking` | `passed` | — |
| `P0-REC-007E` | `CAND-001` | `false` | `[]` | 解析 `R` radius | Deterministic candidate parser | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_parser.py::test_radius -q` | `blocking` | `passed` | — |
| `P0-REC-007F` | `CAND-001` | `false` | `[]` | 解析 angle 与其公差 | Deterministic candidate parser | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_parser.py::test_angle -q` | `blocking` | `passed` | — |
| `P0-REC-007G` | `CAND-003` | `false` | `[]` | `16 × M5` 等成组标注形成一个 item，公共 `quantity=16` | Candidate grouping | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_grouping.py::test_quantity_prefix_groups_one_item -q` | `blocking` | `passed` | — |
| `P0-REC-007H` | `CAND-003` | `false` | `[]` | depth 绑定正确主要求或有序子要求 | Candidate grouping | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_grouping.py::test_depth_belongs_to_ordered_requirement -q` | `blocking` | `passed` | — |
| `P0-REC-007I` | `CAND-003` | `false` | `[]` | through 绑定正确主要求或有序子要求 | Candidate grouping | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_grouping.py::test_through_belongs_to_ordered_requirement -q` | `blocking` | `passed` | — |
| `P0-REC-007J` | `CAND-003` | `false` | `[ITEM-004]` | 多行组合标注形成一个 composite item 和有序 sub-requirements | Candidate grouping | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_grouping.py::test_multiline_composite_preserves_order -q` | `blocking` | `passed` | — |
| `P0-REC-007K` | `ITEM-006` | `false` | `[]` | 可执行、可验证技术要求形成 `global_requirement` 且默认无气泡；非可执行文本不冒充检验项 | Candidate disposition | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_disposition.py::test_executable_general_requirement -q` | `blocking` | `passed` | — |
| `P0-REC-008A` | `ITEM-003` | `false` | `[]` | 复杂 GD&T 只输出 `raw_text/coordinates/coarse_type/requires_confirmation` | Complex fallback | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_complex_fallback.py::test_gdt_field_allowlist -q` | `blocking` | `passed` | — |
| `P0-REC-008B` | `ITEM-003` | `false` | `[]` | 复杂 roughness 只输出四字段粗分类 | Complex fallback | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_complex_fallback.py::test_roughness_field_allowlist -q` | `blocking` | `passed` | — |
| `P0-REC-008C` | `ITEM-003` | `false` | `[]` | 复杂 weld 只输出四字段粗分类 | Complex fallback | `D3-T1` | unit | `pytest backend/tests/unit/candidates/test_complex_fallback.py::test_weld_field_allowlist -q` | `blocking` | `passed` | — |
| `P0-REC-008D` | `CAND-007` | `false` | `[]` | 跨视图相同文本只标记疑似重复并要求人工确认，不自动合并 | Duplicate Advisor | `D3-T2` | unit | `pytest backend/tests/unit/candidates/test_duplicates.py::test_cross_view_match_is_suggestion_only -q` | `blocking` | `passed` | — |
| `P0-REC-009` | `CAND-005` | `false` | `[PDF-007, CAND-002]` | Coverage Ledger 中每个疑似工程 observation 恰有一个 primary disposition、source 与 coordinates | Coverage Owner | `D3-T2` | unit | `pytest backend/tests/unit/candidates/test_coverage.py::test_every_suspicious_observation_has_complete_disposition -q` | `blocking` | `passed` | — |
| `P0-REC-010` | `CAND-005` | `false` | `[CAND-006]` | `ambiguous` 可进入审核；缺 disposition/source/coordinates 或冲突归属为 blocking | Coverage Veto Gate | `D3-T2` | unit | `pytest backend/tests/unit/candidates/test_coverage.py::test_ambiguous_is_reviewable_but_incomplete_is_blocking -q` | `blocking` | `passed` | — |

### REV — Candidate Review

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-REV-001` | `REV-001` | `false` | `[]` | immutable original candidates 与 mutable current candidates 分离保存 | Review aggregate | `D4-T1` | integration | `pytest backend/tests/integration/test_review_working_copy.py::test_original_is_immutable_and_current_is_separate -q` | `blocking` | `passed` | — |
| `P0-REV-002` | `REV-004` | `false` | `[]` | 每个 working-copy command 保存简化 modification log | Review aggregate | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_modification_log_records_command_sequence -q` | `blocking` | `passed` | — |
| `P0-REV-003` | `ITEM-001` | `false` | `[]` | candidate/item 保存到一个或多个 source locations 的基本关系 | Review aggregate | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_source_relations_round_trip -q` | `blocking` | `passed` | — |
| `P0-REV-004` | `REV-004` | `false` | `[]` | operator 可保留 candidate | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_keep_candidate -q` | `blocking` | `passed` | — |
| `P0-REV-005` | `REV-004` | `false` | `[]` | operator 可排除 candidate；排除不物理删除 original candidate | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_exclude_candidate_without_deleting_original -q` | `blocking` | `passed` | — |
| `P0-REV-006` | `REV-004` | `false` | `[]` | operator 可修改 `raw_text`，修改后保留 manual provenance | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_edit_raw_text -q` | `blocking` | `passed` | — |
| `P0-REV-007` | `REV-004` | `false` | `[ITEM-002]` | operator 可修改 common/typed core fields，数值使用 Decimal 语义并保留原文 | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_edit_typed_core_fields -q` | `blocking` | `passed` | — |
| `P0-REV-008` | `ITEM-003` | `false` | `[]` | 复杂类型可编辑字段严格限于 `raw_text/coordinates/coarse_type/requires_confirmation` | Review schema Veto Gate | `D4-T1` | contract | `pytest backend/tests/contract/test_review_schema.py::test_complex_item_rejects_extra_semantic_fields -q` | `blocking` | `passed` | — |
| `P0-REV-009` | `REV-004` | `false` | `[]` | operator 可人工新增遗漏项，source 标为 manual 并要求显式坐标/作用域 | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_add_manual_item -q` | `blocking` | `passed` | — |
| `P0-REV-010` | `BAL-002` | `false` | `[]` | operator 可修改 `balloon_required`；该操作只标记 suggested numbering stale，不静默重排 | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_set_balloon_required_marks_numbering_stale -q` | `blocking` | `passed` | — |
| `P0-REV-011` | `CAND-007` | `false` | `[]` | 简单 merge 生成一个 current item、保留全部 source IDs，quantity 不自动累加 | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_simple_merge_preserves_sources_without_quantity_sum -q` | `blocking` | `passed` | — |
| `P0-REV-012` | `CAND-007` | `false` | `[]` | 简单 split 生成多个 current items，并各自保留输入 candidate source relation | Review command service | `D4-T1` | integration | `pytest backend/tests/integration/test_review_operations.py::test_simple_split_preserves_source_relations -q` | `blocking` | `passed` | — |
| `P0-REV-013` | `REV-006` | `false` | `[]` | 所有 `requires_confirmation` 均显式 resolved 后才允许 freeze | Review freeze Veto Gate | `D4-T2` | integration | `pytest backend/tests/integration/test_review_freeze.py::test_unresolved_confirmation_blocks_freeze -q` | `blocking` | `passed` | — |

### BAL — Balloons

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-BAL-001` | `BAL-002` | `false` | `[]` | working copy 产生稳定、连续但非正式的 suggested numbers | Numbering Owner | `D5-T1` | unit | `pytest backend/tests/unit/balloons/test_numbering.py::test_suggested_numbers_are_stable_and_contiguous -q` | `blocking` | `passed` | — |
| `P0-BAL-002` | `BAL-002` | `false` | `[]` | formal numbers 只能在 reviewed item set freeze 后、`reviewed_result` 创建前生成 | Numbering Owner | `D5-T2` | integration | `pytest backend/tests/integration/test_balloon_service.py::test_formal_numbers_require_frozen_item_set -q` | `blocking` | `passed` | — |
| `P0-BAL-003` | `BAL-003` | `false` | `[]` | 默认正式编号从 1 开始 | Numbering Owner | `D5-T1` | unit | `pytest backend/tests/unit/balloons/test_numbering.py::test_default_start_is_one -q` | `blocking` | `passed` | — |
| `P0-BAL-004` | `BAL-003` | `false` | `[]` | 正式编号唯一、连续、不留缺号 | Numbering Owner | `D5-T1` | unit | `pytest backend/tests/unit/balloons/test_numbering.py::test_formal_sequence_has_no_gap_or_duplicate -q` | `blocking` | `passed` | — |
| `P0-BAL-005` | `BAL-003` | `false` | `[]` | `balloon_required=false` 的通用要求不占编号 | Numbering Owner | `D5-T1` | unit | `pytest backend/tests/unit/balloons/test_numbering.py::test_general_requirements_do_not_consume_numbers -q` | `blocking` | `passed` | — |
| `P0-BAL-006` | `BAL-004` | `false` | `[]` | placement按稳定正式编号顺序搜索有限八方向与多距离候选；同输入确定性一致，不同气泡无circle/circle、glyph/glyph或glyph/other-circle hard overlap，自身编号完整位于所属圆内 | Placement Owner | `D7-T2` | unit | `pytest backend/tests/unit/balloons/test_collision_layout.py::test_batch_layout_has_no_balloon_or_number_overlap -q` | `blocking` | `passed` | — |
| `P0-BAL-007` | `BAL-004` | `false` | `[]` | 所有合法候选耗尽时返回 `manual_required`、best attempt、完整hard collision flags和reason，不伪装为placed | Placement Owner | `D7-T2` | unit | `pytest backend/tests/unit/balloons/test_collision_layout.py::test_exhausted_legal_positions_require_manual_resolution -q` | `blocking` | `passed` | — |
| `P0-BAL-008` | `BAL-005` | `false` | `[]` | operator 可拖动并以 PDF 坐标保存 balloon center；frontend viewport 坐标不落库 | Balloon command service | `D5-T2` | integration | `pytest backend/tests/integration/test_balloon_operations.py::test_move_persists_pdf_coordinates -q` | `blocking` | `passed` | — |
| `P0-BAL-009` | `BAL-006` | `false` | `[]` | 删除 balloon 不删除 inspection item，也不静默改变 `balloon_required` | Balloon command service | `D5-T2` | integration | `pytest backend/tests/integration/test_balloon_operations.py::test_delete_balloon_preserves_item_and_requirement -q` | `blocking` | `passed` | — |
| `P0-BAL-010` | `BAL-006` | `false` | `[]` | operator 可从 reviewed item 重建 balloon | Balloon command service | `D5-T2` | integration | `pytest backend/tests/integration/test_balloon_operations.py::test_rebuild_balloon -q` | `blocking` | `passed` | — |
| `P0-BAL-011` | `BAL-002` | `false` | `[]` | operator 可调整 stable ordering key；未显式 renumber 前 existing formal numbers 不变 | Numbering Owner | `D5-T2` | integration | `pytest backend/tests/integration/test_balloon_operations.py::test_reorder_does_not_silently_renumber -q` | `blocking` | `passed` | — |
| `P0-BAL-012` | `BAL-003` | `false` | `[]` | operator 可显式重新编号，结果仍满足唯一连续无缺号 | Numbering Owner | `D5-T2` | integration | `pytest backend/tests/integration/test_balloon_operations.py::test_explicit_renumber_is_contiguous -q` | `blocking` | `passed` | — |
| `P0-BAL-013` | `BAL-001` | `false` | `[]` | table item/source selection 与 drawing overlay selection 使用同一 IDs 双向定位 | Workbench selection model | `D5-T3` | frontend | `npm --prefix frontend test -- --run src/components/workbench/selection.test.tsx` | `blocking` | `passed` | — |
| `P0-BAL-014` | `BAL-004` | `false` | `[]` | 跨气泡circle/glyph hard overlap、自身编号未完整落在所属圆内、超页、保护区/来源文字遮挡、编号不可读、图表失联、无有效leader或未解决manual_required均阻止Confirm/export | Balloon validator Veto Gate | `D7-T2` | integration | `pytest backend/tests/integration/test_balloon_validation.py::test_unresolved_hard_collision_blocks_confirm_and_export -q` | `blocking` | `passed` | — |

### UI — Review UI

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-UI-001` | `PDF-001` | `false` | `[]` | workbench 支持多页 PDF 切换并保持当前 selection | PDF workspace | `D4-T3` | frontend | `npm --prefix frontend test -- --run src/components/pdf/PdfWorkspace.test.tsx -t 'switches pages'` | `blocking` | `passed` | — |
| `P0-UI-002` | `PDF-002` | `false` | `[]` | workbench 支持 zoom，overlay 与 PDF viewport 同步缩放 | PDF workspace | `D4-T3` | frontend | `npm --prefix frontend test -- --run src/components/pdf/PdfWorkspace.test.tsx -t 'zooms overlays'` | `blocking` | `passed` | — |
| `P0-UI-003` | `PDF-002` | `false` | `[]` | workbench 支持 pan，不改变持久化 PDF 坐标 | PDF workspace | `D4-T3` | frontend | `npm --prefix frontend test -- --run src/components/pdf/PdfWorkspace.test.tsx -t 'pans without mutating pdf coordinates'` | `blocking` | `passed` | — |
| `P0-UI-004` | `REV-003` | `false` | `[]` | Product Design工作台同页区分candidate/source、全部active required balloons与leader，并显示真实active/excluded/manual-required统计、筛选和collision state | Workbench presentation executor | `D7-T2` | frontend | `npm --prefix frontend test -- --run src/components/workbench/RecognitionSummary.test.tsx src/components/workbench/InspectionItemTable.test.tsx src/components/balloons/BalloonOverlay.test.tsx` | `blocking` | `passed` | — |
| `P0-UI-005` | `BAL-001` | `false` | `[]` | 左图与右表点击任一侧会定位并高亮另一侧 | Workbench selection model | `D5-T3` | frontend | `npm --prefix frontend test -- --run src/components/workbench/selection.test.tsx` | `blocking` | `passed` | — |
| `P0-UI-006` | `REV-004` | `false` | `[]` | 核心审核表单支持 keep/exclude/edit/add/split/confirmation/balloon-required；重复建议由识别阶段内部产生，不提供通用人工 merge 入口 | Review UI | `D4-T3` | frontend | `npm --prefix frontend test -- --run src/components/review/ReviewPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx` | `blocking` | `passed` | — |
| `P0-UI-007` | `REV-003` | `false` | `[]` | 明确 Save 动作只保存 working copy，并携带 `expected_version/operator_id`；P0 不新增 autosave contract | Review mutation client | `D4-T3` | frontend | `npm --prefix frontend test -- --run src/features/review/saveWorkingCopy.test.ts src/components/workbench/InspectionWorkbench.test.tsx` | `blocking` | `passed` | — |
| `P0-UI-008` | `REV-006` | `false` | `[]` | 明确 Confirm 动作冻结 reviewed result；普通 Save 不会 freeze | Review freeze UI | `D5-T3` | frontend | `npm --prefix frontend test -- --run src/components/workbench/FreezeReviewButton.test.tsx` | `blocking` | `passed` | — |

### EXP — Export

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-EXP-001` | `EXP-001` | `false` | `[]` | 正式 export 只接受一份已登记 template ID/version/hash/sheet/capacity/mapping version 的受控 `.xlsx` | Template registry | `D6-T1` | unit | `pytest backend/tests/unit/exports/test_template_registry.py -q` | `blocking` | `passed` | — |
| `P0-EXP-002` | `EXP-002` | `false` | `[]` | 固定映射覆盖物料编码、物料名称、图样代号、材质、版本、气泡序号、检验项目、检验标准、检测方法、重点尺寸、检验角色、来源页码和气泡图 | SIP Excel executor | `D6-T2` | unit | `pytest backend/tests/unit/exports/test_excel_mapping.py::test_all_fixed_fields_are_mapped -q` | `blocking` | `passed` | — |
| `P0-EXP-003` | `EXP-001` | `false` | `[]` | logical detail 超过登记容量时明确阻止正式导出；P0 不动态发明通用扩容规则 | Export Veto Gate | `D6-T2` | unit | `pytest backend/tests/unit/exports/test_excel_mapping.py::test_capacity_overflow_is_blocking -q` | `blocking` | `passed` | — |
| `P0-EXP-004` | `EXP-004` | `false` | `[]` | 正式带气泡 PDF 由 backend 从 original PDF、reviewed result 和 PDF 坐标绘制 | Balloon PDF executor | `D6-T1` | integration | `pytest backend/tests/integration/test_balloon_pdf_renderer.py -q` | `blocking` | `passed` | — |
| `P0-EXP-005` | `EXP-004` | `false` | `[]` | Excel 按原页码顺序嵌入正式带气泡 PDF 的全部页面图像 | SIP Excel executor | `D6-T2` | integration | `pytest backend/tests/integration/test_excel_export.py::test_all_ballooned_pages_are_embedded_in_order -q` | `blocking` | `passed` | — |
| `P0-EXP-006` | `EXP-007` | `false` | `[]` | 生成 workbook 必须可由 openpyxl 重新打开 | Excel validator | `D6-T2` | integration | `pytest backend/tests/integration/test_excel_export.py::test_workbook_reopens -q` | `blocking` | `passed` | — |
| `P0-EXP-007A` | `EXP-007` | `false` | `[]` | Excel logical detail count 等于 reviewed inspection-item count | Cross-artifact Veto Gate | `D6-T3` | export | `pytest backend/tests/integration/test_export_consistency.py::test_logical_detail_count_matches_reviewed_items -q` | `blocking` | `passed` | — |
| `P0-EXP-007B` | `EXP-007` | `false` | `[]` | balloon count 等于 `balloon_required=true` item count | Cross-artifact Veto Gate | `D6-T3` | export | `pytest backend/tests/integration/test_export_consistency.py::test_balloon_count_matches_required_items -q` | `blocking` | `passed` | — |
| `P0-EXP-007C` | `EXP-007` | `false` | `[]` | ballooned PDF 正式编号与 Excel 气泡序号一致 | Cross-artifact Veto Gate | `D6-T3` | export | `pytest backend/tests/integration/test_export_consistency.py::test_pdf_and_excel_numbers_match -q` | `blocking` | `passed` | — |
| `P0-EXP-007D` | `EXP-002` | `false` | `[]` | `global_requirement` 且无气泡的 logical detail 序号为空 | Excel validator | `D6-T2` | export | `pytest backend/tests/integration/test_excel_export.py::test_general_requirement_number_is_blank -q` | `blocking` | `passed` | — |
| `P0-EXP-007E` | `EXP-007` | `false` | `[ITEM-005]` | 正式 Excel 必填字段只使用 reviewed/confirmed values，不回读 raw suggestion | Excel validator | `D6-T2` | export | `pytest backend/tests/integration/test_excel_export.py::test_required_cells_use_confirmed_values -q` | `blocking` | `passed` | — |
| `P0-EXP-007F` | `EXP-001` | `false` | `[]` | workbook 的登记 sheet、fixed range 和 sign-off range 未被覆盖 | Excel validator | `D6-T2` | export | `pytest backend/tests/integration/test_excel_export.py::test_fixed_and_signoff_ranges_are_preserved -q` | `blocking` | `passed` | — |
| `P0-EXP-007G` | `EXP-007` | `false` | `[]` | workbook embedded-image page count 等于 source PDF page count | Excel validator | `D6-T2` | export | `pytest backend/tests/integration/test_excel_export.py::test_embedded_image_count_matches_pdf_pages -q` | `blocking` | `passed` | — |
| `P0-EXP-007H` | `EXP-007` | `false` | `[]` | 输出 workbook 的审核填写单元格保持可编辑并可再次保存 | Excel validator | `D6-T2` | export | `pytest backend/tests/integration/test_excel_export.py::test_review_cells_are_editable_and_resavable -q` | `blocking` | `passed` | — |
| `P0-EXP-007I` | `EXP-007` | `false` | `[]` | 正式 ballooned PDF page count 等于 source PDF page count | PDF validator | `D6-T1` | export | `pytest backend/tests/integration/test_balloon_pdf_renderer.py::test_page_count_matches_source -q` | `blocking` | `passed` | — |
| `P0-EXP-007J` | `EXP-003` | `false` | `[]` | 来自 PDF/OCR/LLM/user 且以 `= + - @` 开头的文本写成普通字符串，不形成公式 | Excel validator | `D6-T2` | security | `pytest backend/tests/unit/exports/test_excel_safety.py::test_untrusted_prefixes_are_escaped_as_text -q` | `blocking` | `passed` | — |
| `P0-EXP-007K` | `EXP-003` | `false` | `[]` | 文件名/sheet name 处理路径穿越、非法字符、31-char 限制和重名 | Export naming | `D6-T2` | security | `pytest backend/tests/unit/exports/test_naming.py -q` | `blocking` | `passed` | — |
| `P0-EXP-008` | `EXP-008` | `false` | `[SYS-006]` | manifest 保存 schema version、reviewed-result/input/template/font hashes、artifact hashes、counts 和 renderer/mapping versions | Manifest executor | `D6-T3` | unit | `pytest backend/tests/unit/exports/test_manifest.py -q` | `blocking` | `passed` | — |
| `P0-EXP-009` | `EXP-006` | `false` | `[]` | PDF、Excel、manifest 在独立 staging 全部生成并验证后才原子标记 success；失败时普通下载面不暴露任何部分产物 | Export orchestrator Owner | `D6-T3` | integration | `pytest backend/tests/integration/test_export_atomicity.py -q` | `fatal` | `passed` | — |

### RES — Minimum Result Layers

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-RES-001` | `REV-002` | `false` | `[]` | processing 完成后冻结 immutable `raw_automatic_result`；working edits 不得原地修改 | Automatic-result repository | `D3-T2` | integration | `pytest backend/tests/integration/test_result_layers.py::test_raw_result_is_immutable -q` | `blocking` | `passed` | — |
| `P0-RES-002` | `REV-003` | `false` | `[]` | `review_working_copy` 是独立、versioned、可保存的编辑层 | Review aggregate | `D4-T1` | integration | `pytest backend/tests/integration/test_result_layers.py::test_working_copy_is_versioned -q` | `blocking` | `passed` | — |
| `P0-RES-003` | `REV-006` | `false` | `[]` | Confirm 后创建 immutable `reviewed_result`；后续 mutation 被拒绝 | Review freeze Owner | `D5-T2` | integration | `pytest backend/tests/integration/test_result_layers.py::test_reviewed_result_is_immutable -q` | `blocking` | `passed` | — |
| `P0-RES-004` | `EXP-005` | `false` | `[]` | 正式 PDF、Excel 和 manifest 均引用同一 `reviewed_result_id` | Export orchestrator Owner | `D6-T3` | integration | `pytest backend/tests/integration/test_export_consistency.py::test_artifacts_share_reviewed_result_id -q` | `blocking` | `passed` | — |
| `P0-RES-005` | `PROV-003` | `false` | `[SYS-002, SYS-005, PROV-004, DIAG-001]` | 保存必要 Provider request/response `resource_ref`、request ID 与 schema/prompt/model versions；不保存 secret、Authorization 或完整 base64 | Provider-call repository | `D2-T2` | provider-contract | `pytest backend/tests/contract/test_provider_call_records.py::test_refs_and_versions_persist_without_secrets -q` | `blocking` | `passed` | — |
| `P0-RES-006` | `SYS-004` | `false` | `[]` | 保存结构化 processing/review/export errors，并能定位 page/region/candidate/artifact | Error repository | `D2-T3` | integration | `pytest backend/tests/integration/test_error_records.py -q` | `blocking` | `passed` | — |
| `P0-RES-007` | `REV-004` | `false` | `[]` | 保存简化 operation summary：operator、command、target IDs、before/after version 和 timestamp | Operation audit repository | `D4-T1` | integration | `pytest backend/tests/integration/test_operator_audit.py::test_review_operation_summary -q` | `blocking` | `passed` | — |
| `P0-RES-008` | `PROV-005` | `false` | `[DIAG-003]` | 保存 Provider call count、duration、retry count、estimated cost 和同一 logical-task reuse；P0 不建立跨运行通用 Provider cache | Provider telemetry | `D2-T2` | provider-contract | `pytest backend/tests/contract/test_provider_call_records.py::test_minimum_call_statistics -q` | `blocking` | `passed` | — |

### ACC — P0 Hard Acceptance

| P0 Contract ID | Global Contract ID | Implementation Only | Related Global Contract IDs | Stable P0 Requirement | Owner | Task ID | Tier | Verification Selector | Blocking Level | Current Status | Implementation Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P0-ACC-001` | `null` | `true` | `[PRJ-001, PDF-001, PDF-003]` | 四份 PDF 均可上传并完成 processing；A3/A4 与 1/2 页事实匹配 frozen manifest | P0 harness | `D7-T2` | live-e2e | `phase://live/process?input_set=current-four` | `blocking` | `passed` | current-four 文件、hash、图幅和 process phase 是当前 P0 数据与验收编排。 |
| `P0-ACC-002` | `null` | `true` | `[CAND-005, REV-002]` | 四份均产生带source/coordinates/disposition的可审核candidates；质量人员逐页确认应检验项均keep/add且excluded有明确disposition evidence，空结果、coverage blocking或mass exclusion不得冒充ready | P0 harness | `D7-T2` | live-e2e | `phase://live/candidates?input_set=current-four` | `blocking` | `passed` | current-four candidate/coverage和operator-confirmed item-set completeness是当前P0验收编排。 |
| `P0-ACC-003` | `null` | `true` | `[REV-004, REV-006]` | 四份均可完成至少一次 keep/exclude/edit/add/confirmation，并在适用样例执行 merge 或 split | P0 harness | `D7-T2` | live-e2e | `phase://live/review?input_set=current-four` | `blocking` | `passed` | current-four 必做的具体 review command 组合是当前试用验收编排。 |
| `P0-ACC-004` | `null` | `true` | `[BAL-006, BAL-007]` | 四份的每个active balloon-required item均有一个可见可读正式气泡；完成drag、delete/rebuild、explicit renumber后hard collision和unresolved manual-required均为0 | P0 harness | `D7-T2` | browser-live-e2e | `phase://live/balloons?input_set=current-four` | `blocking` | `passed` | current-four browser balloon操作、可见性和零hard-collision是当前试用验收编排。 |
| `P0-ACC-005` | `null` | `true` | `[EXP-004, EXP-005, EXP-006]` | operator从同一Product Design工作台触发正式export；仅原子成功后每份样例显示恰好ballooned PDF、fixed SIP Excel和manifest三个下载 | P0 harness | `D7-T2` | live-e2e | `phase://live/export?input_set=current-four` | `blocking` | `passed` | current-four同页export和三产物下载phase是当前P0数据与验收编排。 |
| `P0-ACC-006` | `null` | `true` | `[EXP-005, EXP-007]` | 四份的工作台检验项表、reviewed items、balloons、PDF、Excel和manifest使用一致item identity、count与正式编号 | P0 harness | `D7-T2` | live-e2e | `phase://live/consistency?input_set=current-four` | `blocking` | `passed` | current-four UI与cross-artifact consistency phase是当前P0验收编排。 |
| `P0-ACC-007` | `PRJ-005` | `false` | `[EXP-006]` | Provider、storage、template、font 或任一子产物故障都不会产生 formal success/download | Processing / Export formal-success Veto Gate | `D7-T1` | failure-e2e | `phase://failure/no-silent-success` | `fatal` | `passed` | — |

## P0 Input Set And External Gates

这些内容属于 P0 implementation/acceptance context，不进入 global main contract。

### Frozen Current-Four Identity

真实 PDF bytes 和宿主机路径不复制或写入仓库工作树。`.agent/harness/scripts/stage-current-four.py` 在显式 live 模式中原地读取并校验 basename、SHA-256、页数和物理图幅，只把 opaque external input ref、identity 与 page metadata 写入新建的 immutable `.agent/harness/runs/<run-id>/`；正式 upload 后的 bytes 由仓库外受控 FileStorage 持有。`<run-id>` 由脚本实际生成，不是固定目录名。

| Basename | SHA-256 | Pages | Physical page |
| --- | --- | ---: | --- |
| `JS26032501-1-03-036#上下座B#A1.pdf` | `58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec` | 2 | A3 landscape |
| `JS20102801-02-018#手指头#A1.pdf` | `ffee22f2e392f309d3d0acfc2edadc4a8d5330a9bc28009263af5d8597074a86` | 1 | A4 portrait |
| `JS20123103-10-033#手臂拖链支架上改#A2.pdf` | `322d56b00456f495830386b8dc50a32e34086a5bc66d4735e2c3c735d5fbc57d` | 1 | A4 portrait |
| `JS24030402-30-013#上插臂#A0.pdf` | `8fffd93fa7f055f9fe1a7da25bc85630910bdfc2ea86b2ace6ec54979f0a515e` | 2 | A3 landscape |

文件名中的 A0/A1/A2 不是物理页面尺寸依据；live run 以 PDF metadata 为准。

### External Gates

1. **Template Gate:** 质量 Owner 确认唯一 SIP template、sheet、cell mapping、capacity 和批准 hash；当前发现文件只是候选，不自动升级为 truth。
2. **Font Gate:** 质量/法务 Owner 确认 font bytes、license 和 hash。
3. **Provider Gate:** live credentials 只由服务端环境显式注入；fixture 是默认模式，不能伪装 live。
4. **Human Trial Gate:** current-four receipt必须包含质量人员对“自动候选可用、候选可编辑、`operator_confirmed_item_set_is_complete`、非空结果不是假成功、全部required气泡可见可读、hard collision已解决、工作台/PDF/Excel编号一致”的逐样例实际verdict；item-set completeness要求逐页确认所有应检验项已keep/add且excluded有明确operator disposition，不能以mass exclusion或active count非零冒充完成；任一否定答案都阻止freeze/export和receipt通过。
5. **Run Evidence Gate:** `not_run`、stale receipt、latest pointer、旧 run 或 docs claim 不能替代当前 immutable run evidence。

## Harness Mirror Contract

Day 1 实施时才创建以下文件；本 planning turn 不提前实现：

```text
.agent/harness/contracts/p0-contracts.json
.agent/harness/contracts/global-contract-bindings.json
```

生成关系固定为：

```text
this Markdown
→ generate-contract-mirror.py
→ p0-contracts.json
→ generate-global-bindings.py
→ global-contract-bindings.json
```

`check-contracts.py` 必须验证 111 unique、Markdown/JSON逐项相等、所有 business row 的 global ID 存在、所有 implementation-only reason 非空、所有 task/selector 非空、bindings 可由 mirror 确定性重建。任何 JSON 手工漂移都失败，不做双向同步。

Bindings 对每个 global ID 分开保存 `primary_p0_contract_ids`、`related_business_p0_contract_ids` 和 `related_implementation_p0_contract_ids`。后两者不能冒充 primary enforcement；三组都只由 mirror 生成。所有 `P0/P0-partial` global contracts 至少出现在其中一组，P1/P2 不得因 related binding 进入七天 task。

## P1/P2 Exclusion

Global matrix中的P1/P2行只保存长期方向。七天task/selector不包括完整submission/退回治理、完整lineage/artifact lifecycle、通用Provider cache、回归阈值与盲测平台、RBAC/SSO、四眼审核、多模板、scanned正式支持、跨页全局布局最优、生产监控备份灾备或发布/回滚平台；D7-T2的current-four有限多距离collision-safe布局属于已选择的P0 `BAL-004`细化，不提升为P2全局优化。

## Traceability Self-Check

- 111 个 P0 ID 保持原编号，未删除。
- `P0-BAL-002` 的 selector 从循环依赖的 `requires_reviewed_result` 修正为 `requires_frozen_item_set`；最终 `reviewed_result` 仍由 `P0-RES-003` 在 balloon 校验后创建。
- 10 个纯实现选择不冒充 global contract；其余 101 行都有一个有效 global contract。
- 普通 selector 指向 backend/frontend test 或 `.agent/harness/scripts/`；7 个 ACC selector 使用 writing plan 定义、由同一 `run-p0.py` 进程内部 dispatch 的 `phase://`，不递归创建 child run。不存在 repository-root Harness path。
- 已完成行的 `passed` 只来自 sealed task/full-P0 results。D6-T3 与 D7-T1 已由各自 task receipts 投影；D7-T2 的 affected rows 先由 sealed full-P0 run `20260723T025857305843Z-609c61d3` 投影。D7-T3 fresh full-P0 run `20260723T042259807705Z-4e3e5f85` 随后在同一 executable/definition identity 下重新执行全部 111 个 selectors，结果为 111 passed、0 failed、0 blocked、0 not_run，formal receipt 为 passed。因为 111 个 `current_status` 已全部是 `passed`，本次只刷新 evidence provenance，不制造第二次 status cell 变更；run evidence 仍是 Owner。
- Product Design只拥有视觉翻译/QA，frontend仍是executor；Placement、Review/ReviewedResult和Export Owners未迁移，也没有新增第二route、第二plan或独立prototype。
- requirement/task/selector变化会改变 `contract_definition_hash`；D7-T3 final run 保持 `contract_definition_hash=42b4b24623173e6cf862c4f2626042810f5662a137c871d9150847b652007560`，只在同一 selected plan 边界内完成 final receipt/rollback policy closure，没有引入新的 contract、Owner、task、selector 或 P1/P2 scope。
