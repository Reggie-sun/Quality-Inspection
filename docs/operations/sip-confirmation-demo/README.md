# SIP Table Generation Demo

这套教学材料说明当前终态：

```text
审核检验项一次
→ 生成并检查 SIP 表格
→ 只处理异常
→ 异常归零后生成正式文件
```

不再要求用户对每一条检验项重复执行一次“SIP 确认”。系统根据已经审核的 active
检验项生成 SIP 字段；只有无法可靠确定的字段进入异常处理。

## Current Runtime Evidence

以下截图来自 `2026-07-31` 本地真实 workbench，不是 instructional mock：

1. 打开
   [09-live-sip-table-generated.png](09-live-sip-table-generated.png)。
   在 `默认检验角色` 填入 `IPQC`，点击 `生成并检查 SIP 表格`。页面顶部和 SIP
   区域都会显示 `已生成 113 / 异常 2`，而不是“已确认 113 / 115”。
2. 打开
   [10-live-exception-only.png](10-live-exception-only.png)。
   点击 `处理下一条异常` 后，系统只定位到异常行，并明确说明
   `未知检验项类型`。用户只需补全这类无法自动决定的字段，再点击
   `保存当前 SIP 字段`。
   如果之后修改了技术要求匹配关系，受影响的旧行会显示
   `技术要求已变更，请重新生成 SIP 表格`，不会被误算为已完成。
3. 打开
   [11-live-metadata-conflict.png](11-live-metadata-conflict.png)。
   标题栏已有值与图纸识别值不一致时，页面并列显示 `当前值` 和
   `图纸识别值`。点击 `采用识别值` 只更新本地草稿；点击
   `确认项目 SIP 信息` 后才正式保存项目级信息。

本次 runtime smoke 还验证了：

- 生成按钮只发送一个 `generate_sip_table` command；
- command 返回 HTTP `200`；
- 旧的逐项 `已确认 x / y` 文案不存在；
- `采用识别值` 不会提前发送保存请求；
- console error 和异常 HTTP response 均为 `0`。

## Export Boundary

`生成并检查 SIP 表格` 只物化 SIP 字段，不会冻结、编号、生成气泡或导出。

正式文件仍保持 fail-closed：

1. 项目 SIP 信息完整并已保存；
2. SIP 异常为 `0`；
3. 检验项 freeze 完成；
4. 编号与气泡校验通过；
5. ReviewedResult 确认完成。

满足以上条件后，系统才能原子生成带气泡 PDF、SIP Excel 和校验清单。

## Historical Screenshots

`01`～`08` 是旧版“逐项确认 SIP”流程的历史对照，不代表当前产品终态。
