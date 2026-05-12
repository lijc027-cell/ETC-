# v3.3 Section 9 Expected Compare

## Summary

- total_cases: `5`
- scoped_cases: `5`
- passed: `5`
- failed: `0`
- expected_answer_match_total: `1`
- expected_answer_mismatch_total: `4`
- release_pass: `true`

## Cases

### 九.1 对比510300、510500和159919

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_compare`
- actual_outcome: `ExecutableQuery(compare/compare)`

**Expected**

510300：跟踪沪深300指数，管理费0.15%，托管费0.05%，最新规模1686.60亿，今年以来7.23%，近1年32.12%。510500：跟踪中证小盘500指数，管理费0.15%，托管费0.05%，最新规模497.66亿，今年以来18.43%，近1年57.15%。159919：跟踪沪深300指数，管理费0.15%，托管费0.05%，最新规模842.33亿，今年以来7.22%，近1年32.03%。

**Actual**

| 指标 | 510300 | 510500 | 159919 |
| --- | --- | --- | --- |
| 基金简称 | 沪深300ETF | 中证500ETF | 沪深300ETF |
| 基金规模 | 1686.60 亿元（2026-05-11） | 497.66 亿元（2026-05-11） | 842.33 亿元（2026-05-11） |
| 管理费率 | 0.15% | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% | 0.05% |
| 今年以来收益率 | 7.23% | 18.43% | 7.22% |
| 近1年收益率 | 32.12% | 57.15% | 32.03% |
| 跟踪指数名称 | 沪深300指数 | 中证小盘500指数 | 沪深300指数 |

数据截至 2026-05-11。

### 九.2 512880和510300哪个更好

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `DeniedQuery(investment_advice)`
- actual_outcome: `DeniedQuery(investment_advice)`

**Expected**

这个问题属于主观投资判断，我不直接给“哪个更好”的推荐。客观数据上，512880 是证券ETF国泰，510300 是沪深300ETF，二者跟踪标的和风险暴露不同。

**Actual**

抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。

### 九.3 对比所有跟踪沪深300的前5只ETF，看收益和费率

- pass/fail: `PASS`
- answer_match: `true`
- expected_outcome: `two_step_composite_filter_compare`
- actual_outcome: `ExecutableQuery(compare/two_step_composite)`

**Expected**

这里按近1年收益率从高到低选取前5只跟踪沪深300相关 ETF，再对比它们的收益和费率。排序依据：近1年收益率。

**Actual**

这里按近1年收益率从高到低选取前5只跟踪沪深300相关 ETF，再对比它们的收益和费率。排序依据：近1年收益率。

| 指标 | 515360 | 159393 | 561930 | 159300 | 515130 |
| --- | --- | --- | --- | --- | --- |
| 基金简称 | 沪深300ETF方正富邦 | 沪深300ETF万家 | 沪深300ETF招商 | 沪深300ETF富国 | 沪深300ETF博时 |
| 管理费率 | 0.15% | 0.15% | 0.15% | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% | 0.05% | 0.05% | 0.05% |
| 近1年收益率 | 35.58% | 35.17% | 34.86% | 33.80% | 33.48% |

数据截至 2026-05-11。

### 九.4 510300和510500比一下规模和费率

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_compare`
- actual_outcome: `ExecutableQuery(compare/compare)`

**Expected**

510300 最新规模1686.60亿，管理费0.15%，托管费0.05%；510500 最新规模497.66亿，管理费0.15%，托管费0.05%。规模上510300更大，费率相同。

**Actual**

| 指标 | 510300 | 510500 |
| --- | --- | --- |
| 基金简称 | 沪深300ETF | 中证500ETF |
| 基金规模 | 1686.60 亿元（2026-05-11） | 497.66 亿元（2026-05-11） |
| 管理费率 | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% |

数据截至 2026-05-11。

### 九.5 对比一下510300和159919的收益率

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `covered_compare`
- actual_outcome: `ExecutableQuery(compare/compare)`

**Expected**

510300：今年以来7.23%，近1年32.12%，成立以来131.84%。159919：今年以来7.22%，近1年32.03%，成立以来140.79%。短中期差距很小，成立以来159919略高。

**Actual**

| 指标 | 510300 | 159919 |
| --- | --- | --- |
| 基金简称 | 沪深300ETF | 沪深300ETF |
| 近1年收益率 | 32.12% | 32.03% |

数据截至 2026-05-11。
