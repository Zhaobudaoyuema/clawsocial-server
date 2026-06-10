<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'

const props = defineProps<{
  jobId: number | null | undefined
  active: boolean
}>()

const store = useDeidStore()
const expandedId = ref<number | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const FLOW_LABELS: Record<string, string> = {
  entity_scan: '实体扫描',
  re_discover: '再识别',
  deep_detect: '语义检测',
  deep_suggest: '语义改写',
  post_run_verify: '验漏',
  export_readiness: '就绪评估',
  scan_experience: '扫描经验',
}

const calls = computed(() => store.workerCalls)

watch(
  () => [props.active, props.jobId] as const,
  async ([active, jobId]) => {
    if (!active || !jobId) return
    loading.value = true
    error.value = null
    try {
      await store.fetchWorkerCalls(jobId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

function flowLabel(flowId: string) {
  return FLOW_LABELS[flowId] || flowId
}

function toggle(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}
</script>

<template>
  <div class="worker-calls">
    <p v-if="loading" class="worker-calls__hint">加载 Worker 调用记录…</p>
    <p v-else-if="error" class="worker-calls__error">{{ error }}</p>
    <p v-else-if="!calls.length" class="worker-calls__hint">暂无 Worker 调用记录</p>
    <ul v-else class="worker-calls__list">
      <li v-for="c in calls" :key="c.id as number" class="worker-calls__item">
        <button type="button" class="worker-calls__head" @click="toggle(c.id as number)">
          <span class="worker-calls__badge">{{ flowLabel(String(c.flow_id)) }}</span>
          <span class="worker-calls__meta">
            #{{ c.id }} · 段 {{ c.chunk_index }}/{{ c.chunk_total }}
            <template v-if="c.parsed_count"> · 解析 {{ c.parsed_count }}</template>
            <template v-if="c.error"> · <span class="err">{{ c.error }}</span></template>
          </span>
          <span class="worker-calls__chev">{{ expandedId === c.id ? '▾' : '▸' }}</span>
        </button>
        <div v-if="expandedId === c.id" class="worker-calls__body">
          <div class="block">
            <div class="block-label">system</div>
            <pre class="block-pre">{{ c.system_prompt }}</pre>
          </div>
          <div class="block">
            <div class="block-label">user</div>
            <pre class="block-pre">{{ c.user_message }}</pre>
          </div>
          <div class="block">
            <div class="block-label">response</div>
            <pre class="block-pre">{{ c.response || (c.error ? `（错误：${c.error}）` : '（空）') }}</pre>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.worker-calls {
  max-height: min(60vh, 480px);
  overflow: auto;
  font-family: var(--deid-font-mono, Consolas, monospace);
  font-size: 0.75rem;
}
.worker-calls__hint {
  margin: 0;
  padding: 1rem 0;
  color: #5a8f72;
  text-align: center;
}
.worker-calls__error {
  margin: 0;
  padding: 0.75rem;
  color: #f87171;
}
.worker-calls__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.worker-calls__item {
  border-bottom: 1px solid #1a3d2e;
}
.worker-calls__head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 0.35rem;
  border: none;
  background: transparent;
  color: #a7f3d0;
  cursor: pointer;
  text-align: left;
  font: inherit;
}
.worker-calls__head:hover {
  background: rgba(0, 255, 136, 0.04);
}
.worker-calls__badge {
  flex-shrink: 0;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: rgba(0, 255, 136, 0.12);
  color: #00ff88;
  font-size: 0.6875rem;
}
.worker-calls__meta {
  flex: 1;
  color: #6ee7b7;
  opacity: 0.85;
}
.worker-calls__meta .err {
  color: #fbbf24;
}
.worker-calls__chev {
  color: #4b7c5f;
}
.worker-calls__body {
  padding: 0 0.35rem 0.65rem;
}
.block {
  margin-top: 0.45rem;
}
.block-label {
  color: #4b7c5f;
  font-size: 0.6875rem;
  letter-spacing: 0.06em;
  margin-bottom: 0.2rem;
}
.block-pre {
  margin: 0;
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
  background: #0a1210;
  border: 1px solid #1a3d2e;
  color: #d1fae5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: auto;
}
</style>
