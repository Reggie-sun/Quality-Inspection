# Project Bug Memory

This file is the repository-local history for user-reported bugs and confirmed regressions. Read it before debugging; update matching entries instead of duplicating them.

## BUG-20260730-review-fields-relocked

- Status: Resolved
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 2+
- Surface: `frontend/src/components/review/ReviewPanel.tsx`, structured inspection fields and edit controls
- Symptom: diameter, depth, feature type, and through fields render gray and appear impossible to edit; the explicit modify entry has repeatedly disappeared or become an effective hard gate
- Previously correct behavior: structured inspection fields are directly editable, while the modify button remains available and freeze/global disabled state still locks editing
- Reproduction: persisted project item 64 showed all four fields locked until the modify action; direct field focus did not enter edit mode before the fix
- Root cause: commit `45e04d3` restored `readonly`/`disabled` conditions tied to `isEditingSelected`, reintroducing the mandatory edit gate that the earlier direct-editing fix had removed
- Fix: commit `603702b` keeps text and select fields enabled unless the panel is actually disabled, and field focus enters the existing edit state without changing save/cancel/freeze ownership
- Regression check: `ReviewPanel.test.tsx` test `直径尺寸字段支持修改按钮和直接点击两种编辑入口` asserts both inputs lack `readonly` and both selects lack `disabled` before any modify-button click, then covers explicit-button and direct-focus entry
- Runtime proof: `npm test -- --run` passed 205/205; `npm run build` passed; Chrome smoke on persisted item 64 confirmed white editable fields, focus-to-edit, cancel rollback, and no page-console error/warn
- Change: `603702b`
