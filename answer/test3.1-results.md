# v3.0 + v3.1 抽取问题测试结果

测试来源：[`etf-query-test-questions.md`](../etf-query-test-questions.md)

运行方式：`.venv/bin/python scripts/generate_v3_1_results.py`

测试时间：2026-05-08

说明：

- 本轮从总问题集中抽取 `v3.0` 与 `v3.1` 范围内的问题。
- 使用 `semantic_query_v3(..., no_llm=True)`，跳过 LLM，但连接远端真实 MongoDB 执行查询。
- 本文件是远端真实 MongoDB 查询结果，不是 dry-run 示例数据。
- `v3.1` 覆盖 search / filter / sort / compare，以及 filter -> compare 派生演示。

## v3.0 问题

### Q1 510300是什么

- 来源章节：一、单只基金基本信息
- v3 路由：`single / basic_info`
- 判定：PASS

**实际回答**

510300 的基金简称为 沪深300ETF，跟踪指数名称为 沪深300指数，基金规模为 1777.76 亿元（2026-05-07）。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_name_of_tracking_index_fund",
    "ths_fund_scale_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    }
  ],
  "output_style": "summary"
}
```

---

### Q2 帮我查一下510500的基本信息

- 来源章节：一、单只基金基本信息
- v3 路由：`single / basic_info`
- 判定：PASS

**实际回答**

510500 的基金简称为 中证500ETF，跟踪指数名称为 中证小盘500指数，基金规模为 598.28 亿元（2026-05-07）。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510500"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_name_of_tracking_index_fund",
    "ths_fund_scale_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    }
  ],
  "output_style": "summary"
}
```

---

### Q3 159919这只基金跟踪什么指数

- 来源章节：一、单只基金基本信息
- v3 路由：`single / tracking_index`
- 判定：PASS

**实际回答**

159919 的跟踪指数代码为 000300，跟踪指数名称为 沪深300指数。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "159919"
  },
  "projection": [
    "fundcode",
    "ths_tracking_index_code_fund",
    "ths_name_of_tracking_index_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_tracking_index_code_fund",
      "label": "跟踪指数代码",
      "format": "plain"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q4 工银沪深300ETF的费率和基金经理是什么

- 来源章节：一、单只基金基本信息
- v3 路由：`single / fee_and_manager`
- 判定：PASS

**实际回答**

510350 的管理费率为 0.15%，托管费率为 0.05%，基金经理(现任)为 刘伟琳，基金管理人为 工银瑞信基金。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510350"
  },
  "projection": [
    "fundcode",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund",
    "ths_fund_manager_current_fund",
    "ths_fund_supervisor_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_mandate_fee_rate_fund",
      "label": "托管费率",
      "format": "percent"
    },
    {
      "field": "ths_fund_manager_current_fund",
      "label": "基金经理(现任)",
      "format": "plain"
    },
    {
      "field": "ths_fund_supervisor_fund",
      "label": "基金管理人",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q5 510300的管理人是谁

- 来源章节：一、单只基金基本信息
- v3 路由：`single / manager`
- 判定：PASS

**实际回答**

510300 的基金经理(现任)为 柳军，基金管理人为 华泰柏瑞基金。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_fund_manager_current_fund",
    "ths_fund_supervisor_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_manager_current_fund",
      "label": "基金经理(现任)",
      "format": "plain"
    },
    {
      "field": "ths_fund_supervisor_fund",
      "label": "基金管理人",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q6 510300今年的收益率是多少

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510300 的今年以来收益率为 6.12%，今年以来同类排名为 9150/24947，今年以来 ETF 排名为 800。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_yeild_ytd_fund",
    "ths_yeild_rank_ytd_fund_origin",
    "ths_yeild_rank_ytd_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_ytd_fund_origin",
      "label": "今年以来同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_ytd_etf",
      "label": "今年以来 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q7 159919近1年收益，同类排名第几

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

159919 的近1年收益率为 31.18%，近1年同类排名为 7126/22995，近1年 ETF 排名为 589。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "159919"
  },
  "projection": [
    "fundcode",
    "ths_yeild_1y_fund",
    "ths_yeild_rank_1y_fund_origin",
    "ths_yeild_rank_1y_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_1y_fund_origin",
      "label": "近1年同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_1y_etf",
      "label": "近1年 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q8 510500成立以来收益怎么样

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510500 的成立以来收益率为 193.25%，成立以来同类排名为 393/1157，成立以来 ETF 排名为 39。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510500"
  },
  "projection": [
    "fundcode",
    "ths_yeild_std_fund",
    "ths_yeild_rank_std_fund_origin",
    "ths_yeild_rank_std_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_std_fund",
      "label": "成立以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_std_fund_origin",
      "label": "成立以来同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_std_etf",
      "label": "成立以来 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q9 510300近3个月涨了多少

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510300 的近3月收益率为 5.66%，近3月同类排名为 6890/25234，近3月 ETF 排名为 627。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_yeild_3m_fund",
    "ths_yeild_rank_3m_fund_origin",
    "ths_yeild_rank_3m_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_3m_fund",
      "label": "近3月收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_3m_fund_origin",
      "label": "近3月同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_3m_etf",
      "label": "近3月 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q10 510300各周期的收益率给我看看

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510300 的近1周收益率为 1.94%，近1月收益率为 10.50%，近3月收益率为 5.66%，近6月收益率为 5.29%，近1年收益率为 31.27%，近2年收益率为 41.26%，近3年收益率为 31.29%，近5年收益率为 8.63%，今年以来收益率为 6.12%，成立以来收益率为 129.44%。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_yeild_1w_fund",
    "ths_yeild_1m_fund",
    "ths_yeild_3m_fund",
    "ths_yeild_6m_fund",
    "ths_yeild_1y_fund",
    "ths_yeild_2y_fund",
    "ths_yeild_3y_fund",
    "ths_yeild_5y_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_std_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_1w_fund",
      "label": "近1周收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1m_fund",
      "label": "近1月收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_3m_fund",
      "label": "近3月收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_6m_fund",
      "label": "近6月收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_2y_fund",
      "label": "近2年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_3y_fund",
      "label": "近3年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_5y_fund",
      "label": "近5年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_std_fund",
      "label": "成立以来收益率",
      "format": "percent"
    }
  ],
  "output_style": "summary"
}
```

---

### Q11 510300近2年ETF排第几

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510300 的近2年收益率为 41.26%，近2年同类排名为 5888/20618，近2年 ETF 排名为 509。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_yeild_2y_fund",
    "ths_yeild_rank_2y_fund_origin",
    "ths_yeild_rank_2y_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_2y_fund",
      "label": "近2年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_2y_fund_origin",
      "label": "近2年同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_2y_etf",
      "label": "近2年 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q12 510300今年在同类基金里排多少

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510300 的今年以来收益率为 6.12%，今年以来同类排名为 9150/24947，今年以来 ETF 排名为 800。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_yeild_ytd_fund",
    "ths_yeild_rank_ytd_fund_origin",
    "ths_yeild_rank_ytd_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_ytd_fund_origin",
      "label": "今年以来同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_ytd_etf",
      "label": "今年以来 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q13 510300近5年收益率是多少，排名如何

- 来源章节：二、收益率与排名
- v3 路由：`single / performance`
- 判定：PASS

**实际回答**

510300 的近5年收益率为 8.63%，近5年同类排名为 7795/11882，近5年 ETF 排名为 285。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_yeild_5y_fund",
    "ths_yeild_rank_5y_fund_origin",
    "ths_yeild_rank_5y_etf"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_yeild_5y_fund",
      "label": "近5年收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_rank_5y_fund_origin",
      "label": "近5年同类排名",
      "format": "plain"
    },
    {
      "field": "ths_yeild_rank_5y_etf",
      "label": "近5年 ETF 排名",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q14 510300的基金规模多大

- 来源章节：三、规模、净值、份额
- v3 路由：`single / fund_scale`
- 判定：PASS

**实际回答**

510300 的基金规模为 1777.76 亿元（2026-05-07）。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_fund_scale_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    }
  ],
  "output_style": "summary"
}
```

