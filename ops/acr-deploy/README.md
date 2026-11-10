# ACR 持续自动部署

ACR `master → v3` 构建完成并推送镜像后，调用独立于业务容器的 HTTPS 回调。
本目录代码安装到服务器 `/opt/clawsocial-deploy`；不随业务镜像运行，更新业务容器不会中断回调服务。

## 配置与权限

- `/etc/clawsocial-deploy/config.json` 是目标仓库、标签、容器名和兼容标签的唯一配置源，初始格式见 `config.example.json`。
- `/etc/clawsocial-deploy/webhook.token` 保存专用随机凭据，权限 `root:clawsocial-deploy 0640`。接收服务逐次读取，支持替换文件后立即生效。
- 接收服务以无登录权限的 `clawsocial-deploy` 用户运行，只监听 `127.0.0.1:8790`，仅能写入持久队列。
- Nginx 在现有 `multica.clawsocial.world` HTTPS server 中包含 `nginx.conf`，仅暴露 `POST /hooks/acr/clawsocial`。
- ACR 触发器 URL 为 `https://multica.clawsocial.world/hooks/acr/clawsocial?token=<专用凭据>`，名称 `clawsocial_auto_deploy`，表达式 `^v3$`。URL 包含部署凭据，不应复制到仓库、聊天或访问日志；Nginx 与接收器均禁用该路径的 URL 日志。
- 只有后台 worker 以 root 运行并访问 Docker；复用本机已有 Docker 登录状态，不复制仓库密码。

## 部署行为

回调验证凭据、仓库、地域、标签和 digest 后返回 202，并原子写入 `/var/lib/clawsocial-deploy/queue`。
systemd path 单元监控队列，通过 oneshot worker 串行处理，进程退出后队列仍保留。

worker 拉取配置的标签，并确认事件 digest 仍是该标签当前指向；过期事件忽略。
线上镜像已一致且健康时跳过，不重启容器。新镜像必须包含配置要求的兼容标记。

有更新时先备份数据库，按新镜像默认配置创建候选容器；运行时环境差异、端口和挂载从当前容器解析。
停止旧 MySQL 和容器后迁移容器内上传文件、日志，旧容器改名保留，再启动新容器。
等待 Docker healthcheck，并检查页面、v12 鉴权及 v11 入口。失败时先停止新版，再恢复旧容器。

`active.json` 是切换事务恢复记录。若 worker 在切换中退出，下次启动先恢复旧容器，避免新旧 MySQL 同时访问数据卷。
数据库备份供人工恢复；自动回滚恢复应用容器，不自动导入旧 SQL，不覆盖运行期间产生的新数据。
涉及不可逆数据库迁移的版本应先暂停自动部署并单独验证迁移与恢复。

保留最近三次本服务创建的备份、各两个自动部署产生的旧版/失败容器；只清理本 worker 产生且已停止的容器，删除镜像不使用 force。
不清理手动部署备份、其他容器或数据卷。低于 2 GiB 可用磁盘时拒绝开始部署。

## 运维

```bash
systemctl status clawsocial-deploy-receiver.service clawsocial-deploy-worker.path
journalctl -u clawsocial-deploy-worker.service -n 30 --no-pager
ls /var/lib/clawsocial-deploy/history
```

history 中的状态包括 `deployed`、`already_current`、`stale_event_ignored` 和失败原因。
ACR 的 HTTP 202 仅表示事件已接收，部署结果以 worker 日志及 history 为准。

暂停自动部署：

```bash
systemctl stop clawsocial-deploy-worker.path
systemctl stop clawsocial-deploy-receiver.service
```

暂停不会主动打断已经执行中的 worker；先查看其状态，再安排维护。
恢复时启动上述两个单元，积压队列会继续处理。配置使用固定 v3，手工发布其他标签不会自动上线。

安装映射：`receiver.service` → `clawsocial-deploy-receiver.service`，
`worker.service` → `clawsocial-deploy-worker.service`，
`worker.path` → `clawsocial-deploy-worker.path`。修改后先执行 `systemd-analyze verify`、`nginx -t`，再重载对应服务。

本地验证：

```bash
python -m pytest tests/test_acr_deploy.py tests/test_remote_command.py tests/test_remote_command_v11.py tests/test_api.py -q
```

通知格式参考[阿里云 ACR 触发器文档](https://help.aliyun.com/zh/acr/user-guide/manage-webhooks)。
