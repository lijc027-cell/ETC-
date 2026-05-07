# ETF Text2SQL v3 测试覆盖矩阵

本文把 `test-questions.md` 的 38 条问题逐条映射到 v3 阶段、前置识别结果和预期行为。它是 `docs/etf-semantic-query-spec-v3.md` 的 Evaluation 配套文件。

| # | question | phase | recognized_query_mode | intent | expected outcome |
| --- | --- | --- | --- | --- | --- |
| 1.1 | 510300是什么 | v3.0 | single | basic_info | 查询 `tb_ths_etf_base`，按 v1 legacy_summary 返回基本信息。 |
| 1.2 | 帮我查一下510500的基本信息 | v3.0 | single | basic_info | 查询 `tb_ths_etf_base`，按 v1 legacy_summary 返回基本信息。 |
| 1.3 | 159919这只基金跟踪什么指数 | v3.0 | single | tracking_index | 查询跟踪指数代码和名称。 |
| 1.4 | 工银沪深300ETF的费率和基金经理是什么 | v3.0 | single | fee_and_manager | 先名称反查到 fundcode，再查询费率和基金经理；保持 v1 回归。 |
| 2.1 | 510300今年的收益率是多少 | v3.0 | single | performance | period=`ytd`，查询今年以来收益和排名。 |
| 2.2 | 159919近1年收益，同类排名第几 | v3.0 | single | performance | period=`1y`，查询近1年收益、同类排名、ETF 排名。 |
| 2.3 | 510500成立以来收益怎么样 | v3.0 | single | performance | period=`std`，查询成立以来收益和排名。 |
| 2.4 | 帮我查510300各周期的收益率 | v3.0 | single | performance | period=`all`，展开全周期收益字段；输出仍按 v1 回归 shape 验收。 |
| 3.1 | 510300前十大重仓股是什么 | v3.3 | report | report_holding | 前提：report verification passed。查询年报最新期，展开前十大重仓证券代码+占比；未验证名称字段前不编造名称。 |
| 3.2 | 159919的持仓行业有哪些 | v3.3 | report | report_industry | 前提：report verification passed。查询季报最新期，展开前 N 大行业。 |
| 3.3 | 510500最新季报的持仓 | v3.3 | report | report_industry | 前提：report verification passed。查询季报 latest，返回行业/概念；不返回股票重仓。 |
| 3.4 | 帮我看看510300的机构持有情况 | v3.3 | report | institution_holding | 前提：report verification passed。查询年报机构持仓比例和份额。 |
| 4.1 | 帮我找沪深300相关的ETF | v3.1 | search | search | `__search_text__ contains 沪深300`，返回候选列表，默认按规模 desc。 |
| 4.2 | 搜索中证500 | v3.1 | search | search | 搜索简称/指数名/指数代码，返回候选列表。 |
| 4.3 | 找一下创业板ETF | v3.1 | search | search | 搜索创业板相关 ETF，返回候选列表。 |
| 4.4 | 搜索MSCI中国A股 | v3.1 | search | search | 搜索 MSCI 中国 A 股相关 ETF，返回候选列表。 |
| 4.5 | 有没有ETF名字里带医药的 | v3.1 | search | search | 在 fuzzy searchable 字段内 contains 医药，返回候选列表。 |
| 5.1 | 帮我筛选所有股票型ETF | v3.1 | filter | filter | `ths_fund_invest_type_fund eq 股票型`，limit=50，并说明最多展示前 50 条。 |
| 5.2 | 找上交所规模前10的ETF | v3.1 | filter | filter | `ths_fund_listed_exchange_fund eq 上交所`，按规模 desc，limit=10。 |
| 5.3 | 哪些ETF管理费率最低 | v3.1 | filter | filter | 按管理费率 asc 排序，返回列表。 |
| 5.4 | 筛选跟踪沪深300指数的ETF，按收益率排序 | v3.1 | filter | filter | 跟踪指数筛选，按默认收益周期排序；收益周期不明确时按归一规则处理。 |
| 5.5 | 找规模大于10亿的ETF | v3.1 | filter | filter | 单位归一为 `1000000000`，规模 `gt`，返回列表。 |
| 5.6 | 筛选深交所的债券型ETF | v3.1 | filter | filter | 上市地点和投资类型 AND 筛选，返回列表。 |
| 6.1 | 对比510300、510500和159919 | v3.1 | compare | compare | 显式多 fundcode，`fundcode in [...]`，固定 8 列对比。 |
| 6.2 | 帮我对比一下512880和510300 | v3.1 | compare | compare | 显式多 fundcode，固定 8 列对比。 |
| 6.3 | 对比所有跟踪沪深300的前5只ETF，看收益和费率 | v3.1 | composite | compare | 两步：filter 收集前 5 个 fundcode，再固定 8 列 compare。 |
| 7.1 | 510300的基金经理是谁 | v3.0 | single | manager | 查询现任基金经理和基金管理人；保持 v1 回归。 |
| 7.2 | 510300现任基金经理管理了多久 | v3.2 | single | manager_detail | 远端验证后查询任职起始日/任职天数；无法验证时返回结构化数据暂无。 |
| 7.3 | 查一下510300基金经理的历史业绩 | v3.2 | single | manager_detail | 部分覆盖：仅返回任职年化回报，不声称完整历史业绩。 |
| 8.1 | 510300有没有分红记录 | v3.0 | single | dividend | 查询累计分红总额和次数；保持 v1 回归。 |
| 8.2 | 159919的分红情况 | v3.0 | single | dividend | 查询累计分红总额和次数；保持 v1 回归。 |
| 9.1 | 帮我找跟踪沪深300指数、费率最低的ETF，然后看它的基本信息和收益 | v3.1 | composite | filter + basic_info + performance | 两步：筛选费率最低候选，再查 base 摘要和收益。 |
| 9.2 | 股票型ETF里今年收益最高的5只是哪些？对比一下 | v3.1 | composite | filter + compare | 两步：股票型 + 年初至今收益 desc + limit 5，再固定 8 列 compare。 |
| 9.3 | 搜索中证红利，查一下它的基本信息和持仓 | v3.3 | composite | search + basic_info + report_holding | 前提：report verification passed。v3.1 只验收搜索前半段；v3.3 后统一验收基本信息 + 持仓。 |
| 10.1 | 000001有这只ETF吗 | v3.0 | single | basic_info | fundcode 精确查询空结果，返回未找到 ETF。 |
| 10.2 | 帮我查510300的实时行情 | v3.0 | deny | unsupported | `DeniedQuery`，不调用 LLM，不生成 AST。 |
| 10.3 | 510300近一周收益 | v3.0 | single | performance | period=`1w`，查询近1周收益和排名。 |
| 10.4 | 有没有名字叫"人工智能"的ETF | v3.1 | search | search | 搜索人工智能相关 ETF，返回候选列表或空列表提示。 |
