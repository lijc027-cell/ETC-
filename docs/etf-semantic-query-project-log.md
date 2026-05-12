# ETF 语义查询 Agent 项目日志

## 项目背景

基于已有远端 ETF Mongo 数据库和 `references/data-dictionary.md` 字段映射文档，规划一个本地 v1 语义查询 Agent 原型。

目标链路：

```text
自然语言问题 -> 字段语义匹配 -> Qwen 查询计划 -> 本地安全校验 -> SSH 远端 Mongo 查询 -> 模板化结果输出
```

第一版不接入原有 FastAPI 项目，不封装 MCP，只在本地 CLI 跑通。

## 当前项目状态

项目已从 v2 语义编排方向转向 text2sql 主线。v2 spec（`docs/etf-semantic-query-spec-v2.md`）已归档。

目标链路：

```text
自然语言问题 -> Qwen 生成 SQL AST(JSON) -> 本地安全校验 -> 编译成 Mongo 查询 -> 远端执行 -> 模板化结果输出
```

text2sql 中间形态选择 **SQL AST（结构化 JSON）而非 SQL 字符串**。原因：

- v1 已验证"模型出 JSON 计划 → 本地校验 → 编译执行"链路稳定可用，text2sql 阶段是升级 AST 节点能力而不是换范式
- 目标库是 MongoDB，SQL 字符串无直接执行价值，多一层 SQL parser 只会引入方言兼容和注入风险
- AST 层面的安全校验（字段白名单、值域检查、运算符控制）比 SQL 字符串层面简单且可测
- 调试用的 SQL-lookalike 文本由本地根据已校验 AST 机械生成，不依赖 Qwen 输出

从 v1 继承到 text2sql 的资产：

- 字段字典解析（`references/data-dictionary.md`）
- 真实枚举值和口语映射
- ETF 名称解析与歧义处理（`name_resolver.py`）
- 安全白名单、单位阈值、值域约束（`plan.py` 校验层）
- 结果格式化（`formatter.py`）
- 测试问题集与验收样例（`test-questions.md`，38 条）
- 远端数据连接和配置管理（`remote.py`、`.env`）

v2 中保留参考价值的部分：

- 标准化指数名册、分类字段枚举值
- Filter/Sort 字段白名单和值域阈值
- 口语到数据库值的映射规则
- 测试用例中未解决问题的分类

不再继续投入：

- `search` / `filter` / `compare` 的本地预封装执行骨架
- 基于本地 catalog 的业务分流
- 面向 v2 的 pipeline 语义
- v2 的 catalog 快照与签名机制

## v3 Text2SQL Spec 决策与 Review 记录

本轮 v3 规格打磨的目标不是为 `test-questions.md` 写死答案，而是把 ETF 查询能力收敛成可执行、可校验、可分阶段验收的 Text-to-Query AST 运行时。当前权威文档为：

- `docs/etf-semantic-query-spec-v3.md`
- `docs/v3-coverage-matrix.md`

### 1. v3 runtime 必须脱离 v1 执行链路

问题：

早期 `--v3` 入口仍然包着 v1 pipeline：`semantic_query_v3()` 内部复用 `semantic_query()`，导致 v3 问题最终被 v1 `validate_query_plan()` 校验，出现：

```text
v1 暂不支持 intent rank
v1 暂不支持 intent fund_rank
v1 暂不支持 intent fund_existence_check
```

结论：

- 这不是用户跑错了 v1 命令，而是 v3 外壳下面还复用了 v1 执行/校验层。
- v3 运行时必须按独立链路实现：

```text
classification -> AST -> v3 validator -> v3 compiler -> remote readonly query -> v3 formatter
```

- v1 代码可以作为字段、模板、回归行为参考，但 v3 AST 不能再交给 v1 validator 判断。
- deny / unsupported / clarify 需要在 AST 前置阶段直接返回，不能进入 v1 pipeline。

### 2. Hard / Strategy / Test 三层分离

问题：

如果 spec 为了完美匹配固定测试句，把触发词、默认排序、固定列、覆盖矩阵全部写成硬协议，上线后会变成“测试可过、生产泛化差”的系统。

结论：

