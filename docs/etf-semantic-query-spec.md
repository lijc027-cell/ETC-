# ETF 语义查询 Agent 技术方案

## 1. 背景

本方案用于在 `/Users/l/Downloads/laiqian/etf-query` 内实现一个独立的本地原型，不接入现有 `financial-analysis-langchain` 项目。

本 spec 和 `skill.md` 的关系：

- `skill.md` 描述旧的 ETF 查询 skill，核心方式是调用远端 `[ETF_REMOTE_SCRIPT]`。
- 本 spec 描述新的本地语义查询原型，核心方式是解析字段映射、向量召回、Qwen 生成计划、SSH 直查远端 Mongo。
- 第一版实现以本 spec 为准，不调用 `[ETF_REMOTE_SCRIPT]`。

第一版要验证的核心链路是：

```text
自然语言问题
  -> 实体抽取
  -> 如缺少基金代码，则确定性 ETF 名称解析
  -> 基于字段映射表的向量检索
  -> Qwen 生成查询计划
  -> 查询计划校验
  -> SSH 远端 Mongo 只读查询
  -> 返回数据库结果
  -> 输出调试过程和简短答案
```

远端数据库已经存在，第一版不建库、不迁移数据、不改数据库结构。

v1 最终定位：

```text
自然语言 -> 安全可校验的查询计划 -> 远端 Mongo -> 本地模板化人话结果
```

不要定位成：

```text
自然语言 -> 查库 -> Qwen 自由总结/分析
```

Qwen 只负责把自然语言转成结构化查询计划。数据查询、结果格式化和最终展示全部由本地确定性逻辑完成。

## 2. 目标

- 支持从命令行输入自然语言 ETF 问题。
- 抽取确定性实体，例如 ETF 基金代码、时间周期；缺少 6 位代码时，支持单只 ETF 中文名称解析。
- 从 `references/data-dictionary.md` 解析字段映射，并构建可向量检索的索引。
- 根据用户问题召回相关数据库字段候选。
- 使用 Qwen 在候选字段范围内生成 Mongo 查询计划。
- 在执行前校验查询计划，避免模型编造表名、字段名或生成危险操作。
- 通过 SSH 在远端执行只读 Mongo 查询。
- 默认优先输出最终简短回答和关键查询信息；使用 `--verbose` 输出完整调试链路，便于本地验证。

## 3. 非目标

- 第一版不接入现有 FastAPI/SSE 服务。
- 第一版不封装 MCP。
- 第一版不做前端页面。
- 第一版不支持数据库写入、更新、删除。
- 第一版不完整支持 ETF、指数、概念、分析框架的全部问题。
- 第一版不依赖远端 `[ETF_REMOTE_SCRIPT]` 脚本执行查询。
- 第一版不让 Qwen 生成最终答案、投资判断、归因分析或扩展解释。

## 4. v1 支持范围

v1 只支持单只 ETF 的标量字段查询。若远端真实字段以 `[{value, btime}]` 时间序列形式存储，v1 只取最新 `btime` 的 `value` 做标量展示，不展开完整时间序列。

| intent | 支持问题 | 数据范围 |
| --- | --- | --- |
| `basic_info` | 基本信息、是什么、介绍 | 基金代码、简称、类型、跟踪指数、规模等基础字段 |
| `fund_scale` | 基金规模、盘子多大 | 基金规模、总市值 |
| `tracking_index` | 跟踪什么指数、标的指数 | 跟踪指数代码、跟踪指数名称 |
| `performance` | 收益率、表现、涨跌、回报 | 各周期收益率和排名 |
| `fee` | 管理费、托管费、费率 | 管理费率、托管费率 |
| `manager` | 基金经理、谁在管、管理人 | 现任基金经理、基金管理人 |
| `fee_and_manager` | 费率和基金经理组合问题 | 管理费率、托管费率、现任基金经理、基金管理人 |

v1 支持单只 ETF 中文名称解析，但只用于解析 `fundcode`，不作为搜索/筛选功能。示例：

```text
工银沪深300ETF的费率和基金经理是什么
  -> fundcode=510350
  -> matched_name=沪深300ETF工银
```

v1 暂不支持：

- 持仓、行业、概念
- 对比、搜索、筛选
- 季报/年报数据查询
- “有哪些 ETF”“帮我找 ETF”这类搜索/筛选问题
- array/object 字段展开
- 多只 ETF 或多意图复杂组合

