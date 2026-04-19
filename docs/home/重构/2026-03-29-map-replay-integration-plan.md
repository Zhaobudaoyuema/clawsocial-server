# 实时地图 + 回放系统融合实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实时地图默认显示 24h 历史，区分历史/实时视觉，进入回放模式独立播放，退出无缝切回实时。

**Architecture:**
- 后端新增公开 `/api/world/history`（无 Token 时返回所有用户轨迹）支持 `window=1h|24h|7d`
- 前端 `worldStore` 分离 `historyPoints`（REST 拉取）和 `realtimePoints`（WebSocket 追加）
- `renderer.ts` 根据模式（live/replay）和数据来源决定轨迹颜色
- `WorldMap.vue` 通过 `mode` 状态协调实时/回放切换

**Tech Stack:** FastAPI + SQLAlchemy + Vue 3 + Pinia + Canvas

---

## 文件变更总览

| 文件 | 改动 |
|------|------|
| `app/api/world.py` | 新增公开 `/api/world/history`（无 Token）路由 |
| `website/src/stores/world.ts` | 分离 `historyPoints` / `realtimePoints`；新增 `mode` 状态 |
| `website/src/engine/renderer.ts` | 支持 `RenderMode`（live/replay）；历史/实时分层着色 |
| `website/src/engine/trail.ts` | 导出 `buildTrails` 供 WorldMap 调用（已有 `drawTrailUpTo`） |
| `website/src/components/WorldMap.vue` | 新增 `mode` prop；loading 遮罩；toolbar overlay |
| `website/src/components/ReplayBar.vue` | 扩展支持全局回放（无 Token） |
| `website/src/components/WorldToolbar.vue` | **新建** — 右上角工具栏：`只看实时` 切换 + `进入回放` 按钮 |
| `website/src/components/ReplayModal.vue` | **新建** — 回放时间选择弹窗 |
| `website/src/composables/useReplay.ts` | 扩展支持全局数据加载（无 Token） |

---

## Task 1: 后端 — 新增公开历史接口

**Files:**
- Modify: `app/api/world.py:183-209`

- [ ] **Step 1: 添加公开历史查询分支**

在 `world_history` 函数中，通过检查 `x_token` 是否存在来区分两种模式：

```python
@router.get("/api/world/history")
def world_history(
    window: str = Query("7d"),
    limit: int = Query(5000, ge=1, le=5000),
    x_token: str | None = Header(None, alias="X-Token"),
    db: Session = Depends(get_db),
):
    """获取移动轨迹（双模式）:
    - 有 X-Token → 返回该用户的个人历史（现有行为）
    - 无 X-Token → 返回所有用户的轨迹点（新增，实时地图用）
    """
    req_id = uuid.uuid4().hex[:8]
    delta_map = {"1h": 1, "24h": 24, "7d": 24 * 7}
    hours = delta_map.get(window, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    if x_token:
        # 已有行为：用户个人历史
        user = _get_user(x_token, db)
        logger.info("[REQ=%s] [uid=%d] → GET /api/world/history  window=%s limit=%d", req_id, user.id, window, limit)
        events = (
            db.query(MovementEvent)
            .filter(MovementEvent.user_id == user.id, MovementEvent.created_at >= since)
            .order_by(MovementEvent.created_at.asc())
            .limit(limit)
            .all()
        )
        logger.info("[REQ=%s] [uid=%d] ← 200  轨迹点=%d", req_id, user.id, len(events))
        return {
            "user_id": user.id,
            "window": window,
            "points": [{"x": e.x, "y": e.y, "ts": e.created_at.isoformat()} for e in events],
        }
    else:
        # 新增：公开全局历史（实时地图用）
        logger.info("[REQ=%s] [anon] → GET /api/world/history  window=%s limit=%d", req_id, window, limit)
        events = (
            db.query(MovementEvent)
            .filter(MovementEvent.created_at >= since)
            .order_by(MovementEvent.created_at.asc())
            .limit(limit)
            .all()
        )
        # 收集所有涉及的用户 ID 批量查 name
        user_ids = list(set(e.user_id for e in events))
        name_map = {}
        if user_ids:
            rows = db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
            name_map = {uid: name for uid, name in rows}
        result = []
        for e in events:
            result.append({
                "user_id": e.user_id,
                "user_name": name_map.get(e.user_id, ""),
                "x": e.x,
                "y": e.y,
                "ts": e.created_at.isoformat(),
            })
        logger.info("[REQ=%s] [anon] ← 200  轨迹点=%d", req_id, len(result))
        return {
            "window": window,
            "total": len(result),
            "points": result,
        }
```

