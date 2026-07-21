# Generic Agent Rules Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Task 1 baseline 为空的 `Quality_Inspection` 目录中建立五文件、无业务耦合、不会伪装成已启用自动化的 coding-agent bootstrap contract。

**Architecture:** `AGENTS.md` 只做入口与硬边界；三个 `.agent/rules/*.md` 分别唯一拥有 lane、日常执行和 control-plane ownership；`.ai-native/README.md` 只声明 automation 尚未安装。所有内容从 `Enterprise-grade_RAG` 的通用 invariant 重写，不复制其业务路径、命令或 runtime artifacts。

**Tech Stack:** Markdown、CommonMark、`rg`、POSIX shell、Python 3 标准库。

---

## Source Of Truth

- Approved spec: `docs/superpowers/specs/2026-07-21-generic-agent-rules-bootstrap-design.md`
- Target root: `/home/reggie/vscode_folder/Quality_Inspection`
- Source evidence only: `/home/reggie/vscode_folder/Enterprise-grade_RAG/AGENTS.md`, `.agent/`, `.ai-native/`

若本计划与 approved spec 冲突，以 spec 为准。源仓文件只提供 evidence，不得成为目标仓的运行时依赖。

## Execution Selection

- Selected lane: `Standard`（跨文件 control-plane 文档，会改变 agent 执行行为）。
- Selected plan: 本文件，经用户明确批准后按 `superpowers:subagent-driven-development` 执行。
- Selection evidence: 用户批准 revised design、要求开始写 specs，并选择当前 plan 的 subagent-driven execution；Task 1 执行时目标根目录为 non-Git bootstrap。
- Validation action: `close`；Task 7 final review accepted，Task 8 inventory 与 Git preservation checks 已通过，目标 bootstrap 已满足。
- Writer ownership and order: 无后续 writer；父 agent 只运行 `superpowers:verification-before-completion` fresh full validation 并提交 final report。
- Next verification: fresh 七文件 structure/exact-content/Owner/genericity/Git-index check；通过后结束本计划。

Git state amendment（2026-07-21 12:09 +08:00）：Task 1 baseline 执行时目标确认为 non-Git；Task 6 review 时发现目标根目录已由并发外部工作初始化为独立 Git 仓库，并存在与本任务无关的 commit `1b8065c`。本任务没有运行 `git init`，不删除或改写该 Git 状态；本次规则文件保持 unstaged/uncommitted，并在 final cross-file validation 重新核对。

## File Map

| File | Responsibility | Must not own |
| --- | --- | --- |
| `AGENTS.md` | 规则优先级、启动入口、bootstrap state、硬边界、完成合同 | 完整 Fast Gate、lane 表、AI-native 配置 |
| `.agent/rules/workflow-lanes.md` | Fast Gate、Lite/Standard/Heavy、workflow spine、plan continuation、verification evidence selection | Git 细节、delegation SOP、AI-native runtime |
| `.agent/rules/coding-rules.md` | 读取、编辑、debug evidence、已选验证执行、Git、delegation dispatch execution | lane/evidence selection、delegation eligibility、completion reporting、第二套 Owner taxonomy |
| `.agent/rules/ownership-convergence.md` | control-plane roles、单一 Owner、旧路径退役、bridge/shadow 生命周期 | 业务模块路径、目标仓未存在的命令 |
| `.ai-native/README.md` | `disabled / not installed` 状态和未来 activation gate | 可执行 config、schema、eval、scheduler 语义 |

五个文件是一个原子 control-plane unit。Task 1 baseline 时目标不是 Git 仓库；后来出现的并发外部 Git 状态必须保留，本任务不得运行 `git init`、stage 或 commit。

## Task 1: Lock The Bootstrap Baseline

**Files:**

- Read: `docs/superpowers/specs/2026-07-21-generic-agent-rules-bootstrap-design.md`
- Verify absent: `AGENTS.md`
- Verify absent: `.agent/`
- Verify absent: `.ai-native/`

- [x] **Step 1: Confirm the approved spec is present**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f docs/superpowers/specs/2026-07-21-generic-agent-rules-bootstrap-design.md
```

Expected: exit `0` with no output.

- [x] **Step 2: Confirm no implementation file already exists**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test ! -e AGENTS.md
test ! -e .agent
test ! -e .ai-native
```

Expected: all three checks exit `0`. If any path exists, stop, inspect it, and amend the plan rather than overwriting it.

