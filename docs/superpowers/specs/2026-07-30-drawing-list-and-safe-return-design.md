# Drawing List And Safe Return Design

**Status:** Superseded on 2026-08-01 by `2026-08-01-server-backed-drawing-list-design.md`. This file is a historical record of the browser-local design and must not be used as the current drawing-list runtime contract.

## Goal

把根地址 `/` 从“单次上传入口”升级为当前浏览器的图纸任务首页。用户可以保留并继续处理多个已上传项目，从工作台返回列表时不会静默丢失本地草稿。

本次采用用户批准的方案 A：浏览器本机目录。后端项目、审核、气泡和导出仍是正式业务结果 Owner；`localStorage` 只保存进入这些项目所需的本机导航信息。

## Scope

### Included

- 根地址默认展示图纸列表和“上传新图纸”入口。
- 每次成功创建项目后，把项目 ID、上传文件名和本机时间登记到本机目录。
- 目录支持多个项目，刷新浏览器后仍保留。
- 列表按最近打开时间倒序展示。
- 列表逐项读取既有项目状态接口，显示处理中、可继续审核或处理失败。
- 点击列表项进入对应的处理进度或审核工作台。
- 工作台按钮改为“回到图纸列表”。
- 没有本地未保存修改时直接返回。
- 有本地未保存修改时显示“保存并返回 / 不保存返回 / 取消”。
- 保存失败时留在当前工作台，并保留仍未成功提交的草稿。
- 兼容带 `project_id`、`operator_id` 的旧工作台深链。

### Excluded

- 不新增数据库字段、migration 或项目列表 API。
- 不做跨浏览器、跨设备或跨用户同步。
- 不做项目删除、归档、重命名、搜索、分页或批量操作。
- 不改变 review、freeze、balloon、confirm、export 的后端语义和顺序。
- 不把本机目录当作项目存在、审核完成或正式文件成功的业务证据。

## Information Architecture

根地址使用一个首页壳：

1. 顶部产品身份与“上传新图纸”主按钮。
2. 图纸列表：
   - 图纸名称：优先显示上传时记录的文件名。
   - 状态：来自既有 `GET /api/v1/projects/{project_id}/status`。
   - 最近打开：来自本机目录。
   - 操作：`继续处理` 或 `查看进度`。
3. 空列表状态：
   - 显示“还没有图纸任务”。
   - 提供上传入口。
4. 上传状态继续复用现有 PDF 选择、校验、上传、轮询和错误处理，不创建第二套 intake 流程。

上传面板可以在首页内展开；取消上传返回列表，不删除已登记项目。成功创建项目后立即登记目录，并沿用现有轮询流程进入工作台。

## Local Drawing Registry

### Owner

新增一个纯前端 registry 模块，作为本机目录唯一读写 Owner。`QualityInspectionApp` 只消费其经过校验的结果，不直接拼接或修改原始 JSON。

### Storage Contract

`localStorage` key 固定为 `qi.drawing-list.v1`，值为：

```ts
type LocalDrawingEntry = {
  projectId: string;
  fileName: string;
  createdAt: string;
  lastOpenedAt: string;
};
```

约束：

- `projectId` 必须是合法 UUID。
- `fileName` 必须是去除首尾空白后的非空字符串。
- 时间必须是合法 ISO 8601 字符串。
- 同一 `projectId` 只保留一条，新增或再次打开时原地更新。
- 读取到损坏 JSON 或非法条目时忽略非法部分并返回其余合法数据，不阻断应用启动。
- 写入失败时不阻止已成功创建的后端项目；页面显示“本机列表未能保存”，但仍可继续当前项目。

### Compatibility

- 旧 `sessionStorage` 当前项目仍可在升级后的首次加载中打开。
- 如果当前项目不在本机目录且没有文件名，登记为 `未命名图纸.pdf`，仅用于本机导航。
- 旧深链继续接受明确的 `project_id` 和 `operator_id`；返回列表时把该项目加入本机目录，名称使用上述安全占位。

## Project Status Projection

列表对每个本机条目调用既有 `getProjectStatus()`：

- `queued` / `processing`：处理中，并显示既有阶段文案。
- `ready_for_review` / `partial_review_required`：可继续审核。
- `failed`：显示安全的中文失败状态和可重试提示，不泄漏后端原始错误。
- 状态请求失败：显示“状态暂不可用”，保留列表项和继续重试入口。

列表状态只是导航投影。是否可以打开工作台继续由既有 `workbench_ready` 和现有轮询 Owner 决定。

## Navigation And Unsaved Changes

