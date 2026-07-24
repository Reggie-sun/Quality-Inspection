# PDF Auto-Balloon Global Main Contract Matrix

**Status:** Design baseline

**Introduced version:** `v0.1-design`

**Owner:** 长期稳定系统语义

本文件是 PDF Auto-Balloon 系统唯一的长期稳定契约事实来源。它从 design spec Sections 1～9 提取跨阶段成立的产品、数据和模块行为；Section 10 只用于标注当前 enforcement stage，不反向定义本文件的长期语义。

## Authority And Layer Boundary

固定事实链为：

```text
docs/contracts/MAIN_CONTRACT_MATRIX.md
→ docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md
→ .agent/harness/contracts/p0-contracts.json
→ .agent/harness/contracts/global-contract-bindings.json
→ .agent/harness/policy/
→ .agent/harness/scripts/
→ .agent/harness/runs/<run-id>/
→ receipt.json
```

- 本文件拥有长期稳定系统语义。
- P0 traceability matrix 只拥有当前 P0 的选择、细化、任务和验证映射。
- Harness JSON 是由 P0 Markdown 生成的机器镜像；bindings 是生成索引，二者都不是可独立编辑的业务事实来源。
- Run 目录拥有某次代码、配置和输入的执行证据；receipt 只裁决该 run，不修改任何契约。
- 本文件只记录长期语义与 enforcement stage，不记录执行期编号、测试定位、验收数据身份、具体适配器配置、资产摘要、部署参数或运行入口。

## Compatibility And Breaking-Change Rules

矩阵中的 Compatibility Rule 和 Breaking Change Rule 使用以下完整规则代码：

| Rule | Meaning |
| --- | --- |
| `CR-ID` | ID 不透明、永不复用；新增 ID 是兼容变更，已有 ID 的含义不可漂移。 |
| `CR-ADD` | 只允许可选、可忽略、带版本的增量字段；旧消费者必须能安全处理未知增量。 |
| `CR-STATE` | 新增状态或枚举值前，消费者必须具备 unknown-safe 行为；既有转换和终态含义保持不变。 |
| `CR-ENUM` | 枚举只可在 consumer 能安全处理 unknown value 时增量扩展；已有值不得重命名、复用或改变含义。 |
| `CR-COORD` | 可增加派生坐标或诊断矩阵，但不得改变正式坐标基准、单位、方向和 bbox 语义。 |
| `CR-IMM` | 不可变结果和 artifact 只能创建新版本或新 identity，不能原地重解释。 |
| `CR-OWNER` | Signal Provider、Advisor、validator 和 diagnostic surface 只能提供信号或 veto，不能夺取 final Owner。 |
| `CR-FILE` | 可新增存储实现；对外 `resource_ref`、完整性元数据和发布可见性保持稳定。 |
| `CR-SEC` | 安全规则可向更严格方向兼容演进；secret、公式、路径和隐私防护不可静默放宽。 |
| `CR-EVAL` | 指标、数据集、匹配规则和阈值必须版本化；不同版本不得伪装成可直接比较。 |
| `BR-ID` | 更改 identity 的含义、作用域、唯一性或复用规则属于 breaking，要求 major contract version、迁移和所有 consumer 更新。 |
| `BR-SCHEMA` | 删除、重命名、改变类型/必填性/不变量属于 breaking，要求版本化 schema、迁移和兼容窗口。 |
| `BR-STATE` | 重命名/删除状态、改变 transition 前置条件或 terminal 含义属于 breaking，要求状态迁移和 rollback 设计。 |
| `BR-COORD` | 改变 CropBox、原点、单位、旋转归一、矩阵或 bbox 语义属于 breaking，要求数据迁移及 renderer/UI/export 联合验证。 |
| `BR-OWNER` | 转移 final Owner、允许 Provider/diagnostic surface 提交正式语义属于 breaking，必须先修改本矩阵并退休旧路径。 |
| `BR-IMM` | 原地修改冻结结果、复用 identity 表示新内容或改写历史证据属于禁止性 breaking change。 |
| `BR-SEC` | 放宽 secret、公式注入、路径穿越、未授权资源或数据最小化规则，必须经过显式安全审查和 major version；默认禁止。 |
| `BR-PUBLISH` | 允许部分发布、混用 reviewed result、绕过一致性或改变成功可见性属于 breaking，要求全链路迁移与回滚。 |
| `BR-EVAL` | 改变指标公式、grain、baseline、阈值或盲测治理必须创建新 evaluation version，旧结果不得重算冒充原结论。 |
| `BR-STAGE` | `P1/P2/designed-not-enforced` 升级为 enforced 必须经过新的 approved spec/plan；不得由 P0 task 或测试存在性隐式升级。 |