- [x] **Step 3: Record the Git boundary**

Run:

```bash
if git -C /home/reggie/vscode_folder/Quality_Inspection rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo TARGET_GIT_REPO
else
  echo TARGET_NOT_GIT_REPO
fi
```

Expected for the current baseline: `TARGET_NOT_GIT_REPO`. Do not run `git init`.

- [x] **Step 4: Capture the allowed implementation paths**

Allowed paths for all later tasks:

```text
AGENTS.md
.agent/rules/coding-rules.md
.agent/rules/workflow-lanes.md
.agent/rules/ownership-convergence.md
.ai-native/README.md
```

Forbidden paths include `.agent/harness/`, `.agent/context/`, `.agent/skills/`, `.agent/commands/`, `.agent/specs/`, `.agent/runs/`, `.ai-native/config.yaml`, `.ai-native/schemas/`, `.ai-native/evals/`, `.ai-native/runtime/`, and `.ai-native/reports/`.

## Task 2: Create The Thin Entry Contract

**Files:**

- Create: `AGENTS.md`

- [x] **Step 1: Run the entry-contract existence check and verify it fails**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f AGENTS.md
```

Expected: non-zero because `AGENTS.md` does not exist yet.

- [x] **Step 2: Create `AGENTS.md` with this exact content using `apply_patch`**

```markdown
# Quality Inspection Agent Guide

本仓库使用薄入口、分层承载、单一 Owner 的 coding-agent workflow。

## 1. Authority And Rule Layers

同一职责域内的优先级从高到低：

1. `AGENTS.md`
2. `.agent/rules/workflow-lanes.md`
3. `.agent/rules/coding-rules.md`
4. `.agent/rules/ownership-convergence.md`
5. `.ai-native/README.md`

`.ai-native/README.md` 只拥有 AI-native automation 的 activation state，不拥有 workflow 或 execution 决策。

`AGENTS.md` 只拥有入口、优先级、硬边界和完成合同。下位文件补充执行细节，不得重定义上位规则，也不得建立第二套 workflow。

## 2. Start Here

开始任何任务时：

1. 先读本文件。
2. 读 `.agent/rules/coding-rules.md`。
3. 用 `.agent/rules/workflow-lanes.md` 判断 `Lite / Standard / Heavy`。
4. 只有触碰决策 ownership、fallback、bridge、shadow 或旧路径替代时，才读 `.agent/rules/ownership-convergence.md`。
5. 当前 AI-native automation 为 `disabled / not installed`；`.ai-native/README.md` 只拥有 activation state 的细节，目录存在不是已启用的证据。

workflow spine、lane 和 planning 条件只由 `.agent/rules/workflow-lanes.md` 定义；本文件只提供入口，不提交这些 decision dimensions 的独立结论。

## 3. Bootstrap State

仓库可能尚未初始化 Git、语言栈、测试框架、构建命令或 runtime。缺少这些能力时：

- 不得发明命令、路径、服务、账号、端口或验证结果。
- 只运行当前文件系统能够证明存在的检查。
- 未运行的测试必须明确写为未运行，并说明原因。
- Git 不存在时不得擅自执行 `git init`、commit、branch、worktree 或其他仓库初始化动作。
- 新增项目技术栈、测试框架或 runtime 之前，必须先通过新的 spec/plan 授权并记录规则树变更；accepted final rule 必须写入对应 Owner 文件，spec/plan 本身不成为 durable rule source。

## 4. Hard Boundaries

本节是上游 `Veto Gate`：只能阻断越界执行，不选择 lane、current plan 或 validation action。

- 默认高自治执行，但只在用户目标、scope、Owner 和验证方式明确时继续。
- 破坏性、不可逆、权限扩张、稳定 contract 变更、runtime config 变更、实质 scope expansion 或无法安全隔离的已有改动冲突，必须停下请求用户决策。
- 保护用户已有文件和未提交改动；不得 reset、revert、覆盖或顺手清理无关内容。
- 每一项修改都必须直接追溯到当前用户目标。
- 不读取、输出、记录或提交 credential、token、cookie、password 或私密环境值。
- bug、error、regression 和 unexpected behavior 的 root-cause workflow 由 `.agent/rules/workflow-lanes.md` 唯一拥有；本文件不重复提交该决策。
- 不得用文档、旧 receipt、日志摘要或测试数量替代当前真实验证。

