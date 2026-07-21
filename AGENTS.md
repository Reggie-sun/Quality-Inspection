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