## Contract Summary

| Domain | Count |
| --- | ---: |
| `SYS` | 7 |
| `PRJ` | 8 |
| `PDF` | 8 |
| `CAND` | 7 |
| `ITEM` | 7 |
| `REV` | 6 |
| `BAL` | 7 |
| `EXP` | 9 |
| `PROV` | 5 |
| `DIAG` | 5 |
| **Total** | **69** |

| Current Enforcement Stage | Count |
| --- | ---: |
| `P0` | 37 |
| `P0-partial` | 24 |
| `P1` | 4 |
| `P2` | 4 |
| `designed-not-enforced` | 0 |

## SYS — Common Conventions

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SYS-001` | SYS | 全局业务 identity、UTC 时间、aggregate version、actor 与 concurrency 语义必须明确；ID 不因显示名、重试或重新渲染而改变，stale mutation 必须拒绝，lease expiry 使用后端权威时钟。 | Identity, version and concurrency contract | All domain models, API, audit, Harness bindings | opaque IDs; UTC timestamps; monotonic aggregate version; expected version; actor reference; lease expiry/conflict state | request correlation、display labels、timing breakdown | `CR-ID`, `CR-STATE`, `CR-ADD` | `BR-ID`, `BR-SCHEMA`, `BR-STATE` | `v0.1-design` | `P0-partial` |
| `SYS-002` | SYS | 大文件只通过受控 `resource_ref` 暴露；正式引用带 hash、size、MIME、created-at，并在完整性校验后才可见。 | FileStorage metadata Owner | API, worker, Provider records, export, diagnostics | `resource_ref`, `sha256`, `size_bytes`, `mime_type`, `created_at`, visibility state | physical path、temporary key、chunk timing | `CR-FILE`, `CR-ADD` | `BR-SCHEMA`, `BR-SEC`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `SYS-003` | SYS | 稳定字段、诊断字段和 final Owner 必须分离；诊断面可扩展但不得替换稳定字段或提交正式语义。 | Contract governance Owner | All services, Provider adapters, validators, Harness | stable/diagnostic classification; final Owner; consumer boundary | trace、raw response、scores、screenshots、temporary artifacts | `CR-OWNER`, `CR-ADD` | `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `SYS-004` | SYS | 错误使用稳定 envelope；`fatal` 表示当前动作无法安全继续，`blocking` 表示不得越过当前 formal gate，`review_required` 可进入人工审核但必须在 reviewed result 前解决，`warning` 必须记录并只可按规则接受，`informational` 不影响 verdict。fatal/blocking 不能 accepted-risk 为正式成功。 | Error contract Owner | Processing, review, balloon, export, UI, Harness policy | `code`, `message`, `severity`, `stage`, `location_ref`, cause category; stage/verdict effect | stack trace、provider body、retry timing | `CR-ENUM`, `CR-ADD` | `BR-SCHEMA`, `BR-STATE`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `SYS-005` | SYS | Secret、Authorization、完整 base64、宿主机路径和未授权原文不得进入稳定 API、日志或正式 manifest；所有外来文本按不可信输入处理。 | Security boundary Owner | Config, Provider, storage, Excel, API, logs | secret absence; safe resource refs; untrusted-text classification | redacted fingerprints、secure local debug reference | `CR-SEC`, `CR-ADD` | `BR-SEC` | `v0.1-design` | `P0` |
| `SYS-006` | SYS | 稳定 payload、manifest、policy 和 receipt schema 必须显式版本化；新增字段不得让旧 consumer 误判成功。 | Schema compatibility Owner | API, persistence, export, Harness | `schema_version`; compatibility window; unknown-field behavior | migration report、schema diff | `CR-ADD`, `CR-STATE` | `BR-SCHEMA`, `BR-STATE` | `v0.1-design` | `P0-partial` |
| `SYS-007` | SYS | 生产身份、角色、权限和职责分离必须由可信身份边界拥有，具体员工名不能替代角色或授权。 | Authorization Owner | API, review, publication, audit | trusted principal; role; permission; separation-of-duty decision | auth trace、policy evaluation detail | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-SEC`, `BR-OWNER`, `BR-STAGE` | `v0.1-design` | `P2` |

## PRJ — Project And Processing

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PRJ-001` | PRJ | `project`、source file、processing run 和 logical task 各有独立 identity 与关系；重试不改变 source identity。 | Project aggregate | Upload, processing, review, export, Harness | `project_id`, `source_file_id`, content hash, run/task IDs, relations | upload timing、queue message ID | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-SCHEMA` | `v0.1-design` | `P0-partial` |
| `PRJ-002` | PRJ | Workflow state 只能由后端在前置条件、版本和 actor 校验后转换；保存、提交、批准、导出、发布是不同语义。 | Project state machine | API, review, worker, export, UI | processing/edit/review/export/publish state; from/to; actor; reason; timestamp | progress percentage、UI step label | `CR-STATE`, `CR-ADD` | `BR-STATE`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `PRJ-003` | PRJ | PostgreSQL 是任务、审核、发布和业务状态的唯一正式 Owner；Redis/Celery 只协调队列、短期进度和执行。 | Persistence boundary Owner | API, worker, recovery, operations | durable state and result refs in PostgreSQL; ephemeral coordination outside | queue depth、worker heartbeat、short progress | `CR-OWNER`, `CR-ADD` | `BR-OWNER`, `BR-STATE` | `v0.1-design` | `P0` |
| `PRJ-004` | PRJ | 稳定 logical task key 和输入 identity 保证重复投递、Worker 重启和有限重试不重复创建正式结果。 | Idempotency Owner | Processing, Provider calls, export | logical task key; input hashes; existing successful result ref | attempt number、backoff、delivery ID | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-IMM`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `PRJ-005` | PRJ | Unsupported input、依赖不可用、无效配置和处理缺陷必须显式区分；任何失败不得静默形成 ready、reviewed 或 published。 | Processing Veto Owner | Processing, review, export, UI, Harness policy | failure category; terminal/nonterminal state; formal-success veto | stack trace、retry suggestion、internal exception class | `CR-STATE`, `CR-OWNER` | `BR-STATE`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `PRJ-006` | PRJ | 能力 preflight 按操作检查必要存储、队列、Provider、模板和渲染资源；失败只阻止依赖该能力的新动作，不阻止读取已有项目。 | Capability Veto Owner | API, processing, export, UI | capability name; availability; checked-at; blocking reason | latency、probe detail、raw health response | `CR-ADD`, `CR-STATE` | `BR-STATE`, `BR-OWNER` | `v0.1-design` | `P0` |
| `PRJ-007` | PRJ | 项目与外部系统保持代码、状态、密钥、存储和发布生命周期隔离；共享能力只能通过明确 API。 | Deployment isolation Owner | Runtime, Provider integration, operations | repository/database/storage/credential boundary; API-only sharing | container/network/resource metrics | `CR-SEC`, `CR-ADD` | `BR-SEC`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `PRJ-008` | PRJ | 生产运行必须具备资源配额、监控、备份、恢复和灾备边界，且不得改变业务事实 Owner。 | Production operations Owner | Runtime, database, storage, release | quota; backup identity; recovery point; deployment revision | infrastructure metrics、alerts、drill logs | `CR-ADD`, `CR-OWNER` | `BR-OWNER`, `BR-STATE`, `BR-STAGE` | `v0.1-design` | `P2` |

