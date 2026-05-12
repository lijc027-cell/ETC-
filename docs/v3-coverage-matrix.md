# ETF Text2SQL v3 Coverage Matrix

本矩阵覆盖 `etf-query-test-questions.md` 当前版本中的每一条 PM 测试问题。它是 v3 运行时验收权威；PM bucket 只用于覆盖分组，不参与运行时函数分发。`release_scope` 是 release 分母字段，替代 `expected_phase` 作为验收口径。

Coverage Matrix 的 `question` 必须逐字来自 `etf-query-test-questions.md`。如需 paraphrase/fuzz 测试，应新增单独 paraphrase set，不得替换 PM 原句。

## 硬规则

- 每一条 PM 测试问题必须有且只有一行。
- `release_scope` allowed values 固定为 `v3_2_required | v3_3_required | later | boundary`。
- `release_scope` 是唯一 release 分母字段：`v3_2_required` 计入 v3.2 release gate 分母，`v3_3_required` 计入 v3.3 release gate 分母，`later` 和 `boundary` 不进入当前 release strict pass 分母。audit 只能按该字段机械过滤。
- DeniedQuery / UnsupportedQuery / ClarificationRequired 必须 `ast_required=false`、`remote_query_allowed=false`。
- 当前 PM coverage matrix 中，`DeniedQuery` 只允许出现在十二章边界/异常场景；非十二章模糊比较问法必须转为 executable compare/list，或在实体不足时 ClarificationRequired。
- v3.0/v3.1 covered executable questions 必须：
  - `ast_required=true`
  - `llm_ast_draft_required=true`
  - `must_migrate_in_v3_2=true`
  - `deterministic_legacy_allowed=false`
  - `ast_generation_mode=llm_ast_draft`
- v3.2 新增 executable questions 必须 `llm_ast_draft_required=true`。
- report / manager_detail / trading_metric 属于 v3.3 或更后续 gate，不进入 v3.2 strict executable 验收。
- `暂无数据` 只允许用于 remote query 已执行且结果为空或字段为空。

