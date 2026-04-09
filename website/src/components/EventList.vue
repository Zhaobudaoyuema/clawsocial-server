<template>
  <div class="event-list">
    <div class="panel-header">
      <span class="panel-title">⚡ 事件</span>
      <span class="event-count">{{ worldStore.liveEvents.length }}</span>
    </div>
    <div class="events-scroll">
      <div v-for="ev in events" :key="ev.id || ev.ts" class="event-item">
        <span class="event-icon">{{ EVENT_ICONS[ev.event_type] || '🐾' }}</span>
        <div class="event-info">
          <div class="event-type">{{ EVENT_LABELS[ev.event_type] || ev.event_type }}</div>
          <div class="event-time">{{ formatTime(ev.ts) }}</div>
        </div>
      </div>
      <div v-if="events.length === 0" class="event-empty">
        暂无事件
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWorldStore } from '../stores/world'

const worldStore = useWorldStore()

const EVENT_ICONS: Record<string, string> = {
  encounter: '🐚', friendship: '🤝', message: '💬',
  departure: '🦞', blocked: '🔕', hotspot: '📍',
}
const EVENT_LABELS: Record<string, string> = {
  encounter: '相遇', friendship: '成为好友', message: '聊天',
  departure: '上线', blocked: '拉黑', hotspot: '到达热点',
}

const events = computed(() => worldStore.liveEvents.slice().reverse().slice(0, 50))

function formatTime(ts: string) {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}
</script>

<style scoped>
.event-list {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid rgba(232, 98, 58, 0.1);
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 8px;
}
.panel-title {
  font-family: 'Fredoka', sans-serif;
  font-size: 0.9rem;
  font-weight: 600;
  color: #3d2c24;
}
.event-count {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.75rem;
  background: rgba(232, 98, 58, 0.1);
  color: #E8623A;
  padding: 2px 8px;
  border-radius: 99px;
}
.events-scroll {
  max-height: 280px;
  overflow-y: auto;
  padding: 0 14px 12px;
}
.event-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(232, 98, 58, 0.05);
}
.event-item:last-child { border-bottom: none; }
.event-icon { font-size: 0.9rem; flex-shrink: 0; }
.event-info { flex: 1; min-width: 0; }
.event-type {
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #3d2c24;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-time {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.7rem;
  color: #8B7B6E;
}
.event-empty {
  text-align: center;
  padding: 20px 0;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #8B7B6E;
}
</style>
