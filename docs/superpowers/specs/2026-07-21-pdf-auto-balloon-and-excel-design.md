# PDF Auto-Balloon and SIP Excel Design

**Status:** Draft for user review

**Date:** 2026-07-21

**Repository:** `Quality_Inspection`

**Delivery target:** Seven-day internal-trial vertical-slice MVP

## Normative Scope Rule

本设计文档中的 Section 1～9 描述长期设计契约，包括稳定的数据语义、模块责任和生产化边界。它们用于避免P0实现破坏长期方向，但不等于七天内必须完整实现。

七天实际实施范围只由 **Section 10: Revised Delivery Scope** 中的P0清单决定。后续 `writing-plans` 不得因为长期Schema中出现某个实体，就自动把对应的完整后台、UI、版本治理、审计、发布平台或生产基础设施加入七天计划。

七天P0的硬验收对象仅为当前4份真实工程PDF。新增PDF、完整回归集、准确率门槛和正式盲测均不阻塞第7天交付。

## Context and Problem Definition

### 1.1 Actual Goal

输入是没有预制检验气泡的原始机械工程图PDF。系统需要识别原图中的工程标注，形成候选检验项，由人工审核后生成正式气泡、检验表格、带气泡PDF和固定SIP Excel。

本项目不是“识别图纸上已有气泡编号”的OCR工具。气泡由本系统根据检验项审核结果新生成。

目标闭环：

```text
上传原始工程PDF
→ 原生对象解析及必要OCR
→ 自动候选检验项
→ 人工审核修改
→ 自动编号和基础气泡
→ 人工拖动调整
→ 带气泡PDF
→ 固定SIP Excel
```

### 1.2 Repository State at Discovery

调查开始时，`/home/reggie/vscode_folder/Quality_Inspection` 是空目录，不是Git仓库，没有前端、后端、数据库、任务机制、测试、部署或提交历史。因此本设计按全新项目处理，不假设已有业务代码可以复用。

项目使用同一Linux主机上的现有基础资源，但新系统保持独立代码仓库、部署单元、状态数据和发布生命周期。与现有Enterprise-grade RAG/RAGFlow之间只能通过明确API复用无状态能力，不能跨库读取其业务状态。

### 1.3 Examined PDF Samples

实际检查了4份由SOLIDWORKS 2016 SP5.0生成的PDF。当前样例中没有纯扫描PDF。

| File | Pages | Format | Classification | Evidence |
| --- | ---: | --- | --- | --- |
| `JS26032501-1-03-036#上下座B#A1.pdf` | 2 | A3 | `vector` | 大量原生文字和矢量路径，仅有极小Logo图像 |
| `JS20102801-02-018#手指头#A1.pdf` | 1 | A4 | `hybrid` | 保留原生文字和矢量对象，同时存在覆盖整页的1444×2048栅格图层 |
| `JS20123103-10-033#手臂拖链支架上改#A2.pdf` | 1 | A4 | `vector` | 大量原生文字、旋转文字和矢量路径，仅有极小Logo图像 |
| `JS24030402-30-013#上插臂#A0.pdf` | 2 | A3 | `vector` | 大量原生文字和矢量路径，仅有极小Logo图像 |

样例实际包含普通尺寸、直径、孔、螺纹、半径、角度、上下偏差、形位公差、基准、粗糙度、焊接要求、技术要求、标题栏、修订三角形、多方向文字和多页图纸。

#### 1.3.1 Additional Regression Candidate Batch

2026-07-21又从以下目录实际检查到11份PDF，而不是消息中预估的10份：

`/home/reggie/文档/xwechat_files/wxid_ut5o9e1igztd22_f3a1/msg/file/2026-07/123`

磁盘文件名存在GBK/CP437解码造成的中文乱码。下表使用可恢复的中文显示名描述文件，但本次不改动源文件名。

| Display File Name | Pages | Physical Page | Classification | Evidence |
| --- | ---: | --- | --- | --- |
| `BK20101401-09L1000#引拔梁(400W)#C1.PDF` | 1 | A3 landscape | `vector` | 1069个原生字符、373个绘图对象，最大图像覆盖率0.3% |
| `BW25BN007#主引拔电机同心轴#C1.pdf` | 1 | A4 portrait | `scanned` | 无文字层、无矢量绘图，单张图像覆盖整页 |
| `FB26031001-001#手臂滑板1#A2.PDF` | 1 | A3 landscape | `vector` | 1155个原生字符、947个绘图对象，最大图像覆盖率0.3% |
| `FB26041801-015#手臂次传动轮上固定座2#A0.PDF` | 1 | A4 portrait | `vector` | 515个原生字符、112个绘图对象，最大图像覆盖率0.6% |
| `FB26042401-042#梯形螺杆固定座2#A0.PDF` | 1 | A3 landscape | `vector` | 508个原生字符、83个绘图对象，最大图像覆盖率0.3% |
| `HS02CN001#手臂滑板1#A0.PDF` | 1 | A3 landscape | `vector` | 899个原生字符、665个绘图对象，最大图像覆盖率0.3% |
| `JS24080802-4-014#横行滑板左#A0.PDF` | 1 | A3 landscape | `vector` | 1218个原生字符、838个绘图对象，最大图像覆盖率0.3% |
| `JS26032001-1-003#横行滑板#A0.PDF` | 1 | A3 landscape | `vector` | 1228个原生字符、891个绘图对象，最大图像覆盖率0.3% |
| `SY26042201-14#引拔梁固定座#A0.PDF` | 1 | A3 portrait | `vector` | 690个原生字符、183个绘图对象，最大图像覆盖率0.3% |
| `ZH18030601-15#手臂滑板#A0.pdf` | 1 | A3 landscape | `scanned` | 无文字层、无矢量绘图，单张图像覆盖整页 |
| `ZHZS25032501-04#横行滑板（阿博格）#A0.PDF` | 1 | A3 landscape | `vector` | 1008个原生字符、393个绘图对象，最大图像覆盖率0.3% |

该批次的9份矢量PDF由SOLIDWORKS PDF出版程序生成，可作为 `dev_regression_supported` 候选。两份纯栅格PDF由Adobe Acrobat Image Conversion Plug-in生成，只作为 `unsupported_routing_regression`，不进入当前正式识别准确率或P0验收。

新增矢量样例覆盖螺纹、半径、公差、深度、贯穿、角度、焊接、技术要求和大量旋转文字。原生提取中还观察到直径符号丢失或组合标注被拆成 `16 x` 与 `9 通` 等片段，适合验证局部OCR补充、符号恢复和多行分组。

`JS24080802-4-014#横行滑板左#A0.PDF` 与 `JS26032001-1-003#横行滑板#A0.PDF` 的规范化原生文本相似度约84%，可用于稳定性回归，但不能作为两个完全独立的覆盖类别。该批次全部为单页，不能替代原4份样例中的多页覆盖。

