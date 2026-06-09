<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useDeidStore } from '../../stores/deid'

const props = defineProps<{ menuOpen?: boolean }>()
defineEmits<{ toggleMenu: [] }>()

const store = useDeidStore()

const workerLabel = computed(() => {
  const w = store.workerStatus
  if (!w.online) return '智能扫描不可用'
  if (w.state === 'busy') return '智能扫描忙碌'
  return '智能扫描可用'
})

const workerDetail = computed(() => {
  const w = store.workerStatus
  if (!w.online) return '将使用已记住实体匹配'
  return '已就绪'
})

const queueHint = computed(() => {
  const q = store.queueStatus
  const cur = (store.currentJob as { id?: number } | null)?.id
  if (!cur) return null
  if (q.current_job_id === cur) return '正在扫描'
  const idx = q.waiting_job_ids.indexOf(cur)
  if (idx >= 0) {
    const total = q.waiting_count + (q.current_job_id ? 1 : 0)
    return `排队 ${idx + 1}/${total}`
  }
  return null
})

let pollTimer: ReturnType<typeof setInterval> | undefined

onMounted(async () => {
  await store.fetchWorkerStatus()
  pollTimer = setInterval(() => store.fetchWorkerStatus(), 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <header class="topbar">
    <div class="brand-row">
      <button type="button" class="menu-btn" :aria-label="props.menuOpen ? '关闭菜单' : '打开菜单'" @click="$emit('toggleMenu')">
        <svg v-if="!props.menuOpen" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
        </svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </button>
      <div class="brand">
        <span class="logo" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linejoin="round"
            />
            <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
            <path
              d="M8 14l2.5 2.5L16 11"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </span>
        <div>
          <h1>文档脱敏</h1>
          <p class="trust">本地处理 · 数据不出服务器</p>
        </div>
      </div>
    </div>
    <div class="status-row">
      <span v-if="queueHint" class="pill queue">{{ queueHint }}</span>
      <span class="pill worker" :class="store.workerStatus.online ? 'on' : 'off'">
        <span class="dot" />
        <span>{{ workerLabel }}</span>
        <span class="detail">{{ workerDetail }}</span>
      </span>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  height: var(--deid-topbar-height);
  padding: 0 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface);
  box-shadow: var(--deid-shadow-sm);
}
.brand-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.menu-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-sm);
  background: var(--deid-surface);
  color: var(--deid-ink);
  cursor: pointer;
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-primary-soft);
  color: var(--deid-primary);
  flex-shrink: 0;
}
h1 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.trust {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.status-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.875rem;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--deid-border);
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
}
.pill.queue {
  border-color: var(--deid-primary-soft);
  background: var(--deid-preset-bg);
  color: var(--deid-primary);
  font-weight: 500;
}
.pill.worker.on {
  border-color: var(--deid-success-border);
  background: var(--deid-success-bg);
  color: var(--deid-success);
}
.pill.worker.off .dot {
  background: var(--deid-ink-muted);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.detail {
  color: var(--deid-ink-muted);
  font-size: 0.8125rem;
}
.pill.worker.on .detail {
  color: var(--deid-success);
  opacity: 0.75;
}
@media (max-width: 768px) {
  .topbar {
    padding: 0 1rem;
  }
  .menu-btn {
    display: inline-flex;
  }
  .detail {
    display: none;
  }
}
</style>
