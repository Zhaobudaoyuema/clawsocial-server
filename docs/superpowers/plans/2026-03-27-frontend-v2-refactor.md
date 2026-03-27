# ClawSocial v2 前端适配实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端适配后端 v2 重构，对齐 `/ws/observe` 统一端点和新的 API

**Architecture:**
- 所有 WebSocket 连接统一改为 `/ws/observe?type=world` 或 `/ws/observe?type=crawler&token=xxx`
- 消息类型更新：`global_snapshot` → `snapshot`，`step_context` → `crawler`
- CrawlerView 同时连接 world（地图实时位置）和 crawler（个人数据）两个通道
- 新增 API 端点接入：`/api/client/history/*` 和 `/api/world/homepage/{user_id}`

**Tech Stack:** Vue 3, TypeScript, Pinia, WebSocket, Vite

---

## 文件变更总览

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `website/src/composables/useCrawlerWs.ts` | 重写 | 适配 `/ws/observe?type=crawler` |
| `website/src/components/WorldMap.vue` | 修改 | WebSocket URL 改为 `/ws/observe?type=world` |
| `website/src/components/EventList.vue` | 修改 | WebSocket URL 改为 `/ws/observe?type=world` |
| `website/src/components/ShareMap.vue` | 修改 | WebSocket URL 改为 `/ws/observe?type=world` |
| `website/src/components/HeroPreview.vue` | 修改 | WebSocket URL 改为 `/ws/observe?type=world` |
| `website/world/src/composables/useWorldWs.ts` | 修改 | WebSocket URL 改为 `/ws/observe?type=world` |
| `website/src/components/CrawlerPanel.vue` | 修改 | 接入 `/api/client/history/social` 获取事件 |

---

## Task 1: 重构 useCrawlerWs.ts

**Files:**
- Modify: `website/src/composables/useCrawlerWs.ts`

### 1.1 重写 WebSocket 连接

- [ ] **Step 1: 重写 useCrawlerWs.ts**

用以下内容替换整个文件：

```typescript
/**
 * useCrawlerWs — 个人龙虾 WebSocket 连接
 *
 * 连接：/ws/observe?type=crawler&token=xxx
 *
 * 消息类型：
 *   ready       — 连接成功，包含用户基本信息
 *   crawler     — 个人龙虾实时数据（位置 + 今日事件）
 *   error       — 错误推送
 */
import { ref } from 'vue'
import { useCrawlerStore } from '../stores/crawler'
import type { SocialEvent } from '../stores/world'

export function useCrawlerWs() {
  const crawlerStore = useCrawlerStore()
  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect(token: string) {
    if (ws) {
      ws.close()
      ws = null
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws/observe?type=crawler&token=${encodeURIComponent(token)}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      crawlerStore.connected = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    ws.onclose = () => {
      connected.value = false
      crawlerStore.connected = false
      ws = null
      // 自动重连（3秒后）
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          if (token) connect(token)
        }, 3000)
      }
    }

    ws.onerror = () => {
      ws?.close()
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string) as Record<string, unknown>

        if (msg.type === 'ready') {
          // 连接成功
          const user = msg.user as { id: number; name: string }
          crawlerStore.userId = user.id
          crawlerStore.userName = user.name
        } else if (msg.type === 'crawler') {
          // 个人龙虾数据更新
          // msg.x, msg.y: 当前位置
          // msg.events: 今日事件列表
          crawlerStore.x = msg.x as number
          crawlerStore.y = msg.y as number
          crawlerStore.online = true

          // 更新事件列表
          const events = (msg.events as Array<Record<string, unknown>>) || []
          crawlerStore.events = events.map((e) => ({
            type: e.type as SocialEvent['type'],
            other_user_id: e.other_user_id as number | null,
            other_name: e.other_user_name as string | undefined,
            x: e.x as number | null,
            y: e.y as number | null,
            ts: e.ts as string,
          }))
        }
      } catch {
        // ignore parse errors
      }
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
    crawlerStore.connected = false
  }

  return { connected, connect, disconnect }
}
```

- [ ] **Step 2: 更新 crawlerStore 的类型定义**

在 `website/src/stores/crawler.ts` 中，SocialEvent 类型需要从 `website/src/stores/world.ts` 导入，或者内联定义。确认 `SocialEvent` 接口与后端 `crawler` 消息的 events 数组匹配。

当前 `crawlerStore.ts` 已有 `SocialEvent` 内联定义，检查是否与 `world.ts` 中的一致。

- [ ] **Step 3: 提交**

```bash
git add website/src/composables/useCrawlerWs.ts
git commit -m "feat(frontend): 重构 useCrawlerWs 适配 /ws/observe?type=crawler"
```

---

## Task 2: 更新 WorldMap.vue WebSocket 连接

**Files:**
- Modify: `website/src/components/WorldMap.vue:111-129`

### 2.1 更新 WebSocket URL

- [ ] **Step 1: 修改 connectWs 函数中的 URL**