## 5. 运行方式

第一版做成独立 CLI：

```bash
.venv/bin/python etf_agent_demo.py "510300 盘子有多大"
```

默认输出适合演示的人话结果：

```text
用户问题
最终简短回答
关键查询信息
提示：需要完整调试链路和远端原始 JSON 时，加 --verbose。
```

完整调试信息通过 `--verbose` 输出：

```text
实体识别结果
向量召回候选
Qwen 查询计划
SQL-like 展示语句
Mongo 查询参数
远端数据库结果
字段中文名映射
调试过程
```

只输出最终人话回答可使用 `--answer-only`。

## 6. 配置

在 `etf-query` 下新增独立 `.env.example`：

```env
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

ETF_AGENT_LLM_MODEL=qwen-plus
ETF_AGENT_EMBEDDING_MODEL=text-embedding-v3
ETF_AGENT_EMBEDDING_DIM=1024

ETF_SSH_HOST=[ETF_SSH_HOST]
ETF_SSH_PORT=22
ETF_SSH_USER=[ETF_SSH_USER]
ETF_SSH_PASSWORD=
ETF_REMOTE_PYTHON=[ETF_REMOTE_PYTHON]
ETF_REMOTE_MONGO_URI=[ETF_REMOTE_MONGO_URI]
ETF_REMOTE_DB=[ETF_REMOTE_DB]
```

第一版 SSH 主机、用户、远端 Python 和数据库名可以参考 `references/api-reference.md`。真实 SSH 密码只允许写入本地 `.env`，不要写入 `.env.example`、spec 或代码。

项目必须通过 `.gitignore` 排除 `.env`、`.venv/`、`.cache/` 等本地敏感或生成文件。已暴露的 API Key 或 SSH 密码必须轮换。

`references/api-reference.md` 中的 `[ETF_REMOTE_SCRIPT]` 只作为远端环境背景参考。第一版查询执行不调用该脚本，而是通过 SSH 执行固定 Python 查询模板直连 Mongo。

## 7. 数据字典解析

`references/data-dictionary.md` 作为第一版字段映射表。解析器需要抽取：

- 集合名，例如 `tb_ths_etf_base`
- 字段名，例如 `ths_fund_scale_fund`
- 中文字段名，例如 `基金规模`
- 字段类型，如果文档中存在
- 字段说明，如果文档中存在
- 所属分组，例如 `规模与净值`、`收益率（各周期）`

解析规则：

- 集合名来自最近的二级标题 `## tb_xxx`。
- 分组名来自最近的三级标题 `### xxx`；如果没有三级标题，则使用集合标题。
- Markdown 表格按表头列名解析，不依赖固定列序。
- 字段名列识别 `字段名`。
- 中文名列识别 `中文名`。
- 类型列识别 `类型`；不存在时设为 `""`。
- 说明列识别 `说明`；不存在时设为 `""`。
- 空行、分隔行、非字段表格行必须跳过。
- 必须解析 `data-dictionary.md` 中出现的全部集合，包括 `tb_ths_etf_base`、`tb_ths_etf_report_quarter`、`tb_ths_etf_report_year`。

每个字段解析成一个映射项：

```json
{
  "id": "tb_ths_etf_base.ths_fund_scale_fund",
  "collection": "tb_ths_etf_base",
  "field": "ths_fund_scale_fund",
  "cn_name": "基金规模",
  "type": "number",
  "description": "单位：元",
  "section": "规模与净值",
  "search_text": "ETF tb_ths_etf_base 规模与净值 基金规模 单位：元 ths_fund_scale_fund"
}
```

其中 `search_text` 用于生成向量，必须按以下模板生成：

```text
ETF字段 {cn_name} {description} 所属分组:{section} 集合:{collection} 字段:{field}
```

如果 `description` 为空，模板中对应位置留空但不省略其他部分。

## 8. 向量检索

使用 `ETF_AGENT_EMBEDDING_MODEL` 配置的通义/DashScope embedding 模型生成向量。第一版默认使用 `text-embedding-v3`，向量维度为 `1024`。Qwen 聊天模型负责查询计划生成，embedding 模型负责语义召回。

索引策略：

