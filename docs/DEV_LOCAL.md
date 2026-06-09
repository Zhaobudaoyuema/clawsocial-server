# 本地 Windows 调试 → 生产服务器 → Mac Worker

生产站点示例：[https://clawsocial.world/deid](https://clawsocial.world/deid)

Mac Worker **只连一条 WebSocket**（`wss://clawsocial.world/ws/worker`），不会同时连本地。本地调试有两种安全模式：

| 模式 | 本地跑什么 | Worker/LLM | 适用 |
|------|-----------|--------------|------|
| **A 前端代理** | Vite `npm run dev` | 生产 API + 生产 Worker | 改 UI、走生产数据 |
| **B 全栈中继** | 本地 FastAPI + 可选 Vite | 经 token 中继到生产 Worker | 改后端 scan/发现逻辑 |

---

## 模式 A：仅前端本地（最简单）

Mac Worker 保持连 **生产**，浏览器访问本地 Vite，API 代理到生产。

```powershell
cd website
copy .env.development.local.example .env.development.local
# 编辑 .env.development.local：
#   VITE_DEV_PROXY_TARGET=https://clawsocial.world

npm run dev
# 打开 http://localhost:5173/deid
```

数据、上传、扫描结果都在**生产库**；勿用于破坏性测试。

---

## 模式 B：本地 FastAPI + 远程 Worker 中继（改后端）

链路：

```
本地 Windows (FastAPI :8000)
    │  HTTPS + Bearer Token
    ▼
生产 clawsocial.world  /api/deid/dev/worker/*
    │  已有 WebSocket
    ▼
Mac Worker → Ollama
```

### 1. 生产服务器

**无需再配 `.env`**（已内置本机白名单）。部署最新代码即可；`/api/deid/dev/*` 在 `ALLOWED_DEV_MACHINE_GUIDS` 非空时自动启用。

可选覆盖（一般不用）：

```bash
DEID_DEV_RELAY_TOKEN=手动密钥
DEID_DEV_RELAY_IPS=公网IP   # 额外 IP 限制
```

### 2. 本地 Windows

**无需 `.env`** — 自动读取本机 `MachineGuid` 生成 token，默认连 `https://clawsocial.world`。

```powershell
# 查看本机 GUID / token / 是否已注册
python -m scripts.show_dev_relay_token

# 终端 1
python run.py

# 终端 2
cd website && npm run dev
```

新电脑加入白名单：在该电脑运行 `show_dev_relay_token`，把打印的 GUID 加到 `app/deid/worker/dev_machine_token.py` 的 `ALLOWED_DEV_MACHINE_GUIDS`，commit 后 redeploy。

### （旧）手动 token 方式

若不想用机器白名单，仍可用环境变量（本地与服务器一致）：

```bash
DEID_WORKER_RELAY_URL=https://clawsocial.world
DEID_WORKER_RELAY_TOKEN=openssl rand -hex 32
```

```powershell
# 终端 1 — 后端
python run.py

# 终端 2 — 前端（指向本地 API）
cd website
npm run dev
# 不要设 VITE_DEV_PROXY_TARGET，默认 localhost:8000
```

### 4. 验收

```powershell
# 本地应看到 relay 模式 + 生产 Worker 在线
curl http://127.0.0.1:8000/api/deid/worker/status

# 生产 Worker 仍在线（Mac 未改 host）
curl https://clawsocial.world/api/deid/worker/status
```

上传 docx 扫描时，`scan_summary.llm_hits` 应 > 0（Worker 在线时）。

---

## Mac Worker 地址（生产）

Worker **不要**改连本地，除非你要完全脱离生产：

```bash
ollama-worker init --host wss://clawsocial.world/ws/worker --remote-ip <服务器公网IP>
ollama-worker start
```

协议详见 [`docs/superpowers/specs/mac-worker-ws-api.md`](superpowers/specs/mac-worker-ws-api.md)。

---

## 中继 API（仅供模式 B）

| 方法 | 路径 | 鉴权 |
|------|------|------|
| GET | `/api/deid/dev/worker/status` | `Authorization: Bearer <token>` |
| POST | `/api/deid/dev/worker/chat-completions` | 同上 |

Header 也可用：`X-Deid-Relay-Token: <token>`

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 本地 `worker_offline` | 查生产 `/api/deid/worker/status`；Mac Worker 是否连生产 |
| 401 relay_token_invalid | 本地与服务器 `DEID_*RELAY_TOKEN` 不一致 |
| 403 relay_ip_denied | 把本机公网 IP 加入 `DEID_DEV_RELAY_IPS` 或清空该变量 |
| 404 on `/api/deid/dev/*` | 服务器未设置 `DEID_DEV_RELAY_TOKEN` 或未 redeploy |

查询本机公网 IP：`curl ifconfig.me`
