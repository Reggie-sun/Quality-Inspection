# Leader Dimension Inspection Excel Design

## Status

- Date: `2026-07-31`
- Status: `completed`
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-31-leader-dimension-inspection-excel.md`
- Selection evidence: Task 1–5 production commits 已在同一批准 plan 下完成；代表性
  LibreOffice 回算与 isolated-DB focused/broader export suites 验证 v3 合同；最终
  independent review 发现的 manifest `mapping_sha256` 缺口已最小修复并复审接受。
- Validation action: `close`。本 design 只 supersede
  `2026-07-31-sip-auto-mapping-and-exception-review-design.md` 中
  “不修改固定 Excel 模板、列 mapping”的 non-goal；该 design 已完成的
  item review、SIP auto-mapping、exception-only UI 和 project metadata 行为保持不变。
- Writer ownership and order: Task 1 → Task 5 串行完成；原 Task 5 worker 仅对 reviewer
  指出的 mapping identity 缺口实施 scoped repair，parent 完成独立复审和最终判定。
- Next verification: 后续只需按正常 export regression gate 复验；本 design 已无待决
  implementation 或 review gate。

## Context

当前生产 `sip-v1` 是“标准检验指导书（SIP）”，第一工作表包含：

- 气泡序号；
- 检验项目；
- 检验标准；
- 检测方法；
- 是否重点尺寸；
- 检验人员角色；
- 来源页码。

领导参考模板不是现有 SIP 的换色，而是“机械图纸尺寸质量检测表”。用户选择 B：
没有领导原始 `.xlsx`，以参考截图和已批准的非生产 Excel 对比稿重建正式模板。

批准的可见字段为：

1. 编号；
2. 页码；
3. 类型；
4. 基本尺寸；
5. 公差；
6. 上限；
7. 下限；
8. 检测值；
9. 结果判定。

当前 reviewed item 已保留 `item_type`、`nominal`、`upper_tolerance`、
`lower_tolerance`、source page 和 `normalized_text/raw_text` 等结构化事实。
粗糙度等 complex item 使用既有 `coarse_type` 和原始/规范化文本，不需要重写
recognition pipeline。

当前正式导出链为：

```text
reviewed_result
  -> ExportService._excel_rows()
  -> load_template_registration(sip-v1)
  -> render_sip_workbook()
  -> validate_sip_workbook()
  -> staged SIP Excel
  -> PDF / Excel / manifest atomic publish