- 首次运行时解析 `data-dictionary.md`，生成字段映射向量，并写入本地缓存。
- 后续运行时，如果数据字典文件 hash 没变，直接读取缓存。
- 如果数据字典变更，重新构建索引。
- 缓存签名必须包含：`data-dictionary.md` 文件 hash、`ETF_AGENT_EMBEDDING_MODEL`、`ETF_AGENT_EMBEDDING_DIM`、`DASHSCOPE_BASE_URL`。
- 如果 embedding 模型、维度或 base URL 变化，必须重建索引。

Embedding API 调用：

- 使用 OpenAI-compatible embeddings 接口，base URL 为 `DASHSCOPE_BASE_URL`。
- 推荐使用 `openai` Python SDK 调用 `/v1/embeddings`。
- 批量构建索引时按 batch 调用，默认 `batch_size=10`。实测 DashScope OpenAI-compatible `text-embedding-v3` 会拒绝大于 10 的 batch。
- 查询时单条输入用户原始问题生成 query embedding。
- 每条返回向量长度必须等于 `ETF_AGENT_EMBEDDING_DIM`，否则视为 embedding 阶段失败。
- 实现前必须用 `text-embedding-v3` 做一次最小调用验证；如果 compatible mode 不支持该模型，再调整为可用的通义 embedding 调用方式。

缓存路径可以使用：

```text
.cache/etf_mapping_index.json
```

检索输入：

```json
{
  "query": "510300 盘子有多大",
  "top_k": 8
}
```

检索输出：

```json
[
  {
    "score": 0.87,
    "collection": "tb_ths_etf_base",
    "field": "ths_fund_scale_fund",
    "cn_name": "基金规模",
    "description": "单位：元"
  }
]
```

## 9. 实体抽取

Qwen 生成查询计划之前，先用确定性规则抽取实体。

第一版必须支持：

- `fundcode`：识别第一个 6 位数字，例如 `510300`
- `period`：识别常见中文周期
  - `近一周` -> `1w`
  - `近一月` / `近1月` -> `1m`
  - `近三月` / `近3月` -> `3m`
  - `近六月` / `近6月` -> `6m`
  - `近一年` / `近1年` / `最近一年` -> `1y`
  - `今年以来` -> `ytd`
  - `成立以来` -> `std`

如果没有识别到基金代码，第一版进入 ETF 中文名称解析。名称解析只用于把单只 ETF 名称解析为 `fundcode`，不支持搜索、筛选或推荐 ETF。

名称解析成功时，实体结果追加：

```json
{
  "fundcode": "510350",
  "resolved_by": "name",
  "matched_name": "沪深300ETF工银",
  "matched_thscode": "510350.SH"
}
```

名称解析规则：

- 只读查询 `tb_ths_etf_base`。
- 只允许返回 `fundcode`、`thscode`、`ths_fund_extended_inner_short_name_fund`、`ths_fund_supervisor_fund`、`ths_name_of_tracking_index_fund`、`ths_tracking_index_code_fund`。
- 不经过 Qwen，不让模型猜基金代码。
- 支持基金公司和指数关键词顺序反转，例如 `工银沪深300ETF` 可匹配 `沪深300ETF工银`。
- 多只匹配时不默认选择，返回候选让用户补充。
- 无匹配时返回未找到。

名称解析返回三种状态：

```json
{
  "status": "matched",
  "fundcode": "510350",
  "matched_name": "沪深300ETF工银",
  "matched_thscode": "510350.SH",
  "matches": []
}
```

```json
{
  "status": "ambiguous",
  "matches": [
    {"fundcode": "159919", "name": "沪深300ETF", "thscode": "159919.SZ"},
    {"fundcode": "510350", "name": "沪深300ETF工银", "thscode": "510350.SH"},
    {"fundcode": "510330", "name": "沪深300ETF华夏", "thscode": "510330.SH"}
  ]
}
```

```json
{
  "status": "not_found",
  "matches": []
}
```

如果基金代码和名称都无法解析，第一版失败并提示：

```text
实体抽取失败：未识别到 6 位 ETF 基金代码。
```

宽泛搜索类问题，例如 `有哪些沪深300ETF`，不纳入第一版主流程。

多匹配错误输出示例：

```text
阶段：ETF 名称解析
错误：匹配到多只 ETF，请补充具体产品

候选 ETF
- 159919 沪深300ETF 159919.SZ
- 510350 沪深300ETF工银 510350.SH
- 510330 沪深300ETF华夏 510330.SH
```

## 10. 候选增强规则

