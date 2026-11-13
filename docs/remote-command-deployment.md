# 远程命令 v12 与旧版兼容部署

镜像同时提供 v12 和 v11 兼容入口。操作员凭据由环境变量
`REMOTE_COMMAND_OPERATOR_TOKEN` 或 `REMOTE_COMMAND_OPERATOR_TOKEN_FILE` 指定的文件提供，
未指定文件路径时读取 `/app/remote-command-operator.token`。每次请求读取当前凭据；
未配置时 v12 管理接口返回 503。不要把真实凭据写进代码、镜像或日志。

## v12 接入

1. 操作员携带 `Authorization: Bearer <operator-token>` 调用
   `POST /api/remote-command/invites`，请求体包含 `session_minutes`（10、30、180）
   和可选 `lifetime_minutes`（1–180，默认 30）。
2. 被控端使用返回的 `invite_token` 调用 `POST /api/remote-command/targets/register`。
   邀请只能使用一次，数据库只保存邀请哈希与有效期、授权时长和消费状态。
3. 被控端使用返回的 `id` 和 `connection_token` 建立
   `/ws/remote-command/target?id=<id>` 连接，握手时携带
   `Authorization: Bearer <connection-token>`。操作员 token 不应交给被控端。
4. 查询目标列表、状态和执行命令均需操作员鉴权。连接令牌只在对应授权记录中保存哈希。

数据库初始化入口 `python -m scripts.init_db` 会创建邀请表。
授权和连接仍在进程内维护，重启后需要重新注册；邀请消费状态保存在数据库中。
新旧协议的授权及连接均按现有逻辑在北京时间每日 04:00 清除。

## v11 兼容

旧接口位于 `/legacy-v11/api/remote-command/*`，旧 WebSocket 位于
`/legacy-v11/ws/remote-command/target`。它们使用独立中继实例，不能访问 v12 授权。
兼容接口保持旧版公开注册和执行语义，不使用 v12 操作员鉴权。

现有生产 Nginx 将 `clawsocial.world` 的远程命令请求重写至 `/legacy-v11`，
将 `multica.clawsocial.world` 的对应请求转发至 v12 根路径。
仓库内现有 `scripts/remote_command_target_agent.py` 继续使用旧版域名入口；
直接访问应用端口时需在 base URL 后加 `/legacy-v11`。
旧版注册响应的 `websocket_path` 保持外部路径，直接访问端口的客户端需补上此前缀。

Dockerfile 标记 `remote-command.version=12`、`remote-command.legacy-v11=enabled`，
与现有服务器部署检查一致。生产部署应保留 MySQL 数据卷和只读操作员 token 文件挂载。
本次代码同步不包含自动部署回调服务，也不更改 Nginx 配置。

## 大输出分片（2026-11-13）

服务端 WebSocket `registered` 消息新增 `result_chunks: 1`。Agent 仅在该能力存在时，
将超过 256 KiB JSON 帧的命令输出拆为 `result_chunk`：`request_id`、从 0 递增的
`sequence`、`stream`（stdout/stderr）、`data`。每片最多 16384 个 Unicode 字符，
包括 JSON 转义在内仍低于 256 KiB。最后发送原 `result`（退出码及耗时保留），
stdout/stderr 留空并携带 `chunk_count`。只有收到数量匹配的结束帧才返回完整结果。
HTTP 执行接口的响应格式不变；分片不代表命令重跑。

分片暂存仅属于原待处理请求，按原授权目标校验；乱序、重复或结束帧不一致使本次
命令返回 502，超时、取消、断开时释放。单命令 stdout/stderr 合计最多 32 MiB，
最多 4096 片，超限返回明确错误且不关闭目标连接。不返回部分输出冒充成功。
旧版单包 result 不再受应用层 256 KiB 门限限制，仍受 Uvicorn 原生帧上限约束
（默认 16 MiB）；大于该值须升级 Agent。新 Agent 接入旧服务端时，超限结果会报告
需要升级服务端并保留连接，不自动重跑已执行命令。

macOS 公网 v9 的来源为已发布 macOS v8，保持其执行策略、异步执行、心跳和 shell
回退行为，源码为 `scripts/remote_command_public_agent.py`。它与原受限脚本
`scripts/remote_command_target_agent.py` 共用 `remote_command_output.py` 分片实现；
原受限脚本的执行策略不变。打包复用经过 SHA-256 校验的 v8 依赖：

```bash
python3 scripts/build_remote_public_agent.py /tmp/remote-command-target-agent-public-v9.pyz
```

新的 macOS 公网临时 Agent（180 分钟，需保持终端开启）：

```bash
curl -fsSL 'https://ns.chat.360.cn/zhaomi-so/client-up/d1aa54dd3ab0133a8de4aeef462713e7e4936dfb/start-remote-command-public-macos-v9.sh' | REMOTE_COMMAND_BASE_URL=http://clawsocial.world bash -s -- quick
```

包：`https://ns.chat.360.cn/zhaomi-so/client-up/269d8132e68b10a27c9c0a809f68781e4e6b6171/remote-command-target-agent-public-v9.pyz`。
SHA-256：`b988b4ead27737ecbee62a3c45aff47599af0a81cc0cb4b8676c7b3527f351cf`。
旧 CDN 链接不可变，正在运行的旧 Agent 不会自动获得分片能力；使用新入口重新启动。