```

`backend/app/exports/template_registry.py` 是唯一 template registration Owner；
`backend/app/exports/excel.py` 是 Executor；`ExportService` 拥有正式 row projection、
三产物一致性和原子发布。新设计必须在这个链内原位替换，不建立第二套生产 Owner。

## Approved Product Behavior

### Workbook Identity

- 继续使用唯一 `template_id="sip-v1"`。
- template version 从 `2` 升为 `3`。
- mapping version 从 `2` 升为 `3`。
- 原位替换：
  - `backend/assets/templates/sip-v1.xlsx`
  - `backend/assets/templates/sip-v1.mapping.json`
- `template_registry.py` 继续 pin template/mapping SHA-256 并 fail closed。
- 不新增 template selector、feature flag、fallback、shadow export 或 legacy renderer。
- 历史已发布 Excel 与 manifest 保持 immutable，不回写、不迁移。

### Workbook Sheets

正式 workbook 继续包含且只登记两张生产工作表：

1. `尺寸质量检测表`
   - 第一张可见工作表；
   - 使用领导批准的标题、元数据、红色未注公差说明、蓝色表头、类型颜色和九列布局。
2. `气泡图`
   - 保留当前第二工作表职责；
   - 继续按 source page order 嵌入由正式 ballooned PDF 后端渲染的全部页面图像；
   - 不从非生产对比稿删除此稳定合同。

### Header Contract

`尺寸质量检测表` 顶部布局固定为：

| Cell / Range | Visible label | Value source |
| --- | --- | --- |
| `A1:I1` | 机械图纸尺寸质量检测表 | template fixed text |
| `A2` / `B2:D2` | 文件名 | immutable source PDF filename |
| `E2` / `F2:G2` | 检测日期 | `ExportJob.created_at`，转换到 `Asia/Hong_Kong`，格式 `YYYY-MM-DD HH:mm` |
| `H2` / `I2` | 带公差 | exported rows 中上下限均存在的行数 |
| `A3` / `B3:D3` | 总页数 | validated ballooned PDF page count |
| `E3` / `F3:G3` | 检验项总数 | active reviewed item / logical Excel row count |
| `H3` / `I3` | 单位 | fixed text `mm / 按项目` |
| `A4:I4` | 未注公差标准 | confirmed technical-requirement projection |

未注公差说明由 export seam 从 immutable `ReviewedResult.items` 中既有、已确认的
SIP projection 字段确定性生成，不改变 frozen `sip_metadata` 的五字段形状。只消费：

- active item；
- 非空 `technical_requirement_refs`；
- exact `inspection_standard` 为受控的 `GB/T 1804-<class>` 或
  `GB/T 1184-<class>`；
- 不读取 raw PDF、不调用 Provider、不重跑 technical-requirement classifier。

- `GB/T 1804-<class>` 投影为
  `未注线性尺寸公差按 GB/T 1804-<class> 级执行`；
- `GB/T 1184-<class>` 投影为
  `未注形位公差按 GB/T 1184-<class> 级执行`；
- 两项同时存在时以 `；` 连接；
- 同一 standard 出现冲突 class 时阻止正式导出，不选择任一值；
- frozen items 中没有受控值时显示 `【未注公差标准】未确认`。

export 不得从 `normalized_text/raw_text` 猜测 standard，也不得把不受控的
`inspection_standard` 文本当作未注公差标准。

### Row Contract

每个 active reviewed item 继续对应一个 logical Excel row。顺序保持
`ExportService._excel_rows()` 的 reviewed-item order；不因新表格自动 merge、drop 或
reorder。

| Visible field | Stable source / rule |
| --- | --- |
| 编号 | item 对应 formal balloon number；无气泡 global requirement 为空 |
| 页码 | canonical `source_page` |
| 类型 | `item_type` / `coarse_type` 的固定中文 label |
| 基本尺寸 | item-type-specific structured display；无法结构化时使用已审核 `normalized_text/raw_text` |
| 公差 | `upper_tolerance/lower_tolerance` 的确定性显示值 |
| 上限 | numeric base + `upper_tolerance`；无完整显式公差时为空 |
| 下限 | numeric base + `lower_tolerance`；无完整显式公差时为空 |
| 检测值 | template blank input cell，质检人员在下载后的本地副本中填写 |
| 结果判定 | 受控 template formula；服务端不得写用户测量值或判定结果 |

固定 type label 和颜色：

| Structured type | Visible label | Fill |
| --- | --- | --- |
| `linear_dimension` | 线性 | `#E5334E` |
| `diameter_dimension` | 直径 | `#178BFF` |
| `radius` | 半径 | `#22B14C` |
| `coarse_type=roughness` | 粗糙度 | `#C23ACF` |
| `angle` | 角度 | `#F39C3D` |
| `thread` | 螺纹 | `#009688` |
| `general_requirement` | 技术要求 | `#6B7280` |
| `composite` 或其他 coarse item | 复合 | `#B7791F` |

基本尺寸显示规则：

- `linear_dimension`: `nominal`；
- `diameter_dimension`: `Φ{nominal}`；
- `radius`: `R{radius_value}`；
- `angle`: `{angle_value}°`；
- `thread`: `thread_spec`，缺失时使用已审核 normalized/raw text；
- `coarse_type=roughness`: 已审核 normalized/raw text，例如 `Ra3.2`；
- `general_requirement` / `composite`: 已审核 normalized/raw text；
- typed numeric field 缺失时可显示已审核 normalized/raw text，但上限和下限必须为空，
  不从文本重新 parse 数值。

公差显示规则：

- upper 与 lower 都为空：公差、上限、下限全部为空；
- upper 等于 `-lower`：显示 `±<upper>`；
- 非对称完整公差：显示带符号的 `<upper>/<lower>`，例如 `+0.021/0`；
- 只存在 upper 或 lower 之一：属于 malformed structured tolerance，阻止正式导出；
- 上下限只使用 `Decimal` 语义计算，再以 numeric cell 写入 workbook；
- 不对无显式公差的行套用顶部未注公差标准生成数值上下限。

### Measurement And Result Formula

`检测值`：

- 对每个 detail row 初始为空；
- 单元格可编辑；
- 不进入 reviewed result、manifest 或服务器状态；
- 重新导出仍为空，不复用用户本地填写值。

`结果判定`：

- 每行由 template 预置受控公式；
- 公式行为等价于：

```excel
=IF(H6="","",IF(OR(F6="",G6=""),"",IF(AND(ISNUMBER(H6),H6<=F6,H6>=G6),"OK","NG")))
```

- 检测值为空：结果为空；
- 上限或下限为空：结果为空；
- numeric 检测值位于闭区间 `[下限, 上限]`：`OK`；
- numeric 检测值超出区间或填入非 numeric 内容：`NG`；
- `OK` 使用绿色，`NG` 使用红色 conditional formatting；
- formula cell 不属于 user/untrusted data mapping，renderer 不得覆盖。

### Print And Edit Contract

