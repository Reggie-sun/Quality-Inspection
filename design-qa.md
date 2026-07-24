# Design QA

## Grounding

参考图与当前实现以同一 `1565x796` viewport 并排比较。参考图提供工程图、气泡和右侧检验清单的视觉方向；当前实现保留同一核心工作流，同时用更清晰的细线气泡、独立状态 chips、可滚动检验表及冻结/导出状态区避免参考图中的编号与文字重叠。

source sha256: 4b94989308c91593882495b7fd904455365969e562c2ce032de5e01839b5d79b
implementation route: /?project_id=2d438ac8-7f3c-4661-9cab-a2bd2dba1c51&operator_id=reggie
implementation state: visual_qa_pending:first-pdf-balloons
browser: chrome
viewport: 1565x796
implementation capture: reports/design-implementation.png
implementation capture sha256: ff399856ae59850773fb7b043e13a03aeb4b63471616cecbd7bcff66fc1b924d
comparison capture: reports/design-comparison.png
comparison capture sha256: 629160202ef850dae7b3f072919126558e18495a3fe3bb58763edf6ef186de41

## Interaction Evidence

fresh run `20260723T042259807705Z-4e3e5f85` 的 Chrome Playwright pre-export phase 已通过（1 passed，10.5s），验证 Detected、Active、Excluded、Manual required 与 Hard collision filters，row/balloon 双向选择、page traversal、zoom、pan、drag、delete、rebuild、renumber，以及 reviewed result 之前 formal export 保持 disabled。冻结后的 review metadata 不可编辑；249 个 active rows、36 个 excluded rows、242 个正式气泡与 backend、overlay、table 编号映射一致，manual required 与 hard collision 均为 0。

console errors: 0
network errors: 0
P0 issues: 0
P1 issues: 0
P2 issues: 0
final result: passed

## Successor Task 3 — Chinese PDF Upload Entry

### Grounding

本 successor 使用用户在当前会话上传的参考图作为唯一主要视觉基线，并依次执行 `product-design:index` 与 `product-design:image-to-code`。实现复用同一 React 入口、五阶段流程和工程软件视觉语言；上传阶段没有项目数据，因此保留文字产品栏、流程条、主操作区与紧凑说明侧栏，不伪造项目摘要、检验项、处理日志或进度百分比。

source identity: user-attached reference image
source sha256: e9693f9d27083271af68754c7260ad813316c6cdd39807f6a4e90e74ace33de4
source pixels: 1550x1014
implementation route: /
browser: Chrome
locale: zh-CN
timezone: Asia/Hong_Kong
viewport: 1565x796
comparison normalization: reference preserved at original aspect ratio and fitted into a 1565x796 canvas; implementation captured at native 1565x796 CSS pixels

### Visual Decisions

- 使用白色、浅灰、工程蓝、细边框、6～10px 圆角和低阴影密度；未使用 Logo、渐变、玻璃拟态、营销 Hero、插画或紫色主操作色。
- 五阶段流程固定为“上传图纸 → 智能识别 → 人工审核 → 气泡调整 → 文件导出”。完成、当前和待开始状态同时使用数字、中文文字与颜色表达，不以图标或颜色作为唯一信息。
- 裸根上传页采用主操作区与说明侧栏的紧凑网格；PDF 选择、已选文件、阶段状态、错误和重试保持同一视觉层级。
- 后端没有精确进度时只显示阶段状态与 indeterminate indicator；`prefers-reduced-motion` 下停止旋转。
- 支持范围明确说明纯扫描 PDF 可能暂不支持；页面不显示 Project、operator、resource、Provider、模型、文件 Hash 或原始英文错误。

### Interaction Evidence

