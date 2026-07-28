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

## Qwen Vision Runtime And Remaining-Risk Closure — 2026-07-24

### Scope And Grounding

本轮从 commit `7d5ed9534b9dd263d572ea5364f03ed3af2f9a71` 开始，只完成已确认的 Qwen Vision runtime 接入和上一轮剩余 P0/P1 风险收口。实际接入的是现有 Qwen Vision OpenAI-compatible API，不是新增自托管 vLLM 服务。没有新增依赖、修改 `package.json`、建立第二套前端、改写 Review/Balloon/Export Owner，或用前端状态掩盖后端失败。

source identity: user-attached confirmed reference image
source sha256: e9693f9d27083271af68754c7260ad813316c6cdd39807f6a4e90e74ace33de4
source pixels: 1550x1014
implementation route: /
browser: Google Chrome
Playwright browser channel: chrome
locale: zh-CN
timezone: Asia/Hong_Kong
device scale factor: 1
primary viewport: 1565x796
responsive viewports: 1366x768, 1180x800
Product Design calls: `product-design:index`, `product-design:image-to-code`
Design QA workflow: 使用 `product-design:image-to-code` 内置 design-QA workflow，对用户参考图、当前运行态截图和 comparison image 做同方向核验

参考图继续只拥有视觉层级、布局比例、色彩、间距、表格与面板组织、操作层级和工业软件质感。Qwen 输出、检验项、页码、SIP 字段、公司记录、导出物和处理阶段全部来自正式代码或受控 QA runtime projection，不从参考图推导业务事实。

### Initial Findings

P0:

- Qwen 配置虽然存在，但 canonical processing task 没有建立可审计的 runtime Provider factory、局部 crop、strict schema validation、cache 和 Provider call record，LLM advisor 并未形成正式闭环。
- 首次真实 Qwen HTTP 200 响应因 prompt 未携带 frozen output schema 而缺少必填字段，导致需要 Vision advisor 的 PDF 进入安全失败而无法完成处理。
- processing stage 更新提交后，failure claim 在 `expire_on_commit=False` session 中可能读取 stale identity map，影响并发失败归属和最终状态。

P1:

- 状态 projection 不能区分 queued、parsing、recognizing 和 preparing review，前端只能显示过粗阶段。
- 页码卡片不是 PDF 页面缩略图；“适合页面”只恢复固定比例，不按真实容器测量。
- Review/SIP 没有正式 `remarks` schema，前端不能安全增加备注编辑。
- 少数 `retryable=false` 的非输入类错误仍可能给出不够精确的中文下一步。
- 数百条检验项与数百个候选/来源标记需要更低噪声的默认密度和更强的选中态。

P2:

- 极高密度工程图在不隐藏真实候选和来源的前提下仍有视觉拥挤。

### Fixed Findings

- `backend/app/providers/runtime.py` 建立 Qwen OpenAI-compatible factory，只接受现有正式配置，超时 30 秒、SDK retry 为 0，不记录 credential。
- 新增 `backend/app/candidates/advisor.py`：只路由 coarse、composite、OCR、requires-confirmation 或 parser-failed 对象；每页最多 16 次局部 crop；使用稳定 cache key、严格 frozen schema、原文与类型防漂移校验和脱敏 call record。
- Advisor cache 命中前必须解析到对应 Provider call record；worker 若在 cache 与 call record 写入之间中断，后续处理会 fail closed，不会复用缺少审计记录的模型响应。
- `backend/app/processing/runtime_recognition.py`、`tasks.py`、`pipeline.py` 和 `automatic_result.py` 将 advisor 接入 canonical task；正式 Working Copy 移除 advisor provenance，Provider 仍不是业务语义 Owner。
- Qwen prompt 明确声明 `additionalProperties=false` 的完整 output schema；真实 HTTP 200 后成功生成 Automatic Result 和 Working Copy。同一 logical task 重放复用结果，call record 数不增加。
- `backend/app/jobs/idempotency.py` 在成功 claim failure 后只 refresh 当前 logical job，消除 stage commit 后的 stale state，不改变并发 winner 语义。
- 新增 migration `backend/alembic/versions/0007_processing_stage.py`，后端正式投影 queued/parsing/recognizing/preparing_review；前端只显示阶段和 indeterminate indicator，不显示百分比。
- Review command schema、working copy 和前端 SIP 明细加入 optional `remarks`；空值保持空，不阻塞 freeze/export，不生成示例备注。
- `PdfWorkspace.tsx` 使用 PDF.js canvas 渲染真实 48×32 页面缩略图；“适合页面”基于 scroll frame 与真实 page size 计算比例。
- 错误 guidance 按 invalid/unsupported、Provider/config、processing failure 和 retryable 分流；不显示后端英文 message，也不将有效 PDF 误说成无效。
- `OverlayLayer.tsx` 与 `workbench.css` 对高密度 candidate/source 降低默认 opacity，selected/related 保持完整强调；正式红色气泡语义和交互不变。

