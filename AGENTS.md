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

### 2.1 Context And Owner Preflight

- 每次 plan execution 只能有一个 active implementation plan；父计划只拥有父目标和 task 顺序，companion plan 只拥有当前 Task 的实施步骤。supporting plan、spec、历史 report 和 bug memory 只有在当前 Task 引用尚未解析的 contract、Owner、compatibility 或 evidence 问题时，才读取对应内容。用户明确要求的 required reads，以及上位 rule、skill 或 profile 要求的全文读取不受此限制。
- handoff 或 controller brief 已经完整冻结 scope、Owner、allowed paths、unchanged contract、当前 evidence 和 verification command 时，父线程及 fresh subagent 应以该 brief 为当前执行入口；不得无具体缺口地重复全文读取同一 parent plan、design spec、历史 plan 或 report。发现 brief 缺失时，只补读能关闭该缺口的 authoritative source，并在 report 中记录补读原因。
- `Standard / Heavy` 在第一行写入前，父 agent 必须完成一次 `Owner/File Closure Preflight`：记录 problem boundary、single Owner、old path to remove or replace、unchanged contract、全部 planned create/modify paths，以及 focused verification command。
- `Owner/File Closure Preflight` 必须同时核对相关 schema inventory、generator/checker、manifest/runtime identity、index/HEAD gate 和 old-path retirement；确认 approved allowed paths 覆盖全部真实 Owner，且 working tree、index、HEAD 所需证据在当前 stage/commit 约束下可执行。
- preflight 发现必需 Owner 漏列、no-stage/no-commit 与 verification gate 冲突，或新 schema/runtime file 无法进入 authoritative inventory 时，必须在写入前 amend/replan 或请求用户决定；不得先生成 partial implementation，再把本应在 preflight 发现的文件漏列报告为 blocker。

### 2.2 Worktree Environment Injection

- 所有 Quality_Inspection linked worktree 共用唯一 canonical environment source：`/home/reggie/vscode_folder/Quality_Inspection/.env`。进入任一 worktree session 时必须先验证该文件是当前 uid/gid 拥有的 mode `0600` regular file；不得从 worktree 内的 `.env`、副本、symlink 或其他 fallback 读取同一组环境值。
- shell/tool command 之间不得假设 environment 会持久化。每个需要 repository runtime、Provider credential 或 Harness private binding 的命令，必须在同一 shell process 内先执行 `set -a; . /home/reggie/vscode_folder/Quality_Inspection/.env; set +a`，再执行目标命令；不需要这些值的 read/test/lint/git 命令不得无意义加载 credential。
- Canonical `.env` 只拥有跨 worktree 共享的 private/process values，不拥有 linked-worktree runtime routing。source 后必须在同一 shell 内从当前 approved runtime identity Owner 显式设置并验证该 worktree 的 public target tuple（包括 `COMPOSE_PROJECT_NAME`、`QI_P0_API_BASE`、`QI_P0_FRONTEND_BASE` 及 plan要求的source root）；不得继承 root `.env` 中的 routing value来选择 linked worktree target。tuple 与当前 plan/runtime evidence不一致时必须在任何 compose、Provider或Harness mutation前fail closed。
- 不得复制、移动、生成、stage 或 commit canonical `.env`，不得输出、读取到 agent context、记录或 hash 其中的值。只允许按 exact environment key name 报告 `present/absent`；文件不安全、source 失败或 required key 缺失时必须在 runtime/Provider mutation 前 fail closed。
- Environment injection 只提供 private process values，不等同于 operator attestation、account readiness、cycle authorization、paid execution approval 或 Provider success evidence；这些 gate 仍必须由当前 approved plan 的独立事实关闭。

### 2.3 Linked Worktree Auto-Merge

- 任务在 linked worktree 中执行时，完成全部 approved scope、required verification、required independent review（如适用）并将 scoped changes commit 后，父 agent 必须在同一任务中自动把该 worktree branch 合并到本地 `main`；不得再次请求用户确认，也不得停在只报告 worktree commit 的状态。
- merge 前必须用 shell Git 核对 source branch/commit、local `main`、merge-base、两侧 worktree/index 状态、live-agent writer ownership 和 dirty-file overlap。默认使用 `git merge --ff-only`；若 `main` 已前进但不存在冲突或 ownership 风险，则先在 clean task worktree 合入 current `main`，重跑受影响的 required verification，再 fast-forward `main`。任何 merge conflict、重叠 dirty changes、active writer overlap、缺失 scoped commit 或 required verification/review 未通过都必须 fail closed，并报告 exact blocker。
- merge 后必须证明 task commit 是 local `main` 的 ancestor，记录最终 `main` HEAD，并按 integration delta 运行最小必要的 post-merge check；这些检查未完成时不得报告 merge complete。
- 自动 merge 只授权 local branch integration；不授权 push、remote PR merge、deployment、删除 branch/worktree、清理未提交文件或其他 destructive action。

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

### 4.1 Progress And Completion Reporting

- 用户可见进度只在 task start、material evidence transition（例如 `RED -> GREEN`、review verdict）、scope/Owner decision、真实 blocker 和 completion 等节点汇总；不得逐条播报 routine reads、每个 tool call、每次 wait timeout 或未变化的 `agent_status`。
- 上位通信规则要求长任务定期更新时，使用一条合并状态说明“已完成 / 当前在跑 / 新证据或无变化 / 下一 gate”；没有新证据时不得重复同一提醒。只有用户明确要求更高频进度时才提高频率。
- beat、wave、subagent turn、review round 和 SDD breaker 只是同一 Task 的 checkpoint，不拥有 Task completion。剩余工作仍在 approved scope 和 authority 内时，状态必须保持 `IN_PROGRESS`，并通过受限 corrective task 或下一执行切口继续；不得仅因耗时、上下文窗口、单次 agent 结束或 review/fix 轮数上限标为 `BLOCKED`。
- `DONE` 要求当前 Task 的全部 approved steps 和 required verification 已关闭；focused selector green、局部实现或子代理 `DONE` 不能替代父 Task closure。
- `BLOCKED` 只用于存在无法在 approved scope 内解决的具体 authority、contract、external-state 或 destructive-action 冲突。若继续需要实质 scope expansion 或新授权，必须说明 exact conflict 并请求用户决定；否则不得把可继续执行的 partial work 当成终局 blocker。

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