在质量人员提供并确认标准答案前，这11份文件只能用于开发、稳定性、兼容性和输入路由测试，不能计算召回率、字段准确率或漏检率。由于开发人员和设计过程已经查看该批次，它们均不得成为正式盲测集。

### 1.4 Seven-day Success Definition

七天成果是可交给内部人员真实试用的纵向闭环MVP，不是演示静态页面，也不是生产终态。

成功要求：

1. 当前4份PDF可以上传并完成端到端处理。
2. 自动结果可以明显减少人工录入和编号工作。
3. 漏项、误项、字段错误和气泡位置可以人工修正。
4. 最终气泡、表格、带气泡PDF和Excel保持一致。
5. 失败不会静默生成错误的正式文件。

P0不承诺任意机械图纸、100%自动正确、无人审核、完整理解所有工程语义或生产认证。

## Goals and Non-goals

### 2.1 Goals

- 支持约定范围内的CAD矢量PDF和矢量/图像混合PDF。
- 优先使用PDF原生文字、坐标、方向和矢量对象。
- 只在缺失或异常区域调用OCR API。
- 使用局部多模态LLM完成分组复核、工程语义解释和严格JSON结构化。
- 保存页码、原始坐标、渲染坐标和转换参数。
- 支持自动候选、人工审核、基础气泡、重新编号和固定模板导出。
- 保存自动结果和人工结果，避免用人工修正冒充自动识别能力。
- 所有正式产物从同一个审核结果生成并执行一致性校验。

### 2.2 Non-goals

P0不包括：

- AI外观缺陷检测；
- 实际测量值录入；
- Pass/Fail判定；
- 蓝牙或USB量具；
- ERP集成；
- 完整质检报告；
- 任意CAD格式直接解析；
- 纯扫描PDF正式验收；
- 自训练OCR、YOLO或大型视觉模型；
- 任意Excel模板自动适配；
- 高质量全局气泡优化；
- 完整生产级身份、审计、发布和灾备平台。

## Section 1 — Overall Architecture Contract

### 1.1 Technology Stack

后端：

- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy 2 / Alembic
- Redis
- Celery

前端：

- React
- TypeScript
- Vite
- PDF.js
- SVG气泡交互覆盖层；必要时Canvas只用于非交互渲染辅助

文档处理：

- PyMuPDF
- Pillow
- OpenCV仅在必要时使用
- openpyxl

外部能力：

- `OcrProvider`
- `VisionLlmProvider`
- `FileStorage`

长期架构采用模块化单体：一个FastAPI应用、一个Celery Worker、一个React前端、一个PostgreSQL和一个Redis。微服务、Kubernetes或事件总线不属于当前设计方向；七天实际运行单元只由Section 10授权。

### 1.1.1 Deployment Isolation

新系统与现有Enterprise-grade RAG/RAGFlow部署在同一Linux主机，但保持：

- 独立代码仓库和Docker Compose project；
- 独立容器命名、内部网络、环境变量和密钥；
- 独立PostgreSQL database和database user；
- 独立Redis key prefix、任务队列和逻辑database；
- 独立共享volume或对象存储bucket；
- 独立发布、回滚和日志。

新系统不得直接读写RAG业务表、向量库或文档存储。共享OCR、LLM或反向代理时只能通过API，并配置独立调用身份、并发、超时、有限重试和使用统计。Section 10只授权闭环需要的最小隔离；完整资源配额和迁移治理进入P2。

### 1.2 Component Responsibilities

- React负责PDF预览、审核表格、图表联动和气泡交互。
- FastAPI负责项目、候选、检验项、审核和导出API。
- Celery负责PDF解析、OCR、LLM调用、气泡PDF和Excel生成。
- PostgreSQL是任务、审核、发布和业务状态的事实来源。
- Redis只负责Celery协调、短期进度和可选锁协调，不保存正式业务事实。
- FileStorage保存PDF、图片、大型JSON、Provider响应和导出文件。

Redis丢失或重启不得丢失项目状态和处理结果。写请求使用PostgreSQL `version` 进行乐观并发控制。

本地FileStorage的长期正确性合同是：FastAPI和Celery Worker访问同一个受控共享目录或Docker volume；文件先写同一文件系统中的临时路径，完成hash和内容校验后原子重命名；数据库只保存引用、hash、大小、MIME类型和创建时间。Section 10明确选择其中哪些检查进入七天实现。

### 1.3 Provider Boundaries

业务代码只依赖：

```text
OcrProvider
VisionLlmProvider
FileStorage
```

Provider实现、模型、接口版本、Prompt版本、JSON Schema版本和关键参数作为运行配置与结果元数据保存。API Key只存在于服务端环境变量或密钥配置，不写数据库、不返回前端、不进入日志。

本期已选Provider配置：

- OCR：腾讯云 `GeneralAccurateOCR`
- API Version：`2018-11-19`
- Endpoint：`ocr.tencentcloudapi.com`
- `ConfigID=OCR`
- `WordsType=2`
- 大图可启用 `EnableDetectSplit=true`
- 默认归一化并保存 `DetectedText`、`Confidence`、`ItemPolygon`、`Polygon`、`Angle` 和 `RequestId`
- 多模态LLM：阿里云百炼 `qwen3-vl-plus`
- 地域：中国内地，北京
- OpenAI-compatible Chat Completions
- Endpoint：`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions`
- 非思考模式
- `response_format={"type":"json_object"}`

业务Schema不得依赖腾讯云或阿里云SDK类型。

本期先使用两家平台的免费额度。相同文件、页面、区域、模型、Prompt和Schema版本必须命中缓存，不能因刷新页面、人工编辑、移动气泡或重新导出而重复计费。七天缓存实现深度由Section 10限定。

### 1.4 Main Data Flow

```text
上传PDF并计算hash
→ 页面类型检测
→ 原生对象提取
→ 识别需要OCR的区域
→ 页面对象清单
→ 候选生成与基础覆盖检查
→ 局部候选调用VisionLlmProvider
→ JSON Schema与确定性规则校验
→ raw_automatic_result
→ review_working_copy
→ reviewed_result
→ 正式气泡PDF和固定SIP Excel
```

自动编号、业务规则校验、气泡布局、审核状态和Excel导出由本地确定性代码负责。LLM不能直接形成已审核或已发布结果。

## Section 2 — PDF Routing and Page Inventory Contract

### 2.1 Page-level Classification

PDF分流以页面为最小单位。分类信号包括：

- 可用原生字符数和文本块数；
- 字符可打印比例；
- 文本方向和覆盖区域；
- 矢量路径和覆盖区域；
- 图片数量和页面覆盖率；
- 是否存在整页或大面积栅格；
- 原生对象与渲染视觉是否明显不一致。

