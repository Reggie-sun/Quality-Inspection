# Generic Agent Rules Bootstrap Design

**Status:** Approved by user; implementation complete

**Date:** 2026-07-21

**Target:** `/home/reggie/vscode_folder/Quality_Inspection`

**Source evidence:** `/home/reggie/vscode_folder/Enterprise-grade_RAG/AGENTS.md`, `.agent/`, and `.ai-native/`

## Problem Statement

`Enterprise-grade_RAG` 已经形成较完整的 coding-agent workflow、分层规则、单一 Owner 约束和 AI-native 治理经验，但其中混合了大量 RAG、retrieval、Portal、sample governance、远端 runtime 与历史执行产物。直接复制到 `Quality_Inspection` 会把新仓库绑定到错误的业务模型，并留下不存在的命令、路径和验证入口。

本设计获批且 Task 1 baseline 执行时，`Quality_Inspection` 是空目录，不是 Git 仓库，也没有确定的语言栈、测试框架、目录结构或运行时。因此本阶段不能建立文件级机器分类、可执行 harness、AI-native scheduler 或项目专属验证命令。

实施期间，并发外部工作后来初始化了独立 Git 仓库并加入一个与本任务无关的 commit。该 drift 不追溯改变 bootstrap 决策：本任务不执行 `git init`、stage 或 commit，也不把 Git 的出现解释为应用技术栈、测试框架或 AI-native runtime 已存在。任何 target-specific Git workflow 仍需后续独立 spec。

本设计只沉淀可跨项目复用的规则原则，并显式声明哪些自动化尚未启用。目标是让后续 coding agent 在仓库初始化阶段获得清晰、保守、不会误执行的工作合同。

## Decision

采用两阶段策略：

1. 当前阶段只建立五个静态规则文件，形成可独立理解的 bootstrap contract。
2. 等目标仓库具备真实代码、Git、测试框架和验证命令后，再单独设计并启用 harness 与 AI-native runtime。

当前阶段不复制任何可运行控制面的半成品。特别是，不迁移 `.ai-native/config.yaml`、schemas、eval cases 或 component registry。

## Goals

- 建立薄 `AGENTS.md`，只负责入口、优先级、硬边界和完成合同。
- 建立唯一的 workflow lane Owner，避免多个文件重复定义 Fast Gate。
- 沉淀最小改动、root-cause-first、验证优先、Git 安全和 delegation 边界。
- 沉淀单一 active Owner、禁止静默语义覆盖、旧路径退役和 bridge/shadow 生命周期规则。
- 明确 AI-native automation 当前未启用，以及未来启用必须同时满足的完整条件。
- 保证所有规则不依赖 `Enterprise-grade_RAG` 的业务、目录、命令或运行环境。

## Non-Goals

- 不定义 Quality Inspection 的业务领域模型、API、数据结构、权限模型或部署拓扑。
- 不复制 retrieval、ingestion、citation、Portal、sample governance 或 RAGFlow 规则。
- 不迁移 `.agent/specs/`、`.agent/runs/`、`.agent/context/`、`.agent/skills/` 或 `.agent/commands/`。
- 不创建 `.agent/harness/policy.yaml`、harness runner、Make targets 或测试命令。
- 不迁移 `.ai-native/reports/`、`.ai-native/runtime/` 或生成式 component registry。
- 不初始化 Git，不创建 commit，不引入应用代码或依赖。
- 不把未来 AI-native runtime 作为本次 implementation plan 的隐藏第二阶段。

## Target Structure

```text
Quality_Inspection/
├── AGENTS.md
├── .agent/
│   └── rules/
│       ├── coding-rules.md
│       ├── workflow-lanes.md
│       └── ownership-convergence.md
└── .ai-native/
    └── README.md
```

设计 spec 位于 `docs/superpowers/specs/`，是 planning artifact，不属于上述运行时规则树。

## Rule Ownership

| Decision dimension | Single Owner | Allowed summary elsewhere |
| --- | --- | --- |
| 规则优先级、启动入口、硬边界、完成合同 | `AGENTS.md` | 下位文件只引用，不重定义 |
| Fast Gate、Lite/Standard/Heavy、planning/review 条件、verification evidence selection | `.agent/rules/workflow-lanes.md` | `AGENTS.md` 只提供入口链接和 Veto Gate |
| 日常读取、编辑、debug evidence、已选验证执行、Git、delegation dispatch execution | `.agent/rules/coding-rules.md` | delegation eligibility 与 completion reporting 仍由 `AGENTS.md` 拥有 |
| control-plane 角色、单一 Owner、旧路径退役 | `.agent/rules/ownership-convergence.md` | 其他文件不得建立第二套角色模型 |
| AI-native activation state | `.ai-native/README.md` | 其他文件只声明当前未启用 |

任何 implementation 若在两个文件中重复完整 Fast Gate、lane 表或 Owner 定义，视为 design failure，而不是“方便阅读”。

## Component Design

### `AGENTS.md`