---

### Q15 510300总市值多少

- 来源章节：三、规模、净值、份额
- v3 路由：`single / fund_scale`
- 判定：PASS

**实际回答**

510300 的总市值为 1775.99 亿元。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_current_mv_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_current_mv_fund",
      "label": "总市值",
      "format": "amount"
    }
  ],
  "output_style": "summary"
}
```

---

### Q16 510300最新净值是多少

- 来源章节：三、规模、净值、份额
- v3 路由：`single / fund_scale`
- 判定：PASS

**实际回答**

510300 的单位净值为 4.917（2026-05-07）。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_unit_nv_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_unit_nv_fund",
      "label": "单位净值",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q17 510300的份额有多少

- 来源章节：三、规模、净值、份额
- v3 路由：`single / fund_scale`
- 判定：PASS

**实际回答**

510300 的基金份额为 3.616e+10（2026-05-07）。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_fund_shares_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_shares_fund",
      "label": "基金份额",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q18 510300的净值增长率是多少

- 来源章节：三、规模、净值、份额
- v3 路由：`single / fund_scale`
- 判定：PASS

**实际回答**

510300 的单位净值增长率为 0.48%（2026-05-07）。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_unit_nvg_rate_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_unit_nvg_rate_fund",
      "label": "单位净值增长率",
      "format": "percent"
    }
  ],
  "output_style": "summary"
}
```

---

### Q19 510300的基金经理是谁

- 来源章节：五、基金经理
- v3 路由：`single / manager`
- 判定：PASS

**实际回答**

510300 的基金经理(现任)为 柳军，基金管理人为 华泰柏瑞基金。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_fund_manager_current_fund",
    "ths_fund_supervisor_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_manager_current_fund",
      "label": "基金经理(现任)",
      "format": "plain"
    },
    {
      "field": "ths_fund_supervisor_fund",
      "label": "基金管理人",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q20 510300有没有分红记录

- 来源章节：六、分红
- v3 路由：`single / dividend`
- 判定：PASS

**实际回答**

510300 的累计分红总额为 263.86 亿元，累计分红次数为 14。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_accum_dividend_total_amt_fund",
    "ths_accum_dividend_times_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_accum_dividend_total_amt_fund",
      "label": "累计分红总额",
      "format": "amount"
    },
    {
      "field": "ths_accum_dividend_times_fund",
      "label": "累计分红次数",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q21 159919累计分红多少

- 来源章节：六、分红
- v3 路由：`single / dividend`
- 判定：PASS

**实际回答**

159919 的累计分红总额为 80.76 亿元，累计分红次数为 5。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "159919"
  },
  "projection": [
    "fundcode",
    "ths_accum_dividend_total_amt_fund",
    "ths_accum_dividend_times_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_accum_dividend_total_amt_fund",
      "label": "累计分红总额",
      "format": "amount"
    },
    {
      "field": "ths_accum_dividend_times_fund",
      "label": "累计分红次数",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q22 510300分过几次红

- 来源章节：六、分红
- v3 路由：`single / dividend`
- 判定：PASS

**实际回答**

510300 的累计分红总额为 263.86 亿元，累计分红次数为 14。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "510300"
  },
  "projection": [
    "fundcode",
    "ths_accum_dividend_total_amt_fund",
    "ths_accum_dividend_times_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_accum_dividend_total_amt_fund",
      "label": "累计分红总额",
      "format": "amount"
    },
    {
      "field": "ths_accum_dividend_times_fund",
      "label": "累计分红次数",
      "format": "plain"
    }
  ],
  "output_style": "summary"
}
```

---

### Q23 000001有这只ETF吗

- 来源章节：十二、边界/异常场景
- v3 路由：`single / basic_info`
- 判定：PASS

**实际回答**

未在 ETF 数据库中找到代码 000001 对应的 ETF。

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": "000001"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_name_of_tracking_index_fund",
    "ths_fund_scale_fund"
  ],
  "limit": 1,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    }
  ],
  "output_style": "summary"
}
```

---

### Q24 帮我查510300的实时行情

- 来源章节：十二、边界/异常场景
- v3 路由：`deny / None`
- 判定：PASS

**实际回答**

抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。

---

### Q25 abcdef是什么基金

- 来源章节：十二、边界/异常场景
- v3 路由：`single / basic_info`
- 判定：PASS

**实际回答**

未在问题中识别到 ETF 基金代码或名称，请补充后重试。

---

### Q26 510300的持仓行业是什么（季报年报都没有）

- 来源章节：十二、边界/异常场景
- v3 路由：`unsupported / None`
- 判定：PASS

**实际回答**

当前版本暂不支持该查询类型。

---

### Q27 给我推荐一只ETF

- 来源章节：十二、边界/异常场景
- v3 路由：`deny / None`
- 判定：PASS

**实际回答**

抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。

---

### Q28 今天A股大盘怎么样

- 来源章节：十二、边界/异常场景
- v3 路由：`deny / None`
- 判定：PASS

**实际回答**

抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。

---

### Q29 510300能买吗

- 来源章节：十二、边界/异常场景
- v3 路由：`deny / None`
- 判定：PASS

**实际回答**

抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。

---


## v3.1 问题

### Q1 成立以来收益最好的沪深300ETF是哪只

- 来源章节：二、收益率与排名
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 | 成立以来收益率 |
| --- | --- | --- | --- | --- |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% | 163.00% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% | 153.17% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% | 138.28% |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% | 129.44% |
| 159925 | 沪深300ETF南方 | 27.73 亿元（2026-05-07） | 0.15% | 129.42% |
| 510360 | 沪深300ETF广发 | 29.85 亿元（2026-05-07） | 0.50% | 86.74% |
| 515360 | 沪深300ETF方正富邦 | 2.60 亿元（2026-05-07） | 0.15% | 72.42% |
| 515350 | 沪深300ETF民生加银 | 0.83 亿元（2026-05-07） | 0.15% | 63.53% |
| 561930 | 沪深300ETF招商 | 1.92 亿元（2026-05-07） | 0.15% | 62.90% |
| 515130 | 沪深300ETF博时 | 1.14 亿元（2026-05-07） | 0.15% | 61.38% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_name_of_tracking_index_fund": "沪深300指数"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_name_of_tracking_index_fund",
    "ths_yeild_std_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_std_fund",
      "label": "成立以来收益率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_yeild_std_fund",
      -1
    ],
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q2 帮我找沪深300相关的ETF