### Button Contract

工作台头部按钮文案统一为“回到图纸列表”。它不再切换到一个临时上传页，也不再依赖“返回当前图纸”的互斥状态。

### Dirty Owner

`InspectionWorkbench` 已汇总以下本地 dirty 状态，因此继续作为离开保护 Owner：

- 检验项编辑草稿。
- 待判定来源草稿。
- 当前检验项 SIP 草稿。
- 项目 SIP metadata 草稿。

子编辑器不得直接执行页面跳转。

### Return Decision

- `localDraftDirty=false`：直接调用列表导航回调。
- `localDraftDirty=true`：打开应用内确认对话框：
  - `保存并返回`
  - `不保存返回`
  - `取消`
- `取消`：关闭对话框，保留所有草稿。
- `不保存返回`：丢弃当前组件树中的本地草稿，返回列表；后端已成功保存的数据不回滚。
- `保存并返回`：
  1. 按现有 command seam 顺序提交各 dirty editor 的当前草稿。
  2. 每个提交完成刷新后，下一个提交必须读取最新 working-copy version；不得复用第一次提交前的 stale version。
  3. 每个提交继续使用 active lock 和既有 structured failure。
  4. 全部成功后才返回列表。
  5. 任一提交失败立即停止，不跳转；成功部分保持已保存，失败和未执行部分继续留在当前工作台。

保存不得通过 DOM click、隐藏按钮、synthetic event 或新建批量后端 API 实现。各编辑器通过显式、可测试的 draft-save contract 向 `InspectionWorkbench` 暴露当前 dirty 草稿及保存动作，最终仍调用唯一 `submitCommand()`。

## Component Boundaries

### `localDrawingRegistry`

- 校验、读取、登记、触碰最近打开时间。
- 不发网络请求。
- 不判断业务状态。

### `DrawingListScreen`

- 展示条目和状态。
- 触发打开项目或展开上传入口。
- 不创建、修改或确认审核结果。

### `QualityInspectionApp`

- 保持项目创建、状态轮询和 screen 路由 Owner。
- 成功创建项目后登记本机目录。
- 打开列表项时设置当前项目并更新最近打开时间。
- 接收工作台“已允许返回”事件并切换到列表。

### `InspectionWorkbench`

- 汇总 dirty 状态。
- 拥有返回确认对话框。
- 编排显式 draft-save contracts。
- 不直接读写 `localStorage`。

## Error Handling

- 本机目录损坏：忽略非法条目，首页仍可使用。
- 本机目录写入失败：当前后端项目继续有效，显示非阻断警告。
- 单个项目状态失败：只影响该行，不阻断其他项目。
- 保存并返回失败：不跳转、不清空草稿，显示既有安全错误。
- 项目不存在：列表项显示不可用；本次不提供删除功能。
- 上传失败：沿用当前安全错误和重试策略，不生成目录条目。

## Accessibility

- 图纸列表使用带可访问名称的 `table` 或语义化列表。
- 每一行的打开按钮包含图纸名称。
- 对话框使用 `role="dialog"`、明确标题和说明，打开后聚焦“保存并返回”。
- `Escape` 等同取消；对话框打开时焦点不能落到背景工作台。
- 状态变化通过现有 `role="status"` 或行内可读文字表达，不只依赖颜色。

## Verification

### TDD

1. 本机 registry：
   - 多项目登记与去重。
   - 损坏 JSON 和非法条目过滤。
   - 最近打开排序。
2. 首页：
   - 默认显示多个图纸。
   - 新上传项目加入列表且不覆盖旧项目。
   - 点击项目恢复处理或工作台。
   - 单行状态失败不影响其他行。
3. 安全返回：
   - 无 dirty 直接返回。
   - dirty 时三选项出现。
   - 取消保留草稿。
   - 不保存返回不发保存请求。
   - 保存并返回成功后跳转。
   - 保存失败时不跳转且保留失败草稿。
4. 兼容：
   - 旧 session 当前项目。
   - 带 project/operator 的旧深链。

### Runtime

- 全量 frontend tests。
- production build。
- Chrome smoke：
  1. 首页上传第一份图纸。
  2. 返回列表。
  3. 上传或打开第二份图纸。
  4. 确认两份图纸都在列表中。
  5. 在工作台制造未保存修改，分别验证取消、保存失败和成功返回路径。

## Rollback

本功能使用独立提交。回滚时恢复原单项目入口、旧按钮与旧本机 context helper；后端项目、审核 working copy 和正式产物不受影响。回滚后的第一项验证为 frontend focused tests，随后运行 production build。