向量检索前后增加轻量确定性增强，避免常见口语表达完全依赖 embedding 召回。

候选增强不直接执行查询，只用于补充可供 Qwen 选择的候选字段。

第一版必须内置以下增强规则：

| 用户表达/意图 | 强制补充候选字段 |
| --- | --- |
| `是什么`、`介绍`、`基本信息`、`概况` | `fundcode`、`ths_fund_extended_inner_short_name_fund`、`ths_fund_type_fund`、`ths_fund_invest_type_fund`、`ths_name_of_tracking_index_fund`、`ths_fund_scale_fund`、`ths_fund_establishment_date_fund`、`ths_fund_supervisor_fund` |
| `盘子`、`规模`、`多大`、`资产规模` | `ths_fund_scale_fund`、`ths_current_mv_fund` |
| `跟踪`、`跟的`、`指数`、`标的指数` | `ths_tracking_index_code_fund`、`ths_name_of_tracking_index_fund` |
| `管理费`、`托管费`、`费率`、`贵不贵` | `ths_manage_fee_rate_fund`、`ths_mandate_fee_rate_fund` |
| `基金经理`、`谁在管`、`管理人` | `ths_fund_manager_current_fund`、`ths_fund_supervisor_fund` |
| 同时包含费率和基金经理/管理人 | `ths_manage_fee_rate_fund`、`ths_mandate_fee_rate_fund`、`ths_fund_manager_current_fund`、`ths_fund_supervisor_fund` |
| `表现`、`收益率`、`涨跌`、`赚了`、`回报` | 根据 `period` 补充对应周期的收益率和排名字段；如果没有识别到 `period`，默认补充 `1y` 周期字段 |

周期字段增强：

| period | 强制补充候选字段 |
| --- | --- |
| `1w` | `ths_yeild_1w_fund`、`ths_yeild_rank_1w_fund_origin`、`ths_yeild_rank_1w_etf` |
| `1m` | `ths_yeild_1m_fund`、`ths_yeild_rank_1m_fund_origin`、`ths_yeild_rank_1m_etf` |
| `3m` | `ths_yeild_3m_fund`、`ths_yeild_rank_3m_fund_origin`、`ths_yeild_rank_3m_etf` |
| `6m` | `ths_yeild_6m_fund`、`ths_yeild_rank_6m_fund_origin`、`ths_yeild_rank_6m_etf` |
| `1y` | `ths_yeild_1y_fund`、`ths_yeild_rank_1y_fund_origin`、`ths_yeild_rank_1y_etf` |
| `ytd` | `ths_yeild_ytd_fund`、`ths_yeild_rank_ytd_fund_origin`、`ths_yeild_rank_ytd_etf` |
| `std` | `ths_yeild_std_fund`、`ths_yeild_rank_std_fund_origin`、`ths_yeild_rank_std_etf` |

候选合并顺序：

```text
实体抽取结果
  -> 同义词/意图增强候选
  -> 向量检索 top_k 候选
  -> 合并去重
  -> 交给 Qwen 生成查询计划
```

合并规则：

- 多条增强规则同时命中时，候选字段取并集。
- 候选去重 key 为 `collection.field`。
- 合并后候选顺序为：增强候选在前，向量候选按 `score` 降序追加。
- 如果增强候选和向量候选重复，保留增强候选，并附带向量分数作为调试信息。

## 11. Qwen 查询计划生成

Qwen 输入包括：

- 用户原始问题
- 实体抽取结果
- 向量召回的字段候选
- 允许使用的集合和字段

Qwen 必须输出严格 JSON：

```json
{
  "intent": "fund_scale",
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
      "field": "ths_fund_scale_fund",
      "label": "基金规模",
      "unit": "元",
      "format": "yuan_to_100m"
    }
  ]
}
```

Qwen 禁止输出：

- `answer`
- `analysis`
- `summary`
- `recommendation`
- `sql_like`
- 任意解释性自然语言字段

查询计划 schema：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `intent` | string | 是 | 识别出的查询意图，如 `basic_info`、`fund_scale`、`tracking_index` |
| `collection` | string | 是 | Mongo 集合名，必须来自数据字典 |
| `filter` | object | 是 | 只允许等值过滤 |
| `projection` | string[] | 是 | 要返回的字段列表 |
| `limit` | integer | 是 | 1 到 20 |
| `answer_fields` | object[] | 是 | 结果格式化时使用的字段描述 |