| question_id | question | PM bucket | release_scope | routing_result.type | recognized_query_mode | expected_intent_or_profile | ast_generation_mode | ast_required | llm_ast_draft_required | covered_by_v3_0_or_v3_1 | must_migrate_in_v3_2 | deterministic_legacy_allowed | executable_in_current_phase | expected_fallback_or_blocked_reason | remote_query_allowed | included_in_v3_2_0_smoke | included_in_v3_3_report_gate | expected_outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 一.1 | 510300是什么 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_basic_info |
| 一.2 | 帮我查一下510500的基本信息 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_basic_info |
| 一.3 | 159919这只基金跟踪什么指数 | 基本信息 | v3_2_required | ExecutableQuery | single | tracking_index | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_tracking_index |
| 一.4 | 工银沪深300ETF的费率和基金经理是什么 | 基本信息 | v3_2_required | ExecutableQuery | single | fee_and_manager | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_fee_and_manager |
| 一.5 | 510300的成立日期是什么时候 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info_extended | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_basic_info_extended |
| 一.6 | 510300在哪上市的 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info_extended | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_basic_info_extended |
| 一.7 | 510300现在能申购吗 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info_extended | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_basic_info_extended |
| 一.8 | 510300的联接基金代码是多少 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info_extended | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_basic_info_extended |
| 一.9 | 510300的投资目标和策略是什么 | 基本信息 | v3_2_required | ExecutableQuery | single | investment_profile | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_investment_profile |
| 一.10 | 510300的业绩比较基准是什么 | 基本信息 | v3_2_required | ExecutableQuery | single | basic_info_extended | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_basic_info_extended |
| 一.11 | 510300的风险收益特征是什么 | 基本信息 | v3_2_required | ExecutableQuery | single | investment_profile | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_investment_profile |
| 一.12 | 510300的管理人是谁 | 基本信息 | v3_2_required | ExecutableQuery | single | manager | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_manager |
| 二.1 | 510300今年的收益率是多少 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.2 | 159919近1年收益，同类排名第几 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.3 | 510500成立以来收益怎么样 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.4 | 510300近3个月涨了多少 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.5 | 510300各周期的收益率给我看看 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.6 | 510300近2年ETF排第几 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.7 | 510300今年在同类基金里排多少 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.8 | 510300近半年收益率和同类平均比怎么样 | 收益率与排名 | v3_3_required | UnsupportedQuery | null | unsupported_peer_average | null | false | false | false | false | false | false | peer_average_period_semantics_unverified | false | false | false | UnsupportedQuery(blocked_by_verification) |
| 二.9 | 510300近5年收益率是多少，排名如何 | 收益率与排名 | v3_2_required | ExecutableQuery | single | performance | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_performance |
| 二.10 | 成立以来收益最好的沪深300ETF是哪只 | 收益率与排名 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter_sort |
| 三.1 | 510300的基金规模多大 | 规模、净值、份额 | v3_2_required | ExecutableQuery | single | fund_scale | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_fund_scale |
| 三.2 | 510300总市值多少 | 规模、净值、份额 | v3_2_required | ExecutableQuery | single | fund_scale | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_fund_scale |
| 三.3 | 510300最新净值是多少 | 规模、净值、份额 | v3_2_required | ExecutableQuery | single | fund_scale | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_fund_scale |
| 三.4 | 510300的份额有多少 | 规模、净值、份额 | v3_2_required | ExecutableQuery | single | fund_scale | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_fund_scale |
| 三.5 | 510300的净值增长率是多少 | 规模、净值、份额 | v3_2_required | ExecutableQuery | single | fund_scale | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_fund_scale |
| 三.6 | 510300的基金份额最近有变化吗 | 规模、净值、份额 | v3_3_required | ExecutableQuery | single | fund_scale | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_timeseries_latest_two |
| 四.1 | 510300前十大重仓股是什么 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_holding | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_expand_holding |
| 四.2 | 159919的持仓行业有哪些 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_industry | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_expand_industry |
| 四.3 | 510500最新季报的持仓 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_industry | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_expand_quarter_industry |
| 四.4 | 510300的机构持有比例是多少 | 持仓信息 | v3_3_required | ExecutableQuery | report | institution_holding | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_scalar_institution_holding |
| 四.5 | 510300的投资风格是什么 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_style | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_scalar_style |
| 四.6 | 510300的净资产变动情况 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_nav_change | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_scalar_nav_change |
| 四.7 | 159919重仓了哪些概念 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_concept | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_expand_concept |
| 四.8 | 510300年报里行业配置占比最高的前五个 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_industry | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_expand_industry |
| 四.9 | 510300前十大重仓股占净值比多少 | 持仓信息 | v3_3_required | ExecutableQuery | report | report_holding | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_report_expand_holding |
| 五.1 | 510300的基金经理是谁 | 基金经理 | v3_2_required | ExecutableQuery | single | manager | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_manager |
| 五.2 | 510300现任基金经理管理了多久 | 基金经理 | v3_3_required | ExecutableQuery | single | manager_detail | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_manager_detail |
| 五.3 | 510300基金经理的历史业绩怎么样 | 基金经理 | v3_3_required | ExecutableQuery | single | manager_detail | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_manager_detail |
| 五.4 | 510300基金经理管了多少规模的基金 | 基金经理 | v3_3_required | ExecutableQuery | single | manager_detail | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_manager_detail |
| 五.5 | 510300什么时候换的基金经理 | 基金经理 | v3_3_required | ExecutableQuery | single | manager_detail | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_manager_detail_timeline |
| 六.1 | 510300有没有分红记录 | 分红 | v3_2_required | ExecutableQuery | single | dividend | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_dividend |
| 六.2 | 159919累计分红多少 | 分红 | v3_2_required | ExecutableQuery | single | dividend | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_dividend |
| 六.3 | 510300分过几次红 | 分红 | v3_2_required | ExecutableQuery | single | dividend | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_single_dividend |
| 七.1 | 帮我找沪深300相关的ETF | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 七.2 | 搜索中证500 | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 七.3 | 找一下创业板ETF | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 七.4 | 搜索MSCI中国A股 | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 七.5 | 有没有名字里带医药的ETF | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 七.6 | 有没有ETF名字里带"红利"的 | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 七.7 | 我想找跟踪科创50的ETF | 搜索ETF | v3_2_required | ExecutableQuery | search | search | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_search |
| 八.1 | 帮我筛选所有股票型ETF | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.2 | 找上交所规模前10的ETF | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.3 | 哪些ETF管理费率最低 | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.4 | 筛选跟踪沪深300指数的ETF，按收益率排序 | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.5 | 找规模大于10亿的ETF | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.6 | 筛选深交所的债券型ETF | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.7 | 今年以来收益排名前10的ETF | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.8 | 管理费率低于0.2%的ETF有哪些 | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 八.9 | 2024年成立的ETF有哪些 | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | v3_2_filter_date_between |
| 八.10 | 近1年收益率超过20%的ETF | 条件筛选 | v3_2_required | ExecutableQuery | filter | filter | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_filter |
| 九.1 | 对比510300、510500和159919 | 多只对比 | v3_2_required | ExecutableQuery | compare | compare | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_compare |
| 九.2 | 512880和510300哪个更好 | 多只对比 | v3_2_required | DeniedQuery | deny | investment_advice | null | false | false | false | false | false | false | investment_advice | false | true | false | DeniedQuery(investment_advice) |
| 九.3 | 对比所有跟踪沪深300的前5只ETF，看收益和费率 | 多只对比 | v3_2_required | ExecutableQuery | compare | two_step_composite | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | two_step_composite_filter_compare |
| 九.4 | 510300和510500比一下规模和费率 | 多只对比 | v3_2_required | ExecutableQuery | compare | compare | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_compare |
| 九.5 | 对比一下510300和159919的收益率 | 多只对比 | v3_2_required | ExecutableQuery | compare | compare | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | covered_compare |
| 十.1 | 帮我找跟踪沪深300指数、费率最低的ETF，然后看它的基本信息和收益 | 复合意图 | v3_3_required | ExecutableQuery | composite | two_step_composite | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_two_step_filter_composite_single |
| 十.2 | 股票型ETF里今年收益最高的5只是哪些？对比一下 | 复合意图 | v3_2_required | ExecutableQuery | compare | two_step_composite | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | two_step_composite_filter_compare |
| 十.3 | 搜索中证红利，查一下它的基本信息和持仓 | 复合意图 | v3_3_required | ExecutableQuery | composite | two_step_composite | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_two_step_search_composite_single_report |
| 十.4 | 510300今年收益多少，持仓了哪些行业，基金经理是谁 | 复合意图 | v3_3_required | ExecutableQuery | composite | composite_single | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_composite_cross_collection |
| 十.5 | 帮我看看510500的规模大不大，费率贵不贵，收益好不好 | 复合意图 | v3_3_required | ExecutableQuery | single | composite_single | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_composite_single_scale_fee_performance |
| 十.6 | 上交所的ETF里，找管理费最低的3只，对比它们的今年收益 | 复合意图 | v3_2_required | ExecutableQuery | compare | two_step_composite | llm_ast_draft | true | true | true | true | false | true | - | true | true | false | two_step_composite_filter_compare |
| 十.7 | 510300成立以来收益怎么样，分过红吗 | 复合意图 | v3_2_required | ExecutableQuery | single | composite_single | llm_ast_draft | true | true | false | false | false | true | - | true | true | false | composite_single_performance_dividend |
| 十.8 | 对比510300和510500的费率、规模和重仓股 | 复合意图 | v3_3_required | ExecutableQuery | composite | composite_single | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_composite_compare_plus_report |
| 十一.1 | 510300最近成交额多少 | 交易类指标（新增字段） | v3_3_required | ExecutableQuery | single | trading_metric | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_trading_metric_snapshot |
| 十一.2 | 510300的净现金流是正还是负 | 交易类指标（新增字段） | v3_3_required | ExecutableQuery | single | trading_metric | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_trading_metric_snapshot |
| 十一.3 | 510300的融资余额是多少 | 交易类指标（新增字段） | v3_3_required | ExecutableQuery | single | trading_metric | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_trading_metric_snapshot |
| 十一.4 | 510300的融券卖出量多少 | 交易类指标（新增字段） | v3_3_required | ExecutableQuery | single | trading_metric | llm_ast_draft | true | true | false | false | false | true | - | true | false | true | v3_3_trading_metric_snapshot |
| 十二.1 | 000001有这只ETF吗 | 边界/异常场景 | v3_2_required | ExecutableQuery | single | basic_info | llm_ast_draft | true | true | true | true | false | true | not_found | true | true | false | executable_empty_result_not_found |
| 十二.2 | 帮我查510300的实时行情 | 边界/异常场景 | boundary | DeniedQuery | deny | realtime_market | null | false | false | false | false | false | false | realtime_not_supported | false | true | false | DeniedQuery(realtime_not_supported) |
| 十二.3 | abcdef是什么基金 | 边界/异常场景 | boundary | ClarificationRequired | null | invalid_fundcode | null | false | false | false | false | false | false | invalid_fundcode | false | true | false | ClarificationRequired(invalid_fundcode) |
| 十二.4 | 510300的持仓行业是什么（季报年报都没有） | 边界/异常场景 | v3_3_required | UnsupportedQuery | null | report_industry | null | false | false | false | false | false | false | data_not_available | false | true | true | UnsupportedQuery(data_not_available) |
| 十二.5 | 对比510300和000000 | 边界/异常场景 | v3_2_required | ExecutableQuery | compare | compare | llm_ast_draft | true | true | true | true | false | true | partial_entity_found | true | true | false | compare_partial_found |
| 十二.6 | 给我推荐一只ETF | 边界/异常场景 | boundary | DeniedQuery | deny | investment_advice | null | false | false | false | false | false | false | investment_advice | false | true | false | DeniedQuery(investment_advice) |
| 十二.7 | 今天A股大盘怎么样 | 边界/异常场景 | later | DeniedQuery | deny | unsupported_domain | null | false | false | false | false | false | false | unsupported_domain | false | true | false | DeniedQuery(unsupported_domain) |
| 十二.8 | 510300能买吗 | 边界/异常场景 | boundary | DeniedQuery | deny | investment_advice | null | false | false | false | false | false | false | investment_advice | false | true | false | DeniedQuery(investment_advice) |
