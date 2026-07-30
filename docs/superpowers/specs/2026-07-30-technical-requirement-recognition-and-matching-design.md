# Technical Requirement Recognition And Matching Design

## Status

- Date: `2026-07-30`
- Status: `approved`；`A 内联逐条确认` amendment 于 `2026-07-30` 批准
- Selected lane: `Heavy`
- Selected plan:
  `docs/superpowers/plans/2026-07-30-technical-requirement-recognition-and-matching.md`
  是唯一 successor implementation plan
- Selection evidence: 用户确认技术要求需要“语义拆解匹配 + SIP 填充”，并批准
  “规则 Owner + 辅助识别”与“不自动换算标准数值”的边界
- Validation action: `close`
- Selected direction: 用户批准“规则 Owner + 辅助识别”
- Supersession boundary: 本功能是新的 successor scope；不重开已 sealed 的七天
  P0 task，也不把尚未完成 runtime acceptance 的 confidence plan 标记为完成
- Writer ownership and order: spec 阶段父 agent 是本文件唯一 writer；production
  implementation 必须在后续唯一 plan 中串行分配 file ownership
- Next verification: successor implementation 与本 amendment 已按唯一 plan
  完成并关闭；后续只在出现新的用户反馈或 runtime regression 时重开验证

### A Inline Confirmation Flow Amendment

用户针对 production screenshot 明确选择方案 `A 内联逐条确认`，并批准同时补齐
`未注公差按 GB/T 1804-m 级执行` 的 Rule Owner 识别。该 amendment 不新增第二个
matching Owner，也不改变 Review API/schema。

批准的状态流：

1. `待确认`
   - 当前待处理 requirement 内联展示互斥处理方式：
     `采用系统建议`、`选择部分检验项`、`设为全局要求`、`排除此要求`；
   - 用户先形成本地 draft，再看到影响摘要；
   - 未选择合法处理方式前，主按钮保持 disabled；
   - 点击 `确认并处理下一条` 后，仍只提交既有
     `set_technical_requirement_match` command。
2. `已选择，待提交`
   - frontend 可以维护未持久化的 selection draft；
   - selection draft 必须进入工作台既有 dirty/save/freeze gate；返回列表时复用
     现有三向确认，保存时先提交 technical requirement draft；
   - frontend 不得解析 raw text、计算适用范围或把全部 active items 当成系统建议；
   - `系统建议` 只能消费 Rule Owner 已提交的
     `match_outcome / matched_candidate_ids`。
3. `终态`
   - 已确认 requirement 收敛为只读摘要，显示 `已确认`、影响范围和关联项入口；
   - `修改` 只重新打开同一 command 的 draft UI，不创建新 endpoint；
   - 全部 requirement 已确认后，面板收敛为完成摘要，并提供
     `进入检验项审核`；下一阶段仍是 item/SIP 人工审核，不得跳到 freeze、编号或气泡。

明确 `GB/T 1804` 且包含 `执行` 的 `未注/未标注公差` shorthand 可由
Technical Requirement Rule Owner 归类为
`general_dimensional_tolerance`；缺少明确标准、等级或执行语义的
`未注公差` 仍保持 `ambiguous / unresolved`。本 amendment 不自动计算标准数值公差。

## Context

工程图的“技术要求”区域包含会直接影响检验清单和 SIP 的业务语义。当前样例为：

1. 未标注倒角 `C0.5`
2. 锐边去毛刺
3. 零件表面不应有划痕、擦伤等损伤零件外观的缺陷
4. 表面阳极氧化亮光银色处理
5. 未注尺寸公差按 `GB/T 1804-m` 执行
6. 未注形位公差按 `GB/T 1184-k` 执行

当前 `backend/app/candidates/disposition.py::classify_technical_requirement()`
要求同一行同时出现“检查/检验/检测/测量/确认/验证”动词和可验证判据。以上六条均
没有显式检验动词，因此当前实现全部返回 `None`。其中第 3 条还可能被 OCR 拆成多行，
现有逐 observation 分类没有“技术要求标题 + 编号条目 + 续行”的区块语义。

结果是原文虽然可能存在于 source observations 中，却没有自动成为检验项，也没有匹配
到已有候选项或 SIP 字段。这不是单纯的 OCR 漏字，而是 Candidate disposition 与
business-field suggestion 之间缺少唯一的技术要求规则 Owner。