- Hard 层：AST schema、集合/字段/操作符白名单、deny、禁止可执行 SQL/PyMongo、AST 不暴露 OR、compiler 安全边界。
- Strategy 层：触发词种子、deny 关键词、搜索泛词、默认 limit、默认排序、compare 默认列。
- Test 层：coverage matrix、golden、smoke 和 v1 回归基线。
- 覆盖矩阵只用于验收和回归，不是生产问法全集，也不是路由权威。
- 触发词表是 canonical seed list，不是穷举协议；配置可以增量扩展同义词，但不能把核心 seed list 从 spec 中挪空。

### 3. Intent Recognition 成为 AST 前置权威

问题：

仅依赖 LLM 自由输出 intent，会出现 intent 漂移、from 漂移、query_mode 与 output_style 冲突。

结论：

- `recognized_query_mode` 由本地前置识别产生，不由 LLM 输出，也不属于 AST 字段。
- LLM 接收并只能服从以下约束上下文：

```text
recognized_query_mode
intent_candidates
from_candidates
entity_hints
```

- LLM 只能在 `intent_candidates` 和 `from_candidates` 内选择，不能扩大候选范围。
- 多候选时，LLM 根据用户原文做语义消歧；无法判断时返回 unsupported 或 clarify。
- `entity_hints` 需要结构化，承载 fundcode、名称候选、period、报告期、搜索关键词、筛选条件、排序条件等前置解析结果。
- `entity_hints.search_keyword` 优先级高于 AST 中 `__search_text__` 的 value，避免 LLM 把整句问题当搜索词。

### 4. Non-AST 路由结果统一

问题：

`DeniedQuery`、`UnsupportedQuery`、`ClarificationRequired` 分散在 spec 中，容易导致不同入口各写一套失败处理。

结论：

- 三类结果都不生成 AST、不进入 compiler、不访问远端 Mongo。
- `DeniedQuery`：实时行情、交易指标、技术分析、投资建议、个股分析等明确拒绝。
- `UnsupportedQuery`：无法归类、阶段未开放、远端验证未通过、超出 ETF v3 领域。
- `ClarificationRequired`：可归类但条件不足，例如名称歧义、候选过多、搜索关键词无效。
- `ClarificationRequired.options` 必须是对象数组，不能只是展示字符串；至少包含 `id`、`kind`、`label`、`value`、`fundcode`、`thscode`、`reason`，避免用户选择后再次模糊回绑。

### 5. 阶段白名单是当前版本能力边界

问题：

全版本 Query Classification Matrix 列出了 `manager_detail`、`investment_profile`、`report_*` 等 intent，但 v3.0 / v3.1 并不开放这些能力，容易造成 scope creep。

结论：

- Section 3 阶段白名单是当前阶段唯一权威可用集。
- Section 4 矩阵只定义全集映射；和阶段白名单冲突时，以阶段白名单为准。
- v3.0：`basic_info`、`fund_scale`、`tracking_index`、`performance`、`fee`、`manager`、`fee_and_manager`、`dividend`。
- v3.1：在 v3.0 基础上增加 `search`、`filter`、`compare`。
- v3.2：增加 `manager_detail`、`investment_profile`、`subscription_redemption`、`linked_fund`。
- v3.3：report intent 只有在 `verification_passed=true` 后才开放。
- blocked intent 回退规则：
  - `manager_detail -> manager`，保留 single query mode，只少返回详情字段。
  - `investment_profile`、`subscription_redemption`、`linked_fund`、`report_*` 在未开放阶段返回 `UnsupportedQuery`，不偷偷降级成 base AST。

### 6. search / filter 边界收紧

问题：

“找”“帮我找”既可能是搜索，也可能只是口语前缀；“找规模大于 10 亿的 ETF”同时命中 search 和 filter，如果没有 tiebreaker，LLM 可能误选 search。

结论：

- `contains` 使用虚拟字段 `__search_text__`，compiler 内部展开为受控多字段 OR。
- 搜索字段只限基金简称、跟踪指数名称、跟踪指数代码。
- LLM 负责抽取搜索关键词；本地做二次清洗和长度检查。
- search/filter 同优先级冲突时，确定性结构优先：
  - 数值比较 `gt/gte/lt/lte`
  - “前 N”
  - “最高/最低/最大/最小”
  - 分类词，如股票型、债券型、上交所、深交所
