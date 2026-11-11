# 五子棋快速代下

正式入口 https://clawsocial.world/gomoku。用户已确认腾讯小程序为 15×15，区别是显示大小；保留 A–O / 1–15 坐标、中心 H8。页面撤掉讲解侧栏，棋盘独占主要宽度，桌面棋盘框最大 1040px，手机减少边距。

## 使用方式

1. 选择“我方”颜色，新建代下棋局。我方执黑时，服务端自动在 H8 放第一颗黑子；我方执白时，空盘等待录入对手黑棋。
2. 创建后弹出 Codex 连接链接，交给 Codex 打开。邀请链接只授予当前棋局的我方落子能力，不要公开。
3. 用户在原页面点击录入对手落子；Codex 在连接页读盘并替我方落子。页面大字显示我方最新坐标，用户再同步到腾讯小程序。
4. 不显示或要求讲解、复盘。撤销按当前录入/应手回退一轮；我方黑棋固定中心开局保留。清空重来恢复相同颜色与开局，新棋局可重新选色。

## 状态及权限真源

SQLite 默认 `/app/logs/gomoku/rooms.sqlite3`，随现有部署程序迁移 logs 保留。每个房间的 mode 决定流程，humanColor 是手动录入席位的颜色，agentColor 按相反颜色派生。relay 模式中 agentColor 即用户在腾讯小程序所执颜色；不另存一份我方颜色或棋盘缓存，棋盘从 moves 派生。

新页面只创建 relay 模式：POST `/api/gomoku/rooms` 传 `mode: relay, ownColor: black|white`。旧 match API 和既有房间继续保留旧规则与权限，不自动交换席位；旧链接打开新页面后提示新建代下棋局。

两个席位 Token 分开放在 URL fragment，通过 X-Gomoku-Token 请求头访问 API，服务端只存 SHA256。每次落子事务内核对席位、轮次、revision 和占位；relay 不再要求 explanation，match 仍保留原验证。

## 快速调用

仅注册三个原生 WebMCP 工具：

- get_turn：一次 heartbeat POST 获取最新完整棋盘，明确 Codex 是替用户下棋，不是用户的对手。
- play_turn：仅传 move、expectedRevision；一次 POST 落子并返回完整更新状态，不要额外刷新/读页面/截图/播报。
- wait_for_turn：一次 GET `/api/gomoku/rooms/{room}/turn?afterRevision=...&timeout=15`。服务端最多等待 15 秒、每 200ms 检查一次变化，有变化直接返回完整棋盘；超时后继续等待。低于实测客户端约 20 秒的工具执行限制，避免旧版等待 25 秒导致工具连接失效。

录入页面每 400ms 同步一次，Codex 连接页不额外轮询。工具上下文用 15 行紧凑棋盘，不重复完整棋谱或教学文本。网络响应优化不保证模型思考瞬时完成；Codex 必须保持当前对弈任务运行，页面不自行调用模型，也不会在聊天结束后自动唤醒 Codex。

## HTTPS 与部署

宿主机 Nginx 配置的仓库来源为 `ops/gomoku/nginx-https.conf` 和 `ops/gomoku/nginx-http-redirect.conf`。证书由宿主机 Certbot 管理，不进入仓库或镜像：

1. 为 `clawsocial.world` 申请有效证书：`certbot certonly --nginx --cert-name clawsocial.world -d clawsocial.world --non-interactive`（复用已注册账号）。
2. 将 HTTPS 配置安装到 `/etc/nginx/sites-enabled/clawsocial-gomoku.conf`，将 HTTP 跳转片段安装到 `/etc/nginx/snippets/gomoku-http-redirect.conf` 并在该域名现有的 80 端口 server 中 include。
3. `nginx -t` 成功后 reload；启用 Certbot timer，续期 deploy hook 执行 `systemctl reload nginx`。不要全站 HTTP 跳转，ACR 无凭据通知仍保留原 HTTP 入口。
4. 页面和 API 均同源 HTTPS，邀请链接从当前 origin 生成；HTTP 跳转没有 fragment，浏览器会保留原邀请 fragment。fragment 中的 Token 不会发送给 Nginx。旧 HTTP 会话的 sessionStorage 不会跨 origin 迁移，使用原邀请链接或新建棋局。

仓库 master 的 ACR v3 流水线负责构建和自动部署；不要迁移到 GitHub Actions。Nginx/证书属于宿主机配置，镜像更新不会替换它们。回滚页面可沿用 worker 的镜像回滚；如需撤销 HTTPS 入口，移除上述 include 和 HTTPS 配置，nginx -t 后 reload。

## 验收

本地回归：`.venv/bin/python -m pytest tests/test_api.py tests/test_gomoku.py tests/test_remote_command.py tests/test_remote_command_v11.py`。

原生 Codex 内置浏览器验收：黑棋自动 H8 → 用户录入白棋 I8 → agent get_turn / play_turn（无讲解）→ 原页面显示我方 I9；白棋空盘 → 用户录入黑棋 H8 → agent 白棋应手。wait_for_turn 超时在约 15 秒正常返回，工具句柄仍可用；输入后提前返回。接口注入测试不能替代原生验收。