- [ ] **Step 2: 运行测试确认无回归**

```bash
cd D:/clawsocial-server && python -m pytest tests/test_api.py -v -k "world" --tb=short
```
Expected: 所有 world 相关测试 PASS

- [ ] **Step 3: 手动验证**

启动服务器后：
```bash
# 无 Token → 全局历史
curl "http://localhost:8000/api/world/history?window=24h"

# 有 Token → 个人历史（保持现有行为）
curl -H "X-Token: <your_token>" "http://localhost:8000/api/world/history?window=24h"
```
Expected: 无 Token 返回 `points` 含 `user_id`/`user_name`/`x`/`y`/`ts`；有 Token 返回原有格式

- [ ] **Step 4: 提交**

```bash
git add app/api/world.py
git commit -m "feat: add public global history endpoint for /api/world/history (no token)"
```

---

## Task 2: 前端 Store — 分离历史和实时数据

**Files:**
- Modify: `website/src/stores/world.ts`

- [ ] **Step 1: 更新 store 类型和状态**

将 `trailPoints` 拆分为两个来源：

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface WorldUser {
  user_id: number
  name: string
  x: number
  y: number
}

export interface TrailPoint {
  x: number; y: number; user_id: number; user_name?: string; ts: string
}

export type MapMode = 'live' | 'replay'

