# Project Bug Memory

本文件记录项目内用户报告的 bug 和已经确认的回归。调试前先阅读；重复问题更新原记录，不要重复创建。

## BUG-20260803-save-and-return-no-feedback

- Status: 已解决
- First reported: 2026-08-03
- Last reported: 2026-08-03
- Recurrence: 1
- Surface: `InspectionWorkbench` 未保存修改返回对话框、草稿批量保存与失败反馈
- Symptom: 用户点击“保存并返回”后对话框保持不变，看起来按钮没有反应；页面摘要仅在遮罩后显示“保存失败”
- Reproduction: live 项目 `f62ad156-b7dd-43ea-a8ee-fbeda4f78770` 点击后 working copy 仍为 version `1`，API 日志没有该项目的 `/review/commands` 请求，证明保存被前端草稿校验在请求前拒绝；当前对话框没有失败原因或处理建议
- Root cause: `saveAndReturnToDrawingList()` 将草稿句柄的本地校验失败与 API 保存失败都折叠为 `saveState="保存失败"`，但 `saveState` 只显示在对话框后方的项目摘要；对话框继续显示原始未保存说明，没有错误提示或下一步，造成“点击没反应”的用户感知
- Selected lane: `Standard`；局部 frontend 行为与文案修复，但需要 focused test、full frontend suite/build、真实 Chrome smoke 和独立 review
- Selected plan: 本 bug-memory entry 作为当前 ad hoc task contract；不切换或扩展 P0 implementation plan
- Problem boundary: 只让“保存并返回”的失败在当前对话框内可见且可操作；不放宽草稿校验，不自动丢弃内容，不改变保存顺序、Review API、锁、working-copy version 或返回导航语义
- Single owner: `InspectionWorkbench` 继续拥有 return dialog 和多草稿保存编排
- Old path action: 替换“失败后对话框内容完全不变”的静默路径；保留失败时停留工作台和保留草稿的既有安全行为
- Unchanged contract: 只有全部草稿保存成功才调用 `onReset`；本地无效草稿不发 API；API 失败不丢草稿；“不保存返回”和“取消”语义不变
- Allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/InspectionWorkbench.tsx`、`frontend/src/components/workbench/InspectionWorkbench.test.tsx`、`frontend/src/copy/zhCN.ts`
- Writer ownership and order: 父 agent 在隔离 worktree `fix/save-and-return-feedback` 中为唯一 writer；主工作树同文件的另一任务改动不覆盖，完成后先整合最新 `main` 并重跑验证
- Focused verification: `micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/InspectionWorkbench.test.tsx`
- Validation action: 先新增“本地无效草稿不发请求但对话框显示可操作失败提示”的 RED，再做最小 GREEN；随后 full frontend、build、Chrome smoke 与 independent review
- Fix: `InspectionWorkbench` 在打开、取消、放弃、重试和成功路径上显式管理 return-save failure；任一草稿或 metadata 保存失败时保留对话框与草稿，并在对话框内显示 `role="alert"` 的原因中立提示，允许检查后重试、继续编辑或明确不保存返回
- Regression check: 先新增本地无效新增草稿 RED，精确失败于对话框缺少 `role="alert"`；review 后将 API 与本地失败统一文案改为原因中立，并再次取得两项 RED/GREEN。整合最新 `main@f28590a` 后 focused `InspectionWorkbench.test.tsx` 为 `51 passed`，full frontend 为 `25 files / 317 tests passed`，production build 和 `git diff --check` 通过；build 仅保留既有 Vite large-chunk warning
- Runtime proof: Chrome 在 worktree frontend `15175` 对项目 `d5417ca0-2fe3-4dca-ba9f-10b9ba30032c` 填入不完整新增草稿 `M10` 后点击“保存并返回”，对话框保持打开并显示原因中立提示，`M10` 仍保留；浏览器 network 和 API access log 均无该项目 `/review/commands`，随后“不保存返回”回到列表且 `/review/lock/release` 返回 `200`；console 无 error/warning
- Independent review: 初审 `accept with concerns`，指出统一文案会误导 API/锁失败且 `main` 已前进；文案改为原因中立并 fast-forward 整合 `main@f28590a` 后复审 `accept`，确认两项 concern 均关闭、无 blocking 或 non-blocking concern、阶段 gate 与本任务状态机均完整保留
- Change: `.agent/bug-memory.md`、`InspectionWorkbench.tsx`、`InspectionWorkbench.test.tsx`、`zhCN.ts`

## BUG-20260803-auto-accepted-items-remain-pending

- Status: 修复待验证
- First reported: 2026-08-03
- Last reported: 2026-08-03
- Recurrence: 1
- Surface: 新上传图纸从 `automatic-result/3` 创建审核工作副本时的自动通过投影、`quality_inspection-worker-1`
- Symptom: 用户在自动通过修复合入后重新上传图纸，界面仍没有任何自动通过气泡，全部检验项继续显示待人工审核
- Previously correct behavior: `automatic-result/3` 中 `confidence_decision.review_disposition=auto_accepted` 的候选项应在新建审核工作副本时投影为已采纳，并保留其自动采纳来源
- Reproduction: 2026-08-03 13:05 本地新项目 `6d8d9b3a-4083-4e4e-9540-fe9ca8bcd359` 的 raw result 有 139 项，其中 108 项为 `auto_accepted`、31 项为 `review_required`；同一项目的 working copy 却为 139 项全部 `pending + requires_confirmation=true + acceptance_source=null`
- Root cause: `quality_inspection-worker-1` 启动于 2026-08-03 11:46，早于修复提交 `501fd42` 的 12:28；Celery worker 在进程启动时导入 `ReviewService`，不会像 API 的 Uvicorn reload 一样自动加载 bind mount 后续变更，因此用户新上传任务仍执行修复前的 working-copy 投影代码
- Selected lane: `Standard`；不修改稳定 API/schema/runtime config，只恢复已合入代码的 worker runtime identity，并用真实数据库投影与队列状态验证原始 failure surface
- Selected plan: 本 bug-memory entry 作为当前 ad hoc task contract；关闭后返回已批准的 GDT-10E paid-run plan，当前不触发额外 Provider 调用
- Problem boundary: 只替换共享 Compose project 中已确认空闲的 `worker` 进程以加载当前 `main`；不重建 API、PostgreSQL、Redis，不删除 volume，不改变既有项目数据或自动重跑用户项目
- Single owner: `quality_inspection-worker-1` 的 Celery 进程 runtime identity
- Old path action: 退役启动于修复提交之前、仍持有旧 `ReviewService` 的 worker 进程；保留现有 Compose service、queue、database 和 storage Owner
- Unchanged contract: `automatic-result/3`、review working-copy schema、confidence decision、人工审核、freeze、气泡和正式导出合同均不变
- Allowed paths: `.agent/bug-memory.md`；production code 和 runtime config 不修改
- Writer ownership: 父 agent 为唯一 writer；现有其他 agent 均为只读 reviewer/explorer，不拥有本文件
- Validation action: 已确认 worker `active/reserved/scheduled` 为空，再执行 `docker compose -p quality_inspection -f /home/reggie/vscode_folder/Quality_Inspection/compose.yaml up -d --no-deps --force-recreate worker`；随后验证 worker 启动时间、代码 identity、Celery ping/queue、API health，并保留一次重传同一 PDF 的可见闭环验证
- Fix: 仅重建 `quality_inspection-worker-1`，让 Celery 重新导入当前 `main@fe22698` 中含 `501fd42` 的 `ReviewService`；API、PostgreSQL、Redis、volume 和既有项目均未重建或改写。修复前已生成的 broken working copy 不做隐式迁移，避免覆盖人工审核状态
- Regression check: 首次直接 focused pytest 因宿主机继承 Compose-only `postgres` hostname 而在 setup 失败，不作为代码 verdict；仓库隔离 Compose 又被本机 Docker address-pool exhaustion 阻断。改用 host-network + tmpfs disposable PostgreSQL 17，真实迁移至 head 后运行 `/2`、`/3` 参数化 working-copy regression，结果 `2 passed / 29 deselected`，临时容器已移除
- Runtime proof: worker 从旧 ID `53659e4e1d02...` 替换为 `3a9d187f398d...`，新进程启动于 13:11:36+08，晚于 `501fd42`；worker 内 `app/review/service.py`、`app/processing/tasks.py`、`app/processing/automatic_result.py` 与 host 哈希一致，Celery `ping=pong` 且 `active/reserved/scheduled` 全空。API、PostgreSQL、Redis container ID 均保持不变，`5173` 同源 health 返回 `ok`
- Independent review: verdict 为 `accept with concerns`，无 confirmed defect 或 recovery blocker；reviewer 确认 root-cause 时间链、worker-only recovery、关键文件 identity、队列和未改写既有项目。唯一 material risk 是尚缺 worker 重建后的真实新上传或等价 live replay，因而当前只能证明 runtime 已加载修复，不能宣称用户可见回归已经闭环
- Next verification: 用户重传同一 PDF 后，确认 raw `auto_accepted` candidate IDs 与 working-copy `status=auto_accepted` item IDs 完全一致且非空，并在 Workbench 可见；在这项 live proof 前保持“修复待验证”

## BUG-20260801-drawing-list-get-405

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 2
- Surface: `QualityInspectionApp` 图纸目录加载、`GET /api/v1/projects` 与本地 `5173 -> 8000` API proxy
- Symptom: 打开 `http://127.0.0.1:5173/` 后页面一直显示“图纸列表加载中”，并提示“网络异常，请检查连接后重试。”
- Previously correct behavior: 根地址应从服务端加载图纸目录，并显示图纸数量、空目录状态或已有图纸列表
- Reproduction: 用户截图确认故障；本次 `GET http://127.0.0.1:5173/api/v1/health` 返回 HTTP `200`，而页面实际请求的 `GET http://127.0.0.1:5173/api/v1/projects` 返回 HTTP `405 Method Not Allowed`
- Root cause: `5173` frontend 来自当前 `main`，但共享 Compose project `quality-inspection` 的 `8000` API 被 sibling worktree `.worktrees/structured-geometric-tolerance-recognition` 重建并占用；live container label 的 working dir 指向该 worktree，容器内 `projects.router` 不含后来由 `423a2e4` 加入的目录 GET，live OpenAPI 因而只声明同路径 `POST`。frontend 与 API checkout 身份分裂，精确导致目录 GET 返回 `405`
- Fix: 等待 sibling worktree 正在运行的 `verify-p0-live` 自然结束，避免破坏其 runtime identity evidence；随后从当前 `main` 执行 canonical `make dev-local-api`，重建并替换 API。新容器 working dir 与 bind mount 均指向当前仓库根，未修改 production code、API contract 或 runtime config 文件
- Regression check: 在独立临时 PostgreSQL 中运行 `PYTHONDONTWRITEBYTECODE=1 QI_DATABASE_URL=<isolated-postgres> micromamba run -n qi-p0 python -m pytest backend/tests/integration/test_project_catalog_api.py -q`，结果 `3 passed`；唯一 warning 为既有 Starlette `httpx` deprecation
- Runtime proof: live container working dir 为 `/home/reggie/vscode_folder/Quality_Inspection` 且 bind mount 为当前 `backend/app`；`/openapi.json` 的 `/api/v1/projects` 同时包含 `get`、`post`；经 `5173` proxy 的目录 GET 返回 HTTP `200`、`count=8`。`browse` Chromium smoke 确认“网络异常”与“图纸列表加载中”均消失，显示“共 8 份图纸”，console error 为 0，目录请求及 8 个项目状态请求全部为 HTTP `200`
- Change: runtime recovery only；`.agent/bug-memory.md` 记录本次回归
- Selected lane: `Standard`；故障跨 frontend request、Vite proxy 与 backend route，需要 focused test 和真实 browser/API smoke，但不预设改变稳定 API 或 runtime config
- Problem boundary: 只恢复既有图纸目录读取；不改变 PDF 上传、处理状态、审核、锁、freeze 或 export 语义
- Unchanged contract: frontend 继续通过同源 `GET /api/v1/projects` 读取服务端目录；现有 `POST /api/v1/projects` 上传合同保持不变
- Allowed paths: `.agent/bug-memory.md`；已确认当前 `main` 的 route Owner 与 focused test 正确，因此不修改 production code 或 runtime config
- Writer ownership and order: 父 agent 为唯一 writer；只读 explorer 仅做独立调用链核查；实现完成后派发独立只读 reviewer
- Validation action: `completed`；focused integration、live API identity、OpenAPI、同源目录 GET 与浏览器 smoke 均已覆盖原始 failure surface
- Independent review: verdict 为 `accept with concerns`，无 blocker；reviewer 独立确认 API container working dir/mount、live OpenAPI 与 `5173` 目录 GET 均已恢复。唯一 material concern 是 `quality-inspection-worker-1` 仍来自 sibling worktree；worker 不参与本次目录 GET，因此不阻断当前修复，但上传后的异步处理 runtime identity 尚未在本任务中收敛
- Follow-up runtime convergence: 用户批准后，先确认旧 worker 的 active/reserved/scheduled 均为空，再从当前 `main` 以 `docker compose -p quality_inspection -f compose.yaml -f compose.dev-local.yaml up -d --build --no-deps worker` 精确替换 worker；API container ID 保持不变，PostgreSQL、Redis 和 volume 均未重建或删除。新 worker 的 Compose working dir/config 指向当前仓库，`celery_app.py`、`processing/tasks.py`、`candidates/advisor.py` 与 main 文件哈希一致；Celery `ping=pong` 且 active/reserved/scheduled 均为空，`5173` health 为 `ok`、目录 GET 为 HTTP `200`、`count=8`
- Follow-up independent review: verdict 为 `accept`，无 blocker 或 concern；reviewer 独立复核 worker/main 文件哈希、Celery 状态、API container identity、PostgreSQL/Redis/volume 未替换证据及 `5173` health/projects live response
- Next verification: 已关闭；仅在共享 Compose project 再次由缺少 catalog GET 的 sibling checkout 占用 `8000` 时重开