## Approved Product Behavior

用户批准混合行为：

- 可独立执行的要求进入 SIP：
  - 去毛刺；
  - 表面外观缺陷；
  - 表面处理。
- 适用范围型要求按语义匹配：
  - 未注倒角；
  - 未注尺寸公差标准；
  - 未注形位公差标准。
- 只有能够由当前结构化语义安全证明的关系才建立 item-level link。
- 不能安全匹配到具体 item 时，要求仍作为无气泡的
  `global_requirement` 进入 SIP，不得静默消失。
- 自动识别和匹配只产生可追溯建议；现有人工 SIP confirmation、item freeze、
  `ReviewedResult` 和 export gate 保持不变。

## Goals

- 自动定位技术要求区块，按编号重建条目并合并合法续行。
- 将每条要求分类为独立检验、适用范围规则或非检验文本。
- 对适用范围规则建立确定性、可解释、版本化的匹配关系。
- 为可确定的 SIP 字段生成建议值，保留原文、页码、坐标和规则 provenance。
- 让 unmatched、ambiguous、conflicting 和 unsupported 要求保持可见并进入人工复核。
- 保证所有 global requirement 默认无气泡、不占正式编号，但仍进入 SIP logical
  detail。
- 用当前样例的六条要求建立真实回归，证明没有漏项、错绑或静默标准换算。

## Non-Goals

- 本期不根据 `GB/T 1804-m`、`GB/T 1184-k` 自动计算具体数值公差。
- 本期不内置未经批准、未经版本化的国家标准数值表。
- 不让 OCR、视觉模型或 LLM 直接提交正式 SIP 标准、方法、角色或公差数值。
- 不把技术要求标题“技术要求”本身创建为 inspection item。
- 不因 raw text 相同而跨页、跨视图自动合并 requirement 或 candidate。
- 不把全局要求强行绑定到无法由当前 typed semantics 证明适用的 local item。
- 不改变 formal numbering、balloon placement、review freeze、immutable result 或
  atomic export Owner。
- 不新建 runtime feature flag、shadow matcher、frontend rematcher 或 silent fallback。

## Selected Direction

用户批准方案 A：新增唯一 `Technical Requirement Rule Owner`，OCR/视觉只提供
source evidence，规则 Owner 提交 requirement semantics、match relations 和 SIP
suggestions。

未采用：

- 只扩展关键词正则：可以让更多文本成为 `general_requirement`，但无法表达区块、
  续行、适用范围、target relation 或 SIP provenance。
- 模型直接生成 SIP：覆盖面较广，但会把标准、方法和适用范围变成不可稳定复核的
  模型判断，并可能产生制造质量风险。

## Problem Boundary

### Changed Decision Dimensions

本功能新增三个互相衔接但由同一 Owner 提交的 decision：

1. `technical requirement entry reconstruction`
2. `technical requirement semantic classification`
3. `technical requirement applicability matching`

它不拥有 OCR 文本、candidate typed semantics、人工最终确认或 export publication。

### Single Owner

canonical implementation 预期位于：

`backend/app/candidates/technical_requirements.py`

该 Owner 的输入是：

- 按稳定阅读顺序排列的 `TextObservation`；
- 当前 candidate snapshot；
- 版本化、仓库内受控的 requirement rules。

输出是 immutable technical-requirement decisions 和 match relations。

### Old Path To Retire

当前
`backend/app/candidates/disposition.py::classify_technical_requirement()`
的“单行同时命中检验动词和判据”路径必须被替代：

- 既有动词/判据规则可以迁入新 Owner 作为一个版本化 rule；
- `automatic_result.py` 不得同时保留旧 classifier 与新 Owner 两条 active path；
- frontend、Review 和 export 不得重新分类或重新匹配 raw text。

完成后只允许新 Owner 提交技术要求分类与匹配结论。

### Unchanged Contracts

- `TextObservation` 和 PDF inventory 继续拥有 source text、页码与坐标。
- Deterministic parser、complex fallback 和 visual projection 继续拥有 local
  candidate semantics。
- ConfidencePolicy Owner 继续拥有 `auto_accepted` / `review_required`；技术要求
  matcher 只能提供 evidence，不能绕过 confidence policy。
