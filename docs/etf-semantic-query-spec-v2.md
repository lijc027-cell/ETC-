# ETF 语义查询 v2 设计稿（已归档）

> **状态：已归档，不进入实施。** 项目已转向 text2sql 方向。本文档保留作为设计参考，search/filter/compare/pipeline/catalog 等语义不再作为当前主线。

**原 Goal:** 将 ETF 查询从 v1 单只 ETF 标量查询，扩展为 v2A 搜索/筛选、v2B 多只对比；v2.1 保留持仓和基金经理深挖意向，但不在本轮实现。实时行情继续作为明确边界问题。

**Architecture:** v2 仍沿用现有 CLI + 本地校验 + 远端 Mongo 的主链路，但执行层分流为三类：`search` 走本地 catalog 匹配，`filter` 走本地 catalog 过滤/排序，`compare` 走本地 catalog 的两阶段汇总对比。Qwen 只生成结构化 plan，不直接执行搜索逻辑，也不负责最终答案。v2 的本地 catalog 必须包含支撑搜索、筛选、排序、对比所需的最小字段集。

**Tech Stack:** 现有 Python CLI、OpenAI-compatible Qwen、DashScope embedding、SSH/Mongo、local catalog cache.

---

## 1. 继承关系

v1 保留不变，仍覆盖：

- 单只 ETF 的基本信息、费率、收益率、分红、基金经理(现任)、跟踪指数
- 中文名称解析到 fundcode
- `basic_info` / `fund_scale` / `tracking_index` / `performance` / `fee` / `manager` / `fee_and_manager` / `dividend`

v2 在此基础上新增：

- `search`
- `filter`
- `compare`

---

## 2. v2 范围

### v2A: 搜索 / 筛选 / 排序
覆盖问题类型：

- 搜索 ETF：沪深300、中证500、创业板、MSCI中国A股、医药、人工智能
- 条件筛选：股票型 ETF、上交所规模前10、管理费率最低、跟踪沪深300按收益率排序、规模大于10亿、深交所债券型 ETF
- 混合问题第一跳：先找出候选 ETF

### v2B: 多只对比
覆盖问题类型：

- 显式代码对比：`510300、510500、159919`
- 基于筛选结果的对比：先找前5只，再展示收益和费率
- 混合问题第二跳：候选 ETF 的并列展示

### v2.1 后续候选
以下能力列为后续候选，不代表当前版本承诺：

- 前十大重仓股
- 持仓行业
- 最新季报持仓
- 机构持有情况
- 基金经理任职时长
- 基金经理历史业绩

### 明确不支持
- 实时行情

---

## 3. 查询计划形状

v2 继续复用现有顶层结构，只新增 `sort`、`keywords`，并在混合问题和 compare 场景下使用 `pipeline`：

```json
{
  "intent": "search",
  "collection": "tb_ths_etf_base",
  "keywords": ["医药"],
  "filter": {},
  "sort": {"field": "ths_fund_scale_fund", "order": "desc"},
  "projection": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_name_of_tracking_index_fund", "ths_fund_scale_fund"],
  "limit": 10,
  "answer_fields": [
    {"field": "fundcode", "label": "基金代码", "unit": "", "format": "plain"}
  ]
}
```

### 顶层字段
- 保留：`intent`, `collection`, `filter`, `projection`, `limit`, `answer_fields`
- 新增：`sort`, `keywords`, `pipeline`

### 语义
- `filter`：数据库语义，允许等值与受控比较
- `keywords`：仅 `search` 使用，本地语义，不传给 Mongo
- `sort`：单字段排序
- `limit`：最终返回条数
- `answer_fields`：输出格式说明

### Pipeline
`pipeline` 只用于两类场景：

- 需要先搜索/筛选，再进入对比的混合问题
- `intent = compare` 的所有对比问题

`pipeline` 是有序数组，每个 stage 必须是独立可验证的步骤，不能靠代码里的临时分支补齐语义。
`pipeline` 最少 2 段，最多 2 段。
顶层 `filter` / `sort` / `keywords` 与 `pipeline` 互斥，不允许同时出现。