- 来源章节：七、搜索ETF
- v3 路由：`search / search`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% |
| 512010 | 医药ETF | 172.28 亿元（2026-05-07） | 0.50% |
| 512070 | 证券保险ETF | 133.69 亿元（2026-05-07） | 0.50% |
| 515330 | 沪深300ETF天弘 | 80.72 亿元（2026-05-07） | 0.50% |
| 515300 | 300红利低波ETF嘉实 | 51.79 亿元（2026-05-07） | 0.50% |
| 515380 | 沪深300ETF泰康 | 36.83 亿元（2026-05-07） | 0.40% |
| 510350 | 沪深300ETF工银 | 35.59 亿元（2026-05-07） | 0.15% |
| 510360 | 沪深300ETF广发 | 29.85 亿元（2026-05-07） | 0.50% |
| 515660 | 沪深300ETF国联安 | 28.50 亿元（2026-05-07） | 0.30% |
| 159925 | 沪深300ETF南方 | 27.73 亿元（2026-05-07） | 0.15% |
| 159673 | 沪深300ETF鹏华 | 18.98 亿元（2026-05-07） | 0.15% |
| 510380 | 沪深300ETF国寿 | 18.02 亿元（2026-05-07） | 0.50% |
| 515390 | 沪深300ETF华安 | 10.70 亿元（2026-05-07） | 0.15% |
| 159300 | 沪深300ETF富国 | 10.50 亿元（2026-05-07） | 0.15% |
| 510320 | 沪深300ETF中金 | 7.66 亿元（2026-05-07） | 0.15% |
| 562310 | 沪深300成长ETF银华 | 6.66 亿元（2026-05-07） | 0.50% |
| 563900 | 300自由现金流ETF摩根 | 6.65 亿元（2026-05-07） | 0.50% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "__search_text__": {
      "$contains": "沪深300"
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 20,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q3 搜索中证500

- 来源章节：七、搜索ETF
- v3 路由：`search / search`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510500 | 中证500ETF | 598.28 亿元（2026-05-07） | 0.15% |
| 159922 | 中证500ETF嘉实 | 103.61 亿元（2026-05-07） | 0.15% |
| 512500 | 中证500ETF华夏 | 100.83 亿元（2026-05-07） | 0.15% |
| 510580 | 中证500ETF易方达 | 43.20 亿元（2026-05-07） | 0.15% |
| 510510 | 中证500ETF广发 | 25.10 亿元（2026-05-07） | 0.50% |
| 159820 | 中证500ETF天弘 | 20.30 亿元（2026-05-07） | 0.50% |
| 561550 | 中证500增强ETF华泰柏瑞 | 15.80 亿元（2026-05-07） | 0.70% |
| 510590 | 中证500ETF平安 | 13.90 亿元（2026-05-07） | 0.50% |
| 512510 | 中证500ETF华泰柏瑞 | 11.42 亿元（2026-05-07） | 0.15% |
| 560120 | 中证500现金流ETF华夏 | 10.62 亿元（2026-05-07） | 0.50% |
| 159968 | 中证500ETF博时 | 7.29 亿元（2026-05-07） | 0.15% |
| 512330 | 信息科技ETF南方 | 6.87 亿元（2026-05-07） | 0.50% |
| 515190 | 中证500ETF中银证券 | 5.99 亿元（2026-05-07） | 0.15% |
| 159337 | 中证500ETF东财 | 5.12 亿元（2026-05-07） | 0.50% |
| 510530 | 中证500ETF工银 | 4.81 亿元（2026-05-07） | 0.45% |
| 563750 | 中证500ETF汇添富 | 4.67 亿元（2026-05-07） | 0.15% |
| 560500 | 500质量成长ETF鹏扬 | 4.01 亿元（2026-05-07） | 0.45% |
| 159606 | 中证500成长ETF易方达 | 3.76 亿元（2026-05-07） | 0.50% |
| 159982 | 中证500ETF鹏华 | 3.39 亿元（2026-05-07） | 0.15% |
| 159610 | 中证500增强ETF景顺 | 2.01 亿元（2026-05-07） | 0.50% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "__search_text__": {
      "$contains": "中证500"
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 20,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q4 找一下创业板ETF

- 来源章节：七、搜索ETF
- v3 路由：`search / search`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 159915 | 创业板ETF | 463.70 亿元（2026-05-07） | 0.15% |
| 159949 | 创业板50ETF华安 | 238.45 亿元（2026-05-07） | 0.50% |
| 159952 | 创业板ETF广发 | 104.80 亿元（2026-05-07） | 0.15% |
| 159363 | 创业板人工智能ETF华宝 | 74.00 亿元（2026-05-07） | 0.50% |
| 159977 | 创业板ETF天弘 | 69.22 亿元（2026-05-07） | 0.15% |
| 159948 | 创业板ETF南方 | 46.79 亿元（2026-05-07） | 0.15% |
| 159682 | 创业板50ETF景顺 | 41.49 亿元（2026-05-07） | 0.15% |
| 159967 | 创业板成长ETF华夏 | 37.11 亿元（2026-05-07） | 0.50% |
| 159246 | 创业板人工智能ETF富国 | 35.77 亿元（2026-05-07） | 0.40% |
| 159382 | 创业板人工智能ETF南方 | 24.42 亿元（2026-05-07） | 0.50% |
| 159381 | 创业板人工智能ETF华夏 | 23.95 亿元（2026-05-07） | 0.15% |
| 159971 | 创业板ETF富国 | 22.03 亿元（2026-05-07） | 0.15% |
| 159387 | 创业板新能源ETF国泰 | 18.91 亿元（2026-05-07） | 0.50% |
| 159957 | 创业板ETF华夏 | 18.54 亿元（2026-05-07） | 0.15% |
| 159681 | 创业板50ETF鹏华 | 15.10 亿元（2026-05-07） | 0.15% |
| 159368 | 创业板新能源ETF华夏 | 10.94 亿元（2026-05-07） | 0.15% |
| 159908 | 创业板ETF博时 | 10.82 亿元（2026-05-07） | 0.15% |
| 159388 | 创业板人工智能ETF国泰 | 9.40 亿元（2026-05-07） | 0.50% |
| 159107 | 创业板软件ETF富国 | 5.65 亿元（2026-05-07） | 0.50% |
| 159205 | 创业板ETF东财 | 5.61 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "__search_text__": {
      "$contains": "创业板"
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 20,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q5 搜索MSCI中国A股

- 来源章节：七、搜索ETF
- v3 路由：`search / search`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 512090 | MSCIA股ETF易方达 | 6.12 亿元（2026-05-07） | 0.15% |
| 515160 | MSCI中国ETF招商 | 4.52 亿元（2026-05-07） | 0.50% |
| 512990 | MSCIA股ETF华夏 | 2.23 亿元（2026-05-07） | 0.50% |
| 512160 | MSCI中国A股ETF南方 | 2.00 亿元（2026-05-07） | 0.50% |
| 512380 | MSCI中国ETF银华 | 1.29 亿元（2026-05-07） | 0.50% |
| 512180 | MSCIA股ETF建信 | 0.90 亿元（2026-05-07） | 0.50% |
| 512520 | MSCI中国ETF华泰柏瑞 | 0.69 亿元（2026-05-07） | 0.15% |
| 515770 | MSCI中国A股ETF摩根 | 0.64 亿元（2026-05-07） | 0.15% |
| 512360 | MSCIA股ETF平安 | 0.58 亿元（2026-05-07） | 0.50% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "__search_text__": {
      "$contains": "MSCI中国A股"
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 20,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q6 有没有名字里带医药的ETF

- 来源章节：七、搜索ETF
- v3 路由：`search / search`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 512010 | 医药ETF | 172.28 亿元（2026-05-07） | 0.50% |
| 159892 | 恒生医药ETF华夏 | 58.92 亿元（2026-05-07） | 0.50% |
| 159938 | 医药卫生ETF | 47.82 亿元（2026-05-07） | 0.50% |
| 159859 | 生物医药ETF天弘 | 39.55 亿元（2026-05-07） | 0.50% |
| 512290 | 生物医药ETF国泰 | 37.58 亿元（2026-05-07） | 0.50% |
| 159929 | 医药ETF汇添富 | 23.62 亿元（2026-05-07） | 0.50% |
| 516820 | 医疗创新ETF平安 | 17.62 亿元（2026-05-07） | 0.50% |
| 513200 | 港股通医药ETF易方达 | 14.18 亿元（2026-05-07） | 0.15% |
| 159839 | 生物医药ETF汇添富 | 8.73 亿元（2026-05-07） | 0.50% |
| 513700 | 港股通医药ETF鹏华 | 6.75 亿元（2026-05-07） | 0.50% |
| 515950 | 医药50ETF富国 | 5.28 亿元（2026-05-07） | 0.50% |
| 512120 | 医药ETF华安 | 3.64 亿元（2026-05-07） | 0.50% |
| 588700 | 科创医药ETF嘉实 | 3.22 亿元（2026-05-07） | 0.50% |
| 588860 | 科创医药ETF工银 | 2.70 亿元（2026-05-07） | 0.45% |
| 588250 | 科创医药ETF鹏华 | 2.56 亿元（2026-05-07） | 0.50% |
| 515960 | 医药ETF嘉实 | 2.01 亿元（2026-05-07） | 0.50% |
| 159718 | 港股医药ETF平安 | 1.75 亿元（2026-05-07） | 0.50% |
| 159838 | 医药50ETF博时 | 1.62 亿元（2026-05-07） | 0.50% |
| 159776 | 港股医药ETF银华 | 1.10 亿元（2026-05-07） | 0.50% |
| 510660 | 医药ETF华夏 | 0.94 亿元（2026-05-07） | 0.50% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "__search_text__": {
      "$contains": "医药"
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 20,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q7 有没有ETF名字里带"红利"的

- 来源章节：七、搜索ETF
- v3 路由：`search / search`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 512890 | 红利低波ETF华泰柏瑞 | 305.79 亿元（2026-05-07） | 0.50% |
| 510880 | 红利ETF | 191.52 亿元（2026-05-07） | 0.50% |
| 515450 | 红利低波50ETF南方 | 175.21 亿元（2026-05-07） | 0.50% |
| 513630 | 港股低波红利ETF摩根 | 167.82 亿元（2026-05-07） | 0.50% |
| 515180 | 红利ETF易方达 | 144.81 亿元（2026-05-07） | 0.15% |
| 515080 | 中证红利ETF招商 | 94.57 亿元（2026-05-07） | 0.20% |
| 563020 | 红利低波ETF易方达 | 92.59 亿元（2026-05-07） | 0.15% |
| 159545 | 恒生红利低波ETF易方达 | 76.00 亿元（2026-05-07） | 0.15% |
| 159691 | 港股红利ETF工银 | 65.10 亿元（2026-05-07） | 0.45% |
| 513920 | 港股通央企红利ETF华安 | 60.69 亿元（2026-05-07） | 0.50% |
| 515100 | 红利低波100ETF景顺 | 60.26 亿元（2026-05-07） | 0.50% |
| 159549 | 红利低波ETF天弘 | 55.90 亿元（2026-05-07） | 0.50% |
| 159307 | 红利低波100ETF博时 | 55.90 亿元（2026-05-07） | 0.15% |
| 513690 | 港股红利ETF博时 | 52.91 亿元（2026-05-07） | 0.50% |
| 520990 | 港股央企红利ETF景顺 | 51.99 亿元（2026-05-07） | 0.50% |
| 515300 | 300红利低波ETF嘉实 | 51.79 亿元（2026-05-07） | 0.50% |
| 562060 | 标普A股红利ETF华宝 | 46.34 亿元（2026-05-07） | 0.50% |
| 513910 | 港股通央企红利ETF华夏 | 44.39 亿元（2026-05-07） | 0.50% |
| 513530 | 港股通红利ETF华泰柏瑞 | 36.77 亿元（2026-05-07） | 0.50% |
| 513950 | 恒生红利ETF富国 | 32.33 亿元（2026-05-07） | 0.50% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "__search_text__": {
      "$contains": "红利"
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 20,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q8 我想找跟踪科创50的ETF

- 来源章节：七、搜索ETF
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% |
| 588080 | 科创50ETF易方达 | 391.17 亿元（2026-05-07） | 0.15% |
| 588050 | 科创50ETF工银 | 99.12 亿元（2026-05-07） | 0.30% |
| 588060 | 科创50ETF广发 | 75.07 亿元（2026-05-07） | 0.50% |
| 588090 | 科创50ETF华泰柏瑞 | 45.14 亿元（2026-05-07） | 0.50% |
| 588460 | 科创50增强ETF鹏华 | 15.64 亿元（2026-05-07） | 1.00% |
| 588180 | 科创50ETF国联安 | 13.21 亿元（2026-05-07） | 0.30% |
| 588940 | 科创50ETF富国 | 5.53 亿元（2026-05-07） | 0.15% |
| 588150 | 科创50ETF南方 | 5.00 亿元（2026-05-07） | 0.15% |
| 589850 | 科创50ETF东财 | 4.75 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_name_of_tracking_index_fund": "上证科创板50成份指数"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_name_of_tracking_index_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q9 帮我筛选所有股票型ETF

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% |
| 159792 | 港股通互联网ETF富国 | 619.57 亿元（2026-05-07） | 0.15% |
| 510500 | 中证500ETF | 598.28 亿元（2026-05-07） | 0.15% |
| 512880 | 证券ETF国泰 | 554.41 亿元（2026-05-07） | 0.50% |
| 513180 | 恒生科技ETF华夏 | 547.62 亿元（2026-05-07） | 0.50% |
| 513130 | 恒生科技ETF华泰柏瑞 | 497.48 亿元（2026-05-07） | 0.20% |
| 510050 | 上证50ETF | 476.99 亿元（2026-05-07） | 0.15% |
| 588200 | 科创芯片ETF嘉实 | 466.26 亿元（2026-05-07） | 0.50% |
| 159915 | 创业板ETF | 463.70 亿元（2026-05-07） | 0.15% |
| 513050 | 中概互联网ETF | 410.43 亿元（2026-05-07） | 0.60% |
| 588080 | 科创50ETF易方达 | 391.17 亿元（2026-05-07） | 0.15% |
| 512000 | 券商ETF华宝 | 361.37 亿元（2026-05-07） | 0.50% |
| 513330 | 恒生互联网ETF华夏 | 349.13 亿元（2026-05-07） | 0.50% |
| 563360 | A500ETF华泰柏瑞 | 343.94 亿元（2026-05-07） | 0.15% |
| 159326 | 电网设备ETF华夏 | 342.57 亿元（2026-05-07） | 0.50% |
| 513010 | 恒生科技ETF易方达 | 330.23 亿元（2026-05-07） | 0.20% |
| 159941 | 纳指ETF广发 | 329.51 亿元（2026-05-07） | 0.80% |
| 159352 | A500ETF南方 | 322.13 亿元（2026-05-07） | 0.15% |
| 159570 | 港股通创新药ETF汇添富 | 307.85 亿元（2026-05-07） | 0.50% |
| 159636 | 港股通科技30ETF工银 | 307.15 亿元（2026-05-07） | 0.45% |
| 512890 | 红利低波ETF华泰柏瑞 | 305.79 亿元（2026-05-07） | 0.50% |
| 512400 | 有色金属ETF南方 | 296.23 亿元（2026-05-07） | 0.50% |
| 159870 | 化工ETF鹏华 | 280.16 亿元（2026-05-07） | 0.50% |
| 512170 | 医疗ETF华宝 | 273.95 亿元（2026-05-07） | 0.50% |
| 159338 | 中证A500ETF国泰 | 264.63 亿元（2026-05-07） | 0.15% |
| 159995 | 芯片ETF华夏 | 263.90 亿元（2026-05-07） | 0.50% |
| 513120 | 港股创新药ETF广发 | 258.99 亿元（2026-05-07） | 0.50% |
| 159361 | A500ETF易方达 | 253.17 亿元（2026-05-07） | 0.15% |
| 515880 | 通信ETF国泰 | 251.21 亿元（2026-05-07） | 0.50% |
| 159206 | 卫星ETF永赢 | 250.43 亿元（2026-05-07） | 0.50% |
| 513750 | 港股通非银ETF广发 | 250.31 亿元（2026-05-07） | 0.50% |
| 159819 | 人工智能ETF易方达 | 243.87 亿元（2026-05-07） | 0.15% |
| 159949 | 创业板50ETF华安 | 238.45 亿元（2026-05-07） | 0.50% |
| 513500 | 标普500ETF | 237.09 亿元（2026-05-07） | 0.60% |
| 510180 | 上证180ETF | 230.44 亿元（2026-05-07） | 0.15% |
| 159516 | 半导体设备ETF国泰 | 225.83 亿元（2026-05-07） | 0.50% |
| 512050 | A500ETF华夏 | 222.55 亿元（2026-05-07） | 0.15% |
| 513090 | 香港证券ETF易方达 | 222.27 亿元（2026-05-07） | 0.15% |
| 562500 | 机器人ETF华夏 | 216.13 亿元（2026-05-07） | 0.50% |
| 159201 | 自由现金流ETF华夏 | 209.17 亿元（2026-05-07） | 0.15% |
| 159740 | 恒生科技ETF大成 | 203.45 亿元（2026-05-07） | 0.50% |
| 512480 | 半导体ETF国联安 | 202.05 亿元（2026-05-07） | 0.50% |
| 513980 | 港股科技ETF景顺 | 196.26 亿元（2026-05-07） | 0.50% |
| 510880 | 红利ETF | 191.52 亿元（2026-05-07） | 0.50% |
| 513100 | 纳指ETF国泰 | 185.31 亿元（2026-05-07） | 0.60% |
| 159928 | 消费ETF汇添富 | 182.68 亿元（2026-05-07） | 0.50% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_fund_invest_type_fund": "股票型"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_fund_invest_type_fund"
  ],
  "limit": 50,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q10 找上交所规模前10的ETF

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% |
| 518880 | 黄金ETF华安 | 1163.19 亿元（2026-05-07） | 0.50% |
| 511360 | 短融ETF海富通 | 968.65 亿元（2026-05-07） | 0.15% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% |
| 511880 | 银华日利ETF | 799.95 亿元（2026-05-07） | 0.30% |
| 511990 | 华宝添益ETF | 706.63 亿元（2026-05-07） | 0.35% |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% |
| 511380 | 可转债ETF博时 | 611.42 亿元（2026-05-07） | 0.15% |
| 510500 | 中证500ETF | 598.28 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_fund_listed_exchange_fund": "上交所"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_fund_listed_exchange_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q11 哪些ETF管理费率最低

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% |
| 511360 | 短融ETF海富通 | 968.65 亿元（2026-05-07） | 0.15% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% |
| 159792 | 港股通互联网ETF富国 | 619.57 亿元（2026-05-07） | 0.15% |
| 511380 | 可转债ETF博时 | 611.42 亿元（2026-05-07） | 0.15% |
| 510500 | 中证500ETF | 598.28 亿元（2026-05-07） | 0.15% |
| 511220 | 城投债ETF海富通 | 493.64 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {},
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_manage_fee_rate_fund",
      1
    ],
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q12 筛选跟踪沪深300指数的ETF，按收益率排序

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 | 近1年收益率 |
| --- | --- | --- | --- | --- |
| 515360 | 沪深300ETF方正富邦 | 2.60 亿元（2026-05-07） | 0.15% | 34.53% |
| 159393 | 沪深300ETF万家 | 2.58 亿元（2026-05-07） | 0.15% | 34.16% |
| 561930 | 沪深300ETF招商 | 1.92 亿元（2026-05-07） | 0.15% | 33.75% |
| 159300 | 沪深300ETF富国 | 10.50 亿元（2026-05-07） | 0.15% | 32.89% |
| 515130 | 沪深300ETF博时 | 1.14 亿元（2026-05-07） | 0.15% | 32.57% |
| 510350 | 沪深300ETF工银 | 35.59 亿元（2026-05-07） | 0.15% | 32.08% |
| 510390 | 沪深300ETF平安 | 6.04 亿元（2026-05-07） | 0.50% | 32.02% |
| 510380 | 沪深300ETF国寿 | 18.02 亿元（2026-05-07） | 0.50% | 31.61% |
| 159925 | 沪深300ETF南方 | 27.73 亿元（2026-05-07） | 0.15% | 31.60% |
| 159330 | 沪深300ETF东财 | 4.62 亿元（2026-05-07） | 0.50% | 31.49% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_name_of_tracking_index_fund": "沪深300指数"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_name_of_tracking_index_fund",
    "ths_yeild_1y_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_yeild_1y_fund",
      -1
    ],
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q13 找规模大于10亿的ETF

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% |
| 518880 | 黄金ETF华安 | 1163.19 亿元（2026-05-07） | 0.50% |
| 511360 | 短融ETF海富通 | 968.65 亿元（2026-05-07） | 0.15% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% |
| 511880 | 银华日利ETF | 799.95 亿元（2026-05-07） | 0.30% |
| 511990 | 华宝添益ETF | 706.63 亿元（2026-05-07） | 0.35% |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% |
| 159792 | 港股通互联网ETF富国 | 619.57 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_fund_scale_fund": {
      "$gt": 1000000000
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q14 筛选深交所的债券型ETF

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 159600 | 科创债ETF嘉实 | 219.64 亿元（2026-05-07） | 0.15% |
| 159112 | 科创债ETF银华 | 205.11 亿元（2026-05-07） | 0.15% |
| 159200 | 科创债ETF富国 | 143.23 亿元（2026-05-07） | 0.15% |
| 159397 | 信用债ETF广发 | 121.73 亿元（2026-05-07） | 0.15% |
| 159700 | 科创债ETF南方 | 115.79 亿元（2026-05-07） | 0.15% |
| 159395 | 信用债ETF大成 | 110.46 亿元（2026-05-07） | 0.15% |
| 159116 | 科创债ETF工银 | 103.13 亿元（2026-05-07） | 0.15% |
| 159816 | 0-4年地方债ETF鹏华 | 102.11 亿元（2026-05-07） | 0.15% |
| 159111 | 科创债ETF天弘 | 101.99 亿元（2026-05-07） | 0.15% |
| 159398 | 信用债ETF天弘 | 98.87 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_fund_listed_exchange_fund": "深交所",
    "ths_fund_invest_type_fund": "债券型"
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_fund_listed_exchange_fund",
    "ths_fund_invest_type_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q15 今年以来收益排名前10的ETF

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 | 今年以来收益率 |
| --- | --- | --- | --- | --- |
| 513310 | 中韩半导体ETF华泰柏瑞 | 97.71 亿元（2026-05-07） | 0.80% | 75.49% |
| 588780 | 科创芯片设计ETF国联安 | 10.16 亿元（2026-05-07） | 0.50% | 43.99% |
| 589210 | 科创芯片设计ETF广发 | 0.73 亿元（2026-05-07） | 0.50% | 43.66% |
| 588810 | 科创芯片ETF富国 | 6.53 亿元（2026-05-07） | 0.50% | 43.26% |
| 588990 | 科创芯片ETF博时 | 5.88 亿元（2026-05-07） | 0.50% | 42.61% |
| 588890 | 科创芯片ETF南方 | 24.31 亿元（2026-05-07） | 0.50% | 42.60% |
| 588200 | 科创芯片ETF嘉实 | 466.26 亿元（2026-05-07） | 0.50% | 42.32% |
| 589100 | 科创芯片ETF国泰 | 6.53 亿元（2026-05-07） | 0.50% | 42.30% |
| 588290 | 科创芯片ETF华安 | 43.34 亿元（2026-05-07） | 0.15% | 42.17% |
| 588750 | 科创芯片ETF汇添富 | 55.57 亿元（2026-05-07） | 0.50% | 42.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {},
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_yeild_ytd_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_yeild_ytd_fund",
      -1
    ],
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q16 管理费率低于0.2%的ETF有哪些

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 |
| --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% |
| 511360 | 短融ETF海富通 | 968.65 亿元（2026-05-07） | 0.15% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% |
| 159792 | 港股通互联网ETF富国 | 619.57 亿元（2026-05-07） | 0.15% |
| 511380 | 可转债ETF博时 | 611.42 亿元（2026-05-07） | 0.15% |
| 510500 | 中证500ETF | 598.28 亿元（2026-05-07） | 0.15% |
| 511220 | 城投债ETF海富通 | 493.64 亿元（2026-05-07） | 0.15% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_manage_fee_rate_fund": {
      "$lt": 0.2
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_manage_fee_rate_fund",
      1
    ],
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q17 近1年收益率超过20%的ETF

- 来源章节：八、条件筛选
- v3 路由：`filter / filter`
- 判定：PASS

**实际回答**

| 基金代码 | 基金简称 | 基金规模 | 管理费率 | 近1年收益率 |
| --- | --- | --- | --- | --- |
| 510300 | 沪深300ETF | 1777.76 亿元（2026-05-07） | 0.15% | 31.27% |
| 510310 | 沪深300ETF易方达 | 1367.01 亿元（2026-05-07） | 0.15% | 31.43% |
| 518880 | 黄金ETF华安 | 1163.19 亿元（2026-05-07） | 0.50% | 29.28% |
| 510330 | 沪深300ETF华夏 | 915.48 亿元（2026-05-07） | 0.15% | 31.28% |
| 159919 | 沪深300ETF | 886.02 亿元（2026-05-07） | 0.15% | 31.18% |
| 588000 | 科创50ETF华夏 | 704.78 亿元（2026-05-07） | 0.15% | 63.62% |
| 511380 | 可转债ETF博时 | 611.42 亿元（2026-05-07） | 0.15% | 21.92% |
| 510500 | 中证500ETF | 598.28 亿元（2026-05-07） | 0.15% | 53.89% |
| 159937 | 黄金ETF博时 | 493.47 亿元（2026-05-07） | 0.50% | 29.20% |
| 588200 | 科创芯片ETF嘉实 | 466.26 亿元（2026-05-07） | 0.50% | 110.07% |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "ths_yeild_1y_fund": {
      "$gt": 20
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_yeild_1y_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    }
  ],
  "output_style": "list",
  "sort": [
    [
      "ths_fund_scale_fund",
      -1
    ],
    [
      "fundcode",
      1
    ]
  ]
}
```

---

### Q18 对比510300、510500和159919

- 来源章节：九、多只对比
- v3 路由：`compare / compare`
- 判定：PASS

**实际回答**

| 指标 | 510300 | 510500 | 159919 |
| --- | --- | --- | --- |
| 基金简称 | 沪深300ETF | 中证500ETF | 沪深300ETF |
| 基金规模 | 1777.76 亿元（2026-05-07） | 598.28 亿元（2026-05-07） | 886.02 亿元（2026-05-07） |
| 管理费率 | 0.15% | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% | 0.05% |
| 今年以来收益率 | 6.12% | 16.52% | 6.10% |
| 近1年收益率 | 31.27% | 53.89% | 31.18% |
| 跟踪指数名称 | 沪深300指数 | 中证小盘500指数 | 沪深300指数 |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": {
      "$in": [
        "510300",
        "510500",
        "159919"
      ]
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_1y_fund",
    "ths_name_of_tracking_index_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_mandate_fee_rate_fund",
      "label": "托管费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    }
  ],
  "output_style": "compare"
}
```

