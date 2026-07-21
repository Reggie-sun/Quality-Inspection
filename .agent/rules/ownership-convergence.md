# Ownership Convergence Rules

本文件定义通用 control-plane role、单一 Owner、旧路径退役和过渡层生命周期。它不定义业务模块或 lane。

## 1. Role Contract

任何会决定、改写、选择、阻断或修复业务行为的模块，都要声明全部 active roles，不得只声明主要角色而隐藏次要 writer：

| Role | Allowed authority | Forbidden behavior |
| --- | --- | --- |
| `Signal Provider` | 提供结构化事实、候选或置信度 | 提交最终业务决策 |
| `Advisor` | 提供建议、排序或 proposed action | 静默覆盖 Owner |
| `Executor` | 执行 Owner 已提交的 contract | 重算上游语义 |
| `Validator` | 校验 contract 或结果 | 自行选择替代业务路径 |
| `Veto Gate` | 基于明确安全边界阻断 | 创建新的业务路径 |
| `Repairer` | 在声明的不变量内修复格式或局部结果 | 改变不属于它的 decision dimension |
| `Owner` | 对一个明确 decision dimension 提交最终结果 | 与另一个 active Owner 并存 |

每个 decision dimension 只能有一个 active `Owner`。模块同时承担 `Owner + Validator + Repairer` 时，plan 必须证明职责无法安全拆分，并排除自我校验和自我放行。

## 2. No Silent Semantic Override

- structured contract 产生后，下游不得重读 raw input、legacy state 或 diagnostics，重新提交同一语义结论。
- fallback 属于原 decision dimension 的 Owner；fallback 改变业务语义时，必须按 Owner replacement 审查。
- final result 提交后，只允许 observer、telemetry 或 persistence；任何可见 mutation 都是第二 final Owner。
- Veto Gate 只能阻断，不能被普通 Repairer 静默撤销。

## 3. Old Path Retirement

替代旧路径时，同一变更必须选择一个动作：

- `remove`：消费者已迁移并完成验证，直接删除。
- `replace`：新 Owner 接管，旧入口在同一变更失效。
- `mark`：存在 verified real consumer、但当前变更无法安全删除时暂存；必须记录 consumer、target Owner、exit trigger、explicit deadline 和 last verification。consumer inventory 证明为 none 时必须在当前变更删除，inventory 未完成时 verdict 为 `blocked`。
- `preserve`：仅允许仍是 canonical active path 且尚未发生 replacement 的逻辑；必须命名真实 consumer，并解释为什么不形成第二 Owner。

一旦新 Owner 接管，旧路径只能选择 `remove / replace / mark`。任何作为 transitional/legacy surface 的 bridge、readthrough、shadow、flag、fallback 或 wrapper 跨当前变更保留时，都必须使用 `mark` 合同，记录 verified real consumer、target Owner、exit trigger、explicit deadline 和 last verification。

不得把为迁移、兼容、对比或旧路径保留而存在的 transitional/legacy bridge、readthrough、shadow、flag、fallback 或 wrapper 当成永久状态。canonical stable surface 不适用 transition deadline，但必须有唯一 Owner、真实 consumer、明确 contract 与验证证据，且不得用于隐藏 replaced logic。

## 4. Transition Lifecycle

- bridge/readthrough 只允许比较、透传或记录差异，不拥有最终语义；最多保留一个 development cycle，到期必须通过 `remove / replace` 终止该角色。verified external consumer 确实要求兼容时，只能在到期时转换为明确分类的 compatibility adapter，并用 `mark` 记录 consumer、Owner、exit trigger、explicit deadline 和 last verification；不得继续以 bridge/readthrough 身份存在。adapter 到期必须删除，否则 verdict 为 `blocked`。
- 新建 shadow-only path 必须先有真实 consumer、明确 Owner 和 promotion/delete trigger；缺任一项立即拒绝，不进入 grace period。
- 已发现的 legacy shadow 只有在 verified real consumer 存在、但 Owner/trigger migration 尚未完成时，才可通过 `mark` 获得最多两个 development cycles 的 grace period；consumer 为 none 时当前变更立即删除，consumer inventory 未完成时 verdict 为 `blocked`。到期必须删除，否则 verdict 为 `blocked`。
- compatibility adapter 必须指出仍在依赖它的外部 consumer；“可能有人使用”不是证据。

一个 development cycle 是从 current task contract 经 implementation、focused verification 到适用的 commit 或 handoff 的闭环；spec/plan 只在 lane 要求时存在，commit 只在 Git 适用时存在。

## 5. Failure Generalization

- 单个失败样本只直接产生 regression coverage。
- 全局 production rule 必须有 shared-mechanism evidence；两个独立变体可以加强该证据，但不能替代机制证明。
- 根因位于上游 artifact、input、validation 或 data transformation 时，优先修上游，不在下游堆特判。
- 测试通过只证明已覆盖行为，不证明 Owner 唯一、旧路径退出或复杂度下降。

## 6. Removal Candidate Format

```text
[REMOVAL_CANDIDATE] <path-or-symbol>
  reason: <why this path is transitional or duplicate>
  owner: <target owner after removal>
  real_consumer: <verified current consumer>
  trigger: <deletion or convergence condition>
  deadline: <explicit development-cycle or date deadline>
  last_verification: <evidence and date>
```

标记沿用 `workflow-lanes.md` 的 primary surface 顺序：写入 current approved plan；没有时写 current task contract。review/final 只能镜像，不得成为 primary record，也不创建永久 cleanup registry。若没有能够跨 cycle 保留的现有 task surface，不得延期：立即删除或将 verdict 记为 `blocked`。

## 7. Review Checklist

- 本次改变了哪个 decision dimension？
- active Owner before/after 是谁？
- changed dimension 的全部 producer、writer、repairer、fallback 和 recomputation point 是什么？各模块的全部 active roles 是什么？
- 唯一 final effective write 的精确 path/symbol/surface 是什么？
- 是否有第二模块重读原始输入并重做同一判断？
- 旧路径执行了 `remove / replace / mark / preserve` 中哪个动作？
- 新增了多少 branch、fallback、flag、shadow、wrapper 和 helper？
- 哪个真实 consumer 阻止进一步删除？
- 每条保留的旧路径或 transitional path 的 real consumer 和 exit condition 是什么？
- focused verification 是否同时覆盖 active、failure 和 transition path？
- control-plane complexity 是 `increase / unchanged / decrease`，依据是什么？

新增 active Owner 而未退役旧 Owner 的变更不得完成。
