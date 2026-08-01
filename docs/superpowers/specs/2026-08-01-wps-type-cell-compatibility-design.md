# WPS Type Cell Compatibility Design

## Status

- Date: `2026-08-01`
- Status: `approved`
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-08-01-wps-type-cell-compatibility.md`
- Selection evidence: 用户确认选择“正式兼容修复”；同一正式 artifact 在 WPS 中类型列
  视觉为空，但 openpyxl 和 LibreOffice 均证明 C 列值完整。
- Validation action: `replan`；只 supersede
  `2026-07-31-leader-dimension-inspection-excel-design.md` 中“本 change 保持
  `RENDERER_VERSION` 不变”的一次性实施约束。

## Context

正式 v3 workbook 通过 `C6:C517` conditional formatting 为“线性、直径、半径、
粗糙度、角度、螺纹、技术要求、复合”提供白色粗体和类型背景色。WPS 当前只呈现
conditional font，没有呈现 differential fill，结果成为白字白底；截图因此看似“类型
没有识别”。

这不是数据或 mapping 缺失：

- `ReviewedResult.items` 保有 `item_type/coarse_type`；
- `ExportService._excel_rows()` 产生固定中文 `type_label`；
- 实际下载文件 C 列保有非空值；
- 同一 artifact 用 LibreOffice 24.2 渲染时显示正确类型和颜色。

## Approved Behavior

- `ExportService._type_label()` 继续拥有既有 type label 投影；
  `backend/app/exports/sip_workbook_contract.py` 作为 type-color palette 的唯一合同 Owner，
  暴露只读 `TYPE_FILL_COLORS`。
- `backend/app/exports/excel.py` 写入已登记 `type_label` 后，同时把对应 solid fill、白色
  粗体 CJK font 写成该 cell 的 base style。
- 原有 conditional formatting 保留，使支持它的 spreadsheet 在用户编辑类型后仍能更新
  颜色。
- 已填充明细行不得只依赖 differential style 才能看见类型；不支持或部分支持
  conditional formatting 的 WPS 仍必须显示初始值和颜色。
- formal renderer identity 从 `balloon-pdf/1` 升为
  `balloon-pdf/1+xlsx-type-style/1`。template/mapping 继续为 `3/3`，因为 workbook layout、
  column mapping、formula 和受控 asset bytes 均未改变。
- 新 renderer identity 进入 existing logical export key、`ExportJob` 和 manifest，使同一
  immutable reviewed result 能生成一份新的不可变兼容 artifact；历史 v3 artifact 不覆盖、
  不删除、不迁移。

## Unchanged Contracts

- 不修改 recognition pipeline、Provider、OCR、candidate parser、review command 或数据库
  schema。
- 不修改 `backend/assets/templates/sip-v1.xlsx` 或
  `backend/assets/templates/sip-v1.mapping.json`。
- 不修改九列字段、512-row capacity、检测值输入、结果公式、未注公差说明、气泡图、
  PDF bytes 或 artifact atomic publish。
- 不增加 fallback、feature flag、第二 template、第二 renderer Owner 或历史 artifact rewrite。

## Acceptance Criteria

1. Rendered workbook 的已填充类型 cell 自身具有对应 solid fill、白色粗体字体和非空中文
   label；删除全部 conditional formatting 后 base style 仍完整。
2. 原 conditional formatting 仍存在且颜色表与 renderer 的静态 style 使用同一 Owner。
3. 旧 `balloon-pdf/1` logical job 不阻止相同 reviewed result 使用
   `balloon-pdf/1+xlsx-type-style/1` 生成新 export。
4. current logical job 已进入 `processing`、但新版 `ExportJob` 尚未创建时，并发请求不得
   返回同一 reviewed result 的历史 renderer export；只允许返回完整 template/mapping/
   renderer identity 匹配的 current export，否则返回 `ExportInProgress`。
5. focused workbook、atomic export、manifest identity 和 LibreOffice 回算验证通过。
6. 同一 live project 重新点击“生成正式文件”后获得新 export；下载文件 C 列值和静态样式
   正确，历史 export 仍可下载。

## Rollback

回退本 amendment commit，恢复 `RENDERER_VERSION="balloon-pdf/1"` 和 conditional-only type
style。已经发布的新 renderer artifact 保持 immutable、仍可按其 export ID 下载；rollback
不得删除数据库记录或 artifact。rollback 后第一项验证为：

```bash
PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 pytest \
  backend/tests/integration/test_export_atomicity.py::test_logical_export_claim_has_one_execution_owner \
  backend/tests/integration/test_excel_export.py -q
```
