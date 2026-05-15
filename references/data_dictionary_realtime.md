# ETF实时指标接口指标_递交旭哥

## ETF实时指标接入

| 接口字段顺序 | 字段名(index) | ifind中文名称(title) | ifind英文名称(titleEn) | 缩写(abbreviation) | 分类中文 | 应用场景 | 筛选理由 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | tradeDate | 交易日期 | Trading Date | jyrq | 基本行情 | 数据时间戳/去重 | 判断行情日期，避免跨日或缓存数据进入策略。 |
| 2 | tradeTime | 交易时间 | Trading Hours | jysj | 基本行情 | 数据时间戳/延迟判断 | 判断分钟/实时行情更新时间，用于延迟监控和增量刷新。 |
| 3 | preClose | 前收盘价 | Previous Closing Price | qspj | 基本行情 | 涨跌幅基准 | 计算日内收益、涨跌幅校验和风控阈值。 |
| 4 | open | 开盘价 | Open | kpj | 基本行情 | 日内价格区间 | 用于判断开盘后表现和日内趋势。 |
| 5 | high | 最高价 | High | zgj | 基本行情 | 日内价格区间 | 用于判断日内强弱、突破和回落。 |
| 6 | low | 最低价 | Low | zdj | 基本行情 | 日内价格区间 | 用于判断日内弱势、回撤和波动。 |
| 7 | latest | 最新价 | Latest Price | zsj | 基本行情 | 实时价格 | ETF筛选、预警、成交参考的核心价格。 |
| 8 | change | 涨跌 | Price Change | zd | 基本行情 | 涨跌监控 | 接口直接返回涨跌额，便于实时展示和预警。 |
| 9 | changeRatio | 涨跌幅 | Change% | zdf | 基本行情 | 涨跌幅监控 | 最常用的实时涨跌筛选条件。 |
| 10 | swing | 振幅 | Amplitude | zf | 基本行情 | 波动筛选 | 可直接用于筛选日内振幅异常的ETF。 |
| 11 | amount | 成交额 | Turnover | cje | 基本行情 | 流动性/活跃度 | 成交额比成交量更适合跨ETF比较活跃度。 |
| 12 | volume | 成交量 | Volume | cjl | 基本行情 | 流动性/活跃度 | 与成交额配合识别流动性和异常放量。 |
| 13 | latestVolume | 现手 | Current VOL | xs | 基本行情 | 实时成交节奏 | 现手可辅助判断最新成交活跃度。 |
| 14 | sellVolume | 内盘 | Sell Vol | np | 基本行情 | 成交结构 | 内盘可辅助观察主动卖出压力。 |
| 15 | buyVolume | 外盘 | Buy Vol | wp | 基本行情 | 成交结构 | 外盘可辅助观察主动买入意愿。 |
| 16 | iopv | IOPV（净值估值） | IOPV (Net Value Valuation) | iopv | 基本行情 | ETF估值/折溢价 | ETF特有核心指标，用于判断二级市场价格相对净值估值偏离。 |
| 17 | premium | 折价 | Discount | zj | 基本行情 | 折溢价/套利线索 | 与IOPV和最新价配合，用于折溢价筛选。 |
| 18 | bid1 | 买1价 | Bid 1 Price | m1j | 盘口行情 | 盘口价差/可买卖价格 | 最优买价，用于买卖价差、成交可行性和滑点估计。 |
| 19 | ask1 | 卖1价 | Ask 1 Price | m1j | 盘口行情 | 盘口价差/可买卖价格 | 最优卖价，用于买卖价差、成交可行性和滑点估计。 |
| 20 | bidSize1 | 买1量 | Bid 1 Volume | m1l | 盘口行情 | 盘口深度/流动性 | 最优买一量，辅助判断买盘承接。 |
| 21 | askSize1 | 卖1量 | Ask 1 Volume | m1l | 盘口行情 | 盘口深度/流动性 | 最优卖一量，辅助判断卖盘压力。 |