- 有 fundcode 或唯一名称，并且问题包含费率、规模、收益、经理等非 search intent 时，“帮我找/找一下”不触发 search。
- 跟踪指数筛选不应因“沪深300指数”不在枚举表中退化为 search；应本地先精确匹配指数代码，再模糊匹配指数名称，匹配成功后生成 filter。

### 7. Composite 两步编排规则

问题：

“先搜再查”“筛选后对比”“找费率最低的沪深300ETF再看基本信息和收益”不能靠单 AST 覆盖，但如果无限拆步又会回到 v2 pipeline。

结论：

- composite 最多 2 步。
- Step 1 默认 limit 由 orchestrator 控制，默认 10；显式 top-k 使用 `min(k, 10)`。
- Step 1 空结果时停止，返回未找到候选。
- search/filter -> single detail：
  - 1 条候选自动进入 Step 2。
  - 2 条以上默认选规模最大的 1 条，并在答案中说明“自动选择规模最大的基金”。
  - 用户显式要求全部、每只或对比时，按 compare / list 规则处理。
- Step 2 如果是同集合 single detail，可以在主 intent 外附带可展示辅助字段；例如 intent=`performance`，`answer_fields` 同时展示 fundcode、简称、跟踪指数，不视为通用多 intent merge。
- 最终输出顺序：Step 2 已包含上下文时只展示 Step 2；否则先展示 Step 1 简要候选依据，再展示 Step 2。

### 8. v3.3 report gate 与降级边界

问题：

`latest`、`type_num`、年报 array 字段、年报证券名称字段、`rank_num` 对齐等语义如果未远端验证就开放，会直接影响报告展开准确率。

结论：

- v3.3 不等于 report 自动开放。
- `report_*` 进入 `intent_candidates` 的前提是对应远端验证项通过。
- 未验证或 blocked report 返回 `UnsupportedQuery(reason=blocked_by_verification)`。
- blocked report 不允许静默降级为 base 查询。
- 只有 composite 中 base 子步骤本身可执行时，才允许先展示 base 结果，并明确标注 report 部分因结构未验证或能力未开放无法回答。
- expand 字段在已开放 report 文档中缺失或为 null 时，降级展示 fundcode + 报告期基础信息，并说明该报告期暂无对应数据。

### 9. 字段能力矩阵与 formatter 基线

问题：

能力矩阵如果把身份字段、交易字段、金额字段标错，会直接破坏安全边界或展示质量。

结论：

- `fundcode` / `thscode` 只能作为 `filterable_eq` / `in` 身份字段，不应标成 `filterable_compare`。
- 交易类指标字段可以保留在数据字典中，但不能进入 v3 能力矩阵的 selectable/filterable/sortable。
- 分红金额字段必须使用 `amount` format，按元转亿元展示，避免科学计数法。
- `answer_fields` 控制字段展示顺序和格式，compiler projection 独立生成，不能回写污染 AST。
- compare v3.1 默认 8 列是默认模板，不是永久协议；后续可在白名单内扩展。
- v1 13 条回归 answer shape 是测试基线，不要求 formatter 在生产代码里识别“v1 问题”；未来 formatter 升级时同步更新 golden baseline。

### 10. 测试覆盖与泛化验收

问题：

38 条测试问题能覆盖阶段验收，但不能代表生产端全部问法。

结论：

- `docs/v3-coverage-matrix.md` 映射 38 条测试问题到 phase / query mode / intent / outcome。
- smoke 必须覆盖基础、搜索、筛选、显式 compare、空结果、拒绝类、contains 安全。
- golden 需要记录 expected intent recognition result、AST、Mongo params、answer shape、answer value policy。
- v3.1+ 增加 paraphrase set 和 template fuzz set，用于验证同义改写和真实生产问法泛化。
- 准确率验收拆成四层：
  - Intent / AST 准确
  - Mongo params 准确
  - Answer shape 准确
  - Answer value 或格式策略准确

## 问题与方案记录

### 1. 自然语言和数据库字段映射复杂

问题：

用户表达和数据库字段差异较大，例如：

```text
盘子有多大 -> ths_fund_scale_fund
跟踪什么指数 -> ths_name_of_tracking_index_fund
近一年表现 -> ths_yeild_1y_fund
```

方案：