runtime capture directory: frontend/test-results/design-qa-task3/ (untracked runtime evidence)
idle capture: upload-empty.png
selected capture: upload-selected.png
uploading capture: upload-uploading.png
processing capture: upload-processing.png
preparing capture: upload-preparing.png
fatal and retry capture: upload-error-retry.png
success transition capture: upload-success-transition.png
same-input comparison: reference-vs-upload-empty.png
comparison sha256: fc969cb781649a9d7212eb2885725a7616f64292cbc248b8074fd91023278bb1

Chrome 检查确认所有上传态 URL 均保持 `/`，`scrollWidth == clientWidth == 1565`，没有横向溢出；空状态、已选择、上传、解析识别、准备审核、fatal 和 retry 均可通过真实浏览器控件到达。各次干净 context 的 console error 与 network error 均为 0，页面文本检查未发现内部 ID。Task 3 的 success transition 已进入既有 Workbench；该 capture 中继承的英文 Workbench loading 文案属于紧接执行的 Task 4 可见文案恢复范围，不作为 Task 3 上传 shell 的完成声明。

### QA Result

- P0 issues in Task 3 scope: 0
- P1 issues in Task 3 scope: 0
- P2 issues in Task 3 scope: 0
- no Logo: passed
- bare-root upload: passed
- no internal ID or static fake log: passed
- no fake percentage: passed
- Chinese upload/status/error/aria copy: passed
- keyboard focus, aria-busy, aria-live and alert states: passed
- reduced motion: passed
- horizontal overflow: none at 1565x796
- Task 3 result: passed
- successor boundary: Task 4 must localize and visually restore the inherited Review Workbench before final product acceptance

## Successor Task 4 — Chinese Review Workbench

### Grounding

Task 4 继续以同一用户参考图作为唯一主要视觉基线，并通过 `product-design:image-to-code` 的 Browser Design QA 工作流复核真实 Review、冻结、气泡调整和导出完成状态。实现保留既有 Review、Balloon、collision validation、Confirm Reviewed Result 与 Export Owner，只调整中文可见文案、刷新恢复投影和工作台视觉组织。

source identity: user-attached reference image
source sha256: e9693f9d27083271af68754c7260ad813316c6cdd39807f6a4e90e74ace33de4
implementation route: /
browser: Google Chrome 149.0.7827.53
locale: zh-CN
timezone: Asia/Hong_Kong
viewport: 1565x796
runtime evidence directory: frontend/test-results/design-qa-task4/ (untracked runtime evidence)

### Visual And Product Decisions

- 顶部只显示文字品牌“智检通 / 工程图纸智能检验”和“处理另一份图纸”，没有 Logo；工作台加载后不保留过期的“识别完成”提示，五阶段流程条是稳定流程状态展示。
- 页面使用 `46 / 32 / 22` 三栏比例；PDF 区域面积大于检验项区与右侧辅助栏，保持最大视觉权重。
- 检验项列表一次真实渲染 50 行，支持搜索、状态筛选、紧凑分页和跨页选择；第 61 项选择会自动跳到第 2 页。
- 所选项摘要保持 sticky，显示真实气泡号、原始标注、页码和中文状态，不显示 item UUID。
- 右侧 `SIP基本信息` 默认显示紧凑的 8 字段真实摘要，缺失值为“—”；既有 `set_sip_metadata` 编辑命令收进默认折叠的“编辑 SIP 信息”，并额外提供 command-required 的“物料编码”以恢复旧空值，没有复制数据 Owner。
- 正式导出仍只展示带气泡 PDF、SIP Excel 和 manifest 三项真实产物；导出完成时三个下载行在 `796px` 首屏内完整可见，最下方行底部为 `789.6px`。
- “公司处理记录”没有正式事件 projection 时只显示“暂无处理记录”，没有静态假日志。

### State And Interaction Evidence

formal captures:

- `01-review-workbench.png`
- `02-selected-item.png`
- `03-frozen.png`
- `04-balloon-adjustment.png`
- `05-export-completed-initial.png`
- `05-export-completed.png`
- `06-reference-vs-implementation.png`