```json
{
  "intent": "compare",
  "pipeline": [
    {
      "stage": "collect",
      "intent": "filter",
      "filter": {"ths_name_of_tracking_index_fund": "沪深300指数"},
      "sort": {"field": "ths_yeild_ytd_fund", "order": "desc"},
      "limit": 5
    },
    {
      "stage": "compare",
      "compare_fields": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_name_of_tracking_index_fund",
        "ths_fund_scale_fund",
        "ths_yeild_ytd_fund",
        "ths_yeild_1y_fund",
        "ths_manage_fee_rate_fund",
        "ths_mandate_fee_rate_fund"
      ],
      "limit": 5
    }
  ]
}
```

- `collect` stage 负责拿候选行
- `compare` stage 负责固定列顺序与表格化展示
- `compare_fields` 必须固定为 8 列默认对比字段，顺序不可漂移
- `collect.stage` 只允许 `collect`
- `compare.stage` 只允许 `compare`
- `collect` stage 允许 `filter`, `sort`, `limit`, `keywords`
- `compare` stage 只允许 `compare_fields`, `limit`
- `compare_fields` 不允许超出默认 8 列
- `collect.filter.fundcode` 在 compare pipeline 中可使用数组；其他 intent 下仍然只允许标量等值或单键比较对象
- `collect.intent` 必填，只允许 `search` 或 `filter`
- `compare` stage 不允许再次写 `intent`
- pipeline 模式下，最终 `projection` 和 `answer_fields` 由 `compare` stage 的 `compare_fields` 推导生成，不依赖顶层字段

---

## 4. Filter 规则

### 等值
标量值表示等值：

```json
{"ths_fund_invest_type_fund": "股票型"}
```

### 比较
单键对象表示比较：

```json
{"ths_fund_scale_fund": {">": 1000000000}}
```

### 允许比较符
- `=`
- `>`
- `>=`
- `<`
- `<=`

### 约束
- 比较对象必须只有一个 key
- 比较仅允许数值字段
- `filter` 允许多 key，默认 AND
- 不支持 `!=`
- 不支持 `$in`
- 不暴露 Mongo operator 给 Qwen

### 字段级白名单
v2 只允许以下字段进入 `filter` / `sort` / `compare` 相关决策：

| 字段 | 允许操作 | 说明 |
| --- | --- | --- |
| `fundcode` | `=` | 显式代码筛选和 compare 输入 |
| `thscode` | `=` | 交易所后缀代码精确匹配 |
| `ths_fund_invest_type_fund` | `=` | 例如 `股票型`、`债券型` |
| `ths_fund_listed_exchange_fund` | `=` | 例如 `上交所`、`深交所` |
| `ths_name_of_tracking_index_fund` | `=` | 仅接受标准化后的指数名 |
| `ths_tracking_index_code_fund` | `=` | 精确指数代码匹配 |
| `ths_fund_scale_fund` | `=` `>` `>=` `<` `<=` `sort` | 单位元 |
| `ths_manage_fee_rate_fund` | `=` `>` `>=` `<` `<=` `sort` | 百分比数值 |
| `ths_mandate_fee_rate_fund` | `=` `>` `>=` `<` `<=` `sort` | 百分比数值 |
| `ths_yeild_ytd_fund` | `sort` | 仅允许排序，不允许比较筛选 |
| `ths_yeild_1y_fund` | `sort` | 仅允许排序，不允许比较筛选 |

### 分类字段枚举值

v2 生成筛选条件前必须使用真实数据库枚举值，不允许让 Qwen 自行猜测。

| 字段 | 已知值 |
| --- | --- |
| `ths_fund_invest_type_fund` | `股票型`, `债券型`, `混合型`, `货币型`, `其他` |
| `ths_fund_listed_exchange_fund` | `上交所`, `深交所` |

### 真实枚举快照

以下值来自 2026-05-07 远端 Mongo 的 `distinct` 结果，后续实现只读这份固定映射，不再临时查询：

- `ths_fund_invest_type_fund`：`股票型`, `债券型`, `混合型`, `货币型`, `其他`
- `ths_fund_listed_exchange_fund`：`上交所`, `深交所`

### 口语映射

- `股票型ETF` -> `ths_fund_invest_type_fund = 股票型`
- `债券型ETF` -> `ths_fund_invest_type_fund = 债券型`
- `混合型ETF` -> `ths_fund_invest_type_fund = 混合型`
- `货币型ETF` -> `ths_fund_invest_type_fund = 货币型`
- `上交所` / `沪市` -> `ths_fund_listed_exchange_fund = 上交所`
- `深交所` / `深市` -> `ths_fund_listed_exchange_fund = 深交所`