- 将 `data-dictionary.md` 作为字段映射来源。
- 解析集合名、字段名、中文名、类型、说明、分组。
- 为每个字段构造 `search_text`。
- 使用 Qwen embedding 对字段映射做向量检索。

效果：

- 将自然语言问题转换为候选字段召回问题。
- v1 规划覆盖 6 类 ETF 高频查询 intent。

### 2. 纯向量检索不稳定

问题：

只依赖向量检索可能漏掉关键字段，例如“近一年表现”可能召回收益率字段，但漏掉同类排名和 ETF 排名字段。

方案：

- 设计“规则兜底 + aliases 增强 + 向量泛化”的混合匹配方案。
- 对高频 intent 增加确定性候选增强。
- 对 `period` 做规则映射，例如 `近一年 -> 1y`。
- 增加 intent 模板补齐：Qwen 漏字段时，本地自动补齐必要 projection。

效果：

- v1 的 5 个验收问题均有明确必须字段。
- 高频场景不完全依赖 embedding 排名。
- 不需要因漏字段反复重试 Qwen。

### 3. Qwen 输出容易漂移

问题：

如果让 Qwen 同时生成查询计划、SQL-like、答案和解释，会引入多处不确定性。

方案：

- Qwen 只负责生成结构化查询计划。
- 禁止 Qwen 输出 `answer`、`analysis`、`summary`、`recommendation`、`sql_like`。
- 查询计划固定为 JSON schema：
  - `intent`
  - `collection`
  - `filter`
  - `projection`
  - `limit`
  - `answer_fields`
- SQL-like 调试语句由本地根据已校验计划机械生成。

效果：

- 模型不参与最终答案生成。
- 模型不参与真实查询执行。
- 避免调试 SQL-like 和真实 Mongo 查询计划不一致。

### 4. 远端数据库查询存在安全风险

问题：

如果把 Qwen 输出直接拼到远端命令或 Python 代码里，存在注入风险。

方案：

- 查询计划先在本地做 schema 和安全校验。
- 禁止 Mongo operator，例如 `$ne`、`$where`、`$regex`、`$gt`、`$lt`、`$in`。
- `filter` 第一版只允许 `fundcode` / `thscode` 等值查询。
- 本地通过 SFTP 上传已校验 query plan JSON。
- 远端执行固定 Python runner 模板。
- runner 禁止 `eval()` 和 `exec()`。
- 使用 UUID 临时文件，避免并发覆盖。

效果：

- 查询链路限制为只读 `find_one/find`。
- 禁止写入、更新、删除和任意代码执行。
- 查询计划和 shell 命令分离，降低注入风险。

### 5. 新方案和旧 skill 容易混淆

问题：

旧 `skill.md` 描述的是调用远端 `[ETF_REMOTE_SCRIPT]` 的查询方式；新方案是本地生成查询计划后直查 Mongo。

方案：

- 在 spec 中明确两套方案关系。
- v1 以新 spec 为准。
- 不调用 `[ETF_REMOTE_SCRIPT]`。
- `api-reference.md` 只作为远端环境背景参考。

效果：

- 实现边界更清晰。
- 避免工程实现回到旧脚本调用方式。

### 6. 最终结果不交给模型自由生成

问题：

如果让 Qwen 基于查询结果生成最终答案，可能出现自由解释、投资判断或扩展分析。

方案：

- 设计本地 `ResultFormatter`。
- 只基于 `answer_fields` 和 Mongo 原始结果输出字段名和值。
- 金额字段按元转亿元。
- 百分比字段直接追加 `%`。
- null、缺失字段、空字符串统一展示为 `暂无数据`。
- 不做投资判断、归因分析、风险扩展。

效果：

- 输出结果可控、可复现。
- 模型不参与最终结论生成。
- 将 LLM 不确定性限制在字段选择阶段。

## v1 支持范围

v1 仅支持单只 ETF 的标量字段查询。

| intent | 能力 |
| --- | --- |
| `basic_info` | 基本信息、是什么、介绍 |
| `fund_scale` | 基金规模、盘子多大 |
| `tracking_index` | 跟踪指数、标的指数 |
| `performance` | 收益率、表现、涨跌、回报 |
| `fee` | 管理费、托管费、费率 |
| `manager` | 基金经理、管理人 |

暂不支持：

