<script setup lang="ts">
import { computed, ref } from 'vue'
import DeidBadge from './DeidBadge.vue'
import DeidEmptyState from './DeidEmptyState.vue'
import DeidModal from './DeidModal.vue'
import { useDeidStore } from '../../stores/deid'

const props = defineProps<{
  activeJobId?: number | null
  entitiesActive?: boolean
  drawerOpen?: boolean
}>()
const emit = defineEmits<{
  select: [job: Record<string, unknown>]
  newTask: []
  openEntities: []
  closeDrawer: []
  deleted: [jobId: number]
}>()

const store = useDeidStore()

const deleteModalOpen = ref(false)
const pendingDelete = ref<Record<string, unknown> | null>(null)

const pendingDeleteName = computed(() =>
  pendingDelete.value
    ? (pendingDelete.value as { original_filename: string }).original_filename
    : '',
)

const statusMap: Record<string, { variant: 'draft' | 'scanned' | 'done' | 'failed' | 'running'; label: string }> = {
  draft: { variant: 'draft', label: '草稿' },
  queued: { variant: 'running', label: '排队' },
  scanning: { variant: 'running', label: '扫描中' },
  scanned: { variant: 'scanned', label: '待确认' },
  confirmed: { variant: 'scanned', label: '待确认' },
  running: { variant: 'running', label: '脱敏中' },
  done: { variant: 'done', label: '完成' },
  failed: { variant: 'failed', label: '失败' },
}

const currentJob = computed(() => store.currentJob)

function fmtHours(h: number | null | undefined) {
  if (h == null) return ''
  if (h < 1) return '1h 内清理'
  return `${Math.round(h)}h`
}

function ttlTitle(h: number | null | undefined) {
  if (h == null) return '完成后 8 小时自动清理，请及时下载'
  return `完成后约 ${Math.round(h)} 小时后自动清理，请及时下载`
}

const pendingDeleteTtl = computed(() => {
  const h = (pendingDelete.value as { hours_until_cleanup?: number } | null)?.hours_until_cleanup
  return ttlTitle(h)
})

function isActive(job: Record<string, unknown>) {
  if (props.activeJobId != null) return props.activeJobId === job.id
  return (currentJob.value as { id?: number } | null)?.id === job.id
}

function onSelect(job: Record<string, unknown>) {
  emit('select', job)
  emit('closeDrawer')
}

function onNewTask() {
  emit('newTask')
  emit('closeDrawer')
}

function onOpenEntities() {
  emit('openEntities')
  emit('closeDrawer')
}

function onDelete(job: Record<string, unknown>, e: Event) {
  e.stopPropagation()
  pendingDelete.value = job
  deleteModalOpen.value = true
}

async function confirmDelete() {
  if (!pendingDelete.value) return
  const id = (pendingDelete.value as { id: number }).id
  await store.deleteJob(id)
  emit('deleted', id)
  emit('closeDrawer')
  deleteModalOpen.value = false
  pendingDelete.value = null
}
</script>

<template>
  <aside class="rail" :class="{ open: drawerOpen }">
    <div class="rail-section">
      <div class="rail-label">任务</div>
      <ul v-if="store.jobsLoading" class="job-list job-skeleton" aria-busy="true" aria-label="加载任务列表">
        <li v-for="i in 3" :key="i" class="skeleton-row">
          <span class="skeleton-line skeleton-line--title" />
          <span class="skeleton-line skeleton-line--meta" />
        </li>
      </ul>
      <ul v-else-if="store.jobs.length" class="job-list">
        <li v-for="job in store.jobs" :key="(job as { id: number }).id" class="job-item">
          <button
            type="button"
            class="job-row"
            :class="{ active: isActive(job) && !entitiesActive }"
            @click="onSelect(job)"
          >
            <span class="fname">{{ (job as { original_filename: string }).original_filename }}</span>
            <span class="meta">
              <DeidBadge v-bind="statusMap[(job as { status: string }).status] || statusMap.draft" />
              <span
                v-if="(job as { hours_until_cleanup?: number }).hours_until_cleanup != null"
                class="ttl"
                :title="ttlTitle((job as { hours_until_cleanup: number }).hours_until_cleanup)"
              >
                {{ fmtHours((job as { hours_until_cleanup: number }).hours_until_cleanup) }}
              </span>
            </span>
          </button>
          <button
            type="button"
            class="job-delete"
            title="删除任务"
            aria-label="删除任务"
            @click="onDelete(job, $event)"
          >
            ×
          </button>
        </li>
      </ul>
      <DeidEmptyState
        v-else-if="!store.jobsLoading"
        title="还没有任务"
        hint="上传 Word 文档开始第一份脱敏"
        cta-label="上传第一份文档"
        @action="onNewTask"
      />
    </div>

    <div class="rail-foot">
      <button
        type="button"
        class="foot-btn nav-btn"
        :class="{ active: entitiesActive }"
        @click="onOpenEntities"
      >
        我的实体
      </button>
      <button type="button" class="foot-btn primary" @click="onNewTask">
        + 新建任务
      </button>
    </div>

    <DeidModal v-model:open="deleteModalOpen" title="删除任务？" danger persistent>
      <p>
        确定删除「<strong>{{ pendingDeleteName }}</strong>」？此操作不可恢复。
      </p>
      <p class="delete-ttl">{{ pendingDeleteTtl }}</p>
      <template #footer>
        <button type="button" class="deid-btn" @click="deleteModalOpen = false">取消</button>
        <button type="button" class="deid-btn deid-btn--danger" @click="confirmDelete">删除</button>
      </template>
    </DeidModal>
  </aside>