分类筛选时，Qwen 不得自行猜测枚举值，只能从上述固定映射中选取。

### 值域阈值

| 字段 | 最小 | 最大 | 说明 |
| --- | --- | --- | --- |
| `ths_fund_scale_fund` | 1000000 | 1000000000000 | 100万到1万亿元 |
| `ths_manage_fee_rate_fund` | 0.01 | 10.0 | 0.01%到10% |
| `ths_mandate_fee_rate_fund` | 0.01 | 10.0 | 0.01%到10% |
| `ths_yeild_ytd_fund` | -100 | 1000 | 收益率合理区间 |
| `ths_yeild_1y_fund` | -100 | 1000 | 收益率合理区间 |

### 单位约束
- `ths_fund_scale_fund` 单位是元，`10亿` 必须写成 `1000000000`
- 费率和收益率字段按百分比数值处理
- spec 中要明确收益率存储语义：`8.88` 表示 `8.88%`
- 默认收益率周期为近1年，即 `ths_yeild_1y_fund`

### 值域防线
必须加 sanity check，避免单位转换静默出错。

---

## 5. Search 规则

### 关键词来源
从用户问题动态提取，不复用固定指数词表作为唯一来源。
提取规则：
- `搜索X` -> `X`
- `找X相关的ETF` -> `X`
- `有没有ETF名字里带X的` -> `X`
- `有没有名字叫"X"的ETF` -> `X`
- 去掉尾部泛词：`ETF`、`基金`、`指数`、`相关`

典型输入：
- `搜索中证500`
- `有没有ETF名字里带医药的`
- `有没有名字叫"人工智能"的ETF`

### `keywords`
仅在 `search` intent 中出现，顶层字段：

```json
"keywords": ["医药"]
```

### 匹配范围
本地 catalog 子串匹配以下字段：

- `ths_fund_extended_inner_short_name_fund`
- `ths_name_of_tracking_index_fund`
- `ths_tracking_index_code_fund`

要求：
- 去空格
- 大小写不敏感
- 不走远端 regex
- 不把 regex 暴露给 Qwen

### 歧义规则
- 只有单一高置信命中时，search 才能自动收敛到单条结果
- 多命中时返回候选列表，默认最多 5 条
- 候选不足以唯一确定时，标记为歧义，不允许直接进入后续 compare
- broad query 仍然可以返回搜索结果列表，但不能假装是唯一命中
- 如果关键词命中分类字段值，必须优先使用已校准枚举值，而不是原始用户字面量
- search 排序优先级固定如下：
  1. 如果用户明确说“名字里带 / 名字叫 / 名称包含”，优先按基金简称命中
  2. 精确命中标准化 DB 值
  3. 跟踪指数名称连续子串命中
  4. 跟踪指数名称分散命中
  5. 基金简称命中
- 同级候选按 `ths_fund_scale_fund desc`，再按 `fundcode asc` 稳定排序

### 标准化
常见指数名的标准化分两类：

1. `filter` 等值场景：用户说 `沪深300`、`中证500`、`创业板`、`MSCI中国A股`、`中证红利` 时，必须映射为真实 DB 实际值或真实值集合，再做等值匹配
2. `search` 场景：标准化名册只作为增强候选，不替代子串匹配；实际匹配结果由 catalog 子串打分决定
3. 如果 `filter` 等值场景无法标准化为单一 DB 值，则必须降级为 `search`，不允许做模糊等值

标准化名册示例：
- `沪深300` -> `沪深300指数`
- `中证500` -> `中证小盘500指数`
- `创业板` -> `创业板指数`
- `MSCI中国A股` -> 仅保留真实 catalog 里存在的 `MSCI中国A股*` 值，不生成 `MSCI中国A股指数`
- `中证红利` -> `中证红利指数`

