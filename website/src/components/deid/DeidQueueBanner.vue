<script setup lang="ts">
import { computed } from 'vue'
import { useDeidStore } from '../../stores/deid'

const store = useDeidStore()

const currentJobId = computed(() => (store.currentJob as { id?: number } | null)?.id)

const myPosition = computed(() => {
  const q = store.queueStatus
  if (!currentJobId.value) return null
  if (q.current_job_id === currentJobId.value) return 0
  const idx = q.waiting_job_ids.indexOf(currentJobId.value)
  return idx >= 0 ? idx + 1 : null
})

const show = computed(() => {
  const status = (store.currentJob as { status?: string } | null)?.status
  if (status !== 'scanning' && status !== 'queued') return false
  return store.queueStatus.waiting_count > 0 || store.queueStatus.current_job_id != null
})

const message = computed(() => {
  const waiting = store.queueStatus.waiting_count
  const pos = myPosition.value
  if (pos === 0) return '正在扫描你的文档…'
  if (pos != null && pos > 0) return `${waiting + 1} 个任务扫描中 · 你排第 ${pos} 位`
  if (waiting > 0) return `${waiting} 个任务排队中`
  return '扫描队列处理中…'
})
</script>

<template>
  <div v-if="show" class="queue-banner" role="status">
    <span class="deid-spinner" aria-hidden="true" />
    {{ message }}
  </div>
</template>

<style scoped>
.queue-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem;
  background: var(--deid-preset-bg);
  border: 1px solid #bfdbfe;
  border-radius: var(--deid-radius-sm);
  font-size: 0.875rem;
  color: var(--deid-preset);
  margin-bottom: 1rem;
}
</style>
