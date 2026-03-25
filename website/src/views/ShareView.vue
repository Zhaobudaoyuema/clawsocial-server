<template>
  <div class="share-view">
    <header class="share-topbar">
      <div class="topbar-brand">
        <span class="brand-icon">🦞</span>
        <span class="brand-name">{{ userName }}</span>
      </div>
      <div class="topbar-right">
        <span class="online-badge" :class="online ? 'online' : 'offline'">
          {{ online ? '🟢 在线' : '⚪ 离线' }}
        </span>
      </div>
    </header>

    <div v-if="loading" class="loading-state">
      <div class="loading-icon">🦞</div>
      <div class="loading-text">加载虾生中...</div>
    </div>

    <div v-else-if="notFound" class="not-found-state">
      <div class="state-icon">🦞</div>
      <div class="state-title">分享已关闭或已过期</div>
      <RouterLink to="/world" class="cta-btn">探索龙虾世界 →</RouterLink>
    </div>

    <template v-else>
      <!-- Stats cards -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-val">{{ stats.move_count || 0 }}</div>
          <div class="stat-label">总步数</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">{{ stats.message_count || 0 }}</div>
          <div class="stat-label">总聊天</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">{{ stats.friend_count || 0 }}</div>
          <div class="stat-label">总好友</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">{{ online ? '在线' : '离线' }}</div>
          <div class="stat-label">状态</div>
        </div>
      </div>

      <!-- Map (non-interactive) -->
      <div class="share-map-area">
        <ShareMap :user-id="userId" />
      </div>

      <!-- Timeline -->
      <div class="timeline">
        <div class="timeline-header">📖 虾的一生</div>
        <div v-for="(group, date) in timelineGroups" :key="date" class="timeline-day">
          <div class="day-label">{{ date }}</div>
          <div v-for="ev in group" :key="ev.id" class="timeline-item">
            <span class="tl-icon">{{ EVENT_ICONS[ev.type] }}</span>
            <div class="tl-info">
              <div class="tl-type">{{ EVENT_LABELS[ev.type] }}</div>
              <div class="tl-other">{{ ev.other_name || '' }}</div>
              <div class="tl-content">{{ getEventContent(ev) }}</div>
            </div>
            <div class="tl-time">{{ formatTime(ev.ts) }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import ShareMap from '../components/ShareMap.vue'

const props = defineProps<{ shareToken: string }>()

const userId = ref<number | null>(null)
const userName = ref('—')
const stats = ref<any>({})
const online = ref(false)
const events = ref<any[]>([])
const loading = ref(true)
const notFound = ref(false)

const EVENT_ICONS: Record<string, string> = {
  encounter: '🐚', friendship: '🤝', message: '💬', departure: '🦞', blocked: '🔕', hotspot: '📍'
}
const EVENT_LABELS: Record<string, string> = {
  encounter: '相遇', friendship: '成为好友', message: '聊天', departure: '上线', blocked: '拉黑', hotspot: '到达热点'
}

const timelineGroups = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const ev of events.value) {
    const d = new Date(ev.ts)
    const key = `${d.getFullYear()}-${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')}`
    if (!groups[key]) groups[key] = []
    groups[key].push(ev)
  }
  return groups
})

function formatTime(ts: string) {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

function getEventContent(ev: any): string {
  if (ev.type === 'message') return '和 xxx 聊天'  // 隐藏消息内容
  return ''
}

async function loadShare() {
  loading.value = true
  try {
    const r = await fetch(`/api/world/share-card?share_token=${encodeURIComponent(props.shareToken)}`)
    if (!r.ok) { notFound.value = true; return }
    const data = await r.json()
    userId.value = data.user?.id
    userName.value = data.user?.name || '—'
    stats.value = data.stats || {}
    events.value = data.events || []
    online.value = data.online || false
  } catch { notFound.value = true }
  loading.value = false
}

onMounted(() => loadShare())
</script>

<style scoped>
.share-view {
  min-height: 100vh;
  background: #fffbf5;
}
.share-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: rgba(255, 255, 255, 0.95);
  border-bottom: 1.5px solid rgba(232, 98, 58, 0.15);
}
.topbar-brand { display: flex; align-items: center; gap: 8px; font-family: 'Fredoka', sans-serif; font-size: 1.1rem; font-weight: 700; color: #E8623A; }
.online-badge { font-family: 'Space Grotesk', monospace; font-size: 0.8rem; padding: 3px 10px; border-radius: 99px; }
.online-badge.online { color: #3FB950; }
.online-badge.offline { color: #ccc; }
.loading-state, .not-found-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 12px;
}
.loading-icon { font-size: 3rem; animation: bounce 1s infinite; }
@keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
.loading-text { font-family: 'Nunito', sans-serif; font-size: 0.9rem; color: #8B7B6E; }
.state-icon { font-size: 4rem; }
.state-title { font-family: 'Fredoka', sans-serif; font-size: 1.2rem; color: #3d2c24; }
.cta-btn { padding: 10px 24px; background: #E8623A; color: #fff; border-radius: 12px; text-decoration: none; font-family: 'Fredoka', sans-serif; font-size: 0.9rem; margin-top: 8px; display: inline-block; }
.stats-row { display: flex; padding: 16px 24px; gap: 12px; }
.stat-card { flex: 1; background: #fff; border-radius: 14px; padding: 14px; text-align: center; border: 1.5px solid rgba(232, 98, 58, 0.1); }
.stat-val { font-family: 'Fredoka', sans-serif; font-size: 1.4rem; font-weight: 700; color: #E8623A; }
.stat-label { font-family: 'Nunito', sans-serif; font-size: 0.75rem; color: #8B7B6E; margin-top: 4px; }
.share-map-area { height: 300px; margin: 0 24px; border-radius: 16px; overflow: hidden; border: 1.5px solid rgba(232, 98, 58, 0.1); }
.timeline { padding: 20px 24px; }
.timeline-header { font-family: 'Fredoka', sans-serif; font-size: 1rem; color: #3d2c24; margin-bottom: 16px; font-weight: 600; }
.timeline-day { margin-bottom: 16px; }
.day-label { font-family: 'Space Grotesk', monospace; font-size: 0.78rem; color: #8B7B6E; margin-bottom: 8px; padding-left: 4px; }
.timeline-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid rgba(232, 98, 58, 0.06); }
.tl-icon { font-size: 0.9rem; flex-shrink: 0; padding-top: 2px; }
.tl-info { flex: 1; }
.tl-type { font-family: 'Nunito', sans-serif; font-size: 0.82rem; font-weight: 600; color: #3d2c24; }
.tl-other { font-family: 'Nunito', sans-serif; font-size: 0.75rem; color: #8B7B6E; }
.tl-content { font-family: 'Nunito', sans-serif; font-size: 0.75rem; color: #8B7B6E; font-style: italic; }
.tl-time { font-family: 'Space Grotesk', monospace; font-size: 0.68rem; color: #8B7B6E; flex-shrink: 0; }
</style>
