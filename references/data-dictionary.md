# ETF 数据字典

## tb_ths_etf_base（基础信息集合）

### 基金标识

| 字段名                                       | 中文名         | 类型     | 说明                 |
| ----------------------------------------- | ----------- | ------ | ------------------ |
| `fundcode`                                | 基金代码        | string | 6位数字，如 510300      |
| `thscode`                                 | THS 代码      | string | 带交易所后缀，如 510300.SH |
| `ths_fund_extended_inner_short_name_fund` | 基金简称        | string | 场内简称               |
| `ths_fund_type_fund`                      | 基金类型        | string | 如"契约型开放式"          |
| `ths_fund_invest_type_fund`               | 基金投资类型      | string | 股票型/债券型/混合型/货币等    |
| `ths_tracking_index_code_fund`            | 跟踪指数代码      | string | 如 000051           |
| `ths_name_of_tracking_index_fund`         | 跟踪指数名称      | string | 如"沪深300指数"         |
| `ths_perf_comparative_benchmark_fund`     | 业绩比较基准      | string |                    |
| `ths_pur_and_redemp_status_fund`          | 申购赎回状态      | string | 如"正常申购\|正常赎回"      |
| `ths_etf_to_code_fund`                    | ETF关联联接基金代码 | string | 逗号分隔               |

### 时间信息

| 字段名                                | 中文名   | 类型     | 说明           |
| ---------------------------------- | ----- | ------ | ------------ |
| `ths_fund_establishment_date_fund` | 基金成立日 | string | 如 2019-06-12 |

### 规模与净值

| 字段名                      | 中文名     | 类型     | 说明   |
| ------------------------ | ------- | ------ | ---- |
| `ths_fund_scale_fund`    | 基金规模    | number | 单位：元 |
| `ths_fund_shares_fund`   | 基金份额    | number |      |
| `ths_current_mv_fund`    | 总市值     | number | 单位：元 |
| `ths_unit_nv_fund`       | 单位净值    | number |      |
| `ths_unit_nvg_rate_fund` | 单位净值增长率 | number | 百分比  |

### 收益率（各周期）

| 字段名                  | 中文名     | 类型     |
| -------------------- | ------- | ------ |
| `ths_yeild_1w_fund`  | 近1周收益率  | number |
| `ths_yeild_1m_fund`  | 近1月收益率  | number |
| `ths_yeild_3m_fund`  | 近3月收益率  | number |
| `ths_yeild_6m_fund`  | 近6月收益率  | number |
| `ths_yeild_1y_fund`  | 近1年收益率  | number |
| `ths_yeild_2y_fund`  | 近2年收益率  | number |
| `ths_yeild_3y_fund`  | 近3年收益率  | number |
| `ths_yeild_5y_fund`  | 近5年收益率  | number |
| `ths_yeild_ytd_fund` | 今年以来收益率 | number |
| `ths_yeild_std_fund` | 成立以来收益率 | number |

### 同类排名

> **排名字段说明**：
> 
> - `_fund_origin`（string）：完整排名字符串，格式如 `"4247/22901"`（排名/同类总数），适合展示
> - `_fund`（number）：纯数字排名，如 `4247`，适合排序和比较
> - `_etf`（number）：仅在 ETF 内部的排名

