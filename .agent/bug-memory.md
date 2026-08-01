# Project Bug Memory

本文件记录项目内用户报告的 bug 和已经确认的回归。调试前先阅读；重复问题更新原记录，不要重复创建。

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
- Last reported: 2026-08-01
- Recurrence: 1
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
