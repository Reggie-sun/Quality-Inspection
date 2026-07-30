# Project Bug Memory

本文件记录项目内已经确认的回归事实，供后续问题定位时按需检索。

## BUG-20260730-requirement-relation-retirement

- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `backend/app/review/service.py` 的 `Exclude / Merge / Split` command path
- Symptom: 已确认的技术要求 relation 在目标 item 被停用后仍引用 inactive ID，可能在 freeze/export 前静默丢失。
- Previously correct behavior: requirement relation 必须只指向 active item；唯一 target 消失时必须重新进入人工确认。
- Reproduction: 新增 exclude/merge/split focused tests 分别失败于 relation 仍是 `matched_items`、仍指向 `i1`。
- Root cause: `_apply_command()` 只提交 item retirement/replacement，没有把 ID replacement map 同事务应用到 `technical_requirements`。
- Fix: 在 `Exclude / ResolveConfirmation(false) / Merge / Split` 的同一 command
  transaction 内同时应用 `matched_candidate_ids` 与 `generated_candidate_id` replacement
  map；无剩余 target 或 singular global relation 被拆成多个 target 时，把 requirement
  重开为 `unresolved` 并恢复 source coverage confirmation；其他 replacement 只重连
  active item 并重新投影 SIP suggestion。共享同一 observation 的 coverage gate 按全部
  requirements 重算；global merge 只接受 `global_requirement / balloon_required=false`
  source，并在所有 review command 完成后统一校验 active global item 与 global relation
  target，避免 `Edit / Add / SetBalloonRequired` 等旁路破坏无气泡合同。
- Regression check: `backend/tests/integration/test_review_operations.py`

## BUG-20260730-standalone-requirement-owner-replacement

- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 1
- Surface: `candidate_snapshot_from_inventory()` 与 `backend/app/candidates/technical_requirements.py`
- Symptom: title-block 外的 standalone executable requirement 在旧 classifier 被删除后不再保证生成无气泡技术要求项。
- Previously correct behavior: 同时含 inspection verb 和 verifiable criterion 的 standalone observation 会生成 `general_requirement`。
- Reproduction: 两个 snapshot focused cases 都得到 `technical_requirements == ()`，未进入新 Owner。
- Root cause: Owner replacement 迁移了 entry classification，却没有迁移旧入口的 standalone executable observation 准入与 entry 构造。
- Fix: 将 standalone executable predicate 收敛到 Technical Requirement Rule Owner，
  在编号块重建之后补充未消费 observation 的 standalone entry；已识别 subtype 走既有
  rule，其他可执行行保守生成 `standalone_check / ambiguous` 无气泡全局技术要求。
- Regression check: `backend/tests/e2e/test_offline_automatic_result.py`
