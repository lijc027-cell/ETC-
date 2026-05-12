# ETF Query Temporary API

临时给智库使用的 ETF 查数 HTTP 接口。

## 启动

```bash
.venv/bin/python etf_agent_api.py --host 0.0.0.0 --port 8090
```

## 接口

- `GET /health`
- `GET /openapi.json`
- `POST /v1/query`

示例：

```bash
curl -sS http://127.0.0.1:8090/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"510300是什么","phase":"v3.3"}'
```

## Apifox

把 `docs/apifox/etf-query-openapi.json` 导入 Apifox 即可生成接口文档。
