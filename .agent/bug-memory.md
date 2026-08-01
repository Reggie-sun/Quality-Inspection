# Project Bug Memory

本文件记录项目内用户报告的 bug 和已经确认的回归。调试前先阅读；重复问题更新原记录，不要重复创建。

## BUG-20260801-source-balloon-action-affordance

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 2
- Surface: `frontend/src/components/workbench/SourceReviewPanel.tsx` 的待判定来源处理动作、内联类型校验与 `frontend/src/styles/workbench.css`
- Symptom: 首次修复后按钮已区分“添加并生成气泡”和“仅添加检验项”，但未选择检验类型时两种按钮仍使用原生禁用态置灰；用户无法点击动作获得下一步提示
- Previously correct behavior: 待判定来源详情应明确区分“添加并生成气泡”和“仅添加检验项”，同时继续要求用户显式选择检验类型，不绕过 review、freeze 或正式编号流程
- Reproduction: 2026-08-01 第二次用户截图中，原始标注 `1` 的“需要气泡”勾选和未勾选状态分别显示正确动态文案，但主按钮都呈灰色；当前 `SourceReviewPanel` 在 `selectedSourceDraft.itemType === ""` 时直接设置 `disabled`
- Root cause: 首次原因是主动作使用静态文案，已由 `ec0f5c9` 修复；第二次原因是按钮仍把 `itemType === ""` 纳入原生 `disabled` 条件，导致正确的动态文案不可交互，也无法在点击时告诉用户缺少哪个必填项
- Fix: 首次修复保留动态“添加并生成气泡 / 仅添加检验项”；第二次修复只移除缺少 `itemType` 造成的原生禁用，点击时阻止 command、显示红色“请选择检验类型”并聚焦 select；原始标注为空、页码缺失或整体只读时继续真正禁用
- Regression check: 第二次 TDD RED 精确失败于按钮仍有 `disabled`；`npm test -- --run src/components/workbench/InspectionItemTable.test.tsx src/components/workbench/InspectionWorkbench.test.tsx` 为 `64 passed`，覆盖可点击、零 command、alert、`aria-invalid`、focus 和选型后正常 payload；完整 frontend suite 为 `273 passed`，production build 通过
- Runtime proof: localhost 真实 pending source 默认 `itemType=""` 时，“添加并生成气泡”为蓝色且可点击；点击后 select 获得 focus、显示红色提示，network 为 0 requests；取消勾选后“仅添加检验项”同样可点击，选择 `general_requirement` 后提示消失；console error 为 0，证据截图 `/tmp/qi-source-balloon-action-enabled.png`
- Change: `ec0f5c9 fix(ui): expose source balloon action`；第二次 follow-up 为 `fix(ui): keep source actions interactive`
- Selected lane: `Standard`，只改变一个现有 frontend form 的可见动作语义，但需要真实 browser smoke 证明用户路径
- Selected plan: 本 bug-memory entry 作为 ad hoc task contract；不切换或扩展当前 P0 implementation plan
- Problem boundary: 只让现有来源纳入动作明确表达气泡结果；不新增 endpoint、command、默认检验类型或直接正式气泡旁路
- Single owner: `SourceReviewPanel` 继续拥有 source draft 和 `promote_source` producer
- Old path action: 退役不表达 `balloonRequired` 结果的静态“添加为检验项”主按钮文案
- Unchanged contract: `promote_source` 继续要求显式 `item_type` 并携带 `balloon_required`；正式气泡仍由现有 review/freeze/numbering 流程生成
- Allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/SourceReviewPanel.tsx`、`frontend/src/components/workbench/InspectionItemTable.test.tsx`、`frontend/src/styles/workbench.css`
- Amendment: 实现后 focused suite 证明 `InspectionWorkbench.test.tsx` 也是旧静态 accessible name 的直接 consumer；只更新其现有 source-promote 查询，不改变 workbench behavior 或扩大 production scope
- Writer ownership and order: 父 agent 唯一 writer；保留并发出现的 `docs/superpowers/specs/2026-07-23-public-qa-development-deployment-design.md` 与 `docs/superpowers/plans/2026-08-01-lan-frontend-binding.md`
- Independent review: 首次修复最终 verdict 为 `accept`；第二次 recurrence focused review 同样为 `accept`，确认 click interception 不发送 command、双层 `itemType` gate、错误状态清理、native disabled 边界、draft payload 和 CSS scope 均无 findings
- Current amendment: `Standard` lane 继续；按钮不再因缺少 `itemType` 原生禁用，点击时必须阻止提交、显示“请选择检验类型”并聚焦对应 select；不默认或猜测类型，不改变 `promote_source`、draft save、freeze 或 numbering contract
- Validation action: `continue`；同一目标、Owner 和 command seam 不变，只修首次改动遗留的不可交互状态
- Next verification: 已完成；仅在按钮再次因缺少类型变灰，或点击缺少类型时发送 command / 不显示提示时重开

## BUG-20260801-source-disposition-stale-tests

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `backend/tests/integration/test_symbol_recognition_pipeline.py` 的 source-only visual/revision working-copy assertions
- Symptom: 隔离 PostgreSQL 上的完整 `make test-backend` 仅剩 4 个失败；测试期待 working coverage 保持 `requires_confirmation=true` 并允许显式 `promote_source` / `ignore_source`，实际 bootstrap 已投影为 `non_inspection`、`requires_confirmation=false`
- Previously correct behavior: raw automatic coverage 保留 advisor evidence；working-copy bootstrap 按现行 automatic-source-default contract 自动收口非 technical-requirement source-only pending，并保留 legacy/manual correction seam
- Reproduction: fresh full backend suite 为 `1599 passed / 4 failed`；失败仅为 `test_visual_no_detection_remains_actionable_source_review[promote|ignore]` 与 `test_revision_marker_stays_noninspection_until_explicit_promote_source[promote|ignore]`
- Root cause: 这 4 个 parametrized case 早于 approved automatic-source-default amendment；它们仍把新 working copy 的 source-only entry 当作 `requires_confirmation=true` 的 legacy pending target，和 `CAND-005` / `CAND-006` / `REV-004` 现行 raw/working 分层契约冲突。production `ReviewService._review_coverage()` 行为正确
- Fix: 仅更新 `test_symbol_recognition_pipeline.py` 的 4 个旧 case：继续断言 immutable raw advisor evidence，改为锁定 working-copy exact system-default provenance，并证明已收口 entry 的 `promote_source` / `ignore_source` 会原子拒绝且不改变 version、items 或 coverage；production code 未修改
- Regression check: `test_visual_no_detection_uses_system_default_source_disposition[promote|ignore]`、`test_revision_marker_uses_system_default_source_disposition[promote|ignore]`；完整 `make test-backend` 为 `1607 passed`
- Runtime proof: fresh `make test-backend` 在隔离且已迁移的 PostgreSQL 上 `1607 passed / 4 warnings`，退出后 test container/network 已清理；tests-only contract convergence 无 API/UI/runtime behavior change，`auto-feature-smoke-test` 的额外 API/Chrome smoke 不适用
- Change: `test: align source disposition regression expectations`
- Selected lane: `Heavy`，沿用 `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md`
- Problem boundary: 判定并修复 4 个 source-disposition residual；不改变 raw evidence、technical requirement exemption、public correction command、数据库 runtime entry 或 frontend
- Single owner: `ReviewService._review_coverage()` 继续拥有 production bootstrap projection；本修复只更新 integration test contract
- Writer ownership and order: 父 agent 唯一 writer；只读 debugger 已确认 stale-test 根因且未修改文件
- Independent review: `accept`；无 blocking issue、non-blocking concern 或建议项；确认 raw/working separation、exact provenance、settled command rejection 与 legacy pending command coverage 均完整
- Next verification: 已完成；focused 4 cases、完整 backend suite、diff check 与独立 review 均通过

## BUG-20260801-test-backend-compose-dns

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `Makefile:test-backend`、backend integration/e2e database setup
- Symptom: `make test-backend` 在 `1273 passed` 之外产生 `53 failed / 274 errors`，绝大多数为宿主机无法解析数据库 host `postgres`
- Previously correct behavior: 单一命令应在隔离、已迁移的 PostgreSQL 上执行完整 backend suite，不能依赖 Compose-only DNS 或开发数据库
- Reproduction: 当前 `make test-backend` 从宿主机启动 pytest；`getaddrinfo('postgres', 5432)` 失败，而将同一连接重定向到当前 Compose PostgreSQL 的 host-reachable IP 后只读 `SELECT 1` 成功
- Root cause: `test-backend` 没有数据库 lifecycle，宿主机 pytest 直接读取 `.env` 中仅在 Compose 网络可解析的 `postgres`；production Compose PostgreSQL 也没有 host port，且其持久化卷不允许作为 migration tests 的隔离目标
- Fix: `test-backend` 每次启动唯一 Compose project 的 PostgreSQL 17，使用 loopback 动态端口和 tmpfs；healthcheck 后对空库执行 Alembic upgrade，再运行原 backend suite。EXIT/INT/TERM 清理只命中该 test project，并保留 migration/pytest/signal 的原始非零状态
- Regression check: topology 初始 RED 为 `2 failed / 1 passed`；实现及 failure-status follow-up GREEN 为 `4 passed`；fake lifecycle 证明 cleanup failure 不再把 pytest `Error 7` 覆盖成 `Error 1`
- Runtime proof: fresh `make test-backend` 成功创建、迁移和连接隔离 PostgreSQL，不再出现 `postgres` DNS/connection error；完整收集为 `1599 passed / 4 failed / 4 warnings`，4 个 residual 均是 `test_symbol_recognition_pipeline.py` 中 source disposition 语义偏差，不属于本 test runtime entry 修复。pytest 失败后 test container/network/volume 无残留
- Change: `fix: isolate backend test database`
- Selected lane: `Heavy`
- Selected plan: `docs/superpowers/plans/2026-08-01-test-backend-isolated-postgres.md`
- Validation action: `completed` for test runtime entry；backend full-suite verdict 仍为 `failed` due to 4 bounded semantic residuals
- Problem boundary: 仅修 test runtime entry；production/development/QA database config 与测试语义保持不变
- Single owner: `Makefile:test-backend`
- Writer ownership and order: 父 agent 唯一 writer；只读 explorer 已完成且未修改文件
- Independent review: `accept with concerns`；无 blocking issue，concern 仅为不得将 4 个既有 semantic failures 报告为 full backend GREEN
- Next verification: 另起 bounded source-disposition task 判定 4 个 residual 是 stale expectation 还是 behavior regression；不在本任务顺手修改

## BUG-20260801-dimension-export-type-blank

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: v3 `机械图纸尺寸质量检测表` 的 `类型` 列、`ReviewedResult.items -> ExportService._excel_rows()` 投影
- Symptom: 新生成的 v3 Excel 已显示编号、页码、基本尺寸和公差，但所有可见明细行的 `类型` 列为空
- Previously correct behavior: `类型` 应按 reviewed item 的 `item_type/coarse_type` 显示固定中文 label，例如线性、直径、半径、粗糙度
- Reproduction: 用户提供的正式 v3 导出截图中，表头和尺寸/公差列已升级，编号 26、31、34、35、36、37 等行的 C 列视觉为空；本机实际下载文件 `/home/reggie/下载/source-sip (5).xlsx` 与 export artifact SHA-256 均为 `44f9b46766509645c1d5da56e928dd10f7f474ea210c2467bfebf40cf8837347`，openpyxl 读取这些行分别得到 `粗糙度/线性/直径` 等非空值
- Root cause: WPS 对 `C6:C517` 类型条件格式只呈现白色字体、没有呈现对应 solid background fill，导致白字落在白底上；`ReviewedResult.items` 保有 `item_type/coarse_type`，`ExportService._excel_rows()` 和实际 workbook C 列均已正确写值，因此不是 recognition 或 field mapping 丢失
- Fix: renderer 写入类型 label 时同步固化 solid fill 和白色粗体，并保留 conditional formatting；renderer identity 升级为 `balloon-pdf/1+xlsx-type-style/1`，使同一 reviewed result 生成新的 immutable artifact
- Regression check: focused workbook/contract/atomicity tests 与 broader export gate 共 `90 passed`，Ruff 和 `git diff --check` 通过；新增 current-processing/historical-renderer regression 防止并发窗口返回旧 artifact
- Runtime proof: frontend 对同一 project 生成 export `2cb55361-4768-4bec-aaaf-51c873b6521b`，template/mapping `3/3`、renderer `balloon-pdf/1+xlsx-type-style/1`；实际 workbook C 列 label 非空且有静态 fill/font，WPS GUI 已正确显示线性、直径、螺纹及对应颜色；历史 export `57a46870-5c5e-4e30-8603-d72a6a3a8bb1` 仍可下载（HTTP `200`）
- Change: `5e5096d fix(exports): materialize WPS type styles`，已进入 `main`
- Selected lane: `Heavy`
- Selected plan: `docs/superpowers/plans/2026-08-01-wps-type-cell-compatibility.md`；parent plan `docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md` 保持 completed
- Selection evidence: 稳定 v3 row contract 不变；WPS 对 differential fill 的兼容差异需要 static base style 和受控 renderer identity revision，并需要 focused export integration 与同一 runtime artifact proof
- Validation action: `close`；active path、concurrency failure path、frontend generation、WPS 视觉和历史 artifact immutability 均已有当前证据
- Problem boundary: 只修 immutable reviewed item 到 v3 `type_label` 的投影；不修改 recognition pipeline、review command、schema、template layout 或历史 artifact
- Single owner: `backend/app/exports/excel.py` 的 registered detail-cell rendering；artifact rematerialization identity 仍由 `ExportService._logical_task_key()` 和 manifest `renderer_version` 约束
- Writer ownership and order: 父 agent 唯一 writer；现有子任务均已结束，无并发 file ownership
- Next verification: 无；用户可直接在前端下载最新 SIP Excel，无需重新上传图纸

## BUG-20260801-source-editor-wrong-pane

- Status: 阻塞
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `InspectionItemTable`、`InspectionWorkbench` 右侧 detail pane 与待判来源编辑表单
- Symptom: 选中黄色待判来源后，来源处理表单展开在狭窄左侧列表中，字段和按钮被压成竖排；普通蓝色检验项的编辑表单则正确显示在右侧详情区
- Previously correct behavior: 左侧只显示可选择的检验项/来源行；无论选择普通检验项还是待判来源，对应处理表单都应显示在右侧详情区
- Reproduction: 用户截图中左侧约 135px 宽度内显示“原始标注 / 检验类型 / 范围 / 需要气泡 / 忽略 / 添加为检验项”完整表单，而对照蓝色检验项在右侧 detail pane 正常显示
- Root cause: `InspectionItemTable` 同时拥有 source draft、`promote_source` / `ignore_source` command 与完整 `.source-review-fields` 渲染，因此表单被固定组合在左侧 `.inspection-review-workspace__list`；来源处理后 coverage 移除该 source 时，旧 `selectedSourceId` 还会继续占用右侧详情 Owner
- Fix: 提取独立 `SourceReviewPanel`，由 `InspectionWorkbench` 在右侧 `.inspection-review-workspace__detail` 渲染；table 只保留 row/分页/选择；当所选 source 不再属于 `pendingSources` 时清除 `selectedSourceId` 并恢复普通 `ReviewPanel`
- Regression check: `InspectionWorkbench.test.tsx` 先证实旧实现在左侧仍存在 source editor，修复后验证左侧无表单、右侧有表单；coverage 刷新移除 source 后 editor 关闭、ReviewPanel 恢复、SIP source mode 清除、PDF source overlay 取消选中。focused frontend suites `68/68` 通过，production build 通过
- Runtime proof: Chrome MCP 两次 `list_pages` 均返回 `Transport closed`，无法取得同状态截图、console 与横向溢出证据；`design-qa.md` 保持 `blocked`
- Change: `InspectionItemTable.tsx` 退役 inline source editor；新增 `SourceReviewPanel.tsx`；`InspectionWorkbench.tsx` 迁移右侧 Owner 并协调 stale selection；相关 component tests 更新
- Selected lane: `Standard`
- Selected plan: `docs/superpowers/plans/2026-07-31-automatic-source-disposition.md` 的 `2026-08-01 Source Editor Right-Pane Amendment`
- Validation action: code/test/reviewer 已完成；Chrome MCP visual closeout 阻塞

## BUG-20260801-numeric-source-visibility

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `InspectionWorkbench` 的 source-only coverage 可见列表投影、`InspectionItemTable` 黄色“待判来源”行与 `TechnicalRequirementPanel`
- Symptom: 新图纸的黄色列表混入“标记 / 其余 / A / 贯穿 / E”等纯文字来源，挤占紧凑列表；用户只需要保留 `1518 / 18 29 18 / 4x / 125 X...` 等含数字来源
- Previously correct behavior: 黄色“待判来源”队列只承载仍值得逐项检查的数字型工程标注；纯文字 technical requirement 仍应在“技术要求”Owner 面板处理，不重复出现在黄色列表
- Root cause: `InspectionWorkbench.pendingSources` 将所有 `requires_confirmation=true && candidate_id=null` 的 coverage 原样投影为黄色行，没有区分含数字工程标注与已由 `TechnicalRequirementPanel` 承接的纯文字 requirement source
- Fix: 在唯一前端投影 Owner 取得并 trim `rawText` 后，以 `/\d/` 仅保留含 ASCII 数字的黄色来源；`selectSource` 同时拒绝不可见 source，避免 PDF overlay 产生 ghost selection；不修改 backend coverage、`manual_review_count`、technical requirement decision、freeze、编号、气泡、SIP 或 public command/API
- Regression check: TDD 用 `125 X 2` 与 `贯穿` 复现旧实现 RED，并证明纯文字 PDF overlay 原本会进入 ghost selection；修复后断言数字来源行可见、纯文字来源行不可见且不可选、“技术要求匹配”仍显示“贯穿”；`InspectionWorkbench`、`InspectionItemTable`、`RecognitionSummary` 共 `68/68` 通过，frontend build 通过
- Runtime proof: Chrome MCP 返回 `Transport closed`，且用户截图项目不属于当前可达 backend/runtime；本次不以其他项目冒充实机证据，待同一 runtime 可达后补验
- Change: `frontend/src/components/workbench/InspectionWorkbench.tsx` 的单点可见性 filter、对应组件 regression、plan amendment 与本 bug-memory 记录
- Selected lane: `Standard`
- Problem boundary: 只收窄黄色来源队列的可见内容；隐藏不等于 disposition 或删除，后台 unresolved truth 与正式流程门禁保持原样
- Single owner: `frontend/src/components/workbench/InspectionWorkbench.tsx` 的 `pendingSources`
- Rollback: 回退 `/\d/` filter；第一项验证为“黄色待判来源只展示含数字的原始来源”focused test
- Writer ownership and order: 父 agent 唯一 writer；无并发 writer
- Next verification: 当前自动化已关闭；同一截图 runtime 恢复后补 Chrome smoke，或在纯文字重新出现、含数字来源消失时重开

## BUG-20260731-compact-source-batch-overflow

- Status: 已解决
- First reported: 2026-07-31
- Last reported: 2026-07-31
- Recurrence: 1
- Surface: `InspectionItemTable` compact mode、`.source-batch-bar` 与 `.inspection-review-workspace__list`
- Symptom: 新图纸存在待确认来源时，紧凑检验项列表被撑宽，出现横向滚动条并截断“状态”列；无待确认来源的已审核图纸保持正常三列布局
- Previously correct behavior: 无论是否存在待确认来源，紧凑列表都应在当前左栏宽度内完整显示“序号 / 检验项 / 状态”，不产生横向滚动
- Reproduction: live project `b3d4d9ba-4bcb-475b-9fa2-c559a201c7f3` 在 `1440x1000` viewport 下，`.inspection-table-section` 为 `clientWidth=135 / scrollWidth=180`；对照项目 `fb0572f9-4401-4d05-95ae-fde26b28d1d3` 为 `135 / 135`
- Root cause: compact 列表的 `.source-batch-bar` 同时将计数与动作按钮设为 `flex: 0 0 auto` 和 `white-space: nowrap`，其最小内容宽度约 `180px`，超过列表可用宽度并触发外层 `overflow:auto`
- Fix: 为 `.source-batch-bar` 增加 `flex-wrap: wrap`；宽度足够时保持单行，实际 `135px` 紧凑宽度下将动作按钮换到下一行，保留待确认来源事实与批量确认入口，不改变 item 状态、筛选、编号或 review command
- Regression check: 新增 `135px` 紧凑宽度 Playwright 回归；修复前因 `main.scrollWidth > main.clientWidth` RED，修复后 `frontend/e2e/inspection-list-compact-style.spec.ts` 为 `3 passed`；`InspectionItemTable.test.tsx` 为 `26 passed`；frontend production build 通过，仅保留既有 Vite chunk-size warning
- Runtime proof: live project `b3d4d9ba-4bcb-475b-9fa2-c559a201c7f3` 在 `1440x1000` viewport 下，列表、table section、header 分别为 `clientWidth/scrollWidth=155/155`、`135/135`、`133/133`；三列完整显示且无横向滚动。展开确认态的 list、source bar、actions 分别为 `155/155`、`139/139`、`125/125`，取消后未提交 mutation；真实“待人工审核”筛选显示 `13` 行后已复位“全部状态”；review-lock/workbench/source-pdf/renew 请求均为 HTTP `200`，console error/warning 为 `0`
- Change: `frontend/src/styles/workbench.css` 的一行 compact source-bar 换行规则、对应 Playwright 回归、Design QA 证据与本 bug-memory 记录
- Selected lane: `Standard`
- Selected plan: `BUG-20260731-compact-source-batch-overflow` ad hoc frontend layout repair
- Selection evidence: 单个 frontend component/CSS surface，但需要 focused test、build 与真实 Chrome layout smoke；不改变稳定 API/schema 或 backend workflow
- Validation action: `completed`
- Problem boundary: 只修 pending-source bar 对 compact 三列表格的横向挤压；不隐藏待确认来源或已排除项，不改变候选号、筛选和审核语义
- Single owner: `frontend/src/components/workbench/InspectionItemTable.tsx` 与 `frontend/src/styles/workbench.css`
- Old path action: retire compact mode 下 source bar 的不可收缩单行布局；非 compact 呈现保持不变
- Rollback: 若 focused test、build 或同项目 Chrome 测量失败，回退本次 compact modifier/CSS delta；第一项验证为原 focused regression test
- Writer ownership and order: 父 agent 唯一 writer；无并发 writer
- Focused verification: RED/GREEN Playwright regression、组件回归、frontend build、同项目 `.inspection-table-section` 与 list container `scrollWidth <= clientWidth`、console error/warning 为 0
- Independent review: `accept`；补测展开确认态后 reviewer 确认无 blocking issue 或 non-blocking concern
- Next verification: 已关闭；仅在 compact 列表重新出现 `scrollWidth > clientWidth` 时重开

## BUG-20260731-recognition-preview-migration-drift

- Status: 已解决
- First reported: 2026-07-31
- Last reported: 2026-07-31
- Recurrence: 1
- Surface: `GET /api/v1/projects/{project_id}/source-pdf`、Alembic runtime schema 与 `ProjectWorkbenchApp` startup gate
- Symptom: workbench 显示“操作失败，请重试”，所有审核字段和动作禁用，项目没有正式气泡
- Previously correct behavior: 已生成 working copy 的项目应能读取 source PDF 并进入可编辑审核；正式气泡只在审核解析、冻结和生成完成后出现
- Reproduction: live project `b3d4d9ba-4bcb-475b-9fa2-c559a201c7f3` 的 `/review/lock` 与 `/workbench` 返回 HTTP `200`，`/source-pdf` 返回 HTTP `500 internal_server_error`；数据库为 `alembic_version=0011` 且没有 `recognition_preview_heads / recognition_preview_revisions`，API 日志为 `UndefinedTable: relation "recognition_preview_heads" does not exist`
- Root cause: merge `59a0edb` 通过 bind-mounted `backend/app` 热加载了新的
  `_source_pdf_file()`，该 active path 会查询 `recognition_preview_heads`；运行
  PostgreSQL 仍是 `alembic_version=0011`，且 API image 没有新 Alembic files，
  因此每次 `/source-pdf` 都在缺表查询处触发 `UndefinedTable`。
- Fix: 使用当前 Compose network 的一次性 API container，只读挂载
  `backend/alembic` 与 `backend/alembic.ini`，执行 existing migration
  `0011 -> 0012`；未修改或重启 API/worker，未添加 compatibility fallback。
- Regression check: 运行 current `qi-p0` Micromamba environment、同一 Compose
  network 与只读 backend mount 的 focused tests：
  `test_project_workbench_delivers_real_pdf_without_internal_references`、
  `test_recognition_preview_schema_is_owned_by_0012_after_0011`、
  `test_preview_refresh_is_project_and_source_bound_without_working_copy`，
  返回 `3 passed, 3 warnings`；warnings 仅为既有 Starlette deprecation 与只读
  mount 无法写 `.pytest_cache`。
- Runtime proof: fresh schema check 为 `alembic_version=0012`，两张 preview 表、
  expanded processing-stage constraint 和 immutable trigger 均存在；同一项目
  health/workbench/source PDF 分别返回 HTTP `200/200/200`，PDF 为
  `application/pdf`、`194782` bytes。Chrome MCP reload 后启动请求均为 `200`，
  alert 与 console error 均为 `0`，检验项 10 的保留/排除/无需气泡动作已恢复；
  项目仍为 `frozen=false`、`active_balloons=0`，页面只显示候选/自动通过标记。
- Change: runtime database migrated to existing commit `59a0edb` head `0012`；
  repo 只更新本 bug-memory 记录
- Selected lane: `Heavy`
- Selected plan: `BUG-20260731-recognition-preview-migration-drift` ad hoc runtime repair；不重开已关闭的 symbol-recognition plan
- Selection evidence: merge `59a0edb` 已使 active `/source-pdf` path 查询新增 preview schema，但 live database 仍停在 `0011`；这是稳定 schema 与 runtime identity mismatch
- Validation action: `completed`
- Problem boundary: 只补齐 merge 已提交的 `0012` runtime schema，不改变 review、freeze、balloon 或 export contract
- Single owner: `backend/alembic/versions/0012_recognition_preview.py`
- Old path action: retire live `0011` schema state；不增加 compatibility fallback
- Rollback: migration 失败时停止并验证事务仍在 `0011`；post-upgrade 失败时保留证据并停止，不在 active code 仍依赖 `0012` 时擅自 downgrade
- Writer ownership and order: 父 agent 唯一 runtime writer；无并发 writer
- Focused verification: Alembic `0012`、preview schema、同一 `/source-pdf`、workbench controls 与 formal-balloon gate
- Independent review: `accept`；无 blocking issue、confirmed defect 或 material risk
- Next verification: 已关闭；仅在新 deployment/schema drift 或 `/source-pdf` 回归时重开

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