---

### Q19 对比所有跟踪沪深300的前5只ETF，看收益和费率

- 来源章节：九、多只对比
- v3 路由：`composite / filter_to_compare`
- 判定：PASS

**实际回答**

| 指标 | 515360 | 159393 | 561930 | 159300 | 515130 |
| --- | --- | --- | --- | --- | --- |
| 基金简称 | 沪深300ETF方正富邦 | 沪深300ETF万家 | 沪深300ETF招商 | 沪深300ETF富国 | 沪深300ETF博时 |
| 基金规模 | 2.60 亿元（2026-05-07） | 2.58 亿元（2026-05-07） | 1.92 亿元（2026-05-07） | 10.50 亿元（2026-05-07） | 1.14 亿元（2026-05-07） |
| 管理费率 | 0.15% | 0.15% | 0.15% | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% | 0.05% | 0.05% | 0.05% |
| 今年以来收益率 | 7.13% | 7.52% | 7.11% | 6.88% | 6.70% |
| 近1年收益率 | 34.53% | 34.16% | 33.75% | 32.89% | 32.57% |
| 跟踪指数名称 | 沪深300指数 | 沪深300指数 | 沪深300指数 | 沪深300指数 | 沪深300指数 |

**查询计划**

```json
{
  "steps": [
    {
      "collection": "tb_ths_etf_base",
      "filter": {
        "ths_name_of_tracking_index_fund": "沪深300指数"
      },
      "projection": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_name_of_tracking_index_fund",
        "ths_yeild_1y_fund"
      ],
      "limit": 5,
      "answer_fields": [
        {
          "field": "fundcode",
          "label": "基金代码",
          "format": "plain"
        },
        {
          "field": "ths_fund_extended_inner_short_name_fund",
          "label": "基金简称",
          "format": "plain"
        },
        {
          "field": "ths_fund_scale_fund",
          "label": "基金规模",
          "format": "amount"
        },
        {
          "field": "ths_manage_fee_rate_fund",
          "label": "管理费率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_1y_fund",
          "label": "近1年收益率",
          "format": "percent"
        }
      ],
      "output_style": "list",
      "sort": [
        [
          "ths_yeild_1y_fund",
          -1
        ],
        [
          "ths_fund_scale_fund",
          -1
        ],
        [
          "fundcode",
          1
        ]
      ]
    },
    {
      "collection": "tb_ths_etf_base",
      "filter": {
        "fundcode": {
          "$in": [
            "515360",
            "159393",
            "561930",
            "159300",
            "515130"
          ]
        }
      },
      "projection": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_mandate_fee_rate_fund",
        "ths_yeild_ytd_fund",
        "ths_yeild_1y_fund",
        "ths_name_of_tracking_index_fund"
      ],
      "limit": 10,
      "answer_fields": [
        {
          "field": "fundcode",
          "label": "基金代码",
          "format": "plain"
        },
        {
          "field": "ths_fund_extended_inner_short_name_fund",
          "label": "基金简称",
          "format": "plain"
        },
        {
          "field": "ths_fund_scale_fund",
          "label": "基金规模",
          "format": "amount"
        },
        {
          "field": "ths_manage_fee_rate_fund",
          "label": "管理费率",
          "format": "percent"
        },
        {
          "field": "ths_mandate_fee_rate_fund",
          "label": "托管费率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_ytd_fund",
          "label": "今年以来收益率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_1y_fund",
          "label": "近1年收益率",
          "format": "percent"
        },
        {
          "field": "ths_name_of_tracking_index_fund",
          "label": "跟踪指数名称",
          "format": "plain"
        }
      ],
      "output_style": "compare"
    }
  ]
}
```