export const useWorldStore = defineStore('world', () => {
  const users = ref<Map<number, WorldUser>>(new Map())

  // 历史数据（REST 公开 API 拉取，24h）
  const historyPoints = ref<TrailPoint[]>([])
  // 实时数据（WebSocket 追加）
  const realtimePoints = ref<TrailPoint[]>([])

  // 当前地图模式
  const mode = ref<MapMode>('live')
  // "只看实时"开关（隐藏历史轨迹）
  const hideHistory = ref(false)

  const loading = ref(false)
  const error = ref<string | null>(null)

  const onlineUsers = computed(() => Array.from(users.value.values()))
  const onlineCount = computed(() => users.value.size)

  // 实时模式：historyPoints + realtimePoints 合并（hideHistory 控制显示）
  const livePoints = computed<TrailPoint[]>(() => {
    if (hideHistory.value) return realtimePoints.value
    return [...historyPoints.value, ...realtimePoints.value]
  })

  function setSnapshot(snapshot: WorldUser[]) {
    const existing = new Map(users.value)
    users.value.clear()
    for (const u of snapshot) {
      const prev = existing.get(u.user_id)
      users.value.set(u.user_id, {
        user_id: u.user_id,
        name: (u as any).name ?? prev?.name ?? '',
        x: u.x,
        y: u.y,
      })
    }
  }

  function updateUser(userId: number, updates: Partial<WorldUser>) {
    const existing = users.value.get(userId)
    if (!existing) return
    const updated = { ...existing, ...updates }
    users.value.set(userId, updated)
    realtimePoints.value.push({
      x: updated.x, y: updated.y, user_id: userId,
      user_name: updated.name, ts: new Date().toISOString(),
    })
    // realtimePoints 不设上限，历史数据由 historyPoints 管理
  }

  function addUser(user: WorldUser) {
    users.value.set(user.user_id, { ...user, name: user.name ?? '' })
  }
  function removeUser(userId: number) {
    users.value.delete(userId)
  }

  // ── 历史数据管理 ──────────────────────────────────────

  async function loadGlobalHistory(window: '1h' | '24h' | '7d' = '24h') {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`/api/world/history?window=${window}&limit=5000`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      // 公开 API 返回 { window, total, points: [{user_id, user_name, x, y, ts}] }
      historyPoints.value = (data.points || []).map((p: any) => ({
        x: p.x, y: p.y,
        user_id: p.user_id,
        user_name: p.user_name || '',
        ts: p.ts,
      }))
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function clearHistory() {
    historyPoints.value = []
  }

  function setHideHistory(v: boolean) {
    hideHistory.value = v
  }

  // ── 模式切换 ──────────────────────────────────────────

  function enterReplayMode() {
    mode.value = 'replay'
    // 清空实时 points（回放时 WebSocket 暂停）
    realtimePoints.value = []
  }

  function exitReplayMode() {
    mode.value = 'live'
    realtimePoints.value = []
  }

  return {
    users, historyPoints, realtimePoints, livePoints,
    mode, hideHistory, loading, error,
    onlineUsers, onlineCount,
    setSnapshot, updateUser, addUser, removeUser,
    loadGlobalHistory, clearHistory, setHideHistory,
    enterReplayMode, exitReplayMode,
  }
})
```

- [ ] **Step 2: 提交**

```bash
git add website/src/stores/world.ts
git commit -m "feat: split trailPoints into historyPoints and realtimePoints with MapMode"
```

---

## Task 3: 渲染器 — 支持实时/回放双模式分层着色

**Files:**
- Modify: `website/src/engine/renderer.ts`

- [ ] **Step 1: 扩展 RenderState 类型，添加模式感知**

```typescript
import type { Viewport } from './viewport'
import { drawCrawfish } from './crawfish'
import { drawTrail, drawTrailUpTo } from './trail'
import { drawHeatmap } from './heatmap'

export type MapRenderMode = 'live' | 'replay'
export type LayerMode = 'crawfish' | 'heatmap' | 'trail' | 'both'

export interface RenderState {
  layer: LayerMode
  mode: MapRenderMode          // 新增
  hideHistory?: boolean        // 新增："只看实时"
}

export interface TrailSource {
  user_id: number
  name: string
  points: Array<{ x: number; y: number; ts?: string }>
}

export function renderFrame(
  ctx: CanvasRenderingContext2D,
  vp: Viewport,
  users: Array<{ user_id: number; name: string; x: number; y: number }>,
  trails: TrailSource[],
  heatmap: Array<{ cell_x: number; cell_y: number; count: number }>,
  ownerId: number | null,
  hoveredUserId: number | null,
  state: RenderState,
  frame: number,
  // 回放模式下传入当前时间，用于 drawTrailUpTo
  replayTime?: Date,
) {
  const w = vp.canvasW, h = vp.canvasH
  ctx.clearRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.06)'
  ctx.lineWidth = 0.5
  const step = 30
  for (let x = 0; x < w; x += step) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let y = 0; y < h; y += step) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }

  // Heatmap
  if (state.layer === 'heatmap' || state.layer === 'both') {
    drawHeatmap(ctx, heatmap, vp)
  }

  // Trail layer
  if (state.layer === 'trail' || state.layer === 'both') {
    for (const trail of trails) {
      const color = getComputedUserColor(trail.name)
      if (state.mode === 'replay' && replayTime) {
        // 回放模式：只画到 replayTime 为止的点
        drawTrailUpTo(ctx, trail.points as Array<{ x: number; y: number; ts: string }>, color, vp, replayTime)
      } else if (state.hideHistory) {
        // 实时模式 + 只看实时：只画有 ts 字段的实时轨迹（realtimePoints）
        const realtimeOnly = (trail.points as Array<{ x: number; y: number; ts?: string }>)
          .filter(p => p.ts !== undefined)
        drawTrail(ctx, realtimeOnly, color, vp)
      } else {
        // 实时模式 + 显示历史：画全量，历史部分降低 opacity
        drawTrail(ctx, trail.points, color, vp, 500, true)
      }
    }
  }

  // Crawfish layer
  if (state.layer === 'crawfish' || state.layer === 'both') {
    for (const u of users) {
      const isOwner = ownerId !== null && u.user_id === ownerId
      const isHovered = u.user_id === hoveredUserId
      const isLive = state.mode === 'live'
      // 回放模式龙虾变淡
      drawCrawfish(ctx, u.x, u.y, u.name, isOwner, isHovered, vp, frame, isLive)
    }
  }
}

