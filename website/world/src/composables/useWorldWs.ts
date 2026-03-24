/**
 * useWorldWs — 前端观测者 WebSocket 连接
 *
 * 订阅 /ws/observer，获取：
 *   global_snapshot — 初始全量用户快照
 *   user_moved     — 任意龙虾移动
 *   user_spawned   — 龙虾上线
 *   user_left      — 龙虾下线
 *
 * 自动重连，Vue Store 响应式更新。
 */
import { ref, onUnmounted } from 'vue'
import { useWorldStore } from '../stores/world'

export function useWorldWs() {
  const store = useWorldStore()
  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    if (ws) return

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/ws/world/observer`
    ws = new WebSocket(url)

    ws.addEventListener('open', () => {
      connected.value = true
      store.clearToast()
    })

    ws.addEventListener('message', (evt) => {
      try {
        const msg = JSON.parse(evt.data as string) as Record<string, unknown>
        handleMessage(msg)
      } catch {
        // ignore parse errors
      }
    })

    ws.addEventListener('close', () => {
      connected.value = false
      ws = null
      // 自动重连
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          connect()
        }, 5000)
      }
    })

    ws.addEventListener('error', () => ws?.close())
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws?.close()
    ws = null
    connected.value = false
  }

  function handleMessage(msg: Record<string, unknown>) {
    const t = msg.type as string
    switch (t) {
      case 'global_snapshot': {
        const users = msg.users as Array<Record<string, unknown>>
        store.setSnapshot(users.map(u => ({
          user_id: u.user_id as number,
          name: (u.name as string | undefined) ?? '',
          x: u.x as number,
          y: u.y as number,
        })))
        break
      }
      case 'user_moved':
        store.updateUser(msg.user_id as number, {
          x: msg.x as number,
          y: msg.y as number,
        })
        break
      case 'user_spawned':
        store.addUser({
          user_id: msg.user_id as number,
          name: msg.user_name as string,
          x: msg.x as number,
          y: msg.y as number,
        })
        break
      case 'user_left':
        store.removeUser(msg.user_id as number)
        break
    }
  }

  onUnmounted(() => disconnect())

  return { connected, connect, disconnect }
}