页面类型：

- `vector`：原生对象足以描述主要工程标注。
- `hybrid`：存在可用原生对象，同时有大面积图像或缺失区域。
- `scanned`：主要由栅格组成，原生对象不足以支持坐标级标注提取。
- `ambiguous`：证据冲突，技术路由按hybrid执行，但发布前必须人工确认。

每页长期模型保存：

- `detected_page_type`
- `classification_confidence`
- `classification_evidence`
- `classification_rule_version`
- `manually_confirmed_page_type`
- `confirmed_by`
- `confirmed_at`

自动结果不能覆盖人工确认。包含scanned页面的项目可以上传、渲染、诊断和实验性OCR，但不属于本期正式发布范围。

当前4份样例用于形成 `classification_rule_version=v0.1`，不永久冻结阈值。回归集建立后允许校准；正式盲测前冻结；盲测开始后不得临时修改。

### 2.2 Coordinate Contract

业务坐标统一为：

- 基准区域：页面 `CropBox`
- 单位：PDF point
- 原点：未旋转CropBox左上角
- x轴：向右
- y轴：向下
- 页面旋转：存储前归一到未旋转页面坐标
- bbox：`[x0, y0, x1, y1]`
- normalized坐标：基于CropBox有效宽高

保存：

- `bbox_pdf`
- `bbox_normalized`
- `page_rotation`
- `pdf_to_render_matrix`
- `render_to_pdf_matrix`

所有写入坐标经过页面边界裁剪校验。矩阵往返误差目标为不超过0.5 PDF point，渲染坐标不超过1 pixel。

### 2.3 Native Objects and Rendering

页面对象清单的最小长期表示以span级和line级对象为主：

- 原始文本和规范化文本；
- bbox、方向、字体、字号和颜色；
- 线段、折线、曲线、矩形和填充；
- 图片位置、像素尺寸和覆盖率；
- 页面尺寸和渲染参数。

字符级对象只在上下偏差、旋转文字、特殊符号、多行组合、OCR冲突或LLM复核时展开。

页面渲染和OCR截图保存：

- dpi或scale；
- 宽高；
- alpha/background；
- colorspace；
- render engine版本；
- render matrix。

### 2.4 OCR Routing

OCR只补充：

- 原生文字缺失；
- 字符乱码；
- 特殊工程符号异常；
- 图像区域；
- 原生解析与视觉明显不一致的局部区域。

页面建立基础coverage map：

- `native_text_coverage`
- `image_only_regions`
- `suspicious_symbol_regions`
- `visual_native_mismatch_regions`

优先局部OCR，只有确有必要时才整页OCR。整页与局部OCR使用不同 `region_id`，防止重复文字进入候选。

### 2.5 Text Observations

原生与OCR文本不能合并成不可追溯字符串。统一观察对象包含：

- `observation_id`
- `source_type: native | ocr`
- `raw_text`
- `normalized_text`
- `bbox_pdf`
- `direction`
- `confidence`
- `parent_region_id`
- `aligned_group_id`
- `relation_type: equivalent | supplement | conflict | independent`

候选生成读取aligned group，并保留所有原始观察。

### 2.6 Page Inventory

长期页面清单包括：

- 原生文本块；
- OCR补充文本块；
- 矢量对象；
- 图片区域；
- 辅助尺寸几何证据；
- 标题栏、修订栏、技术要求区和主要视图区域；
- 坐标矩阵；
- 页面分类证据；
- 来源冲突与异常。

疑似尺寸线、箭头、引线和公差框在首版路线中只是辅助证据，不能成为候选生成硬依赖。区域状态支持 `detected / ambiguous / manually_adjusted`；低置信度区域不能直接导致内容被排除。

## Section 3 — Candidate Generation Contract

### 3.1 Recall-first Seeds

候选生成采用规则召回优先、几何辅助、局部LLM复核和人工兜底。

长期候选分类需要覆盖：

- 普通线性尺寸；
- `±`和上下偏差；
- `Φ`、孔、沉孔、深度和贯穿；
- `M`螺纹；
- `R`半径和圆角；
- 角度；
- 数量前缀；
- 多行组合标注；
- 常见形位公差原文；
- 粗糙度；
- 明确局部焊接要求；
- 技术要求条款。

单独数字不能自动成为强候选。它需要视图区域、工程符号、邻近几何、字体方向或公差上下文等证据；否则只进入低置信度seed或coverage检查。

### 3.2 Primary Dispositions

每个工程相关observation group有且只有一个主disposition：

- `inspection_candidate`
- `reference_context`
- `non_inspection`
- `ambiguous`

唯一性只约束主disposition，不限制上下文多重引用。基准、标准条款和视图上下文不能为满足唯一去向而复制。

示例：

- 独立基准A：`reference_context / datum_definition`
- 形位公差框：`inspection_candidate`
- 剖视图代号A-A：`non_inspection`，同时可作为视图元数据
- 未注公差条款：可以形成通用要求，同时成为其他尺寸的tolerance context

### 3.3 Grouping Rules

分组证据包括文本方向、基线、行间距、字体、空间邻近、共享引线、视图上下文和工程语义兼容性。

固定规则：

- `16 × M5`、`4 × M6 通`：一个候选，公共quantity保存数量。
- 多行孔、沉孔、深度或螺纹组合：一个复合候选，有序子要求。
- 每个完整形位公差框：一个候选。
- 单独基准符号：reference context，不生成检验项。
- 多个形位公差框：默认分别形成候选。
- 局部粗糙度和局部焊接要求：候选并建议气泡。
- 全局粗糙度和全局焊接要求：通用检验要求，不建议气泡。
- 技术要求逐条分类，只有可执行、可验证的质量要求才成为通用检验项。

仅文本或数值相同不能合并。不同视图的相同标注默认分别保留，只能提出疑似重复建议，由人工决定。

### 3.4 LLM Routing

明确、单行、规则可完整解析的常见尺寸可以先由确定性解析器处理。以下情况调用VisionLlmProvider：

- 多行组合；
- 上下偏差；
- OCR冲突；
- 形位公差；
- 焊接；
- 粗糙度；
- 低置信度；
- 规则校验失败；
- 人工指定视觉复核。

调试模式可配置所有候选调用LLM；正式默认按需路由，并保存 `llm_review_reason`。

每次局部复核保存candidate bbox、crop bbox、padding、图片hash、渲染版本及进入截图的相邻observation。局部上下文不足时最多扩大一次；仍不足则进入人工审核，不能让模型猜测。

LLM只负责分组复核、工程语义解释、复合项结构化、模糊对象分类建议和严格JSON输出。它不决定正式检验项、重点尺寸、气泡编号、气泡位置、检测方法或Excel内容。

