# Candidate Balloon Numbering Design

## Context

中文 PDF 上传 MVP 已能从裸 `/` 完成上传、识别、审核、冻结、气泡生成与正式导出。但真实浏览器复现表明：识别完成进入 Review Workbench 时，backend 尚未生成正式 `BalloonRecord`，页面虽然已有候选框和来源框，却显示“0 个有效气泡”，图纸与检验项列表的气泡号均为“—”。

正式编号必须继续遵守现有业务顺序：

```text
人工审核
→ 冻结检验项
→ backend 生成正式气泡及编号
→ 调整气泡
→ 确认 reviewed result
→ 正式导出
```

因此不能通过上传后自动冻结、提前创建正式编号或由 frontend 写入正式气泡数据来解决该问题。

## Goal

识别完成进入审核工作台后，立即为有效检验项显示可辨识、可选择的蓝色候选序号。正式气泡生成后，同一检验项只显示 backend 拥有的红色正式编号。

最终用户状态转换为：

```text
识别完成
→ 蓝色候选序号可见
→ 审核与冻结
→ 红色正式序号替换候选序号
→ 正式 PDF 使用 backend 正式编号
```

## Non-Goals

- 不自动执行审核、冻结或正式气泡生成。
- 不改变 Review command、freeze gate、编号算法、气泡几何、碰撞判断或导出逻辑。
- 不向 backend 写入候选序号。
- 不把候选序号写入带气泡 PDF、SIP Excel 或 manifest。
- 不增加新的 API、schema、数据库字段、状态枚举或依赖。
- 不把 frontend 提升为正式编号 Owner。

## Ownership

正式编号 Owner 保持为 backend balloon generation：

- `BalloonRecord.formal_number` 是冻结后正式编号真相。
- `BalloonRecord.suggested_number` 只按现有 backend 语义使用。
- PDF、Excel 和 manifest 继续只消费 immutable `reviewed_result` 对应的正式气泡。

frontend 新增的候选序号只是派生显示值：

- 来源为当前 `ReviewWorkingCopy.items` 的稳定顺序。
- 只为 `active === true` 的检验项分配连续正整数。
- 不持久化，不通过 API 提交，不视为 formal number。
- working copy 变化时可以重新计算，界面必须明确使用蓝色候选样式。

## UI Behavior

### Candidate Marker

每个具有候选框且尚无 active 正式气泡的有效检验项，在候选框右上方显示一个紧凑蓝色圆形序号：

- 白色数字、工程蓝边框和浅蓝底色。
- 使用候选框的 PDF 坐标定位，并限制在页面边界内。
- 点击候选序号与点击候选框使用同一 item selection 路径。
- 选中时通过更粗描边和可见选中状态增强，不只依赖颜色。
- accessible name 使用中文，例如“候选气泡 12”。

来源标注继续使用青色虚线框，不附加候选编号。候选框继续保留，便于显示原始识别范围。

### Formal Replacement

当某检验项存在 `status !== "deleted"` 的正式 `BalloonRecord` 时：

- 隐藏该检验项的蓝色候选序号。
- 显示现有红色正式气泡和 backend 编号。
- 不同时显示两个编号，避免误认为存在重复气泡。

若正式气泡被删除且该检验项仍然有效，候选序号可重新出现，提示该项目尚无有效正式气泡；重建仍使用现有 backend command。

### Inspection List And Selection Summary

检验项列表的气泡号列按以下优先级显示：

1. active 正式气泡编号；
2. 蓝色候选序号；
3. “—”。

选中项摘要使用相同优先级。候选序号必须带有候选视觉样式或中文辅助名称，不能冒充正式编号。

## Data Flow

```text
ReviewWorkingCopy.items
→ frontend 过滤 active items
→ 按 working copy 顺序派生 item_id → candidate number
→ ProjectWorkbenchApp 将号码关联到 candidate overlay
→ PdfWorkspace / OverlayLayer 渲染蓝色候选序号
→ InspectionWorkbench 将同一映射传给列表和选中项摘要

backend BalloonRecord
→ 若存在 active balloon
→ OverlayLayer 隐藏对应候选序号
→ 列表和摘要优先显示正式编号
```

候选序号映射应由一个纯函数生成，PDF overlay、列表和摘要共同消费，避免各区域独立编号而产生漂移。

## Failure Handling

- candidate 缺少 `itemId`：只显示现有候选框，不显示序号。
- candidate 对应 excluded item：不显示候选序号。
- 同一 item 存在多个候选框：所有框关联同一候选序号，但只允许一个可访问编号标记，避免重复朗读；优先使用该 item 的第一个稳定候选。
- 正式 balloon number 非法或缺失：沿用现有正式气泡验证与阻塞逻辑，不使用候选序号掩盖错误。
- 页面变换矩阵无效：继续使用现有 fatal render behavior，不新增静默 fallback。

## Accessibility

- 候选序号使用中文 `aria-label`。
- 可通过点击和现有键盘选择路径定位对应检验项。
- 颜色之外同时使用文本、圆形形状和选中描边表达状态。
- 不改变现有 `focus-visible`、`aria-live` 或 fatal error 行为。

## Allowed Paths

Task 6 implementation 只允许修改：

- `frontend/src/api/types.ts`
- `frontend/src/copy/zhCN.ts`
- `frontend/src/components/workbench/candidateNumbering.ts`
- `frontend/src/components/workbench/candidateNumbering.test.ts`
- `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.tsx`
- `frontend/src/components/workbench/InspectionWorkbench.test.tsx`
- `frontend/src/components/workbench/InspectionItemTable.tsx`
- `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- `frontend/src/components/pdf/OverlayLayer.tsx`
- `frontend/src/components/pdf/OverlayLayer.test.tsx`
- `frontend/src/styles/workbench.css`
- `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`

不得修改 backend、contract matrix、历史 receipt、run evidence、旧七天计划或已完成的 successor Task 1～Task 5 语义。

## TDD And Verification

实施必须遵循 RED → GREEN：

1. 纯函数测试：有效项连续编号、排除项跳过、顺序稳定。
2. Overlay 测试：无正式气泡时显示候选序号；有 active 正式气泡时隐藏候选序号；点击保持 item selection。
3. Table 测试：正式编号优先于候选序号，候选序号不显示为内部 ID。
4. Workbench 测试：PDF、列表和摘要使用同一映射。
5. Browser smoke：裸 `/` 上传真实矢量 PDF，识别完成、冻结前即可观察到正整数候选序号；完成正式生成后候选序号被正式序号替换。

验证命令：

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
QI_MVP_BASE_URL=http://127.0.0.1:4173 \
QI_MVP_E2E_PDF=/tmp/qi-task5-real.pdf \
micromamba run -n qi-p0 npm --prefix frontend run e2e -- \
  e2e/chinese-pdf-upload-mvp.spec.ts
python .agent/harness/scripts/check-contracts.py
git diff --check
```

真实浏览器验收使用 Chrome、1565×796、`zh-CN`，并检查 Console 和 Network 无未解释错误。

## Rollback

Task 6 使用独立提交。若需要回滚，执行该提交的常规 `git revert`；第一项验证为：

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
```

回滚只移除 frontend 候选序号显示，不影响正式编号、历史项目、数据库或导出产物。
