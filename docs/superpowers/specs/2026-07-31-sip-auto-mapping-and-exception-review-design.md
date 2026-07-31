# SIP Auto-Mapping And Exception Review Design

## Status

- Date: `2026-07-31`
- Status: `awaiting user review`
- Selected lane: `Heavy`
- Selected plan: 尚未创建 implementation plan；本 spec 获批后使用
  `superpowers:writing-plans` 建立唯一 current plan。
- Selection evidence: 用户选择“检验项只审核一次，SIP 自动映射，仅异常人工处理”，
  并明确指出 SIP 是导出表格，不应对同一检验项再做第二遍业务判断。用户同时选择
  “规则预填 + 批量确认”：检测方法按版本化类型规则建议，检验角色在项目内选择一次
  后批量应用。
- Validation action: `replan`；替代
  `2026-07-31-title-block-sip-prefill-and-confirmation-guidance-design.md`
  中“所有 active item 逐条确认 SIP”的部分，不改变该 design 的标题栏识别 Owner。
- Writer ownership and order: 主线程是唯一 writer；先完成 SIP mapping Owner 与
  backend readiness contract，再完成 frontend exception flow，最后迁移当前真实
  working copy 的可修复路径。explorer、auditor 和 reviewer 始终只读。
- Next verification: spec 获批后先写 backend RED，证明规则可完整映射的 item 不再因
  缺少逐条人工确认而阻止 freeze。

## Context

当前实现把以下三个 decision dimensions 压缩进同一流程：

1. candidate 是否被识别为检验项；
2. item 是否保留为正式检验项；
3. SIP 六个导出字段是否逐条人工确认。

前两个维度已由 `ReviewService` 的 item lifecycle、`keep / exclude / merge / split`
commands 和 `active` state 拥有。第三个维度又要求每个 active item 单独提交
`set_sip_detail_fields`，导致当前真实项目的 115 个 active items 被投影为 115 次
SIP 人工确认。

实时证据显示，115 个 active items 包含 94 个 `auto_accepted` 和 21 个人工 `kept`。
它们是图纸不同坐标的尺寸或工程要求，不能仅因文本相同自动合并。当前标题栏识别也已
返回物料编码、产品名称、图号和版本建议，但 persisted 非空值会让这些建议在 UI
完全不可见。

SIP 的业务职责应收敛为：

```text
confirmed inspection item set
  -> deterministic SIP field mapping
  -> exception detection
  -> fixed Excel export
```

SIP 不再拥有独立的“是否纳入正式集合”判断。

## Approved Product Behavior

### Single Review Owner

- `ReviewService` 中既有 item review 是正式检验项集合的唯一 Owner。
- `active=true` 继续表示 item 仍处于正式 review lifecycle；`exclude` 和
  `superseded` 继续令 item inactive。
- 不新增 `sip_included`、`sip_eligible` 或第二套 membership state。
- candidate 的人工保留、排除、merge 和 split 仍只做一次；SIP 不重复询问是否纳入。
- 相同文字但来源坐标不同的 items 不自动合并；只保留既有显式 `merge` command。

### Automatic SIP Mapping

新增唯一版本化规则 Owner：

`backend/app/review/sip_mapping.py`

规则输入只包括已结构化 item、technical requirement suggestion、source page 和用户
选择的项目默认检验角色；不得重读 PDF、调用 Provider 或从 Excel 反推语义。

首版字段优先级：

1. 已有人工 resolved 值；
2. 已确认 technical requirement 形成的字段建议；
3. item 结构化字段和 `sip-auto-map/1` 类型规则；
4. 用户一次选择并批量应用的默认检验角色。

首版自动映射：

| SIP 字段 | 规则 |
| --- | --- |
| `inspection_item` | 使用 item type label、`normalized_text` 和 quantity 形成可读检验项目；global requirement 使用确认后的 requirement 原文 |
| `inspection_standard` | 优先使用已确认 technical requirement suggestion；否则为 `图纸要求` |
| `inspection_method` | linear/diameter=`游标卡尺`；thread=`螺纹规`；radius=`半径规`；angle=`万能角度尺`；general requirement=`目视`；composite 或未知类型进入异常 |
| `key_dimension` | 存在明确 critical/重点标记或已确认 requirement 值时为 `是`；否则使用版本化默认 `否` |
| `inspection_role` | 使用用户在当前项目一次选择的默认角色；不得由 OCR/LLM 猜测 |
| `source_page` | 使用 canonical zero-based `page_index + 1`；缺少有效 source page 时进入异常 |

