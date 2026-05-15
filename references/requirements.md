# ETF Query MCP 优化需求

## 优先级总览

### P0 — 数据已就绪，可立即开发

| #   | 需求      | intent 命名         | 涉及表             | 字段数 |
| --- | ------- | ----------------- | --------------- | --- |
| 七   | 申赎状态查询  | `purchase_status` | tb_ths_etf_base | 2   |
| 八   | 成交量/换手率 | `liquidity`       | tb_ths_etf_base | 2   |

### P1 — 修复已有功能的 bug

| #   | 需求                           | 问题                                      |
| --- | ---------------------------- | --------------------------------------- |
| 五.1 | nav_on_date LLM 格式化          | 已实现：指定日期净值通过 timeseries_semantics 精确匹配 btime |
| 五.2 | report mode 年份/报告期 validator | 已实现：report_period 硬合同允许用户证据支持的 year_num/type_num |

### P2 — 数据已就绪，但需新 AST 类型或复杂逻辑

| #   | 需求        | intent 命名      | 涉及字段                                      | 难点               |
| --- | --------- | -------------- | ----------------------------------------- | ---------------- |
| 六   | 净值走势图     | `nav_trend`    | ths_unit_nv_fund                          | 需 timeseries AST |
| 九   | 规模/份额变动趋势 | `scale_change` | ths_fund_scale_fund, ths_fund_shares_fund | 时序数组处理           |

### P3 — 待数据库入库后开发

| #   | 需求                    | intent 命名            | 字段数 | 字段类型          |
| --- | --------------------- | -------------------- | --- | ------------- |
| 十   | 估值指标 (PB/PE/ROE)      | `valuation`          | 3   | scalar        |
| 十一  | 风险指标 (波动率/回撤/夏普/跟踪误差) | `risk_metrics`       | 4   | scalar        |
| 十二  | 资金流向                  | `fund_flow`          | 4   | scalar        |
| 十三  | 交易活跃度 (日均换手率/成交额)     | 归入 `liquidity`       | 2   | scalar        |
| 十四  | 股息率                   | `dividend`           | 1   | scalar        |
| 十五  | 份额变动 (每日/近5日/净流入天数)   | 归入 `scale_change`    | 3   | scalar (计算字段) |
| 十六  | 综合费率                  | 归入现有费率               | 1   | scalar (计算字段) |
| 十七  | 溢价率                   | `premium`            | 1   | scalar        |
| 十八  | 规模变动率                 | 归入 `scale_change`    | 1   | scalar (计算字段) |
| 十九  | 基准成份权重                | `index_constituents` | 2   | array         |

#

---

## 一、新增 nav_on_date 意图 ✓

**场景**："510500 5月11日单位净值"

**改动文件**：`etf_agent/v3.py`, `etf_agent/capability_registry.py`, `etf_agent/ast_validator.py`

- [x] `SUPPORTED_INTENTS` 新增 `"nav_on_date"`
- [x] `_INTENT_DESCRIPTIONS` 新增 embedding 描述
- [x] `_lexical_infer_intent` — 净值 + 日期信号 → nav_on_date（优先级在 fund_scale 之前）
- [x] `_question_has_date_signal()` — 正则匹配 `\d+月\d+日|\d+\.\d+|\d+号|\d+日`
- [x] `_force_v3_0_single_classification` — "净值"快捷路由排除含日期信号的问题
- [x] capability 注册 v3.1/v3.3：`fundcode + name + ths_unit_nv_fund`
- [x] `ast_validator.ALLOWED_QUERY_INTENTS` 加入 `("single", "nav_on_date")`
- [x] `_select_fields` / `_answer_fields` 新增 nav_on_date 分支
- [x] 指定日期净值通过 `timeseries_semantics.mode=specified` 传递目标日期，并在执行结果阶段按 `btime` 精确匹配

## 二、开通季报/年报/持仓/重仓股/机构持有/投资风格查询 ✓

**场景**：季报、年报、持仓、重仓股、概念等 report 类内容

**改动文件**：`etf_agent/v3.py`