## PDF — PDF, Page And Coordinates

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PDF-001` | PDF | Page 使用 source 内 0-based `page_index` 和稳定顺序；所有 observation、source location、balloon 和嵌图可追溯到 page。 | Page identity Owner | Inventory, candidates, review, balloon, export, UI | `source_file_id`, `page_index`, page count/order | rendered page cache key、thumbnail index | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `PDF-002` | PDF | 正式坐标以未旋转 CropBox 左上为原点、PDF point、x 右/y 下、`[x0,y0,x1,y1]` 表示；保存双向矩阵并校验边界和误差。 | Coordinate Owner | Inventory, OCR, candidates, UI, balloon, renderer | CropBox; page rotation; PDF/normalized bbox; PDF/render matrices; error budget | viewport transform、device pixel ratio、debug overlay | `CR-COORD`, `CR-ADD` | `BR-COORD` | `v0.1-design` | `P0` |
| `PDF-003` | PDF | 页面分类为 `vector/hybrid/scanned/ambiguous`，保存证据、置信度和规则版本；人工确认不能被自动结果覆盖。 | Page classification Owner | Processing router, UI, evaluation | detected/confirmed type; evidence; confidence; rule version; confirmer | threshold scores、feature vector | `CR-ENUM`, `CR-IMM` | `BR-SCHEMA`, `BR-STATE`, `BR-EVAL` | `v0.1-design` | `P0-partial` |
| `PDF-004` | PDF | 页面 inventory 以 span/line 原生文本、方向、字体和基础 vector/image/render metadata 为稳定事实；字符级展开是按需派生。 | Native inventory Owner | OCR routing, candidates, diagnostics, evaluation | raw/normalized text; bbox; direction; page object identity; render metadata | character expansion、drawing score、parser trace | `CR-ADD`, `CR-COORD` | `BR-SCHEMA`, `BR-COORD`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `PDF-005` | PDF | OCR 只补充原生缺失、异常、图像或视觉冲突区域；局部与整页 region identity 不同，避免重复进入候选。 | OCR routing Owner | OcrProvider, inventory, coverage | OCR reason; region ID/bbox; source image hash; routing mode | crop padding、routing score、retry trace | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `PDF-006` | PDF | Native 与 OCR observation 不互相覆盖；每个 observation 保留来源、文本、坐标、方向、置信度和 aligned relation。 | Observation Owner | Candidate grouping, coverage, review, diagnostics | observation ID; source type; raw/normalized text; bbox; direction; relation | raw Provider token、alignment score | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `PDF-007` | PDF | Page inventory 保存区域、coverage、来源冲突和异常；低置信度区域不得直接导致工程内容被排除。 | Page inventory Owner | Candidate generation, coverage, UI, diagnostics | region identity/type/state; coverage map; anomaly/source relation | region detector score、temporary crops | `CR-ADD`, `CR-OWNER` | `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `PDF-008` | PDF | 纯扫描、加密和损坏输入必须有显式 support-level routing，不能伪装成 vector/hybrid 成功；正式 scanned 支持仍需独立能力与验收阶段。 | Input routing Owner | Upload, processing, OCR, UI, acceptance | input class; support level; unsupported reason | experimental OCR output、repair attempt | `CR-STATE`, `CR-ADD` | `BR-STATE`, `BR-STAGE` | `v0.1-design` | `P0-partial` |

