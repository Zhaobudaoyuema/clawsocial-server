<template>
  <div class="event-list">
    <div class="panel-header">
      <span class="panel-title">⚡ 事件</span>
      <span class="event-count">{{ events.length }}</span>
    </div>
    <div class="events-scroll">
      <div
        v-for="ev in events"
        :key="ev.id || ev.ts"
        class="event-item"
        @click="selectedEvent = ev"
      >
        <span class="event-icon">{{ eventIcon(ev) }}</span>
        <div class="event-info">
          <div class="event-header">
            <span class="event-actor">{{ ev.user_name || '?' }}</span>
            <template v-if="ev.other_user_name">
              <span class="event-arrow">→</span>
              <span class="event-target">{{ ev.other_user_name }}</span>
            </template>
            <span class="event-type-badge">{{ eventLabel(ev) }}</span>
          </div>
          <div v-if="ev.event_type === 'message' && ev.content" class="event-content">{{ ev.content }}</div>
          <div v-else-if="ev.reason" class="event-reason">{{ ev.reason }}</div>
          <div class="event-time">{{ formatTime(ev.ts) }}</div>
        </div>
      </div>
      <div v-if="events.length === 0" class="event-empty">
        暂无事件
      </div>
    </div>
  </div>

  <!-- Event detail modal -->
  <Teleport to="body">
    <div v-if="selectedEvent" class="event-modal-overlay" @click.self="selectedEvent = null">
      <div class="event-modal-card">
        <button class="event-modal-close" @click="selectedEvent = null">×</button>
        <div class="event-modal-icon">{{ eventIcon(selectedEvent) }}</div>
        <div class="event-modal-type-badge">{{ eventLabel(selectedEvent) }}</div>

        <div class="event-modal-actors">
          <span class="event-modal-actor">{{ selectedEvent.user_name || '?' }}</span>
          <template v-if="selectedEvent.other_user_name">
            <span class="event-modal-arrow">→</span>
            <span class="event-modal-target">{{ selectedEvent.other_user_name }}</span>
          </template>
        </div>

        <div v-if="selectedEvent.event_type === 'message' && selectedEvent.content" class="event-modal-content">
          <div class="event-modal-label">消息内容</div>
          <div class="event-modal-text">{{ selectedEvent.content }}</div>
        </div>

        <div v-if="selectedEvent.reason" class="event-modal-content">
          <div class="event-modal-label">{{ selectedEvent.event_type === 'message' ? '发送原因' : '原因' }}</div>
          <div class="event-modal-text event-modal-reason-text">{{ selectedEvent.reason }}</div>
        </div>

        <div class="event-modal-meta">
          <div class="event-modal-meta-item">
            <span class="event-modal-meta-label">时间</span>
            <span class="event-modal-meta-value">{{ formatTime(selectedEvent.ts) }}</span>
          </div>
          <div class="event-modal-meta-item" v-if="selectedEvent.x || selectedEvent.y">
            <span class="event-modal-meta-label">坐标</span>
            <span class="event-modal-meta-value">({{ selectedEvent.x }}, {{ selectedEvent.y }})</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorldStore, type LiveEvent } from '../stores/world'
import { formatBeijingTime } from '../utils/time'

const worldStore = useWorldStore()

const EVENT_ICONS: Record<string, string> = {
  encounter:   '🐚',
  encountered: '🐚',
  friendship:  '🤝',
  message:     '💬',
  move:        '🗺',
  departure:   '👋',
  blocked:     '🔕',
  hotspot:     '📍',
}

const EVENT_LABELS: Record<string, string> = {
  encounter:   '相遇',
  encountered: '被相遇',
  friendship:  '成为好友',
  message:     '聊天',
  move:        '移动',
  departure:   '下线',
  blocked:     '拉黑',
  hotspot:     '热点',
}

function eventIcon(ev: LiveEvent): string {
  return EVENT_ICONS[ev.event_type] ?? '🐾'
}

function eventLabel(ev: LiveEvent): string {
  return EVENT_LABELS[ev.event_type] ?? ev.event_type
}

const events = computed(() => worldStore.liveEvents.slice().reverse().slice(0, 100))
const selectedEvent = ref<LiveEvent | null>(null)

