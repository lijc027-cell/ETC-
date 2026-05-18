# v3.5 Realtime Audit

- total: 29
- passed: 29
- failed: 0

| ID | Status | Question | Actual |
| --- | --- | --- | --- |
| 基础行情.1 | PASS | 510050现在什么价 | ExecutableQuery |
| 基础行情.2 | PASS | 科创50ETF报多少 | UnsupportedQuery(fund_identity_ambiguous) |
| 涨跌.1 | PASS | 510050涨了吗 | ExecutableQuery |
| 涨跌.2 | PASS | 科创50ETF跌了多少 | UnsupportedQuery(fund_identity_ambiguous) |
| 成交.1 | PASS | 510050成交额多少 | ExecutableQuery |
| 盘口.1 | PASS | 510050盘口 | ExecutableQuery |
| 盘口.2 | PASS | 科创50ETF买一多少 | UnsupportedQuery(fund_identity_ambiguous) |
| 折溢价.1 | PASS | 510050溢价多少 | ExecutableQuery |
| 折溢价.2 | PASS | 科创50ETF是折价还是溢价 | UnsupportedQuery(fund_identity_ambiguous) |
| 内外盘.1 | PASS | 510050内外盘 | ExecutableQuery |
| 内外盘.2 | PASS | 科创50ETF外盘多少 | UnsupportedQuery(fund_identity_ambiguous) |
| 振幅.1 | PASS | 510050振幅多大 | ExecutableQuery |
| 对比.1 | PASS | 对比510050和510300 | ClarificationRequired(capability_ambiguous) |
| 复合意图.1 | PASS | 510050涨了没，成交额多少 | ExecutableQuery |
| 复合意图.2 | PASS | 科创50ETF怎么样，折价了吗 | UnsupportedQuery(fund_identity_ambiguous) |
| 复合意图.3 | PASS | 159915价格多少，买一卖一挂了多少 | ExecutableQuery |
| 复合意图.4 | PASS | 对比510050和510300的涨跌幅和溢价 | ExecutableQuery |
| 复合意图.5 | PASS | 这只ETF盘口什么情况，内外盘怎么样 | UnsupportedQuery(fund_identity_required) |
| 复合意图.6 | PASS | 510050价格、涨跌幅、成交额、溢价率 | ExecutableQuery |
| 复合意图.7 | PASS | 510300现在行情，有没有折价，外盘强还是内盘强 | ExecutableQuery |
| 无法回答的问题.1 | PASS | 510050持仓哪些股票 | ExecutableQuery |
| 无法回答的问题.2 | PASS | 510300基金经理是谁 | ExecutableQuery |
| 无法回答的问题.3 | PASS | 科创50ETF跟踪什么指数 | UnsupportedQuery(fund_identity_ambiguous) |
| 无法回答的问题.4 | PASS | 这只ETF规模多大 | UnsupportedQuery(fund_identity_required) |
| 无法回答的问题.5 | PASS | 510050费率多少 | ExecutableQuery |
| 无法回答的问题.6 | PASS | 贵州茅台现在什么价 | UnsupportedQuery(unsupported_domain) |
| 无法回答的问题.7 | PASS | 上证指数多少点 | UnsupportedQuery(unsupported_domain) |
| 无法回答的问题.8 | PASS | 510050五档盘口 | UnsupportedQuery(field_not_supported) |
| 无法回答的问题.9 | PASS | 这只ETF历史走势 | UnsupportedQuery(fund_identity_required) |