## CAND — Candidate And Coverage

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CAND-001` | CAND | 候选采用 recall-first seeds，覆盖明确尺寸、公差、孔/直径、螺纹、半径、角度、复合标注、GD&T、粗糙度、焊接和技术要求；单独数字需工程证据。 | Candidate seed Owner | Parser, grouping, coverage, review | seed identity; coarse type; evidence; source observations; confidence | regex match detail、geometry score、parser trace | `CR-ENUM`, `CR-ADD` | `BR-SCHEMA`, `BR-OWNER`, `BR-EVAL` | `v0.1-design` | `P0-partial` |
| `CAND-002` | CAND | 每个工程相关 observation group 恰有一个 primary disposition：candidate、reference context、non-inspection 或 ambiguous；上下文可被多重引用。 | Disposition Owner | Coverage, review, evaluation | group ID; primary disposition; reason/version; context links | advisor alternatives、score distribution | `CR-ENUM`, `CR-OWNER` | `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0` |
| `CAND-003` | CAND | 分组由方向、基线、空间、引线、视图和语义共同决定；quantity 与有序 composite sub-requirements 不得被文本相同规则破坏。 | Grouping Owner | Candidate model, items, review, evaluation | group members/order; quantity; composite boundary; source links | grouping score、candidate alternatives | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-SCHEMA`, `BR-EVAL` | `v0.1-design` | `P0` |
| `CAND-004` | CAND | Vision LLM 只按需复核局部候选并输出受 schema 约束的建议；确定性 validator 决定是否接受建议，模型不得猜测不足上下文。 | Candidate Advisor boundary | Provider adapter, parser, coverage, review | review reason; crop/source refs; prompt/schema/model versions; validated suggestion | raw response、expanded crop、token trace | `CR-OWNER`, `CR-ADD` | `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `CAND-005` | CAND | Coverage Ledger 覆盖所有疑似工程 observation；缺 disposition/source/coordinates 或冲突归属为 blocking，不允许静默丢弃。 | Coverage Owner and Veto Gate | Processing, review, acceptance | entry identity; disposition; source; coordinates; severity; checked status | ledger explanation、coverage heatmap | `CR-ID`, `CR-OWNER` | `BR-ID`, `BR-OWNER`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `CAND-006` | CAND | Ambiguous、review-required 和自动排除项必须可复查、定位和恢复；低置信度不是不可逆排除理由。 | Review-entry Owner | Workbench, review commands, diagnostics | ambiguity/confirmation state; exclusion reason; recoverable relation | ranking score、filter facets | `CR-STATE`, `CR-ADD` | `BR-STATE`, `BR-OWNER` | `v0.1-design` | `P0` |
| `CAND-007` | CAND | Candidate 修改、merge、split、supersede 和疑似跨视图重复保留 identity/lineage；文本相同不能自动合并。 | Candidate lineage Owner | Review, items, evaluation, diagnostics | candidate/version IDs; parent relations; superseded state; duplicate suggestion | similarity score、merge recommendation | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-IMM`, `BR-STAGE` | `v0.1-design` | `P0-partial` |

