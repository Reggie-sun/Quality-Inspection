# Project Bug Memory

本文件记录项目内用户报告的 bug 和已经确认的回归。调试前先阅读；重复问题更新原记录，不要重复创建。

## BUG-20260731-multi-source-balloon-geometry-selection

- Status: 已解决
- First reported: 2026-07-31
- Last reported: 2026-07-31
- Recurrence: 1
- Surface: `backend/app/balloons/service.py` 的 frozen item source geometry 选择与正式文件准备链
- Symptom: SIP 已显示 `115 / 0`、检验项已冻结，但“生成正式文件”持续显示“尚未审核”并保持禁用
- Previously correct behavior: 已冻结 item 只要任一已关联 source 具有真实 page geometry，就应能生成正式气泡并继续 reviewed result / formal export
- Reproduction: live workbench 为 `items_frozen_at != null`、`numbering_stale=true`、`balloons=0`、`balloon_blockers=["missing_required_balloon"]`；API 日志显示 freeze HTTP `200` 后 `/balloons/generate` HTTP `409`。在同一 API container 内将 commit stubbed 为 no-op 并最终 rollback 的诊断调用精确返回 `BalloonSourceUnavailable: item 2faf49681bddeaab83b7fce8 source 7e1b1feed2af12be9031aaa1 has no page geometry`，且确认未生成任何 balloon
- Root cause: item 同时关联 visual placeholder source `7e1b...` 与有 page geometry 的 text source `f0b1...`；`BalloonService._geometry_for_item()` 只检查 `source_location_ids[0]`，没有尝试同一 item 的后续 canonical source，因此一个不可定位的派生来源阻断全部 formal balloon materialization
- Fix: 唯一 Owner 保持 `BalloonService._geometry_for_item()`；普通 source 按既有
  `source_location_ids` 顺序选择第一个存在于 inventory 的 geometry，遇到无 geometry
  的派生占位来源继续检查后项；`manual:` source 的既有 page/coordinates fallback、
  无 source 和全无 geometry 的 fail-closed 合同保持不变。
- Regression check: 新增真实 `generate_formal` 集成回归，使用
  `["derived-without-geometry", "s1"]` 证明旧实现 RED 于首项
  `BalloonSourceUnavailable`，修复后 GREEN 并持久化 `s1` 的 source identity 与 bbox；
  balloon/freeze/export focused gate `31 passed`，隔离数据库全量 backend
  `1507 passed, 2 warnings`。
- Runtime proof: API bind-mounted source hot reload 后，对原项目重新调用 balloon generate
  返回 `115` 个正式编号气泡；自动布局唯一的第 54 号气泡先为
  `manual_required/source_text_overlap`，以 canonical placement evaluator 只读枚举得到
  合法位置后通过既有 move command 调整为 `placed`，最终 `balloon_blockers=[]`。
  运行中旧版工作台随后完成 review confirm 与 atomic export，两个 POST 均为 HTTP
  `200`，项目状态为 `reviewed`，PDF、SIP Excel、manifest 三项均
  `downloadable=true`；CDP 页面检查三条下载链接各 1 个、console error 与非预期
  request failure 均为 0。Chrome MCP 返回环境级 `Transport closed`，未宣称其通过。
- Change: `fix(balloons): resolve later source geometry`
- Selected lane: `Standard`
- Selected plan: `BUG-20260731-multi-source-balloon-geometry-selection` ad hoc bug task；不切换已完成的 SIP auto-mapping implementation plan
- Selection evidence: 单一 backend owner 的错误 source choice 会阻断冻结后的 balloon/review/export 链；需要 integration regression、live API recovery 与独立 reviewer，但不改变稳定 schema、runtime config 或 formal artifact identity
- Validation action: `completed`
- Problem boundary: frozen active item 的多个既有 source identity 中选择可用 page geometry
- Single owner: `BalloonService._geometry_for_item()`
- Old path action: replace `source_location_ids[0]` only；preserve manual-source fallback、freeze、numbering、reviewed result、export fail-closed
- Focused verification: multi-source first-missing/second-valid integration RED/GREEN，再运行 balloon/review/export focused gate
- Writer ownership and order: 父 agent 唯一 writer；只读 explorer 仅核对现有 fixtures、调用链和风险
- Independent review: `accept`；无 blocking defect 或 material risk。可选补充
  all-sources-missing 与 manual fallback 的定向测试，但现有分支静态保持 fail closed，
  不阻断本次修复。
