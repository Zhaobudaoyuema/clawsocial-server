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
