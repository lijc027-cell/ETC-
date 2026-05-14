# ETF 语义查询 Agent

## Agent 工作规则

- 先确认目标和边界再动手；有多种解释或关键条件不清时，先说明假设并询问。
- 讨论技术方案时优先说人话：先把问题、取舍和结论讲清楚，避免只堆术语。给出正式 plan、最终技术意见、或交付给技术团队的成品时，可以改用效率最高的技术表达。
- 优先选择能满足需求的最简单实现，不做未要求的功能、抽象、配置化或防御性扩展。
- 修改要克制：只碰和任务直接相关的代码，保持现有风格；发现无关问题可以记录，不顺手重构或删除。
- 如果本次修改造成了未使用的 import、变量、函数或测试夹具，要一起清理；不要清理任务前已经存在的无关死代码。
- 每一处改动都应能对应到用户请求、项目边界或验证失败的修复。
- 多步骤任务先给简短计划，并为每步标明验证方式；bugfix 优先用测试或可复现命令确认问题，再修复并复验。
- 完成前运行与改动范围匹配的验证命令；无法运行时说明原因和剩余风险。

## 项目定位

### 最高项目架构标准

本项目的最高标准是：

> 我明确我的基本标准，我要实现的是语义输入并查询，不是通过预封装函数执行，要的是 text2sql 查询。

所有后续实现、评审和验收都必须服从这条标准。也就是说，用户自然语言必须被转换为受限查询 AST，经 validator 校验、compiler 编译后再查询 MongoDB；不能把用户问题路由到预封装业务函数、intent if/else 模板、固定字段拼装器或 deterministic fallback 后算作 text2sql 成功。

允许本地代码做的事情是：识别 deny/unsupported/clarify 边界、抽取实体和证据、裁剪能力范围、校验 AST、安全归一、物理编译、只读执行和格式化。用户请求的查询语义字段、条件、排序、period、sub-intent 和 limit 必须来自 AST draft，并能被 provenance diff 审计。

**当前方向：text2sql**，中间形态选用 SQL AST（结构化 JSON）。Qwen 生成 AST → 本地校验 → 编译成 Mongo 查询 → 远端执行 → 模板化输出。不生成 SQL 字符串，不引入 SQL parser。

v1（已完成）跑通了单只 ETF 标量查询链路：`自然语言 → Qwen 查询计划 → 校验 → SSH 远端 Mongo 查询 → 模板化输出`。v1 的字段字典、枚举值映射、安全白名单、结果格式化等资产继承到 text2sql 阶段。

v2（`docs/etf-semantic-query-spec-v2.md`）已归档不实施。

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
| fee_and_manager | 费率和基金经理（组合 intent） |

不支持：持仓、搜索、筛选、对比、季报/年报、array/object 字段、实时行情。

## 项目进度

### 已完成

- [x] spec 定稿（`docs/etf-semantic-query-spec.md`）
- [x] 全部模块代码实现
- [x] 单元测试 72 条（`tests/test_core.py`）
- [x] 远端 SSH + Mongo 查询跑通
- [x] 13 条 v1 验收问题的 dry-run 测试通过（共 38 条覆盖测试，25 条明确排除）
- [x] intent 漂移归一：收益率、manager、dividend 相关 Qwen intent 变体
- [x] period 补齐：今年、2y、3y、5y、各周期
- [x] 分红字段增强和空查询结果格式化
- [x] 3 条端到端测试通过：`510300是什么`、`510500基本信息`、`159919跟踪指数`

### v1 收尾 / text2sql 起步

- [ ] v1 资产梳理：字段字典、枚举值、安全白名单、formatter 模板、测试集
- [ ] text2sql 方案设计：SQL 方言、安全边界、执行方式
- [ ] text2sql 原型跑通第一条真实链路

### 不做（v1 明确排除，v2 已归档）

名称反查、持仓/行业/概念、搜索/筛选、多只对比、季报/年报数据、array/object 字段展开、实时行情。

## 当前状态

**v1 已完成，转向 text2sql 方向。** 13 条已解决 / 38 条覆盖测试，最后一次测试日期：2026-05-07。完整覆盖清单见 `test-questions-solved-answers.md`。v2 spec 已归档（`docs/etf-semantic-query-spec-v2.md`），不进入实施。

### dry-run 验收通过的 13 条

```
510300是什么                       — basic_info
帮我查一下510500的基本信息            — basic_info
159919这只基金跟踪什么指数            — tracking_index
工银沪深300ETF的费率和基金经理是什么    — fee_and_manager（名称解析 + 组合 intent）
510300今年的收益率是多少              — performance (ytd)
159919近1年收益，同类排名第几          — performance (1y)
510500成立以来收益怎么样              — performance (std)
帮我查510300各周期的收益率            — performance (all periods)
510300的基金经理是谁                 — manager
510300有没有分红记录                 — dividend
159919的分红情况                    — dividend
000001有这只ETF吗                   — basic_info (不存在)
510300近一周收益                    — performance (1w)
```

### 未解决（25 条，v1 明确排除）

| 类别 | 数量 | 原因 |
|------|------|------|
| 持仓信息 | 4 | array/object 字段展开 |
| 搜索 ETF | 5 | 名称搜索、列表查询 |
| 条件筛选 | 6 | 排序、Top N、范围条件 |
| 多只对比 | 3 | 多 ETF 对比 |
| 基金经理深度 | 2 | 任期计算、历史业绩 |
| 混合场景 | 3 | 多意图组合 |
| 边界/异常 | 2 | 实时行情、名称搜索 |

### 验收命令

```bash
.venv/bin/python -m pytest tests/test_core.py -q
```

当前结果：`72 passed in 0.09s`。

## 远端环境

- SSH: <ETF_SSH_USER>@<ETF_SSH_HOST>
- Python: <ETF_REMOTE_PYTHON>
- MongoDB: <ETF_REMOTE_MONGO_URI>, db: <ETF_REMOTE_DB>
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
