# cc-connect Quality Inspection Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `cc-connect.service` 中新增隔离的 `quality-inspection` Codex + 飞书项目映射。

**Architecture:** 用户级服务继续读取唯一的 `/home/reggie/.cc-connect/config.toml`。仅追加一个项目块；官方 `feishu setup` 负责产生并写入新项目的认证字段。项目会话使用 `quality-inspection` key 路由到本仓库。

**Tech Stack:** `cc-connect v1.4.1`、TOML、systemd user service、Feishu QR onboarding、Codex。

---

### Task 1: Record and validate the additive project configuration

**Files:**
- Modify: `/home/reggie/.cc-connect/config.toml`
- Create: `docs/superpowers/specs/2026-07-21-cc-connect-quality-inspection-design.md`
- Create: `docs/superpowers/plans/2026-07-21-cc-connect-quality-inspection.md`

- [ ] **Step 1: Record pre-change service and configuration shape**

Run: `cc-connect daemon status` and inspect only TOML section/key names.

Expected: the user service is running and the existing project is left untouched.

- [ ] **Step 2: Append the new project block**

Append exactly this credential-free TOML block after the existing project:

```toml
[[projects]]
name = "quality-inspection"

[projects.agent]
type = "codex"

[projects.agent.options]
work_dir = "/home/reggie/vscode_folder/Quality_Inspection"
mode = "yolo"
model = "gpt-5.6-sol"
reasoning_effort = "high"
agent_profiles_dir = "/home/reggie/.codex/agents"
```

- [ ] **Step 3: Validate TOML without rewriting the live configuration**

Run: `cfg_tmp=$(mktemp); cp /home/reggie/.cc-connect/config.toml "$cfg_tmp"; cc-connect config format --config "$cfg_tmp"; rm -f "$cfg_tmp"`

Expected: `cc-connect config format` exits zero; only the disposable temporary file is formatted.

- [ ] **Step 4: Restart and check the active service**

Run: `cc-connect daemon restart && cc-connect daemon status`

Expected: status reports `Running`; no existing project name or platform block is changed.

### Task 2: Bind a dedicated Feishu bot to the new project

**Files:**
- Modify: `/home/reggie/.cc-connect/config.toml` (only the new project's Feishu credentials written by the official CLI)

- [ ] **Step 1: Start QR onboarding**

Run: `cc-connect feishu setup --project quality-inspection --qr-image /home/reggie/.cc-connect/feishu-quality-inspection-qr.png --timeout 600`

Expected: a QR code is created for a new Feishu bot and the command waits for the user to scan it; do not print the resulting credentials.

- [ ] **Step 2: Confirm the service has reloaded the new binding**

Run: `cc-connect daemon restart && cc-connect daemon status`

Expected: the service is running and logs contain a platform-started event for `project=quality-inspection` without credential values.

- [ ] **Step 3: Verify project routing from the new bot**

In the new Feishu conversation, send `/new quality-inspection-smoke`, then `/current`.

Expected: the reply identifies a session owned by `quality-inspection`; no message is sent to an existing project's session.

### Task 3: Roll back only if a configuration or startup failure occurs

**Files:**
- Modify: `/home/reggie/.cc-connect/config.toml` (remove only the exact `quality-inspection` block and its newly created Feishu platform block)

- [ ] **Step 1: Remove the failed new project block**

Use `apply_patch` against the exact appended block. Do not alter any pre-existing project, platform, or global setting.

- [ ] **Step 2: Restore service availability**

Run: `cc-connect daemon restart && cc-connect daemon status`

Expected: status reports `Running` with the pre-existing configuration active.