- paper size: A4；
- orientation: landscape；
- print area: `A1:I522`；
- repeated title rows: `1:5`；
- detail capacity: `512` rows，`6:517`；
- footer / signoff body: `518:522`，继续作为固定/签核区；
- 第一页和后续页均保持标题、元数据、红色说明和蓝色表头可读；
- 列宽、边框、字体和行高以已批准对比稿为视觉基准；
- `A:H` detail cells 可编辑，`I` 为受控公式；
- workbook 必须可由 openpyxl 重开、保存、再次重开；
- 当前正式验证必须额外使用 LibreOffice headless 重算代表行，证明公式实际工作。

## Goals

- 把领导批准的尺寸质量检测表原位升级为唯一正式 SIP Excel 第一工作表。
- 直接消费 reviewed item 中已有结构化尺寸、公差、类型和页码事实。
- 让质检人员只填写检测值，由 Excel 自动判定 `OK/NG`。
- 保留 PDF、Excel、manifest 同一 immutable `reviewed_result_id`。
- 保留第二工作表气泡图、模板哈希 preflight、capacity、固定区和原子发布。
- 让正式输出覆盖线性、直径、半径、粗糙度等实际类型，不重写 recognition。

## Non-Goals

- 不修改 recognition pipeline、Provider、OCR、candidate parser 或 symbol routing。
- 不新增数据库表、列或 migration。
- 不修改 `generate_sip_table`、SIP exception-only UI、review commands 或 OpenAPI。
- 不接收或保存服务器端检测值。
- 不让 Excel 判定结果成为正式 reviewed state。
- 不用顶部未注公差标准自动推导每行数值上下限。
- 不删除 `气泡图` 工作表或降低 formal ballooned PDF 的权威性。
- 不建立多模板选择、发布治理 UI、runtime flag、fallback 或第二 production Owner。
- 不修改历史 artifact，不把非生产 `.local/design-qa` 文件直接复制为生产模板。

## Problem Boundary And Ownership

### Changed Decision Dimension

唯一改变的 dimension：

`frozen reviewed item -> formal SIP Excel visible row and trusted workbook formula`

### Roles

- `ReviewService` item lifecycle: `Owner`，继续提交唯一 active reviewed item set；
  本 change 不修改 confirm、review command 或 frozen metadata contract。
- `sip_mapping.py`: `Owner`，继续提交 inspection guidance/readiness 字段；本 change 不改它。
- `ExportService._excel_rows()`: `Owner`，原位替换为 dimension inspection row projection。
- `template_registry.py`: `Owner`，继续唯一提交 template/mapping identity 和 layout contract。
- `sip_workbook_contract.py`: `Owner`，唯一提交 v3 header/detail numeric-field 分类及
  row-specific trusted result formula；builder、renderer、staged validator 共同消费。
- `excel.py`: `Executor`，按 registration 写入 header/detail numeric/text cells，不重做识别。
- controlled workbook formulas: `Executor`，只对本地检测值计算 `OK/NG`。
- `validators.py` / export consistency: `Veto Gate`，校验公式、cell type、identity 和 layout。
- frontend / download API: `Presenter / Transport`，保持不变。

### Old Path Action

- 旧 `sip-v1.xlsx` v2: `replace`，同路径升级为 v3，不保留并行 v2 生产分支。
- 旧 `sip-v1.mapping.json` v2: `replace`，同路径升级为 v3。
- registry v2 constants/hash: `replace` 为 v3 identity。
- 旧七列 visible detail mapping: `replace` 为新七列 server-written mapping 加
  measurement/result template columns。
- `SIP检验记录` sheet: `replace` 为 `尺寸质量检测表`。
- `气泡图` sheet、image anchor 和 page-order embedding: `preserve`。
- `set_untrusted_text()` security boundary: `preserve`；numeric fields 走显式 allowlist，
  不允许 untrusted string 成为公式。
- `generate_sip_table`、`set_sip_detail_fields`、`sip_detail_fields_confirmed`:
  `preserve`，不在本 change 退役。
- 三产物 staging、atomic publish、manifest identity 和 idempotency:
  `preserve`，template/mapping v3 自然产生新 export identity。

没有 transitional bridge、shadow、flag、fallback 或 wrapper 跨本变更保留。

## Data And Compatibility

- reviewed-result schema 保持 `reviewed-result/2`。
- database schema 保持不变。
- working-copy 与 `ReviewedResult.sip_metadata` 的五个人工字段及既有 SIP detail
  fields 保持不变，本 change 不改变 review readiness、confirm 或 API payload contract。
- v3 header note 只从既有 frozen item fields 投影；不存在受控 standard 时显示
  `【未注公差标准】未确认`，不做 hidden migration 或 raw-text fallback。
- template/mapping version 升级使相同 reviewed result 在 v3 下获得新的 logical export key。
- 已成功发布的 v2 export 继续可下载；新 export 不重写旧 artifact。
- registry 只激活 v3；运行时不提供 v2 fallback。
- manifest 继续记录 template/mapping version/hash；本 change 通过 v3 template/mapping
  identity 进入新的 export key。正式 ballooned PDF renderer 未改变，因此既有
  `RENDERER_VERSION` 保持不变。

