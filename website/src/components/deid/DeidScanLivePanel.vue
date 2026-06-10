<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import DeidTechLogTerminal from './DeidTechLogTerminal.vue'
import DeidTechLogModal from './DeidTechLogModal.vue'

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
  /** initial=初次扫描；rescan=核对阶段再识别 */
  variant?: 'initial' | 'rescan'
  reRunIndex?: number
}>()

const logModalOpen = ref(false)
const localStarted = ref<number | null>(null)
const tick = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const isRescan = computed(() => props.variant === 'rescan')

const rescanActive = computed(
  () => isRescan.value && props.phase !== 'done' && props.phase !== 'error',
)

const rescanDone = computed(
  () => isRescan.value && (props.phase === 'done' || props.phase === 'error'),
)

const chunkProgress = computed(() => {
  const m = props.message.match(/(\d+)\s*\/\s*(\d+)/)
  if (!m) return null
  const current = Number(m[1])
  const total = Number(m[2])
  if (!total || current < 0) return null
  return { current, total, pct: Math.min(100, Math.round((current / total) * 100)) }
})

const displayLabel = computed(() => {
  const msg = props.message || ''
  if (isRescan.value) {
    if (msg.includes('初次识别')) {
      if (rescanActive.value) {
        return `第 ${props.reRunIndex || 1} 次再识别中…`
      }
      if (rescanDone.value) {
        return `第 ${props.reRunIndex || 1} 次再识别完成`
      }
    }
    if (rescanDone.value) return msg || `第 ${props.reRunIndex || 1} 次再识别完成`
    return msg || `第 ${props.reRunIndex || 1} 次再识别中…`
  }
  return msg
})

const PHASE_ORDER = ['starting', 'queued', 'extract', 'remembered', 'initial_discover', 're_discover', 'merge', 'done'] as const
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
    if (isRescan.value) {
      if (phase === 'done' || props.percent >= 100) {
        displayPhaseIdx.value = phaseToIdx('done')
      } else {
        displayPhaseIdx.value = phaseToIdx('re_discover')
      }
      if (phase && phase !== 'done' && phase !== 'error' && localStarted.value == null) {
        localStarted.value = Date.now()
      }
      if (phase === 'done' || phase === 'error') {
        if (timer) {
          clearInterval(timer)
          timer = null
        }
      }
      return
    }
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
    if (logModalOpen.value) await nextTick()
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

const isLive = computed(
  () => props.streamConnected && props.phase !== 'done' && props.phase !== 'error',
)

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

  if (isRescan.value) {
    const active = !doneAll
    return [
      { id: 'rescan', label: 'AI 再识别', done: doneAll, active },
      { id: 'merge', label: '合并结果', done: doneAll, active: false },
    ]
  }

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
  <div class="scan-live" :class="{ 'scan-live--rescan': isRescan, 'scan-live--rescan-active': rescanActive }" role="status" aria-live="polite">
    <div v-if="isRescan" class="scan-live__rescan-badge">
      <span v-if="rescanActive" class="scan-live__rescan-spin deid-spinner" aria-hidden="true" />
      <span class="scan-live__rescan-tag">RE-SCAN #{{ reRunIndex || 1 }}</span>
    </div>
    <div class="scan-live__head">
      <div class="scan-live__title-row">
        <span class="scan-live__label">{{ displayLabel }}</span>
        <span class="scan-live__pct" :class="{ 'scan-live__pct--active': rescanActive }">
          <span v-if="rescanActive" class="scan-live__pct-spin deid-spinner" aria-hidden="true" />
          {{ percent }}%
        </span>
      </div>
      <div class="scan-live__track" :class="{ 'scan-live__track--pulse': rescanActive }">
        <div class="scan-live__bar" :style="{ width: `${percent}%` }" />
      </div>
      <div v-if="chunkProgress && rescanActive" class="scan-live__chunk">
        <div class="scan-live__chunk-label">
          <span>文档分段</span>
          <span>{{ chunkProgress.current }} / {{ chunkProgress.total }}</span>
        </div>
        <div class="scan-live__chunk-track">
          <div class="scan-live__chunk-bar" :style="{ width: `${chunkProgress.pct}%` }" />
        </div>
      </div>
      <div class="scan-live__meta">
        <span>已用时 {{ elapsedLabel }}</span>
        <span v-if="streamConnected" class="scan-live__live-dot">实时</span>
        <span v-if="entitiesFound > 0">{{ isRescan ? '本轮新增' : '已发现' }} {{ entitiesFound }} 个实体</span>
      </div>
    </div>

    <p v-if="showDisconnectBanner" class="scan-live__disconnect" role="status">
      实时连接中断，扫描仍在后台进行，请稍候…
    </p>

    <div v-if="!isRescan || rescanDone" class="scan-live__steps">
      <span
        v-for="step in phaseSteps"
        :key="step.id"
        class="scan-live__step"
        :class="{ 'scan-live__step--done': step.done, 'scan-live__step--active': step.active }"
      >
        {{ step.label }}
      </span>
    </div>

    <div v-if="(!isRescan || rescanDone) && (stats?.paragraphs || stats?.chars)" class="scan-live__stats">
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

    <div class="scan-live__tech">
      <div class="scan-live__tech-label">
        <span class="scan-live__tech-icon" aria-hidden="true">▸</span>
        TECH_LOG
      </div>
      <DeidTechLogTerminal
        mode="compact"
        :logs="logs"
        :stream-tail="streamTail"
        :live="isLive"
        @click="logModalOpen = true"
      />
    </div>

    <DeidTechLogModal
      v-model:open="logModalOpen"
      :logs="logs"
      :stream-tail="streamTail"
      :live="isLive"
    />
  </div>
