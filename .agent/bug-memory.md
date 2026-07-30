# Project Bug Memory

本文件记录项目内用户报告的 bug 和已经确认的回归。调试前先阅读；重复问题更新原记录，不要重复创建。

## BUG-20260730-review-fields-relocked

- Status: 已解决
- First reported: 2026-07-30
- Last reported: 2026-07-30
- Recurrence: 至少 2 次
- Surface: `frontend/src/components/review/ReviewPanel.tsx`，结构化检验字段和编辑控件
- Symptom: 直径、深度、特征类型和通孔字段显示为灰色，看起来无法修改；明确的修改入口曾多次消失或再次成为强制门槛
- Previously correct behavior: 结构化检验字段可直接编辑，同时保留修改按钮；只有 freeze 或全局 disabled 状态才锁定编辑
- Reproduction: 已保存项目中的检验项 64 在点击修改操作前四个字段全部被锁定；修复前直接聚焦字段不会进入编辑态
- Root cause: commit `45e04d3` 恢复了由 `isEditingSelected` 控制的 `readonly`/`disabled` 条件，重新引入了早期直接编辑修复已经移除的强制编辑门槛
- Fix: commit `603702b` 让 text 和 select 字段仅在 panel 实际 disabled 时禁用，并让字段 focus 进入现有编辑态，不改变 save/cancel/freeze 的 Owner
- Regression check: `ReviewPanel.test.tsx` 中的测试 `直径尺寸字段支持修改按钮和直接点击两种编辑入口` 会在点击修改按钮前断言两个 input 不含 `readonly`、两个 select 不含 `disabled`，并覆盖按钮入口和直接 focus 入口
- Runtime proof: `npm test -- --run` 通过 205/205；`npm run build` 通过；在已保存检验项 64 上执行 Chrome smoke，确认字段为白色且可编辑、focus 后进入编辑态、取消后回滚，并且 page console 无 error/warn
- Change: `603702b`
