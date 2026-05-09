# ETF Text2SQL v3 技术规格

> 状态：草案
> 目标：用 Text-to-Query AST 替代 v1 query plan，在保持 v1 回归稳定的基础上，分阶段扩展搜索、筛选、对比、base 扩展字段和报告展开能力。

## 1. 核心原则

本项目最高架构标准：

> 我明确我的基本标准，我要实现的是语义输入并查询，不是通过预封装函数执行，要的是 text2sql 查询。

该标准高于任何阶段性实现便利、兼容兜底或验收捷径。v3 的成功路径必须是自然语言语义输入生成受限 AST，经过 validator、compiler 后执行 Mongo 查询；不得通过预封装业务函数、intent if/else 模板、固定字段拼装器或 deterministic fallback 执行后计为 Text2SQL 成功。

v3 不让 LLM 生成可执行 SQL / PyMongo 字符串。

本规格中的 Text2SQL 指自然语言到结构化查询的转换，不要求输出 SQL 字符串。由于目标执行层是 MongoDB，v3 的“SQL”形态是受限 AST：LLM 的主要产物必须是查询结构（`select`、`from`、`where`、`order_by`、`limit`、`answer_fields`），而不是函数名、业务分支名或最终答案。

目标链路：

```text
自然语言
  -> routing_result + recognized_query_mode 分类
  -> 实体、period、条件、报告期证据提取
  -> 必要时名称反查
  -> LLM 生成受限 AST
  -> 本地归一和校验
  -> AST 编译为 Mongo 查询
  -> SSH 远端只读执行
  -> 本地 formatter 输出
```

LLM 只负责生成 AST。执行、校验、格式化、拒绝策略全部由本地确定性代码完成。

`recognized_query_mode` 不承载 `unsupported/clarify`；`UnsupportedQuery` 和 `ClarificationRequired` 通过 `routing_result.type` 表达。

Hard 层定义不可变协议；Strategy 层定义当前版本默认值；Test 层只用于验收和回归，不代表生产问法全集。生产路由允许同义归一与 paraphrase，coverage matrix 不作为唯一路由依据。

PM 文档里的业务桶是覆盖分组，不是运行时函数分发入口。v3 仍然是 text-to-AST 系统：`query_mode` 负责路由，`intent` 负责语义模板，`field_profile` / `answer_fields` 负责字段展示约束，最终都必须落到同一条 AST -> Mongo 编译链路。

判断一项实现是否仍属于 Text2SQL，以以下标准为准：

- LLM 输出查询结构，而不是直接输出答案。
- `query_mode` / `intent` 只约束 AST 形态，不触发预封装业务函数。
- 所有可执行查询都经过统一 AST validator 和 Mongo compiler。
- v3.2 strict pass 中，用户请求的字段、条件、排序、sub-intent、period 字段和 limit 必须来自 LLM Draft AST；`llm_draft_evidence`、Registry、catalog 和本地归一规则只能提供证据、约束、值归一和安全校验，不能补造语义查询。
- 若实现变成 `if intent == ...` 后直接调用固定业务函数并绕过 AST/compiler，则不符合 v3 Text2SQL 主线。

### 1.1 Scope Of Satisfaction [Hard]

本规格中的“满足需求”只在当前版本开放范围内成立：

1. 对 `etf-query-test-questions.md` 中属于当前阶段开放范围的问题，系统应按阶段门禁达到目标准确率。
2. 对当前阶段未开放但已规划的问题，系统必须返回 `UnsupportedQuery` 或阶段说明，不得伪造结果。
3. 对明确排除的问题，包括实时行情、实时交易指标、技术分析、投资建议、个股分析，系统必须返回 `DeniedQuery`；交易指标数据库快照值本身不在此排除项内。
4. 对字段矩阵未覆盖、远端验证未通过、名称歧义或条件不足的问题，系统必须走 `UnsupportedQuery` 或 `ClarificationRequired`，不得静默降级为不相关字段的部分回答。
5. 本规格不承诺覆盖所有 ETF 自然语言问题；生产泛化通过 paraphrase set、template fuzz set、日志回流和 registry 扩展逐步提升。

## 2. 非目标

v3 不支持：

- 执行 LLM 生成的 SQL / PyMongo 代码
- 通过 intent dispatch 直接调用预封装业务函数并绕过 AST/compiler
- 数据库写入、更新、删除
- OR 条件暴露给 AST
- 跨集合 join
- 实时行情、实时交易指标、技术分析、投资建议、个股分析
- LLM 自由总结、投资判断、字段外推

v3.2 不以”字段选择器”作为最终 Text2SQL 形态。除 deny / clarify / unsupported 外，v3.2 covered executable capabilities，包括 v3.0/v3.1 已覆盖可执行问题和 v3.2 新增可执行能力，都必须产出完整 AST Draft，并经过 validator 和 compiler。profile 只能限制字段、集合、操作符、gate 和 formatter 边界，不能替代查询结构生成。运行时必须输出 `ast_generation_mode`，区分 `deterministic_legacy` 与 `llm_ast_draft`，不得把 legacy deterministic 路径计入 LLM Text2SQL 成果。

## 3. 分阶段范围

### v3.0 AST 基座

- 只支持 `tb_ths_etf_base`
- 保留 v1 的实体抽取、period 解析、名称反查
- AST 最终落到 `fundcode eq`
- 保持 v1 已解决 13 条全部通过
- formatter 保持 v1 单句回答 shape

### v3.1 搜索 / 筛选 / 排序 / 对比

- 搜索：名称、指数名、指数代码
- 筛选：投资类型、上市地点、规模、费率、收益率等
- 排序：规模、收益率、费率、排名等
- 对比：generic compare 默认 base 集合固定 8 列；v3.2 field-specific compare 以用户显式维度为准
- 派生对比通过 orchestrator 两步执行
- 增加 Normalization Enhancement：period paraphrase set 与受限 period 归一 fallback
- v3.1 起，`single` 仍是单只 ETF 的 query_mode，但它不是“任意字段自由选择”的函数入口；single 的 AST 仍受 canonical intent / field_profile 约束

### v3.2 Text2SQL 架构补强 + Base 扩展字段

v3.2 是 Text2SQL 架构补强版本，核心变化是 LLM 首次在严格约束下生成完整受限 AST 草案，而不只是字段选择。此前 v3.0/v3.1 的 AST 主要由硬编码规则生成；v3.2 起，新增 single profile 和 `composite_single` 必须让 LLM 在 Registry 约束内生成 AST Draft，本地 validator 只能校验、归一、补齐 identity/context/display-only 字段和执行安全约束后再进入 compiler，不得静默生成用户请求的语义查询结构。

**架构补强（v3.2 基础设施）：**

- 最小 Executable Capability Registry：替代散落常量，作为 intent / from / field_profile / gate 的唯一来源
- `generation_context` 生成：由 Registry、`llm_draft_evidence`、operator/field catalog 裁剪生成，进入 LLM prompt
- LLM 受限 AST 生成：LLM 生成完整 AST Draft（`intent`、`sub_intents`、`from`、`select`、`where`、`order_by`、`limit`、`output_style`、`answer_fields`、`report_period`、`expand`），不得生成可执行 SQL / PyMongo 或最终答案
- AST validator：校验 LLM 输出，补齐 identity/context/display-only baseline，执行本地值归一和安全约束，拒绝越界字段、操作符、gate、阶段冲突和缺失的用户请求语义
- gate 机制：`always | verification_passed | blocked`，远端验证脚本 + gate 状态文件
- 同 fundcode 多 single profile 窄合并（见 Section 15 新增规则）

### v3.2 定位：Covered Capability LLM AST Draft Migration

v3.2 的目标是把 v3.0 / v3.1 已覆盖并验收通过的 executable questions 全部迁移到 LLM full AST Draft 路径，同时新增 v3.2 base 扩展能力。

v3.2 passing path 必须是：

```text
generation_context -> LLM full AST Draft -> validator -> compiler -> formatter
```

deterministic_legacy 只能作为 golden baseline、差异审计和失败诊断，不得作为 v3.2 covered question 的通过路径。

v3.2 不接受“旧问题 legacy 能答 + 新问题 LLM Draft 能答”作为通过标准。v3.2 通过标准是：旧 covered executable questions 和 v3.2 新增 executable questions 都必须通过 `llm_ast_draft` passing path。

#### v3.2 Strict Pass Semantic Provenance [Hard]

v3.2 strict pass 的核心不变量：

> `validated_ast` 中任何用户请求的语义结构，都必须能追溯到 `llm_draft_ast`。validator、compiler、orchestrator、formatter、catalog、Registry 只能约束、归一、审计和物理编译，不得生成语义查询。

语义结构包括：

- `select` 中的用户请求字段
- `where.field` / `where.op` / 组合条件
- `order_by`
- `sub_intents`
- period-specific fields，例如 `ths_yeild_1y_fund`、`ths_yeild_std_fund`
- 用户请求的 `limit`
- composite child query 的字段、条件、排序和 limit

允许 validator 增加：

- identity/context/display-only 字段，例如 `fundcode`、简称、必要标签字段
- catalog 归一后的实体值，例如唯一名称解析出的 fundcode
- value normalization 结果，例如日期、金额、百分比的标准值
- 非语义执行上限，例如系统安全 cap，但必须与用户请求的 `limit` 分开记录
- Registry 明确声明的 display/context 字段，例如 `display_context_for_period_range`；这类字段只能用于展示辅助 metadata，不得作为用户语义字段

字段是否属于 identity/context/display-only 必须以 Registry 的 `semantic_role` 为准，不能由 validator、formatter 或 profile baseline 临时解释。

禁止 strict pass 中出现：

- validator 根据 baseline/profile 补齐用户请求的 semantic field
- validator 或 compiler 改写 `where.field`、`where.op`、`order_by` 后仍计为成功
- orchestrator 为 child AST 注入 field/op/order 模板
- formatter 通过固定字段模板补出未查询的语义答案
- catalog 或 evidence builder 直接决定最终 field/op，而 LLM 只填值
- `provenance_diff.validator_additions_by_kind.semantic` 非空

每个 strict-pass executable case 必须输出 `draft_ast -> validated_ast -> compiled_query` provenance diff。若 diff 中出现 semantic addition、semantic field/op/order override 或 missing requested semantic repair，则该用例不得计入 v3.2 Text2SQL 成功。

`provenance_diff` 最小 schema：

```json
{
  "draft_semantics": {},
  "validated_semantics": {},
  "compiler_expansions": [],
  "validator_additions_by_kind": {
    "identity": [],
    "context": [],
    "display": [],
    "semantic": []
  },
  "semantic_additions": [],
  "semantic_overrides": [],
  "strict_pass": true
}
```

规则：

- `validator_additions_by_kind.semantic` 非空时，`strict_pass=false`。
- `semantic_additions` 或 `semantic_overrides` 非空时，`strict_pass=false`。
- `compiler_expansions` 只能记录安全物理展开，不得记录新增业务语义。
- `display_context_for_period_range` 必须记录在 `validator_additions_by_kind.display` 或 context/display metadata 中，不得进入 `semantic_additions`。

v3.2 交付范围：

- LLM full AST Draft generator
- `generation_context` 构造
- field-level capability registry
- AST Draft validator
- Draft AST -> Validated AST value normalization
- validator defaults 记录
- gate 机制
- `ast_generation_mode` 分桶统计
- v3.0/v3.1 covered executable questions 的 LLM AST Draft migration
- v3.2 新增 single profiles 的 LLM AST Draft
- v3.2 filter 新字段的 LLM AST Draft
- `composite_single` 的 LLM AST Draft

#### v3.2 AST 生成模式迁移状态

v3.2 不声称未开放能力已经迁移到 LLM Text2SQL，但所有 v3.0/v3.1 covered executable questions 和 v3.2 新增 executable questions 必须走 LLM full AST Draft。每次查询必须输出 `ast_generation_mode`，测试报告必须按该字段分开统计。

| 范围 | v3.2 执行方式 | `ast_generation_mode` |
| --- | --- | --- |
| v3.0 baseline single intents | LLM full AST Draft | `llm_ast_draft` |
| v3.1 search | LLM full AST Draft | `llm_ast_draft` |
| v3.1 filter | LLM full AST Draft | `llm_ast_draft` |
| v3.1 compare | LLM full AST Draft | `llm_ast_draft` |
| v3.1 covered composite | 每个 child query 都走 LLM full AST Draft | `llm_ast_draft` |
| v3.2 `basic_info_extended` | LLM full AST Draft | `llm_ast_draft` |
| v3.2 `investment_profile` | LLM full AST Draft | `llm_ast_draft` |
| v3.2 filter 新字段 | LLM full AST Draft | `llm_ast_draft` |
| v3.2 `composite_single` | LLM full AST Draft | `llm_ast_draft` |
| v3.3 `manager_detail` | LLM full AST Draft；数组不可用时返回 `data_not_available` | `llm_ast_draft` |

`llm_ast_draft` 路径不得在 LLM Draft 生成失败或 validator 失败后静默 fallback 到 `deterministic_legacy` 并标记成功。失败时只能返回 validation failure / `UnsupportedQuery`，或明确输出 `ast_generation_mode=llm_ast_draft_failed`；任何 deterministic fallback 都必须在响应与测试报告中显式标记。

### deterministic_legacy 定义与限制

`deterministic_legacy` 指由本地规则、intent dispatch、预封装 AST builder 或固定模板生成 AST 的路径。

包括但不限于：

- `build_v3_ast(intent, entities)`
- `build_v3_1_ast(query_mode, entity_hints, question)`
- `_build_search_ast`
- `_build_filter_ast`
- `_build_compare_ast`
- `_select_fields`
- `_answer_fields`
- deterministic period parser / fallback helper
- 本地规则生成 `field/op/value` where 条件

限制：

- `deterministic_legacy` 在 v3.2 中只允许用于 golden AST / answer shape 对照、migration diff audit、debug fallback、emergency fallback 输出。
- emergency fallback 输出必须标记 `ast_generation_mode=llm_ast_draft_failed`。
- `deterministic_legacy` 不得用于 v3.2 covered question passing path。
- `deterministic_legacy` 不得计入 v3.2 Text2SQL 成功率统计。
- `deterministic_legacy` 不得用于新增能力实现。
- `deterministic_legacy` 不得作为已迁移 intent 的正常运行路径。
- 任何 v3.0/v3.1 covered question 在 v3.2 中如果 `ast_generation_mode=deterministic_legacy`，则该用例 v3.2 验收失败。

**Base 扩展字段（v3.2 新增 3 个 profile）：**

- `basic_info_extended`：成立日期、上市地点、业绩比较基准、申赎状态、联接基金
- `investment_profile`：投资目标、范围、理念、策略、风险特征（长文本组）
- `manager_detail`：基金经理任职起始日、任期、任职年化回报、管理规模等结构化详情

单位净值、净值增长率等基础净值字段已在 v3.0 `fund_scale` 相关能力中开放；v3.2 不重复定义净值历史或时间序列比较能力。

v3.2 起，`basic_info` 保持 v3.0 回归基线 4 字段不变，不因 v3.2 自动扩展。

`subscription_redemption` 和 `linked_fund` 合并入 `basic_info_extended` 而非独立 profile——它们本质是单只 ETF 的属性列，拆分 profile 会导致合理组合问法（”申赎状态和联接基金”）被跨 profile 规则错误拒绝。

`investment_profile` 独立保留，因为它是长文本组，formatter 规则和字段语义不同。

`manager_detail` 独立保留，因为它需要展开 `ths_manager` 数组并按任职起始日形成时间线；`rank_num` 只作为数组排序或展示稳定性字段，不承载任职时间语义。

v3.1 已允许 `ths_fund_listed_exchange_fund` 作为 `filter` 条件和 list 辅助字段，用于”上交所 / 深交所 / 沪市 / 深市”筛选；v3.2 的新增点是让”510300 在哪里上市”这类单只问法进入 `basic_info_extended`。在 v3.1 中，成立日期、业绩比较基准、申赎状态、联接基金和投资画像字段不进入 single `selection_context`，相关单只问法不得降级为不相关字段的部分回答。

### v3.3 报告展开

v3.3 报告能力进入 PM 问题集收口范围。report query 仍必须走：

```text
generation_context -> LLM full AST Draft -> validator -> compiler -> formatter
```

规则：

- `report_industry`、`report_concept`、`report_holding` 为 report 数组能力，必须生成 `select + expand`
- `institution_holding`、`report_style`、`report_nav_change` 已由新版数据字典确认为 year report scalar，进入 v3.3 executable；字段结构未知的新增 report intent 才属于 planned blocked
- 已确认为 scalar 的 report intent 走普通 `select`，不得生成 `expand`
- 用户指定报告期时，child LLM AST Draft 必须生成 `report_period={"mode":"specified", ...}`
- 用户未指定报告期时，child LLM AST Draft 必须显式生成 `report_period={"mode":"latest"}`
- orchestrator 不得静默补齐 `report_period`
- report 数据源不存在对应口径或字段缺失时，返回 `UnsupportedQuery(data_not_available)`

### v3.3 时间序列语义

真实 DB 中 `[{value,btime}]` 结构不是普通标量。用户问题里的“最新 / 指定日期 / 最近两期变化”属于 AST 语义层，不能只交给 compiler 当物理细节处理。

规则：

- LLM AST Draft 必须通过 `timeseries_semantics` 表达时间序列字段的语义。
- 多个时间序列字段必须按字段分别声明，不能共享一个“整行最新 btime”。
- 用户未显式说时间且 LLM 完全未输出 `timeseries_semantics` 时，validator 可对所有被选中的时间序列字段补默认 `latest`，并记录 `validator_applied_default`；这不计为 semantic addition。
- LLM 已输出部分 `timeseries_semantics` 但遗漏其他时间序列字段时，validator 补齐属于 `semantic_repair`，strict pass 失败。
- 用户显式指定日期或“最近两期 / 有没有变化”时，LLM 必须输出对应模式；validator 不得补成 strict pass。
- formatter 展示时间序列字段时必须包含 as-of 时间。

`generation_context` / `validator_expectations` 必须包含 `expected_timeseries_modes`，由 evidence builder 从用户原文解析：

```json
[
  {"field": "ths_fund_scale_fund", "expected_mode": "latest", "evidence": "最新"},
  {"field": "ths_fund_shares_fund", "expected_mode": "latest_two", "evidence": "最近有变化"}
]
```

### 3.4 PM Coverage Buckets -> Runtime Profiles [Reference Only]

PM `etf-query-test-questions.md` 的“意图”列是业务覆盖桶，不是运行时 AST intent 输入。它用于组织测试、验收和需求沟通，不直接驱动函数分发。

| PM bucket | v3 query_mode | v3 canonical intent / profile | 说明 |
| --- | --- | --- | --- |
| 基本信息 | single | `basic_info` / `basic_info_extended` / `tracking_index` / `fee` / `manager` / `fee_and_manager` | 单只 ETF 标量字段查询；`basic_info` 保持 v3.0 回归基线，v3.2 扩展问法走 `basic_info_extended`（含成立日期、上市地点、业绩比较基准、申赎状态、联接基金） |
| 收益率与排名 | single | `performance` | 同一语义模板下按 period 选择字段 |
| 规模净值份额 | single | `fund_scale` | 规模、总市值、单位净值、份额、净值增长率统一归入单只查询模板 |
| 持仓信息 | report | `report_industry` / `report_concept` / `report_holding` / `institution_holding` / `report_style` / `report_nav_change` | report 标量走 select；report 数组走 select + expand |
| 基金经理 | single | `manager` / `manager_detail` | `manager` 只回答当前经理；`manager_detail` 展开 `ths_manager` 时间线 |
| 分红 | single | `dividend` | 累计分红总额与次数 |
| 搜索 ETF | search | `search` | 只改变查询模式，不调用预封装函数 |
| 条件筛选 | filter | `filter` | 通过 AST where/order_by 表达筛选条件 |
| 多只对比 | compare | `compare` | 固定对比模板，不走业务函数 |
| 复合意图 | composite | orchestrator 外层 | 组合多个 AST，不是单一 intent |
| 交易指标 | single | `trading_metric` | v3.3 base 交易时间序列快照字段可执行；实时/盘中行情仍 deny |
| 边界异常 | deny/unsupported | `DeniedQuery` / `UnsupportedQuery` | 按前置识别和阶段白名单处理 |

PM bucket 只定义“该问句属于哪个覆盖组”，不定义“调用哪个预封装函数”。运行时唯一执行路径仍是 AST 生成、校验、编译与执行。

#### PM 映射与运行时约束

- `canonical intent` 是 `field_profile` 的标识符，不是独立函数入口。
- 同一个 `query_mode=single` 下，不同 intent 的差异只体现在字段子集、baseline answer_fields、默认格式/排序规则。
- AST 生成、校验、编译链路完全相同，不因为 PM bucket 改变执行路径。
- 以上 PM 映射是全集覆盖映射，不是当前阶段可执行清单；能否执行只取决于 Section 3.5 Executable Capability Registry。

阶段 intent 白名单：

| 阶段 | allowed intents | execution mode scope | blocked intents |
| --- | --- | --- | --- |
| v3.0 | basic_info, fund_scale, tracking_index, performance, fee, manager, fee_and_manager, dividend | deterministic legacy | 其余全部 |
| v3.1 | v3.0 + search, filter, compare | deterministic legacy | report_*, basic_info_extended, manager_detail, investment_profile |
| v3.2.0 | v3.1 + basic_info_extended, investment_profile, composite_single | v3.0/v3.1 covered executable capabilities 与 v3.2 新增 executable capabilities 全部走 `llm_ast_draft` | report_*, manager_detail |
| v3.3 executable | v3.2.0 + 结构已确认的 manager_detail / report_* / trading_metric / composite | 全部走 `llm_ast_draft` | planned blocked 能力 |
| v3.3 planned blocked | 业务上属于 v3.3 但结构或口径仍为 `tbc` 的 report_* / 同类均值口径相关新增能力 | 不进入 AST；返回 `UnsupportedQuery(blocked_by_verification)` | 待远端验证 |

阶段白名单是 Executable Capability Registry 的阶段视图；运行时可用能力以 Section 3.5 Registry 为唯一真源。未在当前阶段白名单中的 intent 不进入 `intent_candidates`，不进入 AST。

v3.3 阶段必须区分 executable 与 planned blocked。`executable` 表示结构已确认并进入 LLM AST Draft 路径；`planned blocked` 表示业务范围内要收口，但结构或口径未确认，返回 `UnsupportedQuery(blocked_by_verification)`，不进入 AST。已开放能力若远端数据缺失或数组结构不可用，返回 `UnsupportedQuery(data_not_available)`，不得回退到不相关 profile。

**Blocked intent 回退规则：** 当最佳匹配 intent 不在当前阶段白名单时，按以下优先级回退。回退分为 same-mode fallback 和 non-AST fallback。

| blocked intent | fallback type | 回退行为 | 说明 |
| --- | --- | --- | --- |
| `basic_info_extended` | non-AST | `UnsupportedQuery` | v3.1 阶段不回答成立日期、业绩比较基准等单只扩展问法；v3.2 开放后按 profile 执行 |
| `manager_detail` | executable | `UnsupportedQuery(data_not_available)` | 经理时间线依赖 `ths_manager` 数组；数组不可用或无法形成时间线时返回 `data_not_available` |
| `investment_profile` | non-AST | `UnsupportedQuery` | v1 无对应能力，不生成 AST |
| `report_industry` | executable | `UnsupportedQuery(data_not_available)` | report 数据口径不存在或数组不可用时返回 `data_not_available` |
| `report_concept` | executable | `UnsupportedQuery(data_not_available)` | report 数据口径不存在或数组不可用时返回 `data_not_available` |
| `report_holding` | executable | `UnsupportedQuery(data_not_available)` | report 数据口径不存在或数组不可用时返回 `data_not_available` |
| `institution_holding` | executable | `UnsupportedQuery(data_not_available)` | report 标量口径不存在时返回 `data_not_available` |

same-mode fallback 只缩小能力范围（少返回字段），不改变 `recognized_query_mode`。report / manager_detail 的 data_not_available 不属于 fallback，不进入 AST、不进入 compiler。

### manager_detail Rule

`manager_detail` 直接进入 v3.3 executable Registry。

规则：

- `manager` 只回答当前基金经理，使用 `ths_fund_manager_current_fund`
- `manager_detail` 回答任职时间线、任期、任职年化回报、管理规模，使用 `ths_manager` 数组展开
- `rank_num` 只表示数组排序或展示稳定性，不表示第一任、最新任或现任
- 新版数据字典对 `rank_num` 同时出现“第一任”和“当前经理”两种描述，语义自相矛盾；spec 不采纳 `rank_num` 作为时间线或现任判断依据
- 时间线排序必须优先使用 `ths_service_sd_fund`
- formatter 标注“现任”前，必须确认 `ths_fund_manager_current_fund` 与 `ths_manager[].ths_name_fund` 一致；不一致时只展示时间线，不标注现任
- 若 `ths_manager` 数组不可用或无法形成时间线，返回 `UnsupportedQuery(data_not_available)`
- `manager_detail` 不再回退到 `manager`

### 3.5 Executable Capability Registry [Hard]

运行时唯一可执行能力来源为 Executable Capability Registry。Section 3 阶段白名单、Section 4 Query Classification Matrix、Section 14 Capability Matrix 都是 Registry 的不同视图，不得作为独立运行时来源。PM Coverage Buckets 仅用于测试覆盖说明，不参与 Registry 生成。

Registry 每一行必须至少包含：