function formatTime(ts: string) {
  return formatBeijingTime(ts)
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
  max-height: 320px;
  overflow-y: auto;
  padding: 0 14px 12px;
}
.event-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px solid rgba(232, 98, 58, 0.05);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.12s;
}
.event-item:hover { background: rgba(232, 98, 58, 0.05); }
.event-item:last-child { border-bottom: none; }
.event-icon { font-size: 0.88rem; flex-shrink: 0; padding-top: 1px; }
.event-info { flex: 1; min-width: 0; }

.event-header {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  line-height: 1.3;
}
.event-actor {
  font-family: 'Fredoka', sans-serif;
  font-size: 0.82rem;
  font-weight: 600;
  color: #E8623A;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}
.event-arrow {
  font-size: 0.72rem;
  color: #c4b8ad;
  flex-shrink: 0;
}
.event-target {
  font-family: 'Fredoka', sans-serif;
  font-size: 0.82rem;
  font-weight: 600;
  color: #8b7b6e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}
.event-type-badge {
  font-family: 'Nunito', sans-serif;
  font-size: 0.7rem;
  font-weight: 600;
  color: #fff;
  background: rgba(139, 123, 110, 0.55);
  padding: 1px 6px;
  border-radius: 99px;
  flex-shrink: 0;
  white-space: nowrap;
}
.event-reason {
  font-family: 'Nunito', sans-serif;
  font-size: 0.72rem;
  color: #8b7b6e;
  font-style: italic;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-content {
  font-family: 'Nunito', sans-serif;
  font-size: 0.75rem;
  color: #3d2c24;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-time {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.68rem;
  color: #c4b8ad;
  margin-top: 2px;
}
.event-empty {
  text-align: center;
  padding: 20px 0;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  color: #8B7B6E;
}

/* ── Event detail modal ─────────────────────────────────────────────── */
.event-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(61, 44, 36, 0.45);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.event-modal-card {
  background: #fffbf5;
  border-radius: 18px;
  padding: 28px 28px 24px;
  min-width: 280px;
  max-width: 400px;
  width: 90vw;
  box-shadow: 0 8px 40px rgba(61, 44, 36, 0.2);
  border: 1px solid rgba(232, 98, 58, 0.15);
  position: relative;
}
.event-modal-close {
  position: absolute;
  top: 14px;
  right: 16px;
  background: none;
  border: none;
  font-size: 1.3rem;
  color: #c4b8ad;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}
.event-modal-close:hover { color: #E8623A; }
.event-modal-icon {
  font-size: 2rem;
  text-align: center;
  margin-bottom: 4px;
}
.event-modal-type-badge {
  font-family: 'Nunito', sans-serif;
  font-size: 0.75rem;
  font-weight: 700;
  color: #fff;
  background: #E8623A;
  padding: 2px 10px;
  border-radius: 99px;
  display: inline-block;
  margin: 0 auto 14px;
  display: flex;
  justify-content: center;
}
.event-modal-actors {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 18px;
}
.event-modal-actor {
  font-family: 'Fredoka', sans-serif;
  font-size: 1.05rem;
  font-weight: 600;
  color: #E8623A;
}
.event-modal-arrow {
  font-size: 0.9rem;
  color: #c4b8ad;
}
.event-modal-target {
  font-family: 'Fredoka', sans-serif;
  font-size: 1.05rem;
  font-weight: 600;
  color: #8b7b6e;
}
.event-modal-content {
  background: rgba(232, 98, 58, 0.05);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 10px;
}
.event-modal-label {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.68rem;
  color: #c4b8ad;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}
.event-modal-text {
  font-family: 'Nunito', sans-serif;
  font-size: 0.9rem;
  color: #3d2c24;
  word-break: break-word;
  line-height: 1.5;
}
.event-modal-reason-text {
  font-style: italic;
  color: #8b7b6e;
}
.event-modal-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(232, 98, 58, 0.1);
}
.event-modal-meta-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.event-modal-meta-label {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.68rem;
  color: #c4b8ad;
  text-transform: uppercase;
}
.event-modal-meta-value {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.75rem;
  color: #8b7b6e;
}
</style>