## 5. Delegation Boundary

当前父 agent 保留 scope、plan、integration、review、verification 和最终 verdict。只有 delegation 能明显降低上下文、时间、实现风险或验证不确定性时才使用子代理；writer 必须有明确且互不重叠的文件 ownership。详细纪律由 `.agent/rules/coding-rules.md` 拥有。

## 6. Completion Contract

每次修改完成后必须说明：

- 改了什么。
- 验证了什么，以及哪些检查没有运行。
- 仍有什么风险或 blocker。

文档改动必须明确写“docs-only，没有运行代码测试”。只有实际运行并通过的检查才能被报告为通过。
```

- [x] **Step 3: Verify the entry contract owns only top-level concerns**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f AGENTS.md
test "$(rg -n '^## [0-9]+\. ' AGENTS.md | wc -l)" -eq 6
! rg -n '^## Fast Gate$|^### Lite$|^### Standard$|^### Heavy$' AGENTS.md
```

Expected: all commands exit `0`; the final `rg` finds no lane-definition headings.

## Task 3: Create The Single Lane Owner

**Files:**

- Create: `.agent/rules/workflow-lanes.md`

- [x] **Step 1: Create the rules directory**

Run:

```bash
mkdir -p /home/reggie/vscode_folder/Quality_Inspection/.agent/rules
```

Expected: directory exists and no other `.agent` subtree is created.

- [x] **Step 2: Run the lane-owner existence check and verify it fails**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .agent/rules/workflow-lanes.md
```

Expected: non-zero because the file does not exist yet.

- [x] **Step 3: Create `.agent/rules/workflow-lanes.md` with this exact content using `apply_patch`**

```markdown
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
```

- [x] **Step 4: Verify this is the only lane-definition file**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .agent/rules/workflow-lanes.md
test "$(rg -l '^## 1\. Fast Gate$' AGENTS.md .agent/rules/*.md | wc -l)" -eq 1
test "$(rg -l '^### Lite$' AGENTS.md .agent/rules/*.md | wc -l)" -eq 1
```

Expected: both ownership counts equal `1`, and the matching file is `workflow-lanes.md`.

## Task 4: Create The Daily Execution Rules

**Files:**

- Create: `.agent/rules/coding-rules.md`

- [x] **Step 1: Run the coding-rules existence check and verify it fails**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .agent/rules/coding-rules.md
```

Expected: non-zero because the file does not exist yet.

- [x] **Step 2: Create `.agent/rules/coding-rules.md` with this exact content using `apply_patch`**

```markdown
# Coding Rules

本文件拥有日常读取、编辑、debug evidence gathering、已选验证的执行、Git 和 delegation dispatch execution。lane、root-cause workflow 触发条件和 verification evidence precedence/selection 只由 `workflow-lanes.md` 拥有；delegation eligibility 和 completion reporting 只由 `AGENTS.md` 拥有。

## 1. Discovery

- 先读直接相关实现、调用方、测试和文档，再修改。
- 不确定模块归属时先搜索真实 entry point 和 consumer，不按目录名猜测。
- 文本和文件搜索优先使用 `rg` 与 `rg --files`。
- 结构性关系、调用链或高连接模块需要专门结构工具时，先确认工具可用；不可用时明确说明证据边界。
- 现有未提交改动属于用户或其他进行中任务，不得视为可清理垃圾。

## 2. Editing

- 每一行改动都必须直接追溯到当前用户目标。
- 优先最小、稳定、可验证的方案。
- 不添加 speculative feature、单次 abstraction、无 consumer wrapper 或未请求配置。
- 匹配仓库已有命名、import、module boundary 和本地风格。
- 使用 `apply_patch` 做常规文本编辑。
- 清理只由本次修改产生的 orphan；无关 cleanup 只报告，不执行。

## 3. Debugging

- root-cause workflow 的触发和前置条件遵循 `workflow-lanes.md`；本节只定义证据收集与修复纪律。
- 对已进入 root-cause workflow 的问题建立可证伪 hypothesis。
- 用代码、日志、测试或可复现行为验证 hypothesis 后再修复。
- 修 root cause，不为单个样本添加 exact-input 特判。
- 如果实现改变既有行为，添加 regression coverage 或运行最近的现有验证。

## 4. Verification