`answer_fields` 每项 schema：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `field` | string | 是 | projection 中的字段 |
| `label` | string | 是 | 中文展示名 |
| `unit` | string | 否 | 如 `元`、`%` |
| `format` | string | 否 | 如 `yuan_to_100m`、`percent`、`plain` |

禁止额外顶层字段。禁止未知嵌套字段。Qwen 返回非法 JSON 或 schema 不符合要求时，进入查询计划生成失败或校验失败流程。

Qwen 常见 intent 别名需要在校验前归一化：

| Qwen 输出 | 归一化 intent |
| --- | --- |
| `fund_basic_info` | `basic_info` |
| `fund_performance` | `performance` |
| `fund_fee` | `fee` |
| `fund_fee_and_manager` | `fee_and_manager` |
| `track_index` / `tracking` | `tracking_index` |
| `scale` | `fund_scale` |

如果 Qwen 返回的 JSON 有说明文字包裹，例如 `好的，这是查询计划：```json ... ``` `，本地应从 fenced JSON code block 中提取 JSON 后再解析。

如果 Qwen 返回结果缺少必填字段，或 `answer_fields` 不是 object 数组，允许进入确定性 fallback；如果只是多出额外字段，则交给正式查询计划校验层拒绝，而不是提前 fallback。

`sql_like` 不由 Qwen 生成。本地在查询计划校验通过后，根据 `collection`、`filter`、`projection` 机械生成 SQL-like 展示语句，避免调试语句和真实执行计划漂移。

Prompt 约束：

- 只能使用向量召回候选字段，以及必要身份字段，如 `fundcode`
- 第一版只能使用 `tb_ths_etf_base`
- 只能生成只读查询计划
- 不允许编造集合名和字段名
- 只返回 JSON，不返回 Markdown
- 不返回 `sql_like`

System prompt 模板：

```text
你是 ETF 数据库查询计划生成器。

你的任务是根据用户问题、已抽取实体、候选字段，生成一个只读 Mongo 查询计划 JSON。

严格规则：
1. 只能使用输入中提供的候选字段和身份字段白名单。
2. 不允许编造集合名、字段名、过滤条件。
3. 只允许生成 find/find_one 等价的只读查询计划。
4. 不允许生成 insert、update、delete、drop、aggregate、$where、$regex、$ne、$gt、$lt、$in 等操作。
5. filter 只能使用 fundcode 或 thscode 的等值条件。
6. projection 必须是字段名字符串数组。
7. limit 必须是 1 到 20 的整数。
8. answer_fields 只能描述 projection 中的字段。
9. format 只能是 plain、yuan_to_100m、percent、date。
10. 只返回 JSON，不要返回 Markdown、解释文字或 sql_like。
```

User prompt 模板：

```text
用户问题：
{question}

实体抽取结果：
{entities_json}

允许的身份字段：
["fundcode", "thscode", "ths_fund_extended_inner_short_name_fund"]

候选字段：
{candidate_fields_json}

请输出符合 schema 的查询计划 JSON：
{
  "intent": "string",
  "collection": "string",
  "filter": {"fundcode": "string"},
  "projection": ["string"],
  "limit": 1,
  "answer_fields": [
    {"field": "string", "label": "string", "unit": "string", "format": "plain|yuan_to_100m|percent|date"}
  ]
}
```

候选字段传给 Qwen 的结构：

```json
[
  {
    "id": "tb_ths_etf_base.ths_fund_scale_fund",
    "collection": "tb_ths_etf_base",
    "field": "ths_fund_scale_fund",
    "cn_name": "基金规模",
    "type": "number",
    "description": "单位：元",
    "section": "规模与净值",
    "score": 0.87,
    "source": "vector"
  }
]
```

Few-shot 示例：

```text
输入问题：510300 盘子有多大
实体：{"fundcode":"510300"}
候选字段包含：tb_ths_etf_base.ths_fund_scale_fund

输出：
{
  "intent": "fund_scale",
  "collection": "tb_ths_etf_base",
  "filter": {"fundcode": "510300"},
  "projection": ["fundcode", "ths_fund_scale_fund"],
  "limit": 1,
  "answer_fields": [
    {"field": "ths_fund_scale_fund", "label": "基金规模", "unit": "元", "format": "yuan_to_100m"}
  ]
}
```

## 12. 查询计划校验

远端执行前必须校验 Qwen 输出。

校验规则：