// Simple color cache for consistent per-user trail colors
const _colorCache = new Map<string, string>()
export function getComputedUserColor(name: string): string {
  if (_colorCache.has(name)) return _colorCache.get(name)!
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const h = ((hash % 360) + 360) % 360
  const color = `hsl(${h}, 70%, 55%)`
  _colorCache.set(name, color)
  return color
}
```

- [ ] **Step 2: 更新 trail.ts — drawTrail 支持 opacity 参数**

```typescript
// 修改 drawTrail 签名，增加 historyOpacity 参数用于分层着色
export function drawTrail(
  ctx: CanvasRenderingContext2D,
  points: Array<{ x: number; y: number; ts?: string }>,
  color: string,
  vp: import('./viewport').Viewport,
  maxPoints = 500,
  isHistory = false,   // 新增
) {
  if (points.length < 2) return

  const pts = points.slice(-maxPoints)
  ctx.strokeStyle = color
  ctx.lineWidth = isHistory ? 1 : 1.5           // 历史细一点
  ctx.globalAlpha = isHistory ? 0.3 : 0.8        // 历史淡，实时浓
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  const p0 = worldToCanvas(pts[0].x, pts[0].y, vp)
  ctx.beginPath()
  ctx.moveTo(p0.x, p0.y)

  for (let i = 1; i < pts.length - 1; i++) {
    const p1 = worldToCanvas(pts[i].x, pts[i].y, vp)
    const p2 = worldToCanvas(pts[i + 1].x, pts[i + 1].y, vp)
    const midX = (p1.x + p2.x) / 2
    const midY = (p1.y + p2.y) / 2
    ctx.quadraticCurveTo(p1.x, p1.y, midX, midY)
  }

  const last = worldToCanvas(pts[pts.length - 1].x, pts[pts.length - 1].y, vp)
  ctx.lineTo(last.x, last.y)
  ctx.stroke()
  ctx.globalAlpha = 1
}
```

- [ ] **Step 3: 更新 crawfish.ts — drawCrawfish 支持 isLive 参数**

检查 `crawfish.ts` 的 `drawCrawfish` 函数签名，在函数末尾增加 `isLive = true` 参数，回放模式下降低龙虾饱和度。

```typescript
// 签名变更：export function drawCrawfish(..., isLive = true)
// 实现中：回放模式(非实时)时龙虾加灰度滤镜
```

- [ ] **Step 4: 提交**

```bash
git add website/src/engine/renderer.ts website/src/engine/trail.ts website/src/engine/crawfish.ts
git commit -m "feat: add live/replay mode to renderer with history/realtime color distinction"
```

---

## Task 4: useReplay — 扩展支持全局历史加载

**Files:**
- Modify: `website/src/composables/useReplay.ts`

- [ ] **Step 1: 支持无 Token 全局历史**

```typescript
import { ref, computed } from 'vue'

export interface ReplayPoint {
  x: number; y: number; ts: string; user_id: number; user_name?: string
}

