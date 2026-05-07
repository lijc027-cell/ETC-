# ETF 语义查询 Agent

## Agent 工作规则

- 先确认目标和边界再动手；有多种解释或关键条件不清时，先说明假设并询问。
- 优先选择能满足需求的最简单实现，不做未要求的功能、抽象、配置化或防御性扩展。
- 修改要克制：只碰和任务直接相关的代码，保持现有风格；发现无关问题可以记录，不顺手重构或删除。
- 如果本次修改造成了未使用的 import、变量、函数或测试夹具，要一起清理；不要清理任务前已经存在的无关死代码。
- 每一处改动都应能对应到用户请求、项目边界或验证失败的修复。
- 多步骤任务先给简短计划，并为每步标明验证方式；bugfix 优先用测试或可复现命令确认问题，再修复并复验。
- 完成前运行与改动范围匹配的验证命令；无法运行时说明原因和剩余风险。

## 项目定位

自然语言问单只 ETF 的数据 → Qwen 生成查询计划 → 校验 → SSH 远端 Mongo 查询 → 本地模板化展示结果。

v1 只做单只 ETF 标量字段查询。不做搜索、筛选、对比、持仓、array/object 字段。

## 运行方式

```bash
.venv/bin/python etf_agent_demo.py "510300 盘子有多大"           # 完整链路
.venv/bin/python etf_agent_demo.py "510300 是什么" --dry-run     # 不调用 Qwen 和 SSH
.venv/bin/python etf_agent_demo.py "510300 盘子有多大" --verbose # 完整调试输出
.venv/bin/python etf_agent_demo.py "510300 盘子有多大" --answer-only # 只输出人话结果
```

## 架构

```
etf_agent_demo.py          — CLI 入口
etf_agent/
  pipeline.py              — semantic_query() 总编排
  config.py                — .env 加载
  dictionary.py            — data-dictionary.md 解析 → FieldMapping
  cache.py                 — embedding 索引缓存（按 hash+model+dim+base_url 签名）
  entities.py              — 正则提取 fundcode（6位数字）和 period
  retrieval.py             — 向量/词法检索字段候选
  candidates.py            — 关键词增强 + 向量候选合并去重
  llm.py                  — Qwen 生成查询计划 + deterministic_plan 兜底
  plan.py                 — 校验 + intent 模板补齐 + SQL-like 生成
  remote.py               — SSH 上传 query plan → 远端 runner 执行 Mongo 查询 → SFTP 取结果
  formatter.py            — answer_fields + Mongo 原始结果 → 人话文本
tests/
  test_core.py            — 单元测试
docs/
  etf-semantic-query-spec.md  — 技术方案 spec
references/
  data-dictionary.md      — 数据库字段定义
  api-reference.md        — 旧 SSH 执行方式（仅参考）
skill.md                  — 旧 skill 定义（不参与 v1）
```

## 核心链路

```text
用户问题
  → entities.py: 正则提取 fundcode + period
  → candidates.py: 关键词增强（如"盘子"→ths_fund_scale_fund）+ period 增强
  → retrieval.py: 向量检索 top_k 候选
  → candidates.py: 增强在前 + 向量在后，按 collection.field 去重合并
  → llm.py: Qwen 生成 {intent, collection, filter, projection, answer_fields, limit}
    如果 Qwen 返回非法 JSON 或 schema 不对 → deterministic_plan 兜底
  → plan.py: validate_query_plan → 校验 + intent 模板补齐
  → remote.py: SFTP 上传 plan JSON → SSH exec_command 执行远端 Python runner → SFTP 读结果
  → formatter.py: answer_fields + result → 人话文本
```

## v1 支持范围

| intent | 触发词 |
|--------|-------|
| basic_info | 是什么、介绍、基本信息、概况 |
| fund_scale | 盘子、规模、多大、资产规模 |
| tracking_index | 跟踪、指数、标的指数 |
| fee | 管理费、托管费、费率、贵不贵 |
| manager | 基金经理、谁在管、管理人 |
| performance | 表现、收益率、涨跌、赚了、回报 |
| dividend | 分红、分红记录、分红情况 |

不支持：持仓、搜索、筛选、对比、季报/年报、array/object 字段、实时行情。

## 项目进度

### 已完成

- [x] spec 定稿（`docs/etf-semantic-query-spec.md`）
- [x] 全部模块代码实现
- [x] 单元测试 72 条（`tests/test_core.py`）
- [x] 远端 SSH + Mongo 查询跑通
- [x] 12 条 v1 验收问题的 dry-run 测试通过
- [x] intent 漂移归一：收益率、manager、dividend 相关 Qwen intent 变体
- [x] period 补齐：今年、2y、3y、5y、各周期
- [x] 分红字段增强和空查询结果格式化
- [x] 3 条端到端测试通过：`510300是什么`、`510500基本信息`、`159919跟踪指数`

### 当前断点（待修，按优先级排）

- [ ] **P2 — 名称解析边界** — 仓库已有 dry-run 名称解析，但本轮不继续扩展为 v1 必要能力
- [ ] **P2 — 多意图组合扩展** — 仍只维持 v1 的单只 ETF 标量查询边界

### 不做（v1 明确排除）

名称反查、持仓/行业/概念、搜索/筛选、多只对比、季报/年报数据、array/object 字段展开、实时行情。

## 当前状态：12/12 dry-run 验收通过

最后一次测试日期：2026-05-07。

### dry-run 验收通过的 12 条

```
510300是什么
帮我查一下510500的基本信息
159919这只基金跟踪什么指数
510300今年的收益率是多少
159919近1年收益，同类排名第几
510500成立以来收益怎么样
帮我查510300各周期的收益率
510300的基金经理是谁
510300有没有分红记录
159919的分红情况
000001有这只ETF吗
510300近一周收益
```

### 验收命令

```bash
.venv/bin/python -m pytest tests/test_core.py -q
```

当前结果：`72 passed in 0.09s`。

## 远端环境

- SSH: [ETF_SSH_USER]@[ETF_SSH_HOST]
- Python: [ETF_REMOTE_PYTHON]
- MongoDB: [ETF_REMOTE_MONGO_URI], db: [ETF_REMOTE_DB]
- 集合: tb_ths_etf_base, tb_ths_etf_report_quarter, tb_ths_etf_report_year
- 密码和 API Key 在本地 `.env`，不要提交

## 开发命令

```bash
# 跑测试
.venv/bin/python -m pytest tests/ -v

# 跑端到端
.venv/bin/python etf_agent_demo.py "510300是什么"

# 单文件验证
.venv/bin/python -c "from etf_agent.pipeline import semantic_query; print(semantic_query('510300是什么', dry_run=True))"
```
