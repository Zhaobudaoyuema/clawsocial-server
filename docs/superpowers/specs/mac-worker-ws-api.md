# Ollama Mac Worker — WebSocket API 调用方文档

> 版本：v0.3.0 · 协议模式：透明代理（proxy）

## 1. 概述

Mac Worker 是跑在用户本机的常驻程序，通过 **WebSocket 主动连接** 你的远程服务。调用方不直接访问用户机器上的 Ollama，而是：

1. 你的服务端通过已建立的 WebSocket 连接下发 **原始 OpenAI 兼容 API 请求**
2. Worker 将请求 **原样转发** 到本机 `http://127.0.0.1:11434/v1/chat/completions`
3. Worker 将 Ollama 响应 **原样转回**（非流式一次返回；流式按 chunk 返回）

**核心原则**：`body` 里的字段（`model`、`messages`、`stream`、`reasoning_effort` 等）Worker 不修改，与直接 curl 本地 Ollama 一致。

---

## 2. 安全模型

当前 Worker 采用以下约束（**不使用 token**）：

| 约束 | 说明 |
|-|-|
| Worker 出站连接 | 只连配置的远程 `host`；可选固定 `remote_ip` 校验 |
| 路径白名单 | **仅允许**`/v1/chat/completions` |
| 单任务 | 同时只处理 1 个推理，繁忙返回 `429` |
| 本机 Ollama | 默认仅 `127.0.0.1:11434`，不对公网暴露 |
| 传输加密 | 生产环境使用 **WSS** |

Worker 端 IP 限制的含义：确保 Mac 只连到你指定的远程服务，而不是随便连到其他 WebSocket 地址。

---

## 3. 连接方式

### 3.1 WebSocket 地址

```
wss://<你的域名>/ws/worker
```

- 生产环境使用 **WSS**
- Worker 主动连出，Mac 侧无需端口映射

### 3.2 鉴权

**当前版本不需要 token**，也不发送 `Authorization` header。

安全依赖：

- WSS 加密
- Worker 端远程 IP / host 校验
- 你的服务端控制「谁能往这条连接发 action」

### 3.3 连接后 Worker 主动上报

Worker 连接成功后会发送：

```json
{
  "type": "register",
  "hostname": "360itdeMacBook-Pro.local",
  "model": "qwen3.5:4b-mlx",
  "version": "0.1.0",
  "mode": "proxy",
  "remote_ip": "1.2.3.4"
}
```

`remote_ip` 仅在 Worker 配置了固定远程 IP 时出现。

随后发送状态：

```json
{"type": "status", "state": "ready"}
```

`state` 取值：

| 值 | 含义 |
|-|-|
| `ready` | 空闲，可接任务 |
| `busy` | 正在推理 |
| `paused` | 已暂停，拒绝新任务 |
| `offline` | 未连接 |

---

## 4. 消息类型总览

| 方向 | 识别方式 | 用途 |
|-|-|-|
| 服务端 → Worker | `{"type":"ping"}` | 心跳探测 |
| Worker → 服务端 | `{"type":"pong"}` | 心跳响应 |
| Worker → 服务端 | `type` 为 `register` / `status` | 上线注册、状态变更 |
| 服务端 → Worker | 含 `body` 字段（且无控制类 `type`） | **API 代理请求** |
| Worker → 服务端 | 含 `id` + `status` | **API 代理响应** |

**判断是否为 API 请求**：消息是 JSON 对象，包含 `body` 字段（值为 object），且 `type` 不是 `ping`/`pong`/`register`/`status`。

---

## 5. API 代理请求（服务端 → Worker）

### 5.1 请求格式

```json
{
  "id": "req-001",
  "method": "POST",
  "path": "/v1/chat/completions",
  "body": {
    "model": "qwen3.5:4b-mlx",
    "messages": [
      {"role": "user", "content": "用一句话介绍北京"}
    ],
    "reasoning_effort": "none",
    "stream": false,
    "max_tokens": 200
  }
}
```

| 字段 | 必填 | 说明 |
|-|-|-|
| `id` | 建议 | 请求唯一 ID，响应原样带回 |
| `method` | 否 | 默认 `POST` |
| `path` | 否 | 默认 `/v1/chat/completions`；**其他 path 会返回 403** |
| `body` | 是 | 与 curl Ollama 时 POST 的 JSON 完全一致 |