保持薄入口合同，包含：

- 规则层优先级和职责分工。
- 启动顺序：先读 `AGENTS.md`，再读 `coding-rules.md`，需要 lane 判断时读 `workflow-lanes.md`。
- 高自治执行原则与需要停下来的边界。
- 现有未提交改动保护、破坏性操作保护和最小 scope。
- 文档、代码与行为变更的最低验证义务。
- 最终报告固定回答：改了什么、验证了什么、风险是什么。
- Bootstrap state：在 Git、语言栈、测试框架或运行入口不存在时，不得发明命令或声称验证已运行。

`AGENTS.md` 不包含具体 lane 表、文件分类枚举、业务模块列表或 AI-native runtime 配置。

### `.agent/rules/workflow-lanes.md`

这是 lane 判断的唯一 Owner，定义：

- `Lite`：不命中更高 lane，且为一到三个相关文件、单模块、低风险。
- `Standard`：未命中 Heavy，但存在跨模块/非局部多文件耦合、control-plane/workflow truth、shared non-runtime config，或需要 integration/smoke。
- `Heavy`：稳定 API/schema、认证授权、数据迁移、runtime entry/config、跨模块 data-integrity/security boundary 或不可逆/破坏性操作。
- 统一主线：`spec -> plan -> implement -> review`。
- bug、error、regression 必须先形成并验证 root-cause hypothesis。
- plan 恢复时只允许一个 selected plan；fresh validation 映射为 `continue / amend / close / replan / blocked`。

该文件不引用 retrieval、RAG、Portal、特定 Make target 或不存在的 harness。

### `.agent/rules/coding-rules.md`

承载高频执行纪律：

- 先读相关实现、测试和调用方，再修改。
- 每一行改动都必须可追溯到用户目标。
- 优先最小、稳定、可验证方案，不新增 speculative abstraction。
- bugfix 使用 root-cause-first，并添加或运行最接近真实失败面的验证。
- 本地 Git 事实使用 shell `git`；只 stage 当前任务文件；不覆盖用户已有改动。
- 只有目标目录确实是 Git 仓库时才执行 commit 规则。
- 是否 delegation 由 `AGENTS.md` 决定；本文件只执行已选 dispatch，并要求完整 role/scope/authority/boundaries/no-nested-delegation/conflict/output/verification contract 与非重叠 writer ownership。
- 无测试框架时明确报告“没有可执行代码测试”，不能虚构通过状态。

该文件不重复 lane 定义，也不引用不存在的 `policy.yaml`。

### `.agent/rules/ownership-convergence.md`

从源仓提炼通用 anti-complexity contract：

- 每个 decision dimension 只能有一个 active `Owner`。
- `Signal Provider / Advisor / Executor / Validator / Veto Gate / Repairer / Owner` 的权限边界必须显式。
- 下游不得重新读取原始输入并静默重算上游已提交语义。
- 替代旧路径时，同一变更必须删除、替换或标记明确的 removal trigger。
- bridge/readthrough 最多保留一个 development cycle；shadow-only 若没有真实 consumer 和 promotion/delete trigger，不得永久存在。
- 单个失败样本只直接产生 regression；全局规则需要机制证据或多个独立变体。
- 测试通过不等于架构通过；最终 review 还要检查 active Owner 数量、fallback、wrapper 和旧路径净变化。

该文件只给通用检查方法和标注格式，不包含 RAG 路径、query/citation 术语或源仓检测命令。

### `.ai-native/README.md`

这是 activation boundary，不是 runtime 配置。必须明确：

- AI-native automation 当前为 `disabled / not installed`。
- 本目录只有状态说明，不能作为 harness、eval、promotion 或 scheduler 已启用的证据。
- 禁止在没有 runner 和 tests 的情况下加入看似可执行的 `config.yaml`。
- 未来启用必须通过独立 spec 和 plan，同时交付完整 runner、目标仓配置、全部实际消费的 schemas、train/holdout evals、生成式 component registry、protected paths、focused tests 和 smoke。
- component registry 必须从目标仓真实路径生成，禁止复制源仓 inventory。

## Rule Resolution Flow

```text
[User request]
      |
      v
[AGENTS.md entry and hard boundaries]
      |
      +--> [coding-rules.md: day-to-day execution]
      |
      +--> [workflow-lanes.md: select Lite/Standard/Heavy]
      |             |
      |             v
      |       [spec -> plan -> implement -> review]
      |
      +--> [ownership-convergence.md: only when decision ownership changes]
      |
      `--> [.ai-native/README.md: confirms automation is not installed]
