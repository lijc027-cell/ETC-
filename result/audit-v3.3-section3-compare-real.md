# v3.3 Section 3 Expected Compare

## Summary

- total_cases: `6`
- passed: `6`
- failed: `0`
- expected_answer_match_total: `0`
- expected_answer_mismatch_total: `6`

## Cases

### 三.1 510300的基金规模多大

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_fund_scale`
- actual_outcome: `ExecutableQuery(single/fund_scale)`

**Expected**

沪深300ETF 基金规模最新约 1724.05亿。

**Actual**

510300 的基金规模为 1686.60 亿元（2026-05-11）。

查询起始时间：2026-05-12T03:57:01.787642Z

查询结束时间：2026-05-12T03:57:11.121593Z

LLM token：2033

### 三.2 510300总市值多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_fund_scale`
- actual_outcome: `ExecutableQuery(single/fund_scale)`

**Expected**

沪深300ETF 总市值最新约 1723.28亿。

**Actual**

510300 的总市值为 1685.75 亿元。

查询起始时间：2026-05-12T03:57:11.122434Z

查询结束时间：2026-05-12T03:57:17.996130Z

LLM token：2018

### 三.3 510300最新净值是多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_fund_scale`
- actual_outcome: `ExecutableQuery(single/fund_scale)`

**Expected**

沪深300ETF 最新净值 4.8882，日期 2026-05-09。

**Actual**

510300 的单位净值为 4.968（2026-05-11）。

查询起始时间：2026-05-12T03:57:17.996998Z

查询结束时间：2026-05-12T03:57:25.090574Z

LLM token：2018

### 三.4 510300的份额有多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_fund_scale`
- actual_outcome: `ExecutableQuery(single/fund_scale)`

**Expected**

510300 的基金份额最新约 352.70 亿份。

**Actual**

510300 的基金份额为 339.46亿份（2026-05-11）。

查询起始时间：2026-05-12T03:57:25.092005Z

查询结束时间：2026-05-12T03:57:32.362579Z

LLM token：2027

### 三.5 510300的净值增长率是多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_fund_scale`
- actual_outcome: `ExecutableQuery(single/fund_scale)`

**Expected**

沪深300ETF 净值增长率最新为 -0.58%。

**Actual**

510300 的单位净值增长率为 1.64%（2026-05-11）。

查询起始时间：2026-05-12T03:57:32.364149Z

查询结束时间：2026-05-12T03:57:39.624814Z

LLM token：2034

### 三.6 510300的基金份额最近有变化吗

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_timeseries_latest_two`
- actual_outcome: `ExecutableQuery(single/fund_scale)`

**Expected**

510300 的基金份额最新为 352.70 亿份，较上一期持平。

**Actual**

510300 的基金份额为 339.46亿份（2026-05-11），较前一期 352.70亿份（2026-05-10）减少 -13.24亿份（-3.75%）。

查询起始时间：2026-05-12T03:57:39.626630Z

查询结束时间：2026-05-12T03:57:47.891993Z

LLM token：2138
