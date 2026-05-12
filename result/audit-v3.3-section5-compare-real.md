# v3.3 Section 5 Expected Compare

## Summary

- total_cases: `5`
- scoped_cases: `5`
- passed: `5`
- failed: `0`
- expected_answer_match_total: `0`
- expected_answer_mismatch_total: `5`

## Cases

### 五.1 510300的基金经理是谁

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_manager`
- actual_outcome: `ExecutableQuery(single/manager)`

**Expected**

柳军。

**Actual**

510300 的基金经理(现任)为 柳军，基金管理人为 华泰柏瑞基金。

### 五.2 510300现任基金经理管理了多久

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_manager_detail`
- actual_outcome: `ExecutableQuery(single/manager_detail)`

**Expected**

自2012-05-04起任职，5122天。

**Actual**

沪深300ETF（510300）现任基金经理柳军，自2012-05-04起任职，任职5122天，任职期间年化回报6.05%，任职基金总规模3388.01亿元。当前远端库仅返回现任基金经理信息，未提供更早历史更换记录。

### 五.3 510300基金经理的历史业绩怎么样

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_manager_detail`
- actual_outcome: `ExecutableQuery(single/manager_detail)`

**Expected**

任职期间年化回报6.05%。

**Actual**

沪深300ETF（510300）现任基金经理柳军，自2012-05-04起任职，任职5122天，任职期间年化回报6.05%，任职基金总规模3388.01亿元。当前远端库仅返回现任基金经理信息，未提供更早历史更换记录。

### 五.4 510300基金经理管了多少规模的基金

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_manager_detail`
- actual_outcome: `ExecutableQuery(single/manager_detail)`

**Expected**

3388.01亿。

**Actual**

沪深300ETF（510300）现任基金经理柳军，自2012-05-04起任职，任职5122天，任职期间年化回报6.05%，任职基金总规模3388.01亿元。当前远端库仅返回现任基金经理信息，未提供更早历史更换记录。

### 五.5 510300什么时候换的基金经理

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_manager_detail_timeline`
- actual_outcome: `ExecutableQuery(single/manager_detail)`

**Expected**

当前远端库仅返回现任基金经理柳军，起始日2012-05-04。

**Actual**

沪深300ETF（510300）现任基金经理柳军，自2012-05-04起任职，任职5122天，任职期间年化回报6.05%，任职基金总规模3388.01亿元。当前远端库仅返回现任基金经理信息，未提供更早历史更换记录。