- 持仓、行业、概念
- 对比、搜索、筛选
- 季报/年报数据查询
- ETF 名称反查代码
- array/object 字段展开
- 多只 ETF 或多意图复杂组合

## 量化记录

- 支持 6 类 ETF 高频查询 intent。
- 覆盖 5 个 v1 验收问题。
- 解析 3 个 Mongo 集合的数据字典字段。
- 使用 1024 维 Qwen embedding 向量索引。
- 查询计划固定为 6 个核心字段的 JSON schema。
- 禁止 6 类以上高风险 Mongo operator。
- 第一版查询执行限制为只读 `find_one/find`。

## 实现后代码 Review 记录

### Review 背景

完成 v1 原型代码后，对实现进行代码审查，重点检查：

- 是否符合 spec 的 v1 边界
- 查询计划校验是否严格
- intent 模板补齐是否按预期工作
- SSH 远端执行是否安全
- 测试命令和 CLI 验收问题是否可运行

### 1. intent 模板补齐后仍可能被候选字段白名单拒绝

问题：

spec 要求高频 intent 缺少必要字段时，本地自动补齐，不拒绝、不重试。但实现中 `validate_query_plan()` 先补齐 projection，再校验字段是否在 `candidate_ids` 中。这样如果 Qwen 没有选中收益率字段，校验层补齐后仍可能因为“不在候选字段范围内”而拒绝。

复现：

```text
intent = performance
projection = ["fundcode"]
candidate_ids = ["tb_ths_etf_base.fundcode"]
```

校验层补齐：

```text
ths_yeild_1y_fund
ths_yeild_rank_1y_fund_origin
ths_yeild_rank_1y_etf
```

随后被候选字段白名单拒绝。

建议：

- 将 intent 模板补齐字段加入允许字段集合。
- 或在校验层区分“Qwen 选择字段”和“本地模板补齐字段”。

预期效果：

- 保证“模板补齐自动兜底”的设计真正生效。
- 避免高频 intent 因 Qwen 漏字段而失败。

### 2. v1 支持范围没有被校验层完全限制

问题：

spec 明确 v1 暂不支持季报/年报、持仓、行业、概念等复杂查询。但当前校验层只检查 collection 是否存在于数据字典，没有限制为 `tb_ths_etf_base` 或 6 个 v1 intent。

复现：

```text
intent = unknown
collection = tb_ths_etf_report_year
projection = ["fundcode", "year_num"]
```

该计划可以通过校验，和 v1 范围不一致。

建议：

- v1 阶段限制 `collection == "tb_ths_etf_base"`。
- 限制 `intent` 只能是：
  - `basic_info`
  - `fund_scale`
  - `tracking_index`
  - `performance`
  - `fee`
  - `manager`
- 如果后续要支持 `unknown`，应只用于调试，不进入真实远端查询。

预期效果：

- 防止 Qwen 绕进季报/年报集合。
- 保持 v1 单只 ETF 标量字段查询边界清晰。

### 3. embedding batch size 与 spec 不一致

问题：

spec 中写默认 `batch_size=32`，实现中 `EMBEDDING_BATCH_SIZE = 10`，测试也锁定为 10。

建议：

- 二选一保持一致：
  - 如果 10 是基于 DashScope 限制或稳定性考虑，应把 spec 改成 10。
  - 如果没有限制，则把实现改成 32。

预期效果：

- 避免 spec/code drift。
- 后续排查 embedding 调用问题时口径一致。

### 4. 测试运行方式

发现：

直接运行：

```bash
.venv/bin/pytest -q
```

会因为 `ModuleNotFoundError: No module named 'etf_agent'` 失败。

README 中的命令可以通过：

```bash
.venv/bin/python -m pytest tests/test_core.py -q
```

验证结果：

```text
21 passed
```

建议：

- 保留 README 当前测试命令。
- 或后续增加包安装配置，让 `.venv/bin/pytest -q` 也可直接运行。

### 5. v1 dry-run 验收结果

已验证 5 个 dry-run 问题均可输出模板化结果：

```text
510300 是什么
510300 盘子有多大
510300 跟踪什么指数
510300 近一年表现怎么样
510300 的管理费和托管费是多少
```

验证结果示例：

