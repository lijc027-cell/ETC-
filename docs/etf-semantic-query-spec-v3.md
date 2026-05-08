# ETF Text2SQL v3 技术规格

> 状态：草案
> 目标：用 Text-to-Query AST 替代 v1 query plan，在保持 v1 回归稳定的基础上，分阶段扩展搜索、筛选、对比、base 扩展字段和报告展开能力。

## 1. 核心原则

v3 不让 LLM 生成可执行 SQL / PyMongo 字符串。

本规格中的 Text2SQL 指自然语言到结构化查询的转换，不要求输出 SQL 字符串。由于目标执行层是 MongoDB，v3 的“SQL”形态是受限 AST：LLM 的主要产物必须是查询结构（`select`、`from`、`where`、`order_by`、`limit`、`answer_fields`），而不是函数名、业务分支名或最终答案。

目标链路：

```text
自然语言
  -> recognized_query_mode / deny / clarify 分类
  -> 实体、period、条件、报告期解析
  -> 必要时名称反查
  -> LLM 生成受限 AST
  -> 本地归一和校验
  -> AST 编译为 Mongo 查询
  -> SSH 远端只读执行
  -> 本地 formatter 输出
```

LLM 只负责生成 AST。执行、校验、格式化、拒绝策略全部由本地确定性代码完成。

Hard 层定义不可变协议；Strategy 层定义当前版本默认值；Test 层只用于验收和回归，不代表生产问法全集。生产路由允许同义归一与 paraphrase，coverage matrix 不作为唯一路由依据。

PM 文档里的业务桶是覆盖分组，不是运行时函数分发入口。v3 仍然是 text-to-AST 系统：`query_mode` 负责路由，`intent` 负责语义模板，`field_profile` / `answer_fields` 负责字段展示约束，最终都必须落到同一条 AST -> Mongo 编译链路。

判断一项实现是否仍属于 Text2SQL，以以下标准为准：

- LLM 输出查询结构，而不是直接输出答案。
- `query_mode` / `intent` 只约束 AST 形态，不触发预封装业务函数。
- 所有可执行查询都经过统一 AST validator 和 Mongo compiler。
- 字段、条件、排序、limit 必须能从 AST、`entity_hints` 或本地归一规则解释。
- 若实现变成 `if intent == ...` 后直接调用固定业务函数并绕过 AST/compiler，则不符合 v3 Text2SQL 主线。

### 1.1 Scope Of Satisfaction [Hard]

本规格中的“满足需求”只在当前版本开放范围内成立：

1. 对 `etf-query-test-questions.md` 中属于当前阶段开放范围的问题，系统应按阶段门禁达到目标准确率。
2. 对当前阶段未开放但已规划的问题，系统必须返回 `UnsupportedQuery` 或阶段说明，不得伪造结果。
3. 对明确排除的问题，包括实时行情、交易指标、技术分析、投资建议、个股分析，系统必须返回 `DeniedQuery`。
4. 对字段矩阵未覆盖、远端验证未通过、名称歧义或条件不足的问题，系统必须走 `UnsupportedQuery` 或 `ClarificationRequired`。
5. 本规格不承诺覆盖所有 ETF 自然语言问题；生产泛化通过 paraphrase set、template fuzz set、日志回流和 registry 扩展逐步提升。

## 2. 非目标

v3 不支持：

- 执行 LLM 生成的 SQL / PyMongo 代码
- 通过 intent dispatch 直接调用预封装业务函数并绕过 AST/compiler
- 数据库写入、更新、删除
- OR 条件暴露给 AST
- 跨集合 join
- 实时行情、交易指标、技术分析、投资建议、个股分析
- LLM 自由总结、投资判断、字段外推

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
- 对比：base 集合固定 8 列
- 派生对比通过 orchestrator 两步执行
- 增加 Normalization Enhancement：period paraphrase set 与受限 period 归一 fallback
- v3.1 起，`single` 仍是单只 ETF 的 query_mode，但它不是“任意字段自由选择”的函数入口；single 的 AST 仍受 canonical intent / field_profile 约束

### v3.2 Base 扩展字段

- 成立日期、净值、业绩基准
- 申赎状态、联接基金
- 投资目标、范围、理念、策略、风险特征
- 基金经理详情
- 长文本截断展示

### v3.3 报告展开

- report_* 仅在远端验证通过后开放
- `latest`、`type_num`、报告 array 字段、年报证券名称字段的可用性必须完成验证后才能进入 `intent_candidates`
- 未验证通过前，相关 report intent 保持 blocked
- 验证通过后支持季报行业/重仓概念，以及年报重仓证券代码+占比、行业占比、机构持仓、投资风格、净资产变动
- 验证通过后支持 latest / 指定报告期，以及 array 按 `rank_num` 展开和字段配对

### 3.4 PM Coverage Buckets -> Runtime Profiles [Reference Only]

PM `etf-query-test-questions.md` 的“意图”列是业务覆盖桶，不是运行时 AST intent 输入。它用于组织测试、验收和需求沟通，不直接驱动函数分发。

| PM bucket | v3 query_mode | v3 canonical intent / profile | 说明 |
| --- | --- | --- | --- |
| 基本信息 | single | `basic_info` / `tracking_index` / `fee` / `manager` / `fee_and_manager` | 单只 ETF 标量字段查询，仍由 AST 生成字段集合 |
| 收益率与排名 | single | `performance` | 同一语义模板下按 period 选择字段 |
| 规模净值份额 | single | `fund_scale` | 规模、总市值、单位净值、份额、净值增长率统一归入单只查询模板 |
| 持仓信息 | report | `report_industry` / `report_concept` / `report_holding` / `institution_holding` | 需 report 远端验证通过后开放 |
| 基金经理 | single | `manager` / `manager_detail` | `manager_detail` 为 v3.2 扩展 profile，不是函数分发 |
| 分红 | single | `dividend` | 累计分红总额与次数 |
| 搜索 ETF | search | `search` | 只改变查询模式，不调用预封装函数 |
| 条件筛选 | filter | `filter` | 通过 AST where/order_by 表达筛选条件 |
| 多只对比 | compare | `compare` | 固定对比模板，不走业务函数 |
| 复合意图 | composite | orchestrator 外层 | 组合多个 AST，不是单一 intent |
| 交易指标 | deny | `DeniedQuery` | 明确不支持 |
| 边界异常 | deny/unsupported | `DeniedQuery` / `UnsupportedQuery` | 按前置识别和阶段白名单处理 |

