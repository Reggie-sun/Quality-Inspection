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

以下文件属于当前执行状态、计划或领域事实来源，不参与上述规则优先级竞争：

- `docs/contracts/MAIN_CONTRACT_MATRIX.md`
  - 拥有长期稳定系统语义。
- `docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md`
  - 拥有当前 P0 契约选择、任务和验证映射。
- `docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`
  - 拥有当前 Day / Task 的实施顺序和文件级执行步骤。
- `.agent/EXECUTION_STATUS.md`
  - 只记录已经验证的执行进度、commit、当前任务和 blocker。
  - 不拥有 workflow、scope 或契约语义。
- `.agent/harness/runs/<run-id>/`
  - 只拥有某次代码、配置和输入的实际执行证据。

计划、status、receipt 和 run evidence 不得反向覆盖稳定契约或仓库规则。

## 2. Start Here

开始任何任务时：

1. 先读本文件。
2. 读 `.agent/rules/coding-rules.md`。
3. 用 `.agent/rules/workflow-lanes.md` 判断 `Lite / Standard / Heavy`。
4. 只有触碰决策 ownership、fallback、bridge、shadow 或旧路径替代时，才读 `.agent/rules/ownership-convergence.md`。
5. 读取 `.agent/EXECUTION_STATUS.md`，确认当前 branch、worktree、已完成任务、当前任务和 blocker。
6. 用户指定现有 implementation plan 时，读取该 plan 的全局约束、当前 Day 和当前 Task；不得只读取任务局部步骤。
7. 当前 AI-native automation 为 `disabled / not installed`；`.ai-native/README.md` 只拥有 activation state 的细节，目录存在不是已启用的证据。

workflow spine、lane 和 planning 条件只由 `.agent/rules/workflow-lanes.md` 定义；本文件只提供入口，不提交这些 decision dimensions 的独立结论。

当前 P0 的默认 implementation plan 为：

`docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md`

只有用户明确切换计划或批准新计划后，才允许改变 current plan。

## 3. Bootstrap State

仓库可能尚未初始化 Git、语言栈、测试框架、构建命令或 runtime。缺少这些能力时：

- 不得发明命令、路径、服务、账号、端口或验证结果。
- 只运行当前文件系统能够证明存在的检查。
- 未运行的测试必须明确写为未运行，并说明原因。
- Git 不存在时不得擅自执行 `git init`、commit、branch、worktree 或其他仓库初始化动作。
- 新增项目技术栈、测试框架或 runtime 之前，必须先通过新的 spec/plan 授权并记录规则树变更；accepted final rule 必须写入对应 Owner 文件，spec/plan 本身不成为 durable rule source。
- 不得把计划中的示例代码、预期路径或预期命令报告为仓库中已经存在的实现。
- 不得因为 plan 声明某项应当完成，就跳过当前文件、Git 状态和运行证据检查。

## 4. Hard Boundaries

本节是上游 `Veto Gate`：只能阻断越界执行，不选择 lane、current plan 或 validation action。

- 默认高自治执行，但只在用户目标、scope、Owner 和验证方式明确时继续。
- 破坏性、不可逆、权限扩张、稳定 contract 变更、runtime config 变更、实质 scope expansion 或无法安全隔离的已有改动冲突，必须停下请求用户决策。
- 保护用户已有文件和未提交改动；不得 reset、revert、覆盖或顺手清理无关内容。
- 每一项修改都必须直接追溯到当前用户目标。
- 不读取、输出、记录或提交 credential、token、cookie、password 或私密环境值。
- bug、error、regression 和 unexpected behavior 的 root-cause workflow 由 `.agent/rules/workflow-lanes.md` 唯一拥有；本文件不重复提交该决策。
- 不得用文档、旧 receipt、日志摘要、测试数量、代码行数或契约覆盖数量替代当前真实验证。
- 不得把 Provider、frontend、diagnostic surface、validator 或 Harness 提升为正式业务语义 Owner。
- 不得因为长期契约中存在某个实体，就自动将对应 P1/P2 能力加入当前 P0。
- 七天 P0 的实施范围只来自 approved design spec Section 10；Sections 1～9 只约束长期方向。
- 只能执行用户当前明确指定的 Day 和 Task IDs。
- 不得顺带执行后续 Task，也不得因为后续依赖已经清楚而提前实现。
- 同一 task 的同一 file group 同时只能有一个 writer。
- reviewer、auditor 和 research 子代理必须保持只读。
- 当 `collaboration.spawn_agent` schema 不暴露 `agent_type` / `profile` 时，不得据此断言 local profile 不可绑定：先确认 runtime 使用 `~/.codex/bin/codex-spawn-profile-fix`（或经同一 child rollout 三字段验证的等价实现），再用 `task_name="<profile>__<task>"` 和 `fork_turns="none"` 选择 task-name-safe profile；派发后必须从 child rollout metadata 核验实际 `agent_role` / `model` / `reasoning_effort`。只有此前缀通路不可用、profile 名称不符合 `task_name` 字符集或 live proof 失败时，才允许明示 generic fallback；不得静默改名，也不得把 task name 本身当成 profile 已加载的证据。
- 不得用 synthetic fixture、旧 baseline 或自动生成结果冒充 current-four 的真实 live evidence。
- 未通过正式 freeze 的 working copy 不得用于正式编号或正式导出。
- PDF、Excel 和 manifest 不得混用不同的 `reviewed_result`。
- fatal 或 blocking failure 不得通过 warning、accepted risk 或人工文字说明转换为 formal success。

## 5. Active P0 Execution Guardrails

本节只约束当前 PDF Auto-Balloon 七天 P0 的执行，不改变长期 workflow spine。

### 5.1 Current execution boundary

当前实施闭环仅为：

```text
上传原始工程 PDF
→ 原生解析及必要 OCR
→ 自动候选检验项
→ 人工审核修改
→ 自动编号和基础气泡
→ 人工拖动调整
→ 带气泡 PDF
→ 固定 SIP Excel