### 3.5 Coverage Check

基础Coverage Ledger要求所有疑似工程标注具有明确disposition，不允许静默丢弃。

问题级别：

- `blocking`：没有disposition、来源或坐标，或存在不兼容重复归属。
- `review_required`：已进入ambiguous或需要人工确认的context。
- `informational`：低置信度、OCR补充关系等。

`coverage_checked` 成功要求blocking为0且所有对象有disposition。`automatic_result_ready` 可以包含review_required项，使其进入人工审核；正式发布前必须处理。

自动排除项提供可复查列表，能够按原因筛选、在图纸定位并恢复为ambiguous或候选。

## Section 4 — Data Semantics and Business Rules Contract

### 4.1 Long-term Data Layers

长期语义分层：

```text
observation / vector object
→ observation group / reference context
→ candidate seed
→ inspection candidate
→ reviewed inspection item
→ immutable reviewed_result
```

长期模型支持候选版本、合并拆分血缘、字段级来源、reference context、疑似重复关系和不可变审核快照。但Section 10明确限制P0只实现闭环所需的最小子集。

候选语义：

- 修改原文、分类或字段：同一candidate_id的新candidate_version。
- 合并多个候选：创建新candidate_id，原候选superseded。
- 拆分候选：创建多个新candidate_id，并保存split来源。
- 旧候选和旧版本不物理删除。

首次审核拆分使用 `split_from_candidate_id`。`split_from_item_id` 只用于已发布项目的新修订。

### 4.2 Inspection Item Common Fields

长期检验项包含：

- `inspection_item_id`
- `project_id`
- `review_version`
- `item_type`
- `raw_text`
- `normalized_text`
- `inspection_standard_text`
- `scope: local_feature | global_requirement`
- `primary_source_location_id`
- `balloon_required`
- `is_composite`
- `quantity`
- `quantity_scope`
- `structured_payload`
- `semantic_requires_confirmation`
- `version`

`inspection_item_source` 是多页、多视图来源事实的唯一存储。`primary_source_page`由主来源派生，不保存含义不明确的单值source page。

数值字段使用Decimal并保留原始字符串。单位不能凭机械常识补为mm；从标题栏继承时必须关联source context。

### 4.3 Typed Payloads

公共关系字段配合按类型校验的JSONB payload：

| Item Type | Core Fields |
| --- | --- |
| `linear_dimension` | nominal、upper/lower tolerance、unit |
| `diameter_dimension` | diameter、feature_kind、depth、through、hole_type |
| `thread` | thread_spec、thread_depth、through |
| `radius` | radius_value |
| `angle` | angle_value、upper/lower tolerance |
| `geometric_tolerance` | characteristic、tolerance、material condition、datum references |
| `roughness` | parameter、value、unit、machining requirement |
| `weld` | type、size、length、pitch、side、contour、finish、all-around、field weld |
| `general_requirement` | category、requirement text |
| `composite` | composite-level attributes |

识别出 `Φ` 时不能默认是孔。保存 `feature_kind=hole | shaft | cylindrical_feature | unknown`，不确定时进入人工确认。

复合项子要求使用独立、有序的 `sub_requirement` 作为权威存储。API可以组合输出数组，但数据库不能双写两份可修改数据。

非复合项的公共quantity是唯一事实来源；复合子要求可以各自拥有quantity。公共quantity只在表示共享数量时使用，并明确quantity_scope。

### 4.4 Field Provenance

长期模型通过版本化 `field_states` JSONB保存字段值、来源、置信度、确认状态和确认人。来源包括：

- `native_pdf`
- `ocr`
- `llm`
- `deterministic_rule`
- `inherited_context`
- `manual`

Section 10只选择简化来源和人工确认；完整字段级治理UI不属于七天范围。

### 4.4.1 Suggested and Confirmed Business Fields

长期模型分离建议值与正式值：

- `suggested_is_critical` / `confirmed_is_critical`
- `suggested_methods[]` / `confirmed_method`
- `suggested_inspector_roles[]` / `confirmed_inspector_roles[]`
- 建议颜色 / 审核后的 `color_code`

同时保存建议来源、reason、confidence、rule id和rule version。正式Excel只使用确认值。

重点尺寸建议按明确图纸标记、配置规则和人工确认分层。检测方法规则可以考虑特征类型、尺寸范围、公差、孔槽台阶、接触式/非接触式和质量部门配置。检验角色规则可以考虑特征、重点属性、检测方法、工序、产品类别和检验阶段。Section 10只选择固定配置、简单默认值和人工修改；完整规则系统、历史SIP相似推荐和管理后台进入P1。

颜色保存 `color_code`、`color_rule_id`、`color_rule_version` 和 `color_source`。人工颜色不能被后续规则静默覆盖。

### 4.5 Confirmed Business Rules

长期检验项筛选采用质量人员可配置规则并保留人工最终确认；LLM不得猜测正式筛选规则。Section 10授权的七天默认配置采用“全部明确标注优先召回”：所有明确标注的尺寸、孔、螺纹、半径、角度和形位公差先进入候选并建议气泡，审核人员再逐项保留、排除或改为上下文。

1. 本期默认所有明确标注的尺寸、孔、螺纹、半径、角度和形位公差均进入候选并建议气泡。
2. 技术要求逐条分类；可执行、可验证的质量要求生成通用检验项，不生成气泡。
3. 成组重复特征默认一个检验项和一个气泡，quantity保存数量；人工可拆分，本期不自动拆分。
4. 多行组合标注默认一个复合项和一个气泡，子要求有序保存。
5. 不同视图的相同标注默认分别保留；系统只提示疑似重复，人工决定合并。
6. 合并后表格一行、不累加quantity、保留全部来源，由用户选择主气泡位置。
7. 未注公差尺寸仍生成候选；记录标准引用，上下偏差为空并要求人工确认。本期不自动换算GB/T 1804。
8. 每个完整形位公差框形成一项；独立基准符号只作为datum context。
9. 局部粗糙度生成检验项和气泡；全局或“其余表面”要求生成通用项，无气泡。
10. 明确局部焊接要求生成检验项和气泡；全局焊接质量要求生成通用项，无气泡。
11. 修订三角形、剖视代号、局部视图代号、区域编号、比例、页码、签名、日期和标题栏元数据不是检验项。
12. 重点尺寸采用明确标记优先、配置规则建议、人工确认；LLM不作正式判断。
13. 检测方法采用业务规则建议，历史SIP相似推荐进入P1；人工确认形成正式值。
14. 检验人员字段表示角色或责任组，不表示具体员工姓名。
15. 气泡颜色来自版本化规则并允许人工覆盖；颜色不是重点尺寸的唯一事实。

## Section 5 — Balloon Contract

