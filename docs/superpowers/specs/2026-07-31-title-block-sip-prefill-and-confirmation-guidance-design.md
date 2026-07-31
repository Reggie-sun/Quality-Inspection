# Title Block SIP Prefill And Confirmation Guidance Design

## Status

- Date: `2026-07-31`
- Status: `approved`
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-31-title-block-sip-prefill-and-confirmation-guidance.md`
- Selection evidence: 用户指出项目 SIP 基本信息大部分已经存在于图纸标题栏，应由系统
  自动识别并填入；同时批准“安全引导流”，即自动识别只形成待确认建议，不凭空补值，
  检验项 SIP 仍逐项确认并提供明确的下一条入口。
- Validation action: `replan`
- Writer ownership and order: 主线程是唯一 production writer；先完成 backend
  suggestion Owner 与 API contract，再完成 frontend 预填和确认引导；explorer 与
  reviewer 始终只读。
- Next verification: 先运行 title-block suggestion unit/integration RED，确认失败来自
  当前缺少字段级 suggestion projection。

## Context

当前工作台把 `working_copy.sip_metadata` 同时当作项目 SIP 表单的唯一初始值和正式
已确认值。新项目的 `sip_metadata` 为空，因此即使图纸标题栏已经包含产品名称、图号、
版本号和物料编码，用户仍需重复录入。

当前 PDF inventory 已保留 native line observation、页号和 `bbox_pdf`。WELLI layout
profile 也能识别部分标题栏区域，但只提供泛化 `title_metadata_value`，没有字段级
关系；部分真实 WELLI 图纸还可能因完整 layout quorum 未命中而没有
`layout_profile_match`。因此不能把标题栏区域内的任意文本直接提升为 SIP metadata。

当前真实项目 `fb0572f9-4401-4d05-95ae-fde26b28d1d3` 的 persisted inventory 证明：

- `图样代号` 与 `ZHZS25032501-04` 为同一行的明确 label/value；
- `物料编码` 与 `12320096476` 为同一行的明确 label/value；
- `版本号` 与 `A/0` 为同列上下相邻的明确 label/value；
- `横行滑板` 位于图号值同一 value column 的产品名称位置；
- 图中没有可证明的 `材质` 值。

另一个独立问题是：技术要求全部确认后，顶部仍只显示模糊的“已确认”，正式导出又因
大量检验项 SIP 尚未确认而不可用。系统缺少精确进度、下一条入口和导出阻断原因。

## Approved Product Behavior

### Project SIP Metadata Suggestions

workbench 读取 persisted inventory 时，新增只读
`sip_metadata_suggestions` projection。每条 suggestion 必须包含：

- `field`；
- `value`；
- value observation 的 `observation_id`、`page_index`、`bbox_pdf`；
- 可选的 label observation identity；
- 版本化 `rule_version`；
- 明确的 `evidence_codes`。

自动建议只允许使用本地 native text 和确定性几何关系，不调用 Provider，不发送标题栏
crop，不重读 PDF 文件，也不写入 `ReviewWorkingCopy.sip_metadata`。

首版支持：

- `material_code`：明确 `物料编码` label 的同一行右侧唯一值；
- `drawing_number`：明确 `图样代号` label 的同一行右侧唯一值；
- `revision`：明确 `版本号` label 的同列上方唯一版本 token；
- `material`：仅在存在明确 `材质` 或 `材料` label 和唯一相邻值时建议；
- `material_name`：在 drawing number relation 已确定后，仅当同一 title value column
  上方存在唯一、非 label、非纯数字/日期/code 的名称文本时建议。

任一字段出现多个等价候选、跨页关系、OCR-only 值、旋转文本、超出 title anchor
边界、未知 label 或格式不满足时，该字段不生成 suggestion。缺失字段继续留空，用户
手工填写。

### Confirmation Boundary

frontend 初始化项目 SIP draft 时：

1. 已确认 `working_copy.sip_metadata` 始终优先；
2. 只对仍为空的字段采用 suggestion；
3. suggestion 显示“图纸识别，待确认”；
4. 用户修改 suggestion 后仍只是本地 draft；
5. 只有点击既有 `确认项目 SIP 信息`，才提交既有 `set_sip_metadata` command；
6. refresh 后的新 suggestions 不得覆盖已确认值或 dirty draft。

`SetSipMetadata`、freeze、`ReviewedResult` 和 export 继续只读取 confirmed metadata。

### Inspection Item SIP Guidance

- 顶部摘要把模糊的 `已确认` 改为 `检验项 SIP`，显示 `x / y`。
- SIP 面板显示 `检验项 SIP 已确认 x / y`。
- 存在未确认 active item 时提供 `处理下一条未确认 SIP`。
- 成功提交 `set_sip_detail_fields` 后自动选择下一条未确认 active item；失败时保持当前
  selection 和 draft。
- export panel 在 reviewed result 尚不可生成时优先显示
  `还需确认 N 条检验项 SIP`；项目 metadata 缺失时显示项目 SIP 未确认；不得只显示
  含混的 `尚未审核`。
- 不给 `inspection_method`、`inspection_role` 或其他正式检验项字段补无证据默认值。

## Goals

- 消除用户对标题栏已有数据的重复录入。
- 让自动识别建议与正式已确认 SIP 值严格分离。
- 让用户清楚知道技术要求确认后仍需完成多少检验项 SIP。
- 用最短路径进入下一条未确认 SIP，并在成功后连续推进。
- 保持现有 freeze、numbering、balloon、review 和 export gates 不变。

## Non-Goals

- 不引入 OCR/LLM/Provider title-block extraction。
- 不自动确认项目 SIP metadata。
- 不伪造材质、检测方法、检验角色、重点尺寸或标准数值。
- 不修改数据库 schema、`ReviewWorkingCopy` schema 或 `SetSipMetadata` payload。
- 不改变 fixed SIP Excel mapping。
- 不改变 candidate disposition、coverage 或 technical requirement matching。
- 不为不同供应商建立通用可配置模板系统；首版只拥有有证据的 WELLI relation。

## Problem Boundary And Ownership

### Changed Decision Dimension

新增唯一 decision dimension：

`native title-block observations -> evidence-backed project SIP metadata suggestions`

### Roles

- PDF inventory：`Signal Provider`，只提供 native observations 和坐标。
- `backend/app/pdf/title_block_metadata.py`：唯一 suggestion `Owner`，提交字段关系和
  provenance，不能写 confirmed state。
- `backend/app/projects/router.py::_workbench_payload()`：`Executor`，只投影 Owner
  结果，不重算字段语义。
- frontend：`Advisor presenter`，只预填和显示 suggestion。
- `set_sip_metadata`：保留唯一 confirmed business-field `Owner`。
- freeze/export：保留现有 `Validator / Veto Gate / Executor` 角色。

### Old Path Action

- backend 原来没有 title-block SIP suggestion path；不存在需要并存的旧 Owner。
- frontend `metadataDraft()` 的“仅从 confirmed metadata 初始化，否则为空”路径执行
  `replace`：改为 confirmed-first、suggestion-second。旧的 confirmed-only优先级仍被
  `preserve`，因为它是正式值 canonical consumer。
- export 的含混状态文案执行 `replace`，gate 本身 `preserve`。

## Data Contract

workbench response 新增：

```json
{
  "sip_metadata_suggestions": [
    {
      "field": "drawing_number",
      "value": "ZHZS25032501-04",
      "observation_id": "value-observation-id",
      "label_observation_id": "label-observation-id",
      "page_index": 0,
      "bbox_pdf": [1088.29, 781.55, 1162.57, 796.3],
      "rule_version": "welli-title-metadata/1",
      "evidence_codes": [
        "native_line",
        "bottom_right_title_anchor",
        "same_row_right_of_label",
        "unique_candidate"
      ]
    }
  ]
}
```

字段为 additive read API。response schema `extra="forbid"`；unknown internal fields 不得
泄漏。frontend generated transport type 必须从 approved OpenAPI snapshot 机械生成。

## Failure Boundaries

- inventory 不可读：沿用现有 workbench unavailable。
- inventory 可读但没有可靠 title relation：返回空 suggestions，不阻断工作台。
- 单字段冲突：只省略冲突字段，不选择“最像”的值。
- confirmed metadata 已存在：suggestions 可以继续作为只读 evidence 返回，但 frontend
  不得覆盖 confirmed field。
- dirty metadata draft：workbench refresh 不得覆盖本地值。
- item SIP 保存失败：不自动跳转。
- filtered view 不含下一条：next action 必须切换到 `all` 并选择真实 active item，不能
  把隐藏项判定为已完成。

## Verification Strategy

### Unit

- 真实 WELLI geometry relation得到 `物料编码`、`图样代号`、`版本号`、`产品名称`；
- 没有材质 label 时不生成 `material`；
- duplicate/conflicting candidates fail closed；
- OCR-only、rotated、cross-page、非右下 title anchor 不生成；
- suggestion 顺序稳定且 provenance 完整。

### Integration And Contract

- workbench response 返回 suggestions，但 `working_copy.sip_metadata == {}`；
- confirmed metadata 不受 suggestions 影响；
- OpenAPI snapshot 与 generated TypeScript type 同步；
- legacy inventory 不含 layout profile 时仍只依据满足严格 anchor/geometry 的 native
  evidence，缺证据返回空列表。

### Frontend

- confirmed-first、suggestion-second 初始化；
- suggestion badge 和待确认文案；
- dirty draft/confirmed refresh 不被覆盖；
- item SIP `x / y`、next action、成功 auto-next、失败不跳；
- export 显示准确 pending count。

### Runtime

在当前真实项目只读刷新 workbench：

1. response 返回图号、物料编码、版本和产品名称 suggestion；
2. 材质为空；
3. 页面显示识别预填且标记待确认；
4. 未点击确认前 `working_copy.sip_metadata` 仍为空；
5. 使用测试项目或明确可写副本完成一次确认，证明 command 后才进入 confirmed state；
6. 验证下一条检验项 SIP 导航与导出阻断文案；
7. console error、HTTP `>=400` 和 unexpected request failure 为 `0`。

## Rollback

1. revert title-block suggestion、workbench additive response、generated client 和 frontend
   guidance commits；
2. 首项 rollback verification：
   `test_project_workbench_delivers_real_pdf_without_internal_references`，证明旧
   workbench response 和 source PDF bootstrap 恢复；
3. 运行 frontend `InspectionWorkbench`、`SipInformationPanel`、`ExportPanel` focused
   tests，证明 confirmed-only metadata 和旧 selection 行为恢复；
4. 无数据库 downgrade，无 persisted suggestion 数据需要清理；
5. 已确认的 `sip_metadata` 不受 rollback 影响。