- 按 `workflow-lanes.md` 已提交的 claim-specific evidence precedence 和 failure surface 执行验证，本节不重新选择 validation action。
- 只执行被选定检查的真实命令；不得把 lint、type check、unit test、integration、smoke 或 runtime replay 相互替代。
- 不声称未实际运行的检查通过。
- 没有测试框架或可执行入口时，明确写“没有可执行代码测试”，并运行能够证明文档、配置或文件合同的静态检查。
- 长时间检查期间提供简短进度；一次 timeout 不等于失败。

## 5. Git Safety

只有当前目录位于 Git worktree 时才应用以下规则：

- 本地 status、diff、staging、commit、merge 和 worktree 真相使用 shell `git`。
- stage 具体文件，禁止 `git add .`。
- 不 reset、revert、覆盖或清理用户未授权的改动。
- commit 前复查精确 diff 和 staged files。
- 目标不是 Git 仓库时，不得擅自 `git init`；只报告当前文件状态。

## 6. Delegation

- 是否使用 delegation 只由 `AGENTS.md` 决定；本节只执行已经选定的 dispatch，不重新判断 eligibility。
- read-only explorer 用于代码地图、依赖追踪、测试发现和独立证据。
- 每个 task prompt 必须明确 role、scope、authority、boundaries、禁止 nested delegation、规则冲突时停止并报告、expected output 和 verification requirement。
- write-capable worker 只用于 allowed paths 明确、ownership 不重叠的叶子任务；写前检查 ownership overlap，不 revert 或 overwrite 他人改动，并假设存在并发工作。
- reviewer 必须独立检查真实 diff、行为边界和验证证据，不替父 agent 做最终 verdict。
- 子代理不得递归创建或协调其他子代理。
- wait timeout 只是轮询上限；中断前检查消息、工具输出和合理的长运行解释。
- 父 agent 负责综合冲突、复核关键证据、review final diff 和决定收口。

## 7. Delivery

`AGENTS.md` 的 Completion Contract 是唯一 final-report contract，本文件不增加 required fields。交付时只组装当前任务实际收集的 evidence，并按 `AGENTS.md` 报告。
```

- [x] **Step 3: Verify coding rules do not redefine lanes**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .agent/rules/coding-rules.md
! rg -n '^## Fast Gate$|^### Lite$|^### Standard$|^### Heavy$|\| `Lite` \|' .agent/rules/coding-rules.md
```

Expected: file exists; the ownership scan returns no matches.

## Task 5: Create The Ownership Convergence Rules

**Files:**

- Create: `.agent/rules/ownership-convergence.md`

- [x] **Step 1: Run the ownership-rules existence check and verify it fails**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .agent/rules/ownership-convergence.md
```

Expected: non-zero because the file does not exist yet.

- [x] **Step 2: Create `.agent/rules/ownership-convergence.md` with this exact content using `apply_patch`**

````markdown
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
````

- [x] **Step 3: Verify the rule is generic and self-contained**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .agent/rules/ownership-convergence.md
! rg -ni 'enterprise-grade_rag|ragflow|portal|sample-governance|retrieval|citation|qdrant|\.branch-runtime' .agent/rules/ownership-convergence.md
test "$(rg -n '^\| `Owner` \|' .agent/rules/ownership-convergence.md | wc -l)" -eq 1
```

Expected: no source-specific terms; the Owner role is defined exactly once.

## Task 6: Create The AI-Native Activation Boundary

**Files:**

- Create: `.ai-native/README.md`

- [x] **Step 1: Create the AI-native directory without runtime subdirectories**

Run:

```bash
mkdir -p /home/reggie/vscode_folder/Quality_Inspection/.ai-native
```

Expected: `.ai-native/` exists and is empty before the README is added.

- [x] **Step 2: Run the activation-boundary existence check and verify it fails**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .ai-native/README.md
```

Expected: non-zero because the file does not exist yet.

- [x] **Step 3: Create `.ai-native/README.md` with this exact content using `apply_patch`**

```markdown
# AI-Native Automation Status

**Status:** `disabled / not installed`

本目录只声明 activation boundary。它不是 runtime、harness、evaluation、promotion、scheduler 或 release system 已启用的证据。

## Current State

- 没有 executable runner 或 CLI。
- 没有 runtime config、ledger 或 scheduler。
- 没有 trusted component registry。
- 没有 schemas 的实际 consumer。
- 没有 train/holdout evaluation engine。
- 没有 focused tests 或 smoke command。

