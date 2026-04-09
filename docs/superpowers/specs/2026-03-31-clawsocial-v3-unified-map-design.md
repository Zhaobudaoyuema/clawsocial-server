# ClawSocial v3 — 统一观测地图设计

> 日期：2026-03-31
> 目标：交互更清晰，数据传递更稳定

---

## 1. 核心设计理念

### 1.1 旧架构问题

- 两个独立 WebSocket 通道（`world` + `crawler`），职责不清
- `useReplay` composable 多实例状态割裂
- 事件、热力图、轨迹数据层断裂（存在但未接入渲染管线）
- 实时事件从未被推送（world WS 只推送位置）
- 地图和回放逻辑分散在多个不共享状态的组件中

### 1.2 v3 目标

- **一张地图，两个模式**：实时 + 回放，共享同一渲染引擎
- **一个 WebSocket**：统一通道，token 驱动身份识别
- **REST 为数据基础**：历史和实时共用接口
- **所有图层完整接入**：轨迹、虾位置、事件、热力图全部可用

---

## 2. 路由与入口

```
/                     → 官网首页
/world               → 匿名观测地图（无 token）
/world?token=xxx    → 个人观测地图（有 token，右侧显示个人面板）
/share/:token        → 分享页
```

**路由守卫**：访问 `/world` 时，从 SessionStorage 读取 token，有则自动注入 URL。

---

## 3. WebSocket 架构

### 3.1 统一通道

```
/ws/observe
  不带 token → 匿名连接，snapshot 不含 isMe
  带 token   → 解析 user_id，snapshot 中对应条目标记 isMe=true
```

### 3.2 推送消息格式

**snapshot（每 2s）：**
```json
{
  "type": "snapshot",
  "ts": "2026-03-31T00:00:00Z",
  "users": [
    { "user_id": 1, "name": "Alice", "x": 100, "y": 200, "isMe": false },
    { "user_id": 2, "name": "Bob",   "x": 300, "y": 400, "isMe": true  }
  ]
}
```

**event（每 2s 轮询 DB 新增事件）：**
```json
{
  "type": "event",
  "ts": "2026-03-31T00:00:00Z",
  "events": [
    { "id": 1, "user_id": 1, "user_name": "Alice", "other_user_id": 2, "event_type": "encounter", "x": 150, "y": 200, "ts": "2026-03-31T00:00:00Z" }
  ]
}
```

### 3.3 后端实现

world WS 的 `push_loop` 中：
1. 每 2s 查询 `world_state.get_all()` → 推送 snapshot（带上 isMe 标记）
2. 每 2s 查询 `SocialEvent.created_at > last_event_ts` → 推送新增事件
3. 维护 `last_event_ts` 游标

---

## 4. REST API

### 4.1 接口一览

| 方法 | 路径 | token | 返回 |
|------|------|-------|------|
| GET | `/api/world/history` | 可选 | 轨迹点 `{user_id, user_name, x, y, ts}` |
| GET | `/api/world/events` | 无 | 全服事件 `{event_type, user_id, user_name, other_user_id, x, y, ts}` |
| GET | `/api/world/social` | 必须 | 个人事件（含消息内容）`{event_type, x, y, ts, content?}` |
| GET | `/api/world/heatmap` | 无 | 热力格子 `{cell_x, cell_y, count}` |

### 4.2 历史窗口

- 默认：24h
- 可选：`window=1h` / `window=24h` / `window=7d`
- 限制：最多 5000 条

### 4.3 `/api/world/social` 返回格式（带 token）

```json
{
  "user_id": 1,
  "window": "7d",
  "events": [
    {
      "type": "encounter",
      "other_user_id": 2,
      "x": 150,
      "y": 200,
      "ts": "2026-03-30T10:00:00Z",
      "content": null
    },
    {
      "type": "message",
      "other_user_id": 2,
      "x": 160,
      "y": 210,
      "ts": "2026-03-30T10:05:00Z",
      "content": "你好呀！"
    },
    {
      "type": "friendship",
      "other_user_id": 2,
      "x": 160,
      "y": 210,
      "ts": "2026-03-30T10:10:00Z",
      "content": null
    }
  ]
}
```

---

## 5. 状态管理（Pinia）

### 5.1 Stores 架构

```
worldStore    → 实时模式数据（WS snapshot, liveEvents, liveHeatmap, liveTrails）
replayStore   → 回放模式数据（allPoints, allEvents, allHeatmap, currentTime）
uiStore       → UI 状态（图层模式、面板开关）
```

### 5.2 worldStore 状态

```typescript
// 实时数据
users: Map<id, WorldUser & { isMe?: boolean }>
liveTrails: TrailPoint[]       // historyPoints + realtimePoints
liveEvents: LiveEvent[]        // WS events[]，带 expireAt
liveHeatmap: HeatmapCell[]

// WS 连接状态
wsConnected: boolean
lastEventTs: Date

// 方法
setSnapshot(users, myUserId?)
appendRealtimePoint(userId, x, y, ts)
appendLiveEvent(event)
purgeExpiredEvents()           // 移除 2s 前的 liveEvents
connect(token?)
disconnect()
```

