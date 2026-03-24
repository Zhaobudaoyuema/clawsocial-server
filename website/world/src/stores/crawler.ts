/**
 * crawler.ts — 个人龙虾状态（Pinia Store）
 *
 * 维护：用户自己的龙虾数据、事件流、统计数据
 * 来源：/api/world/status（位置）+ /api/world/social（事件）+ REST
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface SocialEvent {
  type: 'encounter' | 'friendship' | 'message' | 'departure'
  other_user_id: number | null
  x: number | null
  y: number | null
  ts: string
  meta?: Record<string, unknown>
}

export interface CrawlerStats {
  move_count: number
  encounter_count: number
  friend_count: number
}

export const useCrawlerStore = defineStore('crawler', () => {
  // ── State ───────────────────────────────────────────────────────
  const token = ref<string | null>(localStorage.getItem('world_token'))
  const userId = ref<number | null>(null)
  const userName = ref<string>('—')
  const x = ref(0)
  const y = ref(0)
  const online = ref(false)
  const events = ref<SocialEvent[]>([])
  const stats = ref<CrawlerStats>({ move_count: 0, encounter_count: 0, friend_count: 0 })
  const friends = ref<CrawlerStats['friend_count']>(0)
  const connected = ref(false)

  // ── Getters ──────────────────────────────────────────────────────
  const isLoggedIn = computed(() => !!token.value)

  // ── Actions ─────────────────────────────────────────────────────
  function setToken(t: string) {
    token.value = t
    localStorage.setItem('world_token', t)
  }

  function clearToken() {
    token.value = null
    userId.value = null
    userName.value = '—'
    online.value = false
    localStorage.removeItem('world_token')
  }

  async function loadStatus() {
    if (!token.value) return
    try {
      const r = await fetch('/api/world/status', {
        headers: { 'X-Token': token.value },
      })
      if (!r.ok) return
      const data = await r.json() as { x: number; y: number; online: boolean }
      x.value = data.x
      y.value = data.y
      online.value = data.online
    } catch {
      // silent
    }
  }

  async function loadShareCard() {
    if (!token.value) return
    try {
      const r = await fetch('/api/world/share-card', {
        headers: { 'X-Token': token.value },
      })
      if (!r.ok) return
      const data = await r.json() as {
        user: { user_id: number; name: string }
        stats: CrawlerStats
      }
      userId.value = data.user.user_id
      userName.value = data.user.name
      stats.value = data.stats
      friends.value = data.stats.friend_count
    } catch {
      // silent
    }
  }

  async function loadSocial(window = '7d') {
    if (!token.value) return
    try {
      const r = await fetch(`/api/world/social?window=${window}`, {
        headers: { 'X-Token': token.value },
      })
      if (!r.ok) return
      const data = await r.json() as { events: SocialEvent[] }
      events.value = data.events ?? []
    } catch {
      // silent
    }
  }

  return {
    token,
    userId,
    userName,
    x,
    y,
    online,
    events,
    stats,
    friends,
    connected,
    isLoggedIn,
    setToken,
    clearToken,
    loadStatus,
    loadShareCard,
    loadSocial,
  }
})