- [x] `_force_unsupported_classification` — report 关键词从硬挡改为路由到 report mode
- [x] 触发词：持仓/重仓/行业/概念/前十大/机构持有/投资风格/净资产
- [x] 新增 "一季报/中报/三季报/Q1/Q2/Q3/Q4" 触发 report mode
- [x] embedding 路径去掉 report 关键词硬挡

## 三、季报 vs 年报按用户语义路由 ✓

**改动文件**：`etf_agent/report_scope.py`

- [x] `resolve_report_scope` — 关键词优先：年报/年度 → year，季报/Q1/Q2/Q3 → quarter
- [x] 未指定时 intent-based fallback：institution_holding/report_style/report_holding → year；concept/industry → quarter
- [x] `report_collection` — 按 scope 前缀决定表名，不再按 intent 写死

## 四、报告期提取 ✓

**改动文件**：`etf_agent/v3.py`

- [x] `_extract_report_period()` — Q1/一季报→type_num=1, 中报→2, Q3→3, 年报→4, 未指定→latest
- [x] `_v3_3_execution_context` — report_period 不再写死 `{"mode": "latest"}`
- [x] validator 已允许 report 查询中由 `report_period` 用户证据支持的 `year_num` / `type_num` 过滤，并拒绝不匹配报告期的额外 where 条件

## 五、待修复问题

| #   | 问题                               | 根因                                                      | 修复方向                                                   |
| --- | -------------------------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| 1   | Windows 终端中文乱码                   | 输出编码非 UTF-8                                             | 统一设 `PYTHONIOENCODING=utf-8`                           |
| 2   | MCP 未在工作目录生效                     | Claude Code 不在项目目录启动时不会加载 .mcp.json                     | 改为 user 级别 MCP 配置或全局注册                                 |

---

## 六、净值走势图 (P2)

**场景**："510500 近一年净值走势"、"159919 成立以来净值曲线"

**intent**：`nav_trend`

**字段**：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_unit_nv_fund` | array | `[{value, btime}]` |

**开发项**：

- [ ] 新增 timeseries AST 类型，LLM 知道数组需完整返回而非只取单点
- [ ] `_answer_fields` / `_select_fields` 新增 nav_trend 分支
- [ ] v3.x capability 注册：select `fundcode + name + ths_unit_nv_fund`
- [ ] keyword：净值走势、净值曲线、净值趋势、净值图
- [ ] embedding："净值走势图、净值历史曲线、净值变化趋势"

---

## 七、申赎状态查询 (P0)

**场景**："510500 可以申购吗"、"159919 开放赎回了吗"

**intent**：`purchase_status`

**字段**（scalar，已入库）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_pur_and_redemp_status_fund` | string | 申购赎回状态，如"正常申购\|正常赎回" |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `purchase_status`
- [ ] `_lexical_infer_intent` keyword：申购、赎回、开放、暂停、申赎、申赎状态
- [ ] v3.1 capability：select `fundcode + name + ths_pur_and_redemp_status_fund`
- [ ] `ast_validator.ALLOWED_QUERY_INTENTS` 加入 `("single", "purchase_status")`
- [ ] `_select_fields` / `_answer_fields` 新增 purchase_status 分支
- [ ] embedding："申购状态、赎回状态、是否开放申购、是否开放赎回、申赎信息"

---

## 八、成交量/换手率 (P0)

**场景**："510500 换手率"、"159919 成交量"

**intent**：`liquidity`