真实 Browser QA 覆盖 124 项 Review 项目和 285 项冻结/导出项目。Review、frozen、export 三种状态分别由阶段 3、4、5 表达；选中项、冻结态、气泡选择和三个正式下载均由真实 projection 驱动。页面 path 始终为 `/`，query string 为空，未发现 Logo、UUID、内部 ID、伪进度百分比、静态假日志或页面级横向溢出。

### Console And Network

- command: `node test-results/design-qa-task4/run-design-qa.mjs`
- exit code: 0
- console errors: 0
- console warnings: 0
- HTTP responses >= 400: 0
- unexpected request failures: 0
- real Workbench/source PDF GET: all 200
- non-GET requests: 3 个本地 fulfill 的 Review lock，不执行 Review、Balloon 或 Export mutation
- explained request aborts: 3 个已返回 200 并完成 canvas 渲染的 source PDF 流在状态切换时被 Chrome 取消

### QA Result

- P0 issues: 0
- P1 issues: 0
- P2 issues: 0
- no Logo or internal ID: passed
- all user-visible product chrome in Chinese: passed
- no fake data, percentage or company log: passed
- PDF remains the largest region: passed
- hundreds-item browsing and selected-item context: passed
- compact truthful SIP card and preserved edit command: passed
- all three completed downloads visible at 1565x796: passed
- focus-visible and reduced motion: passed
- console and network gate: passed
- Task 4 result: passed
- successor boundary: Task 5 bare-root upload-to-two-download browser closure remains intentionally not started in this session

## Successor Task 5 Prerequisite — Source-Only Coverage Review

### Grounding

真实裸根上传发现 124 个检验项之外还存在 90 个 `source-only coverage` 待确认项。既有 backend freeze veto 正确阻止未确认 coverage，但 Task 4 UI 没有对应审核入口，因此用户无法进入正式气泡编号阶段。本修复继续使用用户参考图作为唯一主要视觉基线，仅补齐既有 Review Owner 的可操作入口，不绕过 freeze，也不改变 Balloon、collision、Reviewed Result 或 Export Owner。

source identity: user-attached reference image
source sha256: e9693f9d27083271af68754c7260ad813316c6cdd39807f6a4e90e74ace33de4
source pixels: 1550x1014
implementation route: /
browser: Google Chrome
locale: zh-CN
timezone: Asia/Hong_Kong
viewport: 1565x796
runtime: isolated source-mounted Task 5 QA stack
real input: 152.3 KB engineering PDF
implementation capture: /tmp/qi-task5-design-zhcn-before.png
implementation capture sha256: 907cb88832c63af82931064184651f4752ca2b6a873c1a9bcc40ded96bce8f76
post-save capture: /tmp/qi-task5-design-zhcn-after.png
post-save capture sha256: f159dc52f18e501509aed1a80db557768f4cd05486a6c0e70350b6c36a627cfa
comparison capture: /tmp/qi-task5-reference-vs-coverage.png
comparison capture sha256: 6b68c39fd97c9f18548c59fce79a4b1e1b759ec1c046e21043b04ae7a41dc172

### Product And Visual Decisions

- backend Workbench projection 只补充当前 `requires_confirmation == true` 的 source-only observation；已解决、参考上下文或非检验来源不会长期留在 SVG 中增加图面噪声。
- 中栏在识别汇总与检验项列表之间显示单条紧凑“来源待确认”卡片；待确认项存在时首次进入即可看见，全部解决后卡片自动消失并把空间归还给列表。
- 卡片只展示真实原始标注、真实来源页码和 `current / total` 阶段计数，并提供“上一条来源”“下一条来源”“确认忽略此来源”“确认保留此来源”。
- 当前来源使用既有青色虚线来源框并自动跳转到对应 PDF 页；未增加第二状态 Owner、批量自动接受或静态假数据。
- 每次决定仍先进入既有 pending Review command，再由顶部“保存审核修改”显式提交；保存中禁用重复操作。

