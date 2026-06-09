# 文档脱敏 v2：Mac Worker + LLM 自动发现

- **日期**: 2026-06-08
- **状态**: 已实施
- **协议**: [`mac-worker-ws-api.md`](mac-worker-ws-api.md) v0.2.0
- **前置**: [`2026-05-31-deid-mvp-design.md`](2026-05-31-deid-mvp-design.md)

## 背景

天健审计师处理中国能建底稿时，纯词库维护成本高。服务端仅 2G 内存，无法本地跑 NER/LLM。Mac 本机通过 Worker 连接服务端，Ollama 推理在本地完成。

## 架构

```
Deid UI → POST /jobs/{id}/scan
       → preset + pattern + doc rules + LLM (via WorkerRouter)
       → merge → entities + scan_summary
```

- **不变**: `app/deid/engine/pipeline.py` / `ReplacementPlan` / `run_job` 替换逻辑
- **新增**: `/ws/worker`、`WorkerRouter`、`app/deid/discovery/*`

## Scan 四层发现

| 层 | source | 说明 |
|----|--------|------|
| 词库 | `preset` | 现有 DeidEntity 别名命中 |
| 正则规则 | `pattern` | DeidPatternRule + 机构后缀规则 |
| 文档规则 | `rule` | 以下简称/下称 |
| 智能发现 | `llm` | Mac Worker → Ollama chat/completions |

合并优先级：`manual > preset > rule > llm > pattern`

## Worker 协议要点

- 服务端 → Worker：`{id, method, path, body}`（无 `type`）
- Worker → 服务端：`register` / `status` / `{id, status, body}`
- scan 固定 `stream: false`，`reasoning_effort: "none"`
- 429 指数退避重试（1s/2s/4s，最多 3 次）
- 单 Worker 连接（新连接顶替旧连接）
- lifespan 每 30s ping

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/deid/worker/status` | `{online, state, model, hostname, version}` |
| POST | `/api/deid/jobs/{id}/scan` | 响应含 `scan_summary` |

### scan_summary 示例

```json
{
  "preset_hits": 12,
  "pattern_hits": 3,
  "rule_hits": 2,
  "llm_hits": 5,
  "llm_chunks": 4,
  "llm_skipped": null,
  "worker_model": "qwen3.5:4b-mlx",
  "llm_errors": []
}
```

Worker 离线时 `llm_skipped: "worker_offline"`，scan 不 500。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEID_LLM_ENABLED` | `1` | `0` 跳过 LLM |
| `DEID_LLM_CHUNK_SIZE` | `6000` | 分块大小 |
| `DEID_LLM_CHUNK_OVERLAP` | `500` | 块重叠 |
| `DEID_LLM_TIMEOUT_SEC` | `120` | 单块超时 |
| `DEID_LLM_MODEL` | 空 | 覆盖 register.model |

测试环境 `TESTING=1` 时 conftest 默认 `DEID_LLM_ENABLED=0`。

## 隐私

sample 文本与 LLM 请求 body **禁止**写入 `app.log`；仅内存处理，不落 DB 原文。

## 默认词库包

`ceec` + `general_finance` 为默认；`spic` 非默认（单人能建场景）。


## 可编辑扫描提示词（v2.1）

- 全局提示词存 `deid_settings.scan_prompt`，UI：**词库管理 → 扫描设置**
- 任务级追加存 `deid_jobs.prompt_extra`，UI：**上传步骤 → 本任务额外说明**
- 合成：`build_scan_system_prompt(global, extra)`，scan LLM 使用合成结果
- API：`GET/PUT /api/deid/settings/scan-prompt`、`POST .../reset`、`GET /jobs/{id}/effective-prompt`

## 本地对话（v2.1）

- UI Tab：**本地对话**；模式：无文档 / 选 job / 上传 docx
- 会话内存存储（TTL 2h），不落 DB
- `POST /api/deid/chat/sessions` → `POST .../messages`（SSE 流式）
- Worker `chat_completions_stream` 解析 Ollama SSE chunk
- 对话系统提示词 `CHAT_DEFAULT_SYSTEM`（与 scan 提示词独立）

## Docker 部署

服务端可跑在 Docker（单镜像含 MySQL）；**容器内不装 Ollama**。Mac Worker 通过 WSS **出站**连接 `wss://域名/ws/worker`，反向代理需配置 WebSocket 升级。

详见 [`mac-worker-ws-api.md`](mac-worker-ws-api.md) **§13**（架构图、Nginx/Caddy、验收清单、uploads 卷建议）。

## 验收

- Worker 在线：上传 `ceec_audit_test.docx`，scan 发现「中能建氢能源有限公司」（LLM 或后缀规则）
- Worker 离线：scan 成功，词库+规则可用
- 确认 → run → 残留扫描流程不变
- Docker 生产：`GET /api/deid/worker/status` 在 Worker 连接后为 `online:true`
- `pytest tests/test_api.py tests/test_deid.py tests/test_worker_router.py tests/test_deid_prompt.py tests/test_deid_chat.py` 全通过