```json
{
  "phase": "v3.1",
  "query_mode": "single",
  "intent": "performance",
  "from": "tb_ths_etf_base",
  "output_style": "summary",
  "field_profile": "performance",
  "selectable_fields": ["fundcode", "ths_yeild_1y_fund"],
  "filterable_fields": [],
  "sortable_fields": [],
  "semantic_roles": {
    "fundcode": "identity",
    "ths_yeild_1y_fund": "semantic"
  },
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"}
  ],
  "gate": "always"
}
```

规则：

- `intent_candidates`、`from_candidates`、`selection_context` 必须全部由 Registry 生成。
- v3.2 LLM AST Draft 所需的 `generation_context` 必须由 Registry + `llm_draft_evidence` + 本地 operator/normalization catalog 生成。
- Section 3 是 Registry 的阶段视图。
- Section 4 是 Registry 的路由视图。
- Section 14 是 Registry 的字段能力视图。
- Section 3.4 PM Coverage Buckets 是测试覆盖视图，不是运行时视图。
- 若文档表之间冲突，以 Registry 为准。
- Registry 的 `gate` 允许值为 `always | verification_passed | blocked`。
- Registry 的 `semantic_role` 是字段级语义角色唯一真源；允许值为 `identity | context | display | semantic`。
- 未满足当前 `phase` 或 `gate` 的能力不得进入 LLM prompt。
- v3.2 runtime 的 intent allowlist、selection_context、gate 判断只从 Registry 读取；Section 4 / Section 14 是文档视图，不作为 runtime 来源。
- Registry 加载失败时启动失败，不提供服务。
- Section 4 / Section 14 与 Registry 冲突时，runtime 以 Registry 为准；文档视图应在下次 spec 更新时修正。

### v3.2 Registry 最小实现范围

v3.2 Registry 是 Section 22 中 derived views 的子集。v3.2 只要求 Registry 生成：

1. Phase + gate 过滤后的 intent allowlist
2. 每个 intent 的 `selection_context`（`field_profile`、`selectable_fields`、`allowed_formats`、`semantic_roles`、`baseline_answer_fields`）
3. 每个 intent 的 `from` 集合、`output_style`
4. 每个 intent 的 AST 生成约束：`where_constraints`、`operator_catalog`、`sortable_fields`、`limit_policy`

以下 derived views 不在 v3.2 范围，延后到 v3.3：

- 字段能力矩阵的全量生成（Section 14 仍手动维护）
- Query Classification Matrix 的全量生成（Section 4 仍手动维护）
- PM coverage bucket 映射的自动派生
- deny intent 关键词/模式表的自动派生

v3.2 Registry 的物理形式为 `etf_agent/registry.py` 中的 Python 数据结构或独立 JSON/YAML 文件，不要求数据库存储。

gate 状态来源：

- `always`：硬编码
- `verification_passed`：由远端验证脚本产出 gate 状态文件，Registry 加载时读取
- `blocked`：默认值，验证通过前保持

gate 状态文件规则：

- gate 状态文件缺失：所有 `verification_passed` 能力视为 `blocked`。
- 单个 gate key 缺失：该 key 视为 `blocked`。
- gate 状态文件格式错误：启动失败，不静默降级。
- gate 文件加载成功但能力为 `blocked` 时，该能力不进入 LLM prompt、不进入 `intent_candidates`、不进入 AST；validator 收到包含 blocked 字段或 intent 的 AST 时直接拒绝。
- dry-run 可以使用 mock gate，但输出中必须标记 `dry_run_gate=true`。

### Field-Level Capability Schema

v3.2 validator 不得依赖散落的 if/else 判断字段能力。Registry 必须提供字段级能力定义。

### Field-Level Operator Gate Schema

字段是否可筛选必须精确到 operator + gate。`selectable=true` 不代表字段可筛选。

字段级 schema：

```json
{
  "field": "ths_fund_establishment_date_fund",
  "profile": "basic_info_extended | filter_list",
  "label": "成立日期",
  "type": "date",
  "format": "date",
  "semantic_role": "semantic",
  "selectable": true,
  "sortable": true,
  "filter_operators": {
    "eq": {"gate": "verification_passed", "normalizer": "date"},
    "gte": {"gate": "verification_passed", "normalizer": "date"},
    "lte": {"gate": "verification_passed", "normalizer": "date"},
    "between": {"gate": "verification_passed", "normalizer": "date"}
  }
}
```

无筛选能力：

```json
"filter_operators": {}
```

`ths_etf_to_code_fund` 示例：

```json
{
  "field": "ths_etf_to_code_fund",
  "profile": "basic_info_extended | filter_list",
  "label": "联接基金代码",
  "type": "nullable_ref",
  "format": "plain",
  "semantic_role": "semantic",
  "selectable": true,
  "sortable": false,
  "filter_operators": {
    "eq": {"gate": "verification_passed", "normalizer": "string"},
    "not_null": {"gate": "verification_passed", "normalizer": "null_semantics"},
    "is_null_or_empty": {"gate": "verification_passed", "normalizer": "null_semantics"}
  }
}
```

首批字段类型：

| type | normalizer | allowed operators |
| --- | --- | --- |
| `identity` | `identity` | `eq`, `in` |
| `plain` | `string` | `eq` |
| `text` | `text_contains` | `contains`（仅 search mode `__search_text__`） |
| `filterable_text` | `text_contains` | `contains`（filter mode 字段级，需 Registry 显式标记） |
| `amount` | `amount` | `eq`, `gt`, `gte`, `lt`, `lte` |
| `percent` | `percent` | `eq`, `gt`, `gte`, `lt`, `lte` |
| `date` | `date` | `eq`, `gte`, `lte`, `between` |
| `nullable_ref` | `null_semantics` | `eq`, `not_null`, `is_null_or_empty` |
| `long_text` | `none` | none |

字段级 `semantic_role`：

| semantic_role | 含义 | 是否允许 validator 自动补齐并计入 strict pass |
| --- | --- | --- |
| `identity` | 查询身份字段，例如 `fundcode` | 是 |
| `context` | 解释身份或稳定展示上下文的字段，例如简称 | 是 |
| `display` | 非用户请求语义的展示辅助字段 | 是 |
| `semantic` | 用户问题可直接请求的业务回答字段、筛选字段、排序字段或展开字段 | 否；必须来自 LLM Draft，否则 strict pass 失败 |

最低字段角色规则：

- `fundcode` 必须是 `identity`。
- `ths_fund_extended_inner_short_name_fund` 必须是 `context`。
- 规模、费率、收益、排名、经理、成立日期、申赎、联接、投资目标、report 字段、trading_metric 字段等业务回答字段必须是 `semantic`。

规则：

- `selection_context.selectable_fields` 从当前 profile 的 `selectable=true` 派生。
- `selection_context.semantic_roles` 从当前 profile 的字段级 `semantic_role` 派生，是 validator baseline 补齐的唯一判断依据。
- `where_constraints.field_operators[field]` 只从当前 profile 中 gate 通过的 `filter_operators` 派生。
- `generation_context.sortable_fields` 从当前 profile 的 `sortable=true` 且 gate 通过的字段派生。
- `eq` 不因字段 selectable 自动开放。
- 只有 Registry 明确列出 `filter_operators.eq`，且 gate 通过时，`eq` 才进入 `where_constraints.field_operators`。
- `text` 类型的 `contains` 仅限 search mode 的 `__search_text__` 虚拟字段。filter mode 中若某字段需开放 `contains`，必须标记为 `filterable_text` 类型并在 Registry 中显式定义 `filter_operators.contains` 及 gate。
- `not_null` / `is_null_or_empty` 必须有独立 gate。
- gate 未通过的 operator 不进入 LLM prompt，不进入 `where_constraints.field_operators[field]`。
- validator 收到 blocked operator 必须拒绝，返回 `blocked_by_verification`。
- 字段能力不是全局能力，必须绑定 profile；`filter_list` 的 operator 不代表 single profile 可使用相同 operator。
- Capability Matrix 不得再用单一 `filterable_eq` 暗示所有筛选语义均已开放。
- validator 必须使用字段级 `type`、operator gate、normalizer 校验 field / operator / value 三元组。
- validator 自动补齐只允许 `semantic_role in {identity, context, display}`；若 `baseline_answer_fields` 包含 `semantic` 字段，该字段仍必须来自 LLM Draft，否则 `strict_pass=false`。
- 字段级 schema 是运行时唯一字段能力来源；Section 14 Capability Matrix 只作为派生视图。

### v3.2 Covered Migration Scope

v3.2 必须迁移以下 v3.0/v3.1 covered capabilities。

v3.0 single:

- `basic_info`
- `fund_scale`
- `tracking_index`
- `performance`
- `fee`
- `manager`
- `fee_and_manager`
- `dividend`

v3.1:

- `search`
- `filter`
- `compare`
- covered composite:
  - filter -> compare
  - search/filter -> single detail
  - filter -> single detail

report_*、交易指标、manager_detail、未开放多段复合在 v3.2 仍不属于 covered executable scope；它们在 v3.3 进入可执行范围，缺少数据口径时返回 `UnsupportedQuery(data_not_available)`。

### v3.2 Implementation Sequence Dependencies

以下是实施依赖，不是验收拆分。v3.2.0 发布前必须完成全部 v3.0/v3.1 covered executable migration。

Dependency graph:

1. Runtime infrastructure
   - full AST generator
   - `generation_context` builder
   - field-level Registry
   - Draft -> Validated AST normalizer
   - validator default / baseline recording
   - `ast_generation_mode` output
2. Evidence infrastructure
   - filter evidence builder
   - period evidence builder
   - search evidence builder
   - compare entity evidence builder
3. Low-risk single migration
   - `basic_info`
   - `tracking_index`
   - `fee`
   - `manager`
   - `fee_and_manager`
   - `dividend`
4. `fund_scale` migration
5. `search` migration
6. `compare` migration
7. `filter` migration
8. `performance` migration
9. covered composite migration
10. v3.2 additions

Partial completion rule:

- Steps 1-2 are hard blockers for all `llm_ast_draft` migration.
- Steps 3-8 can be developed and tested independently.
- v3.2.0 cannot be released until all v3.0/v3.1 covered executable questions pass via `llm_ast_draft`.
- If a later step is blocked, earlier completed steps may remain merged behind feature flags, but release status remains incomplete.
- No completed step may fallback to deterministic legacy and count as passed.
- `manager_detail` is part of the v3.3 executable scope and does not block v3.2 smoke.

#### v3.3 Report Migration

目标：将 report Text2SQL 收口到可执行范围。

迁移到 `llm_ast_draft`：

- `report_industry`
- `report_concept`
- `report_holding`
- `institution_holding`

约束：

- report_* 进入 prompt 时必须经过 Registry gate 过滤。
- LLM 输出 report AST Draft。
- validator 校验 `report_period` / `expand` / scalar/report array fields。
- compiler 机械编译 report query。

### Covered Capability Implementation Constraint

从 v3.2 开始，不仅新增能力不得通过新增 deterministic AST builder、intent if/else 分支或预封装业务函数实现，v3.0/v3.1 covered capabilities 也不得继续以 deterministic builder 作为 passing path。

允许保留 legacy 函数，但只能用于 golden baseline / diff audit / debug fallback。

禁止新增：

- `_build_<intent>_ast`
- `_select_fields` 中的新 intent 分支
- `_answer_fields` 中的新 intent 分支
- 基于 intent 直接生成 fixed where/order/limit 的本地函数
- 绕过 AST Draft validator 的 formatter 或 compiler 逻辑

v3.2 covered executable capabilities 和新增能力必须通过：

```text
Registry capability
-> generation_context
-> LLM AST Draft
-> validator
-> compiler
-> formatter
```

例外：

- deny / unsupported / clarify 不生成 AST。
- deterministic_legacy 维护性修复允许修改现有 legacy 代码，但不得扩大 legacy 范围，不得作为 v3.2 covered question passing path。
- orchestrator composite 步骤编排不受此约束限制；但每个 child AST 必须走对应的 `llm_ast_draft` generation mode。

## 4. Query Classification [Hard]

`recognized_query_mode` 是前置识别结果，不由 LLM 输出，也不属于 AST 字段。

### Routing Result 与 Query Mode

`recognized_query_mode` 只表示 query mode 或 deny route，不表示 unsupported / clarify。

允许值：

```text
single | search | filter | compare | report | deny | null
```

语义：

- `single/search/filter/compare/report` 是 executable query modes。
- `deny` 是 non-executable recognized route，命中后返回 `DeniedQuery`。
- `unsupported/clarify` 不属于 `recognized_query_mode`。
- `UnsupportedQuery` / `ClarificationRequired` 时，`recognized_query_mode=null`。

`routing_result.type` 允许值：

```text
ExecutableQuery | DeniedQuery | UnsupportedQuery | ClarificationRequired
```

规则：

- capability-aware routing 必须先做硬拒绝，再做 capability candidate detection，再做实时/盘中语义判断，最后才做 capability_status / gate 决策。
- `ExecutableQuery` 只有在 `capability_status=executable`、对应 gate passed、validator 接受 draft、compiler 产出安全 query 之后才算成立；`blocked_by_verification` 和 `data_not_available` 不进入 strict pass numerator。
- `DeniedQuery` 不生成 AST，不进入 compiler，不访问远端。
- `UnsupportedQuery` / `ClarificationRequired` 不生成 AST，不进入 compiler，不访问远端。
- 测试断言 non-AST 结果时，应以 `routing_result.type` 为准，不得伪造 `recognized_query_mode=unsupported/clarify`。

`composite` 不是 AST query_mode，只属于 orchestrator 外层结构。子 AST 的 `recognized_query_mode` 只能使用：

```text
single | search | filter | compare | report
```

集合白名单：

```text
tb_ths_etf_base
tb_ths_etf_report_quarter
tb_ths_etf_report_year
```

Query Classification Matrix：

本表是 Registry 的路由视图；每阶段仅开放 Registry 当前 phase 与 gate 允许的 intent。未被 Registry 放行的 intent 不进入 `intent_candidates`，也不进入 AST。

| recognized_query_mode | intent | output_style | from_candidates | first_enabled_phase | gate |
| --- | --- | --- | --- | --- | --- |
| single | basic_info | summary | tb_ths_etf_base | v3.0 | always |
| single | fund_scale | summary | tb_ths_etf_base | v3.0 | always |
| single | tracking_index | summary | tb_ths_etf_base | v3.0 | always |
| single | performance | summary | tb_ths_etf_base | v3.0 | always |
| single | fee | summary | tb_ths_etf_base | v3.0 | always |
| single | manager | summary | tb_ths_etf_base | v3.0 | always |
| single | fee_and_manager | summary | tb_ths_etf_base | v3.0 | always |
| single | dividend | summary | tb_ths_etf_base | v3.0 | always |
| single | basic_info_extended | summary | tb_ths_etf_base | v3.2 | always |
| single | manager_detail | summary | tb_ths_etf_base | v3.3 | always |
| single | investment_profile | summary | tb_ths_etf_base | v3.2 | always |
| single | composite_single | summary | tb_ths_etf_base | v3.2 | always（父 intent gate；子 intent 逐一按各自 gate 过滤，任一子 intent gate blocked 时不进入该子 intent 候选） |
| search | search | list | tb_ths_etf_base | v3.1 | always |
| filter | filter | list | tb_ths_etf_base | v3.1 | always |
| compare | compare | compare | tb_ths_etf_base | v3.1 | always |
| report | report_industry | report_list | tb_ths_etf_report_quarter \| tb_ths_etf_report_year | v3.3 | always |
| report | report_concept | report_list | tb_ths_etf_report_quarter | v3.3 | always |
| report | report_holding | report_list | tb_ths_etf_report_year | v3.3 | always |
| report | institution_holding | summary | tb_ths_etf_report_year | v3.3 | always |
| report | report_style | summary | tb_ths_etf_report_year | v3.3 | always |
| report | report_nav_change | summary | tb_ths_etf_report_year | v3.3 | always |

`first_enabled_phase` 和 `gate` 只是 Registry 的镜像字段；`gate` 固定枚举为 `always | verification_passed | blocked`。PM bucket 不是这张矩阵的输入源，只是覆盖映射层。

规则：

- Intent Recognition 是执行路由的唯一权威来源；LLM AST 只能补全查询结构，不能改变 `recognized_query_mode`、扩大 intent/from 候选范围，不能绕过 deny/clarify。
- `intent_candidates` 进入 LLM prompt 前，必须先经过 Registry 过滤后的当前阶段白名单和 gate 过滤。
- Query Classification Matrix 冲突直接失败，不执行。
- intent alias 只允许本地归一。
- `UnsupportedQuery` 是 non-AST routing result，不存在可进入 compiler 的 unsupported AST。
- 表内 `gate` 仅为 Registry gate 的镜像字段；枚举固定为 `always | verification_passed | blocked`，不在表内表达自然语言条件。
- `selection_context` 不是 Intent Recognition 的输出，而是 Registry 裁剪后的 LLM generation input。
- 在 `llm_ast_draft` 路径中，LLM 必须生成 where / order_by / limit 的 AST Draft，validator 根据 `llm_draft_evidence` 和本地归一规则校验、覆盖或拒绝。`deterministic_legacy` 只能用于 golden/debug/emergency fallback。

LLM 生成 AST 时必须接收前置识别结果作为约束上下文：

```text
recognized_query_mode
intent_candidates
from_candidates
llm_draft_evidence
selection_context
generation_context
```

LLM 只能在 `intent_candidates` 和 `from_candidates` 内选择；`selection_context.selectable_fields`、`generation_context.where_constraints.field_operators` 和 `generation_context.sortable_fields` 决定可生成的字段与条件范围，LLM 不得越界。

### Runtime Output Schema

运行时结果必须包含以下审计字段：

```json
{
  "question": "...",
  "answer": "...",
  "routing_evidence": null,
  "routing_result": {
    "type": "ExecutableQuery | DeniedQuery | UnsupportedQuery | ClarificationRequired",
    "reason": null
  },
  "recognized_query_mode": "single | search | filter | compare | report | deny | null",
  "intent_candidates": [],
  "blocked_intent_candidates": [],
  "capability_id": "v3.2.single.basic_info_extended",
  "capability_status": "executable | blocked_by_verification | planned | denied",
  "gate_status": "passed | blocked | not_applicable",
  "capability_status_reason": null,
  "ast_generation_mode": "deterministic_legacy | llm_ast_draft | llm_ast_draft_failed | null",
  "llm_ast_draft_raw": null,
  "draft_ast": null,
  "v3_ast": null,
  "validated_ast": null,
  "provenance_diff": null,
  "operation": null,
  "query_plan": null,
  "mongo_params": null,
  "pipeline": null,
  "computed_fields": null,
  "mongo_params_hash": null,
  "row_count": null,
  "has_more": null,
  "limit_applied": null,
  "maxTimeMS": null,
  "remote_query_allowed": false,
  "prompt_template_version": null,
  "prompt_hash": null,
  "generation_context_hash": null,
  "registry_hash": null,
  "ast_schema_version": "v3_2_base_ast | v3_3_report_ast | null",
  "model_id": null,
  "retry_count": 0,
  "remote_query_executed": false,
  "remote_error": null
}
```

Non-AST 结果规则：

```json
{
  "v3_ast": null,
  "validated_ast": null,
  "operation": null,
  "query_plan": null,
  "mongo_params": null,
  "pipeline": null,
  "computed_fields": null,
  "remote_query_allowed": false
}
```

规则：

- `DeniedQuery`、`UnsupportedQuery`、`ClarificationRequired` 的 `ast_generation_mode=null`。
- `ExecutableQuery` 必须输出 `ast_generation_mode`。
- `routing_result.type=ExecutableQuery` 时，`capability_status` 必须是 `executable`，且 `gate_status` 必须是 `passed` 或 `not_applicable`；否则 strict audit 失败。
- Non-AST 结果也必须输出 capability audit 字段：verification/gate 拦截用 `capability_status=blocked_by_verification`、未开放计划能力用 `planned`、deny route 用 `denied`。
- `search` / `filter` / `compare` 路由必须输出非空 `routing_evidence`；其他路由可以为 `null`。
- `llm_ast_draft` 路径必须保留 `llm_ast_draft_raw`，可截断。
- `validated_ast` 是 compiler 唯一可接受的 AST 输入。
- `provenance_diff` 必须记录 `draft_ast -> validated_ast -> compiled_query` 的语义增删改；strict pass 中若出现 semantic addition / override / repair，则不得计为 v3.2 成功。
- 除 period normalizer 等本规格明确规定阈值的局部归一器外，`confidence` 只用于审计和候选排序，不得作为 validator pass/fail 的通用软门槛。
- `llm_ast_draft_failed`、`blocked_by_verification`、`data_not_available` 必须在测试报告里单独统计，不能算 question-level Text2SQL 成果。
- `ast_schema_version` 只允许取 `v3_2_base_ast` 或 `v3_3_report_ast` 两层，不得按单能力碎拆；版本依据 AST 形状，不依据 PM bucket。

### Non-AST Routing Results

以下结果不生成 AST，不进入 compiler。

| 结果 | 触发条件 | 输出形态 | 是否调用 LLM | 是否进入 compiler |
| --- | --- | --- | --- | --- |
| `DeniedQuery` | `recognized_query_mode=deny` | 固定拒绝文本 | 否 | 否 |
| `UnsupportedQuery` | 无法归类到任何 query_mode | 固定不支持提示 | 否 | 否 |
| `ClarificationRequired` | 已归类但条件不足、名称多候选歧义 | 候选列表或澄清提示 | 否 | 否 |

`UnsupportedQuery` 表示无法归类；`ClarificationRequired` 表示可归类但条件不足。

#### UnsupportedQuery

```json
{
  "type": "UnsupportedQuery",
  "reason": "unclassified | blocked_by_phase | blocked_by_verification | data_not_available | unsupported_domain",
  "message": "当前版本暂不支持该查询。",
  "suggested_action": "try_supported_query | wait_for_later_phase | none"
}
```

#### Non-AST Decision Tree

1. 命中 deny -> `DeniedQuery`
2. 无法归类到任何 query_mode -> `UnsupportedQuery`
3. 可归类但存在名称歧义、候选过多、条件不足 -> `ClarificationRequired`
4. 已归类且条件足够 -> 生成 AST

search 去泛词后无有效关键词时，若仍可归类为 search，则返回 `ClarificationRequired`；若无法归类，则返回 `UnsupportedQuery`。

#### ClarificationRequired

当问题已归类到某个路由方向，但条件不足、候选过多或名称歧义无法唯一执行时，返回 `ClarificationRequired`。

```json
{
  "type": "ClarificationRequired",
  "reason": "name_ambiguity | insufficient_conditions | too_many_candidates",
  "question": "需要用户补充的具体问题",
  "options": [
    {
      "id": "cand_1",
      "kind": "fund_candidate | report_period | filter_value | free_text",
      "label": "沪深300ETF",
      "value": {"fundcode": "510300", "thscode": "510300.SH"},
      "fundcode": "510300",
      "thscode": "510300.SH",
      "reason": "名称匹配到多只候选之一"
    }
  ],
  "has_more": false,
  "state_id": "uuid",
  "next_action": "retry | choose_candidate | stop"
}
```

规则：

- 不进入 AST
- 不进入 compiler
- 不调用远端 Mongo
- `options` 最多返回 5 个
- `options` 按候选质量降序排列：`kind=fund_candidate` 可使用预构建本地 catalog snapshot 的规模字段排序，`kind=report_period` 按 `year_num desc, type_num desc`，`kind=filter_value` 和 `kind=free_text` 保持原始顺序
- 候选总数超过 5 个时，`has_more=true`；未超过时，`has_more=false`
- 响应只展示质量最高的 5 个，但 `state_id` 对应状态必须保留完整候选集或提供 pagination cursor；不得丢弃后续澄清可能选择的候选
- `ClarificationRequired` 不调用 live remote Mongo；若候选排序依赖数据，必须来自本地 catalog snapshot，并在 runtime audit 中记录 `catalog_snapshot_used`
- `has_more` 是顶层布尔字段，表示是否还有未展示的候选
- `options[].id` 用于后续回传
- `options[].kind` 标识候选类型，允许 `fund_candidate`、`report_period`、`filter_value`、`free_text`
- `options[].value` 保存机器可回绑的结构化值
- `options[].fundcode` / `thscode` 仅在 `kind=fund_candidate` 时优先用于直接回绑
- `label` 只负责展示，不作为唯一键
- `state_id` 用于后续补充输入关联

### Catalog And Clarification Contract [Hard]

`FundNameCatalog` 和 `IndexNameCatalog` 是 evidence source，不是 query builder。

规则：

- catalog 输出必须包含 `source`、`snapshot_id`、`snapshot_hash`、`generated_at`、`ttl_seconds`、`stale_policy`、`match_algorithm`、`confidence`。
- catalog unavailable、stale、multi-match、low-confidence 都必须有明确 failure mode：`ClarificationRequired`、`UnsupportedQuery` 或使用 stale snapshot 并显式审计。
- fund name unique match 只允许作为 entity value evidence；LLM Draft 仍必须输出 `fundcode eq` 或对应 query structure。
- index name substring multi-match 必须返回 `ClarificationRequired(reason=value_ambiguity)`，除非存在 exact/alias match 或唯一高置信候选。
- clarification follow-up 必须重新经过 routing、generation_context、LLM AST Draft、validator 和 gate checks；不得把用户选择直接拼进 legacy query。
- `state_id` 必须保留完整候选集或 pagination cursor；只展示 top 5 不等于丢弃其余候选。
- non-AST clarification path 不得访问 live remote Mongo；排序和候选质量只能来自本地 snapshot。
- runtime audit 必须记录 `catalog_snapshot_used`、candidate count、displayed count、truncated/paginated 状态。