因此，coding agent 不得声称 AI-native automation 已运行、已验证或已保护本仓库，也不得执行猜测出来的命令。

## Forbidden Partial Installation

没有 runner 和 tests 时，禁止只加入看似可执行的 config、schemas、eval cases、registry 或 report 目录。半套文件会制造虚假的安全和验证信号。

## Activation Gate

未来启用必须先通过独立 spec 和 implementation plan，并在同一交付中具备：

1. 目标仓可执行 runner 和明确 CLI entry。
2. 基于目标仓真实路径的 runtime config 和 protected paths。
3. runner 实际消费的完整 schemas。
4. train 与 evaluator-only holdout cases。
5. 从目标仓真实 entry points 生成的 component registry。
6. ledger、report 和 cleanup lifecycle。
7. deterministic hard gates、risk levels、rollback 和 stop conditions。
8. focused tests、negative tests 和至少一次真实 smoke receipt。

component registry 必须生成，禁止从其他仓库复制 inventory。activation 前，本目录应继续只包含本 README。
```

- [x] **Step 4: Verify no partial runtime was created**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test -f .ai-native/README.md
test "$(find .ai-native -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)" = "README.md"
rg -n '^\*\*Status:\*\* `disabled / not installed`$' .ai-native/README.md
```

Expected: `.ai-native` contains only `README.md`; status match is printed once.

## Task 7: Validate The Cross-File Contract

**Files:**

- Verify: `AGENTS.md`
- Verify: `.agent/rules/coding-rules.md`
- Verify: `.agent/rules/workflow-lanes.md`
- Verify: `.agent/rules/ownership-convergence.md`
- Verify: `.ai-native/README.md`

- [x] **Step 1: Verify the exact runtime rule file set**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
find AGENTS.md .agent .ai-native -type f -print | sort
```

Expected exactly:

```text
.agent/rules/coding-rules.md
.agent/rules/ownership-convergence.md
.agent/rules/workflow-lanes.md
.ai-native/README.md
AGENTS.md
```

- [x] **Step 2: Run the forbidden source-coupling scan**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
! rg -ni 'enterprise-grade_rag|ragflow|portal|sample-governance|qdrant|\.branch-runtime|verify-retrieval|retrieval-plan' \
  AGENTS.md .agent .ai-native
```

Expected: exit `0` with no matches.

- [x] **Step 3: Run the dangling executable-reference scan**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
! rg -n '`(make|pytest|npm|pnpm|yarn|docker|python scripts/|scripts/ai_native/|\.agent/harness/policy\.yaml)' \
  AGENTS.md .agent .ai-native
```

Expected: exit `0` with no executable references to tools or files that are not installed.

- [x] **Step 4: Run the Markdown structural validator**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
python - <<'PY'
from pathlib import Path

paths = [
    Path("AGENTS.md"),
    Path(".agent/rules/coding-rules.md"),
    Path(".agent/rules/workflow-lanes.md"),
    Path(".agent/rules/ownership-convergence.md"),
    Path(".ai-native/README.md"),
]
errors = []
for path in paths:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not text.endswith("\n"):
        errors.append(f"{path}:missing-final-newline")
    if any(line.rstrip() != line for line in lines):
        errors.append(f"{path}:trailing-whitespace")
    if sum(line.startswith("```") for line in lines) % 2:
        errors.append(f"{path}:unclosed-code-fence")
    for token in ("T" + "BD", "T" + "ODO", "FIX" + "ME", "PLACE" + "HOLDER"):
        if token in text:
            errors.append(f"{path}:placeholder:{token}")
print({"files": len(paths), "errors": errors})
raise SystemExit(1 if errors else 0)
PY
```

Expected:

```text
{'files': 5, 'errors': []}
```

- [x] **Step 5: Run the ownership uniqueness checks**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
test "$(rg -l '^## 1\. Fast Gate$' AGENTS.md .agent/rules/*.md | wc -l)" -eq 1
test "$(rg -l '^## 5\. Git Safety$' AGENTS.md .agent/rules/*.md | wc -l)" -eq 1
test "$(rg -l '^## 1\. Role Contract$' AGENTS.md .agent/rules/*.md | wc -l)" -eq 1
test "$(rg -l '^## Activation Gate$' .ai-native/README.md | wc -l)" -eq 1
```

Expected: every ownership count equals `1`.

