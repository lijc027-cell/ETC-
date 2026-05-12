# v3.3 Section 6 Expected Compare

## Summary

- total_cases: `3`
- scoped_cases: `3`
- passed: `3`
- failed: `0`
- expected_answer_match_total: `0`
- expected_answer_mismatch_total: `3`

## Cases

### 六.1 510300有没有分红记录

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_dividend`
- actual_outcome: `ExecutableQuery(single/dividend)`

**Expected**

有，累计分红14次，累计分红总额263.86亿。

**Actual**

510300 的累计分红总额为 263.86 亿元，累计分红次数为 14。

### 六.2 159919累计分红多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_dividend`
- actual_outcome: `ExecutableQuery(single/dividend)`

**Expected**

80.76亿，累计分红5次。

**Actual**

159919 的累计分红总额为 80.76 亿元。

### 六.3 510300分过几次红

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_single_dividend`
- actual_outcome: `ExecutableQuery(single/dividend)`

**Expected**

14次。

**Actual**

510300 的累计分红次数为 14。