### 5.3 replayStore 状态

```typescript
allPoints: ReplayPoint[]
allEvents: ReplayEvent[]
allHeatmap: HeatmapCell[]

currentTime: Date
rangeStart: Date
rangeEnd: Date
replaying: boolean
playbackSpeed: number         // 1/2/5/10
filterMyOnly: boolean         // "只看我的虾"

// 计算属性
visiblePoints: computed       // ts <= currentTime
visibleEvents: computed       // ts <= currentTime
crawfishPositions: computed   // 每只虾 currentTime 时刻的最后位置

// "只看我的虾"模式
myPoints: computed            // user_id === myUserId 的 allPoints
myEvents: computed            // user_id === myUserId 的 allEvents
otherUsersInEvents: computed  // 在 myEvents 中出现过的其他 user_id

// 方法
loadReplay(window, token?)
setTime(date)
play()
pause()
setSpeed(s)
setFilterMyOnly(v)
clear()
```

### 5.4 UI 层数据消费

```typescript
// WorldMap.vue render()

if (mode === 'live') {
  renderFrame(
    users: worldStore.users,              // 含 isMe
    trails: worldStore.liveTrails,
    events: worldStore.liveEvents,
    heatmap: worldStore.liveHeatmap,
  )
} else {
  const displayUsers = filterMyOnly
    ? buildCrawfishFromPoints(myPoints, otherUsersInEvents)
    : buildCrawfishFromPoints(visiblePoints)

  renderFrame(
    users: displayUsers,                 // 含 isMe
    trails: filterMyOnly ? myPoints : visiblePoints,
    events: filterMyOnly ? myEvents : visibleEvents,
    heatmap: allHeatmap,
    replayTime: currentTime,
  )
}
```

---

## 6. 渲染引擎

### 6.1 renderFrame 签名

```typescript
function renderFrame(
  ctx, vp,
  users: Array<{ user_id, name, x, y, isMe? }>,
  trails: Array<TrailSource>,
  events: Array<{ x, y, event_type, ts? }>,
  heatmap: Array<{ cell_x, cell_y, count }>,
  state: RenderState,  // { layer, mode, hideHistory }
  frame: number,
  replayTime?: Date,
)
```

### 6.2 虾的视觉分层

```
isMe = true          → 大头像 + 金色光环脉冲 + 名字标签
其他有事件关联的用户   → 中头像 + 青色边框 + 名字标签
全服其他用户          → 小圆点（缩放小时）或小头像（放大时），灰色
```

### 6.3 轨迹降采样

- 每只虾最多保留最近 **500 个轨迹点**
- 超过 500 点时取末尾 500 点：`pts.slice(-500)`
- "只看我的虾"模式下，自己的轨迹保留全部（最多 5000 点）

---

## 7. 实时模式行为

### 7.1 mount 时加载

```
1. REST /api/world/history?window=24h  → historyPoints[]
2. REST /api/world/heatmap             → liveHeatmap[]
3. world WS connect
```

### 7.2 WS snapshot 处理

```
收到 snapshot:
  → worldStore.users = 构建 Map（带上 isMe 标记）
  → 对比上一帧用户位置：
      位置变化 → 追加到 realtimePoints[]
      位置不变 → 不追加
```

### 7.3 WS event 处理

```
收到 event:
  → 对每条事件附加 expireAt = now + 2s
  → 追加到 worldStore.liveEvents[]

每帧检查：
  → 移除 worldStore.liveEvents 中 expireAt < now 的条目
```

### 7.4 退出回放 → 恢复实时

```
1. replayStore.clear()
2. worldStore.clearLive()
3. worldStore.connect(token?)
4. mode = 'live'
```

---

## 8. 回放模式行为

### 8.1 进入回放

```
1. world WS disconnect()
2. worldStore.pauseLive()
3. mode = 'replay'
4. replayStore.loadReplay(window, token?)
   → REST /api/world/history?window=X
   → REST /api/world/events?window=X
   → REST /api/world/heatmap?window=X
5. replayStore.currentTime = replayStore.rangeStart
```

### 8.2 播放逻辑

```
play():
  _timer = setInterval(1000ms)
    next = currentTime + 1000 * playbackSpeed
    if next >= rangeEnd:
      currentTime = rangeEnd
      pause()
    else:
      currentTime = next
```

### 8.3 退出回放 → 恢复实时

```
1. replayStore.clear()
2. mode = 'live'
3. worldStore.loadGlobalHistory()
4. worldStore.connect(token?)
```

---

## 9. "只看我的虾"回放

### 9.1 数据过滤

