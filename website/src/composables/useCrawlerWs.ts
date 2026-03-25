import { ref } from 'vue'
import { useCrawlerStore } from '../stores/crawler'

export function useCrawlerWs() {
  const crawlerStore = useCrawlerStore()
  const connected = ref(false)
  let ws: WebSocket | null = null

  function connect(token: string) {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws/crawler?token=${encodeURIComponent(token)}`)

    ws.onopen = () => { connected.value = true; crawlerStore.connected = true }
    ws.onclose = () => {
      connected.value = false; crawlerStore.connected = false
      setTimeout(() => { if (token) connect(token) }, 3000)
    }
    ws.onerror = () => { ws?.close() }
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'ready') {
          crawlerStore.userId = msg.user.id
          crawlerStore.userName = msg.user.name
        } else if (msg.type === 'step_context') {
          crawlerStore.x = msg.x
          crawlerStore.y = msg.y
          crawlerStore.online = true
        }
      } catch {}
    }
  }

  function disconnect() {
    if (ws) { ws.close(); ws = null }
  }

  return { connected, connect, disconnect }
}