## 5. Intent Recognition [Hard + Strategy]

前置识别输出：

```text
recognized_query_mode
intent_candidates
from_candidates
routing_signals
llm_draft_evidence
composite_hint
deny_reason
```

### Routing Signals 与 LLM Draft Evidence

v3.2 中，本地前置解析允许产生两类中间结果，但它们用途不同，不得混用。

#### routing_signals

`routing_signals` 供前置路由和 legacy golden/debug 使用，可以包含结构化判断结果：

```json
{
  "has_filter_signal": true,
  "filter_signal_kinds": ["amount_condition", "date_condition"],
  "legacy_filters": [
    {"field": "ths_fund_scale_fund", "op": "gt", "value": 1000000000}
  ],
  "legacy_sort_hint": {"field": "ths_fund_scale_fund", "direction": "desc"},
  "legacy_limit_hint": 10
}
```

规则：

- `routing_signals` 不得进入 LLM prompt。
- `legacy_filters`、`legacy_sort_hint`、`legacy_limit_hint` 只允许用于 deterministic legacy golden/debug，不得作为 v3.2 passing path。
- `routing_signals` 可以帮助决定 `recognized_query_mode` 和是否进入 `llm_ast_draft`。
- v3.2 strict pass 必须包含 poisoned legacy tests：向 `legacy_filters`、`legacy_sort_hint`、`legacy_limit_hint` 注入错误值时，`compiled_query` 不得变化。

#### llm_draft_evidence

`llm_ast_draft` prompt 只能接收 `llm_draft_evidence`：

```json
{
  "raw_evidence": [],
  "candidate_fields": [],
  "value_candidates": [],
  "deterministic_entities": {}
}
```

规则：

- `llm_draft_evidence` 不得包含完成版 `field/op/value` where。
- `llm_draft_evidence` 不得包含完成版 `sort_hint`。
- `llm_draft_evidence` 不得包含完成版 `limit`。
- LLM 必须基于 evidence 自行输出 `where` / `order_by` / `limit`。
- `candidate_fields`、catalog match、period parse 只能作为 evidence，不是字段白名单或最终答案。
- validator 可使用 normalizer / catalog 对 LLM Draft 做值级校验或值级覆盖；不得使用 `routing_signals` 补造 AST 语义结构。
- 若 LLM Draft 缺少用户请求的 semantic field/op/order/sub_intent/period field，validator 必须拒绝或返回 clarify/unsupported，不能通过 baseline 或 profile 自动补齐后计为 strict pass。

#### Routing Evidence Schema [Hard]

所有 `search` / `filter` / `compare` 路由必须输出可审计的 `routing_evidence`。它是审计信息，不是执行计划，也不能代替 AST Draft。

```json
{
  "routing_evidence": {
    "entity_cardinality": "none | single | multiple | ambiguous",
    "user_goal": "candidate_list | filtered_list | ranked_list | comparison | single_attribute",
    "semantic_constraints": [
      {
        "raw_text": "红利主题",
        "constraint_type": "theme | index | name_fragment | field_filter | sort | limit",
        "candidate_query_mode": "search",
        "candidate_fields": [
          "__search_text__",
          "ths_fund_extended_inner_short_name_fund",
          "ths_name_of_tracking_index_fund"
        ]
      }
    ],
    "why_not_single": "no unique fund identity; user asks for ETF candidates"
  }
}
```

规则：

- `routing_evidence` 必须解释为什么不是 `single`，或者为什么不是 `search/filter/compare`。
- `entity_cardinality` 必须至少区分 `single` 与 `multiple/ambiguous`。
- `semantic_constraints` 只能记录可追溯证据，不得写成完成版 `where` / `order_by` / `limit`。
- `candidate_query_mode` 可以是候选值，但 runtime 仍必须通过 Registry + LLM AST Draft + validator 决定最终执行结构。
- `routing_evidence` 不能由关键词单独决定；关键词、embedding、LLM routing、field retrieval 只能作为组合证据。
- 若系统选择 `single`，必须能说明唯一实体来源；若系统选择 `search/filter/compare`，必须能说明目标是候选集合而非单实体。

#### Implicit Collection Retrieval [Hard]

当用户没有提供唯一 fundcode 或唯一基金名称，而是在描述主题、指数、行业、名称片段、标的指数片段或基金集合特征，并期望返回多个 ETF 候选时，系统应优先进入 `search` / `filter` / `compare`，不得回退到 `single/basic_info`。

判断依据至少包括：

- `entity_cardinality`：用户是否提供唯一 ETF 身份。
- `user_goal`：用户目标是否是候选列表、筛选列表、排序列表或集合比较。
- `semantic_constraint`：用户表达的是主题、指数、行业、基金类型、上市地点、费率、规模、收益率、成立日期等可检索约束。
- `field_mapping`：约束是否可映射到 fuzzy searchable fields、filterable fields 或 sortable fields。
- `why_not_single`：系统选择 `search/filter/compare` 时必须说明为何不是单只查询；系统选择 `single` 时必须说明唯一实体来源。

允许使用关键词、embedding、LLM classification、field retrieval 或 hybrid router，但关键词不得作为唯一依据，也不得作为硬触发词列表。runtime 必须输出 `routing_evidence` 供审计。

#### Anti-Keyword Requirement [Hard]

以下问法不得仅因为缺少显式“搜索/找”等词而回退到 `single/basic_info`：

- `我想查红利主题ETF，名字、规模、费率列出来`
- `有没有跟科创板50有关的基金`
- `名字或标的指数里有新能源的ETF给我看看`
- `医药方向的ETF有哪些`
- `围绕沪深300的ETF列几个`

这些是 semantic acceptance examples，不是 keyword trigger list。实现不得通过硬编码这些完整短语作为通过条件。

`selection_context` 结构：

```json
{
  "field_profile": "performance",
  "selectable_fields": ["fundcode", "ths_yeild_1y_fund"],
  "allowed_formats": ["plain", "percent", "amount", "number"],
  "semantic_roles": {
    "fundcode": "identity",
    "ths_yeild_1y_fund": "semantic"
  },
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"}
  ]
}
```

- `selection_context.field_profile`：运行时语义模板标识，由 `query_mode + canonical intent` 共同决定，用于约束可选字段、baseline answer_fields 和格式规则；它不属于 AST 字段，也不代表预封装业务函数
- `selection_context.selectable_fields`：当前 profile 允许的可选字段子集
- `selection_context.allowed_formats`：当前 profile 允许的展示格式集合
- `selection_context.semantic_roles`：当前 profile 字段级 `semantic_role` 真源；validator 判断 baseline 是否可补齐时只能读取该字段。
- `selection_context.baseline_answer_fields`：该 profile 的最低展示字段要求；validator 只能自动补齐 `semantic_role in {identity, context, display}` 的 baseline。若 baseline 中包含 `semantic` 字段，该字段必须出现在 LLM Draft 中，否则 strict pass 失败。

#### Entity Hint Extraction [Hard]

本地前置解析可以抽取实体、证据、候选字段和值候选，但不得在 `llm_ast_draft` 路径中直接生成最终查询结构。

### llm_draft_evidence 在不同 ast_generation_mode 下的边界

`deterministic_legacy` 可以在 golden/debug/emergency fallback 中使用结构化 `deterministic_legacy_entity_hints.filters` 生成 where，但不得作为 covered executable passing path。

`llm_ast_draft` 不得向 LLM 提供已完成的 `field/op/value` where 条件。它只能提供 evidence 与候选空间：

```json
{
  "raw_evidence": [
    {"text": "规模大于10亿", "kind": "amount_condition"},
    {"text": "2024年成立", "kind": "date_condition"}
  ],
  "candidate_fields": [
    {"field": "ths_fund_scale_fund", "evidence": "规模大于10亿"},
    {"field": "ths_fund_establishment_date_fund", "evidence": "2024年成立"}
  ],
  "value_candidates": [
    {"raw": "10亿", "normalizer": "amount"},
    {"raw": "2024年", "normalizer": "date"}
  ],
  "deterministic_entities": {
    "fundcodes": ["510300"],
    "resolved_index_name": "沪深300"
  }
}
```

规则：

- `llm_ast_draft` 的 where / order_by / limit 必须由 LLM Draft 输出。
- 本地 evidence 不得包含最终 `op`。
- validator 用 evidence 校验 LLM 生成的 where / order_by / limit 是否可追溯。
- validator 可以覆盖确定性实体值，例如 `fundcode`、已解析唯一名称、已验证 index catalog value。
- `llm_ast_draft` prompt 不得包含完成版 `filters`、`sort_hint`、`limit_hint` 或任何 `field/op/value` where 条件。
- `filters`、`sort_hint`、`limit_hint` 仅允许存在于 `routing_signals` 或 `deterministic_legacy_entity_hints` 中，用于 routing、golden baseline、debug fallback，不得作为 v3.2 passing path 的 LLM 输入。

`deterministic_entities` 只能包含已解析实体值，例如：

- `fundcodes`
- `resolved_name`
- `resolved_index_name`
- `search_keyword`
- `report_period_candidate`

`deterministic_entities` 不得包含任何 `field/op/value` 形式的 where clause。

禁止：

```json
{"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "沪深300指数"}
```

允许：

```json
{"resolved_index_name": "沪深300指数"}
```

LLM 必须自行输出 where Draft；validator 使用 `deterministic_entities` 校验或覆盖 value。

以下映射仅用于 `routing_signals`、golden/debug 和 evidence extraction，不得作为 `llm_ast_draft` prompt 中的完成版 where：

| 用户表达 | field | op | value 转换 |
| --- | --- | --- | --- |
| 规模大于10亿 | `ths_fund_scale_fund` | gt | 1000000000 |
| 费率低于0.2% | `ths_manage_fee_rate_fund` | lt | 0.2 |
| 收益率超过20% | `ths_yeild_1y_fund` | gt | 20 |
| 收益超过20% | `ths_yeild_1y_fund` | gt | 20 |
| 上市地点为上交所 | `ths_fund_listed_exchange_fund` | eq | 上交所 |

### Runtime Evidence vs Test Oracle [Hard]

- `runtime evidence` 只用于生产路由、validator 和安全编译；它必须保持 question-local 和 capability-local，不能携带完整 expected query semantics。
- `test oracle` 只用于 audit、negative-contract、mutation 和回归；它可以保存完整 expected AST / expected semantics，但不得喂给生产 validator、compiler 或 formatter。
- 生产 validator 只能看 runtime evidence，不得直接读取 test oracle 里的完整 expected query 语义。
- negative-contract 与 mutation 测试必须证明，删掉 oracle 后生产路径仍按 runtime evidence 决策，而不是回退到本地模板补语义。

比较词映射：

| 用户表达 | op |
| --- | --- |
| 大于、超过、高于、多于 | gt |
| 不低于、至少、大于等于 | gte |
| 小于、低于、少于 | lt |
| 不超过、至多、小于等于 | lte |
| 等于、为、是 | eq |

limit hint 抽取仅用于 `routing_signals` 和 `value_candidates`，不得作为完成版 `limit` 进入 LLM prompt：

| 用户表达 | limit_hint |
| --- | --- |
| 前10、前十、top10 | 10 |
| 前5、前五、top5 | 5 |
| 所有、全部 | 50 |

filter 收益率周期 evidence 规则：

- filter 中出现“收益 / 收益率 / 回报”但未指定周期时，period builder 可以产出 `value_candidates.normalized=1y`，并记录 default reason。
- LLM 仍必须输出 `order_by` / `where` / `answer_fields` Draft；validator 只能用 period evidence 校验收益率字段与用户周期语义一致。若 Draft 缺失 period-specific 收益率字段或排名字段，validation failure，不得由 validator 补齐后计为 strict pass。
- performance 意图的 period 解析与 filter 的收益率周期 evidence 规则一致。

search_keyword 抽取：

- 从用户问题中删除 Section 7 `contains` 规则中的泛词列表中的所有词，再 trim 空白。
- 例如 `有没有名字里带医药的ETF` → `医药`
- 若结果长度 < 2，退回原词再判；原词仍 < 2 时返回 `ClarificationRequired`
- search_keyword 仅用于 search 路由，不影响 filter/compare

识别优先级：

1. deny：实时行情、实时交易指标、技术分析、投资建议、个股分析。
2. compare：对比、比较、vs、和...比，且需要显式多 fundcode。
3. report：持仓、行业、概念、前十大、机构持仓、投资风格。
4. search/filter：搜索、找、筛选、前 N、最高、最低、大于、小于、分类词、哪个费率更低、哪个收益更高、哪个规模更大。
5. single：单只基金代码或可解析名称。
6. unsupported/clarify：无法归类、歧义、条件不足。

路由边界：

- “哪个费率更低 / 哪个收益更高 / 哪个规模更大”未显式多 fundcode 时归入 filter；显式多 fundcode 时归入 compare。
- “哪个好”在显式多 fundcode 场景下归入 compare，只做客观指标对比，formatter 不得给出投资推荐或胜负结论。
- “哪个更值得买 / 推荐哪个 / 能买吗 / 该不该买”归入 deny。
- “季报 + 持仓”且没有“重仓股/重仓证券/前十大”等股票语义时，归入 `report_industry`。
- “年报 + 持仓”或“前十大/重仓股/重仓证券”归入 `report_holding`。
- 多个基金代码并列是实体识别信号，不是普通关键词；显式多 fundcode 使 compare 优先于 filter。
- 若命中多个优先级类别，设置 `composite_hint=true`，保留各子意图候选。
- `"帮我找"` / `"找一下"` 等 search 触发词在以下情况不生效：已提取到 fundcode 或名称解析可唯一确定基金代码，且用户问题同时包含非 search 类 intent 触发词（如"费率""收益""基金经理"）。此时应归入 single 而非 search。无 fundcode 且无名称匹配时，search 触发词正常生效。
- 同一优先级内（priority 4 search/filter），确定性结构条件优先于纯搜索触发词。问题同时包含"找/搜索/有哪些"等搜索词和以下任一信号时，归入 filter 而非 search：
  - 数值比较：大于、小于、不低于、不超过、超过、低于
  - 排序/top：前 N、最高、最低、最大、最小、排名靠前
  - 分类枚举：股票型、债券型、混合型、货币型、上交所、深交所、沪市、深市

**触发词与 canonical seed 关系：**

- 路由种子以 Section 21（Canonical Seed List）为唯一规范来源。
- Section 5 的识别优先级和路由边界使用 Section 21 的 seed 生成 `intent_candidates`，不自行维护独立的触发词表。
- 配置文件中 deny 关键词、触发词种子、搜索泛词仅允许追加 `extra_seeds`，不得删除或覆盖 Section 21 的 `canonical_seeds`。
- `intent_candidates` 由 canonical seeds + extra_seeds 共同生成，生产问法通过 paraphrase 归一进入相同候选空间。
- 当 `intent_candidates` 包含多个值时，LLM 需结合用户原文选择最匹配项；无法判断时返回 `UnsupportedQuery` 或 `ClarificationRequired`。
- 触发词只负责生成候选，不直接绕过 Query Classification Matrix。
- 成立日期 + 范围词（2024年、2024年1月）/ 排序词（最早、最新、最近成立）/ 列举词（哪些、前 N）→ 归入 `filter`，不归入 `basic_info_extended` 或 `search`。
- 成立日期 + 单个 fundcode / 唯一名称 → 归入 `single`，走 `basic_info_extended`。
- 上市地点 / 业绩比较基准 / 申赎状态 / 联接基金 单独出现且无 fundcode 无名称时 → 归入 `filter`；有 fundcode 或唯一名称时 → 归入 `single`，走 `basic_info_extended`。
- 投资目标 / 投资范围 / 投资理念 / 投资策略 / 风险收益特征 + fundcode / 唯一名称 → 归入 `single`，走 `investment_profile`。
- 管理了多久 / 任职起始日 / 任职年化回报 / 管理规模 / 历史业绩 + fundcode / 唯一名称 → 归入 `single`，走 `manager_detail`。

v3.2 中，前置识别不直接生成最终查询。它只负责生成候选空间、路由证据和确定性实体：`routing_result`、`recognized_query_mode`、`intent_candidates`、`from_candidates`、`routing_signals`、`llm_draft_evidence`、`generation_context`。可执行查询结构必须由 LLM AST Draft + validator 形成。

## 6. AST Schema

v3.2 硬约束：除 `DeniedQuery`、`UnsupportedQuery`、`ClarificationRequired` 外，每个可执行查询都必须产生完整 AST。

`llm_ast_draft` 路径中，LLM 必须输出完整 AST Draft，包含 AST schema 定义的所有顶层字段：

- `intent`
- `sub_intents`
- `from`
- `select`
- `where`
- `order_by`
- `limit`
- `output_style`
- `answer_fields`
- `timeseries_semantics`
- `report_period`
- `expand`

缺少任一顶层字段均为 `schema_validation` failure。

validator 可以执行：

- raw value 归一
- identity/context/display-only baseline answer_fields 补齐
- 确定性实体值覆盖或校验
- 非语义 execution cap 补齐，并记录 `validator_applied_defaults`

validator 不得替 LLM 生成缺失的 query structure。用户请求的 semantic field / op / order / sub_intent / period field / limit 缺失时必须 validation failure。compiler 不得生成业务默认语义。

```json
{
  "intent": "performance",
  "sub_intents": null,
  "from": "tb_ths_etf_base",
  "select": ["fundcode", "ths_yeild_1y_fund"],
  "where": [
    {"field": "fundcode", "op": "eq", "value": "510300"}
  ],
  "order_by": null,
  "limit": 1,
  "output_style": "summary",
  "answer_fields": [
    {"field": "ths_yeild_1y_fund", "label": "近1年收益率", "format": "percent"}
  ],
  "timeseries_semantics": null,
  "report_period": null,
  "expand": null
}
```

字段语义：

| 字段 | 说明 |
| --- | --- |
| `intent` | 业务意图 |
| `sub_intents` | `composite_single` 的子 intent 列表；非 `composite_single` 时为 null |
| `from` | Mongo 集合 |
| `select` | 语义字段，不等于最终 Mongo projection |
| `where` | 条件数组，固定 AND |
| `order_by` | 单字段排序或 null |
| `limit` | 返回条数，1-50 |
| `output_style` | formatter 模板 |
| `answer_fields` | 展示字段、标签、格式 |
| `timeseries_semantics` | `[{value,btime}]` 字段的时间语义，按字段声明 |
| `report_period` | 报告期规则 |
| `expand` | 报告 array 展开规则 |

约束：

- AST 不支持 OR。
- `where` 必须是数组。
- `select` 不得被 compiler 回写污染。
- Mongo `projection` 由 compiler 另行生成。
- `intent`、`from`、`output_style` 必须符合前置 `recognized_query_mode` 的候选范围。
- `intent=composite_single` 时，`sub_intents` 必须是非空 `list[str]`；每个子 intent 必须是 Query Classification Matrix 中已注册的 `single` intent，且不得包含 search/filter/compare/report/deny。
- 非 `composite_single` AST 的 `sub_intents` 必须为 `null`。
- `where`、`order_by`、用户请求的 `limit` 必须出现在 LLM Draft 中，并能从用户原文或 `llm_draft_evidence` 解释；无法解释时校验失败。
- validator 只能增加非语义 execution cap 或 display defaults，不能增加用户未表达的 `order_by` 并作为查询语义。
- 除 compare 外，`answer_fields` 不能为空。
- `answer_fields[].field` 必须是 `select` 子集。
- AST Draft 中出现的所有 `field` 必须是 Registry canonical field。
- validator 不得把 LLM 输出的未知字段、别名字段、中文字段名改写成合法字段。
- 字段别名归一只允许发生在 pre-router / evidence extraction 阶段，用于生成 `candidate_fields`，不适用于 AST Draft 字段。
- compare 允许 generic compare 使用固定 8 列 display baseline。
- compare 若用户指定维度，LLM Draft 必须在 `select` / `answer_fields` 中体现请求字段；validator 只可补 identity/context 字段，不得把 field-specific compare 降级为固定 8 列并计为 strict pass。
- report 模式下顶层 AST `order_by` 必须为 `null`。
- report array 内部排序只允许通过 `expand.order_by` 表达；用户明确表达数组内部排序（如“占比最高”）时，LLM Draft 可生成 `expand.order_by`，validator 只能校验证据和字段合法性。

`timeseries_semantics` schema：

```json
{
  "by_field": {
    "ths_fund_scale_fund": {"mode": "latest"},
    "ths_fund_shares_fund": {"mode": "latest_two"},
    "ths_unit_nv_fund": {"mode": "specified", "btime": "2024-06-30"}
  }
}
```

规则：

- 非时间序列字段不得出现在 `timeseries_semantics.by_field`。
- 被 `select`、`where` 或 `order_by` 使用的时间序列字段必须有对应模式；若 AST Draft 完全缺失该对象，validator 只能在用户未显式表达时间时补默认 latest。
- `mode=specified` 必须包含 `btime=YYYY-MM-DD`。
- `mode=latest_two` 只用于“最近两期 / 有没有变化”类最小能力，不开放通用时间序列分析。
- 多字段查询中每个字段独立提取 latest / specified / latest_two，不得用一个字段的 `btime` 锁定其他字段。
- `latest_two` 的 compiler 结果必须包含：

```json
{
  "field": "ths_fund_shares_fund",
  "current": {"value": 10500000000, "btime": "2024-06-30"},
  "previous": {"value": 10000000000, "btime": "2024-03-31"},
  "delta": 500000000,
  "delta_pct": 5.0,
  "direction": "increase"
}
```

### Draft AST 与 Validated AST Value Schema

LLM 输出的 AST Draft 与 validator 输出的 Validated AST 使用不同 value 形态。

LLM AST Draft 中，来自用户原文的值必须保留 raw literal：

```json
{"field": "ths_fund_scale_fund", "op": "gt", "value": {"raw": "10亿"}}
```

Validated AST 中，validator 必须将可归一值转换为标准执行值，并保留 `raw_value` 供审计：

```json
{"field": "ths_fund_scale_fund", "op": "gt", "value": 1000000000, "raw_value": "10亿"}
```

日期范围：

```json
{
  "field": "ths_fund_establishment_date_fund",
  "op": "between",
  "value": {"raw": "2024年"}
}
```

Validated AST：

```json
{
  "field": "ths_fund_establishment_date_fund",
  "op": "between",
  "value": {"start": "2024-01-01", "end": "2024-12-31"},
  "raw_value": "2024年"
}
```

存在性 operator 不需要 raw value：

```json
{"field": "ths_etf_to_code_fund", "op": "not_null", "value": null}
```

compiler 只接收 Validated AST，不接收 raw-only Draft AST。

### Compiler Expansion Metadata

compiler 可以在 Registry 明确声明的场景下产出展示辅助 metadata。该 metadata 不属于 LLM semantic field，不得参与 `where` / `order_by` / `limit`，也不得覆盖查询结果字段。

`performance_period_range` 只允许用于 `performance` intent。compiler 可读取 `ths_unit_nv_fund` 的 `btime` 序列，为每个收益周期产出时间范围：

```json
{
  "performance_period_ranges": [
    {
      "period": "1y",
      "start_btime": "2025-05-08",
      "end_btime": "2026-05-07",
      "display_range": "2025-05-08 ~ 2026-05-07"
    }
  ]
}
```

provenance 必须记录：

```json
{
  "compiler_expansions": ["performance_period_range"],
  "display_context_fields": ["ths_unit_nv_fund"]
}
```

`performance_period_range` 不得重算 `ths_yeild_*` 收益率，不得补排名字段；formatter 只能渲染 compiler 返回的 `display_range`。

### AST Schema Validation Rules [Hard]

v3.2 strict pass 对 AST schema 的要求：

- JSON 解析后只允许单个顶层对象，不允许前后缀文本、注释或多对象拼接。
- 顶层对象必须包含且仅包含 schema 定义的字段；`additionalProperties=false`。
- `select`、`answer_fields`、`sub_intents`、`where`、`order_by`、`limit` 的重复项不得出现。
- `select` 中的 field 必须唯一；`answer_fields[].field` 也必须唯一。
- `where` 只允许 AND 数组，不允许嵌套 OR 结构。
- `order_by` 必须显式包含 `field` 和 `direction`，方向只允许 `asc` / `desc`。
- 非 report query 的 `report_period` 和 `expand` 必须为 `null`。
- `output_style` 必须与 Registry 的 intent/profile 级定义一致；composite 允许按 composite-policy 校验。
- `select`、`where`、`order_by`、`limit`、`answer_fields` 的语义关系必须可由 provenance diff 和 evidence 追溯。

### Where 生成与覆盖规则

| query_mode | deterministic_legacy where source | llm_ast_draft requirement | validator deterministic override |
| --- | --- | --- | --- |
| single | `deterministic_legacy_entity_hints.fundcodes[0]` -> `fundcode eq` | LLM 必须输出 `fundcode eq` Draft | validator 从 `llm_draft_evidence.deterministic_entities.fundcodes` 覆盖或校验 fundcode |
| composite_single | `deterministic_legacy_entity_hints.fundcodes[0]` -> `fundcode eq` | LLM 必须输出 `fundcode eq` Draft | validator 从 `llm_draft_evidence.deterministic_entities.fundcodes` 覆盖或校验 fundcode |
| search | legacy golden only | LLM 必须输出 `__search_text__ contains` Draft | validator 覆盖 search_keyword |
| filter | legacy golden only | LLM 必须输出完整 where Draft | validator 归一 raw value 并拒绝无证据条件 |
| compare | legacy golden only | LLM 必须输出 `fundcode in` Draft | validator 覆盖 fundcode list |
| report | `deterministic_legacy_entity_hints.fundcodes` + report period | v3.3 gate passed 后启用 | validator 覆盖或校验 fundcode；`report_period` 只能校验/归一，不得覆盖或补齐 |

