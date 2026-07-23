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