---

### Q20 510300和510500比一下规模和费率

- 来源章节：九、多只对比
- v3 路由：`compare / compare`
- 判定：PASS

**实际回答**

| 指标 | 510300 | 510500 |
| --- | --- | --- |
| 基金简称 | 沪深300ETF | 中证500ETF |
| 基金规模 | 1777.76 亿元（2026-05-07） | 598.28 亿元（2026-05-07） |
| 管理费率 | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% |
| 今年以来收益率 | 6.12% | 16.52% |
| 近1年收益率 | 31.27% | 53.89% |
| 跟踪指数名称 | 沪深300指数 | 中证小盘500指数 |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": {
      "$in": [
        "510300",
        "510500"
      ]
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_1y_fund",
    "ths_name_of_tracking_index_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_mandate_fee_rate_fund",
      "label": "托管费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    }
  ],
  "output_style": "compare"
}
```

---

### Q21 对比一下510300和159919的收益率

- 来源章节：九、多只对比
- v3 路由：`compare / compare`
- 判定：PASS

**实际回答**

| 指标 | 510300 | 159919 |
| --- | --- | --- |
| 基金简称 | 沪深300ETF | 沪深300ETF |
| 基金规模 | 1777.76 亿元（2026-05-07） | 886.02 亿元（2026-05-07） |
| 管理费率 | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% |
| 今年以来收益率 | 6.12% | 6.10% |
| 近1年收益率 | 31.27% | 31.18% |
| 跟踪指数名称 | 沪深300指数 | 沪深300指数 |

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": {
      "$in": [
        "510300",
        "159919"
      ]
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_1y_fund",
    "ths_name_of_tracking_index_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_mandate_fee_rate_fund",
      "label": "托管费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    }
  ],
  "output_style": "compare"
}
```