规则：

- `deterministic_legacy` 只允许在 golden/debug/emergency fallback 中本地生成 where / order_by / limit，不得作为 covered executable passing path。
- `llm_ast_draft` 路径必须先由 LLM 输出 where / order_by / limit Draft。
- validator 可以覆盖确定性实体值，但不得凭空新增用户未表达的 where 条件。
- compiler 只编译 validator 输出的 Validated AST，不负责生成业务语义。

### 6.1 LLM AST Generation Framework

v3.1 定义 `selection_context` 约束框架；v3.2 起所有 covered executable capabilities 与新增 single profile、`composite_single` 正式启用 LLM 完整 AST Draft 生成。LLM 只能在 `generation_context` 约束内生成受限 AST Draft，这不是预封装函数调用，而是自然语言到查询结构的生成。

LLM 输入：

- `recognized_query_mode`
- `intent_candidates`
- `from_candidates`
- `llm_draft_evidence`：`raw_evidence`、`candidate_fields`、`value_candidates`、`deterministic_entities`
- `selection_context.field_profile`
- `selection_context.selectable_fields`
- `selection_context.baseline_answer_fields`
- `selection_context.allowed_formats`
- `generation_context.where_constraints`
- `generation_context.operator_catalog`
- `generation_context.sortable_fields`
- `generation_context.limit_policy`

`llm_ast_draft` prompt 不得包含完成版 `filters`、`sort_hint`、`limit_hint` 或任何 `field/op/value` where 条件。

`filters`、`sort_hint`、`limit_hint` 仅允许存在于 `routing_signals` 或 `deterministic_legacy_entity_hints` 中，用于 routing、golden baseline、debug fallback，不得作为 v3.2 passing path 的 LLM 输入。

Prompt 中优先提供字段级 `field_operators`，避免 LLM 从全局 `operator_catalog` 为字段选择非法 operator。`operator_catalog` 仅用于 schema 描述和 validator 内部校验；若进入 prompt，必须同时强调字段实际可用 operator 以 `where_constraints.field_operators[field]` 为准。

LLM 输出 AST Draft：

```json
{
  "intent": "basic_info_extended",
  "sub_intents": null,
  "from": "tb_ths_etf_base",
  "select": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_fund_establishment_date_fund"],
  "where": [
    {"field": "fundcode", "op": "eq", "value": "510300"}
  ],
  "order_by": null,
  "limit": 1,
  "output_style": "summary",
  "answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
    {"field": "ths_fund_establishment_date_fund", "label": "成立日期", "format": "date"}
  ],
  "report_period": null,
  "expand": null
}
```

校验规则：

1. `intent` 必须在 `intent_candidates` 中，`from` 必须在 `from_candidates` 中。
2. `select` 必须是 `selection_context.selectable_fields` 的子集。
3. `answer_fields[].field` 必须是 `select` 的子集。
4. `selection_context.baseline_answer_fields` 由 validator 自动补齐，不依赖 LLM；LLM 可以包含 baseline，但不强制。
5. `format` 必须属于 `selection_context.allowed_formats`，并匹配字段 canonical format。
6. `where` 必须只使用 `generation_context.where_constraints` 允许的字段、操作符和值来源；确定性值由本地 `llm_draft_evidence.deterministic_entities` 覆盖或校验。
7. `order_by` 必须为空或使用 `generation_context.sortable_fields` 中的字段。
8. `limit` 必须符合 `generation_context.limit_policy`，超限由 validator 截断或拒绝。
9. `select` 不得包含 report 集合字段，除非 query_mode=report 且 gate 通过。
10. 校验失败 -> 直接失败，不进入 compiler。

Selection Context 规则：

- `selection_context` 由 Registry 裁剪生成。
- LLM 不得修改 `selection_context.field_profile`。
- LLM 不得读取全量 Capability Matrix，只能读取 `selection_context.selectable_fields`。
- Validator 使用同一个 `selection_context` 校验 `select` 和 `answer_fields`。
- 字段补齐只能由 validator 根据 `baseline_answer_fields` 执行，不由 formatter 临时补齐。

### v3.2 生效范围

v3.2 起，v3.0/v3.1 covered executable capabilities 和新增 single profile（`basic_info_extended`、`investment_profile`、`composite_single`）全部通过 `generation_context + LLM AST Draft + validator` 路径生成 AST；v3.3 起 `manager_detail` 也进入同一路径。

v3.0 baseline intents（`basic_info`、`fund_scale`、`tracking_index`、`performance`、`fee`、`manager`、`fee_and_manager`、`dividend`）必须迁移到 LLM full AST Draft。validator 仍校验这些 AST，并强制补齐 identity/context/display-only baseline。LLM 不得删除、替换或重排用户请求的 semantic fields。

v3.1 的 `search`、`filter`、`compare` 和 covered composite 在 v3.2 阶段必须迁移到 LLM full AST Draft。deterministic builders 可保留为 golden baseline / diff audit / debug fallback，但不得作为 v3.2 covered question passing path。

LLM AST Draft prompt 模板：

```text
你是一个 ETF 数据查询系统。根据用户问题，在给定的能力边界内生成查询 AST 草案。

约束：
- 只能在 intent_candidates / from_candidates 内选择 intent 和 from
- 只能从 selectable_fields 中选择字段
- 可以包含 baseline_answer_fields；缺失时由 validator 只补齐 identity/context/display-only baseline
- where 只能使用 where_constraints 允许的字段、操作符和值来源
- order_by 只能使用 sortable_fields 中的字段
- limit 必须符合 limit_policy
- format 只能使用 allowed_formats 中的值
- label 使用中文，简洁准确
- 用户未明确请求的字段不要添加
- 不要生成 SQL、PyMongo、自然语言答案或解释文本

用户问题：{question}
llm_draft_evidence：{llm_draft_evidence}
generation_context：{generation_context}

请输出 JSON：
{
  "intent": "...",
  "sub_intents": null,
  "from": "...",
  "select": ["..."],
  "where": [{"field": "...", "op": "...", "value": "..."}],
  "order_by": null,
  "limit": 1,
  "output_style": "summary",
  "answer_fields": [
    {"field": "...", "label": "...", "format": "..."}
  ],
  "report_period": null,
  "expand": null
}
```

LLM 输出称为 AST Draft。Runtime 处理规则：

- AST Draft 不得直接进入 formatter 或 compiler。
- validator 根据 Registry、`generation_context`、`llm_draft_evidence`、`routing_signals` 和本地归一规则校验 AST Draft。
- validator 可以补齐 identity/context/display-only baseline、截断 limit、补齐非语义 execution cap、覆盖确定性 where 值和归一 format；不得补齐用户未表达的 order_by 作为查询语义。
- validator 必须记录 `baseline_fields_added` 和 `validator_applied_defaults`；`baseline_fields_added` 只能包含 identity/context/display-only 字段，不得补语义字段。
- validator 不得把不相关字段或未解释条件静默替换成其他查询；无法归一时返回 `UnsupportedQuery` 或 validation failure。
- 通过 validator 后的 AST 才能进入 Mongo compiler。

baseline 补齐示例：

```json
"baseline_fields_added": ["fundcode", "ths_fund_extended_inner_short_name_fund"]
```

### LLM AST Draft Failure Response

`llm_ast_draft` 路径失败时，不得静默 fallback 到 deterministic legacy。响应必须包含：

```json
{
  "question": "...",
  "answer": "当前查询未能生成安全可执行的查询结构。",
  "v3": {
    "recognized_query_mode": "filter",
    "intent": "filter",
    "ast_generation_mode": "llm_ast_draft_failed",
    "failure_stage": "llm_call | json_parse | schema_validation | validator | gate",
    "failure_reason": "...",
    "deterministic_fallback_used": false
  },
  "llm_ast_draft_raw": "...可截断...",
  "v3_ast": null,
  "query_plan": null,
  "mongo_params": null
}
```

规则：

- `llm_ast_draft_failed` 不计入成功率。
- 若因 gate blocked 失败，`failure_stage=gate`，`failure_reason=blocked_by_verification`。
- 若 LLM 输出字段、operator 或 value 无法校验，`failure_stage=validator`。
- 不得返回 Mongo params。
- 每次失败或重试都必须保留原始 `llm_ast_draft_raw`、`failure_stage`、`failure_reason` 和 `retry_index`，不得只保留最终一次结果。

validator format 校验规则：

- `answer_fields[].format` 必须属于 `selection_context.allowed_formats`。
- 若字段存在 canonical format，`answer_fields[].format` 必须匹配 canonical format。
- canonical format 是字段级固有属性，由字段语义和数据字典推导，由 validator 内置维护；不得由 LLM 或 profile 覆盖。
- 例：`ths_fund_establishment_date_fund -> date`，`ths_yeild_*_fund -> percent`，`ths_fund_scale_fund -> amount`，`ths_pur_and_redemp_status_fund -> plain`，`ths_etf_to_code_fund -> plain`，`ths_invest_*_fund -> long_text`，`ths_service_sd_fund -> date`，`ths_service_duration_annual_return_fund -> percent`，`ths_tenure_fund -> number`，`ths_rzjjzgm_fund -> amount`。

### Performance Period Handling in LLM AST Draft

`performance` 在 v3.2 中必须走 `llm_ast_draft`。period 归一可以作为 deterministic evidence 提供，但不得直接生成 select 字段或完整 AST；LLM 必须仍显式选择 Registry 允许的 period-specific fields。

LLM prompt 可接收：

```json
{
  "raw_evidence": [
    {"text": "今年", "kind": "period_expression"}
  ],
  "value_candidates": [
    {
      "raw": "今年",
      "normalized": "ytd",
      "normalizer": "period",
      "confidence": 0.98
    }
  ],
  "candidate_fields": [
    {"field": "ths_yeild_ytd_fund", "evidence": "今年"},
    {"field": "ths_yeild_rank_ytd_fund_origin", "evidence": "今年"},
    {"field": "ths_yeild_rank_ytd_etf", "evidence": "今年"}
  ]
}
```

规则：

- LLM 必须输出完整 AST Draft，包括 `select` 和 `answer_fields`。
- LLM 选择的收益率 / 排名字段必须能追溯到 period evidence。
- validator 使用 period candidate 校验 LLM 字段选择。
- 若 period normalizer `confidence >= 0.75`，validator 可覆盖或校验 period 值本身，并记录 `deterministic_overrides` / `baseline_fields_added`；`baseline_fields_added` 只限展示字段，不得在缺失 LLM Draft 语义字段时补齐核心 performance 字段。
- 若 `confidence < 0.75`，返回 `ClarificationRequired(reason=period_ambiguity)`，不得默认成 `1y`。
- `period=all` 时，LLM 必须明确输出 all-period AST 字段集合；validator 只能校验集合是否完整，并记录 `baseline_fields_added` 作为展示字段，不得生成 semantic period fields 后计为 strict pass。
- 排名字段优先选择 `_fund_origin`（展示）和 `_etf`（ETF 排名）；数字型 `_fund` 排名仅用于排序，不作为展示字段。

### 6.2 Search / Filter / Compare LLM Draft Rules (v3.2)

#### Search

v3.2 search 必须由 LLM 输出完整 AST Draft。

规则：

- `where` 使用 `__search_text__ contains`。
- validator 可以用 `llm_draft_evidence.deterministic_entities.search_keyword` 或 `value_candidates` 覆盖 value。
- compiler 只对 validated value 做 `re.escape`。
- search 仍只允许 Registry 放行的搜索字段，不允许 LLM 直接生成正则表达式或扩大 fuzzy 字段范围。

### v3.2 Search Evidence Builder

Search Evidence Builder 负责把用户原文中的搜索对象转为 `llm_draft_evidence`。它不生成 AST，也不生成最终 `where`。

输入：

```text
question
recognized_query_mode=search
field-level registry
SearchKeywordNormalizer
IndexNameCatalog
```

evidence builder 输出：

```json
{
  "raw_evidence": [
    {"text": "搜索中证500", "kind": "search_keyword", "span": [0, 6]}
  ],
  "candidate_fields": [
    {"field": "__search_text__", "evidence": "中证500", "confidence": "high"}
  ],
  "value_candidates": [
    {"raw": "中证500", "normalizer": "search_keyword", "evidence": "搜索中证500"}
  ],
  "deterministic_entities": {
    "search_keyword": "中证500",
    "resolved_index_name": null,
    "fundcodes": []
  }
}
```

规则：

- Search Evidence Builder 可以抽取或归一 `search_keyword`，但不得输出 `{"field": "__search_text__", "op": "contains", "value": ...}`。
- LLM 必须输出完整 AST Draft，并在 `where` 中使用 `__search_text__ contains`。
- validator 优先使用 `deterministic_entities.search_keyword` 覆盖 LLM value；没有确定性关键词时，才允许使用 LLM value 并要求能追溯到 `raw_evidence` / `value_candidates`。
- IndexNameCatalog 命中只进入 `resolved_index_name` 或 `value_candidates`，不得让 builder 直接生成 tracking-index where。
- search keyword 为空、只剩停用词或无法从原文追溯时，返回 `ClarificationRequired(reason=missing_search_keyword)`，不得执行空搜索。

#### Filter

v3.2 filter 必须由 LLM 输出完整 `where` / `order_by` / `limit` Draft。

规则：

- 本地只提供 `raw_evidence`、`candidate_fields`、`value_candidates`、normalizer。
- 本地不得向 LLM 提供已完成的 `field/op/value` where 条件。
- validator 负责金额、百分比、枚举、日期、排序方向归一。
- validator 必须确认 LLM 生成的条件可追溯到用户原文或本地 evidence。

#### Compare

v3.2 compare 必须由 LLM 输出完整 AST Draft。

规则：

- `where` 使用 `fundcode in`。
- validator 覆盖或校验 fundcode list。
- generic compare 默认 8 列由 validator 补齐为 display baseline；LLM 仍负责用户指定维度的 semantic fields。
- 用户指定维度不得被固定列集合吞没；若 Registry 未开放该维度，必须 clarification 或 unsupported。

### v3.2 Compare Entity Evidence Builder

Compare Entity Evidence Builder 负责把用户原文或上游 Step 1 结果中的比较对象转为 `llm_draft_evidence`。它不生成 AST，也不生成最终 `where`。

输入：

```text
question
recognized_query_mode=compare
field-level registry
fundcode resolver
optional upstream step result fundcodes
```

evidence builder 输出：

```json
{
  "raw_evidence": [
    {"text": "510300、510500和159919", "kind": "fundcode_list", "span": [2, 19]}
  ],
  "candidate_fields": [
    {"field": "fundcode", "evidence": "510300、510500和159919", "confidence": "high"}
  ],
  "value_candidates": [
    {"raw": "510300", "normalizer": "fundcode", "evidence": "510300"},
    {"raw": "510500", "normalizer": "fundcode", "evidence": "510500"},
    {"raw": "159919", "normalizer": "fundcode", "evidence": "159919"}
  ],
  "deterministic_entities": {
    "fundcodes": ["510300", "510500", "159919"]
  }
}
```

规则：

- Compare Entity Evidence Builder 可以解析 fundcode、唯一基金名称和上游 Step 1 返回的 fundcode list，但不得输出 `fundcode in` where。
- LLM 必须输出完整 AST Draft，并在 `where` 中使用 `fundcode in`。
- validator 优先使用 `deterministic_entities.fundcodes` 覆盖或校验 LLM fundcode list。
- compare 至少需要 2 个有效 fundcode；只有 1 个有效对象时返回 `ClarificationRequired(reason=compare_requires_two_entities)`，不得降级为 single。
- 部分 fundcode 无效时，validator 可保留有效 fundcode 并记录 `partial_entity_found`；若有效 fundcode 少于 2 个，则 validation failure。
- 用户维度词（如”收益率””费率””规模”）进入 `raw_evidence` / `value_candidates`；field-specific compare 中，LLM Draft 必须依据维度证据在 `select` / `answer_fields` 中选择对应语义字段。validator 确保 identity 字段（fundcode、简称）不被删除；generic compare 的 8 列 display baseline 只能作为展示补充，不得覆盖或弱化用户请求字段的 provenance。

### 6.3 Search/Filter Selection Context (v3.1+)

`search` 和 `filter` 也必须通过 `selection_context` 限制可选字段、展示字段和格式，且 selection_context 由 Registry 裁剪生成，不得由 LLM 自行扩展。

### v3.2 Filter Evidence Builder

Filter Evidence Builder 负责把用户原文中的筛选、排序、限制表达转为 `llm_draft_evidence`。它不生成 AST，也不生成最终 where。

输入：

```text
question
recognized_query_mode=filter
field-level registry
normalizer catalog
IndexNameCatalog
```

evidence builder 输出：

```json
{
  "raw_evidence": [
    {"text": "规模大于10亿", "kind": "amount_condition", "span": [2, 8]},
    {"text": "按收益率排序", "kind": "sort_condition", "span": [10, 16]}
  ],
  "candidate_fields": [
    {
      "field": "ths_fund_establishment_date_fund",
      "evidence": "2024年成立",
      "confidence": "high",
      "reason": "成立 maps to establishment date by canonical seed"
    }
  ],
  "value_candidates": [
    {"raw": "10亿", "normalizer": "amount", "evidence": "规模大于10亿"}
  ],
  "deterministic_entities": {
    "resolved_index_name": null,
    "fundcodes": []
  }
}
```

首批语义证据示例（非穷举、非触发规则）：

| 用户表达 | candidate field |
| --- | --- |
| 成立、成立日期、什么时候成立、2024年成立、最早成立、最近成立 | `ths_fund_establishment_date_fund` |
| 可申购、可赎回、可申赎、申赎状态 | `ths_pur_and_redemp_status_fund` |
| 联接基金、有联接、没有联接、ETF 联接 | `ths_etf_to_code_fund` |
| 业绩比较基准、比较基准、基准包含 | `ths_perf_comparative_benchmark_fund` |

以下表达只用于说明 candidate field evidence 的构造方式，不得作为完整短语匹配、关键词路由或最终 `field/op` 生成依据。

规则：

- v3.2 covered filter 查询全部进入 `llm_ast_draft`。
- evidence builder 只提供 `raw_evidence`、`candidate_fields`、`value_candidates`、normalizer，不决定最终 where。
- 每个 filter evidence record 必须保留 `raw_text`、`normalized_value`、`normalizer`、`confidence` 和目标 `field/op` 的可审计信息；日期、金额、百分比和枚举的归一值不得覆盖原文证据。
- LLM 可以在 `generation_context` 范围内生成混合条件。
- validator 必须确认 LLM 生成的字段可追溯到 evidence 或用户原文。
- LLM 可访问当前 Registry phase + gate 放行的所有 `where_constraints.field_operators` 和 `sortable_fields`。因此混合查询允许整体进入 LLM AST Draft，例如：

```text
规模大于10亿且2024年成立的ETF
```

LLM 可同时生成：

```json
[
  {"field": "ths_fund_scale_fund", "op": "gt", "value": {"raw": "10亿"}},
  {"field": "ths_fund_establishment_date_fund", "op": "between", "value": {"raw": "2024年"}}
]
```

validator 负责将 raw value 归一为可执行值。LLM 不得新增用户原文没有证据的筛选条件或排序条件，例如“2024年成立的 ETF”不得自行追加规模排序。

`ths_etf_to_code_fund` 的 `not_null` / `is_null_or_empty` 能力依赖远端空值形态验证。验证通过前，该字段可作为 single 展示字段；filter 中用于“有联接基金 / 没有联接基金”的条件必须保持 blocked，返回 `UnsupportedQuery(reason=blocked_by_verification)`。

#### Field Disambiguation Rule

当一个 evidence 可能对应多个字段时，Evidence Builder 必须提供候选字段，但不得替 LLM 选择最终字段。

例：“规模”默认 candidate priority：

1. `ths_fund_scale_fund`：基金规模
2. `ths_current_mv_fund`：总市值，仅当用户明确说“总市值 / 市值”时优先

规则：

- LLM 可以选择 `candidate_fields` 中任一字段。
- validator 必须检查 LLM 选择的字段是否有 evidence 支持。
- 若 LLM 选择低优先级字段且用户原文没有明确证据，validator 拒绝，返回 `validation_failed(reason=field_evidence_mismatch)`。
- 若多个字段均合理且无法消歧，返回 `ClarificationRequired(reason=field_ambiguity)`。

#### Normalized Value Override Rule

本地 catalog 可产出 normalized value，但不产出完整 where。

例如跟踪指数：

```json
{
  "raw_evidence": [{"text": "沪深300指数", "kind": "index_condition"}],
  "candidate_fields": [
    {"field": "ths_name_of_tracking_index_fund", "evidence": "沪深300指数"}
  ],
  "value_candidates": [
    {
      "raw": "沪深300",
      "normalized": "沪深300指数",
      "source": "IndexNameCatalog",
      "normalizer": "index_name"
    }
  ]
}
```

validator 规则：

- 若 LLM 输出 raw value，validator 可用 `value_candidates.normalized` 覆盖。
- 若 LLM 输出 normalized value，validator 校验一致。
- 若 LLM 输出与 catalog 候选不一致的 value，validator 拒绝。
- validator 覆盖 value 时必须记录 `deterministic_overrides`。

`search` selection_context：

```json
{
  "field_profile": "search_list",
  "selectable_fields": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "allowed_formats": ["plain", "amount", "percent"],
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
    {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
    {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"}
  ]
}
```

`filter` selection_context：

```json
{
  "field_profile": "filter_list",
  "selectable_fields": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_unit_nv_fund",
    "ths_unit_nvg_rate_fund",
    "ths_yeild_1w_fund",
    "ths_yeild_1m_fund",
    "ths_yeild_3m_fund",
    "ths_yeild_6m_fund",
    "ths_yeild_1y_fund",
    "ths_yeild_2y_fund",
    "ths_yeild_3y_fund",
    "ths_yeild_5y_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_std_fund",
    "ths_fund_establishment_date_fund",
    "ths_fund_listed_exchange_fund",
    "ths_perf_comparative_benchmark_fund",
    "ths_pur_and_redemp_status_fund",
    "ths_etf_to_code_fund"
  ],
  "allowed_formats": ["plain", "amount", "percent", "number", "date"],
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
    {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
    {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"}
  ]
}
```

上面的 `filter` selection_context 示例是 v3.2+ 的 Registry 视图。v3.1 的 `filter` selectable_fields 已包含 `ths_fund_listed_exchange_fund`，用于交易所筛选；但不包含 v3.2 扩展字段 `ths_fund_establishment_date_fund`、`ths_perf_comparative_benchmark_fund`、`ths_pur_and_redemp_status_fund`、`ths_etf_to_code_fund`，也不包含投资画像和经理详情字段。

规则：

- search 的 selectable_fields 只允许 list 固定列，不得追加收益率、成立日期、经理详情等字段。
- filter 的 selectable_fields 只能来自当前 Registry phase 的 base 字段视图，不得越过 trade/report 阶段边界。
- filter 可以在用户明确要求时追加上述 selectable_fields 中的其他字段，但不得突破 selection_context。
- validator 校验 `select` 和 `answer_fields` 时，除 `selection_context` 外，还需确认字段存在于当前 Registry phase 的 selectable_fields；跨 phase 字段拒绝。
- `search` 输出固定使用 list baseline，不允许 LLM 改列。
- `filter` 输出默认使用 list baseline；仅在用户明确要求且字段已在 selection_context 中时，才追加额外展示字段。

### 6.4 v3.2 Base Extension Selection Context

v3.2 的 base 扩展必须通过独立 `field_profile` 进入 single 查询。`basic_info` 的 v3.0 baseline 不变；“什么时候成立 / 在哪里上市 / 业绩比较基准是什么”等问法走 `basic_info_extended`，不得让 LLM 自行把这些字段全量追加到 `basic_info`。

`basic_info_extended`：

```json
{
  "field_profile": "basic_info_extended",
  "selectable_fields": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_establishment_date_fund",
    "ths_fund_listed_exchange_fund",
    "ths_perf_comparative_benchmark_fund",
    "ths_pur_and_redemp_status_fund",
    "ths_etf_to_code_fund"
  ],
  "allowed_formats": ["plain", "date"],
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"}
  ]
}
```

`basic_info_extended` 规则：

- LLM 根据用户原文选择 `selectable_fields` 中用户明确请求的字段。
- 用户未请求的扩展字段不得全量追加。
- 申赎状态和联接基金作为 `basic_info_extended` 的可选字段，LLM 按需选择，不强制展示。
- 成立日期的 `format` 为 `date`，formatter 按 `YYYY-MM-DD` 原样展示或按需格式化。
- PM 测试问句中的成立日期、上市地点、申赎状态、联接基金、业绩比较基准虽然都归入 `basic_info_extended`，但它们对应不同字段。LLM 必须根据用户原文只选择被问到的字段，例如“510300的成立日期是什么时候”只选择 `ths_fund_establishment_date_fund` 及 baseline 字段，不得把 `basic_info_extended` 的 7 个字段全量返回。
- `basic_info_extended` 不是预封装函数；它只定义字段候选空间、格式和 baseline，查询字段仍必须由自然语言到 AST Draft 的语义选择决定。

`investment_profile` 数据质量说明：