PM bucket 只定义“该问句属于哪个覆盖组”，不定义“调用哪个预封装函数”。运行时唯一执行路径仍是 AST 生成、校验、编译与执行。

#### PM 映射与运行时约束

- `canonical intent` 是 `field_profile` 的标识符，不是独立函数入口。
- 同一个 `query_mode=single` 下，不同 intent 的差异只体现在字段子集、baseline answer_fields、默认格式/排序规则。
- AST 生成、校验、编译链路完全相同，不因为 PM bucket 改变执行路径。
- 以上 PM 映射是全集覆盖映射，不是当前阶段可执行清单；能否执行只取决于 Section 3.5 Executable Capability Registry。

阶段 intent 白名单：

| 阶段 | allowed intents | blocked intents |
| --- | --- | --- |
| v3.0 | basic_info, fund_scale, tracking_index, performance, fee, manager, fee_and_manager, dividend | 其余全部 |
| v3.1 | v3.0 + search, filter, compare | report_*, manager_detail, investment_profile, subscription_redemption, linked_fund |
| v3.2 | v3.1 + manager_detail, investment_profile, subscription_redemption, linked_fund | report_* |
| v3.3 | v3.2 + report_*（仅 `verification_passed=true` 后开放） | 未验证通过的 report_* |

阶段白名单是 Executable Capability Registry 的阶段视图；运行时可用能力以 Section 3.5 Registry 为唯一真源。未在当前阶段白名单中的 intent 不进入 `intent_candidates`，不进入 AST。

v3.3 阶段不等于 report 自动开放；report intent 进入 `intent_candidates` 的前提是对应远端验证项通过。

**Blocked intent 回退规则：** 当最佳匹配 intent 不在当前阶段白名单时，按以下优先级回退。回退分为 same-mode fallback 和 non-AST fallback。

| blocked intent | fallback type | 回退行为 | 说明 |
| --- | --- | --- | --- |
| `manager_detail` | same-mode | 回退到 `manager` | 保留 `recognized_query_mode=single`；返回现任基金经理 + 基金管理人，不返回任期/历史业绩 |
| `investment_profile` | non-AST | `UnsupportedQuery` | v1 无对应能力，不生成 AST |
| `subscription_redemption` | non-AST | `UnsupportedQuery` | v1 无对应能力，不生成 AST |
| `linked_fund` | non-AST | `UnsupportedQuery` | v1 无对应能力，不生成 AST |
| `report_industry` | non-AST | `UnsupportedQuery` | v1 无对应能力或 report 验证未通过，不生成 AST |
| `report_concept` | non-AST | `UnsupportedQuery` | v1 无对应能力或 report 验证未通过，不生成 AST |
| `report_holding` | non-AST | `UnsupportedQuery` | v1 无对应能力或 report 验证未通过，不生成 AST |
| `institution_holding` | non-AST | `UnsupportedQuery` | v1 无对应能力或 report 验证未通过，不生成 AST |