真实 catalog 中相关的高频值示例：
- `中证500` 相关：`中证小盘500指数`, `中证500价值指数`, `中证500等权重指数`, `中证500行业中性低波动指数`, `中证500自由现金流指数`, `中证500质量成长指数`
- `创业板` 相关：`创业板指数`, `创业板50指数`, `创业板200指数`, `创业板人工智能指数`, `创业板医药卫生指数`, `创业板新能源指数`
- `医药` 相关：`上证医药卫生行业指数`, `中证中药指数`, `中证医疗指数`, `中证生物医药指数`, `中证医药卫生指数`, `中证医药50指数`, `创业板医药卫生指数`, `中证港股通医药卫生综合指数`
- `人工智能` 相关：`上证科创板人工智能指数`, `中证人工智能主题指数`, `中证人工智能产业指数`, `中证科创创业人工智能指数`, `创业板人工智能指数`, `中证沪港深人工智能50指数`

---

## 6. Compare 规则

### 显式 compare
用户直接给 fundcode：

```json
{
  "intent": "compare",
  "collection": "tb_ths_etf_base",
  "pipeline": [
    {
      "stage": "collect",
      "intent": "filter",
      "filter": {"fundcode": ["510300", "510500", "159919"]},
      "limit": 3
    },
    {
      "stage": "compare",
      "compare_fields": [
        "fundcode",
        "ths_fund_extended_inner_short_name_fund",
        "ths_name_of_tracking_index_fund",
        "ths_fund_scale_fund",
        "ths_yeild_ytd_fund",
        "ths_yeild_1y_fund",
        "ths_manage_fee_rate_fund",
        "ths_mandate_fee_rate_fund"
      ],
      "limit": 3
    }
  ]
}
```

说明：
- `compare` 的 `collect.filter.fundcode` 数组是 v2 受控例外，只对 `compare` pipeline 放行
- 该例外不影响 v1 单只查询的标量 filter 规则

### 派生 compare
先筛出候选，再对候选做对比：

- `对比所有跟踪沪深300的前5只ETF，看收益和费率`
- `股票型ETF里今年收益最高的5只是哪些？对比一下`

### 执行语义
- `compare` 必须使用 `pipeline`
- `pipeline[0]` 负责收集候选
- `pipeline[1]` 负责输出对比表
- `compare` 可接受显式 `fundcode` 数组，或接受普通 `filter + sort + limit` 作为候选收集方式
- 对比结果使用固定 8 列默认对比字段，列顺序必须固定

### 默认对比字段
- 基金代码
- 基金简称
- 跟踪指数
- 基金规模
- 今年以来收益率
- 近1年收益率
- 管理费率
- 托管费率

---

## 7. Sort 规则

### 形状
单字段：

```json
"sort": {"field": "ths_fund_scale_fund", "order": "desc"}
```

### 支持字段
- `ths_fund_scale_fund`
- `ths_manage_fee_rate_fund`
- `ths_mandate_fee_rate_fund`
- `ths_yeild_ytd_fund`
- `ths_yeild_1y_fund`

### 收益率字段
- 允许排序
- 不允许比较筛选

### 校验规则
- `sort.field` 必须在支持字段白名单内，否则拒绝
- `sort.order` 只能是 `asc` 或 `desc`
- `sort` 可以和同字段比较筛选同时出现，例如规模大于10亿后按规模降序

---

## 8. 执行路径

### v1 类 intent
继续走现有：
`plan -> validate -> remote Mongo -> formatter`

### `search`
`plan -> validate -> 本地 catalog -> 子串匹配 -> 排序 -> limit -> formatter`

### `filter`
`plan -> validate -> 本地 catalog -> filter/sort/limit -> formatter`

### `compare`
- 显式代码 compare：按 fundcode 数组取行
- 派生 compare：先 filter/sort/limit 再组成对比表

### catalog
- `fetch_etf_name_catalog` 首次启动时通过 SSH 拉取，之后优先读取本地快照
- catalog 来源必须是 `tb_ths_etf_base`
- catalog 至少要包含以下字段：
  - `fundcode`
  - `thscode`
  - `ths_fund_extended_inner_short_name_fund`
  - `ths_name_of_tracking_index_fund`
  - `ths_tracking_index_code_fund`
  - `ths_fund_invest_type_fund`
  - `ths_fund_listed_exchange_fund`
  - `ths_fund_scale_fund`
  - `ths_manage_fee_rate_fund`
  - `ths_mandate_fee_rate_fund`
  - `ths_yeild_ytd_fund`
  - `ths_yeild_1y_fund`
  - `ths_fund_establishment_date_fund`
  - `ths_fund_type_fund`
