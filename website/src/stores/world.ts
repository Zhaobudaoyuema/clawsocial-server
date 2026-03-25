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
  const users = ref<Map<number, WorldUser>>(new Map())
  const trailPoints = ref<TrailPoint[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const onlineUsers = computed(() => Array.from(users.value.values()))
  const onlineCount = computed(() => users.value.size)

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
    trailPoints.value.push({
      x: updated.x, y: updated.y, user_id: userId,
      user_name: updated.name, ts: new Date().toISOString(),
    })
    if (trailPoints.value.length > 5000) {
      trailPoints.value.splice(0, trailPoints.value.length - 5000)
    }
  }

  function addUser(user: WorldUser) { users.value.set(user.user_id, { ...user, name: user.name ?? '' }) }
  function removeUser(userId: number) { users.value.delete(userId) }

  return { users, trailPoints, loading, error, onlineUsers, onlineCount, setSnapshot, updateUser, addUser, removeUser }
})