</template>

<style scoped>
.rail {
  width: var(--deid-rail-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--deid-border);
  background: var(--deid-rail-bg);
  min-height: calc(100vh - var(--deid-topbar-height));
}
@media (min-width: 769px) {
  .rail {
    min-height: 0;
    height: 100%;
    overflow: hidden;
  }
}
.rail-section {
  padding: 1rem 0.75rem;
}
.rail-label {
  padding: 0 0.65rem 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--deid-ink-muted);
}
.job-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: calc(100vh - var(--deid-topbar-height) - 220px);
  overflow-y: auto;
}
.job-item {
  position: relative;
  display: flex;
  align-items: stretch;
}
.job-item:hover .job-delete,
.job-item:focus-within .job-delete {
  opacity: 1;
}
.job-row {
  flex: 1;
  min-width: 0;
  text-align: left;
  padding: 0.75rem 0.85rem;
  border: none;
  background: transparent;
  border-radius: var(--deid-radius-sm);
  cursor: pointer;
  font-family: inherit;
}
.job-row:hover {
  background: var(--deid-surface-2);
}
.job-row.active {
  background: var(--deid-primary-soft);
  color: var(--deid-ink);
  box-shadow: inset 3px 0 0 var(--deid-primary);
}
.job-delete {
  flex-shrink: 0;
  align-self: center;
  width: 28px;
  height: 28px;
  margin-right: 0.35rem;
  border: none;
  border-radius: var(--deid-radius-sm);
  background: transparent;
  color: var(--deid-ink-muted);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0.45;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.job-delete:hover {
  background: var(--deid-danger-bg);
  color: var(--deid-danger);
}
@media (max-width: 768px) {
  .job-delete {
    opacity: 1;
  }
}
.fname {
  display: block;
  font-size: 0.9375rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 0.35rem;
}
.meta {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}
.ttl {
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  cursor: help;
  border-bottom: 1px dotted var(--deid-border-strong);
}
.rail-foot {
  margin-top: auto;
  padding: 1rem 0.75rem;
  border-top: 1px solid var(--deid-border);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.foot-btn {
  width: 100%;
  padding: 0.65rem 0.85rem;
  border: 1px solid transparent;
  border-radius: var(--deid-radius-sm);
  background: transparent;
  font-family: inherit;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  color: var(--deid-ink-secondary);
}
.foot-btn:hover {
  background: var(--deid-surface-2);
  color: var(--deid-ink);
}
.foot-btn.nav-btn.active {
  background: var(--deid-primary-soft);
  color: var(--deid-primary);
  box-shadow: inset 3px 0 0 var(--deid-primary);
}
.foot-btn.primary {
  background: var(--deid-primary);
  color: #fff;
  border-color: var(--deid-primary);
  text-align: center;
  box-shadow: 0 1px 2px rgba(94, 106, 210, 0.3);
}
.foot-btn.primary:hover {
  background: var(--deid-primary-hover);
  border-color: var(--deid-primary-hover);
  color: #fff;
}
.delete-ttl {
  margin: 0.75rem 0 0;
  font-size: 0.875rem;
  color: var(--deid-ink-muted);
}
.job-skeleton {
  pointer-events: none;
}
.skeleton-row {
  padding: 0.75rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.skeleton-line {
  display: block;
  height: 0.75rem;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    var(--deid-surface-2) 25%,
    var(--deid-surface-3) 50%,
    var(--deid-surface-2) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-pulse 1.2s ease-in-out infinite;
}
.skeleton-line--title {
  width: 72%;
  height: 0.85rem;
}
.skeleton-line--meta {
  width: 42%;
}
@keyframes skeleton-pulse {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}
@media (max-width: 768px) {
  .rail {
    position: fixed;
    top: var(--deid-topbar-height);
    left: 0;
    bottom: 0;
    z-index: var(--deid-drawer-z-index);
    width: min(300px, 88vw);
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: var(--deid-shadow-md);
  }
  .rail.open {
    transform: translateX(0);
  }
}
</style>
