import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type MapMode = 'live' | 'replay'

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
  // --- Users ---
  const users = ref<Map<number, WorldUser>>(new Map())

  // --- History: loaded from REST API (24h global history) ---
  const historyPoints = ref<TrailPoint[]>([])

  // --- Realtime: appended from WebSocket (only live WebSocket points) ---
  const realtimePoints = ref<TrailPoint[]>([])

  // --- Current map mode ---
  const mode = ref<MapMode>('live')

  // --- "只看实时" toggle - hides historyPoints from rendering ---
  const hideHistory = ref(false)

  // --- Loading / error ---
  const loading = ref(false)
  const error = ref<string | null>(null)

  // --- Computed ---
  const onlineUsers = computed(() => Array.from(users.value.values()))
  const onlineCount = computed(() => users.value.size)

  // All live-mode points (history + realtime), respecting hideHistory
  const livePoints = computed<TrailPoint[]>(() => {
    if (hideHistory.value) return realtimePoints.value
    return [...historyPoints.value, ...realtimePoints.value]
  })

  // --- Methods ---

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
    // WebSocket incoming points go into realtimePoints
    realtimePoints.value.push({
      x: updated.x, y: updated.y, user_id: userId,
      user_name: updated.name, ts: new Date().toISOString(),
    })
    if (realtimePoints.value.length > 5000) {
      realtimePoints.value.splice(0, realtimePoints.value.length - 5000)
    }
  }

  function addUser(user: WorldUser) { users.value.set(user.user_id, { ...user, name: user.name ?? '' }) }
  function removeUser(userId: number) { users.value.delete(userId) }

  // Load global 24h history from the new public REST API
  async function loadGlobalHistory(window: '1h' | '24h' | '7d' = '24h') {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`/api/world/history?window=${window}&limit=5000`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      // Public API returns: { window, total, points: [{user_id, user_name, x, y, ts}] }
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

  // Switch to replay mode (WebSocket will be paused externally)
  function enterReplayMode() {
    mode.value = 'replay'
    realtimePoints.value = []
  }

  // Exit replay and return to live mode
  function exitReplayMode() {
    mode.value = 'live'
    realtimePoints.value = []
  }

  return {
    users,
    historyPoints,
    realtimePoints,
    livePoints,
    mode,
    hideHistory,
    loading,
    error,
    onlineUsers,
    onlineCount,
    setSnapshot,
    updateUser,
    addUser,
    removeUser,
    loadGlobalHistory,
    clearHistory,
    setHideHistory,
    enterReplayMode,
    exitReplayMode,
  }
})
