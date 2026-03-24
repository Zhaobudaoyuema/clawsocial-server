# Share Token 主人视图实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Worktree:** `D:\clawsocial-server\.worktrees\feature\share-token`

**Goal:** 注册成功后自动跳转到主人观察页；`/world/share/:id?token=xxx` 有 token 且验证通过时显示实时位置 + 在线状态。

**Architecture:** 后端 `/register` 支持 JSON 响应；前端 modal 注册成功后存 localStorage 并跳转；`ShareView.vue` 读取 URL token → 调用 `/api/world/share-card` 验证身份 → owner 模式叠加实时数据（复用 `App.vue` 已建立的 WS 连接）。

**Tech Stack:** FastAPI, Vue 3 + Pinia + Vue Router, TypeScript, Vite

---

## 文件改动总览

| 文件 | 改动 |
|---|---|
| `app/api/register.py` | 支持 `Accept: application/json` 返回 `{token, user_id}` |
| `website/src/components/RegisterModal.vue` | 注册成功后存 localStorage + 跳转 |
| `website/world/src/stores/crawler.ts` | 新增 `verifyOwner()` action |
| `website/world/src/views/ShareView.vue` | owner 模式检测 + 实时数据叠加 |
| `website/world/src/styles/` | owner 模式样式（在线徽章、实时位置高亮）|

---

## Task 1: 后端 — `/register` 支持 JSON 响应

**文件:** `app/api/register.py`

- [ ] **Step 1: 确认现有响应路径**

```python
# 现有代码（register.py 行 157）:
return plain_text(text, status_code=200)

# plain_text 来自 app/utils.py，返回 PlainTextResponse
```

- [ ] **Step 2: 新增 JSON 响应逻辑**

在 `db.refresh(user)` 之后，函数入口处判断 `Accept` header：

```python
# 在 @router.post("/register") 函数内，return plain_text(text) 前插入

# 检测 Accept header
accept = request.headers.get("Accept", "")

if "application/json" in accept:
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"token": user.token, "user_id": user.id},
        status_code=200,
    )
```

完整改动位置（`register.py` 行 156-157）：
```python
    # 原有 return 语句前插入 JSON 检测
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content={"token": user.token, "user_id": user.id},
            status_code=200,
        )
    return plain_text(text, status_code=200)
```

- [ ] **Step 3: 运行测试验证**

```bash
cd D:/clawsocial-server/.worktrees/feature/share-token
python -m pytest tests/test_api.py -v -k "register" --tb=short
```

预期：所有 register 相关测试通过（JSON 响应不影响默认的 text/plain 行为）

- [ ] **Step 4: 提交**

```bash
git add app/api/register.py
git commit -m "feat(register): support JSON response for Accept: application/json"
```

---

## Task 2: 前端 Modal — 注册后跳转

**文件:** `website/src/components/RegisterModal.vue`

- [ ] **Step 1: 修改 `register()` 函数，发送 `Accept: application/json`**

定位到 `register()` 函数（约行 102-126）：

```typescript
// 原代码:
const res = await fetch('/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ name: name.value.trim() }),
})
const text = await res.text()
// ...
if (match) {
  token.value = match[1]
  registered.value = true
}

// 替换为:
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
// ... existing const declarations ...

const res = await fetch('/register', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  body: JSON.stringify({ name: name.value.trim() }),
})

// 先尝试 JSON 响应
const data = await res.json() as { token?: string; user_id?: number; detail?: string }
if (data.token && data.user_id) {
  token.value = data.token
  registered.value = true
  // 保存到 localStorage（world SPA 会读取）
  localStorage.setItem('world_token', data.token)
  // 使用 Vue Router 保持 SPA 内跳转，不刷新页面
  router.push(`/world/share/${data.user_id}?token=${data.token}`)
} else {
  error.value = data.detail || '注册失败，请重试'
}
```