## ITEM — Inspection Item

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ITEM-001` | ITEM | 正式 inspection item 有独立 identity、project/review version、type、scope、source relations 和 `balloon_required`；多来源由 relation 存储。 | Inspection item Owner | Review, balloon, export, evaluation | item ID; item type; scope; source IDs; primary source relation; version | UI row index、source preview label | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-SCHEMA` | `v0.1-design` | `P0-partial` |
| `ITEM-002` | ITEM | `raw_text` 与 typed `structured_payload` 同时保存；数值用 Decimal 并保留原串，单位和字段值不得凭常识补造。 | Item semantic Owner | Parser, review, export, evaluation | raw/normalized text; Decimal values; original value strings; unit/source context | normalized display text、parse confidence | `CR-ADD`, `CR-IMM` | `BR-SCHEMA`, `BR-IMM`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `ITEM-003` | ITEM | Typed payload 按 item type 校验；未知直径特征保持 `unknown` 并确认，复杂语义不足时保留原文、坐标、粗类和确认要求。 | Typed item schema Owner | Parser, review, export | type discriminator; allowed core fields; feature kind; confirmation flag | LLM explanation、parser alternatives | `CR-ENUM`, `CR-ADD` | `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `ITEM-004` | ITEM | Composite 使用独立有序 sub-requirement 作为权威存储；公共 quantity 只表示共享数量且不在 merge 时自动累加。 | Composite item Owner | Grouping, review, export, evaluation | sub-requirement ID/order; quantity; quantity scope; composite flag | flattened API projection、display rows | `CR-ID`, `CR-ADD` | `BR-ID`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `ITEM-005` | ITEM | 建议值与 confirmed business fields 分离；正式重点属性、方法、角色和颜色只能来自规则或人工确认，导出只读 confirmed 值。 | Business-field confirmation Owner | Review, export, evaluation | suggested/confirmed values; confirmation state; actor; rule/source/version | recommendation alternatives、confidence、reason | `CR-IMM`, `CR-ADD` | `BR-IMM`, `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0-partial` |
| `ITEM-006` | ITEM | Local feature 与 global requirement、气泡默认、重复特征、技术要求和非检验元数据按版本化业务规则区分，人工拥有最终确认。 | Business-rule Owner | Candidate disposition, review, balloon, export | rule ID/version; scope; balloon default; confirmed override | rule score、matched clauses | `CR-ENUM`, `CR-OWNER` | `BR-OWNER`, `BR-SCHEMA`, `BR-EVAL` | `v0.1-design` | `P0-partial` |
| `ITEM-007` | ITEM | 完整复杂工程语义、标准公差库、可配置质量规则和历史推荐必须由版本化规则/知识源实现，不能由模型直接成为正式事实。 | Engineering semantics Owner | Parser, review, business rules, evaluation | semantic schema/version; standard source; rule provenance | model explanation、knowledge retrieval trace | `CR-OWNER`, `CR-EVAL` | `BR-OWNER`, `BR-SCHEMA`, `BR-STAGE` | `v0.1-design` | `P2` |

## REV — Review And Result Layers

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `REV-001` | REV | `raw_automatic_result`、`review_working_copy`、`review_submission_snapshot`、`reviewed_result` 和 published artifacts 是不同 identity/layer，不得互相覆盖。 | Result-layer Owner | Processing, review, export, evaluation | layer identity; project/source relation; schema/version; predecessor relation | UI projection、diff cache | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-IMM`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `REV-002` | REV | Raw automatic result 冻结自动能力证据且不可变；人工编辑不使其失效，也不能用 reviewed result 冒充自动能力。 | Automatic-result Owner | Review, evaluation, diagnostics | raw result ID; inputs; candidates; coverage; Provider refs; created-at | evaluation cache、debug annotations | `CR-IMM`, `CR-EVAL` | `BR-IMM`, `BR-EVAL` | `v0.1-design` | `P0` |
| `REV-003` | REV | Working copy 是独立、versioned、可保存的编辑 aggregate；actor、single-editor/lease 和 optimistic version 保护并发，Save 不等于确认。 | Review-working-copy Owner | API, UI, audit, freeze | working-copy ID/version; lock/lease; actor; saved-at; edit state | draft autosave timing、presence indicator | `CR-ID`, `CR-STATE` | `BR-ID`, `BR-STATE`, `BR-OWNER` | `v0.1-design` | `P0` |
| `REV-004` | REV | Keep/exclude/edit/add/merge/split/confirmation/source/balloon-required 等命令保留 operation summary、provenance 和 lineage，不物理改写原始证据；source-only 决策必须在同一 working-copy transaction 中原子提交 coverage disposition 与 item transition。 | Review-command Owner | Working copy, audit, evaluation, UI | command; target IDs; before/after version; actor; timestamp; relations | click telemetry、UI undo stack | `CR-ADD`, `CR-IMM` | `BR-IMM`, `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0-partial` |
| `REV-005` | REV | 提交审核时生成不可变 `review_submission_snapshot`；提交、退回、批准和职责分离是独立状态与动作。 | Review-submission Owner | Reviewer UI, audit, approval, evaluation | submission ID/version; submitter; submitted-at; review decision/reason | notification trace、review timing | `CR-ID`, `CR-STATE`, `CR-IMM` | `BR-ID`, `BR-STATE`, `BR-IMM`, `BR-STAGE` | `v0.1-design` | `P1` |
| `REV-006` | REV | 所有 confirmation、item-set 和 balloon formal blockers 解决后，Confirm 原子创建 immutable reviewed result；后续修改必须创建新 revision。 | Reviewed-result Owner | Balloon, export, evaluation, publication | reviewed result ID; frozen items/balloons; input versions; confirmer; created-at | confirmation dialog state、freeze timing | `CR-IMM`, `CR-OWNER` | `BR-IMM`, `BR-STATE`, `BR-OWNER` | `v0.1-design` | `P0` |

