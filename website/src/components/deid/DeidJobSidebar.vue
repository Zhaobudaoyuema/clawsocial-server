<script setup lang="ts">
import DeidBadge from './DeidBadge.vue'
import { useDeidStore } from '../../stores/deid'

const store = useDeidStore()
const props = defineProps<{
  activeJobId?: number | null
}>()
const emit = defineEmits<{ select: [job: Record<string, unknown>]; newTask: [] }>()

const statusMap: Record<string, { variant: 'draft' | 'scanned' | 'done' | 'failed' | 'running'; label: string }> = {
  draft: { variant: 'draft', label: '草稿' },
  queued: { variant: 'running', label: '排队中' },
  scanning: { variant: 'running', label: '扫描中' },
  scanned: { variant: 'scanned', label: '待确认' },
  confirmed: { variant: 'scanned', label: '已确认' },
  running: { variant: 'running', label: '脱敏中' },
  done: { variant: 'done', label: '已完成' },
  failed: { variant: 'failed', label: '失败' },
}

function fmtHours(h: number | null | undefined) {
  if (h == null) return ''
  if (h < 1) return '约 1 小时内清理'
  return `约 ${Math.round(h)} 小时后清理`
}

function isActive(job: Record<string, unknown>) {
  if (props.activeJobId != null) {
    return props.activeJobId === job.id
  }
  return (store.currentJob as { id?: number } | null)?.id === job.id
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-head">任务历史</div>
    <div v-if="!store.jobs.length" class="empty">
      <p class="empty-title">暂无任务</p>
      <p class="empty-hint">上传文档开始脱敏，或查看最近 8 小时内的已完成任务</p>
      <button type="button" class="deid-btn deid-btn--primary" @click="emit('newTask')">
        上传文档
      </button>
    </div>
    <ul v-else class="job-list">
      <li
        v-for="job in store.jobs"
        :key="(job as { id: number }).id"
        class="job-item"
        :class="{ active: isActive(job) }"
      >
        <button type="button" class="job-btn" @click="emit('select', job)">
          <span class="fname">{{ (job as { original_filename: string }).original_filename }}</span>
          <span class="meta">
            <DeidBadge
              v-bind="statusMap[(job as { status: string }).status] || statusMap.draft"
            />
            <span v-if="(job as { hours_until_cleanup?: number }).hours_until_cleanup != null" class="ttl">
              {{ fmtHours((job as { hours_until_cleanup: number }).hours_until_cleanup) }}
            </span>
          </span>
        </button>
      </li>
    </ul>
    <button type="button" class="new-btn deid-btn deid-btn--primary" @click="emit('newTask')">
      + 新建任务
    </button>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  flex-shrink: 0;
  background: var(--deid-surface);
  border-right: 1px solid var(--deid-border);
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 56px);
}
.sidebar-head {
  padding: 1rem 1.25rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--deid-ink-muted);
}
.job-list {
  list-style: none;
  margin: 0;
  padding: 0.5rem 0;
  flex: 1;
  overflow-y: auto;
}
.job-item {
  margin: 0;
}
.job-btn {
  width: 100%;
  text-align: left;
  padding: 0.75rem 1.25rem;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  border-left: 3px solid transparent;
  min-height: 44px;
}
.job-item.active .job-btn {
  background: var(--deid-surface-2);
  border-left-color: var(--deid-primary);
}
.job-btn:hover {
  background: var(--deid-surface-2);
}
.fname {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 0.35rem;
}
.meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.ttl {
  font-size: 0.7rem;
  color: var(--deid-ink-muted);
}
.empty {
  padding: 1.5rem 1.25rem;
  text-align: center;
}
.empty-title {
  margin: 0;
  font-weight: 600;
  font-size: 0.9rem;
}
.empty-hint {
  margin: 0.35rem 0 1rem;
  color: var(--deid-ink-muted);
  font-size: 0.8125rem;
}
.new-btn {
  margin: auto 1rem 1rem;
  width: calc(100% - 2rem);
}
@media (max-width: 768px) {
  .sidebar {
    width: 100%;
    min-height: auto;
    border-right: none;
    border-bottom: 1px solid var(--deid-border);
    max-height: 200px;
  }
}
</style>
