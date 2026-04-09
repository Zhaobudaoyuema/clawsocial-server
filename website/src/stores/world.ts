import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type MapMode = 'live' | 'replay'

export interface WorldUser {
  user_id: number
  name: string
  x: number
  y: number
  isMe?: boolean
}

export interface TrailPoint {
  x: number
  y: number
  user_id: number
  user_name?: string
  ts: string
}

export interface LiveEvent {
  id: number
  user_id: number
  user_name: string
  event_type: string
  other_user_id: number | null
  x: number
  y: number
  ts: string
  expireAt: number  // unix ms
}

export const useWorldStore = defineStore('world', () => {
  // ── Users ─────────────────────────────────────────────────────────────────
  const users = ref<Map<number, WorldUser>>(new Map())
  const myUserId = ref<number | null>(null)
  const onlineCount = computed(() => users.value.size)
  const onlineUsers = computed(() => Array.from(users.value.values()))

  // ── Snapshot tracking for position-change detection ────────────────────────
  const _prevUserPositions = new Map<number, { x: number; y: number }>()

  // ── Trails ────────────────────────────────────────────────────────────────
  /** 24h history loaded from REST on mount */
  const historyPoints = ref<TrailPoint[]>([])

  /** Realtime points: only appended when position actually changes */
  const realtimePoints = ref<TrailPoint[]>([])

  /** All live points = history + realtime */
  const livePoints = computed<TrailPoint[]>(() => [
    ...historyPoints.value,
    ...realtimePoints.value,
  ])

  // ── Live events (WS pushed) ───────────────────────────────────────────────
  const liveEvents = ref<LiveEvent[]>([])

  // ── Heatmap ──────────────────────────────────────────────────────────────
  const liveHeatmap = ref<HeatmapCell[]>([])

  // ── WS connection ─────────────────────────────────────────────────────────
  const wsConnected = ref(false)
  let _ws: WebSocket | null = null
  let _token: string | null = null

  // ── Mode ─────────────────────────────────────────────────────────────────
  const mode = ref<MapMode>('live')
  const loading = ref(false)
  const error = ref<string | null>(null)

  // ── setSnapshot ─────────────────────────────────────────────────────────

  /**
   * Called every 2s by the world WebSocket.
   * - Replaces the users Map
   * - Tracks isMe flag
   * - Appends to realtimePoints only when position actually changed
   */
  function setSnapshot(snapshot: WorldUser[], myUid?: number | null) {
    const newMap = new Map<number, WorldUser>()
    for (const u of snapshot) {
      newMap.set(u.user_id, {
        user_id: u.user_id,
        name: u.name || '',
        x: u.x,
        y: u.y,
        isMe: myUid != null && u.user_id === myUid,
      })

      // Position change detection: only append if moved
      const prev = _prevUserPositions.get(u.user_id)
      if (!prev || prev.x !== u.x || prev.y !== u.y) {
        realtimePoints.value.push({
          x: u.x,
          y: u.y,
          user_id: u.user_id,
          user_name: u.name || '',
          ts: new Date().toISOString(),
        })
        // Cap at 5000 per user would be ideal; global cap below
      }
      _prevUserPositions.set(u.user_id, { x: u.x, y: u.y })
    }
    users.value = newMap

    // Cap global realtime points
    if (realtimePoints.value.length > 5000) {
      realtimePoints.value.splice(0, realtimePoints.value.length - 5000)
    }
  }

  // ── Live events ───────────────────────────────────────────────────────────

  /**
   * Called when WS pushes new event(s).
   * Each event gets expireAt = now + 2s.
   */
  function appendLiveEvents(events: LiveEvent[]) {
    const now = Date.now()
    const withExpiry: LiveEvent[] = events.map(e => ({
      ...e,
      expireAt: now + 2000,
    }))
    liveEvents.value.push(...withExpiry)
  }

  /**
   * Called each animation frame to purge expired events.
   */
  function purgeExpiredEvents() {
    const now = Date.now()
    liveEvents.value = liveEvents.value.filter(e => e.expireAt > now)
  }

  // ── WS connection ─────────────────────────────────────────────────────────

  function connect(token?: string | null) {
    if (_ws) _ws.close()
    _token = token ?? null

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/ws/observe${token ? `?token=${encodeURIComponent(token)}` : ''}`
    _ws = new WebSocket(url)

    _ws.onopen = () => { wsConnected.value = true }
    _ws.onclose = () => {
      wsConnected.value = false
      // Reconnect after 3s
      setTimeout(() => connect(_token), 3000)
    }
    _ws.onerror = () => { _ws?.close() }

    _ws.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data as string)
        if (msg.type === 'snapshot') {
          // snapshot.users may include isMe already from server-side injection
          setSnapshot(msg.users || [], myUserId.value)
          // Server-side isMe injection takes priority; also try to detect from token
          if (msg.users) {
            for (const u of msg.users) {
              if (myUserId.value != null && u.user_id === myUserId.value) {
                u.isMe = true
              }
            }
          }
        }
        if (msg.events && Array.isArray(msg.events)) {
          appendLiveEvents(msg.events)
        }
      } catch {}
    }
  }

  function disconnect() {
    if (_ws) {
      _ws.onclose = null
      _ws.close()
      _ws = null
    }
    wsConnected.value = false
  }

  function setMyUserId(id: number | null) {
    myUserId.value = id
  }

  // ── History ───────────────────────────────────────────────────────────────

  async function loadGlobalHistory(window: '1h' | '24h' | '7d' = '24h', token?: string) {
    loading.value = true
    error.value = null
    try {
      const headers: Record<string, string> = {}
      if (token) headers['X-Token'] = token
      const r = await fetch(`/api/world/history?window=${window}&limit=5000`, { headers })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
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

  async function loadHeatmap(window: '1h' | '24h' | '7d' = '24h') {
    try {
      const r = await fetch(`/api/world/heatmap?window=${window}`)
      if (!r.ok) return
      const data = await r.json()
      liveHeatmap.value = (data.cells || []).map((c: any) => ({
        cell_x: c.cell_x,
        cell_y: c.cell_y,
        count: c.count,
      }))
    } catch {}
  }

  function clearLive() {
    realtimePoints.value = []
    liveEvents.value = []
    _prevUserPositions.clear()
  }

  // ── Mode ─────────────────────────────────────────────────────────────────

  function enterReplayMode() {
    mode.value = 'replay'
    realtimePoints.value = []
  }

  function exitReplayMode() {
    mode.value = 'live'
  }

  return {
    // state
    users,
    myUserId,
    historyPoints,
    realtimePoints,
    livePoints,
    liveEvents,
    liveHeatmap,
    mode,
    wsConnected,
    loading,
    error,
    // computed
    onlineUsers,
    onlineCount,
    // actions
    setSnapshot,
    appendLiveEvents,
    purgeExpiredEvents,
    connect,
    disconnect,
    setMyUserId,
    loadGlobalHistory,
    loadHeatmap,
    clearLive,
    enterReplayMode,
    exitReplayMode,
  }
})

export interface HeatmapCell {
  cell_x: number
  cell_y: number
  count: number
}