## Failure Boundaries

- template/mapping 任一 hash 不匹配：preflight 阻止导出。
- 任一登记工作表缺失：preflight 阻止导出。
- active item 数与 Excel logical row 数不一致：阻止导出。
- balloon-required item 无 formal number：阻止导出。
- source page 缺失或非法：阻止导出。
- structured tolerance 只存在一侧：阻止导出。
- numeric base 非法：基本尺寸可显示已审核文本，但不得产生上下限。
- frozen items 中同一受控 general-tolerance standard 出现多个 class：阻止正式导出；
  不选择任一值。
- frozen item 的 `inspection_standard` 不符合受控格式：忽略该值并显示未确认；
  不得降级为 raw-text guess。
- formula cell 缺失、漂移、被 renderer 覆盖或来自 untrusted text：阻止导出。
- renderer、workbook validator 与 staged validator 必须消费同一 numeric/text/formula
  contract；staged workbook 中 numeric cell 被写成 text 时阻止发布。
- measurement template cell 非空或不可编辑：阻止导出。
- LibreOffice 代表性重算不满足 acceptance matrix：不得声明正式模板完成。
- 任一 PDF/Excel/manifest staging 或 validation 失败：不得发布任何部分产物。

## Verification Strategy

### Unit

- v3 registration 只接受新 sheet、header fields、detail fields、measurement/result columns。
- template/mapping bytes、version 和 hash 精确 pin。
- row projection 覆盖 linear、diameter、radius、roughness、angle、thread、
  general requirement 和 composite。
- symmetric/asymmetric/no/partial tolerance 分别得到 expected row 或 blocker。
- untrusted text 仍为 string，numeric allowlist 不能写公式。

### Integration

- 代表行 `500 ±0.2` 导出为上限 `500.2`、下限 `499.8`。
- 检测值初始为空，formula 已存在。
- LibreOffice 写入 `500.3` 并重算为 `NG`。
- 无检测值时 result 为空。
- 无显式公差时 upper/lower/result 为空。
- type colors、header、red note、blue header、print area 和 page setup 与 contract 一致。
- 512 rows 成功；513 rows fail closed。
- 气泡图页数/顺序与 formal PDF 一致。
- workbook 可重开、保存、再重开。

### Cross-Artifact

- Excel row count 等于 active reviewed items。
- Excel 非空编号集合等于 formal balloon number 集合。
- PDF、Excel、manifest 使用同一 reviewed result。
- manifest 记录 v3 template/mapping hashes。
- 任一 Excel formula/layout/identity validation 失败时普通下载不可见。

### Independent Review

reviewer 必须确认：

- 新模板确实解决领导表式，而不是旧 SIP 换色；
- 没有第二 template Owner 或 v2 fallback；
- server 不写检测值/结果；
- formula trust boundary 未被破坏；
- `气泡图` 和三产物一致性未退化；
- active/failure/rollback path 均有可执行验证。

## Rollback

1. 按实现 task commit 逆序 revert renderer/validator、template/mapping 和 contract changes。
2. 恢复 `sip-v1` template v2、mapping v2 及原 pinned hashes；不保留 v3 runtime flag。
3. rollback 后第一项验证：

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/unit/exports/test_template_registry.py::test_p0_exp_001_loads_the_approved_single_template_registration \
  backend/tests/integration/test_export_preflight.py -q
```

4. 再运行 Excel、atomicity 和 consistency focused suite，证明旧七列 SIP 与气泡图恢复。
5. v3 已发布 artifact 继续 immutable；rollback 只影响新的 export materialization，
   不删除或覆盖历史文件。
6. database、review confirm 和 frozen `sip_metadata` 形状从未改变，因此不需要
   database downgrade；v3-era `ReviewedResult` 可直接由恢复后的 v2 export path 消费。

## Acceptance Criteria

- 正式第一工作表标题为“机械图纸尺寸质量检测表”。
- 可见列严格为九列批准字段，视觉样式与对比稿同方向。
- `500 ±0.2` 得到 `500.2 / 499.8`；填写 `500.3` 后为 `NG`。
- 空检测值保持空判定；无显式公差时上下限和判定为空。
- 线性、直径、半径、粗糙度 type 颜色准确。
- 顶部红色说明只来自 confirmed technical requirement projection。
- detection/result 不进入服务器状态或 manifest。
- `气泡图`、formal PDF、manifest、row/number identity 和 atomic publish 全部保持。
- v2 旧生产路径在同一实现中完成 `replace`，没有并行 Owner、flag 或 fallback。
- focused unit/integration/LibreOffice smoke、cross-artifact verification 和 independent review
  全部通过后，才能声明正式实现完成。
