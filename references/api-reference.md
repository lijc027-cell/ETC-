# ETF 数据查询参考

> **何时读我**：当需要通过 SSH 远程查询 ETF 数据时读取。数据直接通过 SSH 在服务器上执行 Python 脚本查询 MongoDB。

---

## 执行方式

所有查询通过 **SSH 远程执行** Python 脚本实现，不需要 HTTP 端口。

**服务器信息**：
- SSH: `[ETF_SSH_USER]@[ETF_SSH_HOST]`，密码 `<ETF_SSH_PASSWORD>`
- 脚本：`[ETF_REMOTE_SCRIPT]`
- Python: `[ETF_REMOTE_PYTHON]`
- MongoDB 直连：`[ETF_REMOTE_MONGO_URI]`

---

## 命令列表

| 命令 | 用途 | 参数 |
|------|------|------|
| `info` | 单只 ETF 完整信息 | `{"fundcode":"510300"}` |
| `search` | 搜索 ETF | `{"keyword":"沪深300","limit":20}` |
| `compare` | 多只对比 | `{"fundcodes":"510300,510500"}` |
| `filter` | 条件筛选 | `{"tracking_index":"沪深300","limit":20}` |
| `holdings` | 持仓信息 | `{"fundcode":"510300","report_type":"quarter"}` |
| `performance` | 收益率 | `{"fundcode":"510300","period":"1y"}` |

---

## Python paramiko 调用（标准模板）

**核心原则：单次 SSH 连接 + 远程脚本执行 + SFTP 读文件返回 JSON**。

### 单路查询（如基本信息）

```python
import paramiko, json, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("[ETF_SSH_HOST]", 22, "[ETF_SSH_USER]", "<ETF_SSH_PASSWORD>")

# Execute command, write result to file on server
ssh.exec_command("cd [ETF_REMOTE_WORKDIR] && [ETF_REMOTE_PYTHON] etf_query.py info '{\"fundcode\":\"510300\"}' > /tmp/etf_result.json 2>/dev/null")
time.sleep(2)

# Read file via SFTP for proper UTF-8 encoding
sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
with sftp.open('/tmp/etf_result.json', 'rb') as f:
    data = json.loads(f.read().decode('utf-8'))
sftp.close()
ssh.close()
```

### 多路并行（基本信息 + 收益率 + 持仓）

```python
import paramiko, json, time, threading

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("[ETF_SSH_HOST]", 22, "[ETF_SSH_USER]", "<ETF_SSH_PASSWORD>")

# Execute all commands on same SSH connection (no wait needed)
ssh.exec_command("cd [ETF_REMOTE_WORKDIR] && [ETF_REMOTE_PYTHON] etf_query.py info '{\"fundcode\":\"510300\"}' > /tmp/etf_a.json 2>/dev/null")
ssh.exec_command("cd [ETF_REMOTE_WORKDIR] && [ETF_REMOTE_PYTHON] etf_query.py performance '{\"fundcode\":\"510300\"}' > /tmp/etf_b.json 2>/dev/null")
ssh.exec_command("cd [ETF_REMOTE_WORKDIR] && [ETF_REMOTE_PYTHON] etf_query.py holdings '{\"fundcode\":\"510300\",\"report_type\":\"quarter\"}' > /tmp/etf_c.json 2>/dev/null")

time.sleep(2)  # Wait for all to complete

# Read all results in one SFTP session
sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
def read_json(path):
    with sftp.open(path, 'rb') as f:
        return json.loads(f.read().decode('utf-8'))

info = read_json('/tmp/etf_a.json')
perf = read_json('/tmp/etf_b.json')
hold = read_json('/tmp/etf_c.json')

sftp.close()
ssh.close()
```

### 单脚本一次性查询（最快，推荐）

对于需要多维度数据的场景（如完整分析单只ETF），用单个远程 Python 脚本一次返回所有数据：

```python
import paramiko, json, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("[ETF_SSH_HOST]", 22, "[ETF_SSH_USER]", "<ETF_SSH_PASSWORD>")

cmd = '''cd [ETF_REMOTE_WORKDIR] && [ETF_REMOTE_PYTHON] -c "
import json
from pymongo import MongoClient
db = MongoClient('[ETF_REMOTE_MONGO_URI]')['[ETF_REMOTE_DB]']
doc = db['tb_ths_etf_base'].find_one({'fundcode': '510300'})
out = {'name': doc.get('ths_fund_extended_inner_short_name_fund'),
       'fundcode': doc.get('fundcode'),
       'tracking_index': doc.get('ths_name_of_tracking_index_fund'),
       'mv': doc.get('ths_current_mv_fund')}
with open('/tmp/etf_all.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, default=str)
"'''

ssh.exec_command(cmd)
time.sleep(2)

sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
with sftp.open('/tmp/etf_all.json', 'rb') as f:
    data = json.loads(f.read().decode('utf-8'))
sftp.close()
ssh.close()
```

### 关键要点

1. **exec_command 不阻塞**：连续调用多个 `exec_command` 会自动在后台并行执行，只需最后 `time.sleep(2)` 统一等待
2. **SFTP 读文件保证 UTF-8**：SSH 通道直接输出中文会乱码，必须通过文件中转
3. **单次连接复用**：同一次 SSH 连接可执行多个 `exec_command` 和 SFTP 操作
4. **临时文件复用**：`/tmp/etf_*.json` 每次调用自动覆盖，无需清理