## BUG-20260801-recognition-preview-unstyled

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `RecognitionPreviewApp`、新上传图纸处于 `local_ready` / `vlm_enriching` 时的只读识别预览
- Symptom: 新上传图纸后页面退化为浏览器默认排版：标题和识别文本贴边纵向堆叠，PDF 只显示在默认大小的小 `iframe` 中，缺少正常产品布局和可读信息层级
- Previously correct behavior: 上传和识别过程应保持产品级页面布局，图纸预览和识别进度在当前视口内清晰可用
- Reproduction: 用户提供 `http://127.0.0.1:5173/` 截图；页面显示“识别预览 / 版本 1 / 本地识别完成”，随后是默认大小 PDF iframe 和逐行裸文本候选值
- Root cause: `QualityInspectionApp` 在 `local_ready` / `vlm_enriching` 阶段直接渲染 `RecognitionPreviewApp`；该组件自首次加入起只输出无 `className` 的裸 `<main>/<h1>/<p>/<iframe>`，现有样式表也没有匹配该 DOM 的选择器。全局 CSS 实际已正常加载，因此浏览器按默认约 `300×150` iframe 和普通段落排版，精确产生用户截图中的退化页面
- Fix: 保持原 GET-only polling 与 revision 单调更新不变，为 preview 增加产品 header、进度摘要、响应式图纸主区和两个限高滚动结果栏；专用规则收敛到 `recognition-preview.css`，桌面为图纸/结果双栏，`820px` 以下转为单栏
- Regression check: TDD RED 精确失败于旧组件缺少 product-layout contract；GREEN focused `4/4`。新增 Playwright 几何回归在 `1440×1000` 与 `768×900` 下验证双栏/单栏、iframe 最小尺寸、结果独立滚动和无横向溢出，`2/2` 通过；本任务修改完成后完整 frontend 曾为 `24 files / 293 tests`，但最终 fresh 全量复跑被并行中的无关 `TechnicalRequirementPanel` / `InspectionWorkbench` TDD 改动打红，因此最终完成证据以 focused `4/4`、Playwright `2/2`、production build 与 `git diff --check` 为准；build 仅保留既有 Vite large-chunk warning
- Runtime proof: headed Chrome 将同一新图纸 `562633c8-…` 的 live `recognition-preview` revision 2 挂载到当前组件；API 与 source PDF 均为 HTTP `200`。`1440×1000` 下 layout/drawing 无横向溢出，iframe 为 `834×722`，21 个检验项与 105 条来源分别 `overflowY=auto`；`768×900` 下为单栏且 iframe `711×630`，console error/warning 为 `0/0`。项目已进入 terminal failed，未以新上传或伪造 status 冒充完整 route-transition replay
- Change: 本提交
- Selected lane: `Standard`；production 修改预计局限 frontend，但需要 API status route 与 headed Chrome smoke 证明真实 transient failure surface
- Selected plan: 本 bug-memory entry 作为 ad hoc task contract；不切换或扩展当前 P0 implementation plan
- Problem boundary: 只修 `local_ready` / `vlm_enriching` 识别预览的布局与可读性；不改变 recognition 数据、polling、status transition、API schema、审核工作台或正式导出
- Single owner: `frontend/src/components/workbench/RecognitionPreviewApp.tsx`
- Old path action: 退役裸 DOM 和浏览器默认 iframe presentation path；保留唯一 preview data/polling Owner
- Unchanged contract: `GET /recognition-preview`、revision 单调更新、GET-only 只读行为、`source_pdf_url` 和 ready routing 均保持不变
- Allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/RecognitionPreviewApp.tsx`、`frontend/src/components/workbench/RecognitionPreviewApp.test.tsx`、`frontend/src/styles/app.css`、`frontend/src/styles/recognition-preview.css`、`frontend/e2e/recognition-preview-style.spec.ts`
- Writer ownership and order: 父 agent 为唯一 writer；只读 explorer 不得修改文件；实现后派发独立只读 reviewer
- Validation action: `completed`；root cause、focused TDD、geometry regression、build、headed Chrome 与独立 review 均已覆盖；当前全工作树 frontend suite 的无关并行失败不计为本任务通过证据
- Independent review: 初审 `accept with concerns` 指出 CSS 删除回归和 component/CSS class seam 尚未持久覆盖；补充 Playwright geometry regression 与 `layout/results` class contract 后，最终 verdict 为 `accept`，无 blocker 或 remaining concern
- Next verification: 已关闭；仅在 preview 再次出现默认 iframe、横向溢出或结果列表撑长整页时重开

## BUG-20260801-review-lock-renewal-cross-project

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `ProjectWorkbenchApp` review lock renewal、`POST /api/v1/projects/{project_id}/review/lock` 与 `review_locks` project scope
- Symptom: 多人分别查看不同图纸时，进入审核页面仍会显示“审核锁续期失败，修改操作已暂停。”；用户观察到无论其他人查看的是第几份图纸都会触发
- Previously correct behavior: review lock 必须按 `project_id` 隔离；不同 operator 同时查看或编辑不同图纸时互不影响，只有同一图纸被其他 operator 持有有效锁时才冲突
- Reproduction: 用户在 `https://qa.srj666.com/` 截图确认已进入页面后出现 renewal failure 文案和“回到图纸列表”；API 日志随后显示 `266e…`、`b3d4…`、`fb057…` 三个项目各自存在独立 lock 请求，409 只发生在对应项目内；数据库同时显示这 3 个 active lock 均由测试 operator `4362748d-…` 持有
- Root cause: Chrome 自动化遗留了 3 个长期打开的 `?project_id=…&operator_id=4362748d-…` 深链 tab，分别对 3 份目录图纸每 240 秒续租 300 秒 project lock；因此其他电脑点击这 3 份图纸都会被各自的测试租约拒绝，看起来像“无论第几份都被锁”。后端 `review_locks.project_id` 主键、`acquire_lock()` 查询和冲突条件均为 project-scoped，不存在全局 operator lock
- Fix: 关闭 3 个已确认属于自动化的深链 tab，并仅将 operator `4362748d-…` 在 `266e…`、`b3d4…`、`fb057…` 上的 3 条测试租约设置为立即过期；验证结束后同样让本次 smoke operator `11111111-…` 的单条租约过期。未删除 review lock 表、未修改其他 operator/project lock、未改变 production code
- Regression check: `backend/tests/integration/test_review_lock.py` 已有同项目第二 editor 拒绝、过期接管和同 operator 续期覆盖；本次只读 call-chain 核验进一步确认 router/model/query 均以 `project_id` 为唯一锁 scope。无需为已确认的测试运行态污染修改 production test/code
- Runtime proof: 清理后数据库一度为 `active_locks=0`；headed Chrome 从 `https://qa.srj666.com/` 服务端 4 份图纸目录打开 `BK20101401-09L1000…`，成功进入含 124 个检验项的完整工作台且无 lock alert。随后外部 browser/operator `4362748d-…` 又主动续租 `266e…`，证明仍有该 operator 的真实页面运行；在此单项目锁有效期间，临时不同 operator 分别获取 `b3d4…` 与 `fb057…` 均返回 HTTP `200`，交叉验证不同图纸互不阻塞。两条临时租约已立即过期，最终只保留外部 browser 的 `266e…` 业务锁
- Change: runtime cleanup only；no production code change
- Selected lane: `Standard`；需要跨 browser tab、frontend renewal、API 日志和 PostgreSQL lock rows 对齐，但最终根因属于有界测试运行态污染
- Problem boundary: 只清理本次自动化遗留的 3 条 project lease；不放宽“一项目一个 active editor”、不允许同图纸并发写、不触碰其他用户锁
- Independent code mapping: 后端锁为明确 project-scoped；另发现 `ProjectWorkbenchApp` 对旧项目在途续租失败缺少 cancellation 的潜在 prop-switch 风险，但当前目录导航会卸载组件，且本次真实 409/DB 证据由 3 个自动化 tab 完整解释，因此不在此运行态修复中扩展代码范围
- Recurrence evidence (2026-08-01): 用户再次在 `http://127.0.0.1:5173/` 被 review lock conflict 阻断；Chrome MCP 同时存在仍停留在工作台的 Headless Chrome tab，`266e…` 以 operator `4362748d-…` 持续成功续租，另有 smoke operator `11111111-…` 持有 `b3d4…`。数据库与网络记录证明即使无人实际操作，只要自动化 tab 未关闭或退出未释放，300 秒 lease 仍会每 240 秒延长
- Recurrence fix: Unknown；本轮先验证 owner-scoped 主动 release API 与 frontend unmount/pagehide 生命周期，不放宽同项目单 editor 合同
- Recurrence regression check: Pending TDD RED/GREEN、API contract gate、frontend lifecycle coverage 与真实 Chrome close/return smoke