### 5.2 等价的本地 curl

```bash
curl http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5:4b-mlx",
    "messages": [{"role": "user", "content": "用一句话介绍北京"}],
    "reasoning_effort": "none",
    "stream": false,
    "max_tokens": 200
  }'
```

### 5.3 Qwen3.5 注意点

- 建议设 `"reasoning_effort": "none"`，避免 token 花在思考链上
- `stream` 原样透传：`true` 流式，`false` 或非流式

---

## 6. 非流式响应（Worker → 服务端）

当 `body.stream` 为 `false` 或未设置时，返回 **单条** 消息：

```json
{
  "id": "req-001",
  "status": 200,
  "body": {
    "id": "chatcmpl-619",
    "object": "chat.completion",
    "model": "qwen3.5:4b-mlx",
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "北京是..."
        },
        "finish_reason": "stop"
      }
    ],
    "usage": {
      "prompt_tokens": 17,
      "completion_tokens": 31,
      "total_tokens": 48
    }
  }
}
```

| 字段 | 说明 |
|-|-|
| `id` | 与请求一致 |
| `status` | HTTP 状态码 |
| `body` | Ollama 原始 JSON，不做改写 |

### 6.1 Python 解析示例

```python
import json

def handle_message(raw: str):
    msg = json.loads(raw)

    if msg.get("type") in ("register", "status", "pong"):
        return

    req_id = msg.get("id")
    if not req_id or msg.get("stream") is True:
        return

    if msg.get("status", 200) >= 400:
        raise RuntimeError(msg.get("body"))

    content = msg["body"]["choices"][0]["message"]["content"]
    usage = msg["body"].get("usage", {})
    return req_id, content, usage
```

---

## 7. 流式响应（`stream: true`）

### 7.1 请求示例

```json
{
  "id": "req-002",
  "method": "POST",
  "path": "/v1/chat/completions",
  "body": {
    "model": "qwen3.5:4b-mlx",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }
}
```

### 7.2 响应帧序列

**中间帧：**

```json
{
  "id": "req-002",
  "status": 200,
  "stream": true,
  "done": false,
  "chunk": "data: {\"choices\":[{\"delta\":{\"content\":\"你\"}}]}\n\n"
}
```

**结束帧：**

```json
{
  "id": "req-002",
  "status": 200,
  "stream": true,
  "done": true
}
```

`chunk` 是 Ollama SSE 的原始文本。

### 7.3 解析要点

1. 按 `id` 聚合消息
2. `done: false` 时解析 `chunk` 里的 `data:` 行
3. `done: true` 表示该请求结束
4. 将各 `delta.content` 拼接为完整回复

---

## 8. 错误响应

### 8.1 Worker 层错误

```json
{
  "id": "req-003",
  "status": 429,
  "body": {
    "error": {
      "message": "worker is busy",
      "type": "worker_error"
    }
  }
}
```

| status | 含义 |
|-|-|
| 400 | `body` 不是 object 等格式错误 |
| 403 | `path` 不是 `/v1/chat/completions` |
| 429 | 已有 1 个任务在执行 |
| 502 | 转发失败（Ollama 不可达等） |
| 503 | Worker 已暂停 |

### 8.2 Ollama 层错误

`status` 为 Ollama 返回的 HTTP 状态码，`body` 为 Ollama 原始错误 JSON。

---

## 9. 心跳

服务端 → Worker：

```json
{"type": "ping"}
```

Worker → 服务端：

```json
{"type": "pong"}
```

---

## 10. 调用方实现建议

### 10.1 请求配对

- 每个请求带唯一 `id`
- 维护 `pending[id]`
- 流式需等到 `done: true`

### 10.2 并发策略

- Worker **同时只跑 1 个任务**
- 收到 `429` 或 `status.state == "busy"` 时应排队重试
- 不要并行发多个推理请求

### 10.3 超时建议

- 非流式：120s+
- 流式：60s 无新 chunk 视为超时

### 10.4 时序图

