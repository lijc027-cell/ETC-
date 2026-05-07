# ETF Semantic Query Demo

本目录是按 `docs/etf-semantic-query-spec.md` 实现的 v1 本地 CLI 原型。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，填入本地私密配置：

```env
DASHSCOPE_API_KEY=你的 DashScope API Key
ETF_SSH_PASSWORD=远端 SSH 密码
```

`.env.example` 不包含真实密码。

## 本地演示

不连 Qwen、不连 SSH 时，可以用 dry-run 展示完整链路：

```bash
.venv/bin/python etf_agent_demo.py --dry-run "510300 盘子有多大"
```

dry-run 会输出实体识别、候选字段、查询计划、SQL-like、Mongo 参数、示例远端结果和最终回答。

## 真实查询

完整链路会调用 DashScope embedding、Qwen 和远端 Mongo：

```bash
.venv/bin/python etf_agent_demo.py "510300 盘子有多大"
```

也可以用单只 ETF 中文名称提问，系统会先从远端基础表解析基金代码：

```bash
.venv/bin/python etf_agent_demo.py "工银沪深300ETF的费率和基金经理是什么"
```

宽泛名称可能匹配多只 ETF，此时会返回候选列表，让你补充具体产品：

```bash
.venv/bin/python etf_agent_demo.py "沪深300ETF的费率是多少"
```

如果只想跳过 Qwen，用确定性计划直查远端 Mongo：

```bash
.venv/bin/python etf_agent_demo.py --no-llm "510300 盘子有多大"
```

## Spec 测试问题

```bash
.venv/bin/python etf_agent_demo.py --dry-run "510300 是什么"
.venv/bin/python etf_agent_demo.py --dry-run "510300 盘子有多大"
.venv/bin/python etf_agent_demo.py --dry-run "510300 跟踪什么指数"
.venv/bin/python etf_agent_demo.py --dry-run "510300 近一年表现怎么样"
.venv/bin/python etf_agent_demo.py --dry-run "510300 的管理费和托管费是多少"
```

## 测试

```bash
.venv/bin/python -m pytest tests/test_core.py -q
```