**字段**（scalar，已入库，当前被 deny）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_turnover_rate_fund` | number | 换手率 (%) |
| `ths_turn_vol_fund` | number | 成交量 (手) |
| `ths_amt_fund` | array | 成交额 `[{value, btime}]` |

**开发项**：

- [ ] 将 `ths_turnover_rate_fund`、`ths_turn_vol_fund` 从 deny list 移除
- [ ] `SUPPORTED_INTENTS` 新增 `liquidity`
- [ ] `_lexical_infer_intent` keyword：换手率、成交量、成交额、流动性、活跃度
- [ ] v3.1 capability：select `fundcode + name + ths_turnover_rate_fund + ths_turn_vol_fund + ths_amt_fund`
- [ ] `ast_validator.ALLOWED_QUERY_INTENTS` 加入 `("single", "liquidity")`
- [ ] `_select_fields` / `_answer_fields` 新增 liquidity 分支
- [ ] embedding："换手率、成交量、成交额、流动性、交投活跃度"

---

## 九、规模/份额变动趋势 (P2)

**场景**："510500 近一年规模变化"、"159919 份额变化趋势"

**intent**：`scale_change`

**字段**（array，已入库）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_fund_scale_fund` | array | 基金规模 `[{value, btime}]`，单位：元 |
| `ths_fund_shares_fund` | array | 基金份额 `[{value, btime}]` |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `scale_change`
- [ ] `_lexical_infer_intent` keyword：规模变动、规模变化、份额变动、份额变化、份额趋势
- [ ] v3.1 capability：select `fundcode + name + ths_fund_scale_fund + ths_fund_shares_fund`
- [ ] `ast_validator.ALLOWED_QUERY_INTENTS` 加入 `("single", "scale_change")`
- [ ] `_select_fields` / `_answer_fields` 新增 scale_change 分支
- [ ] embedding："基金规模变化、份额变动趋势、规模走势"

---

## 十、估值指标 (P3 — 待数据入库)

**场景**："510500 重仓股平均PE"、"159919 PB是多少"

**intent**：`valuation`

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_top_held_average_pb_fund` | number | 重仓股平均持股PB |
| `ths_top_held_average_pe_fund` | number | 重仓股平均持股PE |
| `ths_top_held_average_roe_fund` | number | 重仓股平均持股ROE |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `valuation`
- [ ] keyword：PB、PE、ROE、市净率、市盈率、估值
- [ ] v3.1 capability：select `fundcode + name + ths_top_held_average_pb_fund + ths_top_held_average_pe_fund + ths_top_held_average_roe_fund`
- [ ] embedding："重仓股平均PB、PE、ROE、持仓估值水平"

---

## 十一、风险指标 (P3 — 待数据入库)

**场景**："510500 年化波动率"、"159919 最大回撤"、"510300 夏普比率"

**intent**：`risk_metrics`

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_annual_volatility_fund` | number | 年化波动率（近1年/240日） |
| `ths_max_retrace_rate_one_year` | number | 近1年最大回撤，需指定区间参数 |
| `ths_sharp_annual_fund` | number | 年化夏普比率 |
| `ths_tracking_error_fund` | number | 跟踪误差，计算较复杂 |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `risk_metrics`
- [ ] keyword：波动率、最大回撤、夏普比率、跟踪误差、风险
- [ ] v3.1 capability：select `fundcode + name + ths_annual_volatility_fund + ths_max_retrace_rate_one_year + ths_sharp_annual_fund + ths_tracking_error_fund`
- [ ] embedding："年化波动率、最大回撤、夏普比率、跟踪误差、风险指标"

---

## 十二、资金流向 (P3 — 部分已入库)

**场景**："510500 资金流向"、"159919 净买入额"

**intent**：`fund_flow`

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_inflow_amt_fund` | number | 流入额 |
| `ths_outflow_amt_fund` | number | 流出额 |
| `ths_net_buy_amt_fund` | number | 净买入额 |
| `ths_interval_netcashflow_fund` | number | 区间净流入额 |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `fund_flow`
- [ ] keyword：资金流向、流入额、流出额、净买入、净流入
- [ ] v3.1 capability：select `fundcode + name + ths_inflow_amt_fund + ths_outflow_amt_fund + ths_net_buy_amt_fund + ths_interval_netcashflow_fund`
- [ ] embedding："资金流向、主力资金、净流入、净流出"

---

## 十三、交易活跃度 (P3 — 待数据入库，归入 liquidity intent)

**场景**："510500 日均换手率"、"159919 日均成交额"

**intent**：归入 `liquidity`（与八合并）

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_daily_avg_turnover_int_fund` | number | 日均换手率 |
| `ths_daily_avg_amt_int_fund` | number | 日均成交额 |