- 投资画像字段依赖远端基础表中的长文本质量；字段为空或缺失不视为查询失败。
- formatter 对空字段逐项显示 `暂无数据`，不得编造、摘要或用其他字段替代。
- v3.2 黄金集必须包含至少 1 条投资画像字段全部为空或部分为空的样例。

`investment_profile`：

```json
{
  "field_profile": "investment_profile",
  "selectable_fields": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_invest_objective_fund",
    "ths_invest_socpe_fund",
    "ths_invest_philosophy_fund",
    "ths_invest_strategy_fund",
    "ths_risk_return_characteristics_fund"
  ],
  "allowed_formats": ["plain", "long_text"],
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"}
  ]
}
```

`manager_detail`：

```json
{
  "field_profile": "manager_detail",
  "selectable_fields": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_manager_current_fund",
    "ths_fund_supervisor_fund",
    "ths_service_sd_fund",
    "ths_service_duration_annual_return_fund",
    "ths_tenure_fund",
    "ths_rzjjzgm_fund"
  ],
  "allowed_formats": ["plain", "date", "percent", "amount", "number"],
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
    {"field": "ths_fund_manager_current_fund", "label": "基金经理(现任)", "format": "plain"},
    {"field": "ths_fund_supervisor_fund", "label": "基金管理人", "format": "plain"}
  ]
}
```

`composite_single` selection_context 构造规则：

- 当多个 single profile 候选均有用户原文中的独立证据，且满足 Section 15 的同 fundcode 合并条件时，前置识别层请求 Registry 构造合并 selection_context。
- `field_profile` 固定为 `composite_single`。
- `selectable_fields` 为各子 profile `selectable_fields` 的去重并集。
- `allowed_formats` 为各子 profile `allowed_formats` 的去重并集。
- `baseline_answer_fields` 为各子 profile `baseline_answer_fields` 的去重并集。
- `where_constraints` 取各子 profile 约束的交集；同 fundcode 合并只允许 `fundcode eq`。
- `sortable_fields` 取各子 profile 的交集；v3.2 `composite_single` 默认不开放排序派生。
- `limit_policy` 固定为 single detail：`limit=1`。
- `from`、`output_style` 必须在所有子 profile 中一致，否则不得合并。
- 所有子 profile gate 必须通过；blocked profile 不进入合并候选。
- validator 使用合并后的 generation_context 校验 AST Draft。

独立证据规则：

- `composite_single` 不能只因为 embedding 相似度高或多个 intent 分数接近而触发。
- 每个子 profile 必须能在用户原文中找到对应的独立语义证据，如“投资目标”和“费率”分别对应 `investment_profile` 与 `fee`。
- “510300是什么”不得因为同时接近 `basic_info` 和 `basic_info_extended` 而触发 `composite_single`；没有扩展字段证据时只走 `basic_info`。

v3.2 部分回答规则：

- 同 fundcode 同集合多个 single profile 允许合并为一次查询（见 Section 15 新增”同 fundcode 多 single profile 合并”）。
- 跨集合、跨 query_mode 或含 report 的多意图不做隐式合并。
- `investment_profile` 不得降级为 `basic_info` 或 `basic_info_extended`。
- `basic_info_extended` 不得降级为 `basic_info`。
- `manager_detail` 不得降级为 `manager`；数组不可用时返回 `UnsupportedQuery(data_not_available)`。

## 7. Operator 规则

`op` 白名单：

```text
eq | in | contains | gt | gte | lt | lte | between | not_null | is_null_or_empty
```

`between`、`not_null`、`is_null_or_empty` 是 v3.2 AST operator，不是 Mongo 原生操作符。compiler 必须将它们展开为受控 Mongo 查询表达式。

### eq

用于精确匹配。

v3.0 只启用：

```json
{"field": "fundcode", "op": "eq", "value": "510300"}
```

### in

仅允许：

```text
field = fundcode
```

规则：

- 最多 20 个值。
- compare 可直接使用。
- filter 中的 `in` 只能由 orchestrator 注入。
- Qwen 直接生成普通 filter AST 时不允许 `in`。

### contains

AST 使用虚拟字段：

```json
{"field": "__search_text__", "op": "contains", "value": "医药"}
```

规则：

- `contains` 默认仅允许 `intent=search` 使用虚拟字段 `__search_text__`。
- LLM 负责从用户问题中提取搜索关键词填入 `value`；value 是普通字符串，最长 30
- 若 `llm_draft_evidence.deterministic_entities.search_keyword` 非空，validator 优先使用该值覆盖 AST 中 `__search_text__` 的 `value`；LLM value 仅作为无本地关键词时的补充
- 本地校验层二次清洗：去泛词（`ETF`、`基金`、`指数`、`相关`、`搜索`、`找一下`、`有没有`、`名字里带`、`名字叫`）+ trim 空白
- 清洗后长度 < 2：退回原词再判；原词仍无有效关键词时拒绝 AST，返回 `ClarificationRequired`
- compiler 内部用 `re.escape(value)` 生成 regex
- compiler 内部展开受控多字段 OR，AST 仍不支持 OR
- v3.2 filter 例外：当 Registry 明确把某个文本字段标记为 `filterable_text`，且 `field_operators[field]` 包含 `contains` 时，filter 也可以使用 `contains`。首批仅允许 `ths_perf_comparative_benchmark_fund`。
- filter 的 `contains` value 必须来自用户原文或本地归一；compiler 必须用 `re.escape` 构造受控 regex；LLM 不得输出正则表达式。

搜索字段限：

```text
ths_fund_extended_inner_short_name_fund
ths_name_of_tracking_index_fund
ths_tracking_index_code_fund
```

### between

仅用于 v3.2 LLM AST Draft 路径中已开放比较能力的字段，主要是日期字段。

```json
{"field": "ths_fund_establishment_date_fund", "op": "between", "value": {"raw": "2024年"}}
```

规则：

- validator 必须先将 raw value 归一为确定的 `[gte, lte]` 边界。
- compiler 展开为同一字段的 `gte` + `lte` AND 条件。
- raw value 无法归一时 validation failure，不进入 compiler。

### not_null / is_null_or_empty

用于表达自然语言中的存在性条件，例如“有联接基金 / 没有联接基金”。

```json
{"field": "ths_etf_to_code_fund", "op": "not_null", "value": null}
```

规则：

- 仅允许 Registry 明确标记为空值语义已验证的字段使用。
- `not_null` 编译为字段存在且不为 `null`、`""`、`[]`。
- `is_null_or_empty` 编译为字段缺失或为 `null`、`""`、`[]`。
- 字段真实空值形态未完成远端验证前，该 operator 对该字段 blocked。

## 8. Compiler Rules [Hard]

真实 Mongo projection 自动包含：

```text
select
+ where.field
+ order_by.field
+ timeseries_semantics.by_field
+ report period fields
+ expand.field
+ expand.paired_fields[]
+ display_context_fields
```

`display_context_fields` 只能来自 Registry 明确声明，例如 `performance` 的 `ths_unit_nv_fund` 用于 `performance_period_range`。formatter 或 compiler 不得临时推断新的 display context field。

formatter 只展示：

```text
answer_fields
或 expand.field + expand.paired_fields
```

辅助字段不得展示。

说明：

- `tb_ths_etf_base` 里有一批字段在真实 Mongo 中实际存成 `[{value, btime}]` 时间序列数组；这些字段必须按 `timeseries_semantics.by_field` 独立提取 `value` 与 as-of `btime`。
- `tb_ths_etf_report_quarter` / `tb_ths_etf_report_year` 里的数组字段则按 `rank_num` 展开，不做时间序列折叠。

compiler 只机械编译 Validated AST，不生成业务默认语义。

以下默认值不得在 compiler 阶段产生：

- 默认 `limit`
- 默认 `order_by`
- 默认展示字段
- search / filter 默认排序

这些默认值若需要应用，必须区分查询语义和展示策略：

- 安全上限写入 `execution_cap` / `limit_applied`，不得伪装成用户请求的 `limit`。
- 产品展示排序写入 `display_order`，仅影响 formatter 展示行顺序，**不得进入 compiler 的 Mongo `sort`**。若 compiler 需要 `sort`（如配合 `limit` 使用），`order_by` 必须由 LLM Draft 显式输出。
- `display_order` 与 `order_by` 作用在不同层：`order_by` 进入 compiler 决定 Mongo 查询排序；`display_order` 仅在 formatter 中对已返回结果重排。
- validator 可以注入 `display_order`（formatter 层）。validator 不得注入 `order_by`（compiler 层）。
- 只有用户明确表达排序时，LLM Draft 才能输出 `order_by`；validator 只能校验或值级归一。

```json
"validator_applied_defaults": [
  {"field": "execution_cap", "value": 10, "reason": "safety cap"},
  {"field": "display_order", "value": {"field": "ths_fund_scale_fund", "direction": "desc"}, "reason": "product display default"}
]
```

compiler 只能把 Validated AST 机械转换成 Mongo filter / projection / sort / limit。

- v3.2 AST-only operators 展开：
  - `between` -> 同字段 `gte` + `lte` AND 条件
  - `not_null` -> 字段存在且不为 `null` / `""` / `[]`
  - `is_null_or_empty` -> 字段缺失或为 `null` / `""` / `[]`
- compiler 不接受 LLM 生成的正则表达式；所有 regex 只能由 compiler 对已校验 value 执行 `re.escape` 后生成。
- compiler 对时间序列和 report array 的受控执行顺序固定为：先解析 `timeseries_semantics` / `report_period`，再执行 `expand`，最后执行 `order_by` / `limit` / formatter 展示。
- compiler 允许的受控物理扩展仅限：单字段 latest value、单字段 specified date、单字段 latest_two、数组展开、TopN 配对字段按 `rank_num` 对齐、`expand.order_by` 对展开后数组项按 `rank_num` 或配对字段排序。
- `$group` 只允许作为每个 fundcode、每个字段 latest-value extraction 的物理实现；禁止跨 fundcode 求 sum / avg / count。
- `performance_period_range` 是受控 display expansion：compiler 可读取 `ths_unit_nv_fund` 的 `btime` 序列计算时间范围 metadata，但不得用净值序列重算收益率、不得改变 semantic filter/order/limit。

### Remote Execution Safety [Hard]

Mongo 执行层必须是只读、受限、可审计的物理执行层。

规则：

- collection、projection path、filter field、sort field、aggregation stage 都必须来自 Registry allowlist。
- 禁止 `$out`、`$merge`、`$lookup`、`$function`、server-side JavaScript、任意 `$where`、任意未登记 stage。
- 禁止用 `$group` 做跨基金聚合分析；`$group` 仅允许在 latest-value extraction 中按 fundcode 和字段取最新 `btime`。
- `allowDiskUse=false` 作为 v3.2 smoke 默认值；如后续开放必须有单独 gate 和 explain 审计。
- 每个远端查询必须设置 `maxTimeMS`、硬 `execution_cap`、结果大小上限和只读凭据。
- filter/sort/limit 的语义执行顺序必须是 semantic filter -> semantic sort -> limit；禁止先 limit 再 post-filter/post-sort。
- 对 `[{value,btime}]` 字段，compiler 必须按 `timeseries_semantics.by_field` 选择明确策略：受限 aggregation pipeline 或 materialized scalar field。不得在取回结果后本地排序/筛选再伪装成数据库查询语义。
- 远端 smoke 必须验证 predicate truth、sort monotonicity、top-N oracle 或固定 fixture oracle，而不只验证 answer 格式。
- runtime audit 必须记录 `remote_query_executed`、`mongo_params_hash`、`operation`、`pipeline` 或 `{filter, projection, sort, limit}`、row count、`has_more`、`limit_applied`、`maxTimeMS`、remote error、snapshot/as-of metadata。

## 9. Compare Rules [Strategy]

generic compare 默认 8 列 display baseline：

```text
fundcode
ths_fund_extended_inner_short_name_fund
ths_name_of_tracking_index_fund
ths_fund_scale_fund
ths_yeild_ytd_fund
ths_yeild_1y_fund
ths_manage_fee_rate_fund
ths_mandate_fee_rate_fund
```

规则：

- generic compare 默认使用 8 列 display baseline。
- v3.2 strict pass 中，用户明确指定对比维度时，LLM Draft 必须选择对应 fields；validator 只可补 `fundcode`、简称等 identity/context 字段。
- 显式 compare 使用 `fundcode in [...]`
- 显式 compare 默认最多展示 10 个
- 派生 compare 默认展示 5 个
- 显式 compare 中若部分 `fundcode` 不存在，保留已找到项并列出缺失代码，不中断其余结果。
- 如果当前 Registry 未开放某个用户指定对比维度，返回 `UnsupportedQuery(reason=compare_field_not_supported)` 或 clarification，不得用固定列替代并计为 strict pass。

## 10. Period 规则

performance 周期：

| 标准表达 | 变体 | period | 交易日范围 | 字段 |
| --- | --- | --- | --- | --- |
| 近1周 | 最近一周、过去一周、一周来 | 1w | 往前 5 个交易日 | `ths_yeild_1w_fund` + 排名字段 |
| 近1月 | 最近一个月、过去一个月、这一个月 | 1m | 往前 21 个交易日 | `ths_yeild_1m_fund` + 排名字段 |
| 近3月 | 近3个月、过去三个月、最近一个季度、这三个月、前三个月 | 3m | 往前 63 个交易日 | `ths_yeild_3m_fund` + 排名字段 |
| 近6月 | 近半年、这半年、最近半年、过去六个月、半年来 | 6m | 往前 126 个交易日 | `ths_yeild_6m_fund` + 排名字段 |
| 近1年 | 近一年、最近一年、过去一年、这一年 | 1y | 往前 250 个交易日 | `ths_yeild_1y_fund` + 排名字段 |
| 近2年 | 最近两年、过去两年 | 2y | 往前 500 个交易日 | `ths_yeild_2y_fund` + 排名字段 |
| 近3年 | 最近三年、过去三年 | 3y | 往前 750 个交易日 | `ths_yeild_3y_fund` + 排名字段 |
| 近5年 | 最近五年、过去五年 | 5y | 往前 1250 个交易日 | `ths_yeild_5y_fund` + 排名字段 |
| 今年以来 | 年初以来、今年到目前、今年到现在 | ytd | T 所在年份首个交易日至 T | `ths_yeild_ytd_fund` + 排名字段 |
| 成立以来 | 成立到现在、成立至今、上市以来 | std | 净值序列第一条至 T | `ths_yeild_std_fund` + 排名字段 |
| 各周期 / 全部周期 | 全周期、所有周期 | all | 展开所有收益率字段 |
| 未指定 | - | 1y | legacy display default；v3.2 strict filter/sort 不得静默采用，single performance 可采用但必须标记 default_period_used |

T 指 `ths_unit_nv_fund` 最新一条 `btime`。收益率值直接查询 `ths_yeild_*` 标量字段，不用净值时间序列重算；`ths_unit_nv_fund` 只用于 `performance_period_range` 展示时间范围。

`period=all` 时，compiler 基于同一份 `ths_unit_nv_fund` btime 序列一次性生成全部周期的时间范围。收益率字段为空、排名字段为空或净值序列不足时，对应单元格显示 `暂无数据`，不得让整个 `performance` 查询失败。

排名展示优先使用 `_fund_origin` 和 `_etf`。

排序或比较时使用数字排名 `_fund`。

v3.2 strict pass 规则：

- LLM Draft 必须显式选择 period-specific performance fields。
- period parser 和 `PERIOD_FIELDS` 只能作为 evidence / normalization catalog / consistency check。
- `period=all` 或“各周期”必须由 LLM Draft 输出全部请求字段；validator 只能校验集合是否完整，不能生成字段集合后计为 strict pass。
- filter/sort 中未指定收益周期时，应返回 clarification 或显式记录 default period；不得把默认 `1y` 当作用户语义。

## 11. 归一化规则

### 枚举

| 用户表达 | 字段 | 值 |
| --- | --- | --- |
| 股票型 ETF | `ths_fund_invest_type_fund` | 股票型 |
| 债券型 ETF | `ths_fund_invest_type_fund` | 债券型 |
| 混合型 ETF | `ths_fund_invest_type_fund` | 混合型 |
| 货币型 ETF | `ths_fund_invest_type_fund` | 货币型 |
| 上交所 / 沪市 | `ths_fund_listed_exchange_fund` | 上交所 |
| 深交所 / 深市 | `ths_fund_listed_exchange_fund` | 深交所 |

上表是枚举值归一示例，不是路由触发规则，也不是最终 AST 的 `field/op/value` 生成表。

枚举或值归一失败时，不得默认降级为 search。

仅当用户原文同时包含明确 search 语义，且搜索关键词有效时，才允许转入 search。明确 search 语义包括显式搜索表达，也包括 Section 5 的 Implicit Collection Retrieval：用户未提供唯一 ETF 身份，但表达主题、指数、行业、名称片段、标的指数片段或候选集合目标。

否则返回：

- `ClarificationRequired(reason=value_ambiguity)`：存在多个可选枚举值，需要用户选择；
- `UnsupportedQuery(reason=value_normalization_failed)`：无法归一且无法澄清。

### 指数名称匹配

当 filter 的筛选条件涉及跟踪指数时，不靠 LLM 猜数据库值，也不直接降级为 search。系统维护本地 `IndexNameCatalog`：

- 启动时从远端 `tb_ths_etf_base` 拉取 `ths_name_of_tracking_index_fund` 和 `ths_tracking_index_code_fund` 去重集合
- 本地缓存用于前置识别和 filter 归一
- 缓存按 TTL 刷新或支持手动刷新
- 缓存不可用时，不猜数据库值；返回 `UnsupportedQuery(reason=index_catalog_unavailable)` 或在存在多个候选值但可澄清时返回 `ClarificationRequired(reason=value_ambiguity)`

本地执行两步匹配：

1. 精确匹配 `ths_tracking_index_code_fund`（如 `000300`）
2. 对 `ths_name_of_tracking_index_fund` 做子串匹配（如用户说 `沪深300` 匹配 `沪深300指数`）

IndexNameCatalog 只产生 normalized value / value_candidates，不直接生成 filter AST。

在 `llm_ast_draft` filter 中，LLM 仍必须输出 where Draft；validator 使用 IndexNameCatalog 的 normalized value 校验或覆盖 value。

匹配失败时不得默认降级为 search；仅当用户原文同时包含明确 search 语义且搜索关键词有效时，才允许转入 search，否则返回 `ClarificationRequired` 或 `UnsupportedQuery`。明确 search 语义包括显式搜索表达和 Section 5 的 Implicit Collection Retrieval，不要求一定出现“搜索/找”等词。

指数名称匹配的候选值来源于本地 `IndexNameCatalog`，而 `IndexNameCatalog` 由远端只读集合生成，不从 spec 硬编码。

以下分类词在前置识别中优先归入 filter，而不是普通 search：

```text
股票型、债券型、混合型、货币型、上交所、深交所、沪市、深市
```

### 日期范围归一

该规则自 v3.2 起生效；此前阶段 `ths_fund_establishment_date_fund` 仅支持 `eq`，日期范围问题返回 `UnsupportedQuery`。

- `ths_fund_establishment_date_fund` 的筛选能力采用一次验证、两级开放：
  - 抽样验证通过：`selectable`、`sortable` 开放，并在 `filter_operators` 中开放 `eq/gte/lte/between`。
  - 抽样验证未通过：仅允许 `selectable` 展示；涉及日期 `eq` / `compare` 的 filter 问法返回 `UnsupportedQuery(reason=blocked_by_verification)`。
- 抽样验证标准：从远端 `tb_ths_etf_base` 抽取不少于 20 条非空值，必须稳定为 `YYYY-MM-DD` 字符串或可无损归一为该格式。
- 验证通过后，日期范围筛选应归一为 `gte` / `lte` 组合，不得退化为模糊 search。
- 用户表达如 `2024年成立的ETF有哪些` 归一为 `ths_fund_establishment_date_fund >= 2024-01-01 AND ths_fund_establishment_date_fund <= 2024-12-31`。
- 用户表达如 `2024年1月成立` 归一为月份边界区间。
- 若日期范围无法归一且仍可判定为筛选问题，返回 `UnsupportedQuery`，不得伪造为 search。

### Period Normalization Fallback (v3.1+, 仅遗留参考 / 不用于 v3.2)

