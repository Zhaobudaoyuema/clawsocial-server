<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'

const props = defineProps<{ jobId: number }>()

const store = useDeidStore()

const running = computed(() => store.programScanRunning)
const payload = computed(() => store.programScan)
const changes = computed(() =>
  (payload.value?.changes || []).filter((c) => !c.reverted),
)
const reverted = computed(() =>
  (payload.value?.changes || []).filter((c) => c.reverted),
)

async function ensureScan() {
  if (!props.jobId || store.programScan || running.value) return
  if ((store.currentJob as { status?: string } | null)?.status === 'program_review') {
    await store.fetchProgramScan(props.jobId)
    return
  }
  await store.runProgramScan(props.jobId)
}

onMounted(() => {
  void ensureScan()
})

watch(
  () => props.jobId,
  () => {
    void ensureScan()
  },
)

async function onRescan() {
  await store.runProgramScan(props.jobId)
}

async function onRevert(changeId: string) {
  await store.revertProgramScanChange(props.jobId, changeId)
}

async function onConfirm() {
  await store.confirmProgramScan(props.jobId)
}
</script>

<template>
  <section class="program-stage">
    <h2 class="deid-page-title">程序扫描</h2>
    <p class="deid-page-sub">
      对 Markdown 源文做最长优先干跑替换与验漏，自动补全别名或新建实体
    </p>

    <div v-if="running" class="panel deid-panel running-card">
      <span class="deid-spinner" aria-hidden="true" />
      <p>程序扫描中…</p>
    </div>

    <template v-else-if="payload">
      <div class="stats deid-panel">
        <div class="stat">
          <span class="stat-label">扫描前残留</span>
          <span class="stat-value">{{ payload.residual_before ?? '—' }}</span>
        </div>
        <div class="stat-arrow" aria-hidden="true">→</div>
        <div class="stat">
          <span class="stat-label">扫描后残留</span>
          <span class="stat-value" :class="{ ok: (payload.residual_after ?? 0) === 0 }">
            {{ payload.residual_after ?? '—' }}
          </span>
        </div>
      </div>

      <div v-if="!changes.length && !reverted.length" class="empty deid-panel">
        未发现需补全的实体或别名，可直接进入确认。
      </div>

      <ul v-if="changes.length" class="change-list deid-panel">
        <li v-for="c in changes" :key="c.id" class="change-item">
          <div class="change-main">
            <span class="badge" :class="c.action === 'new_entity' ? 'badge-new' : 'badge-alias'">
              {{ c.action === 'new_entity' ? '新建实体' : '扩展别名' }}
            </span>
            <span v-if="c.action === 'add_alias' && c.canonical_name" class="change-meta">
              → {{ c.canonical_name }}
            </span>
            <p class="change-text deid-mono">{{ c.text }}</p>
            <p v-if="c.hit_count" class="change-hits">命中 {{ c.hit_count }} 处</p>
          </div>
          <button type="button" class="deid-btn deid-btn--ghost" @click="onRevert(c.id)">
            撤销
          </button>
        </li>
      </ul>

      <details v-if="reverted.length" class="reverted">
        <summary>已撤销（{{ reverted.length }}）</summary>
        <ul>
          <li v-for="c in reverted" :key="c.id" class="deid-mono">{{ c.text }}</li>
        </ul>
      </details>

      <p v-if="store.error" class="err">{{ store.error }}</p>

      <footer class="foot">
        <button type="button" class="deid-btn" :disabled="running" @click="onRescan">
          重新扫描
        </button>
        <button
          type="button"
          class="deid-btn deid-btn--primary deid-btn--lg"
          :disabled="running || store.loading"
          @click="onConfirm"
        >
          进入确认
        </button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.program-stage {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.running-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem;
}
.stats {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.875rem 1rem;
}
.stat-label {
  display: block;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
}
.stat-value.ok {
  color: var(--deid-success);
}
.stat-arrow {
  color: var(--deid-ink-muted);
  font-size: 1.125rem;
}
.change-list {
  list-style: none;
  margin: 0;
  padding: 0.5rem 0;
}
.change-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--deid-border);
}
.change-item:last-child {
  border-bottom: none;
}
.change-main {
  flex: 1;
  min-width: 0;
}
.badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  margin-bottom: 0.35rem;
}
.badge-alias {
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
}
.badge-new {
  background: color-mix(in srgb, var(--deid-primary) 12%, transparent);
  color: var(--deid-primary);
}
.change-meta {
  margin-left: 0.5rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.change-text {
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  word-break: break-word;
}
.change-hits {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
}
.reverted {
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.empty {
  padding: 1rem;
  color: var(--deid-ink-muted);
}
.foot {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 0.25rem;
}
.err {
  color: var(--deid-danger);
  margin: 0;
}
</style>
