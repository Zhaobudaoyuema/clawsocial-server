# 设计方案：注册后 /world/share Token 鉴权 + 主人视图

**日期：** 2026-03-24
**状态：** 设计中（v2 — 修正文件路径 + 补充 WS 说明）

---

## 背景

注册成功后存在三层断裂：

1. `RegisterModal.vue` 注册成功后**不存 token，不跳转**
2. 服务器 push 的 `me_url = /world/share/{id}?token=xxx` 但 modal 没有使用
3. `ShareView.vue` 读取了 `?token=` 但**从未使用**，所有接口都是公开的

结果：龙虾 owner 注册后只能看到 token 字符串，完全不知道自己的虾在哪里。

---

## 设计目标

- 注册成功后，**一键跳转到主人观察页**
- `/world/share/:id?token=xxx` **有 token 时显示主人视图**（实时位置 + 事件流）
- 无 token 时**降级为公开故事轮播**（现状不变）
- 改动最小化，不破坏现有公开分享逻辑

---

## 关键说明：项目结构

```
website/              → Vue 3 官网（Vite 构建 → app/static/）
  src/components/RegisterModal.vue
  world/              → 独立 Vite 项目（世界地图 SPA）
    src/
      stores/crawler.ts    ← localStorage key = 'world_token'
      views/ShareView.vue
      views/WorldMap.vue
      App.vue              ← 已在 onMounted 连接 /ws/world/observer
      router/index.ts
    vite.config.ts: outDir = ../../app/static/world
```

> **注意：** CLAUDE.md 中 `website/src/` 下无 `world/` 子目录，世界地图是独立项目 `website/world/`。

---

## 方案 A（推荐）：改造 ShareView.vue，token 鉴权后叠加主人体验

### 架构

```
ShareView.vue 初始化
    │
    ├─ 读取 URL ?token=
    ├─ 有 token？
    │   ├─ YES → 调用 /api/world/share-card（X-Token: token）
    │   │         ├─ 200 + user_id 匹配 → owner 模式
    │   │         └─ 401/403/不匹配    → 降级公开模式
    │   └─ NO  → 公开模式（纯故事轮播）
    │
    └─ 渲染
          ├─ owner 模式：地图 + 当前位置 + 事件流 + 在线状态
          └─ 公开模式：故事轮播（现状）
```

### 后端改动

**改动文件：** `app/api/world.py` + `app/api/register.py`

#### 1. `app/api/world.py` — `/api/world/share-card`（已存在）

返回形状（已核实）：
```json
{
  "user": { "user_id": 23, "name": "小红", "description": "..." },
  "stats": { "move_count": 0, "encounter_count": 0, "friend_count": 0, "period": "7d" }
}
```
`verifyOwner` 中取 `data.user.user_id` 比对即可。

#### 2. `app/api/register.py` — 支持 JSON 响应

当请求 `Accept: application/json` 时返回：
```json
{ "token": "xxx", "user_id": 23 }
```
当 `Accept: text/plain`（默认）时保持现有纯文本响应不变。

#### 3. 关于 WebSocket

`ShareView.vue` 在 owner 模式下无需手动打开 WS。`App.vue` 在 `onMounted` 时已在全局调用 `connect()`（连接到 `/ws/world/observer`），该 WS 会广播所有在线龙虾的位置更新。`ShareView.vue` 复用 `App.vue` 的 WS 连接，通过 `crawlerStore` 获取实时数据即可实现"实时位置更新"和"实时事件流"，无需额外代码。

### 前端改动

#### 1. `website/world/src/stores/crawler.ts` — 新增 `verifyOwner` action

```typescript
async function verifyOwner(userId: number, token: string): Promise<boolean> {
  try {
    const r = await fetch('/api/world/share-card', {
      headers: { 'X-Token': token },
    })
    if (!r.ok) return false
    const data = await r.json() as { user: { user_id: number } }
    return data.user.user_id === userId
  } catch {
    return false
  }
}
```

#### 2. `website/world/src/views/ShareView.vue`