- Review working copy 继续拥有人工 edit、keep、exclude、confirmation 和 version。
- Business-field confirmation Owner 继续拥有 confirmed SIP fields。
- Numbering Owner 继续保证 global requirement 无气泡且不占编号。
- Reviewed-result Owner 与 Export Owner 保持不变。

## Requirement Reconstruction

### Block Detection

技术要求区块由以下受控证据识别：

- 明确标题，例如规范化后的“技术要求”；
- 与标题处于同页、同阅读方向并位于相邻区域的编号条目；
- 编号必须符合受控格式，如 `1.`、`1、`、`（1）`；
- 条目按 `(page_index, direction, y0, x0, observation_id)` 稳定排序。

只命中标题但没有合法条目时，不创建伪 requirement；相关 source observations 保持
`ambiguous / review_required`。

### Continuation Lines

只有同时满足以下条件才把下一 observation 合并为当前条目的续行：

- 同页、同方向；
- 位于同一技术要求区块；
- 下一行没有新编号；
- 几何位置与当前条目正文列对齐；
- 中间没有新的标题、表格边界或明显区域跳转。

合并后：

- `raw_text` 按原始行顺序保留；
- `normalized_text` 只用于规则匹配；
- `source_location_ids` 保留全部贡献 observation；
- coordinates 使用可追溯的成员坐标集合，不伪造成单一来源。

不能安全合并时，保持独立 source review，不按文本猜测。

## Semantic Classification

每条 requirement 产生一个冻结的语义分类：

- `standalone_check`
  - `deburr`
  - `surface_integrity`
  - `surface_treatment`
- `applicability_rule`
  - `default_chamfer`
  - `general_dimensional_tolerance`
  - `general_geometric_tolerance`
- `unsupported`
- `ambiguous`

每个 decision 至少保存：

- stable `requirement_id`
- ordinal（如果存在）
- `raw_text`
- `normalized_text`
- `source_location_ids`
- source page/coordinates
- category/subtype
- parsed parameters，例如 `C0.5`、`GB/T 1804`、class `m`
- `rule_id`
- `rule_version`
- `review_required`

模型建议不得成为 category、standard reference 或 parsed parameter 的唯一正式
evidence。

## Matching Contract

### Match Outcomes

每条 applicability rule 必须得到且只得到一种 outcome：

- `matched_items`：安全匹配到一个或多个 existing candidate IDs；
- `global_scope`：要求有效，但当前 typed semantics 不足以安全绑定具体 item；
- `unresolved`：文本、标准、范围或冲突不足，必须人工复核。

所有 outcome 都保留 source relation；`unresolved` 不得被当作 non-inspection。

### Deterministic Matching

首版规则：

- `general_dimensional_tolerance`
  - 首版受支持的 candidate type 明确限于 `linear_dimension`、
    `diameter_dimension`、`radius` 和 `angle`；
  - 只匹配没有显式上下公差的受支持尺寸 candidate；
  - 显式公差优先，不能被全局规则覆盖；
  - 只记录标准引用和 rule relation；
  - candidate 的 `upper_tolerance` / `lower_tolerance` 保持 `None`，要求人工确认；
  - thread、已有明确公差的尺寸和 unsupported complex item 不得误绑。
- `default_chamfer`
  - 只有 candidate typed semantics 明确表示未单独标注的倒角时才建立 item link；
  - 当前 schema 没有独立 chamfer typed candidate，因此首版使用
    `global_scope` 并生成 global SIP row，不伪造 local target。
- `general_geometric_tolerance`
  - 不绑定已有明确数值的 GD&T 标注；
  - 只有未来受支持的“未注形位要求适用对象”typed semantics 才允许 item link；
  - 当前安全默认是 `global_scope`，保留 `GB/T 1184-k` 引用并要求确认。

### Conflict Rules

以下情况必须 `unresolved / review_required`：

- 同一 scope 出现互相冲突的通用公差标准或等级；
- OCR 无法稳定区分标准编号、连字符或等级；
- requirement 与 explicit local tolerance 发生不一致；
- 一个 source entry 被两个互斥 subtype 同时命中；
- target candidate identity 或 source ownership 不唯一。

不得用“最后一条覆盖前一条”、模型概率或 frontend 选择来消解冲突。

## Persistence And Automatic-Result Contract

结构调查确认：

- `AutomaticResult` 目前把 `candidates`、`coverage` 和 `provider_call_ids` 分列保存，
  不存在任意 automatic-result 顶层 JSON 文档；