## BUG-20260801-sip-metadata-auto-confirm

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `InspectionWorkbench` 的项目级 SIP metadata 建议、`SipInformationPanel` 编辑入口与 `ExportPanel` 正式文件门禁提示
- Symptom: 图纸已经识别并展示物料编码、产品名称、图号和版本号，客户确认完技术要求后，正式文件仍显示“项目 SIP 信息未确认”；客户必须再次展开整张项目 SIP 表单，且无法知道实际只缺“材质”
- Previously correct behavior: 无；旧合同要求所有识别建议都由人工整表确认
- Reproduction: live `266e00ec-b97f-43a8-9f46-9af753374b01` 的 6 条技术要求均已确认、逐行 SIP 为 `121 / 0`，但 `working_copy.sip_metadata` 五字段均未持久化；项目基本信息已从 suggestions 展示 4 个识别值，只有材质缺失，`ExportPanel` 仍只显示泛化“项目 SIP 信息未确认”
- Root cause: `metadataDraft()` 只将图纸识别 suggestions 预填到 frontend local draft，`hasConfirmedSipMetadata()` 与 backend freeze 只接受持久化的 `working_copy.sip_metadata`；完整识别结果不会自动走既有 `set_sip_metadata` command，缺失场景也没有把具体字段投影到正式文件门禁
- Selected lane: `Standard`；保留既有 backend command、freeze/review/export contract，仅调整 frontend 自动提交和缺失/冲突呈现，并需要 focused/full tests、headed Chrome smoke 与独立只读 review
- Problem boundary: 识别值完整且无待补字段时自动通过既有 `set_sip_metadata` 保存；不完整时只提示并要求补充缺失字段，不把 suggestions 直接当作 backend 已确认状态；已持久化人工值继续优先，识别冲突不自动覆盖
- Single owner: `InspectionWorkbench` 继续拥有项目 metadata draft 与 `submitCommand()`；`SipInformationPanel` 和 `ExportPanel` 只消费同一字段状态作客户提示
- Old path action: 退役“所有识别建议都标为待确认并要求整表二次确认”的默认路径；保留人工修改和保存失败后的显式重试入口
- Unchanged contract: `set_sip_metadata` payload、working-copy versioning、dirty/save/return、freeze、reviewed result、balloon 与 atomic export contract 均不变
- Focused verification: `micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/SipInformationPanel.test.tsx src/components/workbench/ExportPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx`
- Allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/InspectionWorkbench.tsx`、`frontend/src/components/workbench/InspectionWorkbench.test.tsx`、`frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`、`frontend/src/components/workbench/SipInformationPanel.tsx`、`frontend/src/components/workbench/SipInformationPanel.test.tsx`、`frontend/src/components/workbench/ExportPanel.tsx`、`frontend/src/components/workbench/ExportPanel.test.tsx`、`frontend/src/copy/zhCN.ts`、`frontend/src/styles/workbench.css`
- Writer ownership: 父 agent 唯一 writer；实现后派发独立只读 reviewer
- Fix: 完整且无冲突的 5 个识别值会在既有命令通道可用时恰好一次提交 `set_sip_metadata`；命令繁忙时等待恢复，不提前消耗 attempt。缺失值只要求补充具体字段；冲突、人工补全、保存失败和等待自动保存分别显示真实状态，失败后保留显式重试。`ExportPanel` 同步投影同一阻断原因，不改变正式导出门禁。
- Regression check: TDD RED 精确暴露完整识别不自动提交、缺失字段仍泛化、busy attempt 被消耗、冲突误报自动保存、失败无明确重试和 Export conflict 泛化；GREEN focused `4 files / 85 tests`、full frontend `24 files / 287 tests`，`npm run build` 与 `git diff --check` 通过。独立 `reviewer` 初审 `reject` 后复核上述状态机修复，最终 verdict `accept`，无 blocking/non-blocking concern。
- Runtime proof: headed Chrome 读取 live `266e00ec-b97f-43a8-9f46-9af753374b01`：正式文件显示“待补充项目 SIP：材质”，SIP 显示“系统已自动采纳 4/5，待补充：材质”，4 个识别字段标为“已自动采纳”，材质为空时“保存补充信息”禁用；本次页面加载仅有 lock/workbench/source-pdf 请求，无 `/review/commands` 写入，console warning/error 为 0。
- Change: 本提交

## BUG-20260801-sip-exception-second-confirmation

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 3
- Surface: `SipInformationPanel` 的异常行与 `SelectedSipDetailFields` 编辑器
- Symptom: SIP 自动映射已填好大部分字段后，`未知检验项类型` 等真实异常仍展开整张 SIP 表单和“保存当前 SIP 字段”，让用户感觉需要对检验项做第二次完整校验
- Root cause: `SipInformationPanel` 已按 exception-only contract 只在异常行挂载编辑器，但 `SelectedSipDetailFields` 不区分异常修复和主动修改，始终渲染全部字段及通用保存文案；`sip_regeneration_required` 也沿同一路径展示了不必要的手工表单
- Selected lane: `Standard`；局部 frontend 行为和文案调整，保留现有 command、draft/save/freeze/export contract，并需要真实 browser smoke
- Problem boundary: 只改变 SIP 异常行的字段显隐、引导和主按钮文案；不改变 `generate_sip_table`、`set_sip_detail_fields` payload、自动 mapping、异常判定或 readiness bit
- Single owner: `SipInformationPanel` 继续决定何时进入异常编辑；`SelectedSipDetailFields` 继续拥有单行草稿与既有 command producer
- Old path action: 退役异常态下默认展开全部 SIP 字段和泛化“保存当前 SIP 字段”的呈现；完整 resolved 行的按需编辑保持不变
- Unchanged contract: 自动映射完整的行不出现逐项确认；缺失字段仍必须补齐，人工保存仍通过 `set_sip_detail_fields` 原子清除该行异常；纯 regeneration exception 仍通过 `generate_sip_table` 处理
- Focused verification: `cd frontend && npm test -- --run src/components/workbench/SelectedSipDetailFields.test.tsx src/components/workbench/SipInformationPanel.test.tsx`
- Writer ownership: 父 agent 唯一 writer；实现后派发独立只读 reviewer
- Main advancement gate: 当前从 `2aaebf4` 前进到 `fe173c1` 的 delta 只与本任务共同触碰 `.agent/bug-memory.md`；production Owner/test 文件无重叠，新条目基于当前 HEAD 追加
- Fix: 可编辑异常只突出 exception code 对应字段，所有自动字段默认折叠并保留按需修改入口，主动作改为“解决并保存 SIP 异常”；完整映射行继续不显示逐项确认。任何包含 `sip_regeneration_required` 的行都不再挂载 `SelectedSipDetailFields` 或 `set_sip_detail_fields` draft/save handle，失效 dirty owner 在卸载时清除，重新生成继续由 `generate_sip_table` 单独拥有
- Regression check: TDD RED 分别证明旧 UI 仍展开全部字段、纯 regeneration 仍保留 hidden draft handle；修复后 focused 3 files 为 `67 passed`，完整 frontend suite 为 `281 passed`，production build 与 `git diff --check` 通过
- Runtime proof: headed Chrome 在真实 `BK20101401-09L1000 / 0.08 / 未知检验项类型` 异常上只显示“检验方法（需补充）”，其他字段默认折叠，主动作是“解决并保存 SIP 异常”，不存在“保存当前 SIP 字段”；仅进行选择/展开，未提交 review command，console error 为 0
- Independent review: 初审 `reject` 指出 regeneration-only 表单虽 hidden 但旧 save handle 仍挂载；改为不挂载并增加 editable dirty → regeneration 的 ref/null、dirty false、no-command 回归后，follow-up verdict 为 `accept with concerns`，无 blocker；仅保留 exception mapping 参数化覆盖建议
- Change: `fix(frontend): focus SIP exception resolution`
- Recurrence evidence (2026-08-01): 真实 `0.08` 行在检验项列表已显示为“粗糙度”，SIP 仍报告“未知检验项类型”并要求人工补“检验方法”；用户指出技术要求/上游识别已具备该语义，预期 SIP 应自动消费而不是再次询问
- Recurrence root cause: `surface_roughness` 按冻结的 coarse candidate contract 只写 `coarse_type="roughness"`，不扩展 `item_type`；检验项列表已回退读取 `coarse_type` 显示“粗糙度”，但 `map_sip_item()` 只读取 `item_type`，因此同一已识别行在 SIP Owner 中被误判为 `unsupported_item_type`。技术要求 suggestion 本身不拥有 `inspection_method`，不应为修复而扩展第二个方法映射 Owner
- Recurrence selected lane: `Standard`；跨 candidate/review/SIP 数据链做只读确认，但 production 写入仅限 backend SIP mapper，不改变 coarse candidate public shape、API schema 或 frontend command
- Recurrence problem boundary: 只让缺少结构化 `item_type` 的粗糙度 coarse item 复用已识别类型，确定性生成“粗糙度 / 粗糙度仪”；未知类型与 `composite_method_required` 仍保留人工异常，人工 SIP 值及 provenance 继续优先
- Recurrence single owner: `backend/app/review/sip_mapping.py::map_sip_item`
- Recurrence fix: `map_sip_item()` 在 `item_type` 缺失时回退读取 `coarse_type`，并增加 `roughness -> 粗糙度 / 粗糙度仪` 的版本化规则；不向技术要求 suggestion 增加 `inspection_method`，也不提升 coarse roughness 为结构化 candidate type
- Recurrence regression check: TDD RED 证明旧 mapper 输出“检验项目：0.08”并缺少方法；unit suite 为 `13 passed`，隔离 PostgreSQL 的完整 backend suite 为 `1611 passed / 4 warnings`，`git diff --check` 通过
- Recurrence runtime proof: headed Chrome 对真实 `BK20101401-09L1000` 执行现有 `generate_sip_table`，HTTP `200`；6 条原 `unsupported_item_type` 粗糙度行自动得到“粗糙度：<值> / 粗糙度仪”、exceptions 清空且 confirmed=true，2 条既有人工方法“无 / 11”保持不变；刷新后摘要从“已生成 115 / 异常 6”变为“已生成 121 / 异常 0”，不再显示“检验方法需补充”
- Recurrence independent review: `reviewer` verdict 为 `accept`，无 blocker 或 concern；确认 structured/unknown/composite 分支、manual provenance、其他 coarse type fail-closed 行为和唯一 SIP Owner 均保持正确
- Recurrence change: `fix(backend): map roughness SIP method`
- Second recurrence evidence (2026-08-01): 用户在“已生成 115 / 异常 6”旁展开一个已确认的“未注形位公差”普通 SIP 行后，把全局异常统计与当前行的完整编辑表单理解为同一行仍需二次审核；live working copy 证明该行 `exceptions=[]`、`sip_detail_fields_confirmed=true`，截图中的“保存当前 SIP 字段”是可选编辑而非异常修复
- Second recurrence root cause: `SipInformationPanel` 将全局 exception count / “处理下一条异常”和当前 resolved row 的普通编辑入口放在同一视觉区域；普通入口仍命名为“查看或修改当前 SIP 行”，展开后按钮与完整表单同时存在，且没有“当前行无异常”的状态提示，因此正确状态被呈现成重复校验
- Second recurrence selected lane: `Standard`；只改 frontend 当前行状态与可选编辑呈现，需要 focused tests、完整 frontend 验证、headed Chrome smoke 和独立只读 review
- Second recurrence problem boundary: 明确区分“全局仍有异常”和“当前行已完成”；普通 resolved row 的修改保持可选，`generate_sip_table`、`set_sip_detail_fields`、exception count、technical-requirement invalidation、draft/save/freeze/export contract 均不变
- Second recurrence single owner: `frontend/src/components/workbench/SipInformationPanel.tsx`
- Second recurrence allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/SipInformationPanel.tsx`、`frontend/src/components/workbench/SipInformationPanel.test.tsx`、`frontend/src/components/workbench/InspectionWorkbench.test.tsx`、`frontend/src/copy/zhCN.ts`、`frontend/src/styles/workbench.css`；focused 联动验证证明 `InspectionWorkbench.test.tsx` 是旧 accessible name 的直接 consumer，只同步入口名，不改变测试语义
- Second recurrence writer ownership: 父 agent 唯一 writer；实现完成后派发独立只读 reviewer
- Second recurrence focused verification: `micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/SipInformationPanel.test.tsx src/components/workbench/InspectionWorkbench.test.tsx`
- Second recurrence fix: resolved 当前行先明确显示“当前行已完成，无需处理”，若全局仍有异常则另行显示“全局另有 N 条 SIP 异常待处理”；普通入口改为“可选修改当前 SIP 行”，展开后入口被可选操作提示替换，原有单行编辑器、异常处理和 command 路径不变
- Second recurrence regression check: TDD RED 精确证明旧 UI 缺少完成提示且 ordinary opener 仍被理解为处理动作；修复后 focused 2 files 为 `61 passed`，完整 frontend suite 为 `282 passed`，production build 与 `git diff --check` 通过
- Second recurrence runtime proof: headed Chrome 在真实 `BK20101401-09L1000` working copy（摘要“已生成 121 / 异常 0”）验证 resolved 当前行只显示“当前行已完成，无需处理”和“可选修改当前 SIP 行”；展开后 opener 消失并显示“以下修改为可选操作，不属于异常处理。”与既有 SIP 字段编辑器，console error 为 0；`115 / 6` 的全局异常分离由 focused component test 覆盖，未为 smoke 改写项目数据
- Second recurrence independent review: `reviewer` verdict 为 `accept`，无 blocker 或 concern；确认 resolved/global 状态分离、optional opener 生命周期、真实异常、regeneration、reviewed/frozen 分支以及现有 contract 均保持正确
- Second recurrence change: `fix(frontend): clarify resolved SIP rows`