> **v3.2 替代：** 本节描述的 LLM-period-fallback 机制属于 v3.1 deterministic_legacy，v3.2 中已被 [Performance Period Handling in LLM AST Draft](#performance-period-handling-in-llm-ast-draft) 替代。本节保留仅用于 v3.0/v3.1 遗留对照和 golden diff audit，不得作为 v3.2 实现范式。v3.2 新增能力不得仿照该模式实现"LLM 小选择器 + 本地组 AST"。

该能力属于 v3.1 Normalization Enhancement，不改变 v3.0 已锁定回归基线。

LLM period fallback 属于 `deterministic_legacy` normalization helper，不属于 `llm_ast_draft`。

它不得计入 v3.2 Text2SQL 成果。v3.2 新增能力不得仿照该模式实现“LLM 小选择器 + 本地组 AST”。

问题背景：

- v3.0 使用本地确定性规则解析 period，例如 `近3个月 -> 3m`、`今年以来 -> ytd`。
- 生产问法存在大量同义表达，例如 `过去三个月`、`最近一个季度`、`年初到现在`、`成立到现在`。
- 规则漏解析时不允许把明确时间表达静默默认成 `1y`，否则会出现“回答成功但周期错误”的高风险结果。

执行顺序：

```text
本地规则解析 period
  -> 规则失败且 intent=performance
  -> LLM 做受限 period 归一
  -> 本地校验 period/evidence/confidence
  -> 作为 LLM AST Draft evidence / consistency check
```

LLM 只能返回：

```json
{
  "period": "1w | 1m | 3m | 6m | 1y | 2y | 3y | 5y | ytd | std | all | unknown",
  "confidence": 0.0,
  "evidence": "用户原文中的连续时间表达"
}
```

校验规则：

- `period` 必须属于白名单。
- `evidence` 必须非空，且必须是用户原文中的完整连续子串；否则该结果无效，降级为 `unknown`。
- `confidence < 0.75` 时视为 `unknown`。
- 如果用户没有明确时间表达，single `performance` 可使用默认 `period=1y`，但必须记录 `default_period_used=true`；filter/sort/ranking 场景应优先 clarification。
- 如果用户有明确时间表达但归一结果为 `unknown`，返回 `ClarificationRequired`，不静默默认成 `1y`。
- LLM 不允许输出字段名、集合名、Mongo 条件或答案。
- `period -> 字段` 在 v3.2 strict pass 中只能作为 evidence/consistency check；LLM Draft 必须输出 Registry 允许的 period-specific fields。
- 该 fallback 只用于 `performance` intent 的 evidence 生成，不用于 `report_period`，也不得在 Draft 缺失字段时生成 query structure。

示例：

```text
510300过去三个月回报如何
-> {"period": "3m", "confidence": 0.91, "evidence": "过去三个月"}
-> 本地映射 ths_yeild_3m_fund + 排名字段
```

```text
510300这段时间表现怎么样
-> {"period": "unknown", "confidence": 0.42, "evidence": "这段时间"}
-> ClarificationRequired：你想看近1月、近3月、近1年，还是今年以来？
```

### 单位和值域

| 类型 | 规则 |
| --- | --- |
| 10亿 | 1000000000 |
| 500万 | 5000000 |
| 0.2% | 0.2 |
| 费率/收益率 | 按百分比数值，不除以 100 |
| 日期 | `YYYY-MM-DD` |

值域：

| 字段类型 | 范围 |
| --- | --- |
| 规模 | 1e6 到 1e12 元 |
| 费率 | 0 到 10 |
| 收益率 | -100 到 1000 |
| 成立日期 | 1990-01-01 到当前日期 |
| limit | 1 到 50 |
| rank_limit | 1 到 10 |

### 排序短语

| 用户表达 | order |
| --- | --- |
| 规模最大 | desc |
| 收益最高 | desc |
| 净值增长率最高 | desc |
| 收益最差 | asc |
| 费率最低 | asc |
| 排名靠前 | asc |
| 成立最早 | asc |
| 成立最新 | desc |
| 分红次数最多 | desc |
| 机构持仓比例最高 | desc |

上表仅说明排序方向归一，不代表这些短语可以绕过 LLM AST Draft 直接生成 `order_by`。

成立日期排序仅当 `ths_fund_establishment_date_fund` gate 通过后生效。gate 未通过时，涉及成立日期排序的 filter 问法返回 `UnsupportedQuery(reason=blocked_by_verification)`。

## 12. 失败策略

- schema、安全、字段能力矩阵、Query Classification Matrix 冲突：直接失败，不执行 Mongo。
- 字段别名归一只允许发生在 pre-router / evidence extraction 阶段，用于生成 `candidate_fields`；AST Draft 中出现的字段必须已经是 Registry canonical field，validator 不得把未知字段、别名字段或中文字段名改写成合法字段。
- 排序方向、单位表达、日期表达：validator 可依据 Registry normalizer 与 evidence 归一，归一后必须重新完整校验。
- 枚举或值归一失败时不得默认降级为 search；仅当用户原文同时包含明确 search 语义且搜索关键词有效时才允许转入 search，否则返回 `ClarificationRequired(reason=value_ambiguity)` 或 `UnsupportedQuery(reason=value_normalization_failed)`。明确 search 语义包括显式搜索表达和 Section 5 的 Implicit Collection Retrieval。
- 用户意图不明确：返回澄清，不生成 AST。
- LLM 输出无法归一到标准字段、标准 intent 或前置候选范围：直接失败，不进入 compiler。
- 问题所需字段或指标未进入 Registry：返回 `UnsupportedQuery`，不得用同类字段或单基金字段部分回答替代。

## 13. Report Schema

`report_period` 固定为 object。

latest：

```json
{"mode": "latest"}
```

指定报告期：

```json
{"mode": "specified", "year_num": 2024, "type_num": 4}
```

规则：

- quarter latest 的物理排序规则在远端确认前不得固定为单一策略。
- 数据字典定义 `type_num=1/2/3/4` 分别表示一季报/中报/三季报/年报；`type_num=4` 不是四季报。
- quarter latest 若直接按 `year_num desc, type_num desc` 会取到年报语义；“最新季报”是否必须排除 `type_num=4` 仍需远端验证。若确认需要排除年报，则候选集必须限定为 `type_num in [1,2,3]` 后再按 `year_num desc, type_num desc` 取最新；验证前不得静默把年报当季报。
- year latest 按 `year_num desc`
- year report 语义优先使用 `tb_ths_etf_report_year`；若实现选择 quarter 集合 `type_num=4` 作为年报来源，必须在 provenance 中记录 collection choice。
- year 的 `type_num` 是否固定或忽略仍需远端验证
- child LLM AST Draft 必须显式产出 `{"mode":"latest"}` 或 `{"mode":"specified", ...}`；orchestrator 不得静默补齐 `report_period`
- 当 `expand` 指定的字段在报告文档中不存在、为 null 或无数组数据时，该 child 只输出 `暂无对应数据` 或对应 reason；不得降级展示报告期基础信息，也不得用其他字段替代用户请求的 report 数组内容。
- 非 report query 的 `report_period` 和 `expand` 必须为 `null`。
- report query 的 `report_period` / `expand` 缺失、重复或多对象拼接均为 schema validation failure。
- `report_period` 与 `expand` 必须来自 child LLM AST Draft；validator 只能校验、归一和拒绝，不得静默补出用户报告期语义，formatter 不得临时补出。

`expand` schema：

```json
{
  "field": "ths_top_held_stock_code_fund",
  "rank_limit": 10,
  "paired_fields": [
    "ths_top_stock_mv_to_fnv_fund"
  ],
  "order_by": {"field": "rank_num", "direction": "asc"}
}
```

规则：

- `expand` 仅允许 `output_style=report_list`
- `expand.field` 必须是当前集合 `array_expandable`
- `expand.order_by` 可省略；省略时默认按 `rank_num asc` 排序
- `expand.order_by.field` 只允许 `rank_num` 或 `paired_fields` 中的字段名；不得用 `expand.field` 的 value 字段作为排序键
- 指定 `expand.order_by` 时按对应展开值排序；缺值排后
- 执行顺序固定为：按 `report_period` 取报告文档 -> 展开 `expand.field` 与 `paired_fields` -> 按 `expand.order_by` 排序 -> 应用父级 AST `limit`
- 缺 `rank_num` 的项排后
- `paired_fields` 只能是 Registry 中声明为同一 report profile 的配对字段名；LLM 不得生成 label / format，展示元数据必须由 Registry 提供
- `paired_fields` 按相同 `rank_num` 对齐
- 配对字段在某个 `rank_num` 上缺失或为 null 时，该配对值显示 `暂无数据`，不得丢弃主字段项
- `expand` 结果为空数组、字段缺失或该报告期无对应数据时，compiler 不报错，formatter 展示 `暂无数据`
- `rank_limit` 是上限，不是必须补满的数量；实际只有 5 条且 `rank_limit=10` 时展示 5 条，不补空行
- `rank_limit` 是展开候选上限，不等于最终结果条数；用户按配对字段排序取 Top N 时，`rank_limit` 必须覆盖足够候选集，最终截断由 `expand.order_by + limit` 完成
- 季报只支持行业、重仓概念
- 年报重仓先展示代码+占比，不编造证券名称
- 标量 report intent（`institution_holding`、`report_style`、`report_nav_change`）不得生成 `expand`

## 14. Capability Matrix Operator-Gate 派生视图

本节是 Executable Capability Registry 的字段视图，仅用于展示、审计和测试，不得独立维护。

以下矩阵基于 `references/data-dictionary.md` 的全量字段，并已用 2026-05-07 的远端只读抽样核对过真实集合键。v2 没有给出完整能力矩阵，但它的字段清单与本次远端核对足以补全这里的定义。

Capability Matrix 是 Registry 的派生视图。字段能力必须按 profile + operator + gate 展示。

| field | profile | selectable | sortable | operator | operator_gate | normalizer | phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ths_etf_to_code_fund` | `basic_info_extended` | true | false | none | - | - | v3.2 |
| `ths_etf_to_code_fund` | `filter_list` | true | false | `eq` | verification_passed | string | v3.2 |
| `ths_etf_to_code_fund` | `filter_list` | true | false | `not_null` | verification_passed | null_semantics | v3.2 |
| `ths_etf_to_code_fund` | `filter_list` | true | false | `is_null_or_empty` | verification_passed | null_semantics | v3.2 |

规则：

- 字段能力不是全局能力，必须绑定 profile。
- `basic_info_extended` 字段不得自动进入 `basic_info`。
- `filter_list` 的 operator 不代表 single profile 可使用相同 operator。
- `selectable=true` 不代表该字段可筛选；筛选能力必须以 operator row 为准。
- `filterable_eq`、`filterable_compare` 等粗粒度标签已废弃，只允许作为历史术语阅读，不得作为 runtime 派生源。

### 14.1 tb_ths_etf_base

#### 标识 / 分类 / 文本

- `fundcode`, `thscode`：`selectable`; `fundcode` 在允许的 profile 中开放 `eq/in` operator；`sortable` 仅作为稳定 tie-breaker 使用
- `fundcode` / `thscode` 仅用于精确定位与 compare 的 `in` / `eq` 筛选，不作为比较维度。
- `ths_fund_extended_inner_short_name_fund`, `ths_fund_type_fund`, `ths_fund_invest_type_fund`, `ths_tracking_index_code_fund`, `ths_name_of_tracking_index_fund`, `ths_perf_comparative_benchmark_fund`, `ths_pur_and_redemp_status_fund`, `ths_etf_to_code_fund`, `ths_fund_listed_exchange_fund`：`selectable`；筛选能力以对应 profile 的 `filter_operators` 为准
- 其中 `ths_fund_extended_inner_short_name_fund`, `ths_name_of_tracking_index_fund`, `ths_tracking_index_code_fund` 额外 `fuzzy_searchable`
- `ths_fund_manager_current_fund`, `ths_fund_supervisor_fund`：`selectable`；名称反查可复用，但 v3 search 主链路不把它们当主要 fuzzy 字段
- `ths_invest_objective_fund`, `ths_invest_socpe_fund`, `ths_invest_philosophy_fund`, `ths_invest_strategy_fund`, `ths_risk_return_characteristics_fund`：`selectable`，仅做展示，不进入 v3.1 search/filter 主路径

#### 时间信息

- `ths_fund_establishment_date_fund`：v3.2 抽样验证通过后为 `selectable`, `sortable`，并开放 `eq/gte/lte/between` operators；验证未通过时仅 `selectable`

#### 规模 / 净值

- `ths_fund_scale_fund`, `ths_fund_shares_fund`, `ths_unit_nv_fund`, `ths_unit_nvg_rate_fund`, `ths_current_mv_fund`：`selectable`, `sortable`；比较筛选能力以 profile operator gate 为准
- 真实 DB 中 `ths_fund_scale_fund`, `ths_fund_shares_fund`, `ths_unit_nv_fund`, `ths_unit_nvg_rate_fund` 为 latest_ts 数组，使用最新 `btime` 的 `value`
- 在 `performance` profile 中，`ths_unit_nv_fund` 只作为 `display_context_for_period_range` 使用；LLM Draft 不需要选择该字段，validator/compiler 可基于 Registry 声明追加物理 projection，并在 provenance 中记录为 display context，不计为 semantic addition

#### 收益率

- `ths_yeild_1w_fund`, `ths_yeild_1m_fund`, `ths_yeild_3m_fund`, `ths_yeild_6m_fund`, `ths_yeild_1y_fund`, `ths_yeild_2y_fund`, `ths_yeild_3y_fund`, `ths_yeild_5y_fund`, `ths_yeild_ytd_fund`, `ths_yeild_std_fund`：`selectable`, `sortable`；比较筛选能力以 profile operator gate 为准
- 新版数据字典确认以上 yield 字段为 `number` 标量；不走 `timeseries_semantics`，也不再作为 v3.3 字段结构 blocker。收益周期字段仍必须来自 LLM AST Draft，validator 不得按 profile baseline 补语义字段。
- 数字排名字段：
  `ths_yeild_rank_1w_fund`, `ths_yeild_rank_1m_fund`, `ths_yeild_rank_3m_fund`, `ths_yeild_rank_6m_fund`, `ths_yeild_rank_1y_fund`, `ths_yeild_rank_2y_fund`, `ths_yeild_rank_3y_fund`, `ths_yeild_rank_5y_fund`, `ths_yeild_rank_ytd_fund`, `ths_yeild_rank_std_fund`；
  `ths_yeild_rank_1w_etf`, `ths_yeild_rank_1m_etf`, `ths_yeild_rank_3m_etf`, `ths_yeild_rank_6m_etf`, `ths_yeild_rank_1y_etf`, `ths_yeild_rank_2y_etf`, `ths_yeild_rank_3y_etf`, `ths_yeild_rank_5y_etf`, `ths_yeild_rank_ytd_etf`, `ths_yeild_rank_std_etf`：
  `selectable`, `sortable`；比较筛选能力以 profile operator gate 为准
- 数据字典同时列出 `ths_yeild_std_rank_etf`，与既有 Registry 命名模式 `ths_yeild_rank_std_etf` 不一致；实现前必须用远端字段探针确认最终物理字段名，不得假设两者同时存在。
- 字符串排名字段：
  `ths_yeild_rank_1w_fund_origin`, `ths_yeild_rank_1m_fund_origin`, `ths_yeild_rank_3m_fund_origin`, `ths_yeild_rank_6m_fund_origin`, `ths_yeild_rank_1y_fund_origin`, `ths_yeild_rank_2y_fund_origin`, `ths_yeild_rank_3y_fund_origin`, `ths_yeild_rank_5y_fund_origin`, `ths_yeild_rank_ytd_fund_origin`, `ths_yeild_rank_std_fund_origin`：
  `selectable`，用于展示

#### 基金经理

- `ths_manager`：`selectable`, `array_expandable`
- `ths_service_sd_fund`, `ths_name_fund`, `ths_service_duration_annual_return_fund`, `ths_rzjjzgm_fund`, `ths_tenure_fund`：`selectable`
- manager_detail 时间线必须优先按 `ths_service_sd_fund` 排序；`rank_num` 只用于数组展示稳定性，不表示任职顺序或现任。
- 其中 `ths_service_sd_fund` 可做日期排序；`ths_service_duration_annual_return_fund`, `ths_rzjjzgm_fund`, `ths_tenure_fund` 可做数值排序/对比

#### 交易时间序列快照 / 补充 / 费率 / 分红

- v3.3 开放 base 交易时间序列快照字段；只回答数据库快照，不承诺实时/盘中行情。
- 数据字典标题称时间序列结构为 10 个字段，但实际字段清单只有 9 个；spec 以字段清单为准，不引用该数量。
- base 时间序列字段清单为：`ths_fund_scale_fund`, `ths_fund_shares_fund`, `ths_unit_nv_fund`, `ths_unit_nvg_rate_fund`, `ths_similar_fund_std_avg_yield_fund`, `ths_amt_fund`, `ths_netcashflow_fund`, `ths_margin_trading_balance_fund`, `ths_short_selling_amtb_fund`。
- `ths_current_mv_fund` 是 `number` 标量，不走 `timeseries_semantics`。
- `ths_amt_fund`, `ths_netcashflow_fund`, `ths_margin_trading_balance_fund`, `ths_short_selling_amtb_fund`：`selectable`；不开放 `filter_operators`、`sortable`、`fuzzy_searchable`、`array_expandable`
- 以上交易字段按 `[{value,btime}]` 时间序列处理，默认使用 `timeseries_semantics.by_field[字段].mode=latest`，formatter 必须展示 as-of `btime`。
- `ths_similar_fund_std_avg_yield_fund` 虽确认为时间序列字段，但暂不纳入 v3.0-v3.3 capability matrix；后续如需同类均值能力必须单独验证周期口径。
- `ths_manage_fee_rate_fund`, `ths_mandate_fee_rate_fund`：`selectable`, `sortable`；比较筛选能力以 profile operator gate 为准；answer_fields format 为 `percent`
- `ths_accum_dividend_total_amt_fund`：`selectable`, `sortable`；比较筛选能力以 profile operator gate 为准；answer_fields format 为 `amount`，除以 1e8 加"亿元"
- `ths_accum_dividend_times_fund`：`selectable`, `sortable`；比较筛选能力以 profile operator gate 为准；answer_fields format 为 `plain`

### 14.2 tb_ths_etf_report_quarter

- `fundcode`, `thscode`, `year_num`, `type_num`：`selectable`, `sortable`；filter operators 以 report profile gate 为准
- `ths_top_n_top_industry_name_fund`, `ths_zcgnmc_fund`：`structure=top_n_array`, `selectable`, `array_expandable`
- 两个数组都按 `rank_num` 展开；`type_num=1/2/3/4` 分别表示一季报/中报/三季报/年报。`type_num=4` 不是四季报；“最新季报”是否跳过 `type_num=4` 仍以远端验证结果为准。
- `report_industry` quarter variant：`from=tb_ths_etf_report_quarter`，`expand.field=ths_top_n_top_industry_name_fund`，`paired_fields=[]`，默认 `expand.order_by={field:"rank_num", direction:"asc"}`。
- “季报 + 持仓”且没有“重仓股/重仓证券/前十大”等股票明细语义时，归入 `report_industry` 并展示为“最新季报行业配置/行业持仓”；不得暗示为重仓股明细。
- “季报 + 重仓股/重仓证券/前十大”返回 `UnsupportedQuery(blocked_by_verification)`，reason=`quarter_holding_stock_fields_unavailable`，不进入 AST。

### 14.3 tb_ths_etf_report_year

- `fundcode`, `thscode`, `year_num`, `type_num`：`selectable`, `sortable`；filter operators 以 report profile gate 为准
- `ths_org_investor_total_held_ratio_fund`, `ths_org_investor_total_held_shares_fund`, `ths_invest_style_fund`, `ths_fanv_chg_fund`, `ths_fanv_chg_rate_fund`：`structure=scalar`, `selectable`
- `institution_holding` 包含机构投资者持有比例和持有份额；`report_style` 包含投资风格；`report_nav_change` 包含净资产变动和净资产变动率。
- 以上 scalar report intent 进入 v3.3 executable，不生成 `expand`；数值字段可在对应 report profile 中开放比较 operator 和 `sortable`，`ths_invest_style_fund` 可允许 `eq`
- `ths_top_n_top_industry_name_fund`, `ths_top_sec_code_fund`, `ths_top_held_stock_code_fund`：`structure=top_n_array`, `selectable`, `array_expandable`
- `ths_top_n_top_industry_mv_to_equity_fund`, `ths_top_n_top_stock_mv_to_equity_fund`, `ths_top_stock_mv_to_fnv_fund`：`structure=paired_top_n_array`, `selectable`, `array_expandable`
- 行业/重仓数组按 `rank_num` 展开，缺少配对字段时显示 `暂无数据`
- `report_industry` year variant：`from=tb_ths_etf_report_year`，`expand.field=ths_top_n_top_industry_name_fund`，`paired_fields=[ths_top_n_top_industry_mv_to_equity_fund]`。用户说“占比最高/前五”时，LLM Draft 必须生成 `expand.order_by={field:"ths_top_n_top_industry_mv_to_equity_fund", direction:"desc"}`，并由父级 AST `limit` 表达最终条数。
- year 集合 `type_num` 的允许值和 latest 语义仍需远端验证；验证前不得依赖它表达复杂 latest 规则。

## 15. Orchestrator

`composite` 属于 orchestrator 外层，不进入单个 AST。

规则：

- 前置 routing 可以输出 `recognized_query_mode=composite`、`composite_type=composite_single | two_step_composite`、`sub_intent_candidates`。
- routing 只能给候选和 evidence，不生成字段、where、order_by、report_period、timeseries_semantics。
- 子意图识别必须走语义匹配（embedding 或 LLM routing）；关键词只允许作为 evidence seed，不能作为唯一分发协议。
- `fee_and_manager` 是独立 intent，不通过通用 merge 推导。
- base + report 拆成多个 child AST。
- search/filter 后 detail/compare/report 拆成两个 stage。
- `two_step_composite` 的 Step 2 可以是 single child、report child、compare child 或一层 `composite_single` child bundle。
- 嵌套深度最多一层；Step 1 只能产出候选 fundcodes，Step 2 才对这些 fundcodes 执行一个或多个 child AST。该限制是为了防止 orchestrator 递归爆炸和 child provenance 链不可审计，超出限制返回 `UnsupportedQuery`。
- `composite_single` 有两种执行形态：同 collection / single profiles 合并时是单 AST；跨 collection、包含 report child 或 compare child 时是 orchestrator 管理的 multi-child bundle。任何单个 AST 都只能有一个 `from`。
- composite Step 2 为 single detail 时，辅助展示字段只能来自该 child LLM AST Draft 的 `answer_fields`，或 validator 仅基于 Registry 的 identity/context/display-only baseline 显式补齐并记录（`baseline_fields_added`）。orchestrator 不得自行追加 `select` / `answer_fields` 字段，也不得补语义字段。
- composite 场景下，Step 1 的 limit 由 orchestrator 统一接管，默认 `limit=10`，覆盖各 stage 的默认 limit
- 仅 Step 2 继续服从对应 query_mode / intent 的默认 formatter 规则
- Step 1 空结果：停止，返回未找到候选
- Step 1 多于 N：截断并说明，N 固定为 10
- 若 Step 1 显式要求 top-k，则实际取 `min(k, 10)`
- 超过 N 时，保留前 N 个候选，并返回“对比上限为 5 只”或“已截断，仅展示前 N 个”提示，提示语需明确上限来自 orchestrator
- Step 2 部分 fundcode 无数据：保留有数据项，列出缺失代码
- multi-child composite 中单个 child 返回 `data_not_available` 或 `blocked_by_verification` 时，不影响其它 child；输出中该 child 展示 `暂无数据` 或对应 reason。只有所有 child 都失败时，父级 composite 才整体失败。
- 名称反查多候选：不进入 AST，返回候选澄清列表
- base + report：各 child 使用自己的 formatter 模板，父级只拼接输出，不重写 child 语义
- composite 父级没有单一 `output_style`；输出顺序由 orchestrator 根据 child 类型确定，不需要 LLM 生成顺序。
- composite 最终输出顺序：
  - summary/detail child 优先。
  - report_list child 在对应 summary/detail 后展示。
  - compare/table child 按用户语义位置或 coverage matrix 锚点顺序插入。
  - Step 2 结果已包含 Step 1 关键信息时（如 compare 表已列出所有基金代码和名称），只展示 Step 2 结果
  - Step 2 为 detail（single 子 AST）且无法从 Step 2 结果推断 Step 1 候选时，先展示 Step 1 简略列表（代码 + 名称），再展示 Step 2 详情
  - Step 1 结果被截断时，需提示"已截断，仅展示前 N 个"
- coverage matrix 是 Section 十复合查询的验收权威；不得仅按关键词或本节示例推断覆盖范围。

**search/filter → single detail 的候选选择规则：**

- Step 1 返回 0 条：停止，返回未找到候选
- Step 1 返回 1 条：自动进入 Step 2
- Step 1 返回多条且用户使用“它 / 这只”等单数指代：返回 `ClarificationRequired`，不得默认选第一条或按规模自动选择
- 用户明确“全部 / 每只 / 对比”：按 compare/list/report 批量规则执行
- 以上规则适用于 search/filter -> single/detail/report 的 composite 场景
- orchestrator 在进入 Step 2 前，只能将 Step 1 结果中的 fundcode 集合写入 Step 2 `llm_draft_evidence.deterministic_entities.fundcodes`，并可传递用户原文中的 report_period evidence；禁止传递 `timeseries_semantics`、field/op/order_by 模板或预组装 AST 片段。
- 同 fundcode 跨集合 composite 中，orchestrator 只能将已解析 fundcode 写入每个 child 的 `llm_draft_evidence.deterministic_entities.fundcodes`；child LLM 必须自行输出 `where fundcode eq` Draft，orchestrator 不得直接注入 child AST 的 `where`。

**filter → compare 派生规则：**

- 用户原文包含“对比 / 比较 / vs / 比一下”，且 Step 1 返回 >= 2 条时，Step 2 进入 compare
- 用户原文包含“前 N 只 ... 对比”或“top N ... 对比”，且 Step 1 返回 >= 2 条时，Step 2 进入 compare
- 用户只说“前 N / 排名前 N / 最高 / 最低”，但没有对比语义时，不触发 compare，Step 1 以 list 输出结束
- Step 1 仅返回 1 条时，不触发 compare，按 filter/list 或 single detail 规则输出
- 派生 compare 使用 Step 1 结果作为候选集，不重新搜索
- 默认取 Step 1 前 5 条进入 compare；用户显式指定 N 时取 `min(N, 5)`
- Step 1 返回 > 5 条时，取前 5 条并提示“对比上限为 5 只，已截断”
- Step 2 generic compare 使用 8 列 display baseline；用户指定维度时仍须由 Step 2 LLM Draft 选择对应 semantic fields
- orchestrator 在进入 Step 2 前，只能将 Step 1 结果中的 fundcode 集合写入 Step 2 `llm_draft_evidence.deterministic_entities.fundcodes`

### Composite Child AST Generation

v3.2 covered composite 的每个 child query 都必须独立走 `llm_ast_draft`。

orchestrator 职责：

- 识别最多 2 步 composite。
- 为每个 step 构造独立 `generation_context`。
- 将 Step 1 的执行结果以 deterministic entity 形式传给 Step 2。
- 将同 fundcode 跨集合 composite 中已解析的 fundcode 以 deterministic entity 形式传给每个 child。
- 将用户原文中已提取的 report_period evidence 传给相关 report child。
- 控制 step-level limit cap。
- 汇总展示结果。

orchestrator 禁止：

- 生成 child AST 的 `select`。
- 生成 child AST 的 `where`。
- 生成 child AST 的 `order_by`。
- 生成 child AST 的 `limit`。
- 生成或传递 child AST 的 `report_period` / `timeseries_semantics`。
- 直接向 child AST 注入 `where fundcode eq`；fundcode 只能进入 child `llm_draft_evidence.deterministic_entities.fundcodes`，由 child LLM Draft 生成 where。
- 调用 deterministic builder 作为 passing path。

Step 1 filter evidence 示例：

```json
{
  "step": 1,
  "recognized_query_mode": "filter",
  "llm_draft_evidence": {
    "raw_evidence": [
      {"text": "股票型ETF里今年收益最高的5只", "kind": "filter_sort_limit"}
    ],
    "candidate_fields": [
      {"field": "ths_fund_invest_type_fund", "evidence": "股票型"},
      {"field": "ths_yeild_ytd_fund", "evidence": "今年收益最高"}
    ],
    "value_candidates": [
      {"raw": "股票型", "normalizer": "enum"},
      {"raw": "5只", "normalizer": "limit"}
    ]
  }
}
```

Step 2 compare 只能接收 Step 1 结果中的确定性实体：

```json
{
  "deterministic_entities": {
    "fundcodes": ["510300", "159919", "510500"]
  }
}
```

Step 2 仍必须由 LLM 输出完整 compare AST Draft。下例只展示 `where` 片段，实际 AST 必须包含 Section 6 要求的全部顶层字段：

```json
{
  "intent": "compare",
  "where": [
    {"field": "fundcode", "op": "in", "value": ["510300", "159919", "510500"]}
  ]
}
```

validator 覆盖或校验 fundcode list，并记录 `deterministic_overrides`。

### v3.2 Two-Step Composite Requirement

已在 v3.1 coverage 中标记为 covered 的 two-step composite，v3.2 必须迁移为 child AST 均走 `llm_ast_draft`。

规则：

- orchestrator 只负责编排步骤、传递 Step 1 结果中的 fundcodes、控制 step limit。
- orchestrator 不生成 child AST。
- Step 1 必须输出完整 LLM AST Draft。
- Step 2 必须输出完整 LLM AST Draft。
- validator 分别校验每个 child AST。
- compiler 只编译 validated child AST。
- 任一 child query 走 `deterministic_legacy`，则该 v3.2 用例失败。

PM 复合意图锚点：

- `十.1 帮我找跟踪沪深300指数、费率最低的ETF，然后看它的基本信息和收益`：`two_step_composite`；Step 1 `filter=llm_ast_draft`；Step 2 `composite_single=llm_ast_draft`
- `十.2 股票型ETF里今年收益最高的5只是哪些？对比一下`：`two_step_composite`；Step 1 `filter=llm_ast_draft`；Step 2 `compare=llm_ast_draft`；orchestrator 只传递 Step 1 fundcodes。
- `十.3 搜索中证红利，查一下它的基本信息和持仓`：`two_step_composite`；Step 1 `search=llm_ast_draft`；Step 2 `composite_single=llm_ast_draft`
- `十.4 510300今年收益多少，持仓了哪些行业，基金经理是谁`：`composite_single`；`performance + report_industry + manager_detail`
- `十.5 帮我看看510500的规模大不大，费率贵不贵，收益好不好`：`composite_single`；`fund_scale + fee + performance`
- `十.6 上交所的ETF里，找管理费最低的3只，对比它们的今年收益`：`two_step_composite`；Step 1 `filter=llm_ast_draft`；Step 2 `compare=llm_ast_draft`
- `十.7 510300成立以来收益怎么样，分过红吗`：`composite_single`；`performance + dividend`
- `十.8 对比510300和510500的费率、规模和重仓股`：`composite_single`；`compare(base: fee + fund_scale) + report_holding(510300) + report_holding(510500)`

以上锚点不是 PM Section 十的完整覆盖清单。Section 十全部 8 条复合意图必须以 `docs/v3-coverage-matrix.md` 为验收权威逐条标记：

- 哪些是 v3.2 covered `two_step_composite` / `composite_single`
- 哪些因数据口径缺失而返回 `UnsupportedQuery(data_not_available)`
- 哪些因超过 2-step 或通用 3 intent merge 而返回 `UnsupportedQuery(multi_step_composite_not_supported)`
- 哪些被显式允许为 `partial_composite`

实现不得仅根据本节两个 PM 锚点推断 composite 覆盖范围；coverage matrix 中每一条 PM 原句的 `expected_outcome`、`ast_required`、`llm_ast_draft_required`、`remote_query_allowed` 才是最终验收口径。

十章全部复合问法在 v3.3 中按 coverage matrix 执行，关键样例包括：

- 10.1: `two_step_composite` -> `composite_single(basic_info + performance)`
- 10.2: `two_step_composite` -> `compare`
- 10.3: `two_step_composite` -> `composite_single(basic_info + report)`
- 10.4: `composite_single(performance + report_industry + manager_detail)`
- 10.5: `composite_single(fund_scale + fee + performance)`
- 10.6: `two_step_composite` -> `compare`
- 10.7: `composite_single(performance + dividend)`
- 10.8: `composite_single(compare(base: fee + fund_scale) + report_holding x2)`

### Multi-Part Composite Boundary

v3.3 仍不支持通用 3 intent merge，也不支持无限多步 composite。

默认策略：

- report 子步骤与 base 子步骤都必须各自生成 child AST；如果某个 child 的数据口径不存在，单个 child 返回 `UnsupportedQuery(data_not_available)`，父级不替其它 child 编造语义。
- v3.3 默认 `UnsupportedQuery(reason=multi_step_composite_not_supported)` 只适用于 3 段以上复合或跨集合、跨 query_mode 的未注册组合。
- 已在 PM coverage 中标记为 covered 的 two-step composite 和 composite_single，不适用默认 Unsupported；必须迁移为 child AST 均走 `llm_ast_draft`。
- 只有 coverage matrix 明确标注 `expected_outcome=partial_composite` 的问题，才允许执行 partial composite。
- partial composite 必须明确说明已执行部分、未执行部分和未执行原因。

允许范围：

- `composite_single` 单 AST 形态：同 fundcode、同 collection、single profiles 合并。
- `composite_single` multi-child bundle 形态：同一用户问题或同一主实体下，跨 collection、report child 或 compare child 由 orchestrator 拆为多个 child AST；每个 child 各自只有一个 `from`。
- search/filter -> detail/compare/report：最多 2 步。
- `two_step_composite` 的 Step 2 可以是 single child、report child、compare child 或一层 `composite_single` child bundle。

覆盖 composite 的每个 child query 都必须独立走 `llm_ast_draft`。

orchestrator 只负责：

- 分步
- Step 1 result -> Step 2 deterministic_entities
- limit cap
- 输出合并

orchestrator 不得生成 child AST 的 `select` / `where` / `order_by` / `limit` / `report_period` / `timeseries_semantics`。
orchestrator 可以把 fundcode 等确定性实体写入 child evidence，但不能把它们写成 child AST 条件。

禁止：

- 为了通过测试，在 formatter 或 builder 中偷偷拼接多个 intent 字段。
- 把未注册的 3 段以上复合压成一个 `composite_single`。
- 把跨 collection composite 压成一个多 `from` AST。
- 把 report 未开放部分降级为 base 字段回答。

### composite_single 执行形态（v3.2+）

`composite_single` 属于 v3.2 `llm_ast_draft` 路径，不是字段选择器，也不是本地字段并集拼接器。

当用户问题涉及同一个 fundcode 的多个 single profile 且所有字段在同一个 collection 时，系统允许把它们合并为一次查询，但必须由 LLM 一次性生成完整 AST Draft。

当用户问题涉及跨 collection、report child 或 compare child 时，`composite_single` 只表示同一用户问题或同一主实体下的 child bundle，不表示单 AST。父级 orchestrator 必须拆成多个 child；每个 child 独立生成 AST Draft、validator、compiler、formatter。

合并条件（全部满足）：

- 同一 fundcode（已通过代码或唯一名称解析确定）
- 同一 collection（`tb_ths_etf_base`）
- 所有涉及的 profile 均为 single query_mode
- 所有涉及的 profile 的 gate 均已通过
- 不涉及 report 集合
- 不涉及 filter / sort 派生
- 每个子 profile 均能在用户原文中找到独立语义证据

执行规则：

1. Registry 构造合并后的 `generation_context`。
2. 合并后的 `generation_context` 包含：
   - `intent_candidates=["composite_single"]`
   - `sub_intent_candidates`
   - 各子 profile 的 selectable fields 并集
   - 各子 profile baseline_answer_fields 并集
   - 各字段 field_operators / format / gate / normalizer 约束
   - `where_constraints` 仅允许 `fundcode eq`
3. LLM 必须一次性输出完整 AST Draft，不得只输出字段列表。
4. AST Draft 必须包含：
   - `intent="composite_single"`
   - `sub_intents`
   - `from`
   - `select`
   - `where`
   - `order_by`
   - `limit`
   - `output_style`
   - `answer_fields`
   - `report_period`
   - `expand`
5. `select` 和 `answer_fields` 中的语义字段必须全部来自 LLM Draft；validator 只能补 `fundcode`、简称等 identity/context/display 字段，不得按 profile baseline 补 fee/performance/scale/manager 等语义字段。
6. validator 使用合并后的 `generation_context` 校验 AST Draft。
7. validator 可以覆盖或校验确定性 fundcode。
8. validator 通过后进入同一个 Mongo compiler。
9. validator 失败不得回退为多个 single AST，也不得回退为 deterministic legacy。

示例：

```json
{
  "intent": "composite_single",
  "sub_intents": ["investment_profile", "fee"],
  "from": "tb_ths_etf_base",
  "select": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_invest_objective_fund",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund"
  ],
  "where": [
    {"field": "fundcode", "op": "eq", "value": "510300"}
  ],
  "order_by": null,
  "limit": 1,
  "output_style": "summary",
  "answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
    {"field": "ths_invest_objective_fund", "label": "投资目标", "format": "long_text"},
    {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
    {"field": "ths_mandate_fee_rate_fund", "label": "托管费率", "format": "percent"}
  ],
  "report_period": null,
  "expand": null
}
```

禁止规则：

- 不得把 `composite_single` 实现成 `select` / `answer_fields` 的本地并集拼接。
- 不得让 LLM 只选择字段。
- 不得在 compiler 阶段注入业务语义；compiler 只编译 validated AST。
- 不做跨 fundcode 合并，不做跨 query_mode 合并。
- 不做 report 合并。
- gate blocked 的 profile 不进入 `sub_intent_candidates`。
- `composite_single` 只要在当前阶段被认定为可执行，就必须一次性覆盖用户原文中全部已支持的 single 子意图；不得只回答其中一部分后当作成功。
- 若用户问题包含多个子意图，但其中任一子意图超出当前阶段能力或口径未通过验证，必须返回 `UnsupportedQuery` / `ClarificationRequired`，不得只执行剩余子意图。

跨 collection `composite_single` child bundle 规则：

- 父级 `recognized_query_mode=composite`，`expected_intent_or_profile=composite_single`。
- 父级不产生 AST；每个 child 都产生自己的完整 AST。
- 同 fundcode child 共享实体时，fundcode 只能进入 child `llm_draft_evidence.deterministic_entities.fundcodes`。
- child LLM 必须自行输出 `where fundcode eq/in`，validator 只能覆盖或校验 value。
- 任一 child 不得从其它 child 继承 `report_period`、`timeseries_semantics`、field/op/order_by 模板。
- 单个 child `data_not_available` / `blocked_by_verification` 不导致父级整体失败；父级输出保留成功 child，并为失败 child 展示 `暂无数据` 或 reason。所有 child 均失败时，父级返回失败。
- 父级输出按 orchestrator 决定的 child 类型顺序拼接；summary/detail 优先，report_list 和 compare/table 保持各自 formatter 输出。

## 16. Deny Intent

命中 deny 后不生成 AST。

PM canonical smoke 中，`DeniedQuery` 只允许出现在十二章边界/异常场景。非十二章问题不得因为措辞模糊直接 deny；能落到已开放客观查询能力时必须生成 AST，无法落到能力时返回 `UnsupportedQuery` 或 `ClarificationRequired`。

分类：

| 类别 | 示例 |
| --- | --- |
| 实时行情类 | 今日涨跌、今日收益、今天收益、价格、当前净值、实时净值、估值、盘中、盘口、最新价格、涨跌幅、K 线 |
| 交易指标类 | 实时成交额、盘中成交额、实时净现金流、实时融资余额、盘中融资余额、实时融券卖出量、盘中融券卖出量、实时换手率、实时资金流、实时溢价率、实时折价率、实时委比、实时量比 |
| 技术分析类 | MACD、均线、RSI |
| 投资建议类 | 能买吗、值得买吗、该不该买、推荐哪只、帮我选、买哪个 |
| 个股分析类 | 贵州茅台怎么样、某股票分析 |

输出使用固定拒绝模板，说明能力边界。

compare 与 deny 边界：

- “哪个好”若显式包含多个 fundcode，归入 compare，只展示客观指标，不输出投资推荐或“更好”结论。
- “哪个更值得买 / 推荐哪个 / 能买吗 / 该不该买”优先归入 deny，不进入 compare。
- “哪个费率更低 / 哪个收益更高 / 哪个规模更大”未显式多 fundcode 时归入 filter；显式多 fundcode 时归入 compare。
- “同类平均”“行业均值”“同类对比均值”这类需要 `ths_similar_fund_std_avg_yield_fund` 的问题，当前 capability matrix 未开放时返回 `UnsupportedQuery(blocked_by_verification)`；字段虽存在，但周期口径未验证，不得静默只回答单基金收益。

PM 冲突预期：

- `512880和510300哪个更好`：`routing_result.type=DeniedQuery`，`recognized_query_mode=deny`，`deny_reason=investment_advice`。如果 PM 需要可执行客观对比，应改写为“对比512880和510300的规模、费率、收益率”等明确指标问法。
- `512880和510300哪个费率更低`：`routing_result.type=ExecutableQuery`，`recognized_query_mode=compare`，`ast_generation_mode=llm_ast_draft`。
- `给我推荐一只ETF`：`routing_result.type=DeniedQuery`，`recognized_query_mode=deny`，`reason=investment_advice`。

交易快照边界：

- `510300最近成交额多少` 走 `trading_metric`，使用数据库快照字段回答
- `510300今天/实时/盘中/当前成交额多少` 仍归入 `DeniedQuery`，因为当前版本不承诺实时行情
- `510300的融资余额是多少`、`510300的融券卖出量多少` 走 `trading_metric`；只有实时/盘中修饰的问法才进入 `DeniedQuery`

### 推荐 / 投资建议边界

以下问题统一归入 `DeniedQuery`：

- 推荐哪只 ETF
- 给我推荐一只 ETF
- 买哪个
- 哪个值得买
- 哪个更适合买
- 帮我选一只

原因：这些问题要求系统做投资建议或主观选择，不属于只读数据查询。

客观排序或筛选不属于投资建议，例如：

- 近一年收益率最高的 5 只 ETF
- 管理费最低的 ETF
- 规模最大的沪深300 ETF
- 列出费率低于 0.5% 的 ETF
- 申购赎回状态、能否申购、能否赎回、开着还是关着

这些应进入 filter / sort，而不是 deny。

判断边界看的是用户是否要求系统替他做选择、推荐、判断或买卖建议，不是表面是否出现“好”“买”“推荐”等词。

系统可以在 deny 文案中提示用户改成可执行筛选条件，但不得把投资建议问题自动改写为 filter 查询。

Coverage matrix 中对应“推荐一只 ETF”应标记：

```text
routing_result.type = DeniedQuery
recognized_query_mode = deny
ast_required = false
llm_ast_draft_required = false
remote_query_allowed = false
```

deny 排除：

- “能不能申赎 / 可否申购 / 可否赎回 / 申赎状态”属于 `basic_info_extended` 的申赎状态查询，不归入投资建议 deny。
- “能买吗 / 能不能买 / 值得买吗 / 该不该买 / 适合买入吗”仍归入投资建议 deny。

## 17. Formatter [Strategy]

| output_style | 输出 |
| --- | --- |
| summary | 标题行 + 关键字段列表 |
| exists | 存在性判断：是 / 否 + 最小证明字段 |
| list | 基金代码 \| 基金简称 \| 基金规模 \| 管理费率 \| 排序字段或排序标记 |
| compare | 横向表格，行为指标，列为基金 |
| report_list | 动态列：排名 \| 主字段；若 `paired_fields` 非空则追加配对列 |
| unsupported | 固定拒绝文本 |

同 collection 单 AST 形态的 `composite_single` 使用 `output_style=summary`。展示规则：

- 按 `answer_fields` 顺序逐字段展示。
- 每个字段使用其 canonical format（`amount` / `percent` / `date` / `plain` / `long_text`）。
- 长文本字段（`long_text`）截断展示，超过 200 字末尾加 `...（已截断）`。
- null 或缺失字段显示 `暂无数据`。
- answer_fields 的顺序和内容由 LLM Draft 输出、validator 基于 baseline 补齐。formatter 不做字段追加或重排。

跨 collection / multi-child 形态的 `composite_single` 没有父级单一 `output_style`。父级 orchestrator 只按 child 顺序拼接各 child formatter 输出；每个 child 保留自己的 `output_style`（例如 `summary`、`report_list`、`compare`），父级 formatter 不得把 report_list 或 compare 表压成 summary。

list formatter 规则：

- 固定列顺序为 `fundcode`、`ths_fund_extended_inner_short_name_fund`、`ths_fund_scale_fund`、`ths_manage_fee_rate_fund`
- `fundcode` 与基金简称作为主标识列，名称显示使用 `ths_fund_extended_inner_short_name_fund`
- `ths_fund_scale_fund` 显示为金额格式，`ths_manage_fee_rate_fund` 显示为百分比格式
- 若 `order_by.field` 不在前 4 列中，第 5 列显示该排序字段；若 `order_by.field` 已在前 4 列中，不新增第 5 列，而是在原列标题或值上追加排序标记（↑/↓），不得重复展示同一字段
- 若 `order_by` 为空，formatter 不得自行选择排序字段或回退字段；需要默认排序/展示字段时必须由 validator 写入 `display_order`（formatter-only），不得写入 Validated AST `order_by`
- 若 filter 明确要求额外展示字段，且该字段存在于 `selection_context.selectable_fields` 中，则必须在固定 4 列后追加展示；search 不允许追加额外字段
- null / 缺失值统一显示 `暂无数据`
- 时间序列字段必须展示 compiler 返回的 as-of `btime`；例如 `基金规模为 X（截至 YYYY-MM-DD）`
- `latest_two` 结果必须展示 current / previous / delta / direction；formatter 不自行重新计算变化方向
- report expand 为空数组、实际条数少于 `rank_limit` 或配对字段局部缺失时，按 compiler 返回结构展示实际数据和 `暂无数据`，不得报错或补齐空行
- report_list formatter 始终展示 `排名 | {expand.field 的 Registry label}`；`paired_fields` 非空时按 Registry label/format 追加配对列。quarter `report_industry` / `report_concept` 没有配对列时只展示两列。
- `report_industry` quarter variant 的标题或字段 label 必须标注为“季报行业配置 / 行业持仓”，不得暗示为重仓股明细。

formatter 只能消费：

- Validated AST 的 `answer_fields`
- Mongo result
- `output_style`
- Registry 允许的 compiler expansion metadata，例如 `performance_period_ranges`

formatter 不得：

- 根据 intent / profile 补查询字段
- 触发二次查询
- 修改 AST
- 用其他字段替代缺失字段
- 根据业务规则派生新查询结果
- 为时间序列字段补 as-of 时间或自行判断变化方向

performance 在 v3.3+ 输出：

```text
周期 | 收益率 | 同类排名 | ETF排名 | 时间范围
```

格式化规则：

- 金额类除以 1e8，保留 2 位，加“亿”
- 收益率、费率、占比保留 2 位，加 `%`
- 排名优先展示 `_fund_origin`
- null 或缺失字段显示 `暂无数据`
- performance 的“时间范围”来自 compiler 返回的 `performance_period_ranges[].display_range`；formatter 不得基于 `ths_unit_nv_fund` 自行计算，也不得用净值序列重算收益率
- 长文本字段使用原文截断展示，不做 LLM 摘要或改写；每个字段最多 200 字，超过时末尾加 `...（已截断）`
- 年报重仓无名称字段时只展示代码+占比
- 不做 LLM 摘要、不编造、不做投资判断

### V1 Baseline Answer Fields (v3.0 回归基线)

v3.0 要求保持 v1 回答 shape。Registry 确定性生成 answer_fields 时必须包含以下基线字段；可根据用户问题追加同集合 `selectable` 字段，但不得删减、替换或重排基线字段。

| intent | baseline answer_fields |
| --- | --- |
| `basic_info` | `fundcode`(plain), `ths_fund_extended_inner_short_name_fund`(plain), `ths_name_of_tracking_index_fund`(plain), `ths_fund_scale_fund`(amount) |
| `fund_scale` | `fundcode`(plain), `ths_fund_scale_fund`(amount) |
| `tracking_index` | `fundcode`(plain), `ths_tracking_index_code_fund`(plain), `ths_name_of_tracking_index_fund`(plain) |
| `performance` | `fundcode`(plain) + period 对应收益率字段(percent) + `_fund_origin`(plain) + `_etf`(number)；period=all 时展开所有周期 |
| `fee` | `fundcode`(plain), `ths_manage_fee_rate_fund`(percent), `ths_mandate_fee_rate_fund`(percent) |
| `manager` | `fundcode`(plain), `ths_fund_manager_current_fund`(plain), `ths_fund_supervisor_fund`(plain) |
| `fee_and_manager` | `fundcode`(plain), `ths_manage_fee_rate_fund`(percent), `ths_mandate_fee_rate_fund`(percent), `ths_fund_manager_current_fund`(plain), `ths_fund_supervisor_fund`(plain) |
| `dividend` | `fundcode`(plain), `ths_accum_dividend_total_amt_fund`(amount), `ths_accum_dividend_times_fund`(plain) |

format 说明：
- `plain`：原值展示，不做单位转换
- `percent`：保留 2 位小数，追加 `%`
- `amount`：除以 1e8，保留 2 位小数，追加"亿元"
- `number`：数字原值展示
- `long_text`：原文展示，不做 LLM 摘要或改写；超过 200 字截断，末尾追加 `...（已截断）`；null 或空字符串显示 `暂无数据`
- `date`：按 `YYYY-MM-DD` 原样展示；null 或空字符串显示 `暂无数据`

v3.1+ 新增 intent（search、filter、compare、report_*、manager_detail、trading_metric 等）不受此基线表约束，使用各自的 formatter 模板。

### v3.2 Baseline Answer Fields

v3.2 不改变 `basic_info` 的 v3.0 baseline。“510300 是什么”仍只展示 v3.0 基线字段；“什么时候成立 / 在哪里上市 / 业绩比较基准是什么”进入 `basic_info_extended`。

| intent | baseline answer_fields |
| --- | --- |
| `basic_info_extended` | `fundcode`(plain), `ths_fund_extended_inner_short_name_fund`(plain) + 用户明确请求的 `ths_fund_establishment_date_fund`(date) / `ths_fund_listed_exchange_fund`(plain) / `ths_perf_comparative_benchmark_fund`(plain) / `ths_pur_and_redemp_status_fund`(plain) / `ths_etf_to_code_fund`(plain) |
| `investment_profile` | `fundcode`(plain), `ths_fund_extended_inner_short_name_fund`(plain) + 用户明确请求的投资目标/范围/理念/策略/风险特征字段(long_text) |
| `manager_detail` | `fundcode`(plain), `ths_fund_extended_inner_short_name_fund`(plain), `ths_fund_manager_current_fund`(plain), `ths_fund_supervisor_fund`(plain) + 用户明确请求的任职时间线字段 |

v3.2 baseline 规则：

- 用户明确请求的字段必须进入 `answer_fields`，除非对应 gate 未通过。
- 未被用户请求的 v3.2 扩展字段不得全量追加，避免“是什么”类回答膨胀。
- `basic_info_extended` 可以一次回答成立日期、上市地点、业绩比较基准、申赎状态、联接基金中的多个字段，但不得混入投资画像或经理详情字段。

## 18. Manager Detail 规则

`manager_detail` 直接可执行。

规则：

- `manager` 只回答当前经理，使用 `ths_fund_manager_current_fund` 和 `ths_fund_supervisor_fund`
- `manager_detail` 回答任职时间线、任期、任职年化回报、管理规模
- `ths_manager` 数组按 `ths_service_sd_fund` 形成时间线；`rank_num` 只作为数组排序或展示稳定性字段，不表示第一任、最新任或现任
- 新版数据字典对 `rank_num` 同时出现“第一任”和“当前经理”两种描述，语义自相矛盾；spec 不采纳 `rank_num` 作为时间线或现任判断依据
- formatter 在标注“现任”前必须确认 `ths_fund_manager_current_fund` 与 `ths_manager[].ths_name_fund` 一致；不一致则只展示时间线
- 若 `ths_manager` 数组不可用或无法形成时间线，返回 `UnsupportedQuery(data_not_available)`
- 详情字段缺失时显示 `暂无数据`，不得用现任经理字段替代

## 19. 远端验证阻塞项

v3.3 的 report 与 manager_detail 分为 executable 与 planned blocked，并保留数据口径检查：

- 成立日期字段 `ths_fund_establishment_date_fund` 必须稳定为 `YYYY-MM-DD` 或可无损归一为该格式
- `ths_manager` 子字段必须能基于 `ths_service_sd_fund` 形成时间线结构；若数组不可用或任职起始日不可用，则 `manager_detail` 返回 `UnsupportedQuery(data_not_available)`
- `rank_num` 不是 manager_detail 的时间语义验证项
- quarter 集合 `type_num=4` 已确认为年报语义；“最新季报”是否跳过 `type_num=4`、year 集合 `type_num`、年报重仓证券名称字段的口径由 report AST 的 `report_period` 和 `expand` 校验约束
- 结构为 `tbc` 的 report 字段属于 planned blocked，返回 `UnsupportedQuery(blocked_by_verification)`，不得假设为 scalar 或 array
- yield 字段结构已确认为 scalar；同类均值字段存在但周期口径未验证，涉及同类均值能力仍按 `blocked_by_verification` 处理
- report 数据口径不存在时返回 `UnsupportedQuery(data_not_available)`，而不是 `ClarificationRequired`
- report 结果为空时才展示 `暂无数据`

### Answer Shape Regression Validator

v3.2 迁移 v3.0/v3.1 covered questions 时，必须保持旧版本 answer shape 不退化。

validator 除校验 AST 安全性外，还必须对 covered questions 执行 answer shape regression validation。

校验项：

- required baseline fields 存在。
- `answer_fields` 顺序符合 baseline。
- label 不破坏既有展示语义。
- format 符合 baseline。
- `output_style` 不变或兼容。
- generic compare 8 列 display baseline 顺序不变；field-specific compare 以用户请求字段的 provenance 为准。
- performance 周期表结构自 v3.3 起为 `周期 | 收益率 | 同类排名 | ETF排名 | 时间范围`；v3.2 回归可接受新增时间范围列，但收益率和排名字段顺序不得退化。
- list baseline 前 4 列顺序不变。

示例：

```json
{
  "answer_shape_baseline": {
    "intent": "fee",
    "answer_fields": [
      {"field": "fundcode", "format": "plain"},
      {"field": "ths_manage_fee_rate_fund", "format": "percent"},
      {"field": "ths_mandate_fee_rate_fund", "format": "percent"}
    ]
  }
}
```

规则：

- LLM 可以输出 `answer_fields`，但 validator 只能按 baseline 补齐 identity/context/display-only 字段、调整展示顺序或拒绝。
- 用户明确请求的 semantic answer field 必须出现在 LLM Draft 的 `select` 或 `answer_fields` 中；validator 不得为了保持旧 answer shape 而补出用户请求字段并计为 strict pass。
- 若 LLM 输出导致 answer shape 破坏，validator 可以修正展示字段顺序并记录 `baseline_fields_added` / `answer_fields_reordered`，或返回 validation failure；记录必须区分 `identity/context/display/semantic` additions。
- answer shape regression failure 不得由 formatter 修复。
- formatter 只能渲染 compiled projection 和 returned rows 中已有的数据，不得通过固定模板补出未查询的语义字段。

## 20. Evaluation [Test]

coverage matrix 只用于验收与回归，不代表生产问法全集。

测试通过只表示当前 Registry 覆盖范围内的 AST 生成、校验、编译、执行和格式化链路符合预期，不表示覆盖所有 ETF 自然语言问法。

### ast_generation_mode 分桶统计

测试报告必须按 `ast_generation_mode` 分桶统计，不得混算。

| ast_generation_mode | 含义 | 是否计入 v3.2 Text2SQL 成果 |
| --- | --- | --- |
| `deterministic_legacy` | legacy golden/debug/emergency fallback 路径 | 否；covered executable question 若出现该 mode 则 v3.2 验收失败 |
| `llm_ast_draft` | v3.2 LLM 完整 AST Draft 路径，且 validator/compiler/e2e 通过 | 是 |
| `llm_ast_draft_failed` | LLM 调用、JSON 解析、schema validation、validator 或 gate 失败 | 否，单独统计失败原因 |
| `blocked_by_verification` | 能力存在但被 gate、口径或结构验证拦截 | 否，单独统计，不能作为 question-level strict pass |
| `data_not_available` | 能力已开放但当前口径/数组/结果不可用 | 否，单独统计，不能作为 question-level strict pass |
| `DeniedQuery` | 明确拒绝或实时/建议/大盘类边界 | 否 |
| `ClarificationRequired` | 歧义、多候选、条件不足 | 否 |

报告必须至少输出：

```text
total_cases
deterministic_legacy_total
deterministic_legacy_debug_fallback_total
llm_ast_draft_total
llm_ast_draft_passed
llm_ast_draft_failed_total
llm_ast_draft_failed
llm_ast_draft_failure_by_stage
blocked_by_verification_total
data_not_available_total
denied_total
clarification_required_total
remote_execution_passed
formatter_passed
strict_semantic_provenance_passed
validator_semantic_addition_failed
poisoned_legacy_signal_passed
```

规则：

- 不得把 `deterministic_legacy` 的通过率合并宣称为 v3.2 Text2SQL 通过率。
- v3.2 Text2SQL 通过率只按 `ast_generation_mode=llm_ast_draft` 的用例计算。
- `llm_ast_draft_failed` 必须保留 `failure_stage` 和 `failure_reason`。
- `blocked_by_verification` 不算 LLM AST 成功；应计入独立 bucket 或 `llm_ast_draft_failed`，取决于是否已经进入 LLM Draft 路径。
- 若 LLM Draft 失败并 fallback 到 `deterministic_legacy`，可以输出 debug answer，但必须标记 `ast_generation_mode=llm_ast_draft_failed`，且该用例不通过 v3.2 验收。
- blocked、fallback、mock、dry-run、unsupported、partial answer 不计入 strict pass denominator；若报告产品健康度，必须单独分桶。

### v3.2 Coverage Gate

所有 coverage matrix 中标记为 v3.0/v3.1 covered 的 executable questions 必须满足：

- `ast_required=true`
- `llm_ast_draft_required=true`
- expected `ast_generation_mode=llm_ast_draft`
- `draft_ast -> validated_ast -> compiled_query` provenance diff 存在且无 semantic additions
- `validated_ast` 与 legacy golden query semantics 等价
- final answer shape 不低于 v3.0/v3.1 baseline
- mutation tests 删除 requested field / where / order_by / period field / sub_intent 后 validator 必须拒绝
- poisoned legacy routing signals 不影响 compiled query
- fallback 只允许改变展示层和安全字段，不允许改变 `routing_result.type`、不允许满足 `expected_outcome`，也不允许把 non-pass 用例算成 strict pass。

任何 covered executable question 在 v3.2 中通过 `deterministic_legacy` 得到成功答案，都不计为 v3.2 通过。

### v3.2 Robustness And Adversarial Acceptance [Hard]

v3.2 release 不只以 PM canonical matrix 通过为准。canonical smoke 只能证明基础路由与 AST 链路正常，不能替代对真实问法的鲁棒性验收。

必须单独覆盖并统计：

- canonical smoke
- paraphrase / synonym set
- adversarial / counterfactual set
- mutation set
- boundary set（deny / clarify / unsupported / data_not_available）

要求：

- 固定 PM 原句通过，不代表 v3.2 完成。
- paraphrase / adversarial set 必须进入 release gate，不能只作为可选回归。
- 测试集不得只包含 canonical seeds，必须覆盖同义表达、否定提示、隐式搜索、多条件筛选、排序、limit、单位归一、日期边界和复合单只完整性。
- 对 paraphrase / adversarial 用例，runtime 必须保持同一语义路由和同一 AST 约束，不得因为词面变化回退到 `single/basic_info` 或其他无关 profile。
- 测试报告必须分别统计 `seed-hit`、`paraphrase-hit`、`adversarial-hit`、`LLM-only interpretation`，不得混算。
- 任何 canonical 能过、paraphrase 失败的 capability，都不能算 v3.2 完成。

代表性 paraphrase 家族至少包括：

- 成立日期：`开张`、`开始运作`、`最早哪天`
- 上市地点：`挂牌`、`沪市`、`深市`
- 投资画像：`风险等级`、`风险原文`
- 排名：`两年期名次`、`ETF 里排到什么位置`
- 搜索：`主题`、`有关`、`名字里`、`标的指数里`

### v3.2 Coverage Floor

v3.2 必须覆盖 v3.0 / v3.1 已覆盖的 executable questions。

对于 v3.0 / v3.1 covered executable questions：

- expected `ast_generation_mode=llm_ast_draft`
- `llm_ast_draft_required=true`
- `deterministic_legacy` 只能作为 golden/debug 对照路径
- 实际运行若走 `deterministic_legacy`，v3.2 验收失败
- `deterministic_legacy` 不得作为 v3.2 covered executable question 的通过路径

例外：

- DeniedQuery / UnsupportedQuery / ClarificationRequired 不需要 AST。
- `blocked_by_verification` 不需要 AST。
- data_not_available 也不需要 AST。
- 明确标记为 later_phase 的问题不计入当前 v3.2 coverage floor。

### v3.3 Coverage Gate

v3.3 收口以 PM 问题集为 canonical smoke：`etf-query-test-questions.md` 每条原句必须在 coverage matrix 中恰好出现一次。

验收要求：

- 一到十一章全部进入 executable 或明确 `UnsupportedQuery(data_not_available)`
- 十二章只保留边界/异常语义
- v3.0/v3.1 covered executable 仍必须走 `llm_ast_draft`
- provenance diff 不允许 semantic additions
- 不允许 deterministic legacy passing path
- 结果至少分桶为 `llm_ast_draft_pass`、`llm_ast_draft_failed`、`blocked_by_verification`、`data_not_available`、`DeniedQuery`、`ClarificationRequired`

### Legacy Migration Metrics

除 v3.2 Text2SQL 通过率外，测试报告必须输出 legacy 剩余面积，用于追踪迁移进度。

```text
legacy_golden_total_cases
legacy_debug_fallback_cases
legacy_remaining_by_intent
llm_ast_draft_migrated_by_intent
migration_coverage_percent
```

定义：

- `legacy_golden_total_cases`：用于 golden baseline / diff audit 的 legacy 对照用例数。
- `legacy_debug_fallback_cases`：LLM Draft 失败后触发 debug/emergency fallback 的用例数。
- `llm_ast_draft_migrated_by_intent`：已迁移到 LLM AST Draft 的 intent / query_mode 清单。
- `migration_coverage_percent`：`llm_ast_draft` covered executable 用例数 / 当前阶段 covered executable 用例数。

规则：

- v3.2.0 可以保留 legacy 代码，但不能用 legacy 通过验收。
- `legacy_debug_fallback_cases > 0` 不阻止输出调试报告，但对应用例 v3.2 验收失败。
- `migration_coverage_percent` 在 v3.2 covered executable scope 内必须达到 100%。

### PM 测试集阶段映射

验收基准以 `etf-query-test-questions.md` 当前版本为准，不固定为旧 38 条。

`docs/v3-coverage-matrix.md` 必须覆盖 PM 测试集中的每一条问题，并标注：

- `question_id`
- `question`
- `PM bucket`
- `release_scope`
- `routing_result.type`
- `recognized_query_mode`
- `expected_intent_or_profile`
- `ast_generation_mode`
- `ast_required`
- `llm_ast_draft_required`
- `covered_by_v3_0_or_v3_1`
- `must_migrate_in_v3_2`
- `deterministic_legacy_allowed`
- `executable_in_current_phase`
- `expected_fallback_or_blocked_reason`
- `remote_query_allowed`
- `included_in_v3_2_0_smoke`
- `included_in_v3_3_report_gate`
- `expected_outcome`

规则：

- Denied / Unsupported / ClarificationRequired 必须标记 `ast_required=false`。
- v3.2 covered executable capabilities 必须标记 `llm_ast_draft_required=true`。
- `covered_by_v3_0_or_v3_1=true` 的 executable question，在 v3.2 必须 `llm_ast_draft_required=true`、`deterministic_legacy_allowed=false`。
- v3.2 新增 executable question 必须 `release_scope=v3_2_required`，除非明确标记 `later` 或 `boundary` 并给出 unsupported / boundary reason。
- `deterministic_legacy_allowed=true` 只允许 legacy debug/golden，不允许作为 v3.2 pass。
- `release_scope` allowed values 固定为 `v3_2_required | v3_3_required | later | boundary`。
- `release_scope` 是唯一 release 分母字段：`v3_2_required` 计入 v3.2 release gate 分母，`v3_3_required` 计入 v3.3 release gate 分母，`later` 和 `boundary` 不进入当前 release strict pass 分母。audit 只能按该字段机械过滤。
- 未进入当前阶段的问题不得为了通过测试而静默降级。
- 多意图或 3 段复合问题必须明确标记 `expected_outcome`。
- Coverage Matrix 是验收权威，PM bucket 不是运行时函数分发入口。

### v3.2 Canonical Verification Command [Test]

v3.2 release gate 必须有一个 canonical verification command。建议命名：

```bash
.venv/bin/python scripts/verify_v3_2_release.py
```

该命令必须至少产出：

- PM question -> coverage matrix alignment report
- Registry -> generated views reproducibility report
- `ast_generation_mode` buckets
- strict semantic provenance report
- validator negative-contract report
- poisoned legacy signal report
- schema failure report
- paraphrase / counterfactual / mutation report
- remote smoke report
- formatter provenance report

失败条件：

- PM 问题缺失、重复、改名但 coverage 未同步。
- checked-in generated views 与 Registry 重新生成结果存在 diff。
- covered executable canonical case 未达到 100% strict pass。
- 任一 strict pass 缺少 raw draft sidecar、prompt/context/registry hash 或 provenance diff。
- 任一 strict pass 出现 validator semantic addition、compiler hidden semantic expansion、formatter semantic repair。
- live remote smoke 未验证 predicate truth、sort monotonicity 或 top-N oracle。

### v3.3 Canonical Verification Command [Test]

v3.3 release gate 在 v3.2 release gate 基础上新增一个 canonical verification command。建议命名：

```bash
.venv/bin/python scripts/verify_v3_3_release.py
```

该命令必须复用 v3.2 的 PM alignment、Registry reproducibility、AST provenance、remote smoke 和 formatter provenance 检查，并额外覆盖：

- report expand：`report_period` 显式产出、TopN 展开、配对字段按 `rank_num` 对齐、空数组展示 `暂无数据`
- manager_detail：按任职起始日形成时间线，`rank_num` 不作为现任或时间语义
- timeseries：`timeseries_semantics.by_field`、独立 latest extraction、`latest_two` current/previous/delta/direction 结构
- composite：multi-child composite 每个 child 独立 LLM AST Draft，父级不得注入字段、条件、排序、报告期或时间序列语义
- trading_metric：最近成交额、净现金流、融资余额、融券卖出量按数据库时间序列快照执行；实时/盘中交易指标仍进入 deny

测试分七类：

- intent recognition tests
- deterministic parser tests
- LLM AST Draft generation tests
- AST validator/compiler tests
- remote execution smoke
- formatter tests
- end-to-end tests

v3.1+ 增加 paraphrase set 和 template fuzz set，覆盖同类改写。

v3.2 adversarial test additions:

- existence check：`000001有这只ETF吗` 应走 `exists` / minimal projection 或明确 unsupported，不得强制套 basic-info 全模板。
- name resolution：覆盖 unique fund name、ambiguous fund name、unresolved name、follow-up 选择候选后重新走 `llm_ast_draft`。
- date filters：覆盖 exact date、after date、before date、between、earliest、latest。
- subscription boundary：`能申购吗/能赎回吗` executable；`能买吗/该不该买` deny。
- objective ranking vs advice：`哪只费率更低/收益更高` executable；显式多 fundcode 的 `哪个更好` 仍属于投资建议边界并 deny；`推荐哪只` deny。
- semantic search：增加无“搜索/找/名字包含”等显式触发词的搜索问法，以及 tracking-index search/filter 边界。
- partial entity compare：部分 fundcode 无效时必须输出 found/missing lists，不得呈现为普通完整 compare。
- field ambiguity：相似字段、同义但不同字段、缺少 canonical seed 的 paraphrase 必须分开统计 seed-hit / paraphrase-hit / LLM-only interpretation。

v3.3 adversarial test additions:

- manager_detail：`rank_num` 被误当时间线或现任依据时必须失败；时间线必须按任职起始日。
- manager：普通当前经理问法误选经理历史数组时必须失败。
- report：标量字段错误生成 `expand`、数组字段缺少 `expand`、TopN 配对字段未按 `rank_num` 对齐时必须失败。
- report 空数据：空数组、实际 TopN 少于上限、配对字段局部缺失不得导致 compiler failure，formatter 展示 `暂无数据`。
- timeseries：用户指定日期但 LLM 漏掉 specified 时 validator 不得补；多时间序列字段只输出部分 `by_field` 时记为 `semantic_repair` 且 strict pass 失败。
- latest_two：份额变化问法必须返回 current / previous / delta / direction；formatter 不得自行计算方向。
- composite：父级注入字段、条件、排序、报告期或 `timeseries_semantics` 必须失败；`composite_single` validator 按 profile baseline 补语义字段必须失败。
- routing：composite 子意图 paraphrase 不得只靠固定关键词识别。
- trading：交易快照被误拒绝、实时行情被误放行都必须失败。

period paraphrase set 从 v3.1 开始进入验收：

| period | paraphrase examples |
| --- | --- |
| `3m` | 近3个月、过去三个月、最近一个季度、这三个月、前三个月 |
| `6m` | 近半年、这半年、最近半年、过去六个月、半年来 |
| `ytd` | 今年以来、年初以来、今年到目前、今年到现在 |
| `std` | 成立以来、成立到现在、成立至今、上市以来 |
| `unknown` | 这段时间、最近、这阵子 |

验收规则：

- 有明确时间表达的 period 归一准确率目标 95%+。
- ambiguous/unknown case 不允许静默默认成 `1y`。
- 所有 LLM fallback 输出必须带 `evidence`，且 `evidence in question`。
- LLM Draft AST 中必须出现 Registry 允许的 period-specific fields；本地 period parser / `PERIOD_FIELDS` 只能作为 evidence、normalization catalog 或 validator consistency check，不得在 Draft 缺失时生成核心 performance 字段并计为 strict pass。

阶段黄金集：

- canonical smoke 以 `etf-query-test-questions.md` 每条原句为准
- v3.0/v3.1 covered executable 继续作为 strict pass 基线
- v3.2/v3.3 新增能力分别按 canonical smoke、paraphrase/fuzz、mutation 三类统计
- 不再用拍脑袋数量定义 v3.2/v3.3 黄金集上限

阶段门禁：

- v3.0：13/13 v1 回归，AST/Mongo/shape 全 100%
- v3.1：smoke 全 100%
- v3.2：covered executable questions `llm_ast_draft` 100%
- v3.3：canonical smoke 全 100%，并跑 composite/report/manager_detail/trading_metric

v1 13 条回归的 expected answer shape 在 v3.0 锁定；若 formatter 升级导致 shape 变化，必须同步更新回归基线。

每条黄金集记录：

```text
question
expected intent recognition result
expected generation_context
expected LLM AST Draft
expected AST
expected semantic AST constraints
expected provenance diff constraints
expected Mongo params
expected operation
expected pipeline / computed_fields（若适用）
expected output_style
expected answer_fields
expected answer shape
answer value policy
是否依赖真实远端数据
```

黄金集不得要求 raw LLM Draft JSON 精确相等作为唯一 oracle。验收应优先比较 semantic AST constraints、validated AST 和 compiled query 语义；raw draft 必须完整保存用于审计。

`expected Mongo params` 固定结构：

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {},
  "projection": {},
  "sort": [],
  "limit": 10
}
```

