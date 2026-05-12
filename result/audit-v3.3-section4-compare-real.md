# v3.3 Section 4 Expected Compare

## Summary

- total_cases: `9`
- scoped_cases: `9`
- passed: `9`
- failed: `0`
- expected_answer_match_total: `0`
- expected_answer_mismatch_total: `9`

## Cases

### 四.1 510300前十大重仓股是什么

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_expand_holding`
- actual_outcome: `ExecutableQuery(report/report_holding)`

**Expected**

2024年年报前十大重仓股：600519、300750、601318、600036、000333、600900、300059、600030、601166、000858。

**Actual**

510300 的2024年年报报告数据如下：
| 排名 | 前十大重仓股代码 | 前十大股票占基金净值比 |
| --- | --- | --- |
| 1 | 600519 | 4.60% |
| 2 | 300750 | 3.37% |
| 3 | 601318 | 2.72% |
| 4 | 600036 | 2.33% |
| 5 | 000333 | 1.76% |
| 6 | 600900 | 1.74% |
| 7 | 300059 | 1.57% |
| 8 | 600030 | 1.37% |
| 9 | 601166 | 1.34% |
| 10 | 000858 | 1.31% |

### 四.2 159919的持仓行业有哪些

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_expand_industry`
- actual_outcome: `ExecutableQuery(report/report_industry)`

**Expected**

2025年一季报行业：食品饮料、银行、非银金融、电力设备、家用电器、公用事业、汽车、有色金属、电子、社会服务。

**Actual**

159919 的2024年年报报告数据如下：
| 排名 | 前N大行业名称 | 前N大行业占比 |
| --- | --- | --- |
| 1 | 银行 | 24.58% |
| 2 | 非银金融 | 29.38% |
| 3 | 电子 | 34.11% |
| 4 | 食品饮料 | 37.95% |
| 5 | 电力设备 | 41.46% |
| 6 | 医药生物 | 43.49% |
| 7 | 汽车 | 44.43% |
| 8 | 计算机 | 45.36% |
| 9 | 公用事业 | 46.22% |
| 10 | 家用电器 | 47.06% |

### 四.3 510500最新季报的持仓

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_expand_quarter_industry`
- actual_outcome: `ExecutableQuery(report/report_industry)`

**Expected**

2025年一季报行业：电子、汽车、国防军工、机械设备、计算机、有色金属、家用电器；重仓概念：华为概念、物联网、人工智能、小米概念、虚拟现实、无人驾驶、新能源汽车、芯片概念、人形机器人、智能座舱。

**Actual**

510500 的2024年年报报告数据如下：
| 排名 | 前N大行业名称 | 前N大行业占比 |
| --- | --- | --- |
| 1 | 电子 | 10.36% |
| 2 | 医药生物 | 19.12% |
| 3 | 电力设备 | 22.80% |
| 4 | 非银金融 | 26.30% |
| 5 | 国防军工 | 28.68% |
| 6 | 计算机 | 30.21% |
| 7 | 基础化工 | 31.52% |
| 8 | 机械设备 | 32.79% |
| 9 | 有色金属 | 33.88% |
| 10 | 汽车 | 34.76% |

### 四.4 510300的机构持有比例是多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_scalar_institution_holding`
- actual_outcome: `ExecutableQuery(report/institution_holding)`

**Expected**

2024年年报机构投资者持有比例83.68%，持有份额747.99亿份。

**Actual**

510300 的2024年年报机构投资者持有比例为 83.68%，机构投资者持有份额为 7.48e+10。

### 四.5 510300的投资风格是什么

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_scalar_style`
- actual_outcome: `ExecutableQuery(report/report_style)`

**Expected**

平衡型基金。

**Actual**

510300 的2024年年报投资风格为 平衡型基金。

### 四.6 510300的净资产变动情况

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_scalar_nav_change`
- actual_outcome: `ExecutableQuery(report/report_nav_change)`

**Expected**

-379.19亿，变动率-9.54%。

**Actual**

510300 的2024年年报净资产变动为 -379.19 亿元，净资产变动率为 -9.54%。

### 四.7 159919重仓了哪些概念

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_expand_concept`
- actual_outcome: `ExecutableQuery(report/report_concept)`

**Expected**

2025年一季报重仓概念：高股息精选、同花顺中特估100、超级品牌、国企改革、同花顺出海50、储能、新能源汽车、锂电池概念、白酒概念、西部大开发。

**Actual**

159919 的2024年年报报告数据如下：
| 排名 | 重仓概念名称 |
| --- | --- |
| 1 | 高股息精选 |
| 2 | 同花顺中特估100 |
| 3 | 超级品牌 |
| 4 | 国企改革 |
| 5 | 白酒概念 |
| 6 | 西部大开发 |
| 7 | 同花顺出海50 |
| 8 | 储能 |
| 9 | 互联网保险 |
| 10 | 参股券商 |

### 四.8 510300年报里行业配置占比最高的前五个

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_expand_industry`
- actual_outcome: `ExecutableQuery(report/report_industry)`

**Expected**

银行24.59%、非银金融29.39%、电子34.16%、食品饮料38.00%、电力设备41.50%。

**Actual**

510300 的2024年年报报告数据如下：
| 排名 | 前N大行业名称 | 前N大行业占比 |
| --- | --- | --- |
| 1 | 银行 | 24.59% |
| 2 | 非银金融 | 29.39% |
| 3 | 电子 | 34.16% |
| 4 | 食品饮料 | 38.00% |
| 5 | 电力设备 | 41.50% |
| 6 | 医药生物 | 43.54% |
| 7 | 汽车 | 44.48% |
| 8 | 计算机 | 45.41% |
| 9 | 公用事业 | 46.27% |
| 10 | 家用电器 | 47.11% |

### 四.9 510300前十大重仓股占净值比多少

- pass/fail: `PASS`
- answer_match: `false`
- expected_outcome: `v3_3_report_expand_holding`
- actual_outcome: `ExecutableQuery(report/report_holding)`

**Expected**

600519 4.60%、300750 3.37%、601318 2.72%、600036 2.33%、000333 1.76%、600900 1.74%、300059 1.57%、600030 1.37%、601166 1.34%、000858 1.31%。

**Actual**

510300 的2024年年报报告数据如下：
| 排名 | 前十大重仓股代码 | 前十大股票占基金净值比 |
| --- | --- | --- |
| 1 | 600519 | 4.60% |
| 2 | 300750 | 3.37% |
| 3 | 601318 | 2.72% |
| 4 | 600036 | 2.33% |
| 5 | 000333 | 1.76% |
| 6 | 600900 | 1.74% |
| 7 | 300059 | 1.57% |
| 8 | 600030 | 1.37% |
| 9 | 601166 | 1.34% |
| 10 | 000858 | 1.31% |