## BUG-20260801-root-resumes-locked-project

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `QualityInspectionApp` 根地址启动恢复、`sessionStorage qi.current-project-id` 与 `ProjectWorkbenchApp` review lock acquisition
- Symptom: 用户打开 `http://127.0.0.1:5173/` 后没有看到图纸列表，而是整页显示“审核项目正由其他人员编辑，请稍后重试。”
- Previously correct behavior: 根地址应显示图纸列表；用户显式选择图纸后才进入对应处理/审核流程，锁冲突不应让根入口失去返回列表的操作
- Reproduction: 用户截图确认 `127.0.0.1:5173` 根地址稳定渲染 review lock conflict 文案；当前代码的 `initialScreen()` 会在 `qi.current-project-id` 存在时直接恢复 processing/workbench
- Root cause: `QualityInspectionApp.initialScreen()` 会按设计恢复 `qi.current-project-id`，而 `ProjectWorkbenchApp` 首次获取 review lock 遇到 409 时进入 `error !== undefined && snapshot === undefined` 分支；该分支只渲染错误文案，没有透传已有 `onReset` 操作，因此用户既不能进入被锁项目，也不能清除当前项目上下文返回列表
- Fix: 保留既有 review lock 冲突和安全中文提示，只在 `ProjectWorkbenchApp` 启动错误分支存在 `onReset` 时渲染“回到图纸列表”；点击继续复用 `QualityInspectionApp.returnToDrawingList()` 清除 session project 并加载服务端图纸目录，不删除、不抢占、不绕过有效锁
- Regression check: TDD RED 精确失败于 409 lock conflict 页面找不到“回到图纸列表”；focused `ProjectWorkbenchApp.test.tsx` 为 `12 passed`；完整 frontend suite 为 `278 passed`，production build 通过
- Runtime proof: headed Chrome 在 `127.0.0.1:5173` 和 `https://qa.srj666.com` 均用不同 operator 恢复一个仍由其他 operator 持有锁的项目，页面保留 409 文案并显示“回到图纸列表”；点击后 `qi.current-project-id=null`，两处均返回服务端目录并显示 `共 4 份图纸`
- Change: `fix(frontend): escape locked project startup`
- Selected lane: `Standard`；修复面只有一个既有 frontend startup error branch，但需确认 session 恢复、review lock 与公网开发入口的真实联动行为
- Problem boundary: 只修 lock conflict 启动页缺少退出路径；不改变根地址恢复策略、锁租约、锁 owner、API、目录过滤或项目状态
- Single owner: `ProjectWorkbenchApp` 继续拥有工作台启动错误展示；`QualityInspectionApp.returnToDrawingList()` 继续拥有清除当前项目上下文和返回目录
- Old path action: 将“只有错误文本的不可退出启动分支”替换为“错误文本加既有 reset callback”；不存在第二套返回逻辑
- Unchanged contract: 有效 review lock 仍阻止其他 operator 进入审核；没有 `onReset` 的兼容调用方仍只显示错误，不新增隐式导航
- Focused verification: `cd frontend && npm test -- --run src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Independent review: verdict 为 `accept with concerns`，无 confirmed defect；reviewer 指出新用例未单独集成验证 session 清理/目录恢复，但既有 `QualityInspectionApp` 测试已覆盖 reset callback 的这两个行为，localhost 与公网 headed Chrome 又验证了 lock conflict 到 4 份图纸目录的完整链路；按钮适用于所有 snapshot 前错误属于轻微 scope concern，保留该行为以确保任何不可进入的恢复项目都能显式退出，同时不影响无 `onReset` 的兼容调用方

## BUG-20260801-technical-requirement-balloon-sip-handoff

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-03
- Recurrence: 3
- Surface: 技术要求确认后的检验项列表、`ReviewPanel` 气泡选择动作与 SIP handoff
- Symptom: 用户从技术要求进入检验项后，同一条通用要求再次显示为“待人工审核”；点击“设为需要气泡”后没有可感知反馈，也没有进入 SIP，流程语义看起来互相矛盾
- Previously correct behavior: 技术要求确认完成后应明确进入哪个后续审核步骤；气泡选择动作应反馈已保存状态，并在满足 SIP 前置条件后提供清晰的 SIP 下一步，而不是让用户误以为该按钮本身等于“进入 SIP”
- Reproduction: 用户截图中 candidate 117～120 的通用要求与普通尺寸一起显示“待人工审核”；选择其中一项并点击“设为需要气泡”后未观察到 SIP 跳转或状态变化
- Root cause: `TechnicalRequirementPanel` 将 `global_scope` 技术要求投影为 `scope="global_requirement"`、`balloon_required=false` 的待确认 `general_requirement`；`ReviewPanel` 却仍无条件暴露“设为需要气泡”。该 command 被后端 `global requirement target must remain global and unnumbered` invariant 以 422 拒绝，而选中项附近没有失败反馈，所以状态不变并表现为“没反应”。同时列表继续使用泛化“待人工审核”，未说明这里是在确认是否进入 SIP，而不是重复确认技术要求匹配关系
- Fix: 对 `scope="global_requirement"` 的选中项将主结论改为“确认进入 SIP”，继续复用既有 `keep` command；移除该 scope 上必然非法的气泡切换和重复的候选确认/拒绝动作，显示固定无需气泡说明；列表状态改为“待确认进入 SIP”。普通 local item 的既有气泡动作保持不变
- Regression check: TDD RED 精确证明旧 UI 仍暴露气泡 action 且状态仍为“待人工审核”；focused suite 为 `62 passed`；在当前 `main@a698951` 上完整 frontend suite 为 `277 passed`，production build 与 `git diff --check` 通过；pending -> kept rerender 证明确认动作退休且不会二次发送 command
- Runtime proof: localhost 当前项目的 authenticated workbench API 返回 4 个 active `global_requirement`，均为 `status=pending`、`requires_confirmation=true`、`balloon_required=false`；headed Chrome 选择“锐边去毛刺”后，列表和详情均显示“待确认进入 SIP”，唯一有效结论动作为“确认进入 SIP”，无“设为需要气泡 / 设为无需气泡 / 确认候选项 / 拒绝候选项”；仅执行行选择，未提交 review command，console error 为 0
- Change: `fix(frontend): clarify global SIP handoff`
- Selected lane: `Standard`；现象跨越技术要求确认、检验项状态投影、气泡 command 与 SIP handoff，需要先完成只读调用链和真实浏览器复现
- Writer ownership and order: 父 agent 唯一 writer；只读 `code-mapper` 仅提供调用链证据
- Problem boundary: 只修 `global_requirement` 在检验项阶段的动作与状态表达；不改变技术要求匹配、`keep` / `set_balloon_required` command、SIP 生成、freeze 或编号 contract
- Single owner: `ReviewPanel` 继续拥有当前检验项动作；`inspectionItemPresentation` 继续拥有列表状态文案
- Old path action: 移除全局要求上必然失败的“设为需要气泡 / 设为无需气泡”选择器，以“确认进入 SIP”复用既有 `keep` command，并明确固定无需气泡
- Unchanged contract: 全局要求仍需人工确认才进入 SIP，始终 `balloon_required=false` 且不生成图纸气泡；SIP 表格仍由现有 `generate_sip_table` 流程生成
- Focused verification: `cd frontend && npm test -- --run src/components/review/ReviewPanel.test.tsx src/components/workbench/inspectionItemPresentation.test.ts`
- Main advancement gate: 实现期间 `main` 从 `7891a94` 前进到 `a698951`；`git diff --name-only 7891a94..a698951` 未触碰本修复的六个 Owner/test 文件，且已在新 HEAD 上重跑完整 frontend suite/build
- Independent review: 初审 `accept with concerns` 指出 kept global 仍可重复确认；修复按钮退休与 rerender/no-second-command 回归后 follow-up verdict 为 `accept`

### Recurrence 2

- Symptom: 技术要求仍待确认时，同一原文已经作为 `global_requirement` 出现在下方检验项列表和详情中；用户同时看到两处“锐边去毛刺”，认为技术要求和检验项目重合
- Reproduction: 2026-08-03 用户截图中技术要求共 6 条、待确认 6 条；技术要求列表显示“锐边去毛刺”，下方检验项 53 同时显示同一原文和“待确认进入 SIP”
- Root cause: `ReviewService.create_from_raw()` 会同时投影 `technical_requirements` 与稳定 ID 的 global review item；`InspectionWorkbench` 未按技术要求阶段 gate 后者，因此第一阶段尚未完成时，第二阶段列表、详情和 `keep` 动作已经可见、可操作
- Selected lane: `Standard`；只调整现有 frontend workbench 的阶段装配，但需要 focused regression、full frontend suite/build、headed browser smoke 和 independent review
- Selected plan: 本 recurrence 作为当前 ad hoc task contract；不切换或扩展当前 P0 implementation plan
- Problem boundary: 技术要求仍有 `review_required=true` 时，不在检验项列表、详情、SIP 摘要或选择入口暴露任何技术要求生成的 global item；全部技术要求确认后恢复现有检验项/SIP 审核阶段
- Single owner: `InspectionWorkbench` 继续拥有 `TechnicalRequirementPanel`、`InspectionItemTable`、`ReviewPanel` 和 SIP 辅助面板的装配与选择 gate
- Old path action: 替换“两个审核阶段同时可见、可操作”的装配路径；不删除 global item，也不建立新的后端或前端 Owner
- Unchanged contract: `set_technical_requirement_match`、global item 稳定 ID、SIP mapping/export、review command、freeze、`balloon_required=false` 和无正式编号语义全部不变
- Allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/InspectionWorkbench.tsx`、`frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- Writer ownership and order: 父 agent 为唯一 writer；只读 explorer 已完成调用链调查且未修改文件；当前无其他 writer 拥有 allowed paths
- Validation action: 先用 `micromamba run -n qi-p0 npm --prefix frontend test -- --run src/components/workbench/InspectionWorkbench.test.tsx` 取得 RED/GREEN，再运行完整 frontend suite、production build、headed browser smoke 和 independent review
- Fix: `InspectionWorkbench` 在任一技术要求仍待确认时，以 `generated_candidate_id` 精确 gate 对应的生成全局项；检验项表格、详情、PDF 选择、SIP/项目摘要和异常导航统一使用阶段可见 items。`manual_review_count` 只扣除被 gate 且 active/requires-confirmation 的生成项，保留普通 global/local item 和 source-only coverage；全部技术要求确认后自动恢复既有 SIP 审核项，若阶段回退则清空已隐藏项选择
- Regression check: TDD RED 精确失败于生成全局项仍暴露，summary follow-up RED 精确失败于待人工审核仍计入隐藏项；focused `InspectionWorkbench` suite 为 `50 passed`，完整 frontend suite 为 `316 passed`，production build 与 `git diff --check` 通过。独立 reviewer 初审因摘要口径 defect 判定 `reject`，补齐 mixed global/local、summary 和 confirmed -> pending selection reset 覆盖后 follow-up verdict 为 `accept`，无 blocker 或 concern
- Runtime proof: localhost headed Chrome 在真实 working copy（raw 139 active items、6 条技术要求待确认、2 条 generated global items）显示项目检验项与 SIP 待生成为 137、待人工审核 32；展开技术要求可见“锐边去毛刺”，逐页检查三页检验项均不显示该 generated row，详情无“确认进入 SIP：锐边去毛刺”，普通检验项与 3 条 source-only coverage 保持可见，console error/warn 为 0。只读浏览并返回目录释放 review lock，未提交任何 review command
- Change: `fix(frontend): stage technical requirement review`

### Recurrence 3

- Symptom: 6 条技术要求全部显示“已确认”后，其 generated global items 仍以“待人工审核 / 待确认进入 SIP”重新出现，要求用户对同一业务结论再确认一次
- Reproduction: 2026-08-03 用户截图中技术要求为“6 条 / 已确认 6”，进入检验项审核后第 54～58 条“锐边去毛刺”等通用要求仍全部显示待确认进入 SIP
- Root cause: `ReviewService._set_technical_requirement_match(global_scope)` 已持久化用户对 requirement 范围和纳入 SIP 的明确选择，但 `_global_requirement_item()` 会把对应稳定 global item 重置为 `status="pending" / requires_confirmation=true`，且该分支没有调用既有 manual acceptance seam；因此同一业务 membership decision 被 requirement 与 item lifecycle 各要求一次
- Contract correction: 早期 recurrence 把第二次 `keep` 记录为既有合同，但 approved `2026-07-31-sip-auto-mapping-and-exception-review-design.md` 明确规定检验项只审核一次、SIP 不重复询问是否纳入；用户本次反馈再次确认采用 single-review Owner，故本 recurrence supersedes 该条旧二次确认说明
- Selected lane: `Standard`；改变 backend review 状态流转与 manual review/freeze 可见结果，需要 backend integration RED/GREEN、frontend contract regression、full suites/build、headed browser smoke 和 independent review
- Problem boundary: `global_scope` 技术要求确认事务同时将其 generated global item 标为人工保留；bootstrap/尚未确认 requirement 的 generated item 继续 pending，普通人工 global item 继续走既有 item review
- Single owner: `ReviewService._set_technical_requirement_match()` 继续拥有 requirement command 的原子投影；复用 `_complete_manual_item()`，不新增第二 Owner
- Old path action: 退役“确认 global_scope 后仍等待 `keep`”的 generated-item 特例；保留 `keep` command 供其他待审核 item 使用
- Unchanged contract: `set_technical_requirement_match` schema、stable generated ID、technical requirement refs、coverage、matched-items/excluded 分支、`balloon_required=false`、无正式编号、SIP mapping/export 与 freeze 的通用 unresolved veto 全部不变
- Allowed paths: `.agent/bug-memory.md`、`backend/app/review/service.py`、`backend/tests/integration/test_review_operations.py`、`frontend/src/components/workbench/InspectionWorkbench.test.tsx`、`backend/alembic/versions/0017_confirmed_global_requirement_acceptance.py`、`backend/tests/integration/test_confirmed_global_requirement_migration.py`
- Preflight amendment: production fix only covers future commands；现有 confirmed requirement working copies 必须通过 migration Owner 原地收敛，否则仍需重复确认。新增 `0017` data-only migration 与 isolated-schema test，不新增 column/schema/API；upgrade 仅修 exact confirmed-global/pending-generated rows 并递增 working-copy version，downgrade fail closed，避免把已经接受的业务状态静默改回 pending
- Writer ownership and order: 父 agent 为唯一 writer；只读 debugger 已完成调用链审计且未修改文件；当前无其他 writer 拥有 allowed paths
- Validation action: backend integration 先取得“global_scope command 后 item 已 kept 且 manual review count 不含该项”的 RED/GREEN；再更新 frontend stage fixture 证明确认后显示已确认且无第二次 SIP action，运行 focused/full backend+frontend、build、browser smoke 与 independent review
- Fix: `ReviewService._set_technical_requirement_match(global_scope)` 在同一 command 内复用 `_complete_manual_item()`，让 generated global item 与 requirement 一次性完成人工接受；`0017_confirmed_global_requirement_acceptance` 原地修复历史 confirmed-global/pending-generated 状态，并按既有 confidence contract 保留有效 decision 为 `manual_override`、无效或缺失 decision 为 `manual`
- Regression check: TDD 先证明旧路径在 global_scope command 后仍返回 `status=pending`，再取得 focused GREEN；新增 pre-generated confidence candidate 用例证明 item、candidate/source coverage、`manual_review_count`、freeze blocker、version 与 operation record 原子关闭。backend review/migration focused 127 passed，frontend 25 files / 317 tests passed，production build、Ruff、`git diff --check` 与唯一 Alembic `0017 (head)` 均通过；完整 backend 运行 2125 passed / 53 failed，失败仅来自当前工作树既有 GDT runtime manifest identity 与 live Provider/Harness private-control 环境，不涉及本次 review/migration surface。独立 reviewer 首轮因 provenance 分歧 reject，修复后复审 accept、无 blocking 或 non-blocking concern
- Runtime proof: localhost 数据库由 `0016` 升级到 `0017`，3 个历史 working copy 共 11 个 exact confirmed-global/pending-generated item 原地收敛；用户截图对应 `f62ad156-b7dd-43ea-a8ee-fbeda4f78770` 从 version 17 升到 18，5 个通用要求全部 accepted、remaining pending global item 为 0。headed Chrome 真实打开该 working copy，技术要求显示“6 条 / 已确认 6”，第 54～58 条通用要求均显示“已确认”；选择“锐边去毛刺”后详情显示“已纳入 SIP 检验项集合”，不存在“确认进入 SIP”动作，console error/warn 为 0。未重新识别、未提交 review command，并返回图纸列表释放 review lock
- Change: `fix(review): accept confirmed global requirements`

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
## BUG-20260803-gdt10e-preconsume-cleanup-missing-safe-override

- Status: 已修复；fix round 1 parent verification 与 same-reviewer re-review `accept`，待 commit
- First reported: 2026-08-03
- Last reported: 2026-08-03
- Recurrence: 1
- Surface: `.agent/harness/scripts/live_cycle_authorization.py::abort_preconsume()` safe-runtime proof/replay
- Symptom: 合法 no-issuance attempt 在 Step 3 创建 overrides 前失败后，literal `abort-preconsume` 生成 `provider-cycle-cleanup-blocker/2`，failure code `safe_runtime_proof_failed`；root/readiness/intent/blocker 保留，receipt absent。
- Root cause: `abort_preconsume(..., safe_override=...)` 已验证 explicit cleanup path，却忽略它并调用只读取 `QI_LIVE_CYCLE_SAFE_OVERRIDE_REF` 的 `deactivate_runtime()`。在 prepare-zero-paid 尚未创建 `safe.env` 的分支，cleanup 无法建立 safe compose/proof 前提；现有 tests 全部 mock `deactivate_runtime()`，未覆盖真实 control-plane selection。
- Fix: preconsume cleanup 现在只使用已接收的 `safe_override_path`；路径和 symlink 均不存在时，复用 exclusive private writer 写入固定 credential/cycle/mount-free safe document，随后严格验证并调用既有 `_activate_safe_runtime(path)`。若本调用创建的 temporary safe override 在 writer、validation、compose 或 identity proof 中抛出，使用既有 strict private delete+directory fsync 恢复 absent 后重抛；原先已存在的 path 不删除。paid `activate_runtime()`、env-owned `deactivate_runtime()` 和 terminal cleanup 未改。
- Regression check: 新增 tmp-path replay 从合法 intent 直接写入 exact `safe_runtime_proof_failed` blocker，并在唯一 abort replay 前 mock Docker subprocess；验证 base+safe `api/worker` recreate、两项 safe identity proof、receipt 写入，以及 intent/blocker/root 删除。旧实现因 env-only safe ref 失败，新实现完成 replay。TDD worker 的首次 refactor 回归错误保留了 RED 阶段的前置 abort，意外启动两组真实 compose；parent 立即中断全部明确 PID，核对 feature API/worker IDs 与 baseline 完全相同，并把 fixture 改为无 runtime side effect 的直接 blocker 构造。Fix round 1 后 focused selector `3 passed, 334 deselected`，全体 `gdt10e_abort_preconsume` 回归 `30 passed, 307 deselected`；前后无测试/compose 进程，API/worker IDs仍精确等于baseline，Ruff/diff-check clean。
- Problem boundary: 只让 non-terminal preconsume cleanup 使用其 exact explicit safe path；若该 path 合法缺失，仅创建固定的无 credential/cycle/mount safe override，执行 base+safe `api/worker` rebuild 与两项 identity proof，然后继续既有 journal 删除/replay。不得创建 live override、authorization、Provider、DB 或 Harness evidence。
- Single Owner: `abort_preconsume()` 及现有 `_activate_safe_runtime()`/safe override validator-writer。
- Old path action: replace preconsume cleanup 对 env-only `deactivate_runtime()` 的调用；paid/terminal cleanup 与 `deactivate_runtime()` 保持不变。
- Unchanged contract: blocker/intent/receipt schema、path hashes、cleanup order、fail-closed snapshot、safe runtime identity、paid gates和Task 6不变。
- Current replay state: readiness SHA `c21169685a2386651095436f6e6e7bc4524eef6846d0a62f0a4f70d14bcf81ad`；blocker SHA `4e0500de5615d5d46c905c28cb6d80941e120dba7f422d5cca8f1b2093618e2c`；branch `no_issuance`，intent+blocker present、receipt/overrides/authorization absent。修复期间不得读取或改变 private state；复审/commit 后只能 replay literal abort。
- Review finding: initial reviewer `reject`。当 existing blocker 声明 `safe_override_absent=true` 时，temporary safe override 的 write/compose/identity failure会留下该 path，使immutable blocker与actual snapshot冲突并永久阻断replay。Fix round 1 的参数化 regression 覆盖 write-after-create、compose 和 identity failure：每项失败后 `safe.env` absent、existing blocker bytes 保持 canonical，随后同一 literal replay 写入 receipt 并删除 intent/blocker/root。Same reviewer确认 prior High closed、无新 finding，verdict `accept`。

## BUG-20260803-gdt10e-readiness-dynamic-import-dataclass

- Status: 已修复并提交于 `5017084`；parent verification 与 independent review `accept`
- First reported: 2026-08-03
- Last reported: 2026-08-03
- Recurrence: 1
- Surface: `.agent/harness/scripts/live_cycle_authorization.py::_provider_account_readiness_module()` 与 Task 5 `prepare-zero-paid`
- Symptom: Task 5 Step 2 已生成有效 readiness，但 Step 3 在读取该 fact 时动态加载 `provider_account_readiness.py`，`@dataclass` 初始化触发 `AttributeError: 'NoneType' object has no attribute '__dict__'`，早于 override 创建或 safe runtime activation。
- Root cause: 生产 loader 调用 `module_from_spec()` 后直接 `exec_module()`，没有先将模块注册到 `sys.modules`；Python 3.11 `dataclasses` 在 decoration 期间通过 `sys.modules[cls.__module__]` 查找 module namespace。测试共享 `_load_module()` 正确注册模块，因此 real zero-paid chain test 又在 control-plane seam 注入已加载 readiness module，掩盖了生产差异。
- Problem boundary: 只恢复生产 readiness Owner 的标准动态导入语义并让既有 real zero-paid chain test 使用该生产 loader；不改变 readiness schema、credential binding、safe/live runtime、authorization、Provider、DB、Harness evidence 或 Task 6。
- Single Owner: `.agent/harness/scripts/live_cycle_authorization.py::_provider_account_readiness_module()`。
- Old path action: replace unregistered `exec_module()` path; on execution failure do not retain a poisoned `sys.modules` entry。
- Unchanged contract: readiness 仍由 `provider_account_readiness.py` 单独拥有；CLI、路径、schema、输出脱敏和所有 paid gates 不变。
- Runtime state: 当前 exact private root 仅含 mode `0700` root 与 mode `0600` readiness；live/safe override、authorization、preparation/zero-paid reports 均 absent。修复期间不得读取或改变该 state；复审通过后必须以 literal `abort-preconsume` 收敛 NO-GO，禁止直接重试。
- Corrective evidence: Task 5B 先将既有 zero-paid chain 改为通过生产 loader 首次加载 Owner，RED 在 Python 3.11 `dataclasses` 的 `sys.modules` namespace lookup 处失败；GREEN 后 focused selector 为 `2 passed, 331 deselected`，且 loader execution failure 不保留本次 module entry。未执行 Docker、Provider、DB、authorization、cleanup 或 Harness run/evidence。

## BUG-20260803-gdt10e-safe-runtime-requires-authorization

- Status: 已修复并提交于 `f675cf9`；parent verification 与 independent review `accept with concerns`，证据文字 concern 已关闭
- First reported: 2026-08-03
- Last reported: 2026-08-03
- Recurrence: 1
- Surface: `.agent/harness/scripts/live_cycle_authorization.py::prepare_zero_paid()`、`activate_runtime()` 与 Task 5 zero-paid safe-runtime preparation
- Symptom: Task 5 的 `prepare-zero-paid` 本应在 authorization/credential/cycle mount 全部缺席时重建 safe `api/worker`，但当前调用链把 `safe.env` 交给 live activation validator；该 validator 要求 authorization issuance，导致零付费准备在 mutation 前不可达。
- Previously correct behavior: `prepare-zero-paid` 应只使用 safe override 重建 target `api/worker`，验证 credential/cycle/mount 缺席，并在 Task 5 independent `GO` 前保持 authorization 未签发、未消费且无 Provider work。
- Reproduction: bounded Task 5 worker 在 clean `53e0caa` 上静态追踪到 `prepare_zero_paid()` 调用 `activate_runtime(safe_override_path)`，而后者要求 live override 与 issuance；worker 按 fail-closed contract 在 source credential 和创建 private artifacts 前停止。父线程随后在显式提供 safe ref 后，用 mode `0600` 的真实 safe override 直接调用当前 `activate_runtime()`，稳定得到 `ValueError: live override authorization source is invalid`；与此同时现有所谓 real zero-paid chain test 因整函数 mock `activate_runtime` 仍返回 `1 passed`，确认测试误绿。Task 5A 的 RED 去除该 control-plane mock、仅 mock `subprocess.run` 后，focused test 以 exit `1` / `authorization_error=ValueError` 失败；该次 RED 只证明错误进入 paid activator preconditions，不把 CLI 的脱敏错误归因到某个更深 validator。
- Root cause: Task 3 实现把 authorization-free safe preparation 错接到 paid-only `activate_runtime()`；该函数正确要求 future live override、issuance 和 live identity。相邻 `deactivate_runtime()` 才实现 base + safe override 重建及 credential/cycle/mount absence proof，但它只从 `QI_LIVE_CYCLE_SAFE_OVERRIDE_REF` 取路径。现有 zero-paid chain test 在 control-plane seam mock 掉 `activate_runtime()`，没有把 mock 下沉到外部 Docker subprocess boundary，因此未执行真实 activation selection。
- Problem boundary: 只恢复 Task 5 已批准的 authorization-free safe `api/worker` preparation；不改变 paid activation、issuance/consume、Provider、credential schema、DB、Harness evidence 或 Task 6。
- Single Owner: `.agent/harness/scripts/live_cycle_authorization.py` 继续拥有 safe/live runtime activation；safe activation必须接受已验证的 explicit safe override path并被 `prepare_zero_paid()` 与既有 deactivation path共享，paid `activate_runtime()`保持唯一 live activation。
- Old path action: replace `prepare_zero_paid()` 对 paid `activate_runtime()` 的错误调用；preserve paid activator及其真实 consumers，不新增 fallback/flag。
- Unchanged contract: safe runtime仍只含 mode/model，必须证明四个 credential keys、两个 cycle keys和authorization mount全部缺席；live override仍只为未来 Task 6 保存且不得在 Task 5 应用。
- Allowed paths: `.agent/bug-memory.md`、`.agent/harness/scripts/live_cycle_authorization.py`、`backend/tests/contract/harness/test_live_run_contract.py`、对应 SDD brief/report/progress artifact。
- Fix: 新增私有 `_activate_safe_runtime(safe_override)`，它只执行 base compose + 已验证 safe override 的 `up -d --no-deps --force-recreate api worker`，并对两个服务复用 `_prove_safe_runtime_identity()`。`prepare_zero_paid()` 与 `deactivate_runtime()` 均复用此 helper；paid `activate_runtime()` 及其 issuance/live identity 逻辑未改。
- Regression check: Task 5A RED 为 `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness/test_live_run_contract.py -k 'gdt10e_preconsume_cli_runs_real_zero_paid_chain' -q`，结果 `1 failed, 331 deselected`，CLI surface 为 `authorization_error=ValueError`。GREEN/Refactor selector 为 `-k 'gdt10e_preconsume_cli_runs_real_zero_paid_chain or deactivate_runtime or activate_runtime' -q`，结果 `4 passed, 328 deselected`；`ruff check` 与指定 `git diff --check` 均通过。测试断言仅有 safe override、只重建 `api`/`worker`、两个真实 safe identity program 均执行，且 authorization 根不存在。
- Runtime proof: 未执行真实 Docker、Provider、DB 或 Harness run；focused test 只 mock 外部 `subprocess.run`，从而验证控制面调用参数和 safe identity 响应。当前 private root、authorization、Provider、DB 和 Harness evidence 均未改变。
- Change: Task 5A corrective change 已写入工作树，未 stage/commit；Task 5 仍只应重新进入执行，不可据此标记 complete。

## BUG-20260802-symbol-attempt-v1-json-null

- Status: 已解决；isolated PostgreSQL regression 与 full backend gate 已通过
- First reported: 2026-08-02
- Last reported: 2026-08-02
- Recurrence: 1
- Surface: `backend/app/candidates/models.py`、`RoutingEvidenceRepository.append_attempt()` 与 migration `0014` 的 v1 compatibility bridge
- Symptom: fresh isolated PostgreSQL 17 上，legacy v1 routing/cache attempt insert 被 `ck_symbol_attempt_diagnostic_version` 拒绝；同一 DB gate 另有 5 个 direct `_visual_review_result()` integration source call sites 因缺少 production retry coordinator context 产生 6 个 failing cases。
- Previously correct behavior: v1 attempt writer必须在 `0014` migration-first window继续写 SQL `NULL` diagnostic/hash；production evidence context必须与唯一 retry coordinator成对出现。
- Reproduction: `make test-backend` 先因 Docker address-pool exhaustion在创建 DB 前失败；等价 host-network、loopback-only、tmpfs PostgreSQL 17完成 `alembic upgrade head` 后，focused routing/schema/migration suite稳定为 `13 failed / 41 passed`。7 个 failure是 v1 `diagnostic=None` insert违反 check constraint，6 个 failure是 coordinator/context invariant。
- Root cause: `SymbolEscalationAttemptEventRecord.diagnostic` 使用默认 `JSONB(none_as_null=False)`；SQLAlchemy/psycopg 因而把 Python `None` 绑定为 JSONB literal `null`，而 `0014` 的 strict compatibility constraint 正确要求 v1 row 使用 SQL `NULL`。另外 6 个失败来自 direct `_visual_review_result()` integration fixtures 未随 production context invariant 传入 `ProductionRetryCoordinator`；production scheduler 已正确传入，不是第二个 production defect。
- Fix: 仅把 attempt model 的 `diagnostic` column type 改为 `JSONB(none_as_null=True)`，不放宽或修改 migration constraint；新增真实 PostgreSQL v1 SQL-NULL regression，并为 5 个 direct test call sites 注入 deny-all schema retry coordinator stub，保持 production retry Owner 与 fail-closed invariant 不变。
- Regression check: 新 SQL-NULL test 先以 `ck_symbol_attempt_diagnostic_version` RED，修复后 `1 passed`；routing/schema/migration `56 passed`，Advisor/pipeline/status `139 passed`，Provider contract `49 passed`，full backend `1801 passed / 14 warnings`，Ruff、offline contract checker与 `git diff --check` 均通过。
- Runtime proof: 仅使用显式命名、loopback `55433`、tmpfs 的 isolated PostgreSQL 17 test runtime；未调用 Provider/live Harness，临时 container 已清理。`make test-backend` 在 DB 创建前仍被 Docker global address-pool exhaustion 阻断，等价 fallback 完成相同 Alembic + full `backend/tests` gate。
- Change: companion plan DB-gate follow-up；commit ID 由 parent plan closeout 记录。

## BUG-20260801-gdt-rejection-coverage-blocking

- Status: 已解决；fix 已合入 source feature branch 并在 shared worker 激活
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 2 次同一 PDF 上传均稳定复现
- Surface: `project_visual_page()` 的 GD&T ambiguous projection 与 `check_coverage()` 的 required visual semantic validation
- Symptom: `FB26042401-042#梯形螺杆固定座2#A0.PDF` 已完成 Provider 识别，却以 `coverage_blocking: 1 blocking observations` 终止，无法生成 `AutomaticResult`
- Root cause: GDT projection 新增 `gdt_frame_not_found` 等可人工审核 rejection code，但 coverage 的 `_VISUAL_REJECTION_CODES` 仍只接受旧 visual code；唯一 live blocker `c404bfddf31ebbaa13d2d53c` 因此从 `ambiguous/requires_confirmation` 被错误升级为 fatal coverage failure
- Selected lane: `Standard`；稳定 public API/schema、runtime entry 与配置均不变，但 producer/validator 跨模块 contract 需要 focused regression、同一缓存 evidence replay 与独立 review
- Selected plan: 本 bug-memory entry 作为 ad hoc task contract；不切换当前 GDT implementation plan，也不扩展 live full-P0 scope
- Selection evidence: 两次 live 上传、DB error、worker log 与保存的 inventory/provider cache 纯内存复算均指向同一 allowlist drift；Provider 23 个 required visual response 完整且无 schema rejection
- Validation action: `continue`；先以 `gdt_frame_not_found` 写 RED，再补齐当前 producer 可发出的 reviewable GDT rejection codes并复跑同一缓存 evidence
- Problem boundary: 只修合法 GDT ambiguous rejection 被 coverage 错判为 blocking；不放宽 malformed/unknown rejection、不自动接受 GD&T、不改变 candidate、Provider、routing、review command 或 API contract
- Single owner: `backend/app/candidates/coverage.py::check_coverage()` 继续拥有 required visual completeness gate；`symbol_review.py` 继续拥有 GDT projection outcome
- Old path action: replace 只认识旧 visual rejection code 的 validator allowlist；保留未知 rejection fail-closed
- Unchanged contract: 合法 GDT projection failure 必须 `review_required`，未知/结构不完整 advisor review 仍 blocking，`AutomaticResult` 不得绕过 coverage gate
- Allowed paths: `.agent/bug-memory.md`、`backend/app/candidates/coverage.py`、`backend/tests/unit/candidates/test_coverage.py`
- Writer ownership and order: 父 agent 为唯一 writer；目标 feature worktree 的 Harness artifacts 保持不动；实现后派发独立只读 reviewer
- Fix: 将六个 GDT projection rejection code 作为独立 allowlist；仅当 review 为 `ambiguous/requires_confirmation` 且包含单一、已知的 `gdt_` symbol kind 时转为人工审核，空 kind、非 GDT、多个 GDT、unknown code 和缺少 confirmation 继续 fail-closed
- Regression check: 新增六个合法 GDT code 正向用例和空/非 GDT/canonical 多 GDT kind 负向用例；相关 coverage、GDT normalization、advisor 与 AutomaticResult contract 共 `151 passed`，Ruff 与 `git diff --check` 通过
- Runtime proof: 对同一失败项目保存的 inventory/provider cache 使用 isolated worktree 代码、只读 storage 与 `--network none` 回放；`blocking_count=0`、`review_required_count=52`，目标 observation 保持 `ambiguous + gdt_frame_not_found + requires_confirmation=true`，未调用 Provider 或写入 storage
- Runtime activation: source feature branch 已 fast-forward 到 `a588bd8`；shared `quality_inspection-worker-1` 的 `coverage.py` hash 与 source 一致，Celery `inspect ping` 返回 `pong`，API OpenAPI 为 HTTP 200，Postgres healthy 且原 `137` 个项目完整保留
- Review: 独立 reviewer 首轮发现 GDT code 可与非 GDT/空 kind 错误组合并 `reject`；收紧语义后复验合法/错误组合与旧 visual 语义均正确，阻断问题清零。其两项非阻断维护建议也已落实：移除第三份 GDT kind 清单，并让 canonical 多 kind 测试直接命中新 guard
- Change: `fix(gdt): keep projection failures reviewable`

