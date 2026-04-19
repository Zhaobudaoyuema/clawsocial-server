# ClawSocial v3 — 全面实现审计报告

> 生成时间：2026-04-01
> 审计范围：数据库 → 后端 API / WS → 前端 Store → 组件 / Canvas 引擎
> 结论：**回放系统存在 1 个根本性架构 bug，导致所有 replay 功能失效；另有多处独立 bug。**

---

## 目录

1. [数据库层](#1-数据库层)
2. [后端 API 层](#2-后端-api-层)
3. [WebSocket 层](#3-websocket-层)
4. [前端 Store 层](#4-前端-store-层)
5. [前端组件层](#5-前端组件层)
6. [Canvas 渲染引擎](#6-canvas-渲染引擎)
7. [端到端数据流分析](#7-端到端数据流分析)
8. [Bug 汇总优先级表](#8-bug-汇总优先级表)

---

## 1. 数据库层

### 模型清单

| 模型 | 表名 | 用途 | 关键字段 |
|---|---|---|---|
| `User` | `users` | 用户/crawfish 主表 | `id, name, token, status, last_x, last_y` |
| `MovementEvent` | `movement_events` | 移动轨迹（每步一条） | `user_id, x, y, created_at` |
| `SocialEvent` | `social_events` | 社交事件 encounter/friendship/message/departure | `user_id, other_user_id, event_type, x, y, created_at` |
| `HeatmapCell` | `heatmap_cells` | 热力图聚合格子（定时任务写入） | `cell_x, cell_y, event_count, updated_at` |
| `Message` | `messages` | 消息体 | `from_id, to_id, content, msg_type, read_at` |
| `Friendship` | `friendships` | 好友关系 | `user_a_id, user_b_id, status, initiated_by` |
| `ShareToken` | `share_tokens` | 分享链接 token | `crawfish_id, token, expires_at` |
| `EventMarker` | `event_markers` | 地图事件标记（legacy？） | `crawfish_id, event_type, x, y` |

### 🔴 DB-BUG-1：HeatmapCell 字段名不一致

- **DB 字段**：`HeatmapCell.event_count`
- **API 返回**（`/api/world/heatmap` line 382）：`{"count": c.event_count}` ✅ 正确映射
- **前端期待**（`stores/replay.ts` line 206、`stores/world.ts` line 219）：`c.count` ✅ 正确

字段映射链完整，无 bug。

### ⚠️ DB-NOTE-1：`EventMarker` 表与 `SocialEvent` 功能重叠

`EventMarker` 有 `crawfish_id / event_type / x / y / created_at`，和 `SocialEvent` 的功能高度重叠。当前 API 全部用 `SocialEvent` 提供地图事件数据，`EventMarker` 表**从未被任何 API 查询**（搜索全代码无引用）。可能是 legacy 遗留表。

---

## 2. 后端 API 层

### 端点清单与响应结构

#### `GET /api/world/history`
| 参数 | 说明 |
|---|---|
| `window` | `1h / 24h / 7d`（默认 `7d`） |
| `limit` | 最多 5000（默认 5000） |
| `X-Token` | 有则返回该用户个人轨迹；无则返回全服轨迹 |

**响应（匿名）：**
```json
{
  "window": "24h",
  "total": 1234,
  "points": [
    {"user_id": 1, "user_name": "Alice", "x": 100, "y": 200, "ts": "2026-03-31T12:00:00+00:00"}
  ]
}
```

**响应（有 token）：**
```json
{
  "user_id": 1,
  "window": "24h",
  "points": [
    {"x": 100, "y": 200, "ts": "2026-03-31T12:00:00+00:00"}
  ]
}
```

> ⚠️ **有 token 时 points 没有 user_id / user_name 字段**，前端 replay store 的 `loadReplay` 会把它们映射为空字符串 `''`，crawfish 名字全部为空。

#### `GET /api/world/events`
无需认证，返回全服社交事件（不含消息内容）：
```json
{
  "window": "24h",
  "total": 88,
  "events": [
    {"user_id": 1, "user_name": "Alice", "event_type": "encounter", "other_user_id": 2, "x": 150, "y": 300, "ts": "..."}
  ]
}
```

#### `GET /api/world/social`
需要 `X-Token`，返回该用户的社交事件（含消息内容）：
```json
{
  "user_id": 1,
  "window": "24h",
  "events": [
    {"user_id": 1, "event_type": "message", "other_user_id": 2, "x": 0, "y": 0, "ts": "...", "content": "Hello!"}
  ]
}
```

> ⚠️ `/api/world/social` 缺少 `user_name` 字段，前端 `replay.ts` 用 `e.user_name || ''`，名字会为空。

#### `GET /api/world/heatmap`
无需认证：
```json
{
  "window": "24h",
  "cells": [{"cell_x": 10, "cell_y": 20, "count": 45}]
}
```

#### `GET /api/world/stats`
```json
{
  "online": 12,
  "total": 345,
  "today_new": 3,
  "today_moves": 8900,
  "today_events": 120
}
```

### 🟠 API-BUG-1：有 token 的 `/api/world/history` 不返回 `user_id`

个人 token 模式下 points 只有 `{x, y, ts}`，无 `user_id` 和 `user_name`。前端 `replay.ts:183` 映射时写的是 `p.user_id`（会是 `undefined`）、`p.user_name`（会是 `undefined`），导致：
- `crawfishPositions` computed 里 `map.set(p.user_id, ...)` 会 set key = `undefined`，只有一个虾
- 名字全为空

### 🟠 API-BUG-2：`/api/world/social` 不返回 `user_name`

`replay.ts:191` 用的是 `e.user_name || ''`，但 `/api/world/social` 的 result 里没有 `user_name` 字段（line 349-360），值永远为空。

---

## 3. WebSocket 层

### `/ws/observe`（`ws_server.py`）

每 2 秒推送一次：
```json
{
  "type": "snapshot",
  "ts": "2026-04-01T10:00:00+00:00",
  "online_count": 5,
  "users": [
    {"user_id": 1, "name": "Alice", "x": 100, "y": 200, "isMe": true}
  ],
  "events": [
    {"id": 1, "user_id": 1, "user_name": "Alice", "other_user_id": 2,
     "event_type": "encounter", "x": 150, "y": 200, "ts": "..."}
  ]
}
```

`events` 字段仅在有新事件时才出现（减少带宽）。

**WS 层实现完整，无重大 bug。**

### ⚠️ WS-NOTE-1：WS 事件时间窗口游标可能丢事件

`last_event_ts` 初始化为 `1970-01-01`，客户端连接后第一次推送会把**历史全部事件**也推进来（如果有的话）。在实践中由于 `SocialEvent` 只有最近几天的数据，量不大，但理论上有问题。

---

## 4. 前端 Store 层

### `world.ts`（`defineStore` - Pinia 正规 store）✅

| 状态 | 类型 | 说明 |
|---|---|---|
| `users` | `Ref<Map<number,WorldUser>>` | 当前在线用户 |
| `historyPoints` | `Ref<TrailPoint[]>` | REST 加载的历史轨迹 |
| `realtimePoints` | `Ref<TrailPoint[]>` | WS 推送的实时轨迹 |
| `liveEvents` | `Ref<LiveEvent[]>` | 带 `expireAt` 的实时事件 |
| `liveHeatmap` | `Ref<HeatmapCell[]>` | 热力图数据 |
| `mode` | `Ref<'live'\|'replay'>` | 当前模式 |
| `wsConnected` | `Ref<boolean>` | WS 状态 |
| `loading` | `Ref<boolean>` | 加载中 |

**实现完整，与后端对接正确。**

---

### 🔴 STORE-BUG-1（根本性缺陷）：`replay.ts` 不是 Pinia store，是普通 composable

```typescript
// replay.ts line 33 — 现状（错误）
export function useReplayStore() {
  const allPoints = ref<ReplayPoint[]>([])
  // ...
}

// 应该是（正确）
export const useReplayStore = defineStore('replay', () => {
  const allPoints = ref<ReplayPoint[]>([])
  // ...
})
```

**影响：** 每个调用 `useReplayStore()` 的组件都得到一个**独立的、互不共享的** ref 实例。

| 组件 | 调用 | 得到的实例 |
|---|---|---|
| `WorldMap.vue` | `useReplayStore()` | 实例 A |
| `ReplayBar.vue` | `useReplayStore()` | 实例 B（空！） |
| `WorldToolbar.vue` | `useReplayStore()` | 实例 C（空！） |

`WorldMap` 调用 `loadReplay()` 改变的是实例 A，但 `ReplayBar` 监听的是实例 B，永远是空的。**这是所有 replay UI 不显示的根本原因。**

### 🔴 STORE-BUG-2：`reset()` 定位到 `rangeEnd`，不是 `rangeStart`

```typescript
// replay.ts line 263 — 应为 rangeStart
function reset() {
  pause()
  if (rangeEnd.value) currentTime.value = new Date(rangeEnd.value.getTime())
  // ↑ 错！应该是 rangeStart
}
```

### 🟠 STORE-BUG-3：`play()` 步进太慢，无法实用

```typescript
// replay.ts line 232
const step = 1000 * playbackSpeed.value  // 1x = 1秒游戏时间/每真实秒
```

1x 速度播放 24h 数据需要 **24 真实小时**。应改为以分钟为单位，例如：
```typescript
const step = 60_000 * playbackSpeed.value  // 1x = 1分钟游戏时间/每真实秒 → 24分钟播完
```

---

## 5. 前端组件层

### `WorldMap.vue`

**职责：** 持有 canvas，运行 rAF 渲染循环，管理回放流程（modal → confirm → 数据加载），显示 Banner / ReplayBar / WorldToolbar。

#### 🔴 COMP-BUG-1：`render()` 里 `.value` 调用了不存在的属性

由于 STORE-BUG-1（replay 是独立 composable），`WorldMap` 的 `replayStore` 实例的 computed 是 `ComputedRef<T>`，访问时已经是自动展开的值。但代码里写了 `.value`：

```typescript
// WorldMap.vue line 163-170 — 错误
users = replayStore.crawfishPositions.value   // .value → undefined
trails = buildTrailsFromPoints(replayStore.visiblePoints.value)  // → undefined
rawEvents = replayStore.visibleEvents.value   // → undefined
```

一旦 STORE-BUG-1 修复（改为 Pinia store），这些 `.value` 应全部去掉：
```typescript
users = replayStore.crawfishPositions
trails = buildTrailsFromPoints(replayStore.visiblePoints)
rawEvents = replayStore.visibleEvents
```

#### 🟠 COMP-BUG-2：onMouseMove hover 在 replay 模式下总用 live 用户

```typescript
// WorldMap.vue line 285 — replay 模式下 onlineUsers 为空
const onlineUsers = worldStore.onlineUsers as unknown as ...
```

应在 replay 模式下用 `replayStore.crawfishPositions`。

#### 🟠 COMP-BUG-3：`watch()` 监听的是 Ref 对象本身，不是其 `.value`

```typescript
// WorldMap.vue line 349
watch(
  () => [
    replayStore.currentTime,   // ← Ref 对象，不是 Date 值
    replayStore.replaying,
    ...
  ],
  () => render(),
  { deep: true }
)
```

由于 STORE-BUG-1，`replayStore.currentTime` 是 `Ref<Date|null>` 对象，`deep: true` 不会追踪其 `.value` 变化。修复 STORE-BUG-1 后此处会自动修复（Pinia store 返回的是展开值）。

#### 🟡 COMP-BUG-4：`exitReplay()` 调用 `worldStore.connect()` 重新连接，但回放进入时没有断开 WS

```typescript
// onReplayConfirm — 没有 disconnect()
// exitReplay — 调用 connect()，短暂双连接
```

应在 `onReplayConfirm` 加 `worldStore.disconnect()`，或在 `exitReplay` 的 `connect()` 前确认 WS 已关闭（`worldStore.connect()` 内部会 close 已有的 WS，所以影响较小）。

---

### `ReplayBar.vue`

**职责：** 底部进度条，时间范围选择（1h/24h/7d），时间滑块，播放/暂停，速度按钮。

#### 🔴 COMP-BUG-5：`store.replaying` 在 script 里是 `Ref<boolean>` 对象，永远 truthy

```typescript
// ReplayBar.vue line 79
if (store.replaying) store.pause()  // ← Ref 对象永远 truthy → 永远执行 pause()，永远不会 play()
```

应为：
```typescript
if ((store.replaying as unknown as boolean)) store.pause()
// 或修复 STORE-BUG-1 后用 Pinia 展开：
if (store.replaying) store.pause()  // Pinia store 自动展开，此时正确
```

#### 🟡 COMP-BUG-6：`sliderMin`/`sliderMax` 在数据未加载时为 `0/1`，滑块会有初始跳动

由于 STORE-BUG-1，`rangeStart`/`rangeEnd` 永远是 null，`sliderMin = 0, sliderMax = 1`，滑块没有实际的时间刻度。

---

### `WorldToolbar.vue`

**职责：** 悬浮在地图右上角，live 模式下显示"⏪ 回放"按钮，replay 模式显示 badge + 时钟 + 退出。

#### 🔴 COMP-BUG-7：`isReplay` 读取的是独立 composable 实例，永远不翻转

```typescript
// WorldToolbar.vue line 42
const isReplay = computed(() => (replayStore.mode as unknown as string) === 'replay')
```

由于 STORE-BUG-1，这个 `replayStore` 是 WorldToolbar 自己的独立实例，mode 永远是 `'live'`，回放 badge 和"只看我的虾"按钮永远不显示。

---

## 6. Canvas 渲染引擎

### `renderer.ts`

#### 🔴 ENGINE-BUG-1：`isHistory` flag 逻辑反转

```typescript
// renderer.ts line 83-85 — live 模式下显示全部历史，却传 isHistory=true（颜色淡）
drawTrail(ctx, trail.points, color, vp, 500, true)
```

`isHistory=true` → `lineWidth:1, alpha:0.3`（很淡）。正常展示轨迹应用 `isHistory=false`。

#### 🟠 ENGINE-BUG-2：事件标记 `ts` 字段完全未使用，没有 2 秒气泡效果

`eventMarker.ts` 接收 `ts?: string` 但从不读取，所有历史事件标记永久显示，无淡出效果。

#### 🟠 ENGINE-BUG-3：`heatmap.ts` `Math.max(...cells.map(...))` 可能栈溢出

大数组下 `Math.max(...arr)` 会超过调用栈限制，应改为 `arr.reduce`。

#### 🟡 ENGINE-BUG-4：`isRelated` 永远是 `false`，"只看我的虾"模式下相关用户无青色标记

```typescript
// renderer.ts line 98
const isRelated = false  // 硬编码，永不激活
```

#### 🟡 ENGINE-BUG-5：`drawTrailUpTo` 中 `isHistory` 硬编码为 `true`，回放轨迹永远淡显

```typescript
// trail.ts line 49
drawTrail(ctx, pts, color, vp, maxPoints, true)  // 应为 false
```

#### 🟡 ENGINE-BUG-6：所有 canvas 绘制调用无 `ctx.save()/restore()`

canvas 状态（shadowBlur, globalAlpha, lineWidth 等）在各层之间泄漏。

---

## 7. 端到端数据流分析

### Live 模式

```
[后端 WorldState] ──2s轮询──▶ [/ws/observe]
      │                            │
      │                     snapshot + events
      │                            │
      ▼                            ▼
[world.ts store]  ◀──onmessage── WS client
  setSnapshot()        ✅ 正常工作
  appendLiveEvents()   ✅ 正常工作
      │
      ▼
[WorldMap.vue render()]
  worldStore.onlineUsers  ─── ✅ Pinia computed，正确展开
  worldStore.livePoints   ─── ✅ 正常
  worldStore.liveEvents   ─── ✅ 正常（2s expireAt 在 purgeExpiredEvents 里处理）
      │
      ▼
[renderFrame()]
  crawfish 绘制  ✅
  trail 绘制     ⚠️ isHistory=true → 轨迹过淡（ENGINE-BUG-1）
  事件标记       ✅ 显示，但无时间过滤（ENGINE-BUG-2）
```

**Live 模式基本可用，主要问题：轨迹颜色过淡。**

---

### Replay 模式

```
用户点击"⏪ 回放"
    │
    ▼
WorldToolbar emits 'enter-replay'  ✅
    │
    ▼
WorldMap.vue showReplayModal = true  ✅
    │
    ▼
ReplayModal 选时间窗口，确认
    │
    ▼
onReplayConfirm(window)
  worldStore.mode = 'replay'   ← 直接写 Ref，绕过 action，但有效
  replayStore.enterReplayMode() ← 改变 WorldMap 的实例 A
  replayStore.loadReplay(window)
    ├─ GET /api/world/history ✅
    ├─ GET /api/world/events 或 /social ✅
    └─ GET /api/world/heatmap ✅
    │
    ▼ 数据加载完成
  WorldMap.vue：isReplayMode.value = true（因读 replayStore 实例 A）
    │
    ▼
replay-banner 出现 ✅（v-if="isReplayMode"）
ReplayBar 挂载 ✅（v-if="isReplayMode"）
    │
    ├─ ReplayBar.vue 调用 useReplayStore() ←── 得到实例 B（空！）🔴
    │   rangeStart = null → 滑块 0→1
    │   replaying = Ref 对象（truthy）→ 永远执行 pause()，不能播放
    │
    ├─ WorldToolbar.vue 调用 useReplayStore() ←── 得到实例 C（空！）🔴
    │   isReplay 永远 false → badge 不显示
    │
    └─ WorldMap.vue render()
        isReplay = isReplayMode.value = true ✅
        users = replayStore.crawfishPositions.value → undefined 🔴
        → renderFrame 收到空 users/trails
        → 地图看起来没变化
```

**Replay 模式：Banner 出现，但 ReplayBar 无数据、播放按钮失效、Toolbar 不变、地图不变。**

---

## 8. Bug 汇总优先级表

### 🔴 P0 — 必须修复，功能完全无法使用

| ID | 位置 | 描述 | 修复方案 |
|---|---|---|---|
| STORE-BUG-1 | `stores/replay.ts` | 不是 Pinia store，每组件独立实例 | 改用 `defineStore('replay', () => {...})` |
| COMP-BUG-1 | `WorldMap.vue` render() | `.value` 调用在 Pinia 展开后的值上 → undefined | STORE-BUG-1 修复后去掉所有 `.value` |
| COMP-BUG-5 | `ReplayBar.vue` | `store.replaying` 是 Ref 对象，永远 truthy → 不能播放 | STORE-BUG-1 修复后自动解决 |
| COMP-BUG-7 | `WorldToolbar.vue` | `isReplay` 读独立实例，永远 false | STORE-BUG-1 修复后自动解决 |

### 🟠 P1 — 功能部分失效

| ID | 位置 | 描述 | 修复方案 |
|---|---|---|---|
| STORE-BUG-2 | `replay.ts reset()` | reset 定位到 rangeEnd，不是 rangeStart | 改为 `rangeStart.value` |
| STORE-BUG-3 | `replay.ts play()` | 1x 速度播 24h 需要 24 真实小时 | step 改为 `60_000 * speed`（分钟级） |
| API-BUG-1 | `world.py history` | 有 token 时 points 无 user_id/user_name | API 补充字段，或前端用已知 myUserId 填充 |
| API-BUG-2 | `world.py social` | social events 无 user_name | API 补充字段 |
| ENGINE-BUG-1 | `renderer.ts` | live 轨迹 `isHistory=true`，颜色过淡 | 改为 `false` |
| ENGINE-BUG-2 | `eventMarker.ts` | 事件标记无时间过滤，全部历史永久显示 | 实现 2s 气泡逻辑 |
| COMP-BUG-2 | `WorldMap.vue` | replay 模式 hover 用 live users | 按 mode 切换 hover 数据源 |

### 🟡 P2 — 体验问题

| ID | 位置 | 描述 |
|---|---|---|
| ENGINE-BUG-3 | `heatmap.ts` | Math.max 大数组栈溢出风险 |
| ENGINE-BUG-4 | `renderer.ts` | isRelated 硬编码 false，青色环永不显示 |
| ENGINE-BUG-5 | `trail.ts` | replay 轨迹 isHistory=true，颜色淡 |
| ENGINE-BUG-6 | 所有引擎文件 | 无 ctx.save/restore，canvas 状态泄漏 |
| COMP-BUG-3 | `WorldMap.vue` | watch 监听 Ref 对象本身（STORE-BUG-1 修复后自动解决） |
| COMP-BUG-4 | `WorldMap.vue` | 进入回放未断开 WS，短暂双连接 |
| DB-NOTE-1 | `models.py` | EventMarker 表从未被使用，可以删除 |

---

## 修复路线图

### Step 1（解锁一切）：修复 STORE-BUG-1

```typescript
// stores/replay.ts
import { defineStore } from 'pinia'

export const useReplayStore = defineStore('replay', () => {
  // ... 完全相同的内部实现，无需改动
})
```

这一个改动会让 COMP-BUG-1、COMP-BUG-3、COMP-BUG-5、COMP-BUG-7 全部自动消失（它们都是 STORE-BUG-1 的连锁反应），同时要把 `WorldMap.vue render()` 里的所有 `.value` 调用去掉。

### Step 2：修复 play() 步进速度（STORE-BUG-3）

### Step 3：修复 reset() 方向（STORE-BUG-2）

### Step 4：修复 live 轨迹颜色（ENGINE-BUG-1）

### Step 5：修复 API 响应缺失 user_id/user_name（API-BUG-1/2）

---

*此文档由全面代码审计自动生成，涵盖 models.py、ws_server.py、world.py、stores/world.ts、stores/replay.ts、components/WorldMap.vue、components/ReplayBar.vue、components/WorldToolbar.vue 及 engine/ 目录全部文件。*