- `collection` 必须存在于数据字典。
- v1 只能使用 `tb_ths_etf_base`；`tb_ths_etf_report_quarter`、`tb_ths_etf_report_year` 暂不进入真实查询。
- v1 intent 必须属于 `basic_info`、`fund_scale`、`tracking_index`、`performance`、`fee`、`manager`、`fee_and_manager`。
- `projection` 字段必须存在于该集合。
- `projection` 原则上只能来自合并后的候选字段，额外允许身份字段白名单和 v1 intent 模板字段。
- 如果候选字段为空，且 projection 中包含非身份、非模板字段，校验层必须拒绝，避免候选召回异常时放行任意字段。
- 第一版默认禁止 projection 已知 array/object 字段；后续显式支持数组格式化时再开放。
- `filter` 第一版只允许使用：
  - `fundcode`
  - 可选 `thscode`
- `filter` key 不能以 `$` 开头。
- `filter` value 只允许 string、number、boolean、null 标量。
- `filter` value 不允许 object 或 array。
- 禁止 `$where`、`$regex`、`$ne`、`$gt`、`$lt`、`$in` 等任何 Mongo operator。
- `limit` 必须是 1 到 20 之间的整数。
- `answer_fields[].field` 必须存在于 `projection`。
- `answer_fields[].format` 只能是 `plain`、`yuan_to_100m`、`percent`、`date`。
- 拒绝任何包含 insert、update、delete、drop 等写操作语义的计划。
- 拒绝未知集合和未知字段。

校验失败时，输出失败原因和原始查询计划，并停止执行 SSH 查询。

intent 模板补齐：

校验层在基础 schema 和安全校验通过后，根据 v1 高频 intent 自动补齐必须字段。补齐只追加缺失字段，不删除 Qwen 多选字段。不因缺少模板字段而拒绝查询计划，也不触发 Qwen 重试。

| intent | 必须补齐的 projection |
| --- | --- |
| `basic_info` | `fundcode`、`ths_fund_extended_inner_short_name_fund`、`ths_name_of_tracking_index_fund`、`ths_fund_scale_fund` |
| `fund_scale` | `ths_fund_scale_fund` |
| `tracking_index` | `ths_tracking_index_code_fund`、`ths_name_of_tracking_index_fund` |
| `performance` | 根据 `period` 补齐对应 `ths_yeild_{period}_fund`、`ths_yeild_rank_{period}_fund_origin`、`ths_yeild_rank_{period}_etf` |
| `fee` | `ths_manage_fee_rate_fund`、`ths_mandate_fee_rate_fund` |
| `manager` | `ths_fund_manager_current_fund`、`ths_fund_supervisor_fund` |
| `fee_and_manager` | `ths_manage_fee_rate_fund`、`ths_mandate_fee_rate_fund`、`ths_fund_manager_current_fund`、`ths_fund_supervisor_fund` |

如果 `intent` 不在上述列表，v1 校验层拒绝，不进入真实远端查询。

模板补齐后的 projection 仍必须重新经过字段存在性、array/object 禁止、filter 和 limit 校验。`answer_fields` 也要为补齐字段同步补齐，字段中文名来自数据字典，`format` 按字段说明和类型确定。

最终执行时，`projection` 转换为 Mongo projection：

```json
{
  "fundcode": 1,
  "ths_fund_scale_fund": 1,
  "_id": 0
}
```

SQL-like 展示语句生成规则：

```text
SELECT <projection 逗号分隔>
FROM <collection>
WHERE <filter_key> = '<escaped_filter_value>'
LIMIT <limit>;
```

第一版只支持单个等值过滤字段。如果 `filter` 中有多个字段，校验层应拒绝。字符串值中的单引号在 SQL-like 中转义为 `''`。SQL-like 只用于调试展示，不参与远端执行。

## 13. 远端 Mongo 查询

执行器通过 SSH 连接远端服务器，然后在远端运行受控 Python 代码查询 Mongo。第一版一次 `semantic_query()` 只执行一个查询，不做并行查询；一次调用使用一个 SSH 连接完成上传、执行、下载和清理。

远端执行逻辑：

