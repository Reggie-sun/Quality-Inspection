# SIP Confirmation Demo

这套截图用于说明标题栏自动带入、项目 SIP 确认、检验项 SIP 连续处理，以及为什么
技术要求已确认后，`生成正式文件` 仍可能保持禁用。

## Steps

1. 打开 [07-title-block-prefill-demo.png](07-title-block-prefill-demo.png)。新项目会从标题栏自动带入
   `物料编码`、`产品名称`、`图号` 和 `版本号`，并标记为
   `图纸识别，待确认`。图纸没有明确给出的 `材质` 仍需人工填写。
2. 补齐缺失字段并点击 `确认项目 SIP 信息`。自动填写不是自动确认；只有这个按钮会把
   项目级信息保存为正式 SIP。
3. 打开 [05-live-guided-progress.png](05-live-guided-progress.png)。真实工作台顶部显示
   `检验项 SIP 3 / 115`，右侧显示同一进度和 `处理下一条未确认 SIP`。
4. 点击 `处理下一条未确认 SIP`。系统只在界面中选择下一条有效且未确认的检验项；
   [08-live-next-unconfirmed.png](08-live-next-unconfirmed.png) 展示了选中后的审核表单。
5. 在 `SIP 确认字段` 填写检验项目、检验标准、检验方法、关键尺寸、检验角色和页码，
   然后点击 `确认当前检验项 SIP`。保存成功后系统自动进入下一条；保存失败时不跳转。
6. 打开 [06-live-export-blocker.png](06-live-export-blocker.png)。正式文件区会明确显示
   `还需确认 112 条检验项 SIP`，而不是含混地显示“尚未审核”。

旧版流程截图 `01`～`04` 保留用于对照，不代表当前最终文案。

## Final State

终态不是“技术要求已确认 5”，而是：

1. 项目 SIP 信息已经人工确认；
2. 所有有效检验项的 SIP 都已确认；
3. freeze、编号和气泡校验通过；
4. 正式审核完成。

随后系统才能生成带气泡 PDF、SIP Excel 和校验清单。