若 query 需要受限 aggregation，则 `expected operation=pipeline`，并记录受限 `pipeline` / `computed_fields`；不得把 aggregation 回退成仅 filter/sort 的假实现。

report latest 必须记录编译后的 `sort` 与 `limit=1` 选择逻辑。

answer value policy：

- 稳定字段精确匹配
- 波动字段校验格式、字段存在、日期/报告期合理
- 需要精确值时使用固定快照或当天基准结果

### PM Test Alignment / Known Gaps

以下问题若超出当前 Registry 能力或数据口径，不得通过静默降级回答硬过测试：

- `benchmark` 不单独开 canonical intent，默认作为 `basic_info` / base profile 的扩展字段处理；若该 profile 未放行，则返回 `UnsupportedQuery`
- `什么时候换的基金经理` 固定归入 `manager_detail`；数组无法基于任职起始日形成时间线时返回 `UnsupportedQuery(data_not_available)`
- `份额最近有变化吗` 在份额字段确认为 `[{value,btime}]` 后归入 `fund_scale` + `timeseries_semantics.latest_two`；否则返回 `UnsupportedQuery(blocked_by_verification)`
- 同一 fundcode 下的通用 3 intent merge 不做隐式合并；需要时应走显式 composite 或返回 `UnsupportedQuery(data_not_available)`
- PM 测试集中要求的能力若未进入 Registry，不得通过部分字段回答替代完整结果