## BAL — Balloon

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `BAL-001` | BAL | Balloon 通过 inspection item 和 source location 关联正式语义；图表选择使用同一 IDs，删除 balloon 不删除 item。 | Balloon aggregate Owner | Review, UI, renderer, export | balloon ID; item ID; source location ID; active/deleted state | UI selection state、hover target | `CR-ID`, `CR-OWNER` | `BR-ID`, `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `BAL-002` | BAL | Suggested numbering 与 formal numbering 分离；影响 item 集合、source 或 `balloon_required` 的编辑只标记 stale，不静默重排正式编号。 | Numbering Owner | Working copy, balloon service, UI, export | suggested/formal number; stale state; ordering key; start number | numbering preview、sort explanation | `CR-STATE`, `CR-IMM` | `BR-STATE`, `BR-IMM`, `BR-OWNER` | `v0.1-design` | `P0` |
| `BAL-003` | BAL | Formal number 在 item 集合冻结后生成，项目内唯一、连续、按稳定顺序；global requirement 无气泡且不占编号。 | Formal-number Owner | Reviewed result, renderer, Excel, validator | formal number; uniqueness scope; contiguous sequence; stable sort inputs | alternative start/sort preview | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-IMM`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `BAL-004` | BAL | Placement 使用确定性有限候选和 Veto 条件；无合法位置返回 `manual_required`、best attempt 和原因，而不是伪造成功。 | Placement Owner | Balloon service, UI, validator | placement state; center; reason; collision class; determinism version | collision score、candidate positions、heatmap | `CR-STATE`, `CR-ADD` | `BR-STATE`, `BR-OWNER`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `BAL-005` | BAL | `anchor_bbox_pdf`、`leader_target_pdf`、primary source 和 `balloon_center_pdf` 语义分离，正式几何使用 PDF 坐标。 | Balloon-geometry Owner | UI, validator, renderer, export | anchor bbox; leader target; center; source; page index | viewport pixels、drag trail、snap score | `CR-COORD`, `CR-ADD` | `BR-COORD`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `BAL-006` | BAL | Move/delete/rebuild/reassociate/reorder/renumber 等命令在后端事务校验 item、source、page 和 number invariants；严重几何错误不可 accepted-risk。 | Balloon-command Owner | API, UI, audit, reviewed freeze | command/version/actor; active relation; numbering validity; blocker state | undo stack、interaction telemetry | `CR-STATE`, `CR-OWNER` | `BR-STATE`, `BR-OWNER`, `BR-PUBLISH` | `v0.1-design` | `P0-partial` |
| `BAL-007` | BAL | Frontend overlay 只负责交互；正式 ballooned PDF 由后端从冻结结果和 PDF 坐标绘制，并记录受控字体与 renderer identity。 | Formal-balloon-render Owner | UI, PDF renderer, export, manifest | reviewed result ref; font identity/hash; renderer version; PDF geometry | SVG preview、canvas cache、render timing | `CR-OWNER`, `CR-IMM` | `BR-OWNER`, `BR-COORD`, `BR-PUBLISH` | `v0.1-design` | `P0` |