- Next verification: 已关闭；仅在新的 multi-source geometry 或正式导出回归时重开

## BUG-20260731-sip-terminal-action-no-feedback

- Status: 已解决
- First reported: 2026-07-31
- Last reported: 2026-07-31
- Recurrence: 1
- Surface: `frontend/src/components/workbench/SipInformationPanel.tsx` 的批量生成动作与 SIP 完成态
- Symptom: SIP 已显示“已生成 115，异常 0”时，蓝色“生成并检查 SIP 表格”仍呈现为主要可点击动作；点击后用户看不到任何状态变化，并感觉它与左侧“生成正式文件”重复
- Previously correct behavior: 批量生成动作应明确反馈执行结果；SIP 达到异常 0 后应呈现可理解的完成终态，并与正式 PDF/Excel/校验清单导出动作清楚区分
- Reproduction: 用户截图显示当前检验项区域为“SIP 表格：已生成 115，异常 0”，默认检验角色已填写，蓝色“生成并检查 SIP 表格”仍可点击；左侧“生成正式文件”同时可见但因“尚未审核”保持禁用
- Root cause: `SipInformationPanel` 只用 ready/exception count 渲染进度并隐藏
  “处理下一条异常”，没有把 `activeCount > 0 && exceptionCount == 0` 投影为终态；
  批量按钮因此仍无条件把 `generate_sip_table` 转发给 `submitCommand`。重复命令实际
  写入新 version，但返回后的计数仍为 `115 / 0`，且按钮自身没有 local result
  feedback，用户只能在远处看到全局保存状态，所以视觉上表现为“点击没反应”。
- Fix: 当 `readyItemCount + exceptionItemCount > 0` 且异常为 `0` 时，将默认角色输入
  和批量生成按钮替换为绿色 `SIP 表格已完成` 终态，并明确说明正式文件需在审核和
  冻结完成后从左侧统一生成；空集合和仍有异常的状态继续保留原生成入口。未改变
  `submitCommand`、backend mapping、freeze 或 `ExportPanel` 合同。
- Regression check: TDD RED
  `没有 SIP 异常时显示完成终态并移除重复生成动作` 先稳定失败于旧生成按钮仍存在；
  reviewer 建议的 `0 / 0` 空态用例通过 mutation check，能拦截把完成条件误简化为
  `exceptionItemCount === 0` 的回归。focused suite 返回 `14/14`，frontend 全量返回
  `269/269`，`npm run build` 与 `npm run api:check` 均通过。
- Runtime proof: Chrome MCP 返回 `Transport closed`；按已批准 fallback 使用
  Playwright + system Chrome 打开当前源码与真实 project workbench，只拦截
  review-lock acquisition 以避免写入真实 lock，其他 workbench/PDF 请求仍走 live
  API。验证 `SIP 表格已完成` 与下一步各 `1` 个，旧生成按钮和默认角色输入均为
  `0`，进度仍是 `115 / 0`，console error 与 HTTP `>=400` 均为 `0`。