- 连接 `MongoClient(ETF_REMOTE_MONGO_URI, serverSelectionTimeoutMS=5000)[ETF_REMOTE_DB]`
- 如果 `limit == 1`，执行 `find_one`
- 否则执行 `find(...).limit(limit)`
- 使用已经校验过的 `filter` 和 `projection`
- 将 ObjectId、日期等不可 JSON 序列化对象转成字符串
- 将结果写入远端临时 JSON 文件
- 通过 SFTP 读取结果，避免中文编码问题
- 远端 runner 捕获 Mongo 查询异常，并写入 `{"success": false, "error": "...", "traceback": "..."}`；本地读取后明确报“远端 Mongo 查询失败”。

安全执行流程：

```text
1. 本地生成 uuid。
2. 本地把已校验 query plan 写入临时 JSON 文件。
3. 通过 SFTP 上传到远端唯一临时路径，例如 /tmp/etf_query_plan_{uuid}.json。
4. 本地通过 SSH `exec_command` 执行固定内联 Python runner 模板，模板代码由本地项目维护。
5. runner 只接收两个路径参数：query plan 文件路径和结果文件路径。
6. runner 读取 JSON，执行只读 Mongo 查询。
7. runner 写入 /tmp/etf_query_result_{uuid}.json。
8. 本地通过 SFTP 读取结果文件。
9. 尝试删除远端 query plan 和 result 临时文件。
10. 临时文件清理失败时打印 warning，不影响已成功返回的查询结果。
```

安全要求：

- 不能把 Qwen 生成的代码直接传到远端 shell 执行。
- 本地只传递已经校验过的 JSON 查询计划。
- 远端 Python 代码只解释固定结构的查询计划。
- 不使用固定 `/tmp/etf_result.json`，避免并发覆盖。
- 不通过 shell 拼接未转义 JSON 执行查询。
- 临时文件删除失败时记录 warning，不影响已经成功返回的查询结果。
- 第一版不要求远端预先存在 runner 脚本。
- 固定 runner 模板禁止使用 `eval()` 或 `exec()`。

远端 runner 模板草稿：

```python
import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient


def to_jsonable(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value


def main():
    query_plan_path = sys.argv[1]
    result_path = sys.argv[2]
    mongo_uri = sys.argv[3]
    db_name = sys.argv[4]

    try:
        with open(query_plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        collection = db[plan["collection"]]
        projection = {field: 1 for field in plan["projection"]}
        projection["_id"] = 0

        if plan["limit"] == 1:
            result = collection.find_one(plan["filter"], projection)
        else:
            result = list(collection.find(plan["filter"], projection).limit(plan["limit"]))

        out = {"success": True, "data": to_jsonable(result)}
    except Exception as exc:
        out = {"success": False, "error": str(exc), "traceback": traceback.format_exc(limit=5)}
    Path(result_path).write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
```

runner 参数来源：

- `query_plan_path` 和 `result_path` 为本地生成 uuid 后的远端临时路径。
- `mongo_uri` 来自本地 `.env` 的 `ETF_REMOTE_MONGO_URI`。
- `db_name` 来自本地 `.env` 的 `ETF_REMOTE_DB`。
- 这些参数由本地代码使用安全 quoting 传给 SSH 命令；query plan JSON 内容不通过 shell 参数传递。

## 14. 结果格式化

默认输出：

1. 用户问题
2. 最终简短回答
3. 关键查询信息：基金代码、集合、projection 字段

`--verbose` 输出额外调试信息：

1. 实体识别结果
2. 向量召回候选
3. Qwen 查询计划
4. SQL-like 展示语句
5. Mongo 查询参数
6. 远端数据库原始 JSON 结果
7. 字段中文名映射
8. 调试过程

常见格式规则：

- 文档说明为 `单位：元` 的字段，同时展示转换后的 `亿元`
- 百分比字段展示 `%`
- 空值或缺失字段展示 `暂无数据`
- 金额字段按 `原始值 / 1e8` 转成亿元，保留 2 位小数。
- 百分比字段默认数据库原始值已经是百分比数值，直接追加 `%`，不乘以 100。
- 普通数值保留原始精度或最多 4 位有效小数。
- null、缺失字段、空字符串统一由本地格式化层展示为 `暂无数据`；远端 runner 只返回原始查询结果，不做展示格式处理。
- 如果远端字段返回 `[{ "value": ..., "btime": "YYYY-MM-DD" }]` 时间序列数组，格式化层取最新 `btime` 对应的 `value`，并在回答中追加日期，例如 `1842.65 亿元（2026-05-05）`。

ResultFormatter 行为边界：