---

### Q22 股票型ETF里今年收益最高的5只是哪些？对比一下

- 来源章节：十、复合意图
- v3 路由：`composite / filter_to_compare`
- 判定：PASS

**实际回答**

| 指标 | 513310 | 588780 | 589210 | 588810 | 588990 |
| --- | --- | --- | --- | --- | --- |
| 基金简称 | 中韩半导体ETF华泰柏瑞 | 科创芯片设计ETF国联安 | 科创芯片设计ETF广发 | 科创芯片ETF富国 | 科创芯片ETF博时 |
| 基金规模 | 97.71 亿元（2026-05-07） | 10.16 亿元（2026-05-07） | 0.73 亿元（2026-05-07） | 6.53 亿元（2026-05-07） | 5.88 亿元（2026-05-07） |
| 管理费率 | 0.80% | 0.50% | 0.50% | 0.50% | 0.50% |
| 托管费率 | 0.15% | 0.10% | 0.10% | 0.10% | 0.10% |
| 今年以来收益率 | 75.49% | 43.99% | 43.66% | 43.26% | 42.61% |
| 近1年收益率 | 192.71% | 99.45% | 暂无数据 | 111.94% | 109.11% |
| 跟踪指数名称 | 中证韩交所中韩半导体指数 | 上证科创板芯片设计主题指数 | 上证科创板芯片设计主题指数 | 上证科创板芯片指数 | 上证科创板芯片指数 |