- Change: `fix(frontend): show SIP terminal completion state`
- Selected lane: `Lite`
- Selected plan: `BUG-20260731-sip-terminal-action-no-feedback` ad hoc bug task；不切换已完成的 SIP auto-mapping implementation plan
- Selection evidence: 当前证据指向单个 workbench frontend 终态投影与动作反馈；不改变 Review API、SIP mapping、freeze 或正式导出合同
- Validation action: `completed`
- Writer ownership and order: 父 agent 唯一 writer；只读 debugger 只提供调用链证据
- Independent review: 最终 verdict `accept`，无 blocker 或 concern。
- Next verification: 已关闭；仅在新 feedback 或 runtime regression 时重开。

## BUG-20260730-technical-requirement-confirm-action-missing

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 2
- Surface: `frontend/src/components/workbench/TechnicalRequirementPanel.tsx` 的待确认技术要求操作区
- Symptom: 技术要求摘要显示“待确认 1”，展开后的对应要求也显示“待确认”，但界面没有可见的确认按钮，用户无法明确完成该要求的确认操作
- Previously correct behavior: 待确认技术要求必须提供可见、可理解的确认入口，并继续由既有 review command Owner 提交状态变更
- Reproduction: 用户截图中技术要求总数为 5、待确认数为 1；展开后第 4 条要求显示“待确认”，只出现“调整匹配”和匹配检验项，没有确认按钮
- Root cause: `set_technical_requirement_match` 本身就是单条技术要求的确认
  Owner，但 `TechnicalRequirementPanel` 只把它投影为“匹配此检验项”，同时仅按
  `match_outcome="unresolved"` 统计待确认；因此 unresolved 要求没有可识别的
  “确认”动作，自动已有 `matched_items / global_scope` 建议且仍
  `review_required=true` 的要求也没有确认当前建议的入口。
- Fix: 待确认计数改用 canonical `review_required`；unresolved 候选动作明确为
  “确认匹配此检验项”；已有 matched 建议可一次性原样确认全部 target，global
  建议可明确确认；所有动作继续复用唯一 `set_technical_requirement_match`
  command seam。确认主按钮只在 enabled 时使用蓝色强调，disabled 状态回到统一灰态。
- Regression check: TDD RED 先稳定失败于缺少“确认匹配此检验项”和自动建议未计入
  待确认；`npm run test -- --run src/components/workbench/TechnicalRequirementPanel.test.tsx`
  返回 `3/3`，`npm run test -- --run src/components/workbench/InspectionWorkbench.test.tsx`
  返回 `32/32`，frontend 全量 `npm run test -- --run` 返回 `226/226`，
  `npm run build` 成功。
- Runtime proof: Chrome MCP 连续返回 `Transport closed`；改用同一
  `127.0.0.1:9222` Chrome 的 Playwright CDP 连接，在真实项目
  `fb0572f9-4401-4d05-95ae-fde26b28d1d3` 验证第 4 条待确认要求已显示
  “确认匹配此检验项”按钮且可用，页面 console error / warning 为 `0 / 0`；
  DOM-only 状态检查确认 enabled 为蓝色、disabled 为统一灰色且
  `cursor=not-allowed`。未点击真实确认命令，避免替用户选择并持久化技术要求关系。
- Change: `fix(frontend): make requirement confirmation explicit`
- Selected lane: `Lite`
- Selected plan: `BUG-20260730-technical-requirement-confirm-action-missing` ad hoc bug task；不切换七天 P0 implementation plan
- Selection evidence: 单个 workbench 前端交互面，当前未发现稳定 API/schema、runtime config 或跨模块 data-integrity boundary 变化
- Validation action: `continue`；先验证 root-cause hypothesis，再执行 TDD RED/GREEN、focused test、build 与 Chrome MCP smoke
- Writer ownership and order: 父 agent 唯一 writer；只读 explorer 不修改任何文件
- Next verification: 已完成 focused/full tests、build、independent review 与无数据写入的 live browser smoke

### Recurrence 2

- Symptom: 明确确认按钮已经出现，但用户仍无法理解应先选择什么、点击后会影响哪些
  检验项，以及确认完成后下一步是什么；unresolved 行仍把大量候选投影成即时提交按钮。
