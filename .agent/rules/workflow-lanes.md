# Workflow Lanes

本文件是 Fast Gate、lane contract、workflow spine、plan continuation，以及 verification evidence precedence/selection 的唯一 Owner。`AGENTS.md` 的 Hard Boundaries 是上游 Veto Gate，只能阻断，不能选择 lane、current plan 或 validation action；`AGENTS.md` 拥有入口、最低 truthfulness hard boundary 和 completion reporting。

## 1. Fast Gate

开始修改前回答三个问题：

1. 是否改变稳定 API/schema、认证授权、数据迁移、runtime entry、control-plane 或 workflow 真源？
2. 是否存在跨模块协作，或存在无法安全地作为一个局部改动处理和验证的多文件耦合？一个模块内的一到三个相关文件不因此命中此项。
3. 是否需要 integration、smoke、migration、security 或 contract verification 才能证明安全？

按最高风险答案选择 lane，不得为了减少流程要求而降级。

| Lane | Entry condition | Minimum contract |
| --- | --- | --- |
| `Lite` | 不命中 `Heavy` 或 `Standard`；一个模块内的一到三个相关文件、低风险 | 读相关实现和测试，最小改动，最接近真实行为的验证，focused review |
| `Standard` | 不命中 `Heavy`，且（存在跨模块协作，或存在无法安全地作为一个局部改动处理和验证的多文件耦合，或涉及 control-plane/workflow truth、shared non-runtime configuration，或需要 integration/smoke） | 明确 allowed paths、required reads、required checks，保留 plan/task contract，focused review |
| `Heavy` | 稳定 API/schema、认证授权、数据迁移、runtime entry/config、不可逆/破坏性操作，或跨模块 data-integrity/security boundary | 先写 spec/plan，明确 rollback，完成必要 integration/security/contract verification 和独立 review |

优先级映射如下：

- 只要命中稳定 API/schema、认证授权、数据迁移、runtime entry/config、不可逆/破坏性操作或跨模块 data-integrity/security boundary，选择 `Heavy`。
- 只有未命中 `Heavy`，且（存在跨模块协作，或存在无法安全地作为一个局部改动处理和验证的多文件耦合，或涉及 control-plane/workflow truth、shared non-runtime configuration，或需要 integration/smoke）时，选择 `Standard`。
- 只有两者均未命中时，才选择 `Lite`。
- 需要 integration/smoke 本身不意味着 `Heavy`；lane 由实际改变的 boundary 决定。
- 当 migration/security/contract verification 只是为了证明一个未改变的 boundary，且没有改变任何 `Heavy` boundary 时，选择 `Standard`；相应 boundary 本身发生改变时仍选择 `Heavy`。

## 2. Workflow Spine

统一主线：

`spec -> plan -> implement -> review`

spec 和 plan 是 conditional gates，不是每次修改都必须经过的阶段。若所选 lane 不要求 spec 或 plan，可以直接进入 implement；review 和 verification contract 仍然适用。

- 新功能、跨模块行为、稳定 contract、权限、数据迁移或 runtime 语义必须先写 spec。
- 多文件联动、风险或 rollback 不清楚、control-plane 改动必须先写 plan。
- bug、error、regression、stack trace 或 unexpected behavior 必须先形成并验证 root-cause hypothesis。
- 所有非文档代码改动默认需要 focused review。
- 会改变 agent 执行行为的文档或 control-plane 改动同样需要 focused review。

## 3. Lane Contracts

### Lite

- scope 限于当前用户目标。
- 不建立新的稳定 contract、Owner、fallback、wrapper 或配置面。
- 运行最小真实验证。
- final 报告改动、验证和风险。

### Standard

- 记录目标、allowed paths、保持不变的 contract 和 required checks。
- 多 writer 必须先完成 ownership overlap 检查。
- 需要 durable plan 或 task contract。
- 实现后完成 focused review 和 lane 对应检查。

### Heavy

- 先确认唯一 Owner、旧路径动作、rollback 和失败边界。
- 不得以 high-risk 为由停在分析；边界和验证明确后应继续完成闭环。
- `AGENTS.md` Hard Boundaries 是上游 Veto Gate；`Heavy` 只消费其 veto verdict，不重新定义它。
- 验证必须覆盖 active path 和 failure path。plan 必须定义 rollback 后的第一项验证；只有实际发生 rollback 时才运行该验证。