**查询计划**

```json
{
  "steps": [
    {
      "collection": "tb_ths_etf_base",
      "filter": {
        "ths_fund_invest_type_fund": "股票型"
      },
      "projection": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_fund_invest_type_fund",
        "ths_yeild_ytd_fund"
      ],
      "limit": 5,
      "answer_fields": [
        {
          "field": "fundcode",
          "label": "基金代码",
          "format": "plain"
        },
        {
          "field": "ths_fund_extended_inner_short_name_fund",
          "label": "基金简称",
          "format": "plain"
        },
        {
          "field": "ths_fund_scale_fund",
          "label": "基金规模",
          "format": "amount"
        },
        {
          "field": "ths_manage_fee_rate_fund",
          "label": "管理费率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_ytd_fund",
          "label": "今年以来收益率",
          "format": "percent"
        }
      ],
      "output_style": "list",
      "sort": [
        [
          "ths_yeild_ytd_fund",
          -1
        ],
        [
          "ths_fund_scale_fund",
          -1
        ],
        [
          "fundcode",
          1
        ]
      ]
    },
    {
      "collection": "tb_ths_etf_base",
      "filter": {
        "fundcode": {
          "$in": [
            "513310",
            "588780",
            "589210",
            "588810",
            "588990"
          ]
        }
      },
      "projection": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_mandate_fee_rate_fund",
        "ths_yeild_ytd_fund",
        "ths_yeild_1y_fund",
        "ths_name_of_tracking_index_fund"
      ],
      "limit": 10,
      "answer_fields": [
        {
          "field": "fundcode",
          "label": "基金代码",
          "format": "plain"
        },
        {
          "field": "ths_fund_extended_inner_short_name_fund",
          "label": "基金简称",
          "format": "plain"
        },
        {
          "field": "ths_fund_scale_fund",
          "label": "基金规模",
          "format": "amount"
        },
        {
          "field": "ths_manage_fee_rate_fund",
          "label": "管理费率",
          "format": "percent"
        },
        {
          "field": "ths_mandate_fee_rate_fund",
          "label": "托管费率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_ytd_fund",
          "label": "今年以来收益率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_1y_fund",
          "label": "近1年收益率",
          "format": "percent"
        },
        {
          "field": "ths_name_of_tracking_index_fund",
          "label": "跟踪指数名称",
          "format": "plain"
        }
      ],
      "output_style": "compare"
    }
  ]
}
```