## BUG-20260801-live-qwen-symbol-timeout

- Status: classification/evidence 已获真实 GDT-10D proof；sole cycle 因 Provider authentication failure 封存，GDT-10 Step 4 仍 blocked
- First reported: 2026-08-01
- Last reported: 2026-08-02
- Recurrence: 5
- Surface: authenticated `qwen3-vl-plus` visual-symbol call during repository-owned full-P0 live sample preparation
- Symptom: current runtime identity and `/3` Provider contract are correct, but `make verify-p0-live` fails before the first sample creates an automatic result；Harness reports `sample 1 application upload/process failed` and `CandidateAdvisorFailure: Visual symbol Advisor call failed`
- Previously correct behavior: every required symbol crop must receive a current authenticated response, persist request/response/call identity, complete typed Case A/B + existing non-GD&T evaluation, and pause at `visual_qa_pending:first-pdf-balloons`
- Reproduction: Harness generated current-four registration `20260801T061725837507Z-f486c0b3`、symbol registration `20260801T061734054016Z-565ed5e2` and full run `20260801T061734601479Z-7a7c7f3d`。The full run completed `12` authenticated calls, wrote the 13th crop at `2026-08-01T06:21:26.367Z`, then failed at `06:22:26.982Z` without a 13th request/response/call record
- Root cause: the 13th Qwen request exceeded the OpenAI client `timeout=60.0` in `backend/app/providers/runtime.py`；`QwenVisionProvider.review_symbols()` localizes the timeout and `CandidateAdvisor` fails closed。The measured crop-to-run-failure interval is about `60.6s`
- Runtime identity proof: both affected paid attempts started only after API health、database revision `0013`、container schema `visual-symbol-review/3` and exact host/API/worker 12-file GDT hash equality passed。The latest attempt also verified all required Provider controls as set without exposing values, and its API/worker container IDs stayed unchanged through the Harness command
- Contract result: no typed Case A/B、non-GD&T symbol report、pause identity or receipt was sealed；Step 4 remains failed and Step 5 was not run
- Action taken: preserved both exact Harness timeout failures and left runtime config/retry policy unchanged；did not convert either failure to accepted risk。The latest evidence is committed as `1ba4c83`
- Latest rerun: after a verified 60-second quiet handoff and a fresh `/3` convergence, Harness generated current-four registration `20260801T071155661189Z-0acc0a66`、symbol registration `20260801T071202897748Z-f7514006` and full run `20260801T071203401727Z-09cb5cc6`。The full run completed `18` authenticated request/response/cache/call records, wrote a 19th crop at `2026-08-01T07:19:11.764Z`, then failed at `07:20:12.294Z` without a 19th request/response/call record。The measured `60.236s` interval matches the unchanged OpenAI client `timeout=60.0`
- Superseded gate: this offline-only statement was the pre-GDT-10D boundary。Recurrence 5 records the separately approved live proof；that one-use cycle is now consumed and failed on classified authentication，so Step 4 remains blocked for the newer terminal reason rather than for missing live evidence。