```text
510300 的基金规模为 123.46 亿元。
510300 的跟踪指数代码为 000300，跟踪指数名称为 沪深300指数。
510300 的近1年收益率为 8.88%，近1年同类排名为 100/500，近1年 ETF 排名为 12。
```

效果：

- CLI dry-run 链路已可演示完整流程。
- 单元测试覆盖核心解析、候选增强、计划校验、格式化和缓存签名。
- 仍需修正上述 3 个 review 问题后，再进入更稳定的真实远端查询验收。

## 可用于简历的表述

设计 ETF 语义查询 Agent v1 原型，基于 Qwen embedding 和字段映射文档实现自然语言到 Mongo 查询计划的语义匹配，覆盖 6 类 ETF 高频查询意图和 5 个验收问题；通过规则增强、intent 模板补齐、严格 JSON schema 校验、Mongo operator 禁止策略和 SSH/SFTP 只读执行链路，将 LLM 不确定性限制在字段选择阶段，实现安全、可复现的远端 ETF 数据查询与模板化输出。

## 实现迭代与问题修复记录

### 1. 依赖安装不能污染 base 环境

问题：

初次准备连接真实远端数据库时，尝试用系统 `python3 -m pip install paramiko` 安装依赖。用户明确要求不要安装到 base 环境。

处理：