### 5.1 Suggested and Formal Numbering

审核前编号只是建议，不能作为正式业务编号。影响项目集合、主来源或balloon_required的操作只将编号状态标记为stale，不得在用户编辑时静默重排其他气泡。

正式编号只在以下条件满足后生成：

- 所有active候选有结论；
- 合并、拆分和疑似重复已处理；
- balloon_required已确认；
- 正式检验项集合已冻结。

默认从1开始；用户可指定起始编号N。Section 10选择的首版编号不允许缺号，无气泡通用要求不占编号。

稳定排序：

1. page index；
2. view region稳定顺序；
3. source bbox；
4. direction；
5. normalized text；
6. stable seed key或source observation hash；
7. candidate id仅作最后兜底。

### 5.2 Minimum Layout Contract

Section 10选择的基础布局使用有限方向候选点和确定性贪心评分：上、右上、右、右下、下、左下、左、左上，必要时增加视图外围位置。

禁止：

- 超出CropBox；
- 覆盖标题栏固定区域；
- 覆盖其他正式气泡中心；
- 无法建立有效引线。

高惩罚：覆盖尺寸文字、技术要求或引线穿过其他气泡。中惩罚：覆盖主要轮廓、引线过长或穿过密集区域。低惩罚：偏离首选方向或靠近页面边缘。

所有候选位置均失败时返回：

- `placement_status=manual_required`
- best attempt position
- collision flags
- failure reason

自动布局不理想不能阻塞审核闭环，用户可以拖动修正。

### 5.3 Geometry Semantics

区分：

- `anchor_bbox_pdf`：完整原标注区域
- `leader_target_pdf`：引线实际指向点
- `primary_source_location_id`：正式项主来源
- `balloon_center_pdf`：气泡圆心

默认leader target取标注bbox靠近气泡的一侧边缘或明确引线端点，不固定使用bbox中心。

### 5.4 Review Operations

Section 10选择的气泡审核操作包括：

- 拖动；
- 删除或重建；
- 修改引线目标；
- 调整顺序并重新编号；
- 选择合并项主来源；
- 图纸与表格双向定位。

删除气泡不能静默删除检验项。重新关联在后端事务中校验原项目是否失去气泡、新项目是否已有气泡、页码和编号是否冲突。

气泡超页、完全覆盖标注、编号不可读、严重重叠或图表失联不能通过accepted risk绕过。

### 5.5 Formal Rendering

前端SVG只用于交互。正式带气泡PDF由后端从reviewed_result和PDF坐标重新绘制。使用受控字体，保存字体名称、hash、字号、编码和renderer版本。

Excel嵌图同样从后端正式气泡PDF渲染，不能使用前端截图。

## Section 6 — Review Workbench Contract

### 6.1 Result Layers

长期流程区分：

- `raw_automatic_result`
- `review_working_copy`
- `review_submission_snapshot`
- `reviewed_result`
- published artifacts

Section 10只授权raw automatic、working copy、reviewed result和正式导出结果。P1补齐submission、退回和完整审核治理。

长期业务状态合同为：

```text
processing
→ ready_for_edit
→ editing
→ pending_review
→ reviewing
→ approved
→ exporting
→ published
```

并允许：`reviewing → changes_requested → editing`、审核开始前撤回、`export_failed → approved`重试、`published → new_revision`和`processing_failed → processing`局部重试。状态只能由后端校验角色、前置条件和版本后转换，并记录from/to、operator、reason和时间。

长期流程在“提交审核”时冻结 `review_submission_snapshot`。编辑保存与审核批准是两个独立动作；Section 10允许同一人兼任并只授权简化的“确认并冻结reviewed result”动作。完整submission/退回UI和角色治理属于P1。

### 6.2 Workbench Behavior Selected by Section 10

左侧：

- 多页PDF切换；
- 缩放和平移；
- 候选框、来源和气泡；
- 点击定位；
- 拖动气泡。

右侧：

- 原始检验标准；
- 核心结构化字段；
- quantity和子要求；
- balloon_required；
- requires_confirmation；
- 重点尺寸、检测方法、角色和颜色的简单建议与人工修改；
- 页码和主来源。

操作：

- 保留；
- 排除；
- 修改原文；
- 修改核心字段；
- 人工新增；
- 简单合并和拆分；
- 修改balloon_required；
- 处理ambiguous；
- 调整气泡和编号；
- 生成预览；
- 确认审核并正式导出。

复杂字段来源可视化、通用上下文编辑器、图形化血缘编辑器和高级批量规则进入P1。

### 6.3 Concurrency

长期流程支持可信反向代理身份、editor/reviewer/admin、项目租约和状态机。Section 10只授权：

- 简单操作人记录；
- 单项目单编辑人；
- 基础锁超时；
- PostgreSQL expected_version；
- 自动保存草稿；
- 保存不等于审核确认。

完整代理身份、RBAC、心跳、管理员接管和四眼审核进入P1/P2。

### 6.4 Preview versus Formal

预览读取working copy，使用独立文件名和存储前缀，并带明显水印。预览不能生成reviewed_result，不能进入正式成功状态，也不能通过重命名变成正式文件。

正式导出只能读取不可变reviewed_result。

## Section 7 — Fixed SIP Excel and PDF Export Contract

### 7.1 Controlled Template

Section 10只授权一份质量部门确认的 `.xlsx` 模板。长期模板注册保存：

- template id和version；
- file hash；
- mapping version；
- 工作表名称；
- 元数据单元格；
- 明细起止区域；
- 样板行或预留容量；
- 固定说明和签核区；
- 气泡图放置规则。

本期不建设通用行插入引擎。模板应预留足够容量，或只复制受控样板行组。超过登记最大容量时阻止正式导出并报告错误。

### 7.2 Mapping

固定映射至少包括：

- 物料编码；
- 物料名称；
- 图样代号；
- 材质；
- 版本号；
- 气泡序号；
- 检验项目；
- 检验标准；
- 检测方法；
- 是否重点尺寸；
- 检验人员角色；
- 来源页码；
- 气泡图区域。

一个普通项对应一个logical detail；一个复合项仍对应一个logical detail；无气泡通用要求也属于logical detail。物理Excel行数不等于逻辑明细数。

保存：

- inspection item count
- ballooned item count
- general requirement count
- logical detail count
- physical Excel row count

### 7.3 Engineering Text and Excel Safety

- raw text完整保存；
- 单元格使用受控Unicode和换行；
- 有独立偏差列时分别填上、下偏差；
- 只有检验标准列时使用审核确认后的多行文本；
- 复杂符号允许保留原文或局部截图，不能为美观改变语义。

来自PDF、OCR、LLM或用户的文本若以 `= + - @` 开头，必须作为普通文本写入，禁止公式注入。只有模板注册的受控公式可以写为公式。