export function useReplay() {
  const replaying = ref(false)
  const playbackSpeed = ref(1)
  const currentTime = ref<Date | null>(null)
  const rangeStart = ref<Date | null>(null)
  const rangeEnd = ref<Date | null>(null)
  const allPoints = ref<ReplayPoint[]>([])
  const visiblePoints = computed(() => {
    if (!currentTime.value) return []
    return allPoints.value.filter(p => new Date(p.ts) <= currentTime.value!)
  })

  let _timer: ReturnType<typeof setInterval> | null = null

  // 支持有 Token（个人）和无 Token（全局）两种加载方式
  async function loadReplay(window: '1h' | '24h' | '7d', token?: string) {
    try {
      const headers: Record<string, string> = {}
      let url = `/api/world/history?window=${window}&limit=5000`
      if (token) {
        headers['X-Token'] = token
      }
      const r = await fetch(url, { headers })
      if (!r.ok) return
      const data = await r.json()
      const pts: ReplayPoint[] = (data.points || []).map((p: any) => ({
        x: p.x,
        y: p.y,
        ts: p.ts,
        user_id: p.user_id,
        user_name: p.user_name || '',
      }))
      allPoints.value = pts
      if (pts.length > 0) {
        const times = pts.map(p => new Date(p.ts).getTime())
        rangeStart.value = new Date(Math.min(...times))
        rangeEnd.value = new Date(Math.max(...times))
        currentTime.value = rangeEnd.value
      }
    } catch {}
  }

  function play() {
    replaying.value = true
    const step = 1000 * playbackSpeed.value
    _timer = setInterval(() => {
      if (!currentTime.value || !rangeEnd.value) return
      const next = new Date(currentTime.value.getTime() + step)
      if (next >= rangeEnd.value!) {
        currentTime.value = rangeEnd.value
        pause()
      } else {
        currentTime.value = next
      }
    }, 1000)
  }

  function pause() {
    replaying.value = false
    if (_timer) { clearInterval(_timer); _timer = null }
  }

  function seekTo(date: Date) {
    currentTime.value = date
  }

  function setSpeed(s: number) {
    playbackSpeed.value = s
    if (replaying.value) { pause(); play() }
  }

  function reset() {
    pause()
    currentTime.value = rangeEnd.value
  }

  function clear() {
    pause()
    allPoints.value = []
    currentTime.value = null
    rangeStart.value = null
    rangeEnd.value = null
  }

  return {
    replaying, playbackSpeed, currentTime, rangeStart, rangeEnd,
    allPoints, visiblePoints,
    loadReplay, play, pause, seekTo, setSpeed, reset, clear
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add website/src/composables/useReplay.ts
git commit -m "feat: extend useReplay to support global (no-token) history loading"
```

---

## Task 5: ReplayModal — 时间范围选择弹窗

**Files:**
- Create: `website/src/components/ReplayModal.vue`

- [ ] **Step 1: 实现弹窗组件**

```vue
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
        <div class="modal-card">
          <div class="modal-header">
            <h3>进入回放</h3>
            <button class="close-btn" @click="$emit('close')">✕</button>
          </div>
          <p class="modal-desc">选择一个时间范围，从头播放历史轨迹</p>
          <div class="range-btns">
            <button
              v-for="r in ranges" :key="r.key"
              class="range-btn" :class="{ active: selected === r.key }"
              @click="selected = r.key"
            >
              <span class="range-label">{{ r.label }}</span>
              <span class="range-desc">{{ r.desc }}</span>
            </button>
          </div>
          <div class="modal-actions">
            <button class="cancel-btn" @click="$emit('close')">取消</button>
            <button class="confirm-btn" @click="confirm">开始回放</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  close: []
  confirm: [window: '1h' | '24h' | '7d']
}>()

const show = ref(true)
const selected = ref<'1h' | '24h' | '7d'>('24h')

const ranges = [
  { key: '1h' as const, label: '最近 1 小时', desc: '查看刚刚发生的故事' },
  { key: '24h' as const, label: '最近 24 小时', desc: '一天内所有龙虾活动' },
  { key: '7d' as const, label: '最近 7 天', desc: '完整的周度活动记录' },
]

function confirm() {
  emit('confirm', selected.value)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 9000;
}
.modal-card {
  background: #fffbf5;
  border-radius: 16px;
  padding: 28px;
  width: 380px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.modal-header h3 {
  font-family: 'Fredoka', sans-serif;
  font-size: 1.2rem;
  color: #3d2c24;
  margin: 0;
}
.close-btn {
  background: none; border: none; cursor: pointer;
  color: #8B7B6E; font-size: 1.1rem;
  padding: 4px;
}
.modal-desc {
  font-size: 0.85rem; color: #8B7B6E; margin: 0 0 20px;
}
.range-btns { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }
.range-btn {
  display: flex; flex-direction: column; align-items: flex-start;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1.5px solid rgba(232,98,58,0.2);
  background: none; cursor: pointer; text-align: left;
  transition: all 0.15s;
}
.range-btn:hover { border-color: #E8623A; background: rgba(232,98,58,0.05); }
.range-btn.active { border-color: #E8623A; background: rgba(232,98,58,0.1); }
.range-label { font-weight: 700; color: #3d2c24; font-size: 0.95rem; }
.range-desc { font-size: 0.78rem; color: #8B7B6E; margin-top: 2px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
.cancel-btn {
  padding: 8px 18px; border-radius: 8px;
  border: 1.5px solid rgba(232,98,58,0.2); background: none;
  color: #8B7B6E; cursor: pointer; font-size: 0.9rem;
}
.confirm-btn {
  padding: 8px 18px; border-radius: 8px;
  border: none; background: #E8623A; color: #fff;
  cursor: pointer; font-size: 0.9rem; font-weight: 600;
}
.confirm-btn:hover { background: #d4522a; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add website/src/components/ReplayModal.vue
git commit -m "feat: add ReplayModal component for time range selection"
```

---

## Task 6: WorldToolbar — 右上角工具栏

**Files:**
- Create: `website/src/components/WorldToolbar.vue`

- [ ] **Step 1: 实现工具栏组件**

```vue
<template>
  <div class="world-toolbar">
    <!-- Replay mode indicator -->
    <div v-if="mode === 'replay'" class="mode-badge replay-badge">
      <span>🔄 回放模式</span>
      <button class="exit-btn" @click="$emit('exit-replay')" title="退出回放">✕</button>
    </div>

    <!-- Live mode toolbar -->
    <template v-else>
      <!-- 只看实时 -->
      <button
        class="tool-btn" :class="{ active: hideHistory }"
        @click="onToggleHistory"
        :title="hideHistory ? '显示历史轨迹' : '隐藏历史轨迹'"
      >
        {{ hideHistory ? '👁️ 实时' : '📜 全量' }}
      </button>

      <!-- 进入回放 -->
      <button class="tool-btn replay-btn" @click="$emit('enter-replay')">
        ⏪ 回放
      </button>
    </template>

    <!-- Replay time display -->
    <div v-if="mode === 'replay' && replayTime" class="replay-clock">
      {{ formatTime(replayTime) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWorldStore } from '../stores/world'

const worldStore = useWorldStore()

const mode = computed(() => worldStore.mode)
const hideHistory = computed(() => worldStore.hideHistory)

const props = defineProps<{
  replayTime?: Date | null
}>()

const emit = defineEmits<{
  'enter-replay': []
  'exit-replay': []
}>()

function onToggleHistory() {
  worldStore.setHideHistory(!worldStore.hideHistory)
}

function formatTime(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<style scoped>
.world-toolbar {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 100;
}
.mode-badge {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  border-radius: 99px;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.85rem;
  font-weight: 600;
}
.replay-badge {
  background: #fff3e0;
  color: #e65100;
  border: 1.5px solid rgba(230,81,0,0.3);
}
.exit-btn {
  background: none; border: none; cursor: pointer;
  color: #e65100; font-size: 0.85rem; padding: 0;
  line-height: 1;
}
.tool-btn {
  padding: 5px 12px;
  border-radius: 99px;
  border: 1.5px solid rgba(232,98,58,0.25);
  background: rgba(255,255,255,0.9);
  color: #8B7B6E;
  font-size: 0.8rem;
  font-family: 'Space Grotesk', sans-serif;
  cursor: pointer;
  transition: all 0.15s;
  backdrop-filter: blur(8px);
}
.tool-btn:hover { border-color: #E8623A; color: #E8623A; }
.tool-btn.active { background: #E8623A; color: #fff; border-color: #E8623A; }
.replay-btn {
  background: #fff3e0;
  color: #e65100;
  border-color: rgba(230,81,0,0.3);
}
.replay-btn:hover { background: #ffe0b2; }
.replay-clock {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.75rem;
  color: #e65100;
  background: rgba(255,243,224,0.9);
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(230,81,0,0.2);
  white-space: nowrap;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add website/src/components/WorldToolbar.vue
git commit -m "feat: add WorldToolbar component with live/replay mode controls"
```

---

## Task 7: WorldMap — 集成模式切换 + loading + 渲染联动

**Files:**
- Modify: `website/src/components/WorldMap.vue`

- [ ] **Step 1: 改造 WorldMap.vue**

主要改动：
1. 导入 `WorldToolbar` 和 `ReplayModal`，渲染在 canvas 上方
2. 导入 `useReplay` composable
3. 在 `onMounted` 中调用 `worldStore.loadGlobalHistory()`
4. `render()` 函数根据 `mode` 决定传 `livePoints` 还是 `useReplay().visiblePoints`
5. 进入回放时：调用 `useReplay().loadReplay()`，断开 WebSocket
6. 退出回放时：显示 loading 遮罩 → 重拉历史 → 重连 WebSocket
7. WebSocket `snapshot` 消息中，实时点同时写入 `historyPoints` 和 `realtimePoints`（如果需要）

```vue
<!-- 模板末尾添加 -->
<template>
  <div class="world-map-wrap" ...>
    <canvas ref="canvasRef" class="world-canvas" />
    <!-- Loading overlay -->
    <Transition name="fade">
      <div v-if="worldStore.loading" class="loading-overlay">
        <div class="loading-spinner" />
      </div>
    </Transition>
    <!-- Toolbar -->
    <WorldToolbar
      :replay-time="replay.currentTime.value"
      @enter-replay="showReplayModal = true"
      @exit-replay="exitReplay"
    />
    <!-- Replay bar (only in replay mode) -->
    <ReplayBar
      v-if="worldStore.mode === 'replay'"
      class="replay-bar-overlay"
      @range-selected="onRangeSelected"
    />
    <!-- Replay time selector modal -->
    <ReplayModal
      v-if="showReplayModal"
      @close="showReplayModal = false"
      @confirm="onReplayConfirm"
    />
    <!-- Zoom controls -->
    ...
  </div>
</template>
```

```typescript
// script setup 改动
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useWorldStore } from '../stores/world'
import { useReplay } from '../composables/useReplay'
import WorldToolbar from './WorldToolbar.vue'
import ReplayModal from './ReplayModal.vue'
import ReplayBar from './ReplayBar.vue'

const worldStore = useWorldStore()
const replay = useReplay()

const showReplayModal = ref(false)

// WebSocket 连接函数
function connectWs() { ... } // 保持现有逻辑不变

// 进入回放
async function enterReplay(window: '1h' | '24h' | '7d') {
  // 1. 断开 WebSocket
  if (ws) { ws.close(); ws = null }
  // 2. 切换模式
  worldStore.enterReplayMode()
  // 3. 加载回放数据
  await replay.loadReplay(window)
  showReplayModal.value = false
}

// 退出回放 → 回到实时
async function exitReplay() {
  replay.clear()
  worldStore.exitReplayMode()
  // 显示 loading
  worldStore.loading = true
  // 重拉历史
  await worldStore.loadGlobalHistory()
  // 重连 WebSocket
  connectWs()
}

// Range selected in ReplayBar (speed change doesn't reload data)
function onRangeSelected(window: string) {
  // User picked a different time window from ReplayBar
  enterReplay(window as '1h' | '24h' | '7d')
}

// render() 根据 mode 选择数据源
function render() {
  if (!canvasRef.value) return
  const ctx = canvasRef.value.getContext('2d')
  const users = worldStore.onlineUsers
  const mode = worldStore.mode

  if (mode === 'replay') {
    // 回放模式：构建 visiblePoints 的 trails
    const trails = buildTrailsFromPoints(replay.visiblePoints.value)
    renderFrame(ctx, vp, users, trails, [], null, hoveredUserId.value,
      { layer: uiStore.layerMode, mode: 'replay' }, frame.value, replay.currentTime.value || undefined)
  } else {
    // 实时模式：history + realtime
    const trails = buildTrails()
    renderFrame(ctx, vp, users, trails, [], null, hoveredUserId.value,
      { layer: uiStore.layerMode, mode: 'live', hideHistory: worldStore.hideHistory },
      frame.value)
  }
}

// buildTrailsFromPoints：从 ReplayPoint[] 构建 trails 格式
function buildTrailsFromPoints(points: ReplayPoint[]) {
  const map = new Map()
  for (const p of points) {
    if (!map.has(p.user_id)) {
      map.set(p.user_id, { user_id: p.user_id, name: p.user_name || '', points: [] })
    }
    map.get(p.user_id).points.push({ x: p.x, y: p.y, ts: p.ts })
  }
  return Array.from(map.values())
}

// watch replay.currentTime → re-render
watch(() => replay.currentTime.value, () => render())

onMounted(async () => {
  resize()
  window.addEventListener('resize', resize)
  loop()
  // 加载 24h 历史
  await worldStore.loadGlobalHistory()
  // 建立 WebSocket
  connectWs()
})
```

- [ ] **Step 2: 提交**

```bash
git add website/src/components/WorldMap.vue
git commit -m "feat: integrate live/replay mode switching, loading overlay, and replay rendering into WorldMap"
```

---

## Task 8: 联调 — 验证完整流程

- [ ] **Step 1: 启动服务器验证后端接口**

```bash
# 终端 1: 启动后端
cd D:/clawsocial-server && python -m app.main
# 终端 2: 手动测试
curl "http://localhost:8000/api/world/history?window=24h"
```

- [ ] **Step 2: 构建前端并验证**

```bash
cd D:/clawsocial-server/website && npm run build
```

- [ ] **Step 3: 启动开发服务器验证完整流程**

```bash
cd D:/clawsocial-server/website && npm run dev
# 打开 http://localhost:5173/world
# 验证：
# 1. 地图加载时显示 loading → 历史数据出现
# 2. 历史轨迹淡色，WebSocket 新点实时追加并鲜艳
# 3. 点击"只看实时" → 历史轨迹消失
# 4. 点击"回放" → 弹窗选择时间范围 → 进入回放模式
# 5. ReplayBar 播放/暂停/快进正常，龙虾按 currentTime 位置显示
# 6. 点击退出 → loading → 历史重新加载 → 回到实时
```

- [ ] **Step 4: 运行全部测试**

```bash
cd D:/clawsocial-server && python -m pytest tests/test_api.py -v
```

- [ ] **Step 5: 提交最终版本**

```bash
git add -A
git commit -m "feat: real-time map with 24h history, live/replay mode switching"
```

---

## 实施检查清单

| 任务 | 状态 |
|------|------|
| Task 1: 后端公开历史接口 | ⬜ |
| Task 2: worldStore 分离数据 | ⬜ |
| Task 3: renderer 双模式着色 | ⬜ |
| Task 4: useReplay 全局加载 | ⬜ |
| Task 5: ReplayModal 弹窗 | ⬜ |
| Task 6: WorldToolbar 工具栏 | ⬜ |
| Task 7: WorldMap 集成 | ⬜ |
| Task 8: 联调验证 | ⬜ |
