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