## EXP — Export And Publication

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `EXP-001` | EXP | 正式 Excel 只使用受控 template registration，登记 template identity/version/hash、mapping version、sheet、capacity、固定区和签核区；超容量阻止导出。 | Template registry Owner | Excel executor, preflight, validator, manifest | template/mapping identity; hash; sheet; capacity; protected ranges | workbook inspection report、cell style diff | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-IMM`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `EXP-002` | EXP | SIP mapping 以 logical detail 为单位覆盖稳定业务字段；普通项、composite 和无气泡 global requirement 均有明确行/序号语义。 | SIP mapping Owner | Reviewed items, Excel executor, validator | fixed field mapping; logical detail count; physical row count; blank-number rule | cell address trace、rendered preview | `CR-ADD`, `CR-IMM` | `BR-SCHEMA`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `EXP-003` | EXP | PDF/OCR/LLM/user 文本不得形成公式；文件名与 sheet name 防路径穿越、非法字符、长度和重名，只有登记模板公式受信。 | Export security Owner | Excel executor, naming, validator, download | text cell type; trusted formula origin; safe filename/sheet name | sanitized-name explanation、rejected input sample | `CR-SEC` | `BR-SEC`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `EXP-004` | EXP | Formal ballooned PDF 是高精度权威文件；Excel 只嵌入由该 PDF 按 source page order 后端渲染的全部页面图像。 | PDF-and-image export Owner | Renderer, Excel executor, validator, user download | source/reviewed refs; page count/order; render parameters; image count | raster cache、compression stats、thumbnail | `CR-IMM`, `CR-COORD` | `BR-IMM`, `BR-COORD`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `EXP-005` | EXP | Ballooned PDF、SIP Excel 和 manifest 必须引用同一 immutable `reviewed_result_id` 及一致输入版本。 | Cross-artifact identity Owner | All export executors, validator, download, Harness | reviewed result ID; input/template/renderer versions; artifact relations | executor timing、staging path | `CR-ID`, `CR-IMM` | `BR-ID`, `BR-IMM`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `EXP-006` | EXP | 三产物在独立 staging 全部生成并验证后才一次性可见；任一失败不更新成功/发布指针，普通下载不暴露部分产物。 | Export orchestrator Owner | Executors, validators, database, download API | export status; staging/published refs; success pointer; error relation | partial files、orphan report、executor logs | `CR-IMM`, `CR-OWNER` | `BR-OWNER`, `BR-IMM`, `BR-PUBLISH` | `v0.1-design` | `P0` |
| `EXP-007` | EXP | 正式导出校验 item/logical detail/balloon/page/image/number/confirmed value 一致性、workbook 可打开编辑、PDF 页数不变；blocking 为零。 | Export consistency Veto Gate | Orchestrator, download, Harness | counts; number sequence; page/image parity; reopen/edit verdict; blocker count | validator details、cell/page diff | `CR-ADD`, `CR-OWNER` | `BR-OWNER`, `BR-PUBLISH`, `BR-SCHEMA` | `v0.1-design` | `P0` |
| `EXP-008` | EXP | Manifest 和 export identity 保存输入、reviewed result、template/mapping/font/renderer 版本与 hash、artifact digest 和 counts；相同正式输入具备幂等语义。 | Export manifest and identity Owner | Orchestrator, validators, download, audit, Harness | manifest schema; dependency identities/hashes; artifact digests; counts; export key | build host、duration、compression detail | `CR-ID`, `CR-ADD`, `CR-IMM` | `BR-ID`, `BR-SCHEMA`, `BR-IMM`, `BR-PUBLISH` | `v0.1-design` | `P0-partial` |
| `EXP-009` | EXP | 多模板、正式 revision、validated/published pointer、rollback 和发布历史由独立治理层拥有，不能通过替换文件模拟。 | Publication-governance Owner | Quality admin, export, release, audit | template family/version; revision; export run; publish/rollback pointer; actor | approval workflow trace、release dashboard | `CR-ID`, `CR-STATE`, `CR-IMM` | `BR-ID`, `BR-STATE`, `BR-IMM`, `BR-STAGE` | `v0.1-design` | `P2` |

## PROV — Provider Boundaries

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PROV-001` | PROV | 业务代码只依赖 `OcrProvider` 和 `VisionLlmProvider` 稳定 port；具体厂商、模型、SDK、endpoint 和参数是可替换配置。 | Provider-port Owner | Processing, OCR routing, candidate advisor, tests | normalized request/result contracts; capability; adapter identity | SDK request/response、endpoint timing | `CR-ADD`, `CR-OWNER` | `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0` |
| `PROV-002` | PROV | OCR 是 Signal Provider，Vision LLM 是 Advisor；二者不能提交 primary disposition、review state、formal number、geometry 或 export content。 | Provider trust-boundary Owner | Candidate, review, balloon, export | provider role; normalized observations/suggestions; validation status | raw alternatives、reasoning-like explanation | `CR-OWNER` | `BR-OWNER` | `v0.1-design` | `P0` |
| `PROV-003` | PROV | 每次 Provider 结果关联 adapter/model/prompt/schema/parameter version、request ID 和安全 request/response refs，业务 schema 不依赖 SDK 类型。 | Provider-call metadata Owner | Persistence, diagnostics, evaluation, Harness | provider/adapter/model/prompt/schema versions; request ID; resource refs | raw body、SDK class、transport headers | `CR-ADD`, `CR-FILE` | `BR-SCHEMA`, `BR-OWNER` | `v0.1-design` | `P0` |
| `PROV-004` | PROV | Credentials 只在服务端 secret boundary；调用使用最小必要 crop，不发送无关标题栏、签名和物料信息，日志与 manifest 保持脱敏。 | Provider privacy and secret Owner | Config, adapters, storage, logs, manifest | credential absence; crop bbox/hash; redacted refs; data-minimization decision | secure local raw response、redaction trace | `CR-SEC` | `BR-SEC` | `v0.1-design` | `P0` |
| `PROV-005` | PROV | Provider request key、成功复用、调用上限、有限重试、耗时/用量/成本统计均版本化；UI 编辑和重新导出不得触发无关调用。 | Provider-call policy Owner | Processing, cache, telemetry, Harness policy | request key inputs; reuse state; retry/budget limits; usage/cost summary | token detail、pricing calculation、backoff trace | `CR-ID`, `CR-EVAL`, `CR-ADD` | `BR-ID`, `BR-EVAL`, `BR-STAGE` | `v0.1-design` | `P0-partial` |