```

没有 machine policy 或 runtime 自动覆盖这条链路。

## Source Extraction Rules

实现时遵循“重写原则，不复制业务文本”：

1. 从源文件提取通用 invariant。
2. 删除所有项目名、绝对路径、服务名、业务模块、账号、端口、远端环境和历史阶段引用。
3. 删除所有指向未迁移文件或命令的引用。
4. 将重复决策归并到上表指定的唯一 Owner。
5. 为目标仓 bootstrap state 改写 Git、测试和 runtime 规则，使其条件化而不是假设已存在。

## Failure Modes

| Failure | Detection | Required response |
| --- | --- | --- |
| 源仓业务术语残留 | 全量关键词和绝对路径扫描 | 阻塞完成，重写相关段落 |
| 引用未迁移文件或命令 | 相对路径与命令闭环检查 | 删除引用或把依赖纳入新的显式 plan |
| 多文件重复定义 Fast Gate | section/phrase comparison | 保留 `workflow-lanes.md` 唯一 Owner，其他位置改成链接摘要 |
| `.ai-native` 看似已启用但没有 runner | 目录结构和 README 状态检查 | 不允许创建 config/schemas/evals；保持明确 disabled |
| 空仓库规则要求执行不存在的测试或 commit | 命令存在性与 Git 状态检查 | 条件化规则并明确未验证项 |
| 为保持“完整”而复制历史产物 | 目标文件清单检查 | 删除非五文件规则资产 |

## Validation Plan

本次是 docs/control-plane bootstrap，不运行应用代码测试。实现完成后至少执行：

1. 文件清单检查：本任务创建的 runtime rule set 恰好是目标五文件；并发外部文件必须保留并单独报告。
2. 禁止内容扫描：不存在 `Enterprise-grade_RAG` 绝对路径、RAG 专属规则、Portal、sample-governance、远端 runtime 或源仓命令。
3. 悬空引用扫描：不存在对 `.agent/harness/policy.yaml`、`scripts/ai_native/*`、`component-registry.yaml`、Make targets 或其他未创建文件的执行性引用。
4. Markdown 基础检查：无尾随空格、未闭合代码块或无效相对链接。
5. Ownership review：确认 Fast Gate、coding discipline、convergence 和 activation state 分别只有一个 Owner。
6. 独立只读 review：检查规则是否会让新 agent 误判当前仓库能力或执行不存在的命令。

Task 1 baseline 时目标目录不是 Git 仓库。当前并发 Git drift 只允许 read-only status 核对；本任务仍不得 stage 或 commit。验证报告必须区分 baseline 与 current state，不得把本任务文件未提交描述为实现 blocker。

## Acceptance Criteria

- 目标五文件均存在且职责符合 Rule Ownership 表。
- `AGENTS.md` 是薄入口合同，没有展开完整 lane 或 AI-native 配置。
- `workflow-lanes.md` 是唯一 Fast Gate 和 lane Owner。
- `coding-rules.md` 不依赖具体语言栈、测试框架或 Git 已初始化假设。
- `ownership-convergence.md` 保留通用角色与退役约束，不包含 RAG 业务路径。
- `.ai-native/README.md` 明确 automation 未启用且列出完整 activation gate。
- 没有源仓业务语义、绝对路径、凭据、历史执行产物或悬空命令。
- 文档验证和独立 review 均通过。
- 最终报告明确：docs-only，没有运行代码测试；Task 1 baseline 为 non-Git，当前 Git 是并发外部状态，本任务没有 init、stage 或 commit。

## Migration Sequence

1. 写 `AGENTS.md`，确定顶层职责和 bootstrap boundary。
2. 写 `workflow-lanes.md`，建立唯一 lane Owner。
3. 写 `coding-rules.md`，补日常执行、Git 与 delegation 纪律。
4. 写 `ownership-convergence.md`，补 control-plane 收敛规则。
5. 写 `.ai-native/README.md`，封闭未启用自动化的边界。
6. 执行 Validation Plan，修复所有残留或悬空引用。
7. 完成独立只读 review，再提交最终结果给用户。

所有步骤由单 writer 顺序执行。文件职责存在依赖关系，没有值得使用并行 worktree 的独立实现 lane。

## Risks And Mitigations

- **过度通用导致规则不可执行：** 通过明确 bootstrap state、完成合同和 future activation gate 保留可操作性。
- **未来业务规则继续堆进 `AGENTS.md`：** 通过 Rule Ownership 表限制顶层文件职责。
- **后续误把 `.ai-native` README 当已安装平台：** README 使用明确的 `disabled / not installed` 状态并禁止空壳 config。
- **目标仓初始化后规则滞后：** Git、语言栈、测试框架和 runtime 出现时，触发新的 target-specific spec，而不是静默改写本 bootstrap contract。

## Rollback

Task 1 baseline 时目标目录为空且不是 Git 仓库；当前已出现并发外部 Git 状态与无关文件。本任务不自动执行 rollback。若用户以后明确要求回滚，只处理本设计新增且仍可明确归属的五个规则文件，不删除 `.git`、无关 commit、用户后来添加的文件或其他 planning artifact。

## Implementation Handoff

用户批准本 spec 后，下一步只允许使用 `superpowers:writing-plans` 编写逐文件 implementation plan。该 plan 必须列出每个文件的内容边界、禁止引用、验证命令和最终只读 review，不得在写 plan 的同一阶段实现规则文件。