- catalog 拉取的是全量字段，不让 `limit` 约束远端采样
- `limit` 只约束最终展示数量
- catalog 需要本地缓存快照；快照失效或签名变化时按同一来源重新拉取
- 远端拉取失败时，允许回退到最近一次成功快照继续服务，但必须在 debug 中标明数据可能陈旧
- 快照文件路径沿用现有 embedding cache 目录，至少包含字段索引和 catalog 数据本体
- 快照签名必须包含：`data-dictionary.md` hash、catalog 字段清单、分类字段枚举映射版本、远端 DB 名称
- search/filter/compare 的固定词表必须从这份 catalog 与上述 distinct 快照生成，不得再临时依赖远端 distinct

### search/filter 输出格式

列表类输出使用表格或等价的等宽列表，列顺序固定为：

| 基金代码 | 基金简称 | 跟踪指数 | 基金规模 | 今年以来收益率 | 近1年收益率 | 管理费率 | 托管费率 |
| --- | --- | --- | --- | --- | --- | --- | --- |

### compare 输出格式

对比表固定使用相同列顺序，按行展示每只 ETF 的固定 8 列：

| 基金代码 | 基金简称 | 跟踪指数 | 基金规模 | 今年以来收益率 | 近1年收益率 | 管理费率 | 托管费率 |
| --- | --- | --- | --- | --- | --- | --- | --- |

---

## 9. 触发规则

### intent 选择
- 先判断是否显式要求对比或比较
- 再判断是否要求筛选/排序
- 最后才判断 search
- `search`：搜索、找、有没有、名字里带
- `filter`：筛选、条件查询、排序 Top N
- `compare`：对比、比较、比较一下、看差异
- 含“对比”的优先 `compare`
- 混合意图必须拆成 `pipeline`，不能单 intent 硬吃

### 无 fundcode
- `search` / `filter` / `compare` 不要求先识别 fundcode
- 只有单只查询 intent 才要求 fundcode；找不到时先走名称反查
- 名称反查失败后，单只查询才报错
- 列表类 intent 允许 `fundcode = null`

---

## 10. v2 兜底策略

v2 的确定性兜底只在 Qwen 失败时触发，不做提前拦截，不根据关键词抢跑。

触发条件：
- Qwen 返回非法 JSON
- Qwen 返回的 plan 不满足 schema-like 结构
- plan 校验失败

兜底原则：
- 只覆盖高频、低歧义的模板
- `search/filter/compare` 兜底必须生成合法 plan 或合法 pipeline
- 如果无法生成合法计划，保留原始错误，不编造结果

典型兜底：
- `股票型ETF` -> `filter` + `ths_fund_invest_type_fund = 股票型`
- `上交所规模前10` -> `filter` + `ths_fund_listed_exchange_fund = 上交所` + `sort` + `limit 10`
- `搜索医药` -> `search` + `keywords=["医药"]`

---

## 11. v2.1 明确不在当前版本内

以下能力不在 v2A+B 范围内，后续单独开 spec 或版本再做：

- 510300前十大重仓股是什么
- 159919的持仓行业有哪些
- 510500最新季报的持仓
- 510300的机构持有情况
- 510300现任基金经理管理了多久
- 510300基金经理的历史业绩
- 搜索中证红利后查持仓

---

## 12. 测试覆盖

### 必测
- 搜索 ETF 关键词命中简称/指数名/指数代码
- `keywords` 顶层字段可用，`filter` 保持纯数据库语义
- 规模大于 10 亿转成 `1000000000`
- 费率/收益率值域校验
- 上交所、深交所、股票型、债券型筛选
- 管理费率最低、规模前10、收益最高排序
- 显式 compare 和派生 compare
- 实时行情返回明确不支持
- v2.1 问题返回当前版本不支持提示
- pipeline 校验拒绝非法 stage、非法字段和顶层/管道混放
- compare 的 fundcode 数组只在 compare 放行
- 值域超出阈值时报错而不是静默执行
- search/filter/compare 的 formatter 输出列顺序固定

### formatter
- `search/filter` 输出列表
- `compare` 输出对比表
- v1 单只查询继续输出单句回答

---

## 13. Assumptions

- v2A+B 只使用 `tb_ths_etf_base`
- 不开放 array/object 投影
- Qwen 只输出结构化 plan
- Mongo operator 只由本地校验/编译层生成
- `limit` 仅控制最终返回数量，不控制 catalog 拉取量