将 `connectWs` 函数中的 URL：
```javascript
const url = `${protocol}//${location.host}/ws/observer`
```

改为：
```javascript
const url = `${protocol}//${location.host}/ws/observe?type=world`
```

消息类型 `msg.type === 'snapshot'` 已正确，无需修改。

- [ ] **Step 2: 提交**

```bash
git add website/src/components/WorldMap.vue
git commit -m "feat(frontend): WorldMap WebSocket 改为 /ws/observe?type=world"
```

---

## Task 3: 更新其他组件的 WebSocket 连接

**Files:**
- Modify: `website/src/components/EventList.vue`
- Modify: `website/src/components/ShareMap.vue`
- Modify: `website/src/components/HeroPreview.vue`
- Modify: `website/world/src/composables/useWorldWs.ts`

### 3.1 EventList.vue

- [ ] **Step 1: 更新 WebSocket URL**

在 `connectWs` 函数中，将 `/ws/observer` 改为 `/ws/observe?type=world`。

消息类型 `msg.type === 'event'` 保持不变（后端 world 模式目前不推送此类型，但这不影响——前端会静默忽略未知类型）。

### 3.2 ShareMap.vue

- [ ] **Step 1: 更新 WebSocket URL**

将 `/ws/observer` 改为 `/ws/observe?type=world`。

### 3.3 HeroPreview.vue

- [ ] **Step 1: 查找并更新 WebSocket 连接**

找到 HeroPreview.vue 中连接 `/ws/observer` 的地方，改为 `/ws/observe?type=world`。

（如果 HeroPreview 使用的是轮询而非 WebSocket，检查是否需要改为 SSE）

### 3.4 world/src/composables/useWorldWs.ts

- [ ] **Step 1: 更新 WebSocket URL**

将 `/ws/world/observer` 改为 `/ws/observe?type=world`。

- [ ] **Step 2: 更新消息类型映射**

将 `handleMessage` 中的 `case 'global_snapshot'` 改为 `case 'snapshot'`：
```typescript
case 'snapshot': {
  // 原来 case 'global_snapshot' 的逻辑
  const users = msg.users as Array<Record<string, unknown>>
  store.setSnapshot(users.map(u => ({
    user_id: u.user_id as number,
    name: (u.name as string | undefined) ?? '',
    x: u.x as number,
    y: u.y as number,
  })))
  break
}
```

- [ ] **Step 3: 提交**

```bash
git add website/src/components/EventList.vue website/src/components/ShareMap.vue website/src/components/HeroPreview.vue website/world/src/composables/useWorldWs.ts
git commit -m "feat(frontend): 统一 WebSocket 为 /ws/observe?type=world"
```

---

## Task 4: CrawlerPanel 接入 /api/client/history

**Files:**
- Modify: `website/src/components/CrawlerPanel.vue`

### 4.1 更新事件加载

当前 CrawlerPanel.vue 中的事件列表是通过 `/ws/crawler` 推送的。现在 `/ws/observe?type=crawler` 也推送事件，但 CrawlerPanel 在 onMounted 时主动拉取历史数据。

检查 CrawlerPanel 中的 `onMounted` 逻辑，看是否需要改为调用 `/api/client/history/social` 而非其他端点。

- [ ] **Step 1: 检查 CrawlerPanel 事件加载逻辑**

读取 `CrawlerPanel.vue` 的完整 script 部分，确认事件是如何加载的。

- [ ] **Step 2: 如需要，修改为使用 `/api/client/history/social`**

如果 CrawlerPanel 主动拉取历史事件，将请求改为：
```
GET /api/client/history/social?limit=20
Headers: X-Token: {token}
```

### 4.2 提交

```bash
git add website/src/components/CrawlerPanel.vue
git commit -m "feat(frontend): CrawlerPanel 适配新 API"
```

---

## Task 5: 构建验证

- [ ] **Step 1: 运行前端构建**

```bash
cd website && npm run build
```

预期：构建成功，无编译错误。

- [ ] **Step 2: 提交**

```bash
git add website/
git commit -m "chore(frontend): v2 架构适配完成"
```

---

## 自检清单

1. **Spec 覆盖检查：**
   - ✅ useCrawlerWs.ts 重构 → Task 1
   - ✅ WorldMap.vue URL → Task 2
   - ✅ EventList/ShareMap/HeroPreview/useWorldWs URL → Task 3
   - ✅ CrawlerPanel API → Task 4
   - ✅ 构建验证 → Task 5

2. **占位符扫描：** 无 TBD/TODO

3. **类型一致性：**
   - `crawler` 消息的 `events` 数组字段：`other_user_name`（新字段），前端需要对应
   - `/ws/observe?type=crawler` 返回的 `crawler` 消息格式已在 Task 1 中对齐

---

## 计划完成

计划已保存到 `docs/superpowers/plans/2026-03-27-frontend-v2-refactor.md`。

**两个执行选项：**

**1. Subagent-Driven（推荐）** — 每个 Task 由独立 subagent 执行，有检查点

**2. Inline Execution** — 在本 session 内顺序执行

**选择哪个方式？**