```
服务端                         Worker                     Ollama
  |                               |                          |
  |<-------- register ------------|                          |
  |<-------- status: ready -------|                          |
  |-------- API request --------->|                          |
  |                               |------ POST /v1/chat ---->|
  |                               |<----- JSON / SSE --------|
  |<-------- API response --------|                          |
```

---

## 11. Node.js 最小示例

```javascript
import WebSocket from "ws";
import { randomUUID } from "crypto";

const ws = new WebSocket("wss://api.example.com/ws/worker");
const pending = new Map();

ws.on("message", (raw) => {
  const msg = JSON.parse(raw.toString());
  if (msg.type === "register" || msg.type === "status") return;

  const { id, stream, done, status, body, chunk } = msg;
  if (!id) return;

  if (stream === true) {
    const slot = pending.get(id) || { chunks: [], resolve: null, reject: null };
    if (chunk) slot.chunks.push(chunk);
    if (done) {
      pending.delete(id);
      slot.resolve?.(slot.chunks);
    } else {
      pending.set(id, slot);
    }
    return;
  }

  const slot = pending.get(id);
  if (!slot) return;
  pending.delete(id);
  status >= 400 ? slot.reject?.(body) : slot.resolve?.(body);
});

function callOllama(body) {
  const id = randomUUID();
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({
      id,
      method: "POST",
      path: "/v1/chat/completions",
      body,
    }));
  });
}
```

---

## 12. 附录

### 12.1 与 HTTP 直接调 Ollama 的差异

| 对比项 | 直接 HTTP | WebSocket 经 Worker |
|-|-|-|
| 地址 | `http://127.0.0.1:11434` | `wss://你的域名` |
| 请求体 | POST body | 消息中的 `body` |
| 响应 | HTTP body | 消息中的 `body` 或 `chunk` |
| 鉴权 | 通常无 | 当前版本无 token |
| 并发 | 自定 | Worker 强制单任务 |

### 12.2 Worker 本地命令（供 Mac 用户）

```bash
ollama-worker init --host wss://api.example.com/ws/worker --remote-ip 1.2.3.4
ollama-worker start
ollama-worker stats
ollama-worker pause
ollama-worker resume
```

---

## 13. Docker 部署 + Mac Worker 联调

本节说明：**服务端跑在 Docker 里时，如何启用 LLM 智能发现**。与「在容器内安装 Ollama」无关——算力始终在 Mac 本机，Docker 只提供 API 与 `/ws/worker` 中转。

### 13.1 架构（反向连接）

```
用户浏览器 ──HTTPS──► 反向代理 (TLS + WebSocket)
                         │
                         ▼
                   Docker: clawsocial
                   ├── FastAPI :8000
                   ├── MySQL（数据卷）
                   └── uploads/deid（文档卷，建议挂载）

办公室 Mac ──WSS 出站──► 同上 /ws/worker
   ollama-worker + Ollama (127.0.0.1:11434)
```

要点：

| 项 | 说明 |
|-|-|
| **Mac 不需要公网 IP** | Worker **主动连出**到 `wss://域名/ws/worker`，Mac 侧无需端口映射 |
| **Docker 内不需要 Ollama** | 容器只跑 FastAPI + MySQL；推理在 Mac 本机完成 |
| **单 Worker** | 同时仅 1 条 Worker 连接（新连接顶替旧连接），适合办公室一台 Mac 专职推理 |
| **Worker 离线** | 词库 + 规则扫描 + 手动添加实体仍可用；`scan_summary.llm_skipped = "worker_offline"` |

### 13.2 部署场景对照

| 场景 | 是否可行 |
|-|-|
| Docker 部署 deid REST + 前端 | ✅ |
| Docker + MySQL 存任务/词库 | ✅ |
| Docker **无 Mac Worker 连接** | ⚠️ 可用，但无 LLM 智能发现 |
| Docker + **Mac Worker 连 WSS** | ✅ **推荐生产方案** |
| Docker 内装 Ollama | ❌ 非本协议设计，也不必要 |
| 多台 Mac 同时推理 | ❌ 当前协议/实现不支持 |

### 13.3 反向代理：WebSocket 必须透传

生产环境在 Docker 前通常有 Nginx / Caddy。**`/ws/worker` 必须支持 WebSocket 升级**，否则 Mac Worker 无法维持长连接。