`inspection_method` 规则是首版可编辑建议，不宣称来自图纸识别。任何 item 仍可通过既有
`set_sip_detail_fields` 修改单行最终值。

### One Project-Level Apply Action

frontend 在 SIP 区提供一个项目级“默认检验角色”输入和
`自动填写 SIP 表格` action。该 action 提交一个 versioned batch command：

```json
{
  "type": "apply_sip_defaults",
  "inspection_role": "IPQC"
}
```

command 在同一 `ReviewWorkingCopy` transaction 内：

- 对全部 active items 计算 mapping；
- 不覆盖已由人工 `set_sip_detail_fields` 保存的字段；
- 合并已确认 technical requirement suggestions；
- 把可完整解析的行标记为 export-ready；
- 把不完整或冲突行保留为 exception；
- 只增加一次 working-copy version；
- 记录一个 operation record，不生成 115 个伪人工操作。

后续 add、promote、edit、merge、split 或 technical requirement remap 若使 item 字段
变化，已有 SIP 值按现有规则失效；UI 显示新 exception，并允许再次执行同一批量 action
或单行修改。批量 action 不属于新的业务准入判断。

### Exception-Only UI

原来的 `检验项 SIP 已确认 x / y` 和 `处理下一条未确认 SIP` 执行 `replace`：

- 摘要显示 `SIP 表格：已自动填写 N，异常 M`；
- `M=0` 时不展示逐条 SIP action；
- `M>0` 时只提供 `处理下一条异常`；
- 异常原因必须明确，例如：`未知检验项类型`、`复合项需要选择检测方法`、
  `缺少来源页码`、`自动建议与人工值冲突`；
- 单行修改仍使用既有 `set_sip_detail_fields` command；
- 不出现要求用户对 115 行逐条点击“确认”的流程。

### Project Metadata Conflict Visibility

标题栏 suggestion Owner 和 `set_sip_metadata` confirmed Owner 保持不变。frontend
显示层调整为：

- persisted value 与 recognized suggestion 相同：显示“图纸识别一致”；
- persisted value 与 suggestion 不同：并列显示“当前值 / 图纸识别值”以及
  `采用识别值` action；
- suggestion 不得静默覆盖 persisted value 或 dirty draft；
- 没有证据的材质继续是人工异常；
- 采用建议只更新本地 draft，仍由一个项目级保存 action 提交。

## Goals

- 让检验项只进行一次保留/排除判断。
- 把 SIP 从第二套审核流程还原为 reviewed items 的确定性导出映射。
- 让规则可确定的绝大多数行自动填好。
- 把人工操作限制到项目默认角色选择和真实异常。
- 让标题栏识别结果即使与旧值冲突也可见、可采用。
- 保持 PDF、Excel 和 manifest 对同一 immutable `reviewed_result_id` 的一致性。

## Non-Goals

- 不按相同尺寸文字自动合并不同坐标或不同视图的 items。
- 不让 OCR、LLM 或 Provider 决定正式检验项、检测方法或检验角色。
- 不建立 P1 可配置质量规则后台。
- 不自动覆盖人工修改或已发布 `ReviewedResult`。
- 不修改固定 Excel 模板、列 mapping 或 formal balloon numbering。
- 不把 SIP exception 解释为 candidate review-required。

## Problem Boundary And Ownership

### Changed Decision Dimension

变更的唯一 dimension：

`active reviewed item -> resolved SIP export fields or explicit exception`

### Roles

- `ReviewService` item lifecycle：`Owner`，继续提交正式 active item set。
- `sip_mapping.py`：SIP field mapping `Owner`，只提交字段建议、provenance 和 exception。
- `apply_sip_defaults`：`Executor`，在 working-copy transaction 中应用 Owner 结果。
- frontend：`Presenter`，显示 batch action、provenance 和 exceptions，不重算规则。
- freeze：`Veto Gate`，只检查 active items 是否 export-ready 或存在 exception。
- export：`Executor / Validator`，只读取 reviewed result 中已 resolved 的字段。

### Old Path Action

- “每个 active item 必须逐条点击确认”执行 `replace`：改为 mapping 完整即
  export-ready，异常才要求单行处理。
- `set_sip_detail_fields` 执行 `preserve`：它仍是人工覆盖单行字段的唯一 command。
- `sip_detail_fields_confirmed` 暂时 `preserve` 为内部 export-readiness bit：
  automatic mapping 和人工修改都可以使其为 true；UI 不再把它描述为“人工确认”。
- `active` 的正式 item-set 职责执行 `preserve`；不叠加 SIP membership Owner。
- frontend 隐藏冲突 suggestion 的路径执行 `replace`：改为 confirmed-first 但冲突可见。

