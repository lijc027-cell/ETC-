# v3.3 Section 11 Expected Compare

## Summary

- total_cases: `4`
- scoped_cases: `4`
- passed: `4`
- failed: `0`
- expected_answer_match_total: `0`
- expected_answer_mismatch_total: `4`
- release_pass: `true`

## Cases

### 十一.1 510300最近成交额多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_trading_metric_snapshot`
- actual_outcome: `ExecutableQuery(single/trading_metric)`
- recognized_query_mode: `single`
- intent: `trading_metric`

**Expected**

最新成交额104.57亿，日期2026-05-11。

**Actual**

510300 的基金简称为 沪深300ETF，成交额为 104.57 亿元（2026-05-11）。

数据起始日：2025-06-17

数据结束日：2026-05-11

### 十一.2 510300的净现金流是正还是负

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_trading_metric_snapshot`
- actual_outcome: `ExecutableQuery(single/trading_metric)`
- recognized_query_mode: `single`
- intent: `trading_metric`

**Expected**

最新净现金流为负，金额-65.41亿，日期2026-05-11。

**Actual**

510300 的基金简称为 沪深300ETF，净现金流为 -65.41 亿元（2026-05-11）。

数据起始日：2025-06-17

数据结束日：2026-05-11

### 十一.3 510300的融资余额是多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_trading_metric_snapshot`
- actual_outcome: `ExecutableQuery(single/trading_metric)`
- recognized_query_mode: `single`
- intent: `trading_metric`

**Expected**

远端字段在2026-05-11这期记录存在，但值为 `null`，当前暂无可用融资余额数据。

**Actual**

510300 的基金简称为 沪深300ETF，融资余额为 暂无数据。

数据起始日：2025-08-05

数据结束日：2026-05-11

### 十一.4 510300的融券卖出量多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_trading_metric_snapshot`
- actual_outcome: `ExecutableQuery(single/trading_metric)`
- recognized_query_mode: `single`
- intent: `trading_metric`

**Expected**

远端可直接提供的是融券金额字段；2026-05-11 这一期值为 `null`，当前暂无可用数据。

**Actual**

510300 的基金简称为 沪深300ETF，融券金额为 暂无数据。

数据起始日：2025-08-05

数据结束日：2026-05-11