### Interaction Evidence

Chrome 从裸 `/` 上传真实 PDF 后自动创建项目并进入 Workbench，初始卡片显示 `1 / 90`。浏览到下一条后显示真实标注“铣深1mm”；选择“确认保留此来源”并点击“保存审核修改”后，既有 `resolve_confirmation` 返回 200，刷新后的计数为 `2 / 89`，已确认 source-only 框不再由新增投影保留。

Playwright `zh-CN` context 复核结果：

- route path `/`，query string 为空；
- `navigator.language == zh-CN`；
- `scrollWidth == innerWidth == 1565`；
- 来源审核卡片顶部为 `290px`，处于首屏；
- PDF canvas 已实际渲染，PNG data length 为 `250658`；
- 可见文案未匹配 UUID；
- console errors 为 0；
- HTTP `>= 400` 为 0；
- 唯一 request failure 是保存刷新时旧 `/api/v1/projects/[id]/source-pdf` fetch 被 Chrome 以 `net::ERR_ABORTED` 取消；新 Workbench 与新 PDF 随后均成功加载，属于已解释的 superseded stream。

### QA Result

- P0 issues: 0
- P1 issues: 0
- P2 issues: 0
- source-only confirmation is browser-operable: passed
- existing Review Owner and freeze veto preserved: passed
- pending-only source projection: passed
- selected source page jump and cyan dashed highlight: passed
- no visible internal ID or static fake data: passed
- no horizontal overflow at 1565x796: passed
- PDF remains the largest visual region: passed
- console and network gate: passed with one explained superseded source stream
- prerequisite result: passed

## Full Product Frontend QA — 2026-07-24

### Scope And Grounding

本轮以 `d2133135ce2e7af246f4c44164374ac13b3510b9` 为 QA 基线，仅检查并修复裸根上传、Review Workbench、气泡和导出前端中确认存在的 P0/P1。没有新增依赖、路由、业务 Owner 或后端状态语义，也没有修改长期契约和封存计划。

source identity: user-attached reference image
source sha256: e9693f9d27083271af68754c7260ad813316c6cdd39807f6a4e90e74ace33de4
source pixels: 1550x1014
implementation route: /
browser: Google Chrome 149.0.7827.53
Playwright browser channel: chrome
locale: zh-CN
timezone: Asia/Hong_Kong
device scale factor: 1
primary viewport: 1565x796
responsive viewports: 1366x768, 1180x800
Product Design calls: `product-design:index`, `product-design:image-to-code`
Design QA workflow: reference 与当前真实实现截图合并为单一 comparison image 后进行视觉核验

参考图只用于视觉层级、布局比例、色彩、间距、表格和面板组织、操作层级与工业软件质感。参考图中的 Logo、自动保存、第二个 Excel、静态操作记录和业务样例没有进入实现。

### Initial Findings

P0:

- 本地 Review、SIP 明细和 SIP metadata 草稿变化后，项目摘要仍显示“已保存”，并可能让用户误以为可以冻结。
- 检验项缺少真实页码时，列表和详情用第 1 页兜底，形成不存在的业务事实。

P1:

- `invalid_pdf` 与 `unsupported_input` 仍提供“重新处理”，可能对同一无效输入创建重复项目；已选文件的“重新选择文件”也没有真正打开文件选择器。
- 状态请求失败后选择新 PDF 没有清理旧错误态和旧项目指针，新的上传入口仍被隐藏。
- 数百个候选项和正式气泡全部进入 Tab 顺序，键盘浏览不可用。
- 已确认结果中的正式气泡仍显示抓取光标并挂载拖动处理器，视觉语义像是仍可修改。
- 冻结或确认后的草稿字段仍可编辑；Review、SIP 与 metadata 缺少取消入口。
- 保存状态和导出状态没有稳定的 `aria-live` 状态播报。
- PDF“缩略图”目前仍是页码卡片；“适合页面”仍是恢复 100% 与平移归零，不是真实容器适配。
- 后端当前没有独立的解析/识别阶段 projection，也没有备注字段的正式 schema；前端不能补假阶段或假字段。