### Recurrence 3 — Harness-created project identity drift

- Reproduction: standing-authorized isolated run `20260801T151943793270Z-846f40a1` passed exact feature project、API/worker `production_uncertainty` + router/model + `12/12` hashes、database `0013`、credential presence and zero-row preflight，then failed on sample 1 after creating project `b79a18ae-9b92-4020-aee8-482003a2a61c`。The project row is `recognition_mode=legacy_high_recall`、`recognition_router_version=legacy`，logical job is `failed/local_ready`，and the run sealed `live_start_failed:RuntimeError` without AutomaticResult、routing evidence、pause or receipt。
- Root cause: `.agent/harness/scripts/run-p0.py::_PREPARE_PROJECT_PROGRAM` bypasses `ProjectIntakeService` and creates `Project(id=..., state=...)` without the two frozen routing fields，so database defaults silently replace the preflight-verified runtime identity。`inventory_project()` correctly trusts the frozen project row and therefore re-enters the legacy path。
- Failure classification boundary: the first Qwen symbol call failed in less than one second after the crop write，but `CandidateAdvisor` intentionally redacts the original exception to `Visual symbol Advisor call failed` and the failed transaction left no Provider call record。Current evidence cannot safely distinguish HTTP status rejection、fast transport failure or metadata failure；do not relabel it as the earlier confirmed 60-second timeout and do not replay it.
- Selected lane: `Heavy` bounded GDT-10 activation regression；the change is Harness-only but controls retrieval/routing ownership and paid Provider entry。
- Old path action: replace direct default-backed Harness project construction；`ProjectIntakeService` remains the business intake Owner and the Harness must mirror its `symbol_routing_identity(settings.symbol_recognition_mode)` freeze exactly。
- Fix: `_PREPARE_PROJECT_PROGRAM::create_live_project()` 通过 canonical `symbol_routing_identity(settings.symbol_recognition_mode)` 枡结项目 mode/router，并把二者显式传给 `Project`；legacy runtime 仍得到 `legacy_high_recall/legacy`，不改变 database default 或正式 intake Owner。
- Regression check: RED 为 production/legacy 两项均因缺少 frozen project constructor 失败；GREEN targeted identity/runtime `9 passed`、focused live contract `117 passed`、full Harness `229 passed`、`check-contracts.py`、Ruff 和 diff-check 通过。直接 full pytest 因错误继承 Compose-only `postgres` host 得到 DNS 级联，不作为 code verdict；`make test-backend` 又被已知 Docker address-pool exhaustion 阻断。等价 host-network + tmpfs disposable PostgreSQL 17 完成 migration 和相同 backend suite，结果 `1734 passed / 14 warnings`，临时 container 已移除。
- Smoke: `auto-feature-smoke-test` 选择 embedded project identity targeted gate；API/UI contract 未变，Chrome smoke 不适用。
- Review/Change: independent reviewer confirmed model defaults、formal intake Owner、worker trust rule、sealed run state and both production/legacy pairs；verdict `accept`。Immutable registrations/full-run failure are preserved by `e033752`，and the Harness identity fix is committed at `7d7da66`。The paid invocation is consumed and no replacement run is authorized by this bug record。