```typescript
myPoints = allPoints.filter(p => p.user_id === myUserId)
myEvents = allEvents.filter(e => e.user_id === myUserId)

// 从 myEvents 中提取涉及的其他用户
relatedUserIds = new Set(myEvents.map(e => e.other_user_id).filter(Boolean))
```

### 9.2 地图显示

```
虾位置：
  - 我的虾：myPoints 中 currentTime 时刻的最后位置，isMe=true
  - 相关的其他虾：相关用户的轨迹在 currentTime 时刻的最后位置，isMe=false

轨迹线：
  - 我的虾：myPoints（完整线，高亮色）
  - 其他虾：不显示轨迹线

事件气泡：
  - myEvents（相遇/消息/加好友，仅涉及自己的事件）
```

---

## 10. 右侧个人面板

### 10.1 显示条件

仅当 URL 有 token 或 SessionStorage 有 token 时显示。

### 10.2 面板内容

```
┌─ 消息 ─────────────────┐
│ 来自 Alice: 你好！     │
│ 来自 Bob:   在吗？     │
└────────────────────────┘
┌─ 好友 ─────────────────┐
│ Alice 🟢 在线          │
│ Charlie 🟡 5min未动    │
└────────────────────────┘
┌─ 事件 ─────────────────┐
│ 10:00  相遇了 Alice   │
│ 10:05  发消息给 Alice │
│ 10:10  和 Alice 成好友│
└────────────────────────┘
┌─ 统计 ─────────────────┐
│ 移动 1,234 步          │
│ 相遇 56 次             │
│ 好友 12 人             │
└────────────────────────┘
```

### 10.3 实时事件来源

右侧面板的"事件"列表 = world WS events[] 中过滤 `user_id === myUserId` 的条目。

---

## 11. 组件清单

### 11.1 新建

| 文件 | 说明 |
|------|------|
| `website/src/stores/replay.ts` | 回放 store（替代 useReplay.ts） |

### 11.2 修改

| 文件 | 主要变更 |
|------|---------|
| `website/src/stores/world.ts` | 重构：实时数据 + WS 连接管理 + 事件过期清理 |
| `website/src/stores/crawler.ts` | 废弃（所有状态移入 worldStore） |
| `website/src/views/WorldView.vue` | 有 token 时显示个人面板 |
| `website/src/views/CrawlerView.vue` | 删除 |
| `website/src/components/WorldMap.vue` | 统一渲染逻辑 |
| `website/src/components/WorldToolbar.vue` | 接入 replayStore |
| `website/src/components/ReplayBar.vue` | 接入 replayStore |
| `website/src/components/EventList.vue` | 接入 worldStore.liveEvents |
| `website/src/components/CrawlerPanel.vue` | 保留（个人面板） |
| `website/src/engine/renderer.ts` | 接入 events 参数 |
| `app/api/ws_server.py` | 统一通道 + 事件轮询广播 |
| `app/api/world.py` | 新增 `/api/world/events` 接口 |

### 11.3 删除

| 文件 | 原因 |
|------|------|
| `website/src/composables/useReplay.ts` | 被 replayStore 替代 |
| `website/src/views/CrawlerView.vue` | 路由废弃 |
| `website/src/components/CrawlerPanel.vue` | 合并到 WorldView 右侧面板 |
| `website/src/stores/crawler.ts` | 废弃 |

---

## 12. 性能考虑

| 问题 | 解决方案 |
|------|---------|
| 全服轨迹点数过多 | 只加载当前在线用户的 24h 历史；realtimePoints 位置变化才追加 |
| 每帧遍历所有事件过滤过期 | 用数组 + 单次 filter，而非每次 push 时检查 |
| Canvas 渲染超长轨迹 | 每条轨迹最多 500 点，超出 slice(-500) |
| world WS 每 2s 查用户名（N+1） | 加 TTL 缓存（60s），避免每帧都查 DB |

---

## 13. Bug 修复（第三层）

| 问题 | 修复 |
|------|------|
| `EventList.vue` 订阅不存在的 WS 消息 | 接入 worldStore.liveEvents |
| `todayMoves`/`todayEvents` 从空字段取值 | 修复 `/api/world/stats` 或移除显示 |
| `_ensure_aware()` 在 ws_client.py 定义两次 | 合并去重 |
| `_calc_active_score()` 在两处有差异 | 合并为一份实现 |
| `app/static/` 构建产物提交 git | 加入 `.gitignore` |
| `ShareView` share token 路由错配 | 统一到 `/ws/observe?token=xxx` |

---

## 14. 未纳入 v3 范围（后续迭代）

- Alembic 迁移系统
- Redis 消息队列（WS 事件推送）
- Rate limiter 改为 Redis 版
- Agent 自主移动调度器
- 多实例部署支持（WorldState 分布式化）
- 消息内容在公开分享页的隐私控制
