# ETF Query Temporary API

临时给智库使用的 ETF 查数 HTTP 接口。

公网地址：`http://47.96.152.227`

## 启动

```bash
.venv/bin/python etf_agent_api.py --host 0.0.0.0 --port 8090
```

当前 ECS 部署由 systemd 管理：

```bash
systemctl status etf-query.service
```

## 接口

- `GET /health`
- `GET /openapi.json`
- `POST /v1/query`

示例：

```bash
curl -sS http://47.96.152.227/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"510050现在什么价","phase":"v3.5"}'
```

## Apifox

推荐直接通过 URL 导入：

```text
http://47.96.152.227/openapi.json
```

也可以把 `docs/apifox/etf-query-openapi.json` 导入 Apifox；该文件已更新为公网地址和 v3.5 默认参数。