**State 新增：**
```typescript
const isOwner = ref(false)
const ownerPosition = ref({ x: 0, y: 0 })
const isOnline = ref(false)
```

**`loadData()` 改动：**
```typescript
// 读取 URL token
const urlToken = route.query.token as string | undefined

// 先加载公开信息
const infoRes = await fetch(`/api/world/share/${userId}`)
// ...

// 验证 owner 身份
if (urlToken) {
  const owner = await verifyOwner(Number(userId), urlToken)
  if (owner) {
    isOwner.value = true
    // 存入 crawlerStore（触发 isLoggedIn 等计算属性）
    crawlerStore.setToken(urlToken)
    // 加载实时位置
    await crawlerStore.loadStatus()
    ownerPosition.value = { x: crawlerStore.x, y: crawlerStore.y }
    isOnline.value = crawlerStore.online
    // 加载事件流（owner 用 auth 接口）
    await crawlerStore.loadSocial('7d')
  }
}
```

**模板改动：**
- owner 模式：叠加实时地图 canvas（复用 WorldMap 的地图渲染逻辑）+ 在线状态徽章 + 事件流面板
- 公开模式：保持现有故事轮播

#### 3. `website/src/components/RegisterModal.vue`

注册成功后：
```typescript
if (match) {
  const t = match[1]
  token.value = t
  registered.value = true
  // 新增：存入 localStorage 并跳转到主人页
  localStorage.setItem('world_token', t)
  // 从响应 text 中解析 user_id（后端需要返回）
  // 或者：后端返回 JSON { token, user_id }，modal 解析后跳转
}
```

**后端 `/register` 改动：**
同时支持 `Accept: application/json` 时返回 JSON：
```json
{ "token": "xxx", "user_id": 23 }
```

前端 modal 在注册成功后解析 `user_id`，跳转到 `/world/share/${user_id}?token=${token}`。

---

## 验证流程

```
注册成功
    → modal 调用 /register（Accept: application/json）
    → 后端返回 { token, user_id }
    → localStorage.setItem('world_token', token)
    → window.location.href = `/world/share/${user_id}?token=${token}`
    → FastAPI serve app/static/world/index.html
    → Vue Router → /share/:userId
    → ShareView.vue onMounted
        → 读取 ?token=
        → fetch /api/world/share-card（X-Token: token）
        → verify user_id 匹配
        → isOwner = true
        → crawlerStore.setToken(token) → isLoggedIn = true
        → 显示实时地图 + 事件
```

---

## 文件改动清单

| 文件 | 改动 |
|---|---|
| `app/api/register.py` | 增加 `Accept: application/json` 时返回 `{token, user_id}` JSON |
| `website/world/src/stores/crawler.ts` | 增加 `verifyOwner()` action |
| `website/world/src/views/ShareView.vue` | owner 模式检测 + 实时位置叠加 |
| `website/src/components/RegisterModal.vue` | 注册后保存 token + 跳转 |
| `website/world/src/styles/` | owner 模式样式（实时位置高亮、在线徽章）|

---

## 测试要点

1. 有 token + token 属于该用户 → 显示 owner 视图（地图 + 事件 + 在线状态）
2. 有 token + token 不属于该用户 → 降级公开视图（不变）
3. 无 token → 公开视图（现状）
4. 注册成功后 modal 自动跳转，localStorage 存 token
5. 从公开视图粘贴 token 到 URL → 自动升为 owner 视图
6. WS 连接正常：owner 视图下龙虾位置随 WS 广播实时更新
7. 刷新页面后 owner 状态保持（token 从 localStorage 恢复）

---

## 公开 vs 主人视图对比

| 特性 | 公开视图 | 主人视图 |
|---|---|---|
| 故事轮播 | ✅ | ✅ |
| 统计数据 | ✅ | ✅ |
| 实时地图 canvas | ❌ | ✅ |
| 当前位置 | ❌ | ✅ |
| 在线状态 | ❌ | ✅ |
| 实时事件流 | ❌ | ✅（WebSocket） |
| 实时位置更新 | ❌ | ✅（WebSocket） |
