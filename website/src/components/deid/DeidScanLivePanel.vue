<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'

export type ScanLiveStats = {
  paragraphs?: number
  chars?: number
  chunks?: number
  tables?: number
}

export type ScanLiveMetrics = {
  elapsed_ms?: number
  prompt_tokens?: number
  completion_tokens?: number
  model?: string | null
}

const props = defineProps<{
  percent: number
  message: string
  phase?: string
  queuePosition?: number | null
  stats?: ScanLiveStats | null
  metrics?: ScanLiveMetrics | null
  logs: string[]
  streamTail?: string
  entitiesFound: number
  streamConnected?: boolean
  startedAt?: number | null
}>()

const logRef = ref<HTMLElement | null>(null)
const showTechLog = ref(false)
const localStarted = ref<number | null>(null)
const tick = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const PHASE_ORDER = ['starting', 'queued', 'extract', 'remembered', 'llm', 'merge', 'done'] as const
const MIN_PHASE_MS = 480
const displayPhaseIdx = ref(0)
let phaseAdvanceTimer: ReturnType<typeof setTimeout> | null = null

function phaseToIdx(phase: string | undefined): number {
  const idx = PHASE_ORDER.indexOf((phase || 'starting') as (typeof PHASE_ORDER)[number])
  return idx >= 0 ? idx : 0
}

function schedulePhaseAdvance(targetIdx: number) {
  if (phaseAdvanceTimer) {
    clearTimeout(phaseAdvanceTimer)
    phaseAdvanceTimer = null
  }
  const step = () => {
    if (displayPhaseIdx.value < targetIdx) {
      displayPhaseIdx.value += 1
      phaseAdvanceTimer = setTimeout(step, MIN_PHASE_MS)
    } else {
      displayPhaseIdx.value = targetIdx
    }
  }
  step()
}