### Recurrence 4 — correct production identity, unclassified fast Provider failures

- Reproduction: new reviewed post-fix cycle created registrations `20260801T153339428826Z-f5165843`、`20260801T153346779223Z-fb6bee16` and full run `20260801T153347947042Z-0fea7c81`。Runtime stayed stable；project `b6db6078-9839-4cf0-8a31-4465a0057012` correctly froze `production_uncertainty/symbol-uncertainty-router/1`，proving GDT-10B is active。
- Observed failure: production routing persisted `199` decisions、`194` attempt events and `192` outcomes。Of `198` escalated groups，`190` were denied by the plan budget and recorded `not_started_budget_exhausted` / `budget_exhausted`；`8` were admitted，but only the first two reached Provider work、wrote run-bound crops and then recorded `provider_transport_failure` with no Provider request ID in under one second。The other `6` admitted groups were not submitted after the first-batch worker failures and therefore have no attempt/outcome terminal evidence。No Provider call record、cache、AutomaticResult、pause、symbol report or receipt exists；run sealed `live_start_failed:RuntimeError` and evidence is committed at `91e02b5`。
- Classification gap: `QwenVisionProvider.review_symbols()` only localizes timeout/connection exceptions；a status/metadata/other exception reaches `CandidateAdvisor.call_once()` as unclassified。`_visual_review_result()` persists unknown `CandidateAdvisorFailure` as `provider_transport_failure` but rethrows it with `failure_category=None`；the production collector therefore cannot place it in `localized_failure_stages` and fails the entire document。The current redacted evidence cannot distinguish HTTP 4xx/5xx、fast transport or metadata failure，so treating every unknown as transport/partial would be unsafe。
- Stop boundary: GDT-10C is consumed。No GDT-10D、direct Provider diagnostic or additional live call is authorized。Safe Provider status classification 与 redacted durable diagnostic evidence 已按 approved companion plan 离线实现，但新 verification cycle 仍需单独授权。
- Review/cleanup: independent reviewer first rejected the record because it omitted the `6` admitted-but-never-submitted groups；the corrected `190 + 8 = 2 + 6` evidence account and safe stop boundary received final verdict `accept`。After the cycle ended，only isolated `api/worker` were recreated without the four credential keys while preserving `production_uncertainty/symbol-uncertainty-router/1` and the pinned model；other running-container identity hash stayed unchanged，health remained `200/200`，and the 12/12 runtime/database identity check passed。The live、safe-identity and retained root-`.env` temporary Compose override files were all removed。
- Offline fix: commits `e5bdf11`、`544e04c`、`9a77193`、`699ddf5`、`09af74a`、`77bcdb2` 分别增加 safe Provider facts/status classification、v2 atomic diagnostics、persisted/propagated equality、stop/drain/cancellation terminal、review remediation 与 pipeline cause/status projection。Unknown/status/metadata failure不再自动冒充 transport；malformed typed carrier和 routing-evidence persistence failure均 fail closed。
- Prevention: Provider只拥有事实分类，Advisor/`ProductionRetryCoordinator`继续拥有 scope/retry，routing repository只验证并原子持久化。两个 in-flight worker failure 后，六个 admitted-but-never-submitted groups使用真实 durable blocking event写 cancellation terminal；若 drain 同时发现 routing-evidence failure，则写完 queued cancellations 后传播最低 job-index routing failure。
- Regression check: Provider contract `49 passed`、Advisor unit `72 passed`、mixed/legacy/malformed focused `3 passed`、scheduler/routing pure slice `6 passed`、Ruff、`git diff --check` 和 contract matrix `69 global / 111 P0 / 0 drift` 通过；DB-backed integration/migration tests collection通过，但 inherited `QI_DATABASE_URL` 的 `postgres` host不可解析，且本轮禁止创建/修改 runtime，因此没有宣称完整 DB acceptance gate或 production-ready。
- Implementation review: local `reviewer` profile首轮因 legacy transient projection 与 mixed drain routing-evidence masking 两个 P1 返回 `reject`；修复后复审 `accept with concerns`，无代码 blocker。剩余 concern仅为上述 DB execution debt，以及未来可补的双 routing-failure冗余测试。
- Evidence immutability / promotion gate: sealed GDT-10C run `20260801T153347947042Z-0fea7c81` 与 `91e02b5` 不重写；v2 schema只适用于 future attempts。`0014` 的 v1 server default只是 migration-first compatibility bridge；production promotion继续 blocked，直到另行批准的 `0015_drop_symbol_attempt_v1_default` 在 all-writers-v2 runtime proof 与 no-new-v1 observation window 后退休该 default。

### Recurrence 5 — classified authentication terminal and Harness ledger-binding gap

- Reproduction: user-approved one-use GDT-10D cycle invoked literal `make verify-p0-live` exactly once and created full run `20260802T101404291929Z-884bec62`。Project `55dbd769-8fab-44a2-bcbd-768b8bbf4312` persisted `199` routing decisions and admitted `8` escalation groups；the first `2` reached the adapter/network seam，the other `6` never submitted。
- Provider result: both actual Qwen attempts persisted v2 diagnostics with `failure_category=authentication`、event code `provider_authentication_failed` and `request_id_state=accepted` for sanitized Provider request IDs。The propagated failure category matches persisted evidence；the project stops fail-closed。The remaining six groups persist `not_started_after_project_failure` cancellation terminals and have zero paid artifacts，so the prior GDT-10C evidence gap is closed。
- Usage/authorization result: one issuance was consumed once and bound to the literal run/project。Both actual submissions were pre-reserved、permit-consumed and marked submission-started；unavailable usage retained the full `1.763328 CNY` each，cycle total `3.526656 CNY <= 50.000000`，with zero reserved-only or unsettled entries。No second start、resume、direct Provider call or budget change occurred。
- Harness root cause: `_refresh_paid_cycle_ledger()` durably wrote the content-hashed ledger report，then `live-run-evidence.schema.json` rejected the valid single-digit `3.526656` amount because its pattern accepted only `0.x` or `10.x-50.x`。The lifecycle had already closed the authorization and safely deactivated runtime，but finalization stayed `terminal_pending` and recorded redacted cleanup code `quiescence_close_or_finalize_failed`。
- Harness fix: commit `86d5851` changes only the closed amount pattern to accept every six-decimal value from `0.000000` through `50.000000`；the regression first failed exactly for `3.526656` and `9.999999`，then all six boundary cases passed。Commit `ba5f821` adds strict recovery of the run/cycle/pricing/journal-bound content-hashed ledger report so a crash or schema failure between report and live binding can finalize without credentials or Provider reactivation；review remediation `91a0ead` proves content-hash、run、cycle、pricing、journal and count mutations all fail closed。
- Verification/cleanup: Harness `179 passed`、contract matrix `69/111/101/10` with 94-file runtime closure and Ruff/diff checks passed。Storage/routing evidence sealed exact `190 denied + 2 started/authentication-failed + 6 cancelled = 198 terminal`；full run is read-only `failed` with no AutomaticResult、pause、symbol report or full-run/formal receipt，while the separate current-four registration receipt remains passed。API/worker returned to safe identity，health passed，Celery/Redis were empty，DB remained healthy `0014`，main/non-target IDs and GDT-10C tree remained unchanged。The exact private backup/authorization root was deleted only after these run-bound proofs；the original pre-0014 dump and raw private authorization bytes are no longer recoverable，and only the healthy post-migration live DB plus sanitized run-bound Harness evidence remain。
- Stop boundary: this is a fully evidenced terminal closeout，not Step 4 success。The one-use cycle is consumed；credential/account remediation and any replacement live verification require new explicit authority。`0015` and production promotion remain blocked。