### 7.4 Ballooned PDF and Embedded Images

正式气泡PDF是高精度权威文件。Excel嵌图是查看预览，不承担全部矢量精度。

嵌图参数使用：

- preferred dpi；
- max long edge；
- max total pixels；
- image format；
- compression quality；
- max embedded image bytes。

按模板实际显示尺寸决定分辨率，并保持宽高比。所有页面按原页码嵌入。当前模板必须验证当前4份样例实际A3/A4 PDF页面尺寸和多页文件的可读性、文件大小、打开和打印行为；文件名中的A0/A1/A2不作为物理页面尺寸依据，该验证不扩张为任意图幅承诺。

### 7.5 Minimum Export Consistency Contract

Section 10选择的导出能力从同一个reviewed_result生成：

- 带气泡PDF；
- 固定SIP Excel；
- 简化manifest。

三个产物在独立staging目录生成。只有PDF、Excel和manifest均成功且通过hash、编号和逻辑明细一致性校验，数据库才将导出状态标记为成功。普通下载接口只暴露成功导出，不允许单独发布部分产物或混用不同审核结果的产物。

P1补齐完整export run发布指针、多产物事务治理、正式修订、回滚和LibreOffice自动烟雾校验。

长期发布合同使用独立 `export_run` staging目录生成PDF、Excel和manifest。全部产物校验后将export run标记为validated，再在PostgreSQL事务中更新 `project.published_export_run_id`。下载接口只读取已发布指针；任何子产物失败都不能更新该指针。Section 10只授权简化导出状态，以实现相同的“不发布部分产物”业务语义，不建设完整发布管理界面。

正式导出的长期幂等键包括reviewed result、原PDF、模板、mapping、renderer、字体和渲染配置hash。相同输入默认返回已有成功结果。`force_regenerate` 只能重新物化文件，不能改变reviewed result。

### 7.6 Validation

Section 10选择的正式导出执行以下最小校验：

- Excel逻辑明细数等于正式检验项数；
- 气泡数等于balloon_required=true项数；
- PDF气泡编号和Excel序号一致；
- 通用要求序号为空；
- 必填字段使用审核确认值；
- 工作表、固定区和签核区未被覆盖；
- 嵌图页数等于PDF页数；
- openpyxl可重新打开；
- Excel可编辑；
- PDF页数与原文件一致。

文件名和工作表名称经过安全生成，处理路径穿越、非法字符、31字符限制和重名。

## Section 8 — Intermediate Results and Error Contract

### 8.1 Long-term Artifacts

长期设计支持不可变artifact、阶段attempt、current pointer、依赖失效、保留等级和发布引用。

artifact保留等级：

- `permanent`：原始PDF、自动结果、审核快照、正式PDF、Excel和manifest。
- `diagnostic`：Provider响应、失败输出、局部截图和阶段JSON。
- `reproducible_cache`：页面渲染、OCR/LLM缓存和中间转换。
- `temporary`：staging、烟雾测试副本和未完成上传。

大型结果保存在FileStorage，PostgreSQL只保存引用、hash、大小、Schema版本、关系和摘要。

长期阶段模型同时保留 `current_processing_stage` 和独立 `processing_stage_run`。阶段运行可以按项目、页面、区域或候选记录，状态为 `pending / running / succeeded / failed / skipped / invalidated`；矢量页未调用OCR时记录为 `skipped`，不得伪造完成。每次重试创建新attempt，成功后只事务化更新current pointer，不覆盖旧结果。

artifact一经生成不可原地修改。生产者先写临时文件，校验hash和Schema，再在PostgreSQL事务中更新current pointer并使旧artifact失效；数据库事务失败时，新文件只能作为不可读的orphan等待清理。修改working copy不得使raw automatic失效；移动气泡只影响布局校验、提交快照和导出；模板变化只影响新导出；Prompt或模型变化不会静默使历史项目失效。

长期Celery任务使用 `stage_run_id` 或稳定 `logical_task_key` 去重，执行前检查输入hash和current pointer，数据库提交成功后才标记succeeded。重复投递、Worker重启和有限重试不得重复创建正式业务结果。task soft/hard timeout、`acks_late`、visibility timeout、Worker并发和Provider限流由版本化运行配置控制。Section 10只授权避免重复正式结果所需的最小幂等检查；完整stage/attempt治理进入P1。

Section 10只授权最小结果引用、错误和调用统计；完整artifact生命周期、依赖图和清理进入P1。

### 8.2 Error Types

运行错误：

- PDF解析和渲染；
- 坐标转换；
- OCR Provider或Schema；
- LLM Provider或JSON Schema；
- 确定性校验；
- 气泡布局；
- 存储；
- 模板、PDF或Excel导出；
- 跨产物一致性。

人工审核修正：

- 候选漏检；
- 候选误选；
- 分组错误；
- 语义或字段错误；
- 上下文错误；
- 气泡关联、位置或编号错误。

系统还区分：

- `unsupported_input`
- `transient_dependency_unavailable`
- `invalid_configuration`
- `processing_defect`

纯扫描、加密或损坏输入不是程序崩溃。Provider暂时不可用也不应把项目标记为永久失败。

### 8.3 Severity

- `fatal`：项目无法继续处理。
- `blocking`：不能进入下一正式门禁。
- `review_required`：可进入人工审核但不能直接发布。
- `warning`：必须展示，可按允许范围人工接受。
- `informational`：运行信息。

正式一致性blocking和fatal不能通过accepted risk绕过。

### 8.4 Provider Calls and Cache

Provider request key至少包含：

- 文件或crop hash；
- page和bbox；
- Provider和Adapter版本；
- 模型及版本；
- Prompt和Schema版本；
- 关键参数。

成功缓存存在时不得重复调用。页面刷新、移动气泡、修改表格或重新导出不能触发OCR/LLM。

每次调用记录请求ID、耗时、重试、计费字符或token、图片数量、计价版本、货币、估算成本和缓存命中。API Key、Authorization、完整base64、SDK签名和完整工程文本不得写结构化日志。

外部API优先接收局部截图，不发送无关标题栏、签名和物料信息。保存实际发送区域及图片hash。

### 8.5 Preflight and Minimum Observability

应用硬启动依赖只有PostgreSQL、FileStorage和可读取的必要配置。Redis/Celery、OCR Provider、LLM Provider、模板、字体和LibreOffice属于能力检查：某外部Provider暂时不可用时，应用仍可查看已有项目，但必须禁止提交依赖该能力的新任务并显示unavailable。Provider连通性测试不得在每次进程启动时强制产生付费调用。

Section 10选择的处理与导出能力执行共享存储、Redis/Celery、已配置Provider、受控模板和气泡字体的最小能力检查；LibreOffice自动烟雾测试进入P1。能力检查失败必须显式阻止对应操作，不能静默产生正式成功状态。