- `ReviewWorkingCopy` 目前只分列保存 `items`、`coverage` 和 `sip_metadata`；
- 把 requirement semantics 塞入 `coverage` 会错误扩大 Coverage Owner。

因此采用明确 schema migration：

- `automatic_results.technical_requirements JSONB NOT NULL DEFAULT '[]'`
  保存 immutable requirement decisions、match relations 和 SIP suggestions；
- `review_working_copies.technical_requirements JSONB NOT NULL DEFAULT '[]'`
  保存从 immutable result 投影出来的 versioned review state；
- 保留当前 `automatic-result/2` candidate envelope 和 confidence contract；
- candidate envelope 只增加 optional `technical_requirement_refs`，不把 match fields
  塞进 typed candidate payload；
- 既有数据库行由 migration backfill 为 `[]`，reader 把空数组解释为“没有自动
  technical-requirement evidence”，不得重算历史结果；
- 不给 `ReviewedResult` 新增 requirement column；确认后的 global items、target item
  SIP fields 和 provenance 继续冻结在既有 `items` 中，export 不读 mutable review
  relation。

migration 必须在写入新数据前完成，并包含 upgrade、downgrade、model/schema contract
tests 和 legacy row compatibility。downgrade 只允许在确认没有需要保留的新
technical-requirement evidence 后执行，不能静默丢弃已生成的业务数据。

示意：

```json
{
  "schema_version": "automatic-result/2",
  "automatic_result_record": {
    "technical_requirements": [
    {
      "requirement_id": "stable-id",
      "ordinal": 5,
      "raw_text": "未注尺寸公差按GB/T 1804-m执行",
      "source_location_ids": ["page-1-line-42"],
      "category": "applicability_rule",
      "subtype": "general_dimensional_tolerance",
      "standard_reference": {
        "code": "GB/T 1804",
        "class": "m"
      },
      "match_outcome": "matched_items",
      "matched_candidate_ids": ["candidate-17", "candidate-21"],
      "rule_id": "general-dimensional-tolerance",
      "rule_version": "technical-requirement/1",
      "review_required": true
    }
    ]
  }
}
```

## SIP Suggestion Contract

技术要求 Owner 只能建议可由 source text 和版本化规则确定的字段：

- `inspection_item`
- `inspection_standard`
- `key_dimension`
- `source_page`
- provenance/remarks

`inspection_method` 和 `inspection_role` 只有在仓库内已有、经过业务批准的版本化规则
明确覆盖该 subtype 时才能建议；否则保持未确认，不得由模型或常识补造。

建议值与 confirmed 值分离：

- requirement suggestion 可以预填 review form；
- `sip_detail_fields_confirmed` 仍为 `false`；
- 用户确认或修改后继续通过现有 `set_sip_detail_fields` command 保存；
- export 仍只读 confirmed fields。

global-scope requirement 形成独立 SIP logical detail，`balloon_number` 为空。
matched-item requirement 把标准/关键要求建议投影到对应 item，但不得覆盖人工已确认值。

## Sample Acceptance Mapping

| # | Requirement | Expected classification | Expected outcome |
| --- | --- | --- | --- |
| 1 | 未标注倒角 C0.5 | `applicability_rule/default_chamfer` | 有安全 target 时 link；否则 `global_scope` SIP row |
| 2 | 锐边去毛刺 | `standalone_check/deburr` | 独立无气泡 SIP suggestion |
| 3 | 表面不应有划痕、擦伤等缺陷 | `standalone_check/surface_integrity` | 合并 OCR 续行后生成独立无气泡 SIP suggestion |
| 4 | 阳极氧化亮光银色处理 | `standalone_check/surface_treatment` | 独立无气泡 SIP suggestion |
| 5 | 未注尺寸公差按 GB/T 1804-m | `applicability_rule/general_dimensional_tolerance` | link 到无显式公差的受支持尺寸；不计算数值 |
| 6 | 未注形位公差按 GB/T 1184-k | `applicability_rule/general_geometric_tolerance` | 当前默认 `global_scope`；不覆盖明确 GD&T |

验收要求：

- 六条全部可见并可追溯；
- 标题不成为 item；
- 第 3 条续行顺序正确；
- global requirement 全部无气泡、不占编号；
- match relation 不覆盖 explicit local semantics；
- SIP suggestion 不自动变成 confirmed business fact；
- unsupported 或 conflict 不静默排除。