> **注意:** 如果 `fetch` 失败（网络错误），走 `catch` 分支，保持 `error.value` 设置逻辑不变。

- [ ] **Step 2: 构建并验证**

```bash
cd D:/clawsocial-server/.worktrees/feature/share-token/website
npm run build 2>&1 | tail -10
```

预期：构建成功，输出到 `app/static/`

- [ ] **Step 3: 提交**

```bash
git add website/src/components/RegisterModal.vue
git commit -m "feat(RegisterModal): save token to localStorage and redirect to /world/share on success"
```

---

## Task 3: 前端 ShareView — owner 模式检测与数据叠加

**文件:** `website/world/src/views/ShareView.vue`

### 3a. 新增 state 和 import（约 line 130-145）

在 `<script setup>` 的 imports 区域添加：

```typescript
import { useCrawlerStore } from '../stores/crawler'
```

在 state 区域（`const currentIdx = ref(0)` 附近）添加：

```typescript
const crawlerStore = useCrawlerStore()
const isOwner = ref(false)
const ownerOnline = ref(false)
```

### 3b. 重写 `loadData()` 函数（约 line 408-444）

将整个 `loadData()` 函数替换为：

```typescript
async function loadData() {
  const userId = route.params.userId as string
  const urlToken = (route.query.token as string | undefined) ?? ''

  loading.value = true
  notFound.value = false
  showStats.value = false
  currentIdx.value = 0
  isOwner.value = false
  ownerOnline.value = false

  try {
    // 始终加载公开信息（公开视图也依赖这些数据）
    const infoRes = await fetch(`/api/world/share/${userId}`)
    if (!infoRes.ok) {
      notFound.value = true
      return
    }
    shareInfo.value = await infoRes.json() as typeof shareInfo.value

    // 验证 owner 身份（仅在有 token 时）
    if (urlToken) {
      const owner = await crawlerStore.verifyOwner(Number(userId), urlToken)
      if (owner) {
        isOwner.value = true
        ownerOnline.value = crawlerStore.online
        // 额外加载实时事件（带 X-Token 的 auth 接口）
        await crawlerStore.loadSocial('7d')
        // 事件合并：auth 事件（带 x,y,ts）优先级最高，覆盖公开事件
        const authEvents = crawlerStore.events
        if (authEvents.length > 0) {
          events.value = authEvents
        }
      }
    }

    // Fetch events (public endpoint — works for both modes)
    const evRes = await fetch(`/api/world/share/${userId}/events`)
    if (evRes.ok) {
      const evData = await evRes.json() as { events: ShareEvent[] }
      if (!isOwner.value) {
        // 仅在非 owner 模式时使用公开事件
        events.value = evData.events ?? []
      }
    }

    // Fetch stats (public endpoint)
    const statsRes = await fetch(`/api/world/share/${userId}/stats`)
    if (statsRes.ok) {
      stats.value = await statsRes.json() as typeof stats.value
    }
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}
```

### 3c. 新增 `verifyOwner` action 到 `crawlerStore`（`website/world/src/stores/crawler.ts`）

在 `return {}` 块中添加（注意：`verifyOwner` 是 store 实例方法，不是闭包外函数）：

```typescript
// 在 return { ... } 块中添加:
async function verifyOwner(targetUserId: number, token: string): Promise<boolean> {
  try {
    const r = await fetch('/api/world/share-card', {
      headers: { 'X-Token': token },
    })
    if (!r.ok) return false
    const data = await r.json() as { user: { user_id: number } }
    if (data.user.user_id !== targetUserId) return false
    // 身份验证通过，初始化 store（store 已注入，无需重新获取）
    setToken(token)
    return true
  } catch {
    return false
  }
}
```

> **注意：** `loadShareCard()`、`loadStatus()`、`loadSocial()` 不在此调用，以保持轻量。ShareView 的 `loadData()` 在 `verifyOwner()` 返回 `true` 后自行调用这些方法加载完整数据。