P2:

- 高密度图纸上的气泡与来源框仍有视觉拥挤；部分紧凑区域的间距可继续打磨，但不影响操作闭环。

### Fixed Findings

- 上传失败按真实 `retryable` 与 HTTP 状态分流；无效或不支持的 PDF 只保留“重新选择文件”，不再对同一输入显示“重新处理”。
- 已选文件提供真实“重新选择文件”和“移除已选文件”操作，文件名与大小来自浏览器 `File`。
- 状态请求失败后接受新有效 PDF 时，清理旧错误态和旧项目指针并恢复新的上传入口，不创建隐藏重复项目。
- 未知页码统一显示“—”或空输入；只接受 item、page index 或 balloon 中真实存在的页码。
- Review、SIP 明细和 SIP metadata 草稿即时驱动“有未保存修改”，并阻止冻结；保存、冻结、确认的既有 Owner 和顺序没有改变。
- 为 Review、手工新增项、SIP 明细和 SIP metadata 增加局部取消操作；切换检验项时保留该项未确认的 SIP 草稿。
- 冻结或 reviewed 状态下禁用 Review/SIP 编辑；reviewed 气泡仍可选择定位，但不再可拖动。
- 候选项和正式气泡分别使用 roving `tabIndex`，每组最多一个当前标记进入 Tab 顺序。
- 保存与导出状态增加中文 `role=status`、`aria-live=polite` 和 `aria-atomic=true`。

changed files:

