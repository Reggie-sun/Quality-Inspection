# cc-connect Quality Inspection Project Design

## Goal

在现有 `cc-connect` 用户级服务中新增 `quality-inspection` 项目，使飞书消息只启动工作目录为 `/home/reggie/vscode_folder/Quality_Inspection` 的 Codex 会话。

## Scope

- 只追加一个 `[[projects]]` 条目到 `/home/reggie/.cc-connect/config.toml`。
- 只为新项目运行一次 `cc-connect feishu setup --project quality-inspection` 的 QR onboarding。
- 保留现有全局设置、旧项目、旧平台绑定、会话历史与认证数据。

## Configuration

新项目使用独立 key `quality-inspection`。其 agent 为 Codex，工作目录固定为本仓库；沿用当前已部署 Codex 项目的非敏感执行档：`yolo` mode、`gpt-5.6-sol` model、`high` reasoning effort 与共享 `/home/reggie/.codex/agents` profiles。不得复制旧项目的 `append_system_prompt`，避免把旧项目上下文带入本项目。

飞书平台凭据不手写、不读取、不记录在项目文档中，而由官方 onboarding 命令在用户扫码后写入。新飞书机器人是该项目唯一新增入口，不复用已有 bot。

## Data Flow

`Feishu bot -> cc-connect.service -> quality-inspection project -> Codex(work_dir=Quality_Inspection) -> Feishu bot`

服务从 `/home/reggie/.cc-connect` 读取全局配置；项目名将用于会话隔离和显式 `cc-connect send -p quality-inspection` 路由。

## Failure Handling And Rollback

在扫码前，通过首次 daemon restart 让 `cc-connect` 解析新增的无凭据项目块；原始 `config.toml` 不会被 formatter 改写，也不会创建含认证字段的临时副本。若解析或 daemon restart 失败，立即从配置中删除刚追加的完整无凭据项目块，再重启服务并确认旧服务恢复运行。若 QR onboarding 超时或用户取消，保留无平台凭据的项目块仅在用户明确要求重试时继续；本次不触碰旧项目或其凭据。

## Verification

验证分三层：`cc-connect` 对无凭据新增块的启动解析、`cc-connect daemon status` 的 active runtime 校验，以及用户扫码后通过 `/current` 或 `/new` 在新飞书机器人中确认会话归属 `quality-inspection`。不向任意既有会话发送测试消息，避免误投；没有完成扫码前不宣称飞书端到端已通过。

## Out Of Scope

- 变更全局 connection、代理、日志、服务 unit 或其他项目。
- 复用旧飞书/微信凭据或改动其路由。
- 修改仓库生产代码、测试框架或 agent system prompt。