PM `十.7 510300成立以来收益怎么样，分过红吗` 必须在 coverage matrix 中标为 `ExecutableQuery` + `recognized_query_mode=single` + `expected_intent_or_profile=composite_single` + `ast_generation_mode=llm_ast_draft`。

## 21. Canonical Seed List

以下 seed 是 v3 核心路由种子，配置文件只能追加同义词，不得删除、覆盖或改变其目标 intent。外部配置只允许追加 `extra_seeds`，不得覆盖 `canonical_seeds`。测试和 review 以 spec 中的 canonical seed list 为基线。PM 业务桶不直接参与这张表的定义。

Canonical seeds 只能用于候选召回、测试审计和最小语义锚点；不得作为 sufficient condition 决定最终 `query_mode` / `intent` / `field_profile`。最终执行结构必须来自 LLM Draft AST，并通过 `routing_evidence` 与 provenance diff 审计。

| intent / route | canonical seeds |
| --- | --- |
| `basic_info` | 是什么、介绍、基本信息、概况、单独基金代码 |
| `basic_info_extended` | 成立日期、什么时候成立、上市地点、上市交易所、在哪里上市、业绩比较基准、申赎状态、能不能申赎、联接基金、有没有联接基金 |
| `fund_scale` | 规模、盘子、多大、资产规模、总市值 |
| `tracking_index` | 跟踪、跟的、标的指数、指数名称、指数代码 |
| `performance` | 收益、收益率、表现、回报、涨、跌、涨跌、排第几、排多少、排名第几、今年、近1周、近1月、近1年、成立以来、各周期 |
| `fee` | 管理费、托管费、费率、费率最低 |
| `manager` | 基金经理、谁在管、管理人 |
| `manager_detail` | 管理了多久、任职、任职天数、任职起始日、任职年化回报、管理规模、历史业绩 |
| `fee_and_manager` | 费率和基金经理、费率以及谁在管 |
| `dividend` | 分红、分红记录、累计分红、分红次数、分过红、分过几次、分了几次、分了多少钱 |
| `trading_metric` | 最近成交额、净现金流、融资余额、融券卖出量 |
| `search` | 搜索、帮我找、找一下、有没有名字叫、名字里带、相关 ETF |
| `filter` | 筛选、前 N、最高、最低、大于、小于、股票型、债券型、上交所、深交所、哪个费率更低、哪个收益更高、哪个规模更大 |
| `compare` | 对比、比较、vs、和...比、显式多个 fundcode 并列 |
| `investment_profile` | 投资目标、投资范围、投资理念、投资策略、风险收益特征 |
| `report_industry` | 持仓行业、行业配置、前 N 大行业、季报持仓 |
| `report_concept` | 重仓概念、概念持仓、题材 |
| `report_holding` | 前十大、重仓股、重仓证券、年报持仓 |
| `institution_holding` | 机构持有、机构持仓、机构投资者比例、机构持有份额 |
| `report_style` | 投资风格、风格 |
| `report_nav_change` | 净资产变动、净资产变化 |
| `unsupported/deny` | 今日涨跌、实时净值、推荐哪只、推荐、给我推荐、能买吗、个股分析、大盘、A股、上证、深证、盘中、实时、当前 |

## 22. Generated Views [Read Only]

以下内容均由 Executable Capability Registry 生成，仅用于展示、测试和审计，不作为独立维护源：

1. `recognized_query_mode / intent / output_style / from` Query Classification Matrix
2. 字段能力矩阵，包含 profile、operator、operator_gate、normalizer、`semantic_role`、`selectable`、`sortable`、`fuzzy_searchable`、`array_expandable`
3. 单位、日期、枚举、排序方向、period 归一表
4. `report_period` 与 `expand` JSON schema
5. deny intent 关键词/模式表
6. 分阶段 smoke/golden 验收表
7. 分阶段 smoke 明细表：question、阶段、预期 recognized_query_mode、预期行为、是否允许远端查询、失败即阻塞
8. intent recognition 触发词和优先级表
9. v3.1 period paraphrase set 与受限 period fallback 校验表
10. PM coverage bucket -> runtime profile 映射表（reference only）
11. selection_context JSON schema
12. field_profile -> selectable_fields / semantic_roles / baseline_answer_fields 映射表

规则：

- 以上各表均由 Registry 派生，不得作为独立维护源。
- 任何变更先改 Registry，再由 Registry 重新生成这些视图。
- 若视图与 Registry 冲突，以 Registry 为准。
- CI 必须重新生成以上视图并与 checked-in 文档比较；存在 diff 时 release gate 失败。
- Coverage Matrix 必须通过 parser-based alignment check 验证每条 PM question 恰好出现一次。

## 23. v3.2 Implementation Gap Checklist

v3.2.0 开工必须完成：

- [ ] 替换字段选择器式 `ast_generator.py`，实现 full AST Draft generator（输出全部 11 个顶层字段）
- [ ] Registry 增加 v3.2 capabilities（`basic_info_extended`、`investment_profile`、`manager_detail`、`composite_single`）
- [ ] Registry 增加 field-level operator / value_schema / normalizer / gate
- [ ] Registry 增加 field-level `semantic_role`，并由 generated view 暴露
- [ ] 实现 `generation_context` builder（`where_constraints`、`field_operators`、`limit_policy`）
- [ ] 实现 gate state loader 与 blocked 过滤
- [ ] Implement `routing_signals` vs `llm_draft_evidence` split.
- [ ] 实现 filter evidence builder（raw_evidence、candidate_fields、value_candidates、normalizer）
- [ ] Implement field evidence disambiguation validation.
- [ ] Implement normalized value override recording.
- [ ] Define and implement performance period evidence handling.
- [ ] Implement composite child `generation_context` builder.
- [ ] Implement answer shape regression validator.
- [ ] Add dependency-aware migration test stages.
- [ ] 实现 Draft AST -> Validated AST value normalization（raw literal → 标准值 + `raw_value`）
- [ ] validator 输出 `baseline_fields_added` / `validator_applied_defaults`，并按 `identity/context/display/semantic` 分类
- [ ] runtime 输出 `capability_id` / `capability_status` / `gate_status` / `capability_status_reason`
- [ ] runtime 输出 `draft_ast -> validated_ast -> compiled_query` provenance diff
- [ ] validator negative-contract tests：删除 requested field / where / order_by / period field / sub_intent 后必须拒绝
- [ ] poisoned legacy signal tests：`legacy_filters` / `legacy_sort_hint` / `legacy_limit_hint` 不影响 strict compiled query
- [ ] formatter provenance tests：formatter 不得补出 compiled projection 未查询的语义字段
- [ ] query result 输出 `ast_generation_mode`
- [ ] 测试报告按 `ast_generation_mode` 和 legacy migration metrics 分桶
- [ ] `build_v3_ast` covered intents migrated to `llm_ast_draft`
- [ ] `build_v3_1_ast` search migrated to `llm_ast_draft`
- [ ] `build_v3_1_ast` filter migrated to `llm_ast_draft`
- [ ] `build_v3_1_ast` compare migrated to `llm_ast_draft`
- [ ] covered composite child ASTs migrated to `llm_ast_draft`
- [ ] deterministic_legacy retained only as golden/debug fallback
- [ ] `classify_v3_query` 支持 v3.2 single intents 的前置识别（`basic_info_extended`、`investment_profile`、`manager_detail`）
- [ ] `semantic_query_v3` 主流程为 v3.0/v3.1 covered capabilities 和 v3.2 新增能力走 `llm_ast_draft` 路径
- [ ] `llm_ast_draft` 失败不静默 fallback 到 `deterministic_legacy`

### 修订原则

```text
v3.2 可以保留 legacy 代码，但不能用 legacy 通过验收。
v3.2 必须让 v3.0/v3.1 已覆盖的 executable questions 全部走 LLM full AST Draft。
v3.2 新增 executable questions 也必须走 LLM full AST Draft。
```