- `frontend/src/app/QualityInspectionApp.tsx`
- `frontend/src/app/QualityInspectionApp.test.tsx`
- `frontend/src/components/balloons/BalloonOverlay.tsx`
- `frontend/src/components/pdf/OverlayLayer.tsx`
- `frontend/src/components/pdf/OverlayLayer.test.tsx`
- `frontend/src/components/review/ReviewPanel.tsx`
- `frontend/src/components/review/ReviewPanel.test.tsx`
- `frontend/src/components/workbench/ExportPanel.tsx`
- `frontend/src/components/workbench/ExportPanel.test.tsx`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`

### Screenshot Evidence

- `.local/design-qa/01-upload-idle.png` — `bc6b9d2bffd0a6b772afa468cfdeaffb322e1a5a409dbf64ad44484f2ac1affc`
- `.local/design-qa/02-file-selected.png` — `dc0f81dac03d5d15ba2bb49356e3c00848364e7b6cb2dadf23f78213b097ecd6`
- `.local/design-qa/03-processing.png` — `1c09748eb02d67e51a3d5e576f433005ac5bc9d960e48e054419073c0d3daa60`
- `.local/design-qa/04-fatal-retry.png` — `09b69d08ab0582a4a6005226ca7aeceb7f8f5d4a388583a4b8a4c2f641cf1752`
- `.local/design-qa/05-workbench-overview.png` — `6e970b26e763fbce56d3c5175b77f82eea8f1201f6f08bc495161cf9021ac101`
- `.local/design-qa/06-item-selected.png` — `71d175e2b888eb7164a85dca3bf034ae2b8ed8b1bf17475430293fd18d2b20a3`
- `.local/design-qa/07-items-frozen.png` — `a772662178aea224046a39764bc0e28a4715428d75e811da67b56f3a0d5a61e7`
- `.local/design-qa/08-balloons-adjusted.png` — `33495879fec05590c5dfb96b848be9a1b9cd003f65c71e4e9706e45a9642e27e`
- `.local/design-qa/09-export-success.png` — `fcfda059b27d9609358fb179074c9cebe03fe936cf108ca2dcac2e749646603d`
- `.local/design-qa/10-reference-comparison.png` — `4a33c72c98bd6e428f60d94c70c5889fa026a25aa9fa2649519f217c33ea90a6`
- `.local/design-qa/11-workbench-1366.png` — `d3030d888680a9c05cfe5a15c486f4750225f67f5edcb348de5733bd5cdee2f8`
- `.local/design-qa/12-workbench-1180.png` — `e264ac8f1b9927247c9059a7ee1522267c3cf921b819b038d7750fb07f8f5fcf`

截图和 comparison image 保持未跟踪，不加入 Git。

### Console, Network And Accessibility

- 当前源码的真实裸根 Chrome E2E 完整执行上传、90 条来源确认、124 条检验项审核、冻结、气泡生成与调整、碰撞解决、确认、原子导出及三个下载；console errors、HTTP `>= 400` 和 request failures 均为 0。
- Design QA 的 reviewed workbench capture 中 console errors 和 network errors 均为 0。
- invalid PDF capture 与 Chrome MCP smoke 各自只有预期的 `POST /api/v1/projects` 422；页面显示安全中文错误，不显示后端 message。Chrome 对该预期 422 记录的 resource console error 已解释，不计为未解释错误。
- 状态请求失败 Chrome MCP smoke 使用不存在的临时项目触发真实 404；重新选择有效 PDF 后实测旧项目指针已清理、上传按钮恢复且错误提示消失。该预期 404 的 resource console error 已解释。
- Chrome accessibility snapshot 的可访问名称均为中文；可见文本与可访问名称没有 UUID。下载 API 的资源标识只存在于真实 link target，不作为可见文案或 accessible name。
- 上传控件可通过 Tab 聚焦，实测 `focus-visible` 为 3px solid outline 与 2px offset；fatal 使用 alert，processing 使用 busy/live 状态，保存和导出状态使用 live region。
- candidate 与 formal balloon 各自最多一个当前标记进入 Tab 顺序；reviewed balloon 保留键盘选择能力但不提供拖动。
- `prefers-reduced-motion` 下停止 processing indicator 动画；状态同时使用中文文字和形状/边框，不只依赖红绿颜色。
- 1565x796、1366x768 与 1180x800 均没有页面级横向溢出；1180px 将右侧 SIP/导出栏重排到主工作区之后，仍可使用。

### Truthfulness And Functional Result

- 无 Logo、紫色主视觉、渐变、玻璃拟态或 AI 光效。
- 页面不显示 project/operator/item UUID、Provider、模型、文件 hash、后端路径或原始英文错误。
- 生产代码没有静态产品数据、静态公司日志或虚假进度百分比；E2E 中 SIP 值是 QA 操作明确输入并由后端保存的测试数据，不是前端默认值或文件名推断。
- “公司处理记录”在没有正式事件 projection 时只显示“暂无处理记录”。
- 正式导出只包含带气泡 PDF、SIP Excel 与 manifest；成功态要求三项均可下载，三个产物来自同一 reviewed result。
- 下载的 PDF 与 XLSX 均为非空且通过文件签名校验。
- 保存不等于冻结，冻结不等于确认；pending command 或本地未确认草稿存在时不能进入下一阶段。
- 气泡拖动保存 PDF 坐标；删除气泡不删除检验项；manual required 与 hard collision 未解决时不能确认。

### Remaining Findings And Conclusion

- Remaining P0: 0.
- Remaining P1: 页码卡片不是真实页面缩略图；“适合页面”不是真实 fit-to-container。二者需要扩大 PDF workspace 行为，未在本轮局部修复中实现。
- Remaining P1 copy edge: 若后端把 `ocr_provider_unavailable` 等非输入类错误标记为 `retryable=false`，错误标题的“稍后重试”与通用下一步“重新选择有效 PDF”可能不一致；应在后续按正式错误类别细化中文下一步，不改变后端 retryable 语义。
- Backend semantic blockers: 独立的“正在解析/正在识别”精确阶段和备注字段没有正式 projection/schema；前端没有伪造。
- Remaining P2: 极高密度图纸的气泡视觉拥挤与局部紧凑间距。
- Runtime risk: 仓库现有无关 `compose.yaml` 改动把 canonical frontend host port 指向已占用端口，导致指定 canonical compose 命令的 frontend 启动失败；隔离 QA stack 的当前源码完整闭环通过。
- Backend host-test risk: 指定的 host pytest 命令缺少 `PYTHONPATH=backend`，补充后仍因 host 无法解析 Compose hostname `postgres` 产生拓扑失败；这不是本轮前端回归。
- Final frontend QA conclusion: P0 为 0，核心中文裸根上传到正式导出的真实闭环通过；剩余 P1/P2 和后端语义 blocker 已明确保留，没有用前端假状态绕过。

### Verification

- `python .agent/harness/scripts/check-contracts.py`: passed；`unclassified=0`、`mirror_drift=0`、`bindings_drift=0`。
- `micromamba run -n qi-p0 npm --prefix frontend test -- --run`: 17/17 test files，84/84 tests passed。
- `micromamba run -n qi-p0 npm --prefix frontend run build`: passed；仅保留既有 large-chunk warning。
- `micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list`: 2 tests / 2 files，可发现中文裸根闭环和 P0 current-four regression。
- 当前源码真实中文裸根闭环：1 passed，2.7m；覆盖来源确认、检验项审核、冻结、气泡、碰撞处理、确认、原子导出和三个非空下载。
- `micromamba run -n qi-p0 pytest backend/tests -q`: collection 因 host import path 缺少 `app` 失败；补 `PYTHONPATH=backend` 后因 host 无法解析 Compose service hostname `postgres` 得到 302 passed、27 failed、116 errors。
- 指定 canonical compose 启动中 postgres、redis、api、worker 正常，frontend 因现有无关 host port 冲突失败；API health 成功，指定 frontend root curl 失败。隔离 source-mounted QA stack 的 API/frontend health 与完整浏览器闭环通过。

### Independent Reviewer

- verdict: accept with concerns
- blocking findings: 0
- confirmed: 无 Logo、无可见内部 ID、无静态假数据/假日志/假进度；PDF 保持最大工作区；中文和可访问性修改成立；保存、冻结、气泡、确认、导出顺序未改变；未新增依赖、路由或业务 Owner。
- evidence correction: `07-items-frozen.png` 已重抓为真实 stage 4 冻结未确认态，与 stage 5 的 `09-export-success.png` 独立。
- non-blocking findings: 真实缩略图/fit-to-container、`retryable=false` 的少数错误文案边缘、极高密度气泡拥挤。

## Toolbar Workspace Layout Correction — 2026-07-24

### Grounding And Normalization

本轮以用户当前会话提供的两张视觉目标为准：一张定义“两栏大图 + 右侧检验区”的主工作台比例，另一张定义 `SIP基本信息 / 正式文件 / 公司处理记录` 的内容和顺序。实现继续使用真实项目 `2d438ac8-7f3c-4661-9cab-a2bd2dba1c51`，没有 mock 业务数据或修改正式结果。

- source visual truth: `.local/source-large-workbench.png`，`1832x966`，SHA-256 `4abd42e23614c7ba3f60b9b653de87d97837d2e1f0a3d9ac8f59942570d6cf29`
- source panel truth: `.local/source-sip-panel.png`，`409x622`，SHA-256 `a18b90f9501b7fc01902557234f6b70fe93ae02b287b8917df5a778a999707db`
- implementation route: `/?project_id=2d438ac8-7f3c-4661-9cab-a2bd2dba1c51&operator_id=reggi`
- browser: Google Chrome
- CSS viewport / device scale factor: `1832x966 / 1`
- default capture: `.local/toolbar-workspace-default.png`，`1832x966`，SHA-256 `7e37f7b01c638c80b875660d69d1cdd8c74284bea06e1568fb002ca664c627cd`
- open capture: `.local/toolbar-workspace-open.png`，`1832x966`，SHA-256 `945624a689d434635a123b667ac0842e9a02446caf7cf98482e7adabbe976feb`
- combined comparison: `.local/design-qa-comparison.png`，SHA-256 `7eec79d2acc3a7ca4d51eda5fb02bca9c7bf88424ec10d0cc14a79ac928fa579`
- normalization: 主工作台 source 与 implementation 均为 `1832x966`；source 包含浏览器 chrome，判断时只比较 app-owned content。面板 source 保持原始比例，与 implementation 的 `380px` 右上浮层做 focused comparison。

### Findings And Iteration

- Earlier P1: 常驻 `46 / 32 / 22` 三栏让 PDF 工作区明显窄于参考大图。Fix: 删除常驻第三栏路径，主工作台改为 `2 / 1` 两栏；Chrome 实测为 `1142.66px / 571.33px`，PDF 继续是最大区域。
- Earlier P1: SIP、正式文件和公司记录默认常驻，占用首屏。Fix: 在 PDF 控件行增加中文“展开 SIP 与导出信息”，默认 `aria-expanded=false`；点击后显示同顺序右上浮层，按钮变为“收起 SIP 与导出信息”。
- Earlier P2: 面板若直接放进横向滚动控件容器会被裁切。Fix: 控件负责切换，浮层作为 PDF workspace 的直接子节点定位；展开和收起均无页面级横向溢出。
- Review P1: 收起时卸载 `ExportPanel` 会丢失本轮导出结果或进行中状态。Fix: 面板始终挂载，仅用 `hidden` 控制可见性；新增成功态和进行中态的收起再展开回归。
- Post-fix comparison: 未发现新的 P0、P1 或 P2。

### Required Fidelity Surfaces

- Fonts and typography: 沿用现有中文系统字体、字号、粗细和层级；按钮、标题、表格和小字无新增截断。业务字段值来自后端，未把英文数据值误改为界面文案。
- Spacing and layout rhythm: 两栏比例、10px 主间距、380px 浮层宽度和右上锚点与参考密度一致；默认态释放第三栏后，图纸面积与参考 smoke 同级。
- Colors and visual tokens: 继续使用既有白色、浅灰、工程蓝、细边框和低阴影；没有引入渐变、紫色主视觉或新 token。
- Image quality and asset fidelity: PDF 仍由真实 PDF.js canvas 与真实 overlay 渲染；缩略图、气泡和来源标注未替换为占位图，也没有新增 raster/icon 资产。
- Copy and content: 新增控件及可访问名称均为中文；三个面板的标题、说明、下载动作和空状态保持中文，真实 SIP/检验值不被伪造。

### Browser And Interaction Evidence

- 默认加载：两栏大图可见，辅助面板不存在于可访问树，toggle 为“展开 SIP 与导出信息”且 `aria-expanded=false`。
- 点击展开：同一按钮变为“收起 SIP 与导出信息”，可访问树出现 `SIP基本信息`、`正式文件导出`、`公司处理记录`，三个真实下载仍可访问。
- 点击收起：面板保留同一 DOM 节点但以 `hidden` 从可访问树隐藏，toggle 恢复默认状态；再次展开仍保留三个下载与组件状态。
- 原“展开工作区”继续可用；点击后 `data-expanded=true` 且按钮变为“收起工作区”。
- 页面级横向溢出：none。
- console errors / warnings: 0 / 0。
- focused region comparison: 使用 combined comparison 的下半行检查面板标题、字段网格、导出卡片、三下载与公司记录；无需额外裁图即可清晰读取。

### Result

- Remaining P0: 0.
- Remaining P1: 0.
- Remaining P2: 0.
- final result: passed
