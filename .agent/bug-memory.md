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

## BUG-20260730-technical-requirements-dominates-review-workspace

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `frontend/src/components/workbench/InspectionWorkbench.tsx`、`TechnicalRequirementPanel` 与 `frontend/src/styles/workbench.css`
- Symptom: 技术要求以高占比独立滚动区插在状态汇总和检验项工作区之间，导致右栏形成三个竞争高度的滚动区；检验项列表和当前检验项详情被压缩，主要审核任务层级混乱
- Previously correct behavior: 技术要求应作为审核辅助信息保持可访问，但默认不占用主要审核工作区；检验项列表与详情双栏应获得主要可用高度
- Reproduction: `main@42bcbf7` 的已保存项目在窄右栏状态下稳定显示高约 220px 的技术要求列表，下面的检验项列表与详情只剩约一半视口高度
- Root cause: `c724db2` 将技术要求列表作为常驻展开内容插入审核栏，随后 `aa6a939` 又为
  `.inspection-pane--with-technical-requirements` 分配
  `minmax(120px, 0.75fr)` 的独立比例行；辅助信息因此始终与检验项主工作区竞争高度。
- Fix: 技术要求默认显示紧凑摘要，保留总数、待确认数和可访问的展开/收起按钮；父级网格
  改为 `auto auto minmax(0, 1fr) auto`，展开态限制为 `min(280px, 40vh)` 并在内部滚动，
  原有要求文本、状态、目标跳转和匹配命令不变。
- Regression check:
  `npm run test -- --run src/components/workbench/TechnicalRequirementPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx`
  返回 `32/32` passed；覆盖默认折叠、计数、待确认数、展开后内容和既有命令。
- Runtime proof: Chrome 在真实 `main` 项目、`1565x958` viewport 下测得右栏
  `500x710`；默认技术要求 `57px`、检验项主工作区 `546px`，展开技术要求 `280px` 后
  主工作区仍为 `323px`；7 个状态卡单排，列表行保留序号、原文/类型和完整状态，
  console error / warning 为 `0 / 0`。
- Change: `ui: prioritize inspection review workspace`

## BUG-20260730-confirmed-item-still-blocks-freeze

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `inspectionItemPresentation`、检验项待处理筛选、识别汇总与正式气泡门禁
- Symptom: 检验项列表和详情显示绿色“已确认”，待人工审核筛选为空，但“冻结检验项”仍禁用
- Previously correct behavior: 任何仍会阻止正式气泡的有效检验项都必须继续显示为待处理并可从待处理筛选定位；只有审核结论和气泡选择都完整后才显示“已确认”
- Reproduction: 当前真实项目中 coverage blocker 和 review-required 都为 0，但 3 个 active kept 项的 `balloon_required` 仍为 null；列表将它们显示为“已确认”，`FreezeReviewButton.hasResolvedReview()` 同时因 null 气泡选择返回 false
- Root cause: `inspectionItemStatus()` 只依据 `status="kept"` 投影“已确认”，`isReviewRequiredItem()` 也将 kept 项移出人工队列；两者没有复用正式气泡门禁所要求的 `balloon_required != null` 条件
- Fix: 新增共享 `isBalloonDecisionPending()` 投影，将审核结论已完成但
  `balloon_required` 仍为空的 active 项统一显示为“待选择气泡”、保留在待人工审核
  筛选，并补入汇总计数；未改变 Review API、schema 或冻结/生成/确认的既有顺序语义
- Regression check: TDD RED 先由 presentation、summary、table 三层测试复现；
  focused workbench 测试 `114/114` 通过，frontend 全量测试 `214/214` 通过；
  `npm run build` 成功（仅保留既有 bundle-size warning）
- Runtime proof: Chrome MCP 在当前真实项目
  `fb0572f9-4401-4d05-95ae-fde26b28d1d3` 验证汇总“待人工审核 3”，列表保留
  candidate 3、6、82 并显示“待选择气泡”；冻结/生成/确认仍按顺序禁用，
  无横向溢出，console error / warning 为 `0 / 0`
- Change: `fix: keep bubble decisions in review queue`