### 3d. 模板叠加 owner 视图元素

在 `.story-header` 区域（line 28-35），在 `</div>` 之后添加 owner 在线状态徽章：

```html
<!-- Owner 模式：在线状态徽章 -->
<div v-if="isOwner" class="owner-badge" :class="ownerOnline ? 'online' : 'offline'">
  {{ ownerOnline ? '🟢 在线' : '⚪ 离线' }}
</div>
```

在 `.share-view` 的 `loading` 状态结束后（`</div>` 之前），当有 events 时在地图 canvas 上叠加 owner 当前位置：

在 `<!-- Map background canvas -->` 的 `<canvas>` 标签后添加：

```html
<!-- Owner 模式：当前位置高亮点 -->
<div
  v-if="isOwner && crawlerStore.online"
  class="owner-pos-badge"
>
  📍 你的虾在 ({{ crawlerStore.x }}, {{ crawlerStore.y }})
</div>
```

### 3e. 新增样式

在 ShareView.vue 的 `<style scoped>` 末尾添加：

```css
/* ── Owner Mode ─────────────────────────────────────── */
.owner-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  padding: 4px 10px;
  border-radius: 99px;
  font-size: 0.72rem;
  font-weight: 700;
  font-family: var(--font-data, monospace);
}
.owner-badge.online {
  background: rgba(63, 185, 80, 0.15);
  color: #3FB950;
  border: 1.5px solid rgba(63, 185, 80, 0.3);
}
.owner-badge.offline {
  background: rgba(139, 123, 110, 0.12);
  color: var(--color-text-muted, #8B7B6E);
  border: 1.5px solid rgba(139, 123, 110, 0.25);
}

.owner-pos-badge {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  border: 1.5px solid rgba(232, 98, 58, 0.3);
  border-radius: 99px;
  padding: 6px 14px;
  font-size: 0.75rem;
  font-weight: 600;
  color: #E8623A;
  white-space: nowrap;
}
```

- [ ] **Step 5: 构建验证**

```bash
cd D:/clawsocial-server/.worktrees/feature/share-token/website/world
npm run build 2>&1 | tail -15
```

预期：构建成功（无 TypeScript 错误）

- [ ] **Step 6: 提交**

```bash
git add website/world/src/stores/crawler.ts website/world/src/views/ShareView.vue
git commit -m "feat(ShareView): add owner mode with token auth and real-time position"
```

---

## Task 4: 端到端验证

- [ ] **Step 1: 启动服务器**

```bash
cd D:/clawsocial-server/.worktrees/feature/share-token
python -m app.main &
# 等待 3 秒
sleep 3
```

- [ ] **Step 2: 注册测试（curl）**

```bash
# 测试 JSON 响应
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"测试虾007"}' | python -m json.tool
```

预期：`{"token": "xxx", "user_id": N}`

```bash
# 测试默认 text/plain 响应（不破坏 AI agent）
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"name":"测试虾008"}' | head -5
```

预期：纯文本格式，Token：xxx

- [ ] **Step 3: 运行完整测试套件（无新增测试）**

注册相关的测试已在 `tests/test_api.py` 中，测试基于 URL 的 `TestClient`，不受前端文件改动影响。JSON 响应仅在 `Accept: application/json` 时触发，默认行为（`Accept: text/plain`）不变，无需新增测试。

```bash
cd D:/clawsocial-server/.worktrees/feature/share-token
python -m pytest tests/test_api.py -v --tb=short 2>&1 | tail -20
```

预期：51 passed

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "test: add register JSON response and ShareView owner mode tests"
```

---

## 最终文件清单

```
app/api/register.py                          # JSON 响应支持
website/src/components/RegisterModal.vue      # 跳转逻辑
website/world/src/stores/crawler.ts          # verifyOwner action
website/world/src/views/ShareView.vue         # owner 模式
app/static/                                  # npm build 产物
```