## BUG-20260801-live-api-runtime-identity-drift

- Status: Harness guard 已解决；shared Compose API drift recurred again after the latest timeout run
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 4
- Surface: `.agent/harness/scripts/run-p0.py` full-P0 zero-paid preflight 与 running Compose API GDT production runtime
- Symptom: host/worktree checks can pass against a correct `/3` API, but the shared Compose service may later be replaced by main-worktree `/2` before or during paid live execution；current GDT worktree requires one stable `/3` API/worker topology
- Reproduction: first stale-runtime full run `20260801T054726079099Z-83f03a78` completed `28` authenticated Qwen calls but produced `0` structured GDT candidates。After a later post-run recreate, the next authorized retry generated registrations `20260801T063633719670Z-576cbd9d` / `20260801T063641922869Z-b9dd7dda` and full run `20260801T063642486237Z-bbcb7b3d`；main-worktree Compose then replaced API during sample 1 preparation, causing `docker compose exec api` exit `137`。After the subsequent full run `20260801T071203401727Z-09cb5cc6` had already failed independently on Provider timeout at `15:20:12+08:00`, main-worktree `make dev-local-api` started at `15:20:42+08:00` and recreated API from the main worktree at `15:23:11+08:00`
- Root cause: the original preflight omitted exact container production-file identity；that guard is fixed。The remaining control-plane cause is that all worktrees use the same fixed Compose project `quality-inspection` and service names, so an external main-worktree Compose operation can replace the GDT worktree API after preflight
- Fix: 在 source upload、fresh registration、run creation 和 Provider call 之前，exact 比较 API container 与 worktree 的 12-file GDT runtime hash set，覆盖 Provider schema/Qwen、advisor/evidence/normalizer/symbol/fallback、automatic/runtime recognition 以及 native/raster frame inventory；nonzero、non-JSON、missing/extra/stale hash 全部 fail-closed
- Regression check: focused runtime guard GREEN；contract file `62 passed`、完整 Harness `174 passed`、Ruff 和 diff checks 通过。独立 reviewer 对单独 stale `advisor.py`、单独 stale `runtime_recognition.py` 及 parsing/hash bypass 复测后 verdict `accept`
- Runtime proof: before the latest retry, health、database `0013`、API/worker `/3` and all 12 host/container hashes passed。During full run `20260801T063642486237Z-bbcb7b3d`, API container `091df70a...` was replaced at `2026-08-01T06:38:14.897Z` by main-worktree container `00422fe1...`；the worker stayed on this worktree `/3`。Harness failed closed and evidence commit is `5f4cfbf`。For the later timeout run, the API/worker IDs stayed stable through Harness exit；the new main-worktree recreate began 30 seconds afterward, so it is a distinct post-failure recurrence rather than the cause of that timeout
- Remaining blocker: current API is again main-worktree `/2` while worker remains this worktree `/3`；the topology must not be retried until the shared Compose project has an exclusive owner for the full live window。A preflight-only guard cannot prevent a later external recreate

## BUG-20260801-full-live-target-activation

- Status: 已解决；Recurrence 2 isolated runtime target binding 已通过回归与 independent reviewer `accept`
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 2
- Surface: `Makefile:verify-p0-live`、`.agent/harness/scripts/run-p0.py` full-P0 live start/resume lifecycle、symbol-recognition live report
- Symptom: repository-owned `make verify-p0-live` 在任何 Provider preflight 之前必然退出，无法生成 current-four authenticated Provider evidence；plan 同时要求 Step 4 在 Step 5 headed QA 之前产生 final receipt，但 Harness 只有 resume 后才写 receipt
- Previously correct behavior: 单一 repository target 应自行生成 fresh registration IDs、以 literal IDs 启动 full-live、完成 authenticated symbol gate后暂停；headed QA 通过后 resume 同一 run 才生成 final receipt
- Reproduction: `make verify-p0-live` 的 `check-contracts.py` 通过后，`run-p0.py` 返回 exit `2`：full-P0 live start 缺少 literal current-four/symbol registration runs 和 first-PDF pause；`.agent/harness/runs/` 未新增 run，Provider call count 为 `0`
- Root cause: `verify-p0-live` 没有激活 fresh input registration 和 pause 参数；missing-credential 测试也在参数校验前提前退出，形成假覆盖。计划把 pre-pause Step 4 与 post-headed-QA receipt 混为同一成功条件；symbol report exact policy 尚未容纳 typed Case A/B 或可重算的 Provider identity hashes
- Fix: target 使用显式 `--activate-current-inputs --pause-after first-pdf-balloons`；runner 先做 credential/runtime/source/contract zero-paid preflight，再从 exact current sources 和 Git-HEAD 唯一 approved annotation bytes 生成 fresh Harness registration IDs，并把 literal IDs 传回原 full-live path。symbol report `/2` 新增 exact typed Case A/B、source/crop/model/prompt/schema identity hashes；Provider crop 按真实 bytes 写入本次 run 并由 policy 重哈希，Case A/B 同时绑定 evaluator label 与 manifest symbol kind。Step 4/5 plan 改为 pause 后 headed QA，再 resume 同一 literal run 生成 receipt
- Regression check: `PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest backend/tests/contract/harness -q` 返回 `173 passed`；focused contract file `61 passed`，`ruff check` 和 `git diff --check` 通过。独立 reviewer 对 malformed counts 与真实 crop-byte tamper 复测均 fail-closed，final verdict `accept`
- Runtime proof: fresh `make verify-p0-live` 先通过 `69` global / `111` P0 contract mapping，再准确退出 `2`：四项 server-only Provider credential 未注入；run directory count 保持 `14 -> 14`，未创建 run、未调用 Provider。activation regression 已解决，GDT-10 live evidence 仍由外部 runtime identity injection 阻塞
- Change: `fix(harness): activate structured GDT live gate`

### Recurrence 2 — isolated runtime target binding

- Last reported: 2026-08-01
- Symptom: GDT-10 feature-only runtime 已按 approved Compose isolation contract 运行在 loopback `127.0.0.1:18000/14173`，但 `run-p0.py::_current_live_identity()` 仍只接受 `http://localhost:8000/3000`；继续执行 `make verify-p0-live` 会拒绝正确 isolated target，或在省略显式 target 时命中 main runtime。
- Previously correct behavior: full-live preflight 必须把 HTTP API/frontend target 与同一次 `_require_compose_runtime_identity()` 验证的 feature-only Compose project 绑定，并在 registration、run creation、upload 和 Provider work 前拒绝 main/feature 混用。
- Reproduction: current source 在 `run-p0.py:1331-1343` 对 API/frontend 使用固定字面量；running Compose labels 证明 feature project 为 `structured-geometric-tolerance-recognition-qa` 且 ports 为 `18000/14173`，main project 仍独立占用 `8000`。尚未运行 Provider/live command。
- Root cause: Compose isolation prerequisite 把 GDT-10 QA runtime 切到 feature-only project 和 `18000/14173`，但 Harness active target、published-port preflight 与 `run.schema.json` receipt identity 仍保留 main `8000/3000`。第一次 schema amendment 又把 old/new bases 写成两个独立 `enum`，会错误接受 mixed API/frontend pair；independent reviewer 的 in-memory probe 捕获该 false success。
- Fix: `_current_live_identity()` 现在要求显式 exact feature project + isolated API/frontend bases；`_require_compose_runtime_identity()` 绑定真实 published ports；`_http_json()` 与 `_browser_environment()` 移除 main defaults；`run.schema.json` 只接受 old-old historical pair 或 isolated-isolated current pair，拒绝 mixed pair并保留历史 sealed receipt 兼容。
- Regression check: exact target/main-default-mixed target 与 published-port tests 已完成 RED→GREEN；schema old/new/mixed 四组测试完成 RED→GREEN。Focused live contract `115 passed`、full Harness `227 passed`、`check-contracts.py`、`ruff`、`git diff --check` 全部通过。
- Runtime proof: fresh zero-paid feature runtime target/health/identity proof 在实现前通过；代码修复后 historical sealed run `20260728T080321805661Z-b59c87de` schema validation 通过。paid invocation count `0`；提交后仍须重跑 fresh real-runtime preflight。
- Change: `fix(harness): bind live gate to isolated runtime`（pending commit at record update）

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

## BUG-20260801-technical-requirement-review-entry-no-feedback

- Status: 已解决
- First reported: 2026-08-01
- Last reported: 2026-08-01
- Recurrence: 1
- Surface: `TechnicalRequirementPanel` 的“进入检验项审核”与 `InspectionWorkbench` 右侧审核工作区
- Symptom: 6 条技术要求全部确认后，点击“进入检验项审核”没有可见反应
- Reproduction: 当技术要求的 `handoffTargetId` 已是当前 `selectedItemId`，且筛选已为 `all` 时，入口只重复写入相同状态；原 focused tests 只断言回调被调用，不验证可见导航
- Root cause: `TechnicalRequirementPanel` 点击只调用 `onSelectItem()`；`InspectionWorkbench` 只执行 `setFilter("all")` 和 `selectItem()`，没有将已选检验项滚入视野或转移焦点。目标和筛选未变时 React 不产生可见更新
- Selected lane: `Standard`；局部 frontend 交互修复，保留现有业务合同并用 focused/full tests、browser smoke 和独立 review 收口
- Selected plan: 本 bug-memory entry 作为 ad hoc task contract；未切换当前 P0 implementation plan
- Selection evidence: 不改变 API、schema、审核命令、draft/save/freeze/export contract；只补齐现有前端入口的可见导航结果
- Validation action: `close`；初审 `reject` 指出面板其他关联项跳转会共享聚焦/滚动副作用，改为只有终态入口调用专用 callback 后复审 `accept`
- Problem boundary: 只修复技术要求终态入口的导航反馈；不改技术要求匹配、普通关联项跳转、保存、审核或正式 SIP 语义
- Single owner: `InspectionWorkbench` 继续拥有检验项选择和工作区导航；`TechnicalRequirementPanel` 通过专用 `onEnterReview` 只发起终态 handoff
- Old path action: 替换“只重复选中目标”的静默路径；其他来源的 `onSelectItem` / `selectItem()` 行为保持不变
- Unchanged contract: `set_technical_requirement_match`、review draft blocker、filter semantics、working-copy versioning、freeze 和 export 均不变
- Allowed paths: `.agent/bug-memory.md`、`frontend/src/components/workbench/InspectionWorkbench.tsx`、`frontend/src/components/workbench/InspectionWorkbench.test.tsx`、`frontend/src/components/workbench/TechnicalRequirementPanel.tsx`、`frontend/src/components/workbench/TechnicalRequirementPanel.test.tsx`、`frontend/src/styles/workbench.css`
- Writer ownership: 父 agent 唯一 writer；已有 SIP metadata 未提交改动位于同文件的非重叠 hunk，未覆盖且不整文件 stage
- Fix: 新增专用 `onEnterReview`；终态入口在原选择成功后定位已选行，将其滚入列表视野、转移焦点并显示明确轮廓；“查看系统建议关联项”和“查看关联项”继续只调用原 `onSelectItem`
- Regression check: TDD RED 首先证明目标已选中时焦点不变，第二次 RED 证明终态入口尚未调用专用 callback；focused `55 passed`，frontend 全量 `24 files / 290 tests` 通过，production build 和 repo-wide `git diff --check` 通过
- Runtime proof: `auto-feature-smoke-test` 在 localhost 已持久化项目 `6943d223…` 验证首次和重复点击；同一已选行获得焦点、`2px` 蓝色轮廓且 console error 为 0，未发送 `/review/commands`；smoke review lock 已精确过期清理
- Independent review: 初审 `reject` 阻断通用 `onSelectItem` 被赋予聚焦副作用；拆分专用 callback 并增加回归后，复审 `accept`，无 blocking 或 non-blocking findings
- Change: `fix(frontend): make inspection review handoff visible`