watch(
  () => props.phase,
  (phase) => {
    if (phase === 'starting' && displayPhaseIdx.value > 0) {
      displayPhaseIdx.value = 0
    }
    schedulePhaseAdvance(phaseToIdx(phase))
    if (phase && phase !== 'done' && phase !== 'error' && localStarted.value == null) {
      localStarted.value = Date.now()
    }
    if (phase === 'done' || phase === 'error') {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  },
  { immediate: true },
)

watch(
  () => props.startedAt,
  (start) => {
    if (start) {
      displayPhaseIdx.value = 0
      schedulePhaseAdvance(phaseToIdx(props.phase))
    }
  },
)

watch(
  () => [props.logs.length, props.streamTail],
  async () => {
    await nextTick()
    const el = logRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

if (typeof window !== 'undefined') {
  timer = setInterval(() => {
    tick.value++
  }, 1000)
}

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (phaseAdvanceTimer) clearTimeout(phaseAdvanceTimer)
})

const elapsedLabel = computed(() => {
  tick.value
  const ms = props.metrics?.elapsed_ms
  if (ms && (props.phase === 'done' || props.percent >= 100)) {
    return formatDuration(ms)
  }
  const start = props.startedAt ?? localStarted.value
  if (!start) return '0:00'
  return formatDuration(Date.now() - start)
})

const totalTokens = computed(() => {
  const p = props.metrics?.prompt_tokens ?? 0
  const c = props.metrics?.completion_tokens ?? 0
  return p + c
})

const hasTechLog = computed(() => props.logs.length > 0 || !!props.streamTail)

const showDisconnectBanner = computed(() => {
  const phase = props.phase || ''
  if (props.streamConnected) return false
  if (props.percent >= 100) return false
  if (phase === 'done' || phase === 'error' || phase === 'queued') return false
  return true
})

const phaseSteps = computed(() => {
  const currentIdx = displayPhaseIdx.value
  const doneAll = props.phase === 'done' || props.percent >= 100

  const defs = [
    { id: 'submit', label: '提交', until: phaseToIdx('extract') },
    { id: 'extract', label: '解析文档', until: phaseToIdx('remembered') },
    { id: 'remembered', label: '词库', until: phaseToIdx('llm') },
    { id: 'llm', label: 'AI 识别', until: phaseToIdx('merge') },
    { id: 'merge', label: '合并', until: phaseToIdx('done') },
  ]

  return defs.map((step, i) => {
    const startIdx = i === 0 ? 0 : defs[i - 1].until
    const done = doneAll || currentIdx >= step.until
    const active = !doneAll && currentIdx >= startIdx && currentIdx < step.until
    return { id: step.id, label: step.label, done, active }
  })
})

function formatDuration(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatNum(n?: number) {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN')
}
</script>

<template>
  <div class="scan-live" role="status" aria-live="polite">
    <div class="scan-live__head">
      <div class="scan-live__title-row">
        <span class="scan-live__label">{{ message }}</span>
        <span class="scan-live__pct">{{ percent }}%</span>
      </div>
      <div class="scan-live__track">
        <div class="scan-live__bar" :style="{ width: `${percent}%` }" />
      </div>
      <div class="scan-live__meta">
        <span>已用时 {{ elapsedLabel }}</span>
        <span v-if="streamConnected" class="scan-live__live-dot">实时</span>
        <span v-if="entitiesFound > 0">已发现 {{ entitiesFound }} 个实体</span>
      </div>
    </div>

    <p v-if="showDisconnectBanner" class="scan-live__disconnect" role="status">
      实时连接中断，扫描仍在后台进行，请稍候…
    </p>

    <div class="scan-live__steps">
      <span
        v-for="step in phaseSteps"
        :key="step.id"
        class="scan-live__step"
        :class="{ 'scan-live__step--done': step.done, 'scan-live__step--active': step.active }"
      >
        {{ step.label }}
      </span>
    </div>

    <div v-if="stats?.paragraphs || stats?.chars" class="scan-live__stats">
      <span v-if="stats?.paragraphs">段落 {{ formatNum(stats.paragraphs) }}</span>
      <span v-if="stats?.chars">字数 {{ formatNum(stats.chars) }}</span>
      <span v-if="stats?.chunks && stats.chunks > 1">分段 {{ stats.chunks }}</span>
      <span v-if="metrics?.model">{{ metrics.model }}</span>
      <span v-if="totalTokens > 0">Token {{ formatNum(totalTokens) }}</span>
      <span v-if="metrics?.prompt_tokens">↑{{ formatNum(metrics.prompt_tokens) }}</span>
      <span v-if="metrics?.completion_tokens">↓{{ formatNum(metrics.completion_tokens) }}</span>
    </div>

    <p v-if="phase === 'queued' && queuePosition && queuePosition > 0" class="scan-live__hint">
      扫描服务繁忙，排队第 {{ queuePosition }} 位…
    </p>

    <button
      v-if="hasTechLog"
      type="button"
      class="scan-live__tech-toggle"
      @click="showTechLog = !showTechLog"
    >
      {{ showTechLog ? '隐藏技术日志' : '显示技术日志' }}
    </button>

    <div v-if="showTechLog" ref="logRef" class="scan-live__log">
      <p v-if="logs.length === 0 && !streamTail" class="scan-live__log-empty">等待扫描日志…</p>
      <div v-for="(line, i) in logs" :key="i" class="scan-live__log-line">{{ line }}</div>
      <div v-if="streamTail" class="scan-live__log-stream">{{ streamTail }}</div>
    </div>
  </div>
</template>

<style scoped>
.scan-live {
  padding: 1.25rem 1.35rem;
  border-radius: var(--deid-radius);
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
}
.scan-live__head {
  margin-bottom: 0.85rem;
}
.scan-live__title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.65rem;
  font-size: 1rem;
}
.scan-live__label {
  color: var(--deid-ink);
  font-weight: 500;
}
.scan-live__pct {
  color: var(--deid-primary);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.scan-live__track {
  height: 8px;
  border-radius: 999px;
  background: var(--deid-border);
  overflow: hidden;
}
.scan-live__bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--deid-primary), var(--deid-primary-hover));
  transition: width 0.35s ease;
}
.scan-live__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 1rem;
  margin-top: 0.55rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  font-variant-numeric: tabular-nums;
}
.scan-live__live-dot {
  color: var(--deid-success, #059669);
  font-weight: 500;
}
.scan-live__live-dot::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 0.35rem;
  border-radius: 50%;
  background: currentColor;
  animation: scan-pulse 1.2s ease-in-out infinite;
}
@keyframes scan-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
.scan-live__steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
}
.scan-live__step {
  font-size: 0.75rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--deid-surface);
  color: var(--deid-ink-muted);
  border: 1px solid var(--deid-border);
}
.scan-live__step--active {
  color: var(--deid-primary);
  border-color: var(--deid-primary);
  background: color-mix(in srgb, var(--deid-primary) 8%, transparent);
}
.scan-live__step--done {
  color: var(--deid-ink);
  border-color: var(--deid-success-border, #86efac);
  background: var(--deid-success-bg, #ecfdf5);
}
.scan-live__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
  color: var(--deid-ink-muted);
  font-variant-numeric: tabular-nums;
}
.scan-live__hint {
  margin: 0 0 0.65rem;
  font-size: 0.9375rem;
  color: var(--deid-ink-muted);
}
.scan-live__tech-toggle {
  display: inline-flex;
  margin-bottom: 0.65rem;
  padding: 0.35rem 0.65rem;
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-sm);
  background: var(--deid-surface);
  color: var(--deid-ink-secondary);
  font-size: 0.8125rem;
  font-family: inherit;
  cursor: pointer;
}
.scan-live__tech-toggle:hover {
  border-color: var(--deid-border-strong);
  color: var(--deid-ink);
}
.scan-live__disconnect {
  margin: 0 0 0.75rem;
  padding: 0.55rem 0.75rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-warning-bg);
  border: 1px solid var(--deid-warning-border);
  color: var(--deid-warning);
  font-size: 0.875rem;
  line-height: 1.45;
}
.scan-live__log {
  max-height: 240px;
  overflow-y: auto;
  padding: 0.65rem 0.75rem;
  border-radius: calc(var(--deid-radius) - 2px);
  background: var(--deid-scan-log-bg, #f8fafc);
  border: 1px solid var(--deid-border);
  font-family: ui-monospace, 'Cascadia Code', 'Segoe UI Mono', monospace;
  font-size: 0.75rem;
  line-height: 1.45;
}
.scan-live__log-empty {
  margin: 0;
  color: var(--deid-ink-muted);
  font-style: italic;
}
.scan-live__log-line {
  color: var(--deid-scan-log-fg, #475569);
  white-space: pre-wrap;
  word-break: break-word;
}
.scan-live__log-stream {
  color: var(--deid-scan-log-fg, #64748b);
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 0.25rem;
  opacity: 0.9;
}
</style>
