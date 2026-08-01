# Field Mapping

| 对比稿字段 | 现有识别字段 / 来源 |
| --- | --- |
| 编号 | 审核后顺序编号 |
| 页码 | `source_page` |
| 类型 | `item_type` |
| 基本尺寸 | `nominal` |
| 公差 | `upper_tolerance` / `lower_tolerance` 的显示值 |
| 上限 / 下限 | `nominal + upper_tolerance` / `nominal + lower_tolerance` |
| 检测值 | 质检人员手工填写 |
| 结果判定 | Excel 公式：检测值为空则空白；上下限缺失则空白；区间内 `OK`，否则 `NG` |

顶部红色说明由已确认技术要求中的未注公差标准投影；本文件及对比稿均为非生产设计验证，不接入正式导出。
