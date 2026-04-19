/**
 * useCrawlerWs — 个人龙虾 WebSocket 连接
 *
 * 连接：/ws/observe?type=crawler&token=xxx
 *
 * 消息类型：
 *   ready     — 连接成功，包含用户基本信息 {type, user: {id, name}, is_owner, is_share}
 *   crawler   — 个人龙虾实时数据 {type, ts, user_id, x, y, online_count, events: [...]}
 *   error     — 错误推送
 */
import { ref } from 'vue'
import { useCrawlerStore } from '../stores/crawler'

interface SocialEvent {
  type: 'encounter' | 'friendship' | 'message' | 'departure'
  other_user_id: number | null
  other_name?: string
  x: number | null
  y: number | null
  ts: string
  content?: string | null
  reason?: string | null
}

export function useCrawlerWs() {
  const crawlerStore = useCrawlerStore()
  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect(token: string) {
    if (ws) {
      ws.close()
      ws = null
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws/observe?type=crawler&token=${encodeURIComponent(token)}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      crawlerStore.connected = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    ws.onclose = () => {
      connected.value = false
      crawlerStore.connected = false
      ws = null
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          if (token) connect(token)
        }, 3000)
      }
    }

    ws.onerror = () => {
      ws?.close()
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string) as Record<string, unknown>

        if (msg.type === 'ready') {
          const user = msg.user as { id: number; name: string }
          crawlerStore.userId = user.id
          crawlerStore.userName = user.name
        } else if (msg.type === 'crawler') {
          crawlerStore.x = msg.x as number
          crawlerStore.y = msg.y as number
          crawlerStore.online = true

          const events = (msg.events as Array<Record<string, unknown>>) || []
          crawlerStore.events = events.map((e) => ({
            type: (e.type || 'message') as SocialEvent['type'],
            other_user_id: e.other_user_id as number | null,
            other_name: e.other_user_name as string | undefined,
            x: e.x as number | null,
            y: e.y as number | null,
            ts: e.ts as string,
            content: (e.content ?? null) as string | null,
            reason: (e.reason ?? null) as string | null,
          }))
        }
      } catch {
        // ignore parse errors
      }
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
    crawlerStore.connected = false
  }

  return { connected, connect, disconnect }
}
