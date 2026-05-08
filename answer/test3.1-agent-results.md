# v3.1 Agent E2E Results

测试时间：2026-05-08

- PASS：16
- FAIL：0
- LLM AST generated：13
- LLM AST fallback：0
- LLM AST skipped：3

| 问句 | 路由 | 判定 | 原因 |
| --- | --- | --- | --- |
| 帮我找沪深300相关的ETF | `search / search` | PASS |  |
| 找规模大于10亿的ETF | `filter / filter` | PASS |  |
| 哪些ETF管理费率最低 | `filter / filter` | PASS |  |
| 对比510300、510500和159919 | `compare / compare` | PASS |  |
| 股票型ETF里今年收益最高的5只是哪些？对比一下 | `composite / filter_to_compare` | PASS |  |
| 低成本的沪深300产品都有哪些 | `filter / filter` | PASS |  |
| 便宜一点的沪深300产品 | `filter / filter` | PASS |  |
| 科创板50相关产品 | `search / search` | PASS |  |
| 偏债的场内基金有哪些 | `filter / filter` | PASS |  |
| 510300 510500 159919放一起看看 | `compare / compare` | PASS |  |
| 512880和510300谁费用更省 | `compare / compare` | PASS |  |
| 沪深300产品里回报靠前的 | `filter / filter` | PASS |  |
| 规模不小于100亿的产品 | `filter / filter` | PASS |  |
| 510300近半年和同类比怎么样 | `unsupported / None` | PASS |  |
| 沪深300里面哪只更值得买 | `deny / None` | PASS |  |
| 2024年成立的ETF有哪些 | `unsupported / None` | PASS |  |
