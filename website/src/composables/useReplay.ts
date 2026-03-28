import { ref, computed } from 'vue'

export interface ReplayPoint {
  x: number; y: number; ts: string; user_id: number; user_name?: string
}

export function useReplay() {
  const replaying = ref(false)
  const playbackSpeed = ref(1)  // 1, 2, 5, 10
  const currentTime = ref<Date | null>(null)
  const rangeStart = ref<Date | null>(null)
  const rangeEnd = ref<Date | null>(null)
  const allPoints = ref<ReplayPoint[]>([])
  const visiblePoints = computed(() => {
    if (!currentTime.value) return []
    return allPoints.value.filter(p => new Date(p.ts) <= currentTime.value!)
  })

  let _timer: ReturnType<typeof setInterval> | null = null

  async function loadReplay(window: '1h' | '24h' | '7d', token?: string) {
    try {
      const headers: Record<string, string> = {}
      const url = `/api/world/history?window=${window}&limit=5000`
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
    const step = 1000 * playbackSpeed.value  // 1 real second = playbackSpeed seconds
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
