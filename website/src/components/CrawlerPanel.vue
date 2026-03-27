<template>
  <div class="crawler-panel">
    <!-- 7天事件（默认展开） -->
    <div class="panel-section">
      <button class="panel-toggle" @click="uiStore.toggleEventPanel()">
        <span>⚡ 近7天事件</span>
        <span class="toggle-arrow" :class="{ open: uiStore.eventPanelOpen }">▼</span>
      </button>
      <div v-if="uiStore.eventPanelOpen" class="panel-content">
        <div v-for="ev in events" :key="ev.id" class="event-row">
          <span class="ev-icon">{{ EVENT_ICONS[ev.type] }}</span>
          <div class="ev-info">
            <div class="ev-type">{{ EVENT_LABELS[ev.type] }}</div>
            <div class="ev-name">{{ ev.other_name || '—' }}</div>
            <div v-if="ev.content" class="ev-content">{{ ev.content }}</div>
          </div>
          <div class="ev-time">{{ formatTime(ev.ts) }}</div>
        </div>
        <div v-if="loadingMore" class="load-more">加载中...</div>
        <div v-else-if="hasMore" class="load-more" @click="loadMore">加载更多</div>
        <div v-if="events.length === 0" class="empty">暂无事件</div>
      </div>
    </div>

    <!-- 好友列表 -->
    <div class="panel-section">
      <button class="panel-toggle" @click="uiStore.toggleFriendPanel()">
        <span>🤝 好友</span>
        <span class="toggle-arrow" :class="{ open: uiStore.friendPanelOpen }">▼</span>
      </button>
      <div v-if="uiStore.friendPanelOpen" class="panel-content">
        <div v-for="f in friends" :key="f.id" class="friend-row">
          <span class="friend-name">{{ f.name }}</span>
          <span class="friend-time">{{ formatDate(f.last_seen) }}</span>
        </div>
        <div v-if="friends.length === 0" class="empty">暂无好友</div>
      </div>
    </div>

    <!-- 相遇记录 -->
    <div class="panel-section">
      <button class="panel-toggle" @click="uiStore.toggleEncounterPanel()">
        <span>🐚 相遇</span>
        <span class="toggle-arrow" :class="{ open: uiStore.encounterPanelOpen }">▼</span>
      </button>
      <div v-if="uiStore.encounterPanelOpen" class="panel-content">
        <div v-for="e in encounters" :key="e.id" class="encounter-row">
          <span class="enc-name">{{ e.name }}</span>
          <span class="enc-time">{{ formatDate(e.ts) }}</span>
        </div>
        <div v-if="encounters.length === 0" class="empty">暂无相遇记录</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUiStore } from '../stores/ui'
import { useCrawlerStore } from '../stores/crawler'

const uiStore = useUiStore()
const crawlerStore = useCrawlerStore()

const events = ref<any[]>([])
const friends = ref<any[]>([])
const encounters = ref<any[]>([])
const cursor = ref<string | null>(null)
const hasMore = ref(true)
const loadingMore = ref(false)

const EVENT_ICONS: Record<string, string> = {
  encounter: '🐚', friendship: '🤝', message: '💬', departure: '🦞', blocked: '🔕', hotspot: '📍'
}
const EVENT_LABELS: Record<string, string> = {
  encounter: '相遇', friendship: '成为好友', message: '聊天', departure: '上线', blocked: '拉黑', hotspot: '到达热点'
}

function formatTime(ts: string) {
  const d = new Date(ts)
  return `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}
function formatDate(ts: string) {
  const d = new Date(ts)
  return `${d.getMonth()+1}/${d.getDate()}`
}

async function loadEvents() {
  if (!crawlerStore.token) return
  try {
    const url = cursor.value
      ? `/api/client/history/social?cursor=${encodeURIComponent(cursor.value)}&limit=20`
      : `/api/client/history/social?limit=20`
    const r = await fetch(url, {
      headers: { 'X-Token': crawlerStore.token }
    })
    if (!r.ok) return
    const data = await r.json()
    const newEvents = (data.data || []).map((e: any, i: number) => ({
      id: e.id ?? (Date.now() + i),
      type: e.type,
      other_user_id: e.other_user_id,
      other_name: e.other_user_name || '?',
      x: e.x,
      y: e.y,
      ts: e.ts,
    }))
    if (!cursor.value) events.value = newEvents
    else events.value.push(...newEvents)
    cursor.value = data.pagination?.next_cursor ?? null
    hasMore.value = data.pagination?.has_more ?? false
  } catch {}
}

async function loadFriends() {
  if (!crawlerStore.token) return
  try {
    const r = await fetch('/friends', { headers: { 'X-Token': crawlerStore.token } })
    if (!r.ok) return
    const text = await r.text()
    const lines = text.trim().split('\n')
    friends.value = lines.slice(1).map((l: string) => {
      const [id, name, status, last_seen] = l.split('\t')
      return { id: Number(id), name, status, last_seen }
    }).filter((f: any) => f.status === 'accepted')
  } catch {}
}

async function loadEncounters() {
  if (!crawlerStore.token) return
  encounters.value = events.value
    .filter((e: any) => e.type === 'encounter')
    .map((e: any) => ({ id: e.id, name: e.other_name || '?', ts: e.ts }))
}

async function loadMore() {
  loadingMore.value = true
  await loadEvents()
  loadingMore.value = false
}

onMounted(async () => {
  await Promise.all([loadEvents(), loadFriends()])
  await loadEncounters()
})
</script>

<style scoped>
.crawler-panel { display: flex; flex-direction: column; }
.panel-section { border-bottom: 1px solid rgba(232, 98, 58, 0.1); }
.panel-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: none;
  border: none;
  cursor: pointer;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.88rem;
  font-weight: 600;
  color: #3d2c24;
  text-align: left;
}
.panel-toggle:hover { background: rgba(232, 98, 58, 0.04); }
.toggle-arrow {
  font-size: 0.6rem;
  color: #8B7B6E;
  transition: transform 0.2s;
}
.toggle-arrow.open { transform: rotate(180deg); }
.panel-content { padding: 4px 14px 12px; }
.event-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(232, 98, 58, 0.05);
}
.event-row:last-child { border-bottom: none; }
.ev-icon { font-size: 0.9rem; flex-shrink: 0; padding-top: 2px; }
.ev-info { flex: 1; min-width: 0; }
.ev-type {
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #3d2c24;
  font-weight: 600;
}
.ev-name {
  font-family: 'Nunito', sans-serif;
  font-size: 0.75rem;
  color: #8B7B6E;
}
.ev-content {
  font-family: 'Nunito', sans-serif;
  font-size: 0.75rem;
  color: #E8623A;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ev-time {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.68rem;
  color: #8B7B6E;
  flex-shrink: 0;
}
.friend-row, .encounter-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid rgba(232, 98, 58, 0.05);
}
.friend-row:last-child, .encounter-row:last-child { border-bottom: none; }
.friend-name, .enc-name {
  font-family: 'Nunito', sans-serif;
  font-size: 0.82rem;
  color: #3d2c24;
}
.friend-time, .enc-time {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.7rem;
  color: #8B7B6E;
}
.load-more {
  text-align: center;
  padding: 10px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #E8623A;
  cursor: pointer;
}
.empty {
  text-align: center;
  padding: 16px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #8B7B6E;
}
</style>
