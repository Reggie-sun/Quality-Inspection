# Optional Material And Formal Readiness Specification

## Problem

项目 SIP 当前把 `material` 与物料编码、产品名称、图号、版本号一起作为五个必填字段。图纸未标注材质时，用户只能写入 `none` 之类占位值才能继续，导致正式结果含有伪数据。

旧 working copy 还可能保留当前 `review-source-default/1` 已会自动判定为非检验来源的无候选 coverage 条目。这些条目继续计入人工审核并阻断 freeze；正式文件区域只显示“尚未审核”，无法区分真实待审核项、待选择气泡和历史误阻断。

## Approved Behavior

- 保留稳定的五字段 `set_sip_metadata` command 和 SIP/manifest 输出形状。
- `material_code`、`material_name`、`drawing_number`、`revision` 继续必填。
- `material` 改为可选字符串；空字符串表示图纸未标注，UI 显示为空态，Excel/manifest 保留该列/键但写入空值。
- 历史精确 sentinel `none` 在项目继续处理时归一化为空字符串，不再作为已知材质导出；其他大小写文本不自动改写。
- 旧 working copy 中无 candidate、且不属于技术要求来源的待确认 coverage 条目，继续由唯一规则 `review-source-default/1` 收敛为 `non_inspection`；不得自动处理技术要求来源或真实候选检验项。
- 正式文件区域优先显示剩余人工动作数量，包括待审核检验项和待选择气泡；不再用“尚未审核”掩盖可操作原因。
- “待审核检验项”只统计 active item，不混入技术要求来源或 source-only coverage 计数。
- 真实 `requires_confirmation` 项和 `balloon_required is None` 项仍必须由用户处理，不得自动确认。
- 已确认的空材质优先于后续识别 suggestion，刷新或下一次保存不得静默回填。
- 技术要求终态的“进入检验项审核”会选中目标并把焦点交给检验项审核区，避免点击无反馈。

## Owner And Contract Boundary

- 单一业务 Owner：`backend/app/review/service.py::ReviewService`。
- schema Owner：`backend/app/review/schemas.py`，负责五字段 transport shape 与 required/optional 划分。
- export consumer：`backend/app/exports/service.py` 只消费已确认 snapshot，不建立第二套必填规则。
- frontend 只投影后端契约并展示 blocker，不拥有自动通过语义。

## Failure Boundary

- 缺少任一四个必填 metadata 字段时，freeze/confirm/export 仍阻断。
- `material` 类型不是字符串、metadata 缺键或出现额外键时仍拒绝。
- 技术要求来源、候选关联 coverage、真实待人工检验项和未选择气泡仍阻断。
- malformed 历史 coverage 不得自动归类为 `non_inspection`；读取投影保持可用，freeze 以既有 `coverage_blocking` 失败且不持久化归一化副作用。
- 归一化不得改变 frozen/reviewed result 的条目集合、编号或气泡状态。

## Rollback

回退本次单一提交即可恢复旧契约；不执行数据删除或不可逆 migration。若发生 rollback，第一项验证为：

```bash
make check-contracts
```

随后运行后端 review/export focused tests 与前端 workbench focused tests，确认旧五字段必填行为完整恢复。

## Acceptance

- 空 `material` 的 command、freeze、confirm 和 export 路径通过，缺少四个必填字段仍失败。
- 当前项目读取时不再展示 `none`，旧的 106 条安全可归一化来源不再计入人工审核。
- 当前项目仍明确显示真实的 13 个待审核检验项和 4 个待选择气泡；完成这些动作后原有自动 freeze/balloon/finalize 流程可继续。
- contract、backend、frontend、build、targeted API 和 Chrome smoke 均通过。
