import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

// ── Types ────────────────────────────────────────────────────────────────────

export interface ReplayPoint {
  user_id: number
  user_name: string
  x: number
  y: number
  ts: string
}

export interface ReplayEvent {
  id?: number
  user_id: number
  user_name?: string
  event_type: string
  other_user_id: number | null
  x: number
  y: number
  ts: string
  content?: string | null
  reason?: string | null
}

export interface HeatmapCell {
  cell_x: number
  cell_y: number
  count: number
}

// ── Store ────────────────────────────────────────────────────────────────────

export const useReplayStore = defineStore('replay', () => {
  // ── Raw data ──────────────────────────────────────────────────────────────
  const allPoints = ref<ReplayPoint[]>([])
  const allEvents = ref<ReplayEvent[]>([])
  const allHeatmap = ref<HeatmapCell[]>([])

  // ── Time navigation ────────────────────────────────────────────────────────
  const currentTime = ref<Date | null>(null)
  const rangeStart = ref<Date | null>(null)
  const rangeEnd = ref<Date | null>(null)
  const replaying = ref(false)
  const playbackSpeed = ref(1)  // 1 / 2 / 5 / 10
  const mode = ref<'live' | 'replay'>('live')

  // ── My user ───────────────────────────────────────────────────────────────
  const myUserId = ref<number | null>(null)
  const filterMyOnly = ref(false)

  let _timer: ReturnType<typeof setInterval> | null = null

  // ── Computed: visible points ───────────────────────────────────────────────

  /**
   * 当前时间之前的全部轨迹点。
   * 用于全局回放：显示所有用户的轨迹。
   */
  const visiblePoints = computed<ReplayPoint[]>(() => {
    if (!currentTime.value) return []
    const ct = currentTime.value.getTime()
    return allPoints.value.filter(p => new Date(p.ts).getTime() <= ct)
  })

  /**
   * 当前时间之前的全部事件。
   * 用于全局回放：显示所有事件气泡。
   */
  const visibleEvents = computed<ReplayEvent[]>(() => {
    if (!currentTime.value) return []
    const ct = currentTime.value.getTime()
    return allEvents.value.filter(e => new Date(e.ts).getTime() <= ct)
  })

  // ── Computed: "只看我的虾" ────────────────────────────────────────────────

  /** 仅属于我的轨迹点 */
  const myPoints = computed<ReplayPoint[]>(() => {
    if (!myUserId.value) return visiblePoints.value
    return visiblePoints.value.filter(p => p.user_id === myUserId.value)
  })

  /** 仅涉及我的事件 */
  const myEvents = computed<ReplayEvent[]>(() => {
    if (!myUserId.value) return visibleEvents.value
    return visibleEvents.value.filter(e => e.user_id === myUserId.value)
  })

  /** 在我的事件中出现过（相遇/发消息）的其他用户 ID */
  const relatedUserIds = computed<Set<number>>(() => {
    const ids = new Set<number>()
    for (const e of myEvents.value) {
      if (e.other_user_id) ids.add(e.other_user_id)
    }
    return ids
  })

  // ── Computed: crawfish positions ─────────────────────────────────────────

  /**
   * 全局回放：每只虾在 currentTime 时刻的最后位置。
   * 构建方式：遍历 visiblePoints，以 user_id 为 key 保留最后一个。
   */
  const crawfishPositions = computed<CrawfishPosition[]>(() => {
    if (!currentTime.value) return []
    const ct = currentTime.value.getTime()
    const map = new Map<number, CrawfishPosition>()
    for (const p of allPoints.value) {
      const t = new Date(p.ts).getTime()
      if (t > ct) continue
      map.set(p.user_id, {
        user_id: p.user_id,
        name: p.user_name || '',
        x: p.x,
        y: p.y,
        isMe: p.user_id === myUserId.value,
      })
    }
    return Array.from(map.values())
  })

  /**
   * "只看我的虾"：我的虾 + 在我的事件中出现过的其他用户。
   * 这些其他用户只有位置标记，没有轨迹线。
   */
  const myModePositions = computed<CrawfishPosition[]>(() => {
    if (!currentTime.value || !myUserId.value) return []
    const ct = currentTime.value.getTime()
    const result: CrawfishPosition[] = []

    // 我的虾
    let lastMe: CrawfishPosition | null = null
    for (const p of allPoints.value) {
      if (p.user_id !== myUserId.value) continue
      const t = new Date(p.ts).getTime()
      if (t > ct) continue
      lastMe = { user_id: p.user_id, name: p.user_name || '', x: p.x, y: p.y, isMe: true }
    }
    if (lastMe) result.push(lastMe)

    // 相关的其他用户
    for (const uid of relatedUserIds.value) {
      let last: CrawfishPosition | null = null
      for (const p of allPoints.value) {
        if (p.user_id !== uid) continue
        const t = new Date(p.ts).getTime()
        if (t > ct) continue
        last = { user_id: p.user_id, name: p.user_name || '', x: p.x, y: p.y, isMe: false }
      }
      if (last) result.push(last)
    }
    return result
  })

  // ── Load ───────────────────────────────────────────────────────────────────

  async function loadReplay(
    window: '1h' | '24h' | '7d',
    token?: string,
  ) {
    try {
      const headers: Record<string, string> = {}
      if (token) headers['X-Token'] = token

      // 并行加载：轨迹 + 事件 + 热力图
      const [historyRes, eventsRes, heatmapRes] = await Promise.all([
        fetch(`/api/world/history?window=${window}&limit=5000`, { headers }),
        token
          ? fetch(`/api/world/social?window=${window}`, { headers })
          : fetch(`/api/world/events?window=${window}`),
        fetch(`/api/world/heatmap?window=${window}`),
      ])

      if (!historyRes.ok || !eventsRes.ok || !heatmapRes.ok) return

      const [historyData, eventsData, heatmapData] = await Promise.all([
        historyRes.json(),
        eventsRes.json(),
        heatmapRes.json(),
      ])

      // 解析轨迹
      const pts: ReplayPoint[] = (historyData.points || []).map((p: any) => ({
        user_id: p.user_id,
        user_name: p.user_name || '',
        x: p.x,
        y: p.y,
        ts: p.ts,
      }))

      // 解析事件
      const evts: ReplayEvent[] = (eventsData.events || []).map((e: any) => ({
        id: e.id,
        user_id: e.user_id,
        user_name: e.user_name || '',
        event_type: e.event_type,
        other_user_id: e.other_user_id ?? null,
        x: e.x ?? 0,
        y: e.y ?? 0,
        ts: e.ts,
        content: e.content ?? null,
        reason: e.reason ?? null,
      }))

      // 解析热力图
      const cells: HeatmapCell[] = (heatmapData.cells || []).map((c: any) => ({
        cell_x: c.cell_x,
        cell_y: c.cell_y,
        count: c.count,
      }))

      allPoints.value = pts
      allEvents.value = evts
      allHeatmap.value = cells

      if (pts.length > 0) {
        // 用 reduce 避免大数组 spread 栈溢出
        const times = pts.map(p => new Date(p.ts).getTime())
        const tMin = times.reduce((m, t) => t < m ? t : m, times[0])
        const tMax = times.reduce((m, t) => t > m ? t : m, times[0])
        rangeStart.value = new Date(tMin)
        rangeEnd.value = new Date(tMax)
        // 正放：从头开始
        currentTime.value = new Date(tMin)
      }
    } catch (e) {
      console.error('[replayStore] loadReplay failed', e)
    }
  }

  // ── Playback control ───────────────────────────────────────────────────────

  function play() {
    if (replaying.value) return
    replaying.value = true
    // 每个真实秒推进 playbackSpeed 分钟的游戏时间
    // 1x = 1分钟/秒 → 24h 回放约需 24 真实分钟
    // 10x = 10分钟/秒 → 24h 回放约需 2.4 真实分钟
    const step = 60_000 * playbackSpeed.value
    _timer = setInterval(() => {
      if (!currentTime.value || !rangeEnd.value) return
      const next = new Date(currentTime.value.getTime() + step)
      if (next >= rangeEnd.value) {
        currentTime.value = new Date(rangeEnd.value.getTime())
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
    currentTime.value = new Date(date)
  }

  function setSpeed(s: number) {
    playbackSpeed.value = s
    if (replaying.value) { pause(); play() }
  }

  function setFilterMyOnly(v: boolean) {
    filterMyOnly.value = v
  }

  function reset() {
    pause()
    if (rangeStart.value) currentTime.value = new Date(rangeStart.value.getTime())
  }

  function clear() {
    pause()
    allPoints.value = []
    allEvents.value = []
    allHeatmap.value = []
    currentTime.value = null
    rangeStart.value = null
    rangeEnd.value = null
    filterMyOnly.value = false
  }

  function setMyUserId(id: number | null) {
    myUserId.value = id
  }

  function enterReplayMode() {
    mode.value = 'replay'
  }

  function exitReplayMode() {
    mode.value = 'live'
    clear()
  }

  return {
    // raw data
    allPoints,
    allEvents,
    allHeatmap,
    // time
    currentTime,
    rangeStart,
    rangeEnd,
    replaying,
    playbackSpeed,
    mode,
    // filter
    filterMyOnly,
    myUserId,
    // computed
    visiblePoints,
    visibleEvents,
    myPoints,
    myEvents,
    relatedUserIds,
    crawfishPositions,
    myModePositions,
    // actions
    loadReplay,
    play,
    pause,
    seekTo,
    setSpeed,
    setFilterMyOnly,
    reset,
    clear,
    setMyUserId,
    enterReplayMode,
    exitReplayMode,
  }
})

export interface CrawfishPosition {
  user_id: number
  name: string
  x: number
  y: number
  isMe: boolean
}