</template>

<style scoped>
.scan-live {
  padding: 1.25rem 1.35rem;
  border-radius: var(--deid-radius);
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
}
.scan-live--rescan {
  padding: 0.85rem 1rem;
  background: color-mix(in srgb, var(--deid-primary) 4%, var(--deid-surface-2));
  border-color: color-mix(in srgb, var(--deid-primary) 25%, var(--deid-border));
}
.scan-live--rescan-active {
  border-color: color-mix(in srgb, var(--deid-primary) 55%, var(--deid-border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--deid-primary) 12%, transparent);
}
.scan-live__rescan-badge {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin-bottom: 0.55rem;
}
.scan-live__rescan-spin {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
}
.scan-live__rescan-tag {
  font-family: var(--deid-font-mono, Consolas, monospace);
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--deid-primary);
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  background: var(--deid-primary-soft);
  border: 1px solid color-mix(in srgb, var(--deid-primary) 35%, transparent);
}
.scan-live__pct {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--deid-primary);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.scan-live__pct--active {
  color: var(--deid-primary);
}
.scan-live__pct-spin {
  width: 0.875rem;
  height: 0.875rem;
}
.scan-live__track--pulse .scan-live__bar {
  background: linear-gradient(
    90deg,
    var(--deid-primary),
    color-mix(in srgb, var(--deid-primary) 70%, #fff),
    var(--deid-primary-hover)
  );
  background-size: 200% 100%;
  animation: scan-bar-shimmer 1.6s ease-in-out infinite;
}
@keyframes scan-bar-shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}
.scan-live__chunk {
  margin-top: 0.55rem;
}
.scan-live__chunk-label {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.3rem;
  font-size: 0.6875rem;
  color: var(--deid-ink-muted);
  font-variant-numeric: tabular-nums;
}
.scan-live__chunk-track {
  height: 4px;
  border-radius: 999px;
  background: var(--deid-border);
  overflow: hidden;
}
.scan-live__chunk-bar {
  height: 100%;
  border-radius: 999px;
  background: color-mix(in srgb, var(--deid-preset) 80%, var(--deid-primary));
  transition: width 0.35s ease;
}
.scan-live--rescan .term--compact .term__body {
  max-height: 96px;
}
.scan-live__tech {
  margin-top: 0.15rem;
}
.scan-live__tech-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.45rem;
  font-family: var(--deid-font-mono, Consolas, monospace);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: #3d6b52;
}
.scan-live__tech-icon {
  color: #00ff88;
  animation: scan-pulse 1.2s ease-in-out infinite;
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
</style>
