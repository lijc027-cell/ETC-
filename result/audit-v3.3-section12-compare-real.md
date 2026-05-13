# v3.3 Section 12 Expected Compare

## Summary

- total_cases: `8`
- scoped_cases: `8`
- passed: `8`
- failed: `0`
- expected_answer_match_total: `2`
- expected_answer_mismatch_total: `6`
- release_pass: `true`

## Cases

### 十二.1 000001有这只ETF吗

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `executable_empty_result_not_found`
- actual_outcome: `ExecutableQuery(single/basic_info)`
- routing_type: `ExecutableQuery`
- recognized_query_mode: `single`
- intent: `basic_info`

**Expected**

未查到这只ETF。

**Actual**

未在 ETF 数据库中找到代码 000001 对应的 ETF。

### 十二.2 帮我查510300的实时行情

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `DeniedQuery(realtime_not_supported)`
- actual_outcome: `DeniedQuery(deny/realtime_not_supported)`
- routing_type: `DeniedQuery`
- recognized_query_mode: `deny`
- intent: `realtime_not_supported`

**Expected**

这套远端库不提供实时行情。当前能直接查到的是最新净值，510300 在 2026-05-12 的单位净值是 4.9646。

**Actual**

这套远端库不提供实时行情。当前能直接查到的是最新净值，510300 在 2026-05-12 的单位净值是 4.9646。

### 十二.3 abcdef是什么基金

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `ClarificationRequired(invalid_fundcode)`
- actual_outcome: `ClarificationRequired(clarify/invalid_fundcode)`
- routing_type: `ClarificationRequired`
- recognized_query_mode: `clarify`
- intent: `invalid_fundcode`

**Expected**

这不是有效的 ETF 代码，当前也查不到对应基金。

**Actual**

这不是有效的 ETF 代码，当前也查不到对应基金。

### 十二.4 510300的持仓行业是什么（季报年报都没有）

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `ExecutableQuery(report_industry)+premise_correction`
- actual_outcome: `ExecutableQuery(report/report_industry)`
- routing_type: `ExecutableQuery`
- recognized_query_mode: `report`
- intent: `report_industry`

**Expected**

就 510300 来说，并不属于“季报年报都没有”的情况。当前远端库里有 2025 年一季报持仓行业数据：食品饮料、银行、非银金融、电力设备、家用电器、公用事业、汽车、有色金属、电子、国防军工。

**Actual**

就 510300 来说，并不属于“季报年报都没有”的情况。当前远端库里有 2025年一季报持仓行业数据：食品饮料、银行、非银金融、电力设备、家用电器、公用事业、汽车、有色金属、电子、国防军工。

### 十二.5 对比510300和000000

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `compare_partial_found`
- actual_outcome: `ExecutableQuery(compare/compare)`
- routing_type: `ExecutableQuery`
- recognized_query_mode: `compare`
- intent: `compare`

**Expected**

510300 能查到，000000 未查到。下面是 510300 的可查数据：

| 指标 | 510300 |
| --- | --- |
| 基金简称 | 沪深300ETF |
| 基金规模 | 1656.77 亿元 |
| 管理费率 | 0.15% |
| 今年以来收益率 | 7.15% |

数据截至 2026-05-12。

**Actual**

510300 能查到，000000 未查到。下面是 510300 的可查数据：

| 指标 | 510300 |
| --- | --- |
| 基金简称 | 沪深300ETF |
| 基金规模 | 1656.77 亿元（2026-05-12） |
| 管理费率 | 0.15% |
| 托管费率 | 0.05% |
| 今年以来收益率 | 7.15% |
| 近1年收益率 | 30.51% |
| 跟踪指数名称 | 沪深300指数 |

数据截至 2026-05-12。

### 十二.6 给我推荐一只ETF

- pass/fail: `PASS`
- answer_match: `true`
- expected_outcome: `DeniedQuery(investment_advice)`
- actual_outcome: `DeniedQuery(deny/investment_advice)`
- routing_type: `DeniedQuery`
- recognized_query_mode: `deny`
- intent: `investment_advice`

**Expected**

这个属于投资建议，我不直接给推荐。

**Actual**

这个属于投资建议，我不直接给推荐。

### 十二.7 今天A股大盘怎么样

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `DeniedQuery(unsupported_domain)`
- actual_outcome: `DeniedQuery(deny/unsupported_domain)`
- routing_type: `DeniedQuery`
- recognized_query_mode: `deny`
- intent: `unsupported_domain`

**Expected**

这个超出当前 ETF 数据库查询范围，我这里没有大盘实时或当日综述数据。

**Actual**

这个超出当前 ETF 数据库查询范围，我这里没有大盘实时或当日综述数据。

### 十二.8 510300能买吗

- pass/fail: `PASS`
- answer_match: `true`
- expected_outcome: `DeniedQuery(investment_advice)`
- actual_outcome: `DeniedQuery(deny/investment_advice)`
- routing_type: `DeniedQuery`
- recognized_query_mode: `deny`
- intent: `investment_advice`

**Expected**

这属于投资建议问题，我不直接回答“能不能买”。

**Actual**

这属于投资建议问题，我不直接回答“能不能买”。