## Review And UI

workbench 对每条技术要求至少显示：

- 原始要求和来源页；
- 分类；
- “已匹配 N 项 / 全局要求 / 待确认”状态；
- matched item navigation；
- SIP 建议与 confirmed 值的区分；
- unresolved/conflict 原因。

用户可以：

- 确认或修改 SIP 字段；
- 把误识别要求排除为 non-inspection；
- 把 global requirement 重新关联到受支持 item；
- 取消错误 relation。

所有变更必须走现有 versioned review command seam；前端本地状态不能成为正式关系
Owner。

## Error Handling

- 标题存在但区块结构不可靠：保留 source review，不生成伪条目。
- OCR 标准编号不确定：保留原文并标记 unresolved，不规范化成另一个标准。
- requirement 匹配不到 item：创建 global-scope review item，不丢失。
- 多条全局规则冲突：阻止自动匹配和 SIP confirmation，显示冲突来源。
- legacy automatic result：不重算历史自动能力，允许现有人工流程继续。
- unknown optional field consumer：必须在 contract test 中证明兼容；失败则先做
  reader migration。

## Data Flow

```text
PDF inventory / OCR observations
  → stable reading order
  → Technical Requirement Rule Owner
      → block reconstruction
      → semantic classification
      → deterministic candidate matching
      → SIP suggestions + provenance
  → immutable AutomaticResult
  → Review working copy
      → inspect / relink / edit / confirm
  → existing item freeze
  → existing ReviewedResult
  → existing PDF / SIP Excel / manifest export
```

## Verification Strategy

### Focused Unit Tests

- 标题和编号区块识别；
- 多行续行合并及错误边界；
- 六条样例的 table-driven classification；
- `GB/T 1804-m` 只匹配无显式公差的受支持尺寸；
- explicit tolerance 不被覆盖；
- `GB/T 1184-k` 当前为 global scope；
- conflicting standards fail closed；
- requirement ID 同时包含 source identity，不按文本去重；
- SIP suggestion 不写 confirmed state。

### Contract And Integration Tests

- `automatic-result/2` additive reader/writer compatibility；
- candidate refs 与 top-level requirements 双向一致；
- Review bootstrap 保留 provenance、match outcome 和 suggestions；
- manual edit/confirm 不改写 immutable automatic result；
- global requirement 不生成 balloon、不占正式编号；
- SIP Excel 为 global requirement 输出空序号并只使用 confirmed fields；
- legacy result 缺少新字段时保持可读并 fail closed。

### Runtime And Browser Proof

使用包含本设计六条技术要求的 approved real PDF：

1. 上传并完成当前真实 processing；
2. 在 source-mounted workbench 中看到六条要求；
3. 验证第 3 条续行重建；
4. 验证 `2/3/4` 的独立 SIP suggestions；
5. 验证 `1/5/6` 的 match/global-scope 状态；
6. 验证用户修改、确认、freeze；
7. 导出并核对 SIP logical details、空 balloon number 与 source provenance。

截图不能代替 approved source PDF 的 processing proof；若只有截图，runtime acceptance
保持 blocked。

## Rollback

schema rollback：

1. 先停止新 writer 生成 technical requirement decisions；
2. 保留 reader 对 `[]` 和已存在 requirement records 的兼容；
3. 现有 immutable results 不删除、不重写；
4. 只有数据库查询证明两个新增 column 全部为空数组，才允许执行 downgrade 删除
   column；否则 rollback 停在 application rollback 并保留 schema；
5. application rollback 回到旧 source-review behavior；
6. 首项 rollback verification 是 legacy `automatic-result/2` processing +
   Review bootstrap focused integration test；
7. 若执行 schema downgrade，再运行 `alembic upgrade head` 和 schema integration
   test 证明可恢复。

## Implementation Planning Gate

用户批准本 spec 后才允许创建唯一 successor implementation plan。plan 必须：

- 先完成 structural code mapping 和 exact call-site inventory；
- 记录 allowed paths、single writer order 和 unchanged contracts；
- 先写 failing regression tests，再写 implementation；
- 显式退役旧 classifier active path；
- 包含 contract、integration、frontend 和 real-PDF browser proof；
- 对 core behavior diff 进行独立只读 review；
- 在 runtime proof 前不 claim feature complete。