---

### Q23 上交所的ETF里，找管理费最低的3只，对比它们的今年收益

- 来源章节：十、复合意图
- v3 路由：`composite / filter_to_compare`
- 判定：PASS

**实际回答**

| 指标 | 510300 | 510310 | 511360 |
| --- | --- | --- | --- |
| 基金简称 | 沪深300ETF | 沪深300ETF易方达 | 短融ETF海富通 |
| 基金规模 | 1777.76 亿元（2026-05-07） | 1367.01 亿元（2026-05-07） | 968.65 亿元（2026-05-07） |
| 管理费率 | 0.15% | 0.15% | 0.15% |
| 托管费率 | 0.05% | 0.05% | 0.05% |
| 今年以来收益率 | 6.12% | 6.22% | 0.53% |
| 近1年收益率 | 31.27% | 31.43% | 1.54% |
| 跟踪指数名称 | 沪深300指数 | 沪深300指数 | 中证短融指数(净价) |

**查询计划**

```json
{
  "steps": [
    {
      "collection": "tb_ths_etf_base",
      "filter": {
        "ths_fund_listed_exchange_fund": "上交所"
      },
      "projection": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_fund_listed_exchange_fund"
      ],
      "limit": 3,
      "answer_fields": [
        {
          "field": "fundcode",
          "label": "基金代码",
          "format": "plain"
        },
        {
          "field": "ths_fund_extended_inner_short_name_fund",
          "label": "基金简称",
          "format": "plain"
        },
        {
          "field": "ths_fund_scale_fund",
          "label": "基金规模",
          "format": "amount"
        },
        {
          "field": "ths_manage_fee_rate_fund",
          "label": "管理费率",
          "format": "percent"
        }
      ],
      "output_style": "list",
      "sort": [
        [
          "ths_manage_fee_rate_fund",
          1
        ],
        [
          "ths_fund_scale_fund",
          -1
        ],
        [
          "fundcode",
          1
        ]
      ]
    },
    {
      "collection": "tb_ths_etf_base",
      "filter": {
        "fundcode": {
          "$in": [
            "510300",
            "510310",
            "511360"
          ]
        }
      },
      "projection": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_fund_scale_fund",
        "ths_manage_fee_rate_fund",
        "ths_mandate_fee_rate_fund",
        "ths_yeild_ytd_fund",
        "ths_yeild_1y_fund",
        "ths_name_of_tracking_index_fund"
      ],
      "limit": 10,
      "answer_fields": [
        {
          "field": "fundcode",
          "label": "基金代码",
          "format": "plain"
        },
        {
          "field": "ths_fund_extended_inner_short_name_fund",
          "label": "基金简称",
          "format": "plain"
        },
        {
          "field": "ths_fund_scale_fund",
          "label": "基金规模",
          "format": "amount"
        },
        {
          "field": "ths_manage_fee_rate_fund",
          "label": "管理费率",
          "format": "percent"
        },
        {
          "field": "ths_mandate_fee_rate_fund",
          "label": "托管费率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_ytd_fund",
          "label": "今年以来收益率",
          "format": "percent"
        },
        {
          "field": "ths_yeild_1y_fund",
          "label": "近1年收益率",
          "format": "percent"
        },
        {
          "field": "ths_name_of_tracking_index_fund",
          "label": "跟踪指数名称",
          "format": "plain"
        }
      ],
      "output_style": "compare"
    }
  ]
}
```

---

### Q24 对比510300和000000

- 来源章节：十二、边界/异常场景
- v3 路由：`compare / compare`
- 判定：PASS

**实际回答**

| 指标 | 510300 |
| --- | --- |
| 基金简称 | 沪深300ETF |
| 基金规模 | 1777.76 亿元（2026-05-07） |
| 管理费率 | 0.15% |
| 托管费率 | 0.05% |
| 今年以来收益率 | 6.12% |
| 近1年收益率 | 31.27% |
| 跟踪指数名称 | 沪深300指数 |

缺失代码：000000

**查询计划**

```json
{
  "collection": "tb_ths_etf_base",
  "filter": {
    "fundcode": {
      "$in": [
        "510300",
        "000000"
      ]
    }
  },
  "projection": [
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_1y_fund",
    "ths_name_of_tracking_index_fund"
  ],
  "limit": 10,
  "answer_fields": [
    {
      "field": "fundcode",
      "label": "基金代码",
      "format": "plain"
    },
    {
      "field": "ths_fund_extended_inner_short_name_fund",
      "label": "基金简称",
      "format": "plain"
    },
    {
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "format": "amount"
    },
    {
      "field": "ths_manage_fee_rate_fund",
      "label": "管理费率",
      "format": "percent"
    },
    {
      "field": "ths_mandate_fee_rate_fund",
      "label": "托管费率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_ytd_fund",
      "label": "今年以来收益率",
      "format": "percent"
    },
    {
      "field": "ths_yeild_1y_fund",
      "label": "近1年收益率",
      "format": "percent"
    },
    {
      "field": "ths_name_of_tracking_index_fund",
      "label": "跟踪指数名称",
      "format": "plain"
    }
  ],
  "output_style": "compare"
}
```

---


## 汇总

- v3.0 抽取题数：29
- v3.1 抽取题数：24
- 总题数：53
- PASS：53
- FAIL：0

本文件可直接作为 v3.1 demo 展示材料：先展示 v3.0 单只基金能力，再展示 v3.1 搜索、筛选、排序和对比能力。