**开发项**：

- [ ] 在 P0 的 `liquidity` intent 基础上扩展 capability，新增以上 2 个字段
- [ ] keyword 补充：日均换手率、日均成交额

---

## 十四、股息率 (P3 — 待数据入库)

**场景**："510500 股息率"、"红利ETF 股息率TTM"

**intent**：`dividend`

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_dividend_yield_ttm_ex_sd_fund` | number | 股息率TTM（近12个月） |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `dividend`
- [ ] keyword：股息率、分红率、TTM
- [ ] v3.1 capability：select `fundcode + name + ths_dividend_yield_ttm_ex_sd_fund`
- [ ] embedding："股息率、分红收益率、TTM股息率"

---

## 十五、份额变动 (P3 — 计算字段，归入 scale_change intent)

**场景**："510500 近5日份额变动"、"159919 份额净流入天数"

**intent**：归入 `scale_change`（与九合并）

**字段**（scalar，由 `ths_fund_shares_fund` 时序数据派生）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `daily_share_fluctuation` | number | 每日份额变动 |
| `5_day_share_fluctuation` | number | 近5日份额变动 |
| `net_inflow_days_of_shares` | number | 区间内每日份额变动为正的天数 |

**开发项**：

- [ ] 在 P2 的 `scale_change` intent 基础上扩展 capability
- [ ] 需确认：这三个字段入库后是直接查询还是代码计算

---

## 十六、综合费率 (P3 — 计算字段)

**场景**："510500 综合费率"、"哪只ETF费率最低"

**intent**：归入现有费率查询（与 `ths_manage_fee_rate_fund` / `ths_mandate_fee_rate_fund` 同组）

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `composite_fee_rate` | number | 综合费率 = 管理费率 + 托管费率 + 其他费用 |

**开发项**：

- [ ] 如果入库为独立字段：在现有费率 capability 中新增 `composite_fee_rate`
- [ ] 如果是计算字段：在 answer 层做加法计算
- [ ] keyword 补充：综合费率、总费率、持有成本

---

## 十七、溢价率 (P3 — 待数据入库)

**场景**："510500 溢价率"、"159919 折价还是溢价"

**intent**：`premium`

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_etf_premium_rate_fund` | number | ETF基金溢价率 (%) |

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `premium`
- [ ] keyword：溢价率、折溢价、折价、溢价
- [ ] v3.1 capability：select `fundcode + name + ths_etf_premium_rate_fund`
- [ ] embedding："溢价率、折溢价率、折价溢价"

---

## 十八、规模变动率 (P3 — 计算字段，归入 scale_change intent)

**场景**："510500 近3个月规模变动率"

**intent**：归入 `scale_change`

**字段**（scalar）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `rate_of_change_fund_scale_three_month` | number | 近3个月基金规模变动率 (%) |

**开发项**：

- [ ] 在 `scale_change` capability 中新增此字段
- [ ] 如果是计算字段，由 `ths_fund_scale_fund` 时序数据派生

---

## 十九、基准成份权重 (P3 — 部分已入库)

**场景**："510500 成份股权重分布"

**intent**：`index_constituents`

**字段**（array）：
| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ths_fund_basement_fund` | array | 基准成份代码 |
| `ths_fund_basement_ratio_fund` | array | 基准成份权重，配对使用 |

**注意**：此为指数基准成份权重（如沪深300指数成份），非基金实际持仓权重。后者已在 report mode 覆盖。

**开发项**：

- [ ] `SUPPORTED_INTENTS` 新增 `index_constituents`
- [ ] keyword：成份股、基准成份、指数权重、成份权重
- [ ] v3.1 capability：select `fundcode + name + ths_fund_basement_fund + ths_fund_basement_ratio_fund`
- [ ] 考虑是否走 expand（array 展开）逻辑
- [ ] embedding："指数成份股、基准成份权重、跟踪指数构成"

---
