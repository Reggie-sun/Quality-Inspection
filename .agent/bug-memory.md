# Project Bug Memory

本文件记录项目内用户报告的 bug 和已经确认的回归。调试前先阅读；重复问题更新原记录，不要重复创建。

## BUG-20260730-unclassified-vision-failure-category

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `CandidateAdvisor` failure classification 与 `InventoryPipeline` error projection
- Symptom: convergence 后 full backend suite 中，未分类的 Vision Provider `RuntimeError` 被记录为 `processing_defect`，旧 task-level contract 期望 `transient_provider_failure`。
- Previously correct behavior: 已分类 timeout/transport/schema 进入 localized partial；systemic contract corruption 必须 fail closed。未分类 Provider runtime failure 的归属需由当前 plan/code/test 证据确认。
- Reproduction: `backend/tests/integration/test_processing_entry_task.py::test_vision_failure_is_sanitized_without_result_layers` 在 merged HEAD `4fa73c2` 稳定失败于 `error.cause_category`。
- Root cause: `_review_result()` 将 Provider 调用与本地 response validation
  置于同一个 broad `except`，generic Provider `RuntimeError` 因而变成无类别
  `CandidateAdvisorFailure`，随后被 pipeline 当作 `processing_defect`。
- Fix: Provider 调用边界单独转换为 sanitised typed failure，保留已显式提供的
  timeout/transport/schema/unavailable 类别，generic RuntimeError 才默认
  `transport`；本地 response validation 保持无类别。`InventoryPipeline` 仅对
  共享 Provider category 集合中的显式类别投影
  `transient_provider_failure`，其余保持 `processing_defect`。
- Regression check: `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/integration/test_processing_entry_task.py::test_vision_failure_is_sanitized_without_result_layers -q`
- Runtime proof: 未运行；当前任务禁止 live Provider/browser/PDF/Harness。
- Change: `fix: preserve typed provider failure projection`; existing RED
  已由 `1 passed` GREEN 验证，未创建 Provider/browser/PDF/Harness runtime proof。

## BUG-20260730-requirement-relation-retirement

- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `backend/app/review/service.py` 的 `Exclude / Merge / Split` command path
- Symptom: 已确认的技术要求 relation 在目标 item 被停用后仍引用 inactive ID，可能在 freeze/export 前静默丢失。
- Previously correct behavior: requirement relation 必须只指向 active item；唯一 target 消失时必须重新进入人工确认。
- Reproduction: 新增 exclude/merge/split focused tests 分别失败于 relation 仍是 `matched_items`、仍指向 `i1`。
- Root cause: `_apply_command()` 只提交 item retirement/replacement，没有把 ID replacement map 同事务应用到 `technical_requirements`。
- Fix: 在 `Exclude / ResolveConfirmation(false) / Merge / Split` 的同一 command
  transaction 内同时应用 `matched_candidate_ids` 与 `generated_candidate_id` replacement
  map；无剩余 target 或 singular global relation 被拆成多个 target 时，把 requirement
  重开为 `unresolved` 并恢复 source coverage confirmation；其他 replacement 只重连
  active item 并重新投影 SIP suggestion。共享同一 observation 的 coverage gate 按全部
  requirements 重算；global merge 只接受 `global_requirement / balloon_required=false`
  source，并在所有 review command 完成后统一校验 active global item 与 global relation
  target，避免 `Edit / Add / SetBalloonRequired` 等旁路破坏无气泡合同。
- Regression check: `backend/tests/integration/test_review_operations.py`

## BUG-20260730-standalone-requirement-owner-replacement

- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `candidate_snapshot_from_inventory()` 与 `backend/app/candidates/technical_requirements.py`
- Symptom: title-block 外的 standalone executable requirement 在旧 classifier 被删除后不再保证生成无气泡技术要求项。
- Previously correct behavior: 同时含 inspection verb 和 verifiable criterion 的 standalone observation 会生成 `general_requirement`。
- Reproduction: 两个 snapshot focused cases 都得到 `technical_requirements == ()`，未进入新 Owner。
- Root cause: Owner replacement 迁移了 entry classification，却没有迁移旧入口的 standalone executable observation 准入与 entry 构造。
- Fix: 将 standalone executable predicate 收敛到 Technical Requirement Rule Owner，
  在编号块重建之后补充未消费 observation 的 standalone entry；已识别 subtype 走既有
  rule，其他可执行行保守生成 `standalone_check / ambiguous` 无气泡全局技术要求。
- Regression check: `backend/tests/e2e/test_offline_automatic_result.py`

## BUG-20260730-review-fields-relocked

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 至少 2 次
- Surface: `frontend/src/components/review/ReviewPanel.tsx`，结构化检验字段和编辑控件
- Symptom: 直径、深度、特征类型和通孔字段显示为灰色，看起来无法修改；明确的修改入口曾多次消失或再次成为强制门槛
- Previously correct behavior: 结构化检验字段可直接编辑，同时保留修改按钮；只有 freeze 或全局 disabled 状态才锁定编辑
- Reproduction: 已保存项目中的检验项 64 在点击修改操作前四个字段全部被锁定；修复前直接聚焦字段不会进入编辑态
- Root cause: commit `45e04d3` 恢复了由 `isEditingSelected` 控制的 `readonly`/`disabled` 条件，重新引入了早期直接编辑修复已经移除的强制编辑门槛
- Fix: commit `603702b` 让 text 和 select 字段仅在 panel 实际 disabled 时禁用，并让字段 focus 进入现有编辑态，不改变 save/cancel/freeze 的 Owner
- Regression check: `ReviewPanel.test.tsx` 中的测试 `直径尺寸字段支持修改按钮和直接点击两种编辑入口` 会在点击修改按钮前断言两个 input 不含 `readonly`、两个 select 不含 `disabled`，并覆盖按钮入口和直接 focus 入口
- Runtime proof: `npm test -- --run` 通过 205/205；`npm run build` 通过；在已保存检验项 64 上执行 Chrome smoke，确认字段为白色且可编辑、focus 后进入编辑态、取消后回滚，并且 page console 无 error/warn
- Change: `603702b`

## BUG-20260730-alembic-0008-revision-collision

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `GET /api/v1/projects/{project_id}/status`、`backend/app/projects/models.py`、`backend/alembic/versions/`
- Symptom: API hot reload 后能正常启动且 health 为 200，但 project status 持续返回 `500 project_status_failed`
- Previously correct behavior: 同一 project 在 reload 前返回 200；processing failure 应投影为 sanitized `200 failed`
- Reproduction: live DB 标记 `alembic_version=0008`，`automatic_results` 和 `review_working_copies` 已有 feature-only technical-requirements columns，但 `projects` 只有 `id/state/version`；当前 ORM 查询稳定触发 PostgreSQL `UndefinedColumn`
- Root cause: feature-only technical-requirements migration 与 symbol-routing migration 曾复用 revision `0008`；live DB 记录了前者，integrated graph 把 `0008` 解释为后者，Alembic 因相同 revision ID 跳过了 symbol-routing DDL
- Fix: 将 integrated `0010_technical_requirements.py` 收敛为 collided-state
  reconciliation Owner：用 Inspector 只补缺失的 canonical symbol-routing fields、
  constraint 和 technical columns；既有对象与 JSONB evidence 保持不变，downgrade
  仍只拥有 technical columns。
- Regression check: `backend/tests/integration/test_migration_reconciliation.py`
  在隔离 schema 中锁定 `0008 → 0009 → 0010` graph，顺序执行真实 `0009/0010`
  migration，验证既有 project backfill、technical sentinel 数据保全和 `0010` 幂等性。
- Runtime proof: live DB 从 `0008` 升至 `0010`；同一 project status 返回 sanitized
  HTTP 200、`phase=failed`、`vision_provider_call_failed`；`/api/v1/health` 返回 200。
- Change: focused Alembic revision-collision recovery commit
