# v3.1 Reference Audit

测试时间：2026-05-08

- PASS：11
- FAIL：0
- REVIEW：1

| 问句 | 模型路由 | 模型数量 | 参考数量 | 判定 | 原因 |
| --- | --- | --- | --- | --- | --- |
| 510300是什么 | `single / basic_info` | 1 | 1 | PASS |  |
| 工银沪深300ETF的费率和基金经理是什么 | `single / fee_and_manager` | 1 | 1 | PASS |  |
| 510300今年的收益率是多少 | `single / performance` | 1 | 1 | PASS |  |
| 近1年收益率超过20%的ETF | `filter / filter` | 10 | 10 | PASS |  |
| 找规模大于10亿的ETF | `filter / filter` | 10 | 10 | PASS |  |
| 哪些ETF管理费率最低 | `filter / filter` | 10 | 10 | PASS |  |
| 我想找跟踪科创50的ETF | `filter / filter` | 10 | 10 | PASS |  |
| 帮我找沪深300相关的ETF | `search / search` | 20 | 20 | REVIEW | search 子串匹配可能有合理差异 |
| 对比510300、510500和159919 | `compare / compare` | 3 | 3 | PASS |  |
| 对比510300和000000 | `compare / compare` | 1 | 1 | PASS |  |
| 股票型ETF里今年收益最高的5只是哪些？对比一下 | `composite / filter_to_compare` | 5 | 5 | PASS |  |
| 帮我查510300的实时行情 | `deny / None` | 0 | 0 | PASS |  |
