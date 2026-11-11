# 五子棋教学首版

入口 `/gomoku`，API `/api/gomoku/rooms`。独立 HTML/CSS/ES module，由 FastAPI 提供，Dockerfile 的 COPY app 自动包含；不修改博客、地图或远程命令入口，无需额外前端构建。

玩家创建房间并选颜色，复制邀请链接给 Codex。两个席位分别持有随机 capability Token，使用 URL fragment 保存并通过 X-Gomoku-Token 请求头发送；不要公开邀请链接。服务端仅存 Token 的 SHA256。每一步验证角色、轮次、坐标及 revision，事务内更新。无禁手，连续五子及以上获胜。

SQLite 存储默认 `/app/logs/gomoku/rooms.sqlite3`，随已有部署程序迁移 logs 保留；开发环境为项目 logs/gomoku。可用 GOMOKU_DB 指定私有持久路径，不要放在 /files 暴露的 uploads 内。备份应包含此目录。房间在单个应用实例中共享，暂不支持多节点分布式部署。

WebMCP 运行时兼容 document.modelContext 与 navigator.modelContext：
- get_turn：完整标注坐标的棋盘、轮次、最近六手、确定性的一步成五点。
- play_turn：带 expectedRevision 的落子，同时保存中文点评、落子讲解、标记坐标。
- wait_for_turn：最多等待 25 秒，超时由 Agent 再次调用；不保证客户端自动唤醒。
- review_last_move：不落子，只点评玩家上一手（含终局）。
- get_move_history：完整棋谱与讲解。

普通浏览器没有原生 WebMCP 时明确显示不可用；不会自动用网页机器人替代 Codex。实际 Codex 原生对接须在支持 WebMCP 的客户端验收。本地浏览器测试注入注册接口验证工具调用契约，不能视为原生客户端兼容认证。

如果 Nginx 没有全站转发到应用，需要在承载此功能的 HTTPS server 中加入两个 location（按已有服务实际 upstream 调整，不能覆盖已有远程命令路由）：

```nginx
location = /gomoku { proxy_pass http://127.0.0.1:8000; }
location = /gomoku/ { proxy_pass http://127.0.0.1:8000; }
location ^~ /api/gomoku/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

修改服务器路由前核对实际监听端口，nginx -t 后 reload。仓库 master 的 ACR v3 流水线负责构建和自动部署；不要迁移到 GitHub Actions。