## Failure Boundaries

- 未选择默认检验角色：mapping 可以预览其他字段，但 active rows 保持 exception，阻止
  formal freeze。
- unknown/composite item type：不猜测检测方法，保留单行 exception。
- source page 缺失或越界：不使用用户界面序号猜测，保留 exception。
- technical requirement suggestion 冲突：不选择任一标准，保留 exception 并显示来源。
- 已有人工 resolved fields：batch action 不覆盖；若自动 suggestion 不同，只显示冲突。
- batch command version conflict：整批失败，不产生部分 rows 或多个 versions。
- add/edit/merge/split 后规则输入变化：清除旧 readiness，并重新进入 exception/mapping。
- historical `ReviewedResult` 和已发布 artifacts：保持 immutable，不迁移、不回写。

## Data And Compatibility

- `ReviewWorkingCopy.items` 继续承载 resolved SIP fields、
  `sip_detail_fields_confirmed` 和 provenance；不新增数据库列。
- 新增 `apply_sip_defaults` review command，属于稳定 write API schema 变更。
- 已存在 working copies 不在读取时执行 hidden fallback。用户首次点击 batch action 时，
  通过同一事务显式写入自动映射结果。
- 新 working copy 可以预计算 suggestion/exception，但没有默认角色时不得伪造
  export-ready。
- OpenAPI snapshot 和 generated TypeScript client 必须同步。

## Verification Strategy

### Unit

- 每种支持 item type 得到 hand-derived 的字段和 `sip-auto-map/1` provenance；
- technical requirement standard 优先于 `图纸要求`；
- unknown/composite、缺页码和冲突返回精确 exception code；
- 同文字不同 source IDs 不被 mapping 合并；
- 人工 resolved fields 不被 batch mapping 覆盖。

### Integration And Contract

- `apply_sip_defaults` 只增加一个 working-copy version 和一个 operation record；
- 规则完整的 active items 不再产生 SIP confirmation blocker；
- exception 仍阻止 freeze；
- edit/merge/split/requirement remap 使受影响 item 重新进入 exception；
- OpenAPI 接受新 command 且拒绝未知/空角色 payload；
- reviewed result、balloons、Excel rows 和 manifest count 仍基于同一 active item set。

### Frontend

- 项目默认角色只需输入一次；
- batch action 后显示 auto-filled/exception counts；
- 无异常时不显示 next-confirmation action；
- 有异常时只导航到异常 item；
- title metadata persisted/suggestion 冲突并列可见，采用建议不立即写 server；
- batch save/version conflict 保留输入并显示失败。

### Runtime

在真实项目 `fb0572f9-4401-4d05-95ae-fde26b28d1d3` 的可恢复 working copy 上：

1. batch action 只产生一个 review version；
2. 94 个 auto-accepted 和 21 个 kept items 不再要求逐条点击；
3. 已知类型 rows 自动获得可见 field provenance；
4. 三个缺少 canonical type/scope 的当前 items 保持 exception，不被猜测；
5. 五个已有人工作业值的 rows 不被静默覆盖，冲突可见；
6. 标题栏四个 recognized values 与旧值并列显示，材质保持人工处理；
7. console error、HTTP `>=400` 和 unexpected request failure 为 `0`；
8. 在测试项目或明确可写副本完成 freeze/export，验证 PDF、Excel 和 manifest 一致。

## Rollback

1. revert frontend exception flow、batch command 和 `sip_mapping.py` commits；
2. 首项 rollback verification：运行
   `backend/tests/integration/test_review_freeze.py` 中逐条 confirmation blocker case，
   证明旧 gate 恢复；
3. 运行 `InspectionWorkbench`、`SipInformationPanel` 和 export consistency focused tests；
4. 已有 working copy 中自动写入的字段仍是合法 confirmed SIP data，不需要数据库
   downgrade；若回滚后用户继续修改，可使用既有 `set_sip_detail_fields`；
5. historical reviewed results 和 artifacts 从未迁移，因此无需恢复。

## Acceptance Criteria

- 用户不需要对 115 条规则完整的 SIP rows 逐条点击确认。
- item review 仍是唯一正式集合决策，不新增 SIP membership state。
- 批量 action 是一个 versioned transaction。
- 自动 mapping 不覆盖人工值，不自动 merge 不同来源 items。
- 只有真实 exception 阻止 freeze/export。
- 标题栏识别冲突始终可见且只能显式采用。
- focused/full backend、frontend、OpenAPI、build、browser/API smoke 和 independent review
  全部完成后才可声明实现完成。