## 4. Plan Selection And Continuation

每次开始或恢复 plan execution 时，当前父 agent 只允许选择一个 current plan。证据优先级：

1. 最新用户明确目标、纠偏或点名的 plan/spec。
2. 当前 task contract 中仍有效的 `plan_ref`。
3. 同一目标下最新、可复现的 validation residual 或 blocker。
4. 与当前 branch/worktree 和代码事实一致的 handoff。
5. 其他 planning artifact 只能作为低优先级 signal。

fresh validation 必须映射为：

| Result | Action |
| --- | --- |
| 当前 step 的预期证据成立 | `continue` |
| 预期证据失败，但目标、root cause、Owner 和 scope 仍有效 | `continue`：保留当前 step，修复后重跑 |
| 目标和 Owner 不变，但 allowed paths/checks/order 需要改变 | `amend` |
| 证据证明目标已满足或实现已不必要 | `close` |
| 新增 Owner、stable contract、权限、runtime config 或实质 scope | `replan` |
| writer、dirty overlap、runtime identity 或关键外部信息不明 | `blocked` |

任何 amendment 都要记录 delta、依据、writer ownership 和下一项验证，不得静默扩大 scope。

### Repository-Owned Live Verification Standing Authorization

本仓库已获得用户对 repository-owned、plan-bounded external Provider live verification 的持续授权。满足以下全部条件时，执行 agent 不得再把“等待用户逐次授权”作为 gate，应在 zero-paid preflight 通过后直接继续：

- current approved plan 已明确命令、输入范围、Provider/model identity、cost/call/wall budget、acceptance evidence 和 failure stop；
- zero-paid preflight 已在任何 run creation、upload 或 Provider call 前证明 target worktree/runtime、API/worker code identity、database revision、credential presence 和隔离边界；
- 执行不改变 public/production deployment、credential value、account、billing policy 或 stable business contract，也不停止、替换或删除其他 runtime/data；current approved plan 可以明确授权仅重建其 isolated verification runtime 的指定 service，以加载既有 approved credential source 和 plan-bound mode/model，但必须记录 exact Compose project/files/services、使用 `--no-deps`、不改 volume/data，并在 paid work 前重新证明 runtime identity；
- 只执行 plan 明确允许的 run/attempt；失败后不得因 standing authorization 自动增加 retry、扩大 budget 或开启 replacement run。

runtime identity mismatch、credential 缺失、cost/budget scope 不明、paid attempt 已耗尽、public/production promotion、破坏性动作、权限扩张或实质 scope expansion 仍按 `AGENTS.md` Hard Boundaries fail closed。该 standing authorization 只移除重复的人为确认，不改变 Provider retry Owner、业务审批、review lock 或 formal acceptance gate。

每次 selection 必须记录 `Selected lane / Selected plan / Selection evidence / Validation action / Writer ownership and order / Next verification`，并按确定顺序选择恰好一个 primary surface：先写 current approved plan；没有时写 current task contract；仍没有时写 current progress update。final report 可以镜像最终状态，但绝不能作为 pre-execution selection record 的 primary surface。不得为此新建 registry 或 ledger。

## 5. Verification Truth

- runtime/current-behavior claim 的证据优先级是：current authenticated/live runtime evidence > current integration/smoke/replay > focused tests > static code inspection > docs/old receipt。
- implementation-intent claim 由 current code 加 current relevant tests 共同证明。
- architecture / Owner uniqueness / old-path retirement claim 必须由 current producer/consumer and call-site inventory 和 independent review 证明；适用时再补充 current configuration/activation state 与 focused behavior tests。存在矛盾的 active consumer 或 unresolved conflict 时，verdict 必须是 `blocked`，不得标记为 passed。
- runtime evidence 与 code/tests 冲突时，verdict 必须是 `blocked/runtime identity mismatch`，不得选择方便的证据下结论。
- integration 和 smoke 不可互换；必须选择最接近实际 failure surface 的验证。
- 只把实际执行的 tests、checks、smoke 或 replay 报告为通过。
- 验证不可用时，说明 blocker、未覆盖行为和剩余风险。
- 测试通过不自动证明 architecture、Owner 唯一性或旧路径已退役。