Section 10选择的基础错误面板显示：

- 当前阶段；
- 页级成功、失败和跳过；
- blocking、review_required和warning数量；
- 错误定位入口；
- 允许的局部重试；
- Provider调用次数、耗时和估算成本。

详细诊断通过数据库、管理接口和离线JSON完成。完整trace浏览器、artifact依赖图、实时成本大屏和根因分析UI进入P1。

## Section 9 — Testing and Acceptance Contract

### 9.1 Test Surfaces

长期测试契约包括：

- PDF分类、坐标、文本规范化、候选规则和Schema单测；
- Provider fixture contract测试；
- FastAPI、PostgreSQL、Redis、Celery和FileStorage集成测试；
- React图表联动、编辑和气泡交互测试；
- 上传到正式导出的E2E；
- Excel公式注入、路径和工作表名称安全测试；
- PDF/Excel/编号一致性测试。

Section 10只授权当前4份样例闭环所需的focused单测、Provider fixture和E2E，不要求七天内完成生产级覆盖率体系。

### 9.2 Three-layer Evaluation

自动层冻结 `raw_automatic_result` 并计算：

- 检验项召回率；
- 检验项误选率；
- 错误排除率；
- 标注分组准确率；
- 原文exact match和CER；
- 字段准确率；
- 复合项准确率；
- 气泡覆盖率和关联准确率；
- 自动编号准确率；
- 重点尺寸、方法和角色建议准确率；
- 页面分类准确率。

人工效率层基于 `raw_automatic_result → reviewed_result` 的结构化diff，统计受影响项、字段、净新增、净删除、气泡移动、合并拆分、干预率和时间节省。

正式交付层要求：

- 所有正式项目完整；
- 需要气泡的项目关联正确；
- 编号唯一连续；
- PDF、Excel和reviewed result一致；
- Excel可打开和编辑；
- blocking为0；
- 正式导出成功率100%。

自动识别不足允许通过人工审核完成正式结果，但必须保留raw automatic，不能用最终人工结果冒充自动识别能力。

指标使用以下固定定义；匹配规则和统计粒度随评测版本冻结：

| Metric | Formula | Grain |
| --- | --- | --- |
| 检验项召回率 | 与标准答案匹配的自动检验项数 / 标准答案检验项总数 | item、page、document及数据集汇总 |
| 检验项误选率 | 无标准答案匹配的自动检验候选数 / 自动检验候选总数 | item和document |
| 错误排除率 | 被自动归为non_inspection的真实检验项数 / 标准答案检验项总数 | item和document；高严重级 |
| 标注分组准确率 | 分组成员与标准答案完全一致的自动组数 / 可评分自动组数 | observation group |
| 原文准确率 | exact match；另报字符错误率 `CER=(S+D+I)/N` | item和字符 |
| 字段准确率 | 正确结构化字段数 / 标准答案中可评分字段数 | field、field type和item type |
| 复合项准确率 | 组合边界及有序子要求均正确的复合项数 / 标准答案复合项数 | composite item |
| 气泡覆盖率 | 已生成气泡的应气泡项目数 / 标准答案应气泡项目数 | item和page |
| 气泡关联准确率 | 指向正确正式项目和来源的气泡数 / 自动气泡总数 | balloon |
| 自动编号正确率 | 编号及稳定顺序均符合冻结规则的气泡数 / 自动气泡总数 | balloon和document |
| 最终人工干预率 | 从raw automatic到reviewed result发生净语义变化的项目数 / reviewed item总数 | item和document |

人工修改同时报告 `affected_item_count`、`operation_count`、`affected_field_count`、`net_added_items`、`net_removed_items` 和审核耗时。操作日志用于解释过程，但修改量以两个不可变结果之间的结构化diff为准，不按点击次数代替。

### 9.3 Dataset Governance

- 当前4份：第7天主链路开发、调试和硬E2E对象。
- 2026-07-21新增批次实际包含11份：9份vector回归候选和2份scanned输入路由样例。
- 9份vector只有在质量人员提供标准答案后才进入可计分固定回归集；2份scanned不进入当前正式准确率计算。
- 从新增候选中完成6～9份有代表性、带标准答案的首批固定回归：P0结束到P1前完成，不阻塞第7天。
- 后续扩展到10～20份固定回归。
- 5～10份不可见PDF：正式盲测候选，P1冻结基线后使用。

没有质量人员确认标准答案的PDF只能用于稳定性、性能和兼容性测试，不能计算准确率。

覆盖矩阵考虑单页/多页、简单/密集、vector/hybrid、图幅、尺寸、公差、孔、螺纹、组合项、GD&T、基准、粗糙度、焊接、技术要求、旋转文字、重复数值和多视图。

当前4份和开发期间查看过的文件不能成为正式盲测。

### 9.4 Threshold Freeze

本spec固定指标、公式、错误严重级别和正式一致性硬门槛，不凭经验写死全部自动识别数字。

P1流程：

1. 建立固定回归基线；
2. 质量部门核对标准答案；
3. 形成版本化acceptance threshold set；
4. 冻结代码、规则、Provider、模型、Prompt、Schema、模板和字体；
5. 使用不可见盲测集；
6. 盲测后不得降低门槛；修改冻结内容视为新一轮验收。

## Section 10 — Revised Delivery Scope and Normative Implementation Authority

本节是实际实施范围的唯一Owner。Section 1～9和本文件前述长期契约不得扩张本节P0。

### 10.1 P0 — Seven-day Vertical Slice

#### Runtime

- 一个FastAPI、一个Celery Worker、一个React前端、PostgreSQL、Redis和共享本地FileStorage。
- API与Worker共享同一存储目录；采用临时文件、hash校验和原子重命名，保存文件引用和基础元数据。
- 处理前检查共享存储、Redis/Celery和已配置Provider；导出前检查受控模板和气泡字体。
- 简单操作人记录。
- 单项目单编辑人。
- PostgreSQL version乐观锁和基础锁超时。
- 简化处理状态和错误状态。
- 同一逻辑后台任务的重复投递不得重复创建正式结果；不建设完整stage/attempt治理。

#### PDF and Recognition

- 支持当前范围内的vector和hybrid PDF。
- 多页PDF。
- PyMuPDF原生文字、坐标和方向优先。
- 腾讯OCR补充缺失区域。
- qwen3-vl-plus处理局部候选并输出严格JSON。
- 保存span/line级原生文字、页码、bbox、方向、页面分类和渲染转换参数；字符级信息只按需要展开。
- 支持普通尺寸、对称和上下偏差、直径/孔、螺纹、半径、角度、数量、深度、贯穿、多行组合和可执行技术要求。
- 复杂GD&T、粗糙度、焊接和跨视图重复只要求原文、坐标、类型大类和人工确认。
- 基础coverage检查保证明确疑似工程标注不被静默丢弃；允许ambiguous进入人工审核。