- Root cause hypothesis: 当前 frontend 把业务决策、影响预览和持久化提交压缩为同一次
  button click；同时 exact screenshot text `未注公差按GB/T1804-m级执行` 未命中
  Rule Owner，因此没有可消费的系统建议。
- Approved fix direction: `A 内联逐条确认`；先形成本地互斥 draft，再预览影响并显式
  `确认并处理下一条`；终态为只读 `已确认` 摘要，全部完成后进入检验项/SIP 审核。
  Rule Owner 只对包含明确 `GB/T 1804`、等级和执行语义的 shorthand 扩展识别。
- Selected lane: `Standard` amendment to the existing approved technical-requirement plan。
- Resolution: Rule Owner 已识别明确 `GB/T 1804-m级执行` shorthand，同时保持缺少
  `执行`、非法等级和其他标准 fail closed；frontend 已替换为单 active editor 的
  draft → impact → confirm-next → terminal 流，并把 draft 纳入工作台现有
  dirty/save/prepare/finalize gate。多草稿返回时按 technical requirement →
  metadata → remaining drafts 顺序保存。
- Regression check: backend focused/offline slice `93 passed`；frontend focused
  `44 passed`、full `257 passed`；production build PASS（仅既有 large-chunk
  warning）；Playwright E2E spec collection PASS。
- Runtime proof: 用户批准的 Playwright CDP fallback 使用 intercepted API 验证
  local draft、影响预览、dirty return gate、existing command payload、terminal、
  modify 与 inspection handoff；console error/warning、HTTP `>=400` 和 unexpected
  request failure 均为 `0`，真实项目写入为 `0`。
- Independent review: rollout `019fb21e-b59c-7741-97ac-229d960d910a`
  最终 verdict `accept`，无剩余 blocker。
- Change: `feat: add sequential technical requirement confirmation`
- Next verification: 已关闭；仅在新 feedback 或 runtime regression 时重开。

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

## BUG-20260730-quantity-hidden-from-review

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: 工程图数量前缀解析结果、检验项审核编辑与 Review command
- Symptom: `3 × M10 通`、`6 × ⌀12 通` 等候选项在后端仍保留
  `quantity`，但审核详情“解析结果”不展示数量，也无法人工修正
- Previously correct behavior: typed inspection item 的解析结果首项展示可编辑数量；
  保存时作为正整数 `quantity` 随同既有 `edit` command 提交
- Reproduction: `ReviewItem.quantity=4` 时，当前
  `ReviewPanel.test.tsx` 反向断言“审核详情不展示数量字段”
- Root cause: commit `723fc45` 只从 `ReviewPanel` 删除 `QUANTITY_FIELD`、
  integer 解析和 number input；Candidate schema、parser、working copy 与前端
  `ReviewItem` 类型仍保留既有 `quantity` owner
- Fix: 在 `ReviewPanel` 恢复既有 `quantity` 核心字段、nullable 正整数解析与
  number input，并继续通过唯一 `edit` command 保存；未改 Candidate schema、
  review persistence、分组合并语义或 SIP 导出模板
- Regression check: TDD RED 先由数量显示和保存用例复现；`ReviewPanel`
  `32/32` 通过，覆盖正整数、清空为 `null`、`0` 与 `1.5` 不提交；
  frontend 全量 `221/221` 通过，`npm run build` 成功；quantity grouping
  `2/2` 与 review typed edit / merge `2/2` 通过
- Runtime proof: Chrome MCP 在真实项目
  `fb0572f9-4401-4d05-95ae-fde26b28d1d3` 选中
  `3 x M10 通`，解析结果显示数量 `3`、螺纹规格 `M10`、通孔“是”，
  quantity input 为 `min=1 / step=1`；页面无横向溢出，
  console error / warning 为 `0 / 0`
- Change: `fix(frontend): restore inspection quantity field`