## DIAG — Diagnostic Surfaces And Evaluation

| Contract ID | Domain | Stable Contract | Owner | Consumers | Stable Fields or States | Diagnostic Surface | Compatibility Rule | Breaking Change Rule | Introduced Version | Current Enforcement Stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DIAG-001` | DIAG | Provider raw response、局部截图、collision score、parser trace、临时 artifact、耗时和成本明细属于可扩展诊断面；不得替代稳定字段或 final Owner。 | Diagnostic-surface Owner | Debug tools, offline reports, support | diagnostic type; resource ref; producer/version; relation to stable entity | raw body、crop、score vectors、temporary path | `CR-ADD`, `CR-OWNER` | `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0-partial` |
| `DIAG-002` | DIAG | 长期 artifact/processing stage 模型保留 immutable attempts、current pointer、依赖失效和 retention class；重试不覆盖历史 attempt。 | Artifact-lifecycle Owner | Processing, export, diagnostics, cleanup | artifact/stage-run ID; status; attempt; current pointer; dependency; retention | orphan report、cleanup queue、attempt logs | `CR-ID`, `CR-IMM`, `CR-STATE` | `BR-ID`, `BR-IMM`, `BR-STATE`, `BR-STAGE` | `v0.1-design` | `P1` |
| `DIAG-003` | DIAG | 稳定可观察面只暴露当前阶段、page outcome、severity counts、定位入口和 Provider 调用摘要；详细 trace 可扩展但不能决定业务成功。 | Observability contract Owner | UI, API, operations, Harness reports | stage; page outcome; severity counts; location ref; call summary | trace browser、dependency graph、cost drilldown | `CR-ADD`, `CR-OWNER` | `BR-OWNER`, `BR-SCHEMA` | `v0.1-design` | `P0-partial` |
| `DIAG-004` | DIAG | 自动能力、人工效率和正式交付是三个独立 evaluation layer；指标公式、grain、匹配规则和 raw-to-reviewed diff 必须版本化。 | Evaluation Owner | QA, quality Owner, baselines, reporting | evaluation version; metric definitions; grain; raw/reviewed identities; results | confusion cases、per-field breakdown、timing detail | `CR-EVAL`, `CR-IMM` | `BR-EVAL`, `BR-STAGE` | `v0.1-design` | `P1` |
| `DIAG-005` | DIAG | 数据集分为开发、固定回归和不可见盲测；只有质量确认标准答案可计分，threshold freeze 后不得因盲测结果降低门槛。 | Dataset and threshold governance Owner | QA, evaluation, release, quality Owner | dataset identity/class; answer approval; threshold-set version; freeze state | sample notes、coverage heatmap、candidate pool | `CR-EVAL`, `CR-IMM` | `BR-EVAL`, `BR-STAGE` | `v0.1-design` | `P1` |

## Global Self-Check Contract

- Contract IDs 必须唯一且只使用登记 domain。
- 每行必须有 Owner、Consumers、Stable Fields or States、Diagnostic Surface、Compatibility Rule、Breaking Change Rule、Introduced Version 和 Current Enforcement Stage。
- `P1/P2` 行存在只表示长期契约已设计，不授权七天 P0 task、selector 或 Harness acceptance。
- 修改本文件后，P0 traceability 只能重新选择或映射；不得让生成 JSON 反向覆盖本文件。