| 字段名                              | 中文名         | 类型     | 说明          |
| -------------------------------- | ----------- | ------ | ----------- |
| `ths_yeild_rank_1w_fund`         | 近1周同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_1w_fund_origin`  | 近1周同类排名     | string | 如 "100/500" |
| `ths_yeild_rank_1w_etf`          | 近1周 ETF 排名  | number | ETF 内排名     |
| `ths_yeild_rank_1m_fund`         | 近1月同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_1m_fund_origin`  | 近1月同类排名     | string |             |
| `ths_yeild_rank_1m_etf`          | 近1月 ETF 排名  | number |             |
| `ths_yeild_rank_3m_fund`         | 近3月同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_3m_fund_origin`  | 近3月同类排名     | string |             |
| `ths_yeild_rank_3m_etf`          | 近3月 ETF 排名  | number |             |
| `ths_yeild_rank_6m_fund`         | 近6月同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_6m_fund_origin`  | 近6月同类排名     | string |             |
| `ths_yeild_rank_6m_etf`          | 近6月 ETF 排名  | number |             |
| `ths_yeild_rank_1y_fund`         | 近1年同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_1y_fund_origin`  | 近1年同类排名     | string |             |
| `ths_yeild_rank_1y_etf`          | 近1年 ETF 排名  | number |             |
| `ths_yeild_rank_2y_fund`         | 近2年同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_2y_fund_origin`  | 近2年同类排名     | string |             |
| `ths_yeild_rank_2y_etf`          | 近2年 ETF 排名  | number |             |
| `ths_yeild_rank_3y_fund`         | 近3年同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_3y_fund_origin`  | 近3年同类排名     | string |             |
| `ths_yeild_rank_3y_etf`          | 近3年 ETF 排名  | number |             |
| `ths_yeild_rank_5y_fund`         | 近5年同类排名     | number | 纯数字排名       |
| `ths_yeild_rank_5y_fund_origin`  | 近5年同类排名     | string |             |
| `ths_yeild_rank_5y_etf`          | 近5年 ETF 排名  | number |             |
| `ths_yeild_rank_ytd_fund`        | 今年以来同类排名    | number | 纯数字排名       |
| `ths_yeild_rank_ytd_fund_origin` | 今年以来同类排名    | string |             |
| `ths_yeild_rank_ytd_etf`         | 今年以来 ETF 排名 | number |             |
| `ths_yeild_rank_std_fund`        | 成立以来同类排名    | number | 纯数字排名       |
| `ths_yeild_rank_std_fund_origin` | 成立以来同类排名    | string |             |
| `ths_yeild_rank_std_etf`         | 成立以来 ETF 排名 | number |             |

### 基金经理

| 字段名                             | 中文名      | 类型     | 说明                                                                                                                                                         |
| ------------------------------- | -------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ths_fund_manager_current_fund` | 基金经理(现任) | string |                                                                                                                                                            |
| `ths_manager`                   | 基金经理详情   | array  | 包含 rank_num, ths_name_fund(姓名), ths_service_sd_fund(任职起始日), ths_service_duration_annual_return_fund(任职年化回报), ths_tenure_fund(任职天数), ths_rzjjzgm_fund(管理规模) |
| `ths_fund_supervisor_fund`      | 基金管理人    | string |                                                                                                                                                            |

### 基金经理详情子字段（ths_manager 数组内嵌字段，也作为独立字段存储）

| 字段名                                       | 中文名      | 类型     | 说明                               |
| ----------------------------------------- | -------- | ------ | -------------------------------- |
| `ths_service_sd_fund`                     | 任职起始日    | string | 如 "2024-02-02"，rank_num=1 为第一任经理 |
| `ths_name_fund`                           | 基金经理姓名   | string | rank_num=1 为第一任经理                |
| `ths_service_duration_annual_return_fund` | 任职期间年化回报 | number | 单位：%                             |
| `ths_rzjjzgm_fund`                        | 任职基金总规模  | number | 单位：元                             |
| `ths_tenure_fund`                         | 任职天数     | number |                                  |

### 交易类指标

| 字段名                               | 中文名    | 类型     | 说明  |
| --------------------------------- | ------ | ------ | --- |
| `ths_amt_fund`                    | 成交额    | number |     |
| `ths_netcashflow_fund`            | 净现金流   | number |     |
| `ths_margin_trading_balance_fund` | 融资余额   | number |     |
| `ths_short_selling_amtb_fund`     | 融券卖出金额 | number |     |

### 其他补充字段

