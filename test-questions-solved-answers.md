# ETF Query 已解决测试问句与回答

生成日期：2026-05-07

来源文件：`test-questions.md`

生成方式：基于当前 v1 代码执行 `semantic_query(..., dry_run=True)` 后整理。注意：本文件中的数值来自 dry-run 示例结果，不代表远端 Mongo 的真实数据；用于核对问题覆盖、字段选择和回答格式是否符合预期。

## 覆盖摘要

- 已纳入：13 个问题
- 覆盖范围：单只 ETF 基本信息、跟踪指数、费率与基金经理、收益率、基金经理、分红、代码不存在、近一周收益
- 未纳入：持仓、搜索、筛选、对比、实时行情，以及“基金经理管理多久/历史业绩”等 v1 未真正覆盖的问题

## 1. 单只基金基本信息

### 1.1 510300是什么

- 覆盖状态：已解决
- intent：`basic_info`
- fundcode：`510300`
- projection：`fundcode`, `ths_fund_extended_inner_short_name_fund`, `ths_name_of_tracking_index_fund`, `ths_fund_scale_fund`
- 回答：

> 510300 的基金简称为 沪深300ETF，跟踪指数名称为 沪深300指数，基金规模为 123.46 亿元。

### 1.2 帮我查一下510500的基本信息

- 覆盖状态：已解决
- intent：`basic_info`
- fundcode：`510500`
- projection：`fundcode`, `ths_fund_extended_inner_short_name_fund`, `ths_name_of_tracking_index_fund`, `ths_fund_scale_fund`
- 回答：

> 510500 的基金简称为 沪深300ETF，跟踪指数名称为 沪深300指数，基金规模为 123.46 亿元。

### 1.3 159919这只基金跟踪什么指数

- 覆盖状态：已解决
- intent：`tracking_index`
- fundcode：`159919`
- projection：`fundcode`, `ths_tracking_index_code_fund`, `ths_name_of_tracking_index_fund`
- 回答：

> 159919 的跟踪指数代码为 000300，跟踪指数名称为 沪深300指数。

### 1.4 工银沪深300ETF的费率和基金经理是什么

- 覆盖状态：已解决
- intent：`fee_and_manager`
- fundcode：`510350`
- projection：`fundcode`, `ths_manage_fee_rate_fund`, `ths_mandate_fee_rate_fund`, `ths_fund_manager_current_fund`, `ths_fund_supervisor_fund`
- 回答：

> 510350 的管理费率为 0.50%，托管费率为 0.10%，基金经理(现任)为 示例值，基金管理人为 示例值。

## 2. 收益率查询

### 2.1 510300今年的收益率是多少

- 覆盖状态：已解决
- intent：`performance`
- fundcode：`510300`
- projection：`fundcode`, `ths_yeild_ytd_fund`, `ths_yeild_rank_ytd_fund_origin`, `ths_yeild_rank_ytd_etf`
- 回答：

> 510300 的今年以来收益率为 8.88%，今年以来同类排名为 100/500，今年以来 ETF 排名为 12。

### 2.2 159919近1年收益，同类排名第几

- 覆盖状态：已解决
- intent：`performance`
- fundcode：`159919`
- projection：`fundcode`, `ths_yeild_1y_fund`, `ths_yeild_rank_1y_fund_origin`, `ths_yeild_rank_1y_etf`
- 回答：

> 159919 的近1年收益率为 8.88%，近1年同类排名为 100/500，近1年 ETF 排名为 12。

### 2.3 510500成立以来收益怎么样

- 覆盖状态：已解决
- intent：`performance`
- fundcode：`510500`
- projection：`fundcode`, `ths_yeild_std_fund`, `ths_yeild_rank_std_fund_origin`, `ths_yeild_rank_std_etf`
- 回答：

> 510500 的成立以来收益率为 8.88%，成立以来同类排名为 100/500，成立以来 ETF 排名为 12。

### 2.4 帮我查510300各周期的收益率

