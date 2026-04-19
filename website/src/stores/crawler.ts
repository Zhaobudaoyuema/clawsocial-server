import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface SocialEvent {
  type: 'encounter' | 'friendship' | 'message' | 'departure'
  other_user_id: number | null
  other_name?: string
  x: number | null
  y: number | null
  ts: string
  content?: string | null
  reason?: string | null
}

export const useCrawlerStore = defineStore('crawler', () => {
  const token = ref<string | null>(null)  // SessionStorage, set via setToken
  const userId = ref<number | null>(null)
  const userName = ref<string>('—')
  const x = ref(0)
  const y = ref(0)
  const online = ref(false)
  const events = ref<SocialEvent[]>([])
  const friends = ref<number>(0)
  const connected = ref(false)

  const isLoggedIn = computed(() => !!token.value)

  function setToken(t: string) { token.value = t }
  function clearToken() { token.value = null; userId.value = null; userName.value = '—'; online.value = false }

  return { token, userId, userName, x, y, online, events, friends, connected, isLoggedIn, setToken, clearToken }
})