- 只基于 `answer_fields` 和 Mongo 原始结果陈述字段名和值。
- 不做投资判断。
- 不做涨跌原因、归因分析或风险扩展。
- 不追加用户没有请求的解释。
- 不调用 Qwen 生成最终答案。

示例：

```text
510300 的基金规模为 123.45 亿元。
```

## 15. 第一版测试问题

至少跑通以下命令：

```bash
.venv/bin/python etf_agent_demo.py "510300 是什么"
.venv/bin/python etf_agent_demo.py "510300 盘子有多大"
.venv/bin/python etf_agent_demo.py "510300 跟踪什么指数"
.venv/bin/python etf_agent_demo.py "510300 近一年表现怎么样"
.venv/bin/python etf_agent_demo.py "510300 的管理费和托管费是多少"
.venv/bin/python etf_agent_demo.py "工银沪深300ETF的费率和基金经理是什么"
```

每次运行必须输出：

- 识别出的 `fundcode`
- 最终简短回答
- 默认输出关键查询信息
- 使用 `--verbose` 时输出向量召回候选、合法 JSON 查询计划、SQL-like 展示语句、Mongo 查询参数、远端查询结果

每个问题的 projection 至少包含以下字段：

| 测试问题 | 必须包含字段 |
| --- | --- |
| `510300 是什么` | `fundcode`、`ths_fund_extended_inner_short_name_fund`、`ths_name_of_tracking_index_fund`、`ths_fund_scale_fund` |
| `510300 盘子有多大` | `fundcode`、`ths_fund_scale_fund` |
| `510300 跟踪什么指数` | `fundcode`、`ths_tracking_index_code_fund`、`ths_name_of_tracking_index_fund` |
| `510300 近一年表现怎么样` | `fundcode`、`ths_yeild_1y_fund`、`ths_yeild_rank_1y_fund_origin`、`ths_yeild_rank_1y_etf` |
| `510300 的管理费和托管费是多少` | `fundcode`、`ths_manage_fee_rate_fund`、`ths_mandate_fee_rate_fund` |
| `工银沪深300ETF的费率和基金经理是什么` | `fundcode`、`ths_manage_fee_rate_fund`、`ths_mandate_fee_rate_fund`、`ths_fund_manager_current_fund`、`ths_fund_supervisor_fund` |

## 16. 失败场景

以下失败必须明确标注发生阶段：

- 缺少 `.env` 或缺少 API Key
- embedding 调用失败
- 未识别到基金代码且名称解析失败
- ETF 名称解析多匹配
- ETF 名称解析无匹配
- 向量召回结果为空
- Qwen 返回非法 JSON
- 查询计划校验失败
- SSH 连接失败
- 远端 Mongo 查询失败
- 远端结果为空

例如：

```text
阶段：查询计划校验
错误：projection 包含未知字段 ths_unknown_field
```

校验失败用例至少覆盖：

- 未知 `collection`
- 未知 `projection` 字段
- `filter` 包含 `$ne`
- `filter` value 是对象
- `limit` 超过 20
- Qwen 返回非法 JSON
- Qwen 返回“中文说明 + fenced JSON”时必须能提取 JSON
- 修改 `ETF_AGENT_EMBEDDING_MODEL`、`ETF_AGENT_EMBEDDING_DIM` 或 `DASHSCOPE_BASE_URL` 后，索引缓存必须失效并重建
- Qwen 如果选择已知 array/object 字段，第一版校验层必须拒绝
- `candidate_ids=[]` 且 projection 包含非身份、非模板字段时必须拒绝
- `tb_ths_etf_report_quarter`、`tb_ths_etf_report_year` 在 v1 真实查询中必须拒绝
- 宽泛名称 `沪深300ETF的费率是多少` 必须返回候选，不进入 Qwen 查询计划生成

## 17. 后续 MCP 边界

实现时保留后续封装 MCP 的函数边界：

```python
semantic_query(question: str) -> dict
```

建议返回结构：

```json
{
  "question": "...",
  "entities": {},
  "retrieved_mappings": [],
  "query_plan": {},
  "result": {},
  "answer": "...",
  "debug": {
    "stages": [
      {
        "name": "entity_extraction",
        "status": "ok",
        "detail": {}
      }
    ]
  }
}
```

CLI 入口只负责读取命令行参数和打印结果，核心逻辑放在 `semantic_query()` 内，方便后续迁移成 MCP tool。