- 在项目目录创建 `.venv`。
- 后续依赖安装和运行统一使用：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python etf_agent_demo.py "510300 盘子有多大"
```

- README 中同步改为 `.venv/bin/python` 运行方式。

效果：

- 项目依赖隔离在 `/Users/l/Downloads/laiqian/etf-query/.venv`。
- 不再污染 base Python 环境。
- 本地演示命令更稳定、可复现。

### 2. 真实远端查询链路接入

问题：

dry-run 能跑通，但用户要求必须连接远端 Mongo，用真实数据库信息回答。

处理：

- `.env` 中配置 DashScope API Key、SSH host/user/password、远端 Python、Mongo URI 和 DB。
- 真实链路使用：
  - DashScope embedding 做字段召回。
  - Qwen 生成查询计划。
  - 本地校验查询计划。
  - SSH/SFTP 上传固定 runner 和 query plan。
  - 远端 runner 只读查询 Mongo。

遇到的问题与修复：

- DashScope `text-embedding-v3` compatible mode 拒绝 batch size 大于 10。
- 将 `EMBEDDING_BATCH_SIZE` 从 spec 初始设想的 32 调整为 10。
- spec 同步修改为 `batch_size=10`，说明是实测 DashScope 限制。

效果：

真实命令已跑通：

```bash
.venv/bin/python etf_agent_demo.py "510300 盘子有多大"
```

真实回答示例：

```text
510300 的基金规模为 1842.65 亿元（2026-05-05）。
```

### 3. 远端真实字段是时间序列数组

问题：

spec 假设 v1 查询的是标量字段，但真实 Mongo 中 `ths_fund_scale_fund` 返回的是时间序列数组：

```json
[
  {"value": 184264546935.87, "btime": "2026-05-05"}
]
```

原 formatter 直接 `float(value)`，遇到 list 报错：

```text
float() argument must be a string or a real number, not 'list'
```

处理：

- `ResultFormatter` 支持 `[{value, btime}]` 形态。
- 对时间序列字段取最新 `btime` 的 `value`。
- 人话回答中追加日期，例如：

```text
1842.65 亿元（2026-05-05）
```

效果：

- 保留远端原始 JSON 作为调试证据。
- 最终回答仍是简短确定性人话。
- 兼容真实库中“标量字段实际以时间序列存储”的情况。

### 4. CLI 输出人话被长 JSON 淹没

问题：

初版 CLI 默认先输出完整调试链路和远端原始 JSON。规模字段原始数组很长，导致用户认为“只回了 JSON，没有人话部分”。

处理：

- CLI 默认输出顺序改为：

```text
用户问题
最终简短回答
关键查询信息
```

- 完整调试链路和远端原始 JSON 改为 `--verbose` 才输出。
- 新增 `--answer-only`，只输出最终人话回答。

效果：

普通演示命令：

```bash
.venv/bin/python etf_agent_demo.py "510300 近一年表现怎么样"
```

输出：

```text
最终简短回答
510300 的近1年收益率为 31.43%，近1年同类排名为 6916/22987，近1年 ETF 排名为 583。
```

### 5. Qwen intent 漂移与 schema 漂移

问题：

真实 Qwen 输出中出现了若干非 spec intent 或 schema 变体：

- `fund_performance`
- `fund_fee`
- `track_index`
- `fund_fee_and_manager`
- 顶层多出 `format`
- `answer_fields` 偶尔不是 object 数组

处理：

- 增加 intent alias 归一化：
  - `fund_performance -> performance`
  - `fund_fee -> fee`
  - `track_index -> tracking_index`
  - `fund_fee_and_manager -> fee_and_manager`
- `is_plan_schema_like()` 改为只做必要字段和基本类型预检。
- 额外字段由正式 `validate_query_plan()` 拒绝。
- schema 不像合法查询计划时，才进入确定性 fallback。

效果：

- 常见 Qwen 命名漂移不再导致 v1 正常查询失败。
- 仍保持严格校验：未知顶层字段、未知字段、未知集合、危险 filter 不能进入远端查询。

### 6. intent 模板补齐与候选字段白名单冲突

问题：

校验层先按 intent 自动补齐 projection，再要求 projection 必须来自候选字段。这样会导致模板补齐字段被候选白名单拒绝，违背 spec 中“不因缺少模板字段而拒绝”的设计。

处理：

- 将本地模板字段加入允许字段集合。
- 区分：
  - Qwen 自己选择的字段。
  - 本地 intent 模板补齐字段。
  - v1 高频模板中本来允许的字段。

效果：

例如 `performance` 计划即使 Qwen 只给了 `fundcode`，校验层也可以补齐：

```text
ths_yeild_1y_fund
ths_yeild_rank_1y_fund_origin
ths_yeild_rank_1y_etf
```

并允许通过后续字段校验。

### 7. v1 范围收紧

问题：

早期校验只检查 collection 是否存在于数据字典，导致 Qwen 可能绕进 `tb_ths_etf_report_year` 或 `tb_ths_etf_report_quarter`，与 v1 “只支持单只 ETF 标量字段查询”的边界不一致。

处理：

- v1 校验层限制：
  - `collection == "tb_ths_etf_base"`
  - intent 必须属于 v1 支持集合。
- 季报、年报、持仓、行业、概念等 array/object 查询明确拒绝。

效果：

命令：

```bash
.venv/bin/python etf_agent_demo.py "510300 最新年报的前十大重仓股"
```

返回：

```text
v1 暂不支持 intent unsupported
```

不会进入 Qwen 计划执行或远端年报数组查询。

### 8. remote runner 错误处理与临时文件清理

问题：

早期 runner 没有 try/except，远端 Mongo 不可达或查询异常时，runner 可能崩溃不写结果文件，本地只能看到泛化的 SSH 失败信息。

处理：

- runner 内部捕获异常，写入：

```json
{"success": false, "error": "...", "traceback": "..."}
```

- 本地读取结果后，如果 `success=false`，明确报：

```text
阶段：远端 Mongo 查询
错误：远端 Mongo 查询失败
```

- 远端临时文件清理失败时打印 warning。

效果：

- 远端 Mongo 异常和 SSH 连接异常更容易区分。
- 符合 spec 中“临时文件删除失败时记录 warning”的要求。

### 9. `_strip_markdown` 对 Qwen 常见输出不鲁棒

问题：

早期 JSON 提取只支持整个字符串都是 fenced code block：

```text
```json
{...}
```
```

如果 Qwen 输出：

```text
好的，这是查询计划：
```json
{...}
```
```

就会解析失败。

处理：

- 从 `re.match("^...$")` 改为 `re.search(...)`。
- 支持从“中文说明 + JSON 代码块”中提取 JSON。

效果：

- 降低 Qwen 格式轻微漂移导致 fallback 或失败的概率。

### 10. candidate_ids 为空时存在校验空洞

问题：

早期 `_validate_fields()` 中把 `candidate_ids` 作为 if 条件的一部分。若 `candidate_ids=[]`，非模板、非身份字段可能绕过候选校验。

处理：

- 当 `candidate_ids` 为空时，显式检查 projection 中是否存在非身份、非模板字段。
- 若存在则拒绝：

```text
候选字段为空，projection 包含非模板字段 ...
```

效果：

- 候选召回异常时不会无条件放行任意字段。
- 防止未来改动破坏“projection 原则上来自候选字段”的安全边界。

### 11. `.env` 凭据暴露风险

问题：

本地 `.env` 包含真实 SSH 密码和 DashScope API Key，审查时已被读取并在对话中暴露。

处理：

- 确认当前目录不是 git 仓库，因此 `.env` 未在该项目中提交。
- 新增 `.gitignore`：

```text
.env
.venv/
.cache/
__pycache__/
.pytest_cache/
```

建议：

- 轮换已暴露的 SSH 密码。
- 轮换已暴露的 DashScope API Key。
- 后续不要把真实凭据写进 spec、README、代码或对话。

效果：

- 降低后续误提交风险。
- 但已暴露凭据仍应按安全流程轮换。

### 12. ETF 中文名称解析

问题：

原 v1 只支持用户输入 6 位 ETF 代码。用户提出希望支持：

```text
工银沪深300ETF的费率和基金经理是什么
```

预期先解析：

```text
fundcode = 510350
matched_name = 沪深300ETF工银
```

再进入现有查询链路。

处理：

- 新增 `etf_agent/name_resolver.py`。
- 无 6 位代码时，pipeline 进入 ETF 中文名称解析。
- 名称解析不经过 Qwen，不让模型猜代码。
- 真实运行时从远端 `tb_ths_etf_base` 拉基础 catalog。
- 只读字段限制为：
  - `fundcode`
  - `thscode`
  - `ths_fund_extended_inner_short_name_fund`
  - `ths_fund_supervisor_fund`
  - `ths_name_of_tracking_index_fund`
  - `ths_tracking_index_code_fund`
- 支持基金公司和指数关键词顺序反转，例如 `工银沪深300ETF` 匹配 `沪深300ETF工银`。
- 宽泛名称多匹配时返回候选，不默认选择。

效果：

真实命令：

```bash
.venv/bin/python etf_agent_demo.py "工银沪深300ETF的费率和基金经理是什么"
```

返回：

```text
510350 的管理费率为 0.15%，托管费率为 0.05%，基金管理人为 工银瑞信基金，基金经理(现任)为 刘伟琳。
```

多匹配命令：

```bash
.venv/bin/python etf_agent_demo.py "沪深300ETF的费率是多少"
```

返回候选：

```text
匹配到多只 ETF，请补充具体产品
- 159919 沪深300ETF 159919.SZ
- 510350 沪深300ETF工银 510350.SH
- 510330 沪深300ETF华夏 510330.SH
```

### 13. LangChain / MCP 架构判断

问题：

用户询问当前实现是否使用 LangChain，以及未来如果做 MCP 是否必须使用 `financial-analysis-langchain` 项目中的 LangChain/LangGraph 框架。

判断：

- 当前 `etf-query` v1 demo 不是 LangChain/LangGraph 实现。
- 它是框架无关的核心能力模块：

```python
semantic_query(question: str) -> dict
```

- `financial-analysis-langchain` 项目使用：
  - FastAPI
  - LangChain `ChatOpenAI`
  - LangGraph `create_react_agent`
  - `langchain_core.tools.tool`

结论：

- 如果最终目标是 MCP，不必把核心逻辑绑定到 LangChain。
- 当前框架无关设计更适合作为 MCP tool 的底层能力。
- 后续可分别加薄包装：
  - `mcp_server.py`：封装 MCP tool。
  - `langchain_tool.py`：封装 LangChain tool，用于接入 `financial-analysis-langchain`。

效果：

- 核心查询逻辑不被单一框架锁死。
- 可以同时支持 CLI、MCP、LangChain tool 三种入口。

## 当前验证状态

截至本日志更新：

- 单元测试：

```bash
.venv/bin/python -m pytest tests/test_core.py -q
```

结果：

```text
72 passed
```

- 已验证真实远端查询：
  - `510300 盘子有多大`
  - `510300 近一年表现怎么样`
  - `工银沪深300ETF的费率和基金经理是什么`

- 已验证 v1 不支持场景会明确拒绝：
  - `510300 最新年报的前十大重仓股`
  - `沪深300ETF的费率是多少` 多匹配时返回候选
  - `不存在ETF的费率是多少` 无匹配时报未找到