same-mode fallback 只缩小能力范围（少返回字段），不改变 `recognized_query_mode`。non-AST fallback 不保留可执行 query mode，不进入 AST，不进入 compiler。

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
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"}
  ],
  "gate": "always"
}
```

规则：

- `intent_candidates`、`from_candidates`、`selection_context` 必须全部由 Registry 生成。
- Section 3 是 Registry 的阶段视图。
- Section 4 是 Registry 的路由视图。
- Section 14 是 Registry 的字段能力视图。
- Section 3.4 PM Coverage Buckets 是测试覆盖视图，不是运行时视图。
- 若文档表之间冲突，以 Registry 为准。
- Registry 的 `gate` 允许值为 `always | verification_passed | blocked`。
- 未满足当前 `phase` 或 `gate` 的能力不得进入 LLM prompt。

## 4. Query Classification [Hard]

`recognized_query_mode` 是前置识别结果，不由 LLM 输出，也不属于 AST 字段。

识别白名单：

```text
single | search | filter | compare | report | deny
```

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

| recognized_query_mode | intent | output_style | from | first_enabled_phase | gate |
| --- | --- | --- | --- | --- | --- |
| single | basic_info | summary | tb_ths_etf_base | v3.0 | always |
| single | fund_scale | summary | tb_ths_etf_base | v3.0 | always |
| single | tracking_index | summary | tb_ths_etf_base | v3.0 | always |
| single | performance | summary | tb_ths_etf_base | v3.0 | always |
| single | fee | summary | tb_ths_etf_base | v3.0 | always |
| single | manager | summary | tb_ths_etf_base | v3.0 | always |
| single | fee_and_manager | summary | tb_ths_etf_base | v3.0 | always |
| single | dividend | summary | tb_ths_etf_base | v3.0 | always |
| single | manager_detail | summary | tb_ths_etf_base | v3.2 | always |
| single | investment_profile | summary | tb_ths_etf_base | v3.2 | always |
| single | subscription_redemption | summary | tb_ths_etf_base | v3.2 | always |
| single | linked_fund | summary | tb_ths_etf_base | v3.2 | always |
| search | search | list | tb_ths_etf_base | v3.1 | always |
| filter | filter | list | tb_ths_etf_base | v3.1 | always |
| compare | compare | compare | tb_ths_etf_base | v3.1 | always |
| report | report_industry | report_list | tb_ths_etf_report_quarter | v3.3 | verification_passed |
| report | report_concept | report_list | tb_ths_etf_report_quarter | v3.3 | verification_passed |
| report | report_holding | report_list | tb_ths_etf_report_year | v3.3 | verification_passed |
| report | institution_holding | report_list | tb_ths_etf_report_year | v3.3 | verification_passed |

`first_enabled_phase` 和 `gate` 只是 Registry 的镜像字段；`gate` 固定枚举为 `always | verification_passed | blocked`。PM bucket 不是这张矩阵的输入源，只是覆盖映射层。

规则：

- Intent Recognition 是执行路由的唯一权威来源；LLM AST 只能补全查询结构，不能改变 `recognized_query_mode`、扩大 intent/from 候选范围，不能绕过 deny/clarify。
- `intent_candidates` 进入 LLM prompt 前，必须先经过 Registry 过滤后的当前阶段白名单和 gate 过滤。
- Query Classification Matrix 冲突直接失败，不执行。
- intent alias 只允许本地归一。
- `unsupported` AST 只作 LLM 兜底识别，不进入 Mongo compiler。
- 表内 `gate` 仅为 Registry gate 的镜像字段；枚举固定为 `always | verification_passed | blocked`，不在表内表达自然语言条件。
- `selection_context` 不是 Intent Recognition 的输出，而是 Registry 裁剪后的 LLM generation input。

LLM 生成 AST 时必须接收前置识别结果作为约束上下文：

```text
recognized_query_mode
intent_candidates
from_candidates
entity_hints
selection_context
```

LLM 只能在 `intent_candidates` 和 `from_candidates` 内选择；`selection_context.selectable_fields` 决定可生成的字段范围，LLM 不得越界。

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
  "reason": "unclassified | blocked_by_phase | blocked_by_verification | unsupported_domain",
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
- `options` 按候选质量降序排列：`kind=fund_candidate` 按规模（`ths_fund_scale_fund`）desc，`kind=report_period` 按 `year_num desc, type_num desc`，`kind=filter_value` 和 `kind=free_text` 保持原始顺序
- 候选总数超过 5 个时，`has_more=true`；未超过时，`has_more=false`
- `options` 保留质量最高的 5 个，不保留完整候选集；被截断的候选不再暴露
- 被截断候选不进入 `state_id` 对应状态；后续只能基于已返回的 `options[].id` 回绑
- `has_more` 是顶层布尔字段，表示是否还有未展示的候选
- `options[].id` 用于后续回传
- `options[].kind` 标识候选类型，允许 `fund_candidate`、`report_period`、`filter_value`、`free_text`
- `options[].value` 保存机器可回绑的结构化值
- `options[].fundcode` / `thscode` 仅在 `kind=fund_candidate` 时优先用于直接回绑
- `label` 只负责展示，不作为唯一键
- `state_id` 用于后续补充输入关联

## 5. Intent Recognition [Hard + Strategy]

前置识别输出：

```text
recognized_query_mode
intent_candidates
from_candidates
entity_hints
composite_hint
deny_reason
```

`entity_hints` 结构：

```json
{
  "fundcodes": [],
  "name_query": "",
  "period": "1y | ytd | std | all | null",
  "filters": [
    {"field": "ths_fund_invest_type_fund", "op": "eq", "value": "股票型"}
  ],
  "sort_hint": {"field": "ths_fund_scale_fund", "direction": "desc"},
  "limit_hint": null,
  "report_period_hint": null,
  "search_keyword": ""
}
```

`selection_context` 结构：

```json
{
  "field_profile": "performance",
  "selectable_fields": ["fundcode", "ths_yeild_1y_fund"],
  "allowed_formats": ["plain", "percent", "amount", "number"],
  "baseline_answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"}
  ]
}
```

- `fundcodes`：从用户问题中抽取的 6 位基金代码列表，compare 场景可包含多个
- `name_query`：名称反查的原始查询文本，无 fundcode 时填充
- `period`：从用户问题中解析的 performance 周期，非 performance 意图时为 null
- `filters`：从用户问题中抽取的结构化筛选条件（分类词、数值比较等），由本地归一规则填充，LLM 不直接生成
- `sort_hint`：从排序短语表中匹配的排序方向
- `limit_hint`：用户显式指定的 N，如"前5只"中的 5
- `report_period_hint`：报告期相关表达，仅 report intent 时填充
- `search_keyword`：从用户问题中预提取的搜索关键词，LLM 可据此填充 `__search_text__` 的 value
- `selection_context.field_profile`：运行时语义模板标识，由 `query_mode + canonical intent` 共同决定，用于约束可选字段、baseline answer_fields 和格式规则；它不属于 AST 字段，也不代表预封装业务函数
- `selection_context.selectable_fields`：当前 profile 允许的可选字段子集
- `selection_context.allowed_formats`：当前 profile 允许的展示格式集合
- `selection_context.baseline_answer_fields`：该 profile 的最低展示字段要求，由 validator 自动补齐

识别优先级：

1. deny：实时行情、交易指标、技术分析、投资建议、个股分析。
2. compare：对比、比较、vs、和...比，且需要显式多 fundcode。
3. report：持仓、行业、概念、前十大、机构持仓、投资风格。
4. search/filter：搜索、找、筛选、前 N、最高、最低、大于、小于、分类词、哪个费率更低、哪个收益更高、哪个规模更大。
5. single：单只基金代码或可解析名称。
6. unsupported/clarify：无法归类、歧义、条件不足。

路由边界：

- “哪个费率更低 / 哪个收益更高 / 哪个规模更大”未显式多 fundcode 时归入 filter；显式多 fundcode 时归入 compare。
- “哪个好 / 哪个更值得买 / 推荐哪个”归入 deny。
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

## 6. AST Schema

```json
{
  "intent": "performance",
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
  "report_period": null,
  "expand": null
}
```

字段语义：

| 字段 | 说明 |
| --- | --- |
| `intent` | 业务意图 |
| `from` | Mongo 集合 |
| `select` | 语义字段，不等于最终 Mongo projection |
| `where` | 条件数组，固定 AND |
| `order_by` | 单字段排序或 null |
| `limit` | 返回条数，1-50 |
| `output_style` | formatter 模板 |
| `answer_fields` | 展示字段、标签、格式 |
| `report_period` | 报告期规则 |
| `expand` | 报告 array 展开规则 |

约束：

- AST 不支持 OR。
- `where` 必须是数组。
- `select` 不得被 compiler 回写污染。
- Mongo `projection` 由 compiler 另行生成。
- `intent`、`from`、`output_style` 必须符合前置 `recognized_query_mode` 的候选范围。
- `where`、`order_by`、`limit` 必须能从 `entity_hints`、用户原文或归一化规则中解释；无法解释时校验失败。
- 除 compare 外，`answer_fields` 不能为空。
- `answer_fields[].field` 必须是 `select` 子集。
- compare 允许 `answer_fields=[]`，但校验层必须补齐固定 8 列。
- compare 永远展示固定 8 列，不支持用户指定子集展示。
- report 模式下 `order_by` 必须为 `null`。

### 6.1 LLM Field Selection (v3.1+)

v3.1 起，`recognized_query_mode=single` 时，LLM 只能在 `selection_context` 约束内生成 `select` 和 `answer_fields`。这不是预封装函数调用，而是受限 AST 字段生成。

LLM 输入：

- `entity_hints`：`fundcodes`、`period`、`name_query`
- `selection_context.field_profile`
- `selection_context.selectable_fields`
- `selection_context.baseline_answer_fields`
- `selection_context.allowed_formats`

LLM 输出：

```json
{
  "select": ["fundcode", "ths_yeild_1y_fund"],
  "answer_fields": [
    {"field": "fundcode", "label": "基金代码", "format": "plain"},
    {"field": "ths_yeild_1y_fund", "label": "近1年收益率", "format": "percent"}
  ]
}
```

校验规则：

1. `select` 必须是 `selection_context.selectable_fields` 的子集
2. `answer_fields[].field` 必须是 `select` 的子集
3. `selection_context.baseline_answer_fields` 由 validator 自动补齐，不依赖 LLM
4. `format` 必须属于 `selection_context.allowed_formats`
5. `select` 不得包含 report 集合字段
6. 校验失败 -> 直接失败，不进入 compiler

Selection Context 规则：

- `selection_context` 由 Registry 裁剪生成。
- LLM 不得修改 `selection_context.field_profile`。
- LLM 不得读取全量 Capability Matrix，只能读取 `selection_context.selectable_fields`。
- Validator 使用同一个 `selection_context` 校验 `select` 和 `answer_fields`。
- 字段补齐只能由 validator 根据 `baseline_answer_fields` 执行，不由 formatter 临时补齐。

performance 特殊规则：

- `entity_hints.period` 非空时，LLM 必须选择对应周期的收益率字段 + 排名字段
- `period=all` 时选择全部周期字段
- 排名字段优先选择 `_fund_origin`（展示）和 `_etf`（ETF 排名）；数字型 `_fund` 排名仅用于排序，不作为展示字段
- 校验层若发现 period 对应字段缺失，应自动补齐 baseline 要求字段，再重新校验

## 7. Operator 规则

`op` 白名单：

```text
eq | in | contains | gt | gte | lt | lte
```

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

- 仅允许 `intent=search`
- LLM 负责从用户问题中提取搜索关键词填入 `value`；value 是普通字符串，最长 30
- 若 `entity_hints.search_keyword` 非空，validator 优先使用该值覆盖 AST 中 `__search_text__` 的 `value`；LLM value 仅作为无本地关键词时的补充
- 本地校验层二次清洗：去泛词（`ETF`、`基金`、`指数`、`相关`、`搜索`、`找一下`、`有没有`、`名字里带`、`名字叫`）+ trim 空白
- 清洗后长度 < 2：退回原词再判；原词仍无有效关键词时拒绝 AST，返回 `ClarificationRequired`
- compiler 内部用 `re.escape(value)` 生成 regex
- compiler 内部展开受控多字段 OR，AST 仍不支持 OR

搜索字段限：

```text
ths_fund_extended_inner_short_name_fund
ths_name_of_tracking_index_fund
ths_tracking_index_code_fund
```

## 8. Compiler Rules [Hard]

真实 Mongo projection 自动包含：

```text
select
+ where.field
+ order_by.field
+ report period fields
+ expand.field
+ expand.display_fields[].field
```

formatter 只展示：

```text
answer_fields
或 expand.display_fields
```

辅助字段不得展示。

说明：

- `tb_ths_etf_base` 里有一批字段在真实 Mongo 中实际存成 `[{value, btime}]` 时间序列数组；这些字段在展示和大部分本地排序场景里统一取最新 `btime` 对应的 `value`。
- `tb_ths_etf_report_quarter` / `tb_ths_etf_report_year` 里的数组字段则按 `rank_num` 展开，不做时间序列折叠。

默认规则：

- `limit` 优先级：
  1. 用户显式指定 N：`limit = min(N, 50)`
  2. 用户说“所有”：`limit = 50`，并在答案说明最多展示前 50 条
  3. 普通 search：`limit = 20`
  4. 普通 filter：`limit = 10`
  5. compare：显式最多 10，派生默认 5
- search 默认排序：
  - `ths_fund_scale_fund desc`
- filter 无排序时按 `ths_fund_scale_fund desc`
- `ths_fund_scale_fund` 必须在 v3.1 进入 `selectable` 和 `sortable`

## 9. Compare Rules [Strategy]

compare 默认固定 8 列：

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

- v3.1 默认 8 列；当前阶段（v3.0-v3.3）固定 8 列，不做运行时扩展。
- 显式 compare 使用 `fundcode in [...]`
- 显式 compare 默认最多展示 10 个
- 派生 compare 默认展示 5 个
- 用户指定维度不改变 compare 列集合；额外维度进入后续大版本单独设计。

## 10. Period 规则

performance 周期：

| 用户表达 | period | 字段 |
| --- | --- | --- |
| 近1周 | 1w | `ths_yeild_1w_fund` + 排名字段 |
| 近1月 | 1m | `ths_yeild_1m_fund` + 排名字段 |
| 近3月 | 3m | `ths_yeild_3m_fund` + 排名字段 |
| 近6月 | 6m | `ths_yeild_6m_fund` + 排名字段 |
| 近1年 | 1y | `ths_yeild_1y_fund` + 排名字段 |
| 近2年 | 2y | `ths_yeild_2y_fund` + 排名字段 |
| 近3年 | 3y | `ths_yeild_3y_fund` + 排名字段 |
| 近5年 | 5y | `ths_yeild_5y_fund` + 排名字段 |
| 今年以来 | ytd | `ths_yeild_ytd_fund` + 排名字段 |
| 成立以来 | std | `ths_yeild_std_fund` + 排名字段 |
| 各周期 / 全部周期 | all | 展开所有收益率字段 |
| 未指定 | 1y | 保持 v1 默认 |

排名展示优先使用 `_fund_origin` 和 `_etf`。

排序或比较时使用数字排名 `_fund`。

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

无确定枚举映射时降级为 search，不允许模型猜数据库值。

### 指数名称匹配

当 filter 的筛选条件涉及跟踪指数时，不靠 LLM 猜数据库值，也不直接降级为 search。本地执行两步匹配：

1. 精确匹配 `ths_tracking_index_code_fund`（如 `000300`）
2. 对 `ths_name_of_tracking_index_fund` 做子串匹配（如用户说 `沪深300` 匹配 `沪深300指数`）

匹配成功 → 生成 filter AST，`where` 条件为 `{"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "<远端真实值>"}`。匹配失败 → 降级为 search。

指数名称匹配的候选值来源于远端 `tb_ths_etf_base` 中实际存在的 `ths_name_of_tracking_index_fund` 和 `ths_tracking_index_code_fund` 去重集合，不从 spec 硬编码。

以下分类词在前置识别中优先归入 filter，而不是普通 search：

```text
股票型、债券型、混合型、货币型、上交所、深交所、沪市、深市
```

### Period Normalization Fallback (v3.1+)

该能力属于 v3.1 Normalization Enhancement，不改变 v3.0 已锁定回归基线。

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
  -> 本地 PERIOD_FIELDS 映射字段
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
- 如果用户没有明确时间表达，`performance` 可使用默认 `period=1y`。
- 如果用户有明确时间表达但归一结果为 `unknown`，返回 `ClarificationRequired`，不静默默认成 `1y`。
- LLM 不允许输出字段名、集合名、Mongo 条件或答案。
- `period -> 字段` 只能由本地 `PERIOD_FIELDS` 完成。
- 该 fallback 只用于 `performance` intent，不用于 `report_period`。

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

## 12. 失败策略

- schema、安全、字段能力矩阵、Query Classification Matrix 冲突：直接失败，不执行 Mongo。
- 字段别名、排序方向、单位表达：允许本地归一，归一后必须重新完整校验。
- 枚举无法确定：降级为 search。
- 用户意图不明确：返回澄清，不生成 AST。
- LLM 输出无法归一到标准字段、标准 intent 或前置候选范围：直接失败，不进入 compiler。

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

- quarter latest 按 `year_num desc, type_num desc`
- quarter 是否排除 `type_num=4` 必须远端验证
- year latest 按 `year_num desc`
- year 的 `type_num` 是否固定或忽略必须远端验证
- 当 `expand` 指定的字段在报告文档中不存在或为 null 时，降级展示报告期基础信息，并说明该报告期暂无对应数据。

`expand` schema：

```json
{
  "field": "ths_top_held_stock_code_fund",
  "rank_limit": 10,
  "display_fields": [
    {"field": "ths_top_held_stock_code_fund", "label": "证券代码", "format": "plain"},
    {"field": "ths_top_stock_mv_to_fnv_fund", "label": "占基金净值比", "format": "percent"}
  ]
}
```

规则：

- `expand` 仅允许 `output_style=report_list`
- `expand.field` 必须是当前集合 `array_expandable`
- 按 `expand.field.rank_num asc` 排序
- 缺 `rank_num` 的项排后
- `display_fields` 按相同 `rank_num` 对齐
- 配对字段缺失时显示 `暂无数据`
- 季报只支持行业、重仓概念
- 年报重仓先展示代码+占比，不编造证券名称

## 14. 字段能力矩阵

本节是 Executable Capability Registry 的字段视图，仅用于展示、审计和测试，不得独立维护。

以下矩阵基于 `references/data-dictionary.md` 的全量字段，并已用 2026-05-07 的远端只读抽样核对过真实集合键。v2 没有给出完整能力矩阵，但它的字段清单与本次远端核对足以补全这里的定义。

```text
selectable
filterable_eq
filterable_compare
sortable
fuzzy_searchable
array_expandable
```

### 14.1 tb_ths_etf_base

#### 标识 / 分类 / 文本

- `fundcode`, `thscode`：`selectable`, `filterable_eq`; `fundcode` 可用于 compare 的 `in`；`sortable` 仅作为稳定 tie-breaker 使用
- `fundcode` / `thscode` 仅用于精确定位与 compare 的 `in` / `eq` 筛选，不作为比较维度。
- `ths_fund_extended_inner_short_name_fund`, `ths_fund_type_fund`, `ths_fund_invest_type_fund`, `ths_tracking_index_code_fund`, `ths_name_of_tracking_index_fund`, `ths_perf_comparative_benchmark_fund`, `ths_pur_and_redemp_status_fund`, `ths_etf_to_code_fund`, `ths_fund_listed_exchange_fund`：`selectable`, `filterable_eq`
- 其中 `ths_fund_extended_inner_short_name_fund`, `ths_name_of_tracking_index_fund`, `ths_tracking_index_code_fund` 额外 `fuzzy_searchable`
- `ths_fund_manager_current_fund`, `ths_fund_supervisor_fund`：`selectable`, `filterable_eq`; 名称反查可复用，但 v3 search 主链路不把它们当主要 fuzzy 字段
- `ths_invest_objective_fund`, `ths_invest_socpe_fund`, `ths_invest_philosophy_fund`, `ths_invest_strategy_fund`, `ths_risk_return_characteristics_fund`：`selectable`，仅做展示，不进入 v3.1 search/filter 主路径

#### 时间信息

- `ths_fund_establishment_date_fund`：`selectable`, `filterable_eq`, `sortable`

#### 规模 / 净值

- `ths_fund_scale_fund`, `ths_fund_shares_fund`, `ths_unit_nv_fund`, `ths_unit_nvg_rate_fund`, `ths_current_mv_fund`：`selectable`, `filterable_compare`, `sortable`
- 真实 DB 中 `ths_fund_scale_fund`, `ths_fund_shares_fund`, `ths_unit_nv_fund`, `ths_unit_nvg_rate_fund` 为 latest_ts 数组，使用最新 `btime` 的 `value`

#### 收益率

- `ths_yeild_1w_fund`, `ths_yeild_1m_fund`, `ths_yeild_3m_fund`, `ths_yeild_6m_fund`, `ths_yeild_1y_fund`, `ths_yeild_2y_fund`, `ths_yeild_3y_fund`, `ths_yeild_5y_fund`, `ths_yeild_ytd_fund`, `ths_yeild_std_fund`：`selectable`, `filterable_compare`, `sortable`
- 数字排名字段：
  `ths_yeild_rank_1w_fund`, `ths_yeild_rank_1m_fund`, `ths_yeild_rank_3m_fund`, `ths_yeild_rank_6m_fund`, `ths_yeild_rank_1y_fund`, `ths_yeild_rank_2y_fund`, `ths_yeild_rank_3y_fund`, `ths_yeild_rank_5y_fund`, `ths_yeild_rank_ytd_fund`, `ths_yeild_rank_std_fund`；
  `ths_yeild_rank_1w_etf`, `ths_yeild_rank_1m_etf`, `ths_yeild_rank_3m_etf`, `ths_yeild_rank_6m_etf`, `ths_yeild_rank_1y_etf`, `ths_yeild_rank_2y_etf`, `ths_yeild_rank_3y_etf`, `ths_yeild_rank_5y_etf`, `ths_yeild_rank_ytd_etf`, `ths_yeild_rank_std_etf`：
  `selectable`, `filterable_compare`, `sortable`
- 字符串排名字段：
  `ths_yeild_rank_1w_fund_origin`, `ths_yeild_rank_1m_fund_origin`, `ths_yeild_rank_3m_fund_origin`, `ths_yeild_rank_6m_fund_origin`, `ths_yeild_rank_1y_fund_origin`, `ths_yeild_rank_2y_fund_origin`, `ths_yeild_rank_3y_fund_origin`, `ths_yeild_rank_5y_fund_origin`, `ths_yeild_rank_ytd_fund_origin`, `ths_yeild_rank_std_fund_origin`：
  `selectable`，用于展示

#### 基金经理

- `ths_manager`：`selectable`, `array_expandable`
- `ths_service_sd_fund`, `ths_name_fund`, `ths_service_duration_annual_return_fund`, `ths_rzjjzgm_fund`, `ths_tenure_fund`：`selectable`
- 其中 `ths_service_sd_fund` 可做日期排序；`ths_service_duration_annual_return_fund`, `ths_rzjjzgm_fund`, `ths_tenure_fund` 可做数值排序/对比

#### 交易类指标 / 补充 / 费率 / 分红

- 交易指标字段保留在数据字典中，但不纳入 v3 capability matrix。
- `ths_amt_fund`, `ths_netcashflow_fund`, `ths_margin_trading_balance_fund`, `ths_short_selling_amtb_fund`：不允许 `selectable`、`filterable_eq`、`filterable_compare`、`sortable`、`fuzzy_searchable`、`array_expandable`
- `ths_similar_fund_std_avg_yield_fund` 暂不纳入 v3.0-v3.3 capability matrix，后续如需同类均值能力单独设计。
- `ths_manage_fee_rate_fund`, `ths_mandate_fee_rate_fund`：`selectable`, `filterable_compare`, `sortable`；answer_fields format 为 `percent`
- `ths_accum_dividend_total_amt_fund`：`selectable`, `filterable_compare`, `sortable`；answer_fields format 为 `amount`，除以 1e8 加"亿元"
- `ths_accum_dividend_times_fund`：`selectable`, `filterable_compare`, `sortable`；answer_fields format 为 `plain`

### 14.2 tb_ths_etf_report_quarter

- `fundcode`, `thscode`, `year_num`, `type_num`：`selectable`, `filterable_eq`, `sortable`
- `ths_top_n_top_industry_name_fund`, `ths_zcgnmc_fund`：`selectable`, `array_expandable`
- 两个数组都按 `rank_num` 展开；`type_num` 的允许值和 latest 语义仍以远端验证结果为准

### 14.3 tb_ths_etf_report_year

- `fundcode`, `thscode`, `year_num`, `type_num`：`selectable`, `filterable_eq`, `sortable`
- `ths_org_investor_total_held_ratio_fund`, `ths_org_investor_total_held_shares_fund`, `ths_invest_style_fund`, `ths_fanv_chg_fund`, `ths_fanv_chg_rate_fund`：`selectable`
- 其中数值字段 `filterable_compare`, `sortable`；`ths_invest_style_fund` 仅 `filterable_eq`
- `ths_top_n_top_industry_name_fund`, `ths_top_n_top_industry_mv_to_equity_fund`, `ths_top_sec_code_fund`, `ths_top_n_top_stock_mv_to_equity_fund`, `ths_top_held_stock_code_fund`, `ths_top_stock_mv_to_fnv_fund`：`selectable`, `array_expandable`
- 行业/重仓数组按 `rank_num` 展开，缺少配对字段时显示 `暂无数据`

## 15. Orchestrator

`composite` 属于 orchestrator 外层，不进入单个 AST。

规则：

- v3 不做通用同集合多意图 merge。
- `fee_and_manager` 是独立 intent，不通过通用 merge 推导。
- 若命中多个优先级类别，设置 `composite_hint=true`，保留各子意图候选，不只取最高优先级。
- base + report 拆成两个 AST
- search/filter 后 detail/compare/report 拆成两个 AST
- 最多 2 步
- composite Step 2 为 single detail 时，允许在主 intent 的 `answer_fields` 中附带同集合 `selectable` 的辅助展示字段。辅助字段不改变 AST intent，不触发额外 AST，不计入多意图 merge。例如 intent=performance 的 answer_fields 可包含 fundcode、简称、跟踪指数、基金规模等 basic_info 字段。
- composite 场景下，Step 1 的 limit 由 orchestrator 统一接管，默认 `limit=10`，覆盖各 stage 的默认 limit
- 仅 Step 2 继续服从对应 query_mode / intent 的默认 formatter 规则
- Step 1 空结果：停止，返回未找到候选
- Step 1 多于 N：截断并说明，N 固定为 10
- 若 Step 1 显式要求 top-k，则实际取 `min(k, 10)`
- 超过 N 时，保留前 N 个候选，并返回“已截断”提示
- Step 2 部分 fundcode 无数据：保留有数据项，列出缺失代码
- 名称反查多候选：不进入 AST，返回候选澄清列表
- base + report：先展示 base 摘要，再展示 report_list
- composite 最终输出顺序：
  - Step 2 结果已包含 Step 1 关键信息时（如 compare 表已列出所有基金代码和名称），只展示 Step 2 结果
  - Step 2 为 detail（single 子 AST）且无法从 Step 2 结果推断 Step 1 候选时，先展示 Step 1 简略列表（代码 + 名称），再展示 Step 2 详情
  - Step 1 结果被截断时，需提示"已截断，仅展示前 N 个"
- 9.3 在 v3.1 只覆盖”搜索中证红利”前半段；持仓部分到 v3.3 验收

**search/filter → single detail 的候选选择规则：**

- Step 1 返回 0 条：停止，返回未找到候选
- Step 1 返回 1 条：自动进入 Step 2
- Step 1 返回 2 条及以上：默认选择规模（`ths_fund_scale_fund`）最大的 1 条进入 Step 2，并在答案中标注”自动选择规模最大的基金：{名称}({fundcode})”
- 用户显式要求”都查 / 全部 / 对比 / 每个”时，多条进入 Step 2（subject to Step 2 limit caps）
- 以上规则适用于 search→detail 和 filter→detail 的 composite 场景；compare 和 report 子步骤不受此规则影响

## 16. Deny Intent

命中 deny 后不生成 AST。

分类：

| 类别 | 示例 |
| --- | --- |
| 实时行情类 | 今日涨跌、今日收益、今天收益、价格、当前净值、实时净值、估值、盘中、盘口、最新价格、涨跌幅、K 线 |
| 交易指标类 | 成交额、成交量、换手率、资金流、融资余额、融券、溢价率、折价率、委比、量比 |
| 技术分析类 | MACD、均线、RSI |
| 投资建议类 | 能买吗、值得买吗、该不该买、推荐哪只、帮我选、买哪个、哪个好、收益更好的是哪个 |
| 个股分析类 | 贵州茅台怎么样、某股票分析 |

输出使用固定拒绝模板，说明能力边界。

compare 与 deny 边界：

- “哪个好 / 哪个更值得买 / 推荐哪个”优先归入 deny，不进入 compare。
- “哪个费率更低 / 哪个收益更高 / 哪个规模更大”未显式多 fundcode 时归入 filter；显式多 fundcode 时归入 compare。

## 17. Formatter [Strategy]

| output_style | 输出 |
| --- | --- |
| summary | 标题行 + 关键字段列表 |
| list | 代码 \| 名称 \| 规模 \| 费率 \| 相关排序字段 |
| compare | 横向表格，行为指标，列为基金 |
| report_list | 排名 \| 行业/概念/证券代码 \| 占比 |
| unsupported | 固定拒绝文本 |

performance 在 v3.1+ 输出：

```text
周期 | 收益率 | 同类排名 | ETF排名
```

格式化规则：

- 金额类除以 1e8，保留 2 位，加“亿”
- 收益率、费率、占比保留 2 位，加 `%`
- 排名优先展示 `_fund_origin`
- null 或缺失字段显示 `暂无数据`
- 长文本最多 200 字，末尾加省略提示
- 年报重仓无名称字段时只展示代码+占比
- 不做 LLM 摘要、不编造、不做投资判断

### V1 Baseline Answer Fields (v3.0 回归基线)

v3.0 要求保持 v1 回答 shape。以下模板为 v3.0 validator 强制补齐的默认 answer_fields，LLM 可在此基础上追加同集合 `selectable` 字段，但不得删减基线字段。

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

v3.1+ 新增 intent（search、filter、compare、report_*、manager_detail 等）不受此基线表约束，使用各自的 formatter 模板。

## 18. Manager Detail 规则

`manager_detail` v3.2 字段：

- `ths_fund_manager_current_fund`
- `ths_fund_supervisor_fund`
- `ths_service_sd_fund`
- `ths_service_duration_annual_return_fund`
- `ths_tenure_fund`
- `ths_rzjjzgm_fund`

阻塞规则：

- 未验证 `ths_manager.rank_num` 是否代表现任前，不允许从 `rank_num` 推断现任经理。
- 若顶层 manager_detail 字段无值，只回答现任经理和基金管理人，并说明任期/历史业绩暂无可用结构化数据。

## 19. 远端验证阻塞项

未验证前能力不开启：

- v3.2：成立日期字段是否稳定为 `YYYY-MM-DD`
- v3.2：`ths_manager` 子字段是顶层字段还是仅在数组内
- v3.2：`ths_manager.rank_num` 是否能代表现任顺序
- v3.3：quarter 集合 `type_num=4` 是否应纳入 latest
- v3.3：year 集合 `type_num` 是否固定或可忽略
- v3.3：年报重仓是否存在证券名称字段；未验证前只展示代码+占比

未开放阶段内，report intents 不进入 `intent_candidates`，也不进入 AST。

未验证通过时，report_* 不进入 AST；系统固定返回 `UnsupportedQuery`（reason=`blocked_by_verification`），不得返回 `ClarificationRequired`（澄清意味着"补信息后可能可执行"，与"能力未开放"语义不同）。

在 `composite` 场景中，若 base 子步骤独立存在且不依赖 report 验证项，base 子步骤正常执行并展示；report 子步骤固定返回 `UnsupportedQuery`。不得把 blocked report 静默降级为 base 查询，也不得伪装成已完成的 report 结果。

## 20. Evaluation [Test]

coverage matrix 只用于验收与回归，不代表生产问法全集。

测试通过只表示当前 Registry 覆盖范围内的 AST 生成、校验、编译、执行和格式化链路符合预期，不表示覆盖所有 ETF 自然语言问法。

38 条原始测试问题的逐条阶段映射见 `docs/v3-coverage-matrix.md`。

测试分七类：

- intent recognition tests
- deterministic parser tests
- LLM AST generation tests
- AST validator/compiler tests
- remote execution smoke
- formatter tests
- end-to-end tests

v3.1+ 增加 paraphrase set 和 template fuzz set，覆盖同类改写。

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
- AST 中不能出现 LLM 生成的字段名，只能出现本地 `PERIOD_FIELDS` 映射字段。

阶段黄金集：

| 阶段 | 黄金集 |
| --- | --- |
| v3.0 | 13 条回归 + 5 条拒绝/边界 |
| v3.1 | 至少 20 条 search/filter/sort/compare |
| v3.2 | 至少 15 条 base 扩展 |
| v3.3 | 至少 20 条 report |
| cross-stage composite | 至少 10 条，v3.3 后统一验收 |

v3.3 report 黄金集至少包含：

- `report_industry` 至少 4 条
- `report_concept` 至少 4 条
- `report_holding` 至少 4 条
- `institution_holding` 至少 4 条
- report latest / specified / empty / missing paired field 至少 4 条

阶段门禁：

| 阶段 | 门禁 |
| --- | --- |
| v3.0 | 13/13 v1 回归，AST/Mongo/shape 全 100% |
| v3.1 | smoke 全 100%，该层黄金集 85%+ |
| v3.2 | smoke 全 100%，该层黄金集 90%+ |
| v3.3 | smoke 全 100%，该层黄金集 80%+，并跑 composite |

v1 13 条回归的 expected answer shape 在 v3.0 锁定；若 formatter 升级导致 shape 变化，必须同步更新回归基线。

每条黄金集记录：

```text
question
expected intent recognition result
expected selection_context
expected AST
expected Mongo params
expected output_style
expected answer_fields
expected answer shape
answer value policy
是否依赖真实远端数据
```

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

report latest 必须记录编译后的 `sort` 与 `limit=1` 选择逻辑。

answer value policy：

- 稳定字段精确匹配
- 波动字段校验格式、字段存在、日期/报告期合理
- 需要精确值时使用固定快照或当天基准结果

## 21. Canonical Seed List

以下 seed 是 v3 核心路由种子，配置文件只能追加同义词，不得删除、覆盖或改变其目标 intent。外部配置只允许追加 `extra_seeds`，不得覆盖 `canonical_seeds`。测试和 review 以 spec 中的 canonical seed list 为基线。PM 业务桶不直接参与这张表的定义。

| intent / route | canonical seeds |
| --- | --- |
| `basic_info` | 是什么、介绍、基本信息、概况、单独基金代码 |
| `fund_scale` | 规模、盘子、多大、资产规模、总市值 |
| `tracking_index` | 跟踪、跟的、标的指数、指数名称、指数代码 |
| `performance` | 收益、收益率、表现、回报、涨、跌、涨跌、排第几、排多少、排名第几、今年、近1周、近1月、近1年、成立以来、各周期 |
| `fee` | 管理费、托管费、费率、费率最低 |
| `manager` | 基金经理、谁在管、管理人 |
| `manager_detail` | 管理了多久、任职、任职天数、任职起始日、任职年化回报、管理规模、历史业绩 |
| `fee_and_manager` | 费率和基金经理、费率以及谁在管 |
| `dividend` | 分红、分红记录、累计分红、分红次数、分过红、分过几次、分了几次、分了多少钱 |
| `search` | 搜索、帮我找、找一下、有没有名字叫、名字里带、相关 ETF |
| `filter` | 筛选、前 N、最高、最低、大于、小于、股票型、债券型、上交所、深交所、哪个费率更低、哪个收益更高、哪个规模更大 |
| `compare` | 对比、比较、vs、和...比、显式多个 fundcode 并列 |
| `investment_profile` | 投资目标、投资范围、投资理念、投资策略、风险收益特征 |
| `subscription_redemption` | 申购、赎回、申赎状态 |
| `linked_fund` | 联接基金、ETF 联接 |
| `report_industry` | 持仓行业、行业配置、前 N 大行业、季报持仓 |
| `report_concept` | 重仓概念、概念持仓、题材 |
| `report_holding` | 前十大、重仓股、重仓证券、年报持仓 |
| `institution_holding` | 机构持有、机构持仓、机构投资者比例、机构持有份额 |
| `unsupported/deny` | 今日涨跌、实时净值、成交额、融资余额、推荐哪只、推荐、给我推荐、能买吗、个股分析、大盘、A股、上证、深证 |

## 22. Generated Views [Read Only]

以下内容均由 Executable Capability Registry 生成，仅用于展示、测试和审计，不作为独立维护源：

1. `recognized_query_mode / intent / output_style / from` Query Classification Matrix
2. 字段能力矩阵，包含 `selectable`、`filterable_eq`、`filterable_compare`、`sortable`、`fuzzy_searchable`、`array_expandable`
3. 单位、日期、枚举、排序方向、period 归一表
4. `report_period` 与 `expand` JSON schema
5. deny intent 关键词/模式表
6. 分阶段 smoke/golden 验收表
7. 分阶段 smoke 明细表：question、阶段、预期 recognized_query_mode、预期行为、是否允许远端查询、失败即阻塞
8. intent recognition 触发词和优先级表
9. v3.1 period paraphrase set 与受限 period fallback 校验表
10. PM coverage bucket -> runtime profile 映射表（reference only）
11. selection_context JSON schema
12. field_profile -> selectable_fields / baseline_answer_fields 映射表

规则：

- 以上各表均由 Registry 派生，不得作为独立维护源。
- 任何变更先改 Registry，再由 Registry 重新生成这些视图。
- 若视图与 Registry 冲突，以 Registry 为准。