| 字段名                                   | 中文名           | 类型     | 说明  |
| ------------------------------------- | ------------- | ------ | --- |
| `ths_similar_fund_std_avg_yield_fund` | 同类基金成立以来平均收益率 | number |     |

### 费率

| 字段名                         | 中文名  | 类型     | 说明  |
| --------------------------- | ---- | ------ | --- |
| `ths_manage_fee_rate_fund`  | 管理费率 | number | 百分比 |
| `ths_mandate_fee_rate_fund` | 托管费率 | number | 百分比 |

### 分红

| 字段名                                 | 中文名    | 类型     |
| ----------------------------------- | ------ | ------ |
| `ths_accum_dividend_total_amt_fund` | 累计分红总额 | number |
| `ths_accum_dividend_times_fund`     | 累计分红次数 | number |

### 其他

| 字段名                                    | 中文名    | 类型     |
| -------------------------------------- | ------ | ------ |
| `ths_invest_objective_fund`            | 投资目标   | string |
| `ths_invest_socpe_fund`                | 投资范围   | string |
| `ths_invest_philosophy_fund`           | 投资理念   | string |
| `ths_invest_strategy_fund`             | 投资策略   | string |
| `ths_risk_return_characteristics_fund` | 风险收益特征 | string |
| `ths_fund_listed_exchange_fund`        | 上市地点   | string |

---

## tb_ths_etf_report_quarter（季报集合）

| 字段名                                | 中文名     | 类型     | 说明                             |
| ---------------------------------- | ------- | ------ | ------------------------------ |
| `fundcode`                         | 基金代码    | string |                                |
| `thscode`                          | THS 代码  | string |                                |
| `year_num`                         | 年份      | number |                                |
| `type_num`                         | 报告期类型   | number | 1=一季报, 2=中报, 3=三季报, 4=年报       |
| `ths_top_n_top_industry_name_fund` | 前N大行业名称 | array  | [{value: "行业名", rank_num: 排名}] |
| `ths_zcgnmc_fund`                  | 重仓概念名称  | array  | [{value: "概念名", rank_num: 排名}] |

---

## tb_ths_etf_report_year（年报集合）

| 字段名                                        | 中文名         | 类型     | 说明                              |
| ------------------------------------------ | ----------- | ------ | ------------------------------- |
| `fundcode`                                 | 基金代码        | string |                                 |
| `thscode`                                  | THS 代码      | string |                                 |
| `year_num`                                 | 年份          | number |                                 |
| `type_num`                                 | 报告期类型       | number |                                 |
| `ths_org_investor_total_held_ratio_fund`   | 机构投资者持有比例   | number | 百分比                             |
| `ths_org_investor_total_held_shares_fund`  | 机构投资者持有份额   | number |                                 |
| `ths_invest_style_fund`                    | 投资风格        | string | 如"平衡型"、"成长型"                    |
| `ths_fanv_chg_fund`                        | 净资产变动       | number |                                 |
| `ths_fanv_chg_rate_fund`                   | 净资产变动率      | number | 百分比                             |
| `ths_top_n_top_industry_name_fund`         | 前N大行业名称     | array  | [{value: "行业名", rank_num: 排名}]  |
| `ths_top_n_top_industry_mv_to_equity_fund` | 前N大行业占比     | array  | [{value: 占比%, rank_num: 排名}]    |
| `ths_top_sec_code_fund`                    | 重仓证券代码      | array  | [{value: "股票代码", rank_num: 排名}] |
| `ths_top_n_top_stock_mv_to_equity_fund`    | 前N大股票占比     | array  | [{value: 占比%, rank_num: 排名}]    |
| `ths_top_held_stock_code_fund`             | 前十大重仓股代码    | array  | [{value: "股票代码", rank_num: 排名}] |
| `ths_top_stock_mv_to_fnv_fund`             | 前十大股票占基金净值比 | array  | [{value: 占比%, rank_num: 排名}]    |