- [x] **Step 6: Confirm no code test framework exists**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
for path in package.json pyproject.toml requirements.txt go.mod Cargo.toml Gemfile; do
  test ! -e "$path" || { echo "UNEXPECTED_RUNTIME:$path"; exit 1; }
done
echo DOCS_ONLY_NO_CODE_TEST_FRAMEWORK
```

Expected: `DOCS_ONLY_NO_CODE_TEST_FRAMEWORK`.

- [x] **Step 7: Request one independent read-only review**

The reviewer must check:

```text
Verdict: accept | accept with concerns | reject
Blocking issues
Non-blocking concerns
Evidence from exact files and headings
Whether an agent could infer a nonexistent command, runtime, or automation capability
Whether Fast Gate, coding discipline, ownership convergence, and activation state each have one Owner
Recommended minimal follow-up
```

Expected: `accept` or `accept with concerns` with no blocking issue. The parent agent must verify every blocking or important claim before changing the files.

## Task 8: Close The Docs-Only Delivery

**Files:**

- Review: all five runtime rule files
- Preserve: `docs/superpowers/specs/2026-07-21-generic-agent-rules-bootstrap-design.md`
- Preserve: `docs/superpowers/plans/2026-07-21-generic-agent-rules-bootstrap.md`

- [x] **Step 1: Review the final file list and modification scope**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
for path in \
  AGENTS.md \
  .agent/rules/coding-rules.md \
  .agent/rules/workflow-lanes.md \
  .agent/rules/ownership-convergence.md \
  .ai-native/README.md \
  docs/superpowers/specs/2026-07-21-generic-agent-rules-bootstrap-design.md \
  docs/superpowers/plans/2026-07-21-generic-agent-rules-bootstrap.md; do
  test -f "$path"
done
find . -path './.git' -prune -o -type f -print | sort
```

Expected: all seven task-owned files exist. The inventory may additionally contain files created by concurrent external work; preserve and report them instead of treating them as task output.

- [x] **Step 2: Preserve the concurrent Git state and do not commit**

Run:

```bash
cd /home/reggie/vscode_folder/Quality_Inspection
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git status --short
  echo TARGET_GIT_APPEARED_NO_COMMIT_PER_APPROVED_SPEC
else
  echo TARGET_NOT_GIT_REPO_NO_COMMIT
fi
```

Expected for the fresh state: `TARGET_GIT_APPEARED_NO_COMMIT_PER_APPROVED_SPEC`. The approved spec forbids creating a commit in this bootstrap task; do not stage files, initialize Git, or modify the concurrent repository state.

- [x] **Step 3: Produce the final report**

Use this exact reporting contract:

```text
Scope:
- Standard control-plane docs bootstrap; five runtime rule files.

Changes:
- Thin AGENTS entry contract.
- Single workflow lane Owner.
- Daily coding/Git/delegation rules.
- Generic ownership-convergence rules.
- Explicit AI-native disabled activation boundary.

Validation:
- Exact file-set check.
- Forbidden source-coupling scan.
- Dangling executable-reference scan.
- Markdown structural validation.
- Ownership uniqueness checks.
- Independent read-only review.
- Docs-only; no code test framework and no code tests run.

Risks:
- Rules remain bootstrap-generic until the repository gains a real technology stack.
- AI-native automation is intentionally not installed.
- Target was non-Git at Task 1 baseline, but concurrent external work later initialized Git and added an unrelated commit. This task preserved that state and created no commit; task files remain unstaged/uncommitted.
```

## NOT In Scope

- 初始化 Git 或创建 branch/worktree。
- 选择 Quality Inspection 的语言栈、框架、数据库或部署方式。
- 建立 `.agent/harness/policy.yaml` 或任何 executable harness。
- 移植 AI-native runner、config、schemas、evals、registry、scheduler 或 reports。
- 复制源仓的业务 rules、skills、commands、specs、runs、context 或 historical evidence。
- 编写应用代码、测试框架或 CI/CD。

## Execution Order

所有任务共享同一规则 ownership，必须串行执行：

```text
Task 1 baseline
  -> Task 2 AGENTS.md
  -> Task 3 workflow-lanes.md
  -> Task 4 coding-rules.md
  -> Task 5 ownership-convergence.md
  -> Task 6 .ai-native/README.md
  -> Task 7 validation and independent review
  -> Task 8 docs-only closure
```

Sequential implementation, no parallelization opportunity.
