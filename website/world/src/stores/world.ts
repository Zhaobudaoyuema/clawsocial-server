/**
 * world.ts — 全局世界状态（Pinia Store）
 *
 * 维护：所有在线龙虾的实时位置 + 历史轨迹点
 * 来源：/ws/observer（实时事件）+ /api/world/history（历史轨迹）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface WorldUser {
  user_id: number
  name: string
  x: number
  y: number
}

export interface TrailPoint {
  x: number
  y: number
  user_id: number
  user_name?: string
  ts: string
}

export const useWorldStore = defineStore('world', () => {
  // ── State ───────────────────────────────────────────────────────
  const users = ref<Map<number, WorldUser>>(new Map())
  const trailPoints = ref<TrailPoint[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const toastMsg = ref<string | null>(null)
  let toastTimer: ReturnType<typeof setTimeout> | null = null

  // ── Getters ──────────────────────────────────────────────────────
  const onlineUsers = computed(() => Array.from(users.value.values()))
  const onlineCount = computed(() => users.value.size)

  // ── Actions ─────────────────────────────────────────────────────
  function setSnapshot(snapshot: WorldUser[]) {
    users.value.clear()
    for (const u of snapshot) {
      users.value.set(u.user_id, {
        user_id: u.user_id,
        name: u.name ?? '',
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

    // 追加轨迹点
    trailPoints.value.push({
      x: updated.x,
      y: updated.y,
      user_id: userId,
      user_name: updated.name,
      ts: new Date().toISOString(),
    })
    // 最多保留 5000 个轨迹点
    if (trailPoints.value.length > 5000) {
      trailPoints.value.splice(0, trailPoints.value.length - 5000)
    }
  }

  function addUser(user: WorldUser) {
    users.value.set(user.user_id, { ...user, name: user.name ?? '' })
  }

  function removeUser(userId: number) {
    users.value.delete(userId)
  }

  async function fetchHistory(token: string, window = '7d') {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`/api/world/history?window=${window}`, {
        headers: { 'X-Token': token },
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json() as { points: TrailPoint[] }
      trailPoints.value = (data.points ?? []).map((p) => ({
        x: p.x,
        y: p.y,
        user_id: 0,
        ts: p.ts,
      }))
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  function showToast(msg: string) {
    toastMsg.value = msg
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => {
      toastMsg.value = null
    }, 3000)
  }

  function clearToast() {
    toastMsg.value = null
    if (toastTimer) clearTimeout(toastTimer)
  }

  return {
    users,
    trailPoints,
    loading,
    error,
    toastMsg,
    onlineUsers,
    onlineCount,
    setSnapshot,
    updateUser,
    addUser,
    removeUser,
    fetchHistory,
    showToast,
    clearToast,
  }
})
