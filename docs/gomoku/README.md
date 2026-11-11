# 五子棋快速代下

正式入口 https://clawsocial.world/gomoku。用户已确认腾讯小程序为 15×15，坐标与腾讯截图一致：A1 左下、O15 右上，字母位于底边，数字向上递增，中心 H8。页面撤掉讲解侧栏，棋盘独占主要宽度，棋盘框最大 560px，并按视口高度减去 330px 限制大小，手机同时受可用宽度限制；顶部与操作区收紧间距，使棋盘与操作按钮在一屏内显示。

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

- get_turn：一次 heartbeat POST 获取最新黑白坐标列表，明确 Codex 是替用户下棋，不是用户的对手。固定棋盘规则放在工具描述中。
- play_turn：仅传 move、expectedRevision；一次 POST 落子，工具只返回 revision / played 确认（终局追加 status / winner），不要额外刷新/读页面/截图/播报。
- wait_for_turn：一次 GET `/api/gomoku/rooms/{room}/turn?afterRevision=...&timeout=15`。服务端最多等待 15 秒、每 200ms 检查一次变化，有变化直接返回黑白坐标列表；超时仅返回 revision / timeout，之后继续等待。低于实测客户端约 20 秒的工具执行限制，避免旧版等待 25 秒导致工具连接失效。

录入页面每 400ms 同步一次，Codex 连接页不额外轮询。工具上下文用空格分隔的 black / white 坐标列表，未列出的格点为空；只在有一步获胜点时追加 win / block，终局追加 status / winner。示例：`{"revision":3,"you":"white","yourTurn":true,"black":"A1 K15","white":"O15","secondsLeft":12}`。落子后直接 wait_for_turn，不重复 get_turn。网络响应优化不保证模型思考瞬时完成；Codex 必须保持当前对弈任务运行，页面不自行调用模型，也不会在聊天结束后自动唤醒 Codex。

## 15 秒提示

服务端在成功落子、撤销或重开时保存 turnStartedAt，moveDeadline 按此时间加 15 秒派生；只在 relay 的 Codex 回合显示。读取、heartbeat、页面轮询及刷新均不重置计时。页面用 serverTime 校准时钟，每 100ms 更新显示，剩余 5 秒变红，归零提示“已超时 · 请立即落子”；不会自动判负或代落随机棋。旧房间缺少时间戳时先不显示，下次落子后开始。该提示不能保证模型在 15 秒内应答。

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

本轮本地验收：92 项回归通过；原生 WebMCP 读盘返回坐标列表，play_turn 返回精简确认，A1 左下、O15 右上及鼠标 K15 录入正确；刷新倒计时继续递减。