- 覆盖状态：已解决
- intent：`performance`
- fundcode：`510300`
- projection：`fundcode`, `ths_yeild_1w_fund`, `ths_yeild_1m_fund`, `ths_yeild_3m_fund`, `ths_yeild_6m_fund`, `ths_yeild_1y_fund`, `ths_yeild_2y_fund`, `ths_yeild_3y_fund`, `ths_yeild_5y_fund`, `ths_yeild_ytd_fund`, `ths_yeild_std_fund`
- 回答：

> 510300 的近1周收益率为 8.88%，近1月收益率为 8.88%，近3月收益率为 8.88%，近6月收益率为 8.88%，近1年收益率为 8.88%，近2年收益率为 8.88%，近3年收益率为 8.88%，近5年收益率为 8.88%，今年以来收益率为 8.88%，成立以来收益率为 8.88%。

## 7. 基金经理

### 7.1 510300的基金经理是谁

- 覆盖状态：已解决
- intent：`manager`
- fundcode：`510300`
- projection：`fundcode`, `ths_fund_manager_current_fund`, `ths_fund_supervisor_fund`
- 回答：

> 510300 的基金经理(现任)为 示例值，基金管理人为 示例值。

## 8. 分红信息

### 8.1 510300有没有分红记录

- 覆盖状态：已解决
- intent：`dividend`
- fundcode：`510300`
- projection：`fundcode`, `ths_accum_dividend_total_amt_fund`, `ths_accum_dividend_times_fund`
- 回答：

> 510300 的累计分红总额为 3，累计分红次数为 3。

### 8.2 159919的分红情况

- 覆盖状态：已解决
- intent：`dividend`
- fundcode：`159919`
- projection：`fundcode`, `ths_accum_dividend_total_amt_fund`, `ths_accum_dividend_times_fund`
- 回答：

> 159919 的累计分红总额为 3，累计分红次数为 3。

## 10. 边界/异常场景

### 10.1 000001有这只ETF吗

- 覆盖状态：已解决
- intent：`basic_info`
- fundcode：`000001`
- projection：`fundcode`, `ths_fund_extended_inner_short_name_fund`, `ths_name_of_tracking_index_fund`, `ths_fund_scale_fund`
- 回答：

> 未在 ETF 数据库中找到代码 000001 对应的 ETF。

### 10.3 510300近一周收益

- 覆盖状态：已解决
- intent：`performance`
- fundcode：`510300`
- projection：`fundcode`, `ths_yeild_1w_fund`, `ths_yeild_rank_1w_fund_origin`, `ths_yeild_rank_1w_etf`
- 回答：

> 510300 的近1周收益率为 8.88%，近1周同类排名为 100/500，近1周 ETF 排名为 12。

## 未纳入本副本的问题

以下问题来自 `test-questions.md`，但当前 v1 未明确解决，或 dry-run 虽有返回但语义覆盖不足，因此不计入“已解决”。

- 3.1 `510300前十大重仓股是什么`
- 3.2 `159919的持仓行业有哪些`
- 3.3 `510500最新季报的持仓`
- 3.4 `帮我看看510300的机构持有情况`
- 4.1 `帮我找沪深300相关的ETF`
- 4.2 `搜索中证500`
- 4.3 `找一下创业板ETF`
- 4.4 `搜索MSCI中国A股`
- 4.5 `有没有ETF名字里带医药的`
- 5.1 `帮我筛选所有股票型ETF`
- 5.2 `找上交所规模前10的ETF`
- 5.3 `哪些ETF管理费率最低`
- 5.4 `筛选跟踪沪深300指数的ETF，按收益率排序`
- 5.5 `找规模大于10亿的ETF`
- 5.6 `筛选深交所的债券型ETF`
- 6.1 `对比510300、510500和159919`
- 6.2 `帮我对比一下512880和510300`
- 6.3 `对比所有跟踪沪深300的前5只ETF，看收益和费率`
- 7.2 `510300现任基金经理管理了多久`
- 7.3 `查一下510300基金经理的历史业绩`
- 9.1 `帮我找跟踪沪深300指数、费率最低的ETF，然后看它的基本信息和收益`
- 9.2 `股票型ETF里今年收益最高的5只是哪些？对比一下`
- 9.3 `搜索中证红利，查一下它的基本信息和持仓`
- 10.2 `帮我查510300的实时行情`
- 10.4 `有没有名字叫"人工智能"的ETF`