changed production files:

- `.agent/harness/scripts/run-p0.py`
- `backend/alembic/versions/0007_processing_stage.py`
- `backend/app/candidates/advisor.py`
- `backend/app/candidates/coverage.py`
- `backend/app/jobs/idempotency.py`
- `backend/app/processing/automatic_result.py`
- `backend/app/processing/pipeline.py`
- `backend/app/processing/runtime_recognition.py`
- `backend/app/processing/tasks.py`
- `backend/app/projects/schemas.py`
- `backend/app/projects/service.py`
- `backend/app/providers/call_records.py`
- `backend/app/providers/runtime.py`
- `backend/app/review/schemas.py`
- `backend/app/review/service.py`
- `frontend/src/api/types.ts`
- `frontend/src/app/QualityInspectionApp.tsx`
- `frontend/src/components/pdf/OverlayLayer.tsx`
- `frontend/src/components/pdf/PdfWorkspace.tsx`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/styles/workbench.css`

对应 contract、unit、integration、E2E 和 frontend component tests 同步更新；未新增 runtime dependency。

### Qwen Runtime Truth

- `.env` 中 Qwen API key、workspace 和 model 配置均存在；QA 只检查是否存在，没有打印值。
- 当前 runtime log 中 Qwen HTTP 200 count 为 2；对应 2 个 Provider call record 均通过字段 allowlist 和 forbidden-content 检查，credential/base64/data URL count 为 0。
- 主 Qwen smoke 产生 1 个 Automatic Result、1 个 validated-or-rejected advisor decision 和 1 个 Working Copy；同一 canonical logical task 重放后结果复用，未增加 call record。
- 最终原生 `M6` 浏览器 QA 前后 Qwen call record 都为 2，证明清晰 native candidate 没有不必要调用 Vision Provider。
- runtime log：traceback 0、Authorization 0、API-key pattern 0、data-image 0。

### Browser, Network And Accessibility

- Google Chrome context 实测为 `1565x796 / scale 1 / zh-CN / Asia/Hong_Kong`。
- 裸 `/` 显示文字品牌“智检通”和“工程图纸智能检验”，无 Logo 图形；空态上传按钮禁用，无内部 ID 和页面级横向溢出。
- 选择文件后显示浏览器 `File` 的真实文件名和 784 B 大小，可重新选择或移除。
- 为截取确定性阶段证据，QA 短暂停止 worker，在单一受控 QA 项目上写入正式 `LogicalJob.processing_stage` projection，分别验证 queued、parsing、recognizing、preparing_review；随后恢复 queued、重启 worker 并由 canonical task 完成真实处理。生产前端和业务代码没有 mock 或静态阶段。
- processing 使用 `aria-busy=true` 和 polite live status；四阶段均无百分比。
- invalid PDF 使用 `role=alert`、中文原因和“重新选择文件”；唯一 network failure 为预期 422，Chrome 对该 422 记录 1 条 resource console error，已解释。
- 成功上传、工作台、缩略图、fit、remarks、密集图和响应式路径：console errors 0，HTTP `>=400` 0。
- 当前已发布结果的三个真实下载均成功且签名有效：带气泡 PDF 887343 B、SIP Excel 1393236 B、manifest 1090 B；三者与 manifest 内部引用均来自同一个 reviewed result，下载路径 HTTP failure 为 0。
- Tab 可到达 file input，`.pdf-dropzone:focus-within` 实测有可见 outline；workbench accessibility snapshot 包含中文 landmark 和可访问名称，无 UUID。
- `prefers-reduced-motion: reduce` 实测生效，transition 和 animation duration 为 0。
- 真实缩略图为 48×32 canvas，包含非白渲染像素；fit 后 page layer 为 `741×494`，完整落在 `918.65625×520` frame 内。
- 当前两栏工作台中 PDF pane 实测宽 `1012.65625`，大于列表 pane 的 `506.34375`；SIP/导出辅助面板默认收起，无页面级横向溢出。
- 高密度实图当前页为 89 个 candidate markers、75 个 source markers、50 行表格；candidate 点击可定位 selected row。
- 1366×768 和 1180×800 的 `scrollWidth` 分别等于 viewport width，PDF 与表格均保留可用。
- 独立 Reviewer 首轮发现 `05–10`、`15–17` 来自已退休的三栏 runtime。QA 随即从当前 worktree 重建隔离 frontend，重抓工作台、冻结、气泡、导出、comparison、缩略图、密集图和响应式证据；新截图均显示当前两栏布局和“展开 SIP 与导出信息”控件。

### Screenshot Evidence

- `.local/design-qa/01-upload-idle.png` — `bc6b9d2bffd0a6b772afa468cfdeaffb322e1a5a409dbf64ad44484f2ac1affc`
- `.local/design-qa/02-file-selected.png` — `23426321c9b127efe295a39d3ebb5a63cb02595f89f07bdf0d323f158dac3912`
- `.local/design-qa/03-processing.png` — `baf9db2265307092fbe8fb6e0d603cb815fdbd67b9770434a0236d98410564f6`
- `.local/design-qa/04-fatal-retry.png` — `dda9ae812eebd2f4d8cbe3ddff2bbeda3da53812e3f4b3cd4fb8115df9272e7c`
- `.local/design-qa/05-workbench-overview.png` — `b528ae96a6f22094c9bf75dd513e8044b98056668f92518e5c224b92adad2565`
- `.local/design-qa/06-item-selected.png` — `0687a69b706c12b7591714d967e87c8e94f858fc3ca33ed9a670fb845620c5bc`
- `.local/design-qa/07-items-frozen.png` — `044813b0f1575838122da15aeef536515e8ee818defcf6c6158534a4ae3dd7a6`
- `.local/design-qa/08-balloons-adjusted.png` — `ea5e54e8357c2579fdec08b6a6b7c9c8be8ca10d6d7870388e3c34b296d0a78d`
- `.local/design-qa/09-export-success.png` — `64017b11f5a90c2f865e403e7e44f490f0e710c6cb7d704c5318a9e670903418`
- `.local/design-qa/10-reference-comparison.png` — `3da95a251ca0dab4321226b646c9ad41ea3cb48422d6aaef5d39829aa1df169c`
- `.local/design-qa/11-workbench-1366.png` — `b569eae28257efcbaebf46cbe61245504baa487a4dadf6d032521f450dc4cf21`
- `.local/design-qa/12-workbench-1180.png` — `a34e74eefbdd59de1a495bee8d0a7ff760b3de4a3ceeb80fe24eb7368f21126a`
- `.local/design-qa/13-processing-parsing.png` — `9776914c7294d4e34fefd4b1531feba6d10df3acbcc257b31786c356b14045d3`
- `.local/design-qa/14-processing-recognizing.png` — `cf52e58edccebec8e9aadab55a8a09b3e1d93b6767aed04d124905ca5a670fdf`
- `.local/design-qa/15-real-thumbnails-fit.png` — `632f35bfc311d75f680f70f0bb4ea8a7374f35d77311100b5b924fbed447d661`
- `.local/design-qa/16-item-remarks.png` — `996c1329668a0761e908165ef77432592ad87ada4123e2b6ffc64df98105e3f9`
- `.local/design-qa/17-dense-overlay-focus.png` — `f4ec4b59afd7eac94660964f41fe14b62094866877880d815d3e0ced87338978`
- `.local/design-qa/18-workbench-1180.png` — `416631b5a4731067336f77267b1771f45e18134ba1caaff6d8aa7386c1c991b1`
- `.local/design-qa/19-processing-preparing-review.png` — `44f18a35f493c12fdcd0db7ea13cd3155f1d60fd946c52f8afcd0b9e571117fa`

全部截图、受控 PDF、浏览器 evidence JSON 和下载物保持未跟踪，不加入 Git。

### Verification

- `python .agent/harness/scripts/check-contracts.py`: passed；`global_contracts=69`、`p0_contracts=111`、`unclassified=0`、`mirror_drift=0`、`bindings_drift=0`。
- 用户指定的 `micromamba run -n qi-p0 pytest backend/tests -q`: 从仓库根执行时得到 55 个同源 collection errors，原因为 console entrypoint 没有把 `backend/app` 加入 import path。
- 修正启动方式、先执行 Alembic migration，并使用自动创建/删除的隔离 PostgreSQL：`cd backend && micromamba run -n qi-p0 python -m pytest tests -q`，473 passed，1 条既有 Starlette deprecation warning。
- `micromamba run -n qi-p0 npm --prefix frontend test -- --run`: 17/17 files，96/96 tests passed。
- `micromamba run -n qi-p0 npm --prefix frontend run build`: passed；仅既有 large-chunk warning。
- `micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list`: 2 tests / 2 files，中文裸根闭环和 P0 Workbench regression 均可发现。
- `QI_MVP_E2E_PDF`: 当前 shell 未设置，因此未执行依赖正式外部 PDF 的 Playwright closure。
- API `:8000`、现有 frontend `:3000` 和隔离 QA frontend `:3002` health 均成功。
- canonical Compose 的 postgres、redis、api、worker 正常；现有无关 `compose.yaml` host-port 改动仍使 canonical frontend container 无法绑定已占用端口，本轮未覆盖、未清理该改动。

### Remaining Findings And Conclusion

- Remaining P0: 0.
- Remaining P1: 0.
- Remaining P2: 极端密集图仍然天然拥挤；已通过默认降噪和 selected/related 强调缓解，但没有隐藏真实候选、来源或正式气泡。
- Product Design direction: 保持白色、浅灰、工程蓝、无 Logo、无紫色/渐变/玻璃拟态；PDF 仍为最大工作区，表格、SIP 和导出层级与参考方向一致。
- Truthfulness: 无可见内部 ID、静态假产品数据、静态假日志、虚假百分比或参考图写死字段；“公司处理记录”只显示真实事件或空状态。
- Final QA conclusion: passed。P0 为 0，Qwen Vision advisor 已进入 canonical runtime，上一轮全部 P1 已关闭；只保留不影响闭环的极端密度 P2。

## Successor Task 5 — Compact Workbench Workflow Header — 2026-07-24

### Scope And Visual Grounding

本轮只重做 ready workbench 顶部结构与视觉层级：文字品牌、五阶段流程和“处理另一份图纸”入口合并为单一轻量横向头部；原审核动作保留在项目摘要后的轻量操作区。没有修改步骤语义、snapshot 状态推进、保存/冻结/生成/确认事件或后端接口。

- source reference: `/tmp/codex-clipboard-PBmihd.png`
- source pixels: `1292x846`
- source SHA-256: `8b14544c48ad2e04ba007172c4bef5077c77279290ff0c5c3676b42f582b4d90`
- implementation route: `/?project_id=2d438ac8-7f3c-4661-9cab-a2bd2dba1c51&operator_id=reggi`
- browser: Google Chrome
- primary real-project viewport: `1900x953 / device scale 1`
- step-3 focused viewport: `1812x922 / device scale 1`
- responsive viewport: `800x826 / device scale 1`
- normalized comparison: `/tmp/qi-header-comparison-final.png`
- comparison pixels / SHA-256: `1832x945` / `1ec9b0b0bab7859a0b3b5c51c76d4d248e6630bf8d035d68711f0b50c9257f75`

comparison 将 source 与 implementation 顶部区域统一显示为 `1292px` 宽；两者均处于第 3 步“人工审核”状态。step-3 implementation 截图来自只用于 header 状态核验的兼容直达页，页头以下的项目错误不参与比较；真实 persisted project 则用于完整 workbench、状态推进和按钮交互核验。

### Findings And Iteration

- Initial P1: 已完成节点沿用旧绿色，仍带有当前后台样式痕迹。Fix: 完成节点和已完成连接线统一改为参考方向的工程蓝；连接线保持 `1px`，当前节点用轻量外环区分。
- Initial P1: compatibility query route 由 `main.tsx` 直接渲染 `ProjectWorkbenchApp`，新按钮首次真实点击时没有 reset callback。Fix: 该入口显式传入返回 `/` 的 callback；Chrome 再次点击后成功进入 PDF 上传页。
- Initial P2: ready 页面重复显示全局品牌标题、阶段卡片和 workbench 标题。Fix: 删除 ready 页旧 `.stage-rail` 与 `.workbench-header`，只保留单一 `WorkbenchWorkflowHeader`；审核操作迁到项目摘要后。
- Post-fix comparison: 未发现新的 P0、P1 或 P2。

### Fidelity And Layout

- Branding: 只保留“智检通 / 工程图纸智能检验”纯文字，header 内 `img, svg` count 为 `0`；没有参考图 Logo 或替代图形。
- Structure: desktop 使用 `brand | workflow | action` 单行 grid；实测 header 高 `76px`，没有旧式大卡片、圆角外框或粗分割线。
- Steps: 五个节点均保留标题与副文案；完成、当前、待开始分别使用实心蓝、蓝色外环、浅灰；状态仍由最新 workbench snapshot 推进。
- Hierarchy: 主标题 `21px`，副标题 `12px`；阶段标题 `12px`、说明 `10px`；右侧按钮高 `36px`，视觉权重低于流程。
- Responsive: `800px` 宽时品牌与按钮分列、流程占第二行；header 高 `137.1875px`，页面级横向溢出为 false，五段标题与副文案完整可读。
- Adjacent actions: 保存、冻结、生成和确认按钮顺序及 disabled 条件保持不变，只从重复标题栏移至项目摘要后的 `审核流程操作` region。

### Browser And Interaction Evidence

- real-project screenshot: `/tmp/qi-workflow-header-final.png`，`1900x953`，SHA-256 `5b51cb44a3efb01669adfae5073573b47ebd2f7874c3291ef976fda5f45139f8`
- step-3 screenshot: `/tmp/qi-workflow-step3-desktop-final.png`，`1812x922`，SHA-256 `0b8c9534fd419c51e87162b254e6755060c19e27b7f55928b7f51ccee87edb9b`
- responsive screenshot: `/tmp/qi-workflow-header-800x826-final.png`，`800x826`，SHA-256 `2fee1e6eacc67e5c53f8444e885ead1c02c8d89bc7f39e06892692b4a9249be4`
- real reviewed project: 当前阶段为“文件导出”，证明 reviewed result / successful export 仍驱动第 5 步。
- editing projection tests: 当前阶段为“人工审核”，冻结或气泡存在时进入第 4 步；未用外层固定值替代 snapshot Owner。
- Chrome actual click: “处理另一份图纸”从 compatibility query route 成功导航到 `/`，PDF 上传入口出现；随后恢复 persisted project preview。
- accessibility: banner 为“工程图纸检验流程”，navigation 为“检验处理阶段”，当前项带 `aria-current=step`；审核动作保留独立中文 region。
- legacy duplicate count: `.workbench-header,.stage-rail` 为 `0`。
- page horizontal overflow: none。
- console errors / warnings after final real-project navigation: `0 / 0`。

### Verification

- focused component tests: 3 files，35 tests passed。
- full frontend tests: 17 files，102 tests passed。
- production build: passed；仅保留既有 Vite large-chunk warning。
- Chrome smoke: desktop visual, responsive visual, snapshot-driven stage progression, reset navigation and console checks passed。
- screenshots and comparison artifacts remain under `/tmp` and are not committed。

### Result

- Remaining P0: 0.
- Remaining P1: 0.
- Remaining P2: 0.
- final result: passed

## Successor Task 6 — Pending Source Decision Card — 2026-07-24

### Scope And Visual Grounding

本轮只重做检验项列表下方“待判定来源处理”卡片的结构与视觉层级。`promote_source`、`ignore_source`、草稿更新、页码校验、禁用条件和上层保存流程均保持不变。

- source visual truth: `/tmp/codex-clipboard-qG7S5l.png`
- source pixels / density: `576x236 / 1x`
- source SHA-256: `1393c07563ee2def756818efbbfbb41c31d0170bf694b31f4371d9ad6122bd36`
- rendered implementation, incomplete state: `/tmp/source-review-implementation-v1.png`
- rendered implementation, complete state: `/tmp/source-review-implementation-v2.png`
- implementation screenshot pixels / density: `1885x985 / device scale 1`
- rendered card CSS size: `560x266.6875`
- browser viewport: `1900x953`
- normalized side-by-side comparison: `/tmp/source-review-comparison-final.png`
- comparison pixels / SHA-256: `1200x706` / `c126fa2f87fa00d529e3da8d10de6963f09bbdee79960a5a2cb457a345275413`
- comparison state: 原始标注为 `A`，检验类型未选择，添加按钮禁用；source 与 implementation 状态一致。

### Full And Focused Comparison

- Full-view evidence: 独立 Vite 预览在真实 `InspectionItemTable` 内同时显示来源行、分页和决策卡片，确认卡片与列表密度、背景和控制高度协调。
- Focused evidence: normalized comparison 将原始截图与实现卡片并排。组件本身就是本轮完整视觉范围，不需要额外更小的局部裁切。
- Initial comparison: 未发现 P0、P1 或 P2；因此没有为视觉 QA 进行第二轮生产代码修改。

### Fidelity Surfaces

- Fonts and typography: 沿用项目既有 Inter / 中文系统字体栈；标题 `13px/700`，辅助说明与状态标签降级为 `10px`，不再使用 fieldset legend 作为醒目的浮动标题。
- Spacing and layout rhythm: 卡片采用 `header / two-column field grid / action footer` 三段结构；字段统一为 `36px` 控件高度，第二行的范围选择与气泡开关实测同高 `57px`。
- Colors and tokens: 大面积橙色警告底替换为白色与浅灰；橙色只保留在“待判定来源”状态胶囊，主要动作使用既有 `--qi-blue`，边框继续复用中性灰体系。
- Image quality and assets: 本组件没有 Logo、图标、插画或其他图像资产；未新增 SVG、emoji、CSS 图形或占位资源。
- Copy and content: 保留全部业务字段与动作文案；新增一句简短说明和气泡行为提示，帮助用户理解当前决策，不改变字段含义。
- Accessibility: fieldset 的可访问名称继续为“待判定来源处理”；新增可见 `h3`，checkbox 和所有输入仍有原中文 accessible name；键盘 focus 样式继续继承全局 token。

### Interaction And Browser Evidence

- incomplete state: 未选择检验类型时“添加为检验项”保持禁用。
- complete state: 在真实浏览器渲染中将检验类型切换为“通用要求”后，主要动作立即启用并显示工程蓝；没有提交后端命令。
- component tests: 继续覆盖 `promote_source` 与 `ignore_source` 的完整 payload，新测试覆盖标题层级、字段网格、气泡开关和按钮顺序。
- real persisted workbench: `/?project_id=2d438ac8-7f3c-4661-9cab-a2bd2dba1c51&operator_id=reggi` 成功加载；该已完成项目没有待判定来源，因此只用于确认周边真实工作台无回归。
- console errors / warnings after final real-workbench navigation: `0 / 0`。
- 临时预览入口和对比资源已删除，未进入 Git。

### Verification

- focused test: `InspectionItemTable.test.tsx`，17 tests passed；新增测试先以缺少标题和分层结构的预期原因失败，再随实现转绿。
- full frontend tests: 16 files，108 tests passed。
- production build: passed；仅保留既有 Vite large-chunk warning。
- API verification: not applicable，本轮未修改 API 或后端行为。
- Chrome smoke: component incomplete/complete states、真实 workbench 加载和 console 检查 passed。

### Result

- Remaining P0: 0.
- Remaining P1: 0.
- Remaining P2: 0.
- final result: passed

## Unified SIP Information Panel — 2026-07-27

### Scope And Visual Grounding

本轮将参考图中左侧 `SIP基本信息` 与右侧 `所选检验项 SIP 确认` 收敛为右侧详情列中的唯一
`SIP 信息` 面板。参考图用于确认原有工程软件视觉语言、字段密度和两类 SIP 信息的内容；
批准设计明确要求改变信息架构，因此不把“仍然左右分栏”当作像素级匹配目标。

- source visual truth: `/tmp/codex-clipboard-yhU57R.png`
- source pixels / density: `654x630 / 1x`
- rendered implementation: `/tmp/qi-unified-sip-1565x796-panel-top.png`
- implementation pixels / density: `1565x796 / device scale 1`
- implementation CSS viewport: `1565x796`
- normalized comparison: `/tmp/qi-sip-reference-vs-implementation.png`
- normalized comparison pixels: `2219x796`
- normalization: 两张截图保持原始像素尺寸，参考图垂直居中补白到 `796px` 后横向并排；
  未缩放字体、表格或控件。
- state: 真实上传工程 PDF 的 Review Workbench；项目 metadata editor 收起，active 检验项
  已选中，左侧导出与处理辅助浮层收起。

### Full And Focused Comparison

- Full-view evidence: 并排图显示参考图的项目 SIP 摘要位于左侧浮层、当前项 SIP 位于右侧；
  实现将二者按“项目基本信息 / 当前检验项”层级置于同一右侧详情面板，并保留 PDF 为最大视觉
  区域、检验项列表密度和既有浅灰/工程蓝视觉体系。
- Focused evidence: `SIP 信息` 面板在 full-view 中字段标题、两列 metadata 摘要、折叠编辑入口
  和当前项表单均可读，因此无需额外裁切；`390x844` 截图另外验证 metadata 摘要收敛为单列，
  当前项表单自然续排且没有与“气泡操作”重叠。
- Initial comparison: 未发现 P0、P1 或 P2；视觉 QA 没有触发第二轮样式修复。

### Required Fidelity Surfaces

- Fonts and typography: 沿用参考图和现有工作台的中文系统字体、紧凑字号与加粗分区标题；
  `SIP 信息`、`项目基本信息`、`当前检验项` 层级清楚，长字段值使用既有截断和 title 行为。
- Spacing and layout rhythm: 面板使用右侧详情列完整宽度；两类 SIP 信息以分区和细分隔线组织，
  没有负 margin、固定截图坐标或页面级横向溢出。
- Colors and visual tokens: 继续复用既有白色、浅灰、细边框和工程蓝 focus/action token；
  没有新增渐变、阴影层级或与参考图不一致的装饰色。
- Image quality and assets: 本次没有新增或替换 Logo、图标、插画和图片资产；PDF canvas 与气泡
  overlay 保持原渲染路径。
- Copy and content: `编辑项目 SIP 信息`、`确认项目 SIP 信息`、`确认当前检验项 SIP` 与
  `展开导出与处理信息` 明确区分项目级、当前项和辅助导出职责；待判定来源显示明确空态。
- Accessibility: 唯一外层 `region` 名称为 `SIP 信息`，两个分区使用 heading/region；
  表单 accessible name 保留当前 item identity，空态不只依赖颜色或 disabled。
- Responsiveness: `1565x796`、`1240x796`、`768x900`、`390x844` 均无页面级横向溢出；
  `390px` 宽时 metadata 摘要从两列变为单列。

### Interaction And Browser Evidence

- 真实上传 PDF 后确认页面只有一个 `SIP 信息` region，且位于
  `.inspection-review-workspace__detail`；旧左侧 SIP 卡片不存在。
- 项目 metadata 与当前检验项 SIP 均验证修改、取消、成功保存、断网失败、草稿保留和联网重试。
- 当前项 draft 在 item 切换后返回仍保留；选择待判定来源时项目基本信息继续显示，当前项分区
  改为“当前选择的是待判定来源。”且不渲染可提交表单。
- 浏览器发现外部成功文案会遮蔽后续本地 dirty 状态；已补充优先级修复与回归测试，修复后真实
  浏览器在编辑时显示“有未保存修改”。
- reviewed / frozen 的双 fieldset 禁用由 component tests 覆盖；当前真实 124 项项目无法在不改变
  业务数据的情况下完成整条 freeze/export 流程，因此没有伪造 live reviewed/frozen evidence。
- console error 检查在排除两次刻意断网失败后无未解释错误；正式导出生命周期未修改。

### Findings And Comparison History

- Remaining P0: 0.
- Remaining P1: 0.
- Remaining P2: 0.
- P3 follow-up polish: none required for this scope.
- P0/P1/P2 visual iterations: none；初次同图比较已通过。
- focused test gap: 当前真实项目不具备可快速到达的 reviewed/frozen/export 完成态；这些状态由
  component tests 和未修改的 export owner 覆盖。
- final result: passed

## Review Action Semantics — 2026-07-28

### Scope And Visual Grounding

本轮将用户批准的方案 A 落到真实 `ReviewPanel` 操作栏：按“检验结论 / 内容调整 /
气泡标记”分组，常驻解释“排除”和“无需气泡”的不同后果，并为“排除”增加行内确认。

- source visual truth:
  `.local/design-qa/review-action-semantics-source-options.png`
- source pixels / density: `1380x990 / device scale 1`
- rendered implementation:
  `.local/design-qa/review-action-semantics-confirmation.png`
- implementation pixels / density: `1317x643 / device scale 1`
- responsive focused implementation:
  `.local/design-qa/review-action-semantics-narrow-actions.png`
- responsive pixels / CSS viewport: `800x790 / 800x790`
- same-input comparison:
  `.local/design-qa/review-action-semantics-comparison.png`
- comparison pixels: `1365x1571`
- state: 真实 editing project 的第一个 active 检验项；宽屏证据打开“排除”确认，窄屏
  证据保持默认操作栏。
- normalization: source 是三方案概念板，implementation 是真实 workbench，二者不是同一
  页面构图；比较图按卡片等宽并排，判断范围限定为方案 A 的语义分组、常驻说明、危险确认
  与窄屏可读性，不进行全页像素匹配。

### Full And Focused Comparison

- Full-view evidence: 同图对比确认真实实现保留方案 A 的三个关键决策：动作按语义分组、
  “排除 / 无需气泡”后果常驻显示，以及“排除”确认块紧邻危险按钮。
- Focused evidence: `800x790` 截图显示现有 responsive breakpoint 下 command rail 位于
  表单右侧，三组标题、按钮和两条说明均可读，内部与页面级均无横向溢出。
- Intentional adaptation: 概念板为较宽的双列按钮；真实 rail 宽约 `166px`，因此沿用产品
  原有竖向按钮节奏，避免为匹配概念稿扩大右栏或压缩检验字段。
- Initial comparison: 未发现 P0、P1 或 P2；未触发视觉修复迭代。

### Required Fidelity Surfaces

- Fonts and typography: 沿用现有中文系统字体、`11px` 操作文字和加粗 legend；说明使用
  `10px / 1.4`，在 `166px` rail 和 `800px` 窗口中仍可读。
- Spacing and layout rhythm: 三个 fieldset 使用一致的 `7px` 内部 gap 与细边框；确认块在
  “检验结论”内自然增高，不遮挡 SIP 面板、检验项列表或页面滚动。
- Colors and visual tokens: 普通操作复用既有白色和工程蓝；危险按钮与确认块使用低饱和红棕
  边框/底色，未增加渐变、强阴影或新的全局 token。
- Image quality and assets: 本次没有新增 Logo、图标、插画或图片资产；PDF canvas 和气泡
  overlay 未修改。
- Copy and content: 常驻文案准确区分“排除不进入 SIP”和“无需气泡仍进入 SIP”；确认文案
  明确说明正式 SIP、图纸气泡与原始识别记录的后果。
- Accessibility: 三组操作通过 fieldset/legend 暴露可访问名称；确认块为 `alertdialog`，
  打开后焦点进入“取消排除”，取消后返回“排除”；不只依赖颜色表达危险。

### Interaction And Browser Evidence

- Chrome MCP 在真实 workbench 打开“排除”确认后，network inventory 没有
  `/review/commands` 请求，证明首次点击不会立即提交。
- 点击“取消排除”后确认块消失，焦点返回 `排除检验项：3.2`；没有改变项目数据。
- focused unit tests 覆盖取消、Escape、失败保留、成功重试和现有 exclude payload；
  “设为无需气泡”继续一次点击发送既有 command。
- 宽屏 `1317x643` 与窄屏 `800x790` 均无操作栏溢出。
- console errors / warnings: `0 / 0`。

### Verification And Result

- focused tests: `ReviewPanel.test.tsx` 与 `InspectionWorkbench.test.tsx`，
  `49/49` passed。
- full frontend tests: `19` files，`165/165` passed。
- production build: passed；仅保留既有 Vite large-chunk warning。
- API verification: not applicable，本轮未修改 API 或 backend 行为。
- Chrome smoke: persistent copy、confirmation open/cancel、no premature command、
  focus return、responsive layout 和 console 检查 passed。
- Remaining P0: 0.
- Remaining P1: 0.
- Remaining P2: 0.
- P3 follow-up polish: none required for this scope.
- comparison history: 初次同图比较通过，无 P0/P1/P2 修复迭代。
- final result: passed