#### Candidate Review

- 保存原始候选、当前候选、简化修改日志和基本来源关系。
- 保留、排除、修改原文和核心字段；复杂类型的核心字段仅为 `raw_text / coordinates / coarse_type / requires_confirmation`。
- 人工新增遗漏项。
- 修改balloon_required。
- 简单合并和拆分。
- requires_confirmation处理。
- 不建设通用血缘引擎和复杂差异界面。

#### Balloons

- 自动连续建议编号。
- 审核后正式连续编号。
- 默认从1开始且不留缺号；无气泡通用要求不占编号。
- 基础确定性位置建议。
- manual_required。
- 拖动、删除、重建、调整顺序和重新编号。
- 图纸与表格双向定位。
- 自动布局不理想不得阻塞人工闭环。

#### Review UI

- 页面切换、缩放和平移。
- 候选、来源和气泡显示。
- 左图右表联动。
- 核心表单审核。
- 保存review working copy。
- 确认并冻结reviewed result。

#### Export

- 一份受控xlsx模板。
- 固定字段映射。
- 当前样例数量和图幅范围内的受控容量。
- 带气泡PDF。
- 全部页面嵌入Excel。
- openpyxl重新打开校验。
- PDF、Excel和编号一致性校验。
- 简化manifest。
- PDF、Excel和manifest三个产物均生成并通过校验后才标记成功。

#### Minimum Result Layers

- raw automatic result。
- review working copy。
- reviewed result。
- 正式PDF、Excel和简化manifest。
- 必要Provider请求/响应引用、错误记录、操作摘要和调用统计。

#### P0 Hard Acceptance

当前4份真实PDF（实际PDF页面尺寸为A3/A4；文件名中的A0/A1/A2不作为物理页面尺寸依据）必须：

- 可以上传并处理；
- 可以生成候选检验项；
- 可以人工修正；
- 可以生成和调整气泡；
- 可以导出固定SIP Excel和带气泡PDF；
- 最终气泡、表格和Excel保持一致；
- 失败不静默产生正式成功状态。

新增批次、带标准答案回归集、准确率门槛和正式盲测均不阻塞第7天。

### 10.2 P1 — Immediate Hardening

- 完整candidate version和合并拆分血缘。
- 字段级来源、置信度、editor/reviewer确认。
- 通用reference context和candidate relation。
- 完整stage run、artifact、current pointer和依赖失效。
- Provider attempt差异和历史可视化。
- 可信代理身份、基础RBAC、完整租约和管理员接管。
- export run发布指针、多产物治理和LibreOffice自动烟雾测试。
- 正式修订、回滚和发布历史。
- 版本化重点尺寸、颜色、检测方法和角色规则。
- 历史SIP相似推荐。
- artifact清理和完整离线评测。
- 从新增9份vector候选中完成6～9份标准答案回归，并逐步扩展至10～20份。
- 基线定标、门槛冻结和正式盲测准备。

### 10.3 P2 — Productionization

- 完整SSO、生产RBAC、四眼审核和审计平台。
- 多模板注册和验证。
- 纯扫描PDF正式支持。
- 标准公差规则库。
- 完整GD&T、焊接和粗糙度语义。
- 高质量全局气泡布局。
- 正式盲测治理平台。
- 生产级资源隔离、监控、告警、备份和灾备。
- 独立服务器迁移。
- 真实需求出现后的多人细粒度协作。

## Risks and Mitigations

| Risk | Impact | P0 Mitigation |
| --- | --- | --- |
| PDF旋转和坐标转换错误 | 气泡错位、OCR区域错误 | 固定CropBox坐标合同、矩阵测试、当前4份逐页核对 |
| OCR与原生文本冲突 | 原文或分组错误 | 原生与OCR独立保存、冲突进入人工确认 |
| LLM JSON或工程语义不稳定 | 字段错误、复合项错误 | 局部截图、严格Schema、确定性校验、人工确认 |
| 密集图纸候选噪声 | 审核成本上升 | 区域规则、数字弱候选、可复查自动排除 |
| 自动气泡布局不理想 | 遮挡或重叠 | manual_required和人工拖动，不追求P0全局最优 |
| Excel模板容量或嵌图问题 | 导出失败 | 固定模板、受控容量、当前4份实际A3/A4 PDF页面资格验证 |
| PDF、Excel或manifest部分成功 | 错误发布 | 同一reviewed result、staging、三个产物都通过后才标记成功 |
| API限流或暂不可用 | 自动处理失败 | 缓存、有限重试、保留已有结果、明确错误 |
| P0被长期治理扩张 | 七天主链路延期 | Section 10为唯一实施Owner，writing-plans必须逐项映射P0 |

## Self-review Record

写入后的自审结论：

1. 文档没有未决内容、占位符或缺少Owner的模糊承诺。
2. 目标明确为从原始工程PDF识别检验要求并新生成气泡，没有误写成OCR已有气泡编号。
3. 检验项选择规则明确为长期可配置、P0默认全部明确标注优先召回、正式结果人工确认。
4. 明确区分PyMuPDF原生解析主链路、腾讯OCR局部补充和qwen3-vl-plus局部语义复核。
5. 已定义建议/正式编号、基础布局、`manual_required`、人工拖动、重建、重排和后端正式绘制。
6. 已定义固定SIP模板、当前样例容量、带气泡PDF、全部页面嵌图和跨产物一致性验收。
7. 未承诺任意图纸、100%自动准确、无人审核、完整复杂工程语义或生产认证。
8. 新增回归PDF、数字准确率门槛和正式盲测明确不阻塞第7天。
9. 复杂GD&T、粗糙度、焊接、跨视图重复在P0只要求原文、坐标、类型大类和人工确认。
10. candidate血缘、完整artifact治理、生产身份、正式发布平台和规则管理后台均留在P1/P2。
11. Section 10是七天实施范围的唯一Owner；Section 1～9中的长期实体不能被writing-plans自动展开成P0功能。
12. P0每项均直接服务于“识别—审核—气泡—Excel/PDF”纵向闭环，能够独立形成后续实施计划。

## Design Approval and Next Gate

本设计已通过逐节brainstorming确认。写入后必须先由用户审核本spec。

在用户明确批准书面spec之前：

- 不调用 `writing-plans`；
- 不写实现计划；
- 不创建业务代码；
- 不搭建运行环境。

用户批准书面spec后，下一步唯一允许的skill是 `superpowers:writing-plans`。该计划必须以Section 10的P0为唯一七天范围，不得将P1/P2治理能力重新加入P0。