**Nginx 示例**（TLS 在 Nginx 终止，`wss://` → 容器 `http://127.0.0.1:8000`）：

```nginx
upstream clawsocial {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    # ssl_certificate / ssl_certificate_key ...

    location /ws/worker {
        proxy_pass http://clawsocial;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        proxy_pass http://clawsocial;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Caddy 示例**（自动 HTTPS）：

```caddy
api.example.com {
    reverse_proxy /ws/worker localhost:8000 {
        flush_interval -1
    }
    reverse_proxy localhost:8000
}
```

开发/内网直连 Docker 映射端口（如 `-p 8000:8000`）时，可用 `ws://服务器IP:8000/ws/worker` 做联调；**生产请用 WSS**（见 §2、§3.1）。

### 13.4 Docker 运行建议

单镜像已含 MySQL，典型启动：

```bash
docker run -d \
  --name clawsocial-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -v clawsocial-mysql:/var/lib/mysql \
  -v clawsocial-uploads:/app/uploads \
  clawsocial-server:latest
```

| 卷 | 用途 |
|-|-|
| `clawsocial-mysql` | MySQL 数据持久化 |
| `clawsocial-uploads` | deid 上传 docx、导出文件（**建议挂载**，否则容器重建后文档丢失） |

Compose 部署见仓库 `docker-compose.yml`；运维流程见 [`docs/DOCKER_DEPLOY.md`](../../DOCKER_DEPLOY.md)。

### 13.5 Mac Worker 连接生产服务

在**办公室 Mac**（已安装 Ollama 与 `ollama-worker`）执行：

```bash
# 1. 拉模型（与 register.model 一致）
ollama pull qwen3.5:4b-mlx

# 2. 初始化 Worker（remote-ip 填 Docker 宿主机的公网 IP，非容器内网 IP）
ollama-worker init \
  --host wss://api.example.com/ws/worker \
  --remote-ip 1.2.3.4

# 3. 启动（可配合 launchd 常驻）
ollama-worker start
```

`--remote-ip` 为 Worker 端可选校验：确保 Mac 只连到你指定的远程服务 IP。

### 13.6 验收清单

| 步骤 | 命令 / 操作 | 期望结果 |
|-|-|-|
| 1 | `curl https://api.example.com/api/deid/worker/status` | `{"online":false,...}`（Worker 未连时） |
| 2 | Mac 上 `ollama-worker start` | 服务端日志出现 `worker registered` |
| 3 | 再次 `curl .../worker/status` | `online:true`, `state:"ready"`, 含 `model` / `hostname` |
| 4 | 浏览器 `/deid` 上传 docx → 扫描 | `scan_summary.llm_hits > 0`（Worker 在线时） |
| 5 | 停止 Worker 后再扫描 | scan 仍 200，`llm_skipped:"worker_offline"` |

服务端实现：`app/api/ws_worker.py`、`app/deid/worker/router.py`；扫描排队：`ScanQueue` 串行，与 Worker 单任务一致。

### 13.7 常见问题

| 现象 | 可能原因 | 处理 |
|-|-|-|
| Worker 连上后立即断开 | 反向代理未配置 WebSocket Upgrade | 检查 §13.3 Nginx/Caddy |
| `online:false` 但 Mac 显示已连接 | 连错路径（少了 `/worker`） | `--host` 必须是 `.../ws/worker` |
| LLM 超时 | 文档块过大或模型冷启动 | 调 `DEID_LLM_TIMEOUT_SEC`；Worker 侧先 warmup |
| 扫描成功但 `llm_hits:0` | Worker 离线或 `DEID_LLM_ENABLED=0` | 查 status API 与环境变量 |

---

## 14. 变更记录

| 版本 | 日期 | 说明 |
|-|-|-|
| v0.1.0 | 2026-06-08 | 初版：透明代理 |
| v0.2.0 | 2026-06-08 | 去掉 token；增加远程 IP 限制；单任务；仅 `/v1/chat/completions`；补充 403/429 |
| v0.3.0 | 2026-06-01 | 新增 §13 Docker 部署 + Mac Worker 联调；修正 §12.2 init 路径为 `/ws/worker` |