# 五子棋教学首版

正式入口 https://clawsocial.world/gomoku；HTTP 的五子棋页面和 API 路径返回 308 跳转 HTTPS。入口 `/gomoku`，API `/api/gomoku/rooms`。独立 HTML/CSS/ES module，由 FastAPI 提供，Dockerfile 的 COPY app 自动包含；不修改博客、地图或远程命令入口，无需额外前端构建。

玩家创建房间并选颜色，复制邀请链接给 Codex。两个席位分别持有随机 capability Token，使用 URL fragment 保存并通过 X-Gomoku-Token 请求头发送；不要公开邀请链接。服务端仅存 Token 的 SHA256。每一步验证角色、轮次、坐标及 revision，事务内更新。无禁手，连续五子及以上获胜。

SQLite 存储默认 `/app/logs/gomoku/rooms.sqlite3`，随已有部署程序迁移 logs 保留；开发环境为项目 logs/gomoku。可用 GOMOKU_DB 指定私有持久路径，不要放在 /files 暴露的 uploads 内。备份应包含此目录。房间在单个应用实例中共享，暂不支持多节点分布式部署。

WebMCP 要求 HTTPS 安全上下文（localhost 开发例外），优先使用 document.modelContext.registerTool，兼容旧版 navigator.modelContext；页面在顶层 document 的模块脚本初始化时注册一次，无需 Codex 专用桥接：
- get_turn：完整标注坐标的棋盘、轮次、最近六手、确定性的一步成五点。
- play_turn：带 expectedRevision 的落子，同时保存中文点评、落子讲解、标记坐标。
- wait_for_turn：最多等待 25 秒，超时由 Agent 再次调用；不保证客户端自动唤醒。
- review_last_move：不落子，只点评玩家上一手（含终局）。
- get_move_history：完整棋谱与讲解。

普通浏览器没有原生 WebMCP 时明确显示不可用；不会自动用网页机器人替代 Codex。实际 Codex 原生对接须在支持 WebMCP 的客户端验收。本地浏览器测试注入注册接口验证工具调用契约，不能视为原生客户端兼容认证。

## HTTPS 与部署

宿主机 Nginx 配置的仓库来源为 `ops/gomoku/nginx-https.conf` 和 `ops/gomoku/nginx-http-redirect.conf`。证书由宿主机 Certbot 管理，不进入仓库或镜像：

1. 为 `clawsocial.world` 申请有效证书：`certbot certonly --nginx --cert-name clawsocial.world -d clawsocial.world --non-interactive`（复用已注册账号）。
2. 将 HTTPS 配置安装到 `/etc/nginx/sites-enabled/clawsocial-gomoku.conf`，将 HTTP 跳转片段安装到 `/etc/nginx/snippets/gomoku-http-redirect.conf` 并在该域名现有的 80 端口 server 中 include。
3. `nginx -t` 成功后 reload；启用 Certbot timer，续期 deploy hook 执行 `systemctl reload nginx`。不要全站 HTTP 跳转，ACR 无凭据通知仍保留原 HTTP 入口。
4. 页面和 API 均同源 HTTPS，邀请链接从当前 origin 生成；HTTP 跳转没有 fragment，浏览器会保留原邀请 fragment。fragment 中的 Token 不会发送给 Nginx。旧 HTTP 会话的 sessionStorage 不会跨 origin 迁移，使用原邀请链接或新建棋局。

仓库 master 的 ACR v3 流水线负责构建和自动部署；不要迁移到 GitHub Actions。Nginx/证书属于宿主机配置，镜像更新不会替换它们。回滚页面可沿用 worker 的镜像回滚；如需撤销 HTTPS 入口，移除上述 include 和 HTTPS 配置，nginx -t 后 reload。

## 原生客户端验收

2026-11-11 在 Codex Desktop 内置浏览器验证：HTTP 原生发现返回无工具；同一页面在有效 HTTPS 上原生发现全部五个工具，确认安全上下文是注册失败原因。工具 descriptor 的 name/description/inputSchema/execute 和当前 content 文本返回格式可被客户端识别。

发布后必须通过浏览器原生 `webmcp.fetchTools()` 发现工具，并通过返回的工具句柄调用；不要注入 modelContext：

1. 玩家在 HTTPS 页面创建黑棋棋局，用棋盘回车落下 H8。
2. 复制邀请链接，在另一个 Codex 内置浏览器标签页打开对手席位。
3. 原生发现五个工具；调用 get_turn，核对 yourTurn、revision、H8 黑子。
4. 调用 play_turn（I8、读取到的 expectedRevision、中文 humanMoveReview/explanation 和 highlights）。
5. 回到玩家标签页，确认轮询同步两颗棋子、点评与讲解。不得将含 Token 的完整邀请链接写入报告。

本地回归：`.venv/bin/python -m pytest tests/test_api.py tests/test_gomoku.py`。接口注入测试仅验证函数契约，不能替代上述原生验收。
