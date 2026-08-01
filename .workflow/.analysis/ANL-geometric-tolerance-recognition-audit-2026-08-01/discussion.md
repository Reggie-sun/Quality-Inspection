# Analysis Discussion

**Session ID**: `ANL-geometric-tolerance-recognition-audit-2026-08-01`

**Topic**: 几何公差识别端到端现状审计与目标 Specs

**Started**: `2026-08-01T09:35:00+08:00`

**Dimensions**: detection, recognition, normalization, persistence, API, UI, tests, runtime

**Depth**: deep

## Table of Contents

- [Analysis Context](#analysis-context)
- [Current Understanding](#current-understanding)
- [Discussion Timeline](#discussion-timeline)
- [Decision Trail](#decision-trail)
- [Synthesis And Conclusions](#synthesis-and-conclusions)

## Current Understanding

- 当前支持 text-anchored vector ROI 与三种 VLM GD&T subtype，不支持 typed GD&T。
- subtype 在 candidate projection 被压平；datum A 在独立 line association 边界失联。
- API/UI 没有丢弃一个已经存在的 datum 字段，因为 normalized payload 从未有该字段。
- 目标修复必须由 candidate-domain normalizer 统一拥有，不能在 frontend 解析 raw text。

## Analysis Context

- Focus areas: 完整数据链、两个真实案例、数据丢失点、测试真实性、目标合同
- Perspectives: detection/recognition explorer, contract/UI architecture auditor, parent runtime verification
- Constraints: 不改业务代码；不切换 current P0 plan；只提交文档

## Initial Questions

- 几何公差框在当前系统中以什么 observation/bbox 进入识别？
- subtype、数值与 datum 在哪一层存在，在哪一层第一次消失？
- 第 85/88 项的真实 runtime payload 与 raw Provider evidence 是什么？
- 当前测试证明的是模型能力，还是 frozen/synthetic projection 行为？
- typed GD&T 的唯一 Owner 和最小稳定合同应是什么？

## Initial Decisions

- 采用 Standard documentation/audit lane；发现 future schema/runtime change 属 Heavy，但本轮不执行。
- 并行使用两个不重叠 read-only profile：detection/recognition mapping 与 contract/UI audit。
- 以 current runtime API + PostgreSQL JSONB + immutable inventory/provider artifacts 作为最终事实。

---

## Discussion Timeline

### Round 1 - Codebase Exploration (`2026-08-01T09:42:00+08:00`)

#### User Input

要求沿 input -> detection -> crop -> OCR/VLM -> normalization -> persistence -> API -> UI
完成现状审计，并区分“模型未识别”和“识别后被丢弃”。

#### Decision Log

- Decision: 不把现有 `coarse_type="geometric_tolerance"` 误报为 typed GD&T support。
- Reason: Provider schema、projection 和 exact-four-field tests 共同证明正式 payload 无结构化字段。
- Impact: 审计分别记录 raw evidence、normalized candidate 和 UI surface。

#### Key Findings

- `VisualObservation` 是 text line + adjacent vector path 的 context，不是 frame detector。
- Qwen schema 只区分 parallelism/perpendicularity/flatness 三种 GD&T subtype。
- projection 只输出 raw text、coordinates、coarse type、confirmation。
- 无 cell splitting、modifier、diameter-zone、composite frame schema。

#### Corrected Assumptions

- ~~系统可能只识别“几何公差”大类~~ -> raw VLM 已能识别三种 subtype，业务投影才统一成大类。
- ~~系统直接 OCR 整个公差框再只取数字~~ -> 实际是 native/OCR text + VLM symbol class + deterministic projection。

#### Narrative Synthesis

起点是 UI 现象；本轮把问题收敛为两个 Owner boundary：ROI/text association 与
candidate normalization。剩余问题是用真实第 85/88 项判定 `A` 的具体失联层。

### Round 2 - Runtime Trace (`2026-08-01T10:05:00+08:00`)

#### Decision Log

- Decision: 把 project `9b9911d1-e64e-47a3-b8e5-539aa466dd40` 作为截图现象对应的 live evidence handle。
- Reason: API/DB 中第 85 项为 `∥ 0.1`，第 88 项为 `⏥ 0.08`，与用户描述精确匹配。
- Impact: 可以逐层区分真实数据和静态推断。

#### Key Findings

- inventory 中 datum `A` 存在，bbox 落在 parallelism ROI 内。
- parallelism `VisualObservation.associated_text_observation_ids` 只有两个 `0.1` IDs。
- raw Provider response 为 `gdt_parallelism`/0.97 与 `gdt_flatness`/0.96。
- AutomaticResult、working copy、API 保持 coarse payload；UI 没有独立 datum 可渲染。

#### Corrected Assumptions

- ~~A 可能由模型识别后被 normalizer 删除~~ -> 当前 raw input association 已没有 A；unit test 证明如果 A 被关联，raw text 会保留它。
- ~~flatness 可能完全未识别~~ -> live Provider response 明确为 `gdt_flatness`。

#### Narrative Synthesis

真实证据把 subtype 与 datum 两类失败分开：subtype 是 post-recognition semantic loss；
datum 是 pre-normalization association/contract loss。API/UI 只是忠实传递已降级数据。

### Round 3 - Contract Synthesis (`2026-08-01T10:25:00+08:00`)

#### Decision Log

- Decision: canonical discriminator 使用 `item_type="geometric_tolerance"`；不同时新增独立可写 `category`/`measurement_type`。
- Reason: 避免三个同义字段形成多个 Owner。
- Impact: `category` 仅可作为派生兼容字段，`tolerance_type` 拥有 subtype。

- Decision: Provider 只返回 frame/cell evidence，candidate-domain normalizer 提交正式语义。
- Reason: 符合现有 Provider non-owner 与 deterministic validation 边界。
- Impact: frontend、API、database 都不能自行解释 raw model output。

#### Key Findings

- typed contract 必须保序保存 segments、datum references、modifiers 和 raw glyph。
- old `gdt_* -> CoarseCandidate` path 需要显式 retirement gate，不能长期双写。
- real image conditions 与 current drawing headed UI proof 是 readiness 必需项。

#### Narrative Synthesis

本轮将审计结论转为未来可执行合同，但不创建 implementation plan。所有会改变
standards context、schema 或 runtime 的开放决定保留给 future Heavy plan。

---

## Decision Trail

1. Raw evidence、normalized candidate、API/UI 分层报告，不用一个“识别失败”覆盖所有失败。
2. datum A 的第一确认丢失点定为 visual observation association / Provider input contract。
3. subtype 的第一确认语义丢失点定为 `project_visual_observation()` coarse projection。
4. 唯一 semantic Owner 定为 candidate-domain `GeometricToleranceNormalizer`。
5. 本轮只写 audit/spec/analysis artifacts，不修改代码、plan 或 contract matrix。

## Synthesis And Conclusions

### Executive Summary

当前是三类视觉 subtype detection + coarse fallback，不是结构化 GD&T。案例 A 的
subtype 和 datum 分别在两个不同边界失败；案例 B 的 flatness 已被模型识别但没有
成为 typed field。配套 Specs 定义了 typed union、frame/cell evidence、normalizer、
persistence/API/UI 和真实样本 gate。

### Recommendations

1. 在 future Heavy plan 中新增唯一 `GeometricToleranceNormalizer` 和 typed candidate。
2. 先修 frame 内所有独立 text line 的 association，再扩 Provider frame/cell evidence schema。
3. 用 Case A/B + modifier/composite real crops 建立 contract -> persistence -> API -> UI 闭环。
4. 替代路径验证后退役 supported GD&T 的 coarse projection，禁止 frontend raw-text parser。

### Remaining Open Questions

- 首个 standards context 与 modifier scope。
- `▱/⏥` glyph alias policy。
- historical coarse data 的 migration/read strategy。
- scanned frame detector 的 latency/accuracy gate。

### Session Statistics

- Rounds: 4
- Key findings: 12
- Dimensions covered: 8
- Artifacts: 6
- Decisions: 5

### Round 4 - Independent Review (`2026-08-01T10:40:00+08:00`)

#### Review Summary

- Verdict: `accept with concerns`
- Concern 1: live Case A/B 缺少仓库内可定位 receipt。
- Concern 2: OCR orchestration symbol 写成不存在的 `RuntimeRecognition.recognize()`。
- Concern 3: unsupported/ambiguous 新 GD&T 仍可能走 coarse path，single owner 不够绝对。
- Concern 4: multi-layer shape、modifier v1 scope、派生字段存在双重表达。

#### Decisions And Corrections

- 新增脱敏 sealed receipt，记录 source/inventory/provider SHA-256 和两个案例的逐层证据。
- OCR owner 修正为 `RuntimeRecognition.build_inventory()`，实际调用为 `OcrProvider.recognize_png()`。
- 所有新 GD&T/疑似 GD&T 输入强制进入 normalizer；unsupported 只能 typed unknown/Coverage ambiguity。
- multi-layer 唯一使用 `frames[] -> segments[]`；v1 modifier 冻结为 M/L/S/unknown；symbol 与 normalized text 单向派生。

#### Narrative Synthesis

独立审查没有改变根因结论，但把 runtime 可复核性和目标 single-owner schema 收敛成
更严格的合同。所有 concern 已在 durable audit/spec/receipt 中处理。
