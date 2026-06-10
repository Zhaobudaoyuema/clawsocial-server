<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidSubStepper from './DeidSubStepper.vue'
import DeidTechLogTerminal from './DeidTechLogTerminal.vue'
import DeidTechLogModal from './DeidTechLogModal.vue'
import { semanticCatLabel } from './semanticCategories'

const props = defineProps<{
  jobId: number
  mode: 'idle' | 'scanning' | 'review'
}>()

const emit = defineEmits<{
  proceedConfirm: []
}>()

const store = useDeidStore()
const logModalOpen = ref(false)
const backfillTried = ref(false)

const semanticSteps = [
  { id: 'detect', label: '指纹检测' },
  { id: 'review', label: '改写预览' },
  { id: 'apply', label: '应用预览' },
]

const subCurrent = computed(() => {
  if (props.mode === 'idle') return 'detect'
  if (props.mode === 'scanning') {
    const phase = store.scanProgress?.phase
    if (phase === 'semantic_suggest') return 'review'
    return 'detect'
  }
  return 'review'
})

const subDescriptions = computed((): Record<string, string> => {
  const d: Record<string, string> = { apply: '确认后于完成阶段一次性写入' }
  if (props.mode === 'idle') d.detect = '一次 Worker 调用：按文档分段检测语义指纹并生成改写'
  if (props.mode === 'scanning') {
    const phase = store.scanProgress?.phase
    d.detect =
      phase === 'semantic_suggest'
        ? '个别条目缺少改写，正在补生成'
        : 'Worker 逐段分析文档（与实体扫描相同分段）'
    if (phase === 'semantic_suggest') d.review = 'Worker 正在为每条指纹生成改写'
  }
  if (props.mode === 'review') d.review = '已自动生成改写，勾选需应用的条目'
  return d
})

const risks = computed(() => store.semanticRisks)
const workerOnline = computed(() => store.workerStatus.online)
const showLive = computed(() => props.mode === 'scanning' || store.semanticLoading)

const missingRewrite = computed(() =>
  risks.value.some((r) => !(r.rewritten || r.suggested_rewrite)),
)

const scanMessage = computed(() => store.scanProgress?.message || '指纹检测中…')
const scanPercent = computed(() => store.scanProgress?.percent ?? 8)
const isLive = computed(
  () => store.scanLive.streamConnected && (props.mode === 'scanning' || store.semanticLoading),
)

watch(
  () => [props.mode, props.jobId, risks.value.length, missingRewrite.value] as const,
  async ([mode, jobId, count, missing]) => {
    if (mode !== 'review' || !jobId || count === 0 || !missing) return
    if (backfillTried.value || store.semanticLoading) return
    backfillTried.value = true
    try {
      await store.semanticSuggestAll(jobId)
    } catch {
      /* store.error 已设置 */
    }
  },
  { immediate: true },
)

async function onStart() {
  backfillTried.value = false
  await store.semanticStart(props.jobId)
}

async function onSkip() {
  await store.semanticSkip(props.jobId)
  emit('proceedConfirm')
}

function toggleEnabled(riskId: string, enabled: boolean) {
  store.patchSemanticRisk(riskId, { enabled })
}

function updateRewrite(riskId: string, value: string) {
  store.patchSemanticRisk(riskId, { rewritten: value })
}

function rewriteValue(r: Record<string, unknown>) {
  return (r.rewritten as string) || (r.suggested_rewrite as string) || ''
}

function onProceed() {
  store.saveSemanticSelection()
  emit('proceedConfirm')
}
</script>

<template>
  <section class="semantic-stage deid-panel">
    <h2 class="deid-page-title">语义扫描</h2>
    <p class="deid-page-sub">检测可能暴露身份的指纹表述，自动生成改写预览（可选）</p>

    <DeidSubStepper
      :steps="semanticSteps"
      :current="subCurrent"
      :busy="showLive"
      :descriptions="subDescriptions"
    />

    <div v-if="mode === 'idle'" class="idle-actions">
      <button
        type="button"
        class="deid-btn deid-btn--primary deid-btn--lg"
        :disabled="!workerOnline || store.semanticLoading"
        @click="onStart"
      >
        {{ store.semanticLoading ? '启动中…' : '开始语义扫描' }}
      </button>
      <button type="button" class="deid-btn deid-btn--lg" @click="onSkip">
        跳过，直接确认
      </button>
      <p v-if="!workerOnline" class="offline-hint">Worker 离线，请跳过语义扫描</p>
    </div>

    <div v-else-if="showLive" class="semantic-live deid-panel">
      <div class="semantic-live__head">
        <div class="semantic-live__title-row">
          <span class="deid-spinner semantic-live__spin" aria-hidden="true" />
          <span class="semantic-live__label">{{ scanMessage }}</span>
          <span class="semantic-live__pct">{{ scanPercent }}%</span>
        </div>
        <div class="semantic-live__track">
          <div class="semantic-live__bar" :style="{ width: `${scanPercent}%` }" />
        </div>
        <div class="semantic-live__meta">
          <span v-if="isLive" class="semantic-live__dot">实时</span>
          <span v-if="store.scanLive.metrics?.model">{{ store.scanLive.metrics.model }}</span>
        </div>
      </div>
      <div class="semantic-live__tech">
        <div class="semantic-live__tech-label">
          <span class="semantic-live__tech-icon" aria-hidden="true">▸</span>
          TECH_LOG
        </div>
        <DeidTechLogTerminal
          mode="compact"
          log-title="deid-semantic.log"
          stream-prompt="root@deid-worker:~$ semantic --stream"
          :logs="store.scanLive.logs"
          :stream-tail="store.scanLive.streamTail"
          :live="isLive"
          @click="logModalOpen = true"
        />
      </div>
      <DeidTechLogModal
        v-model:open="logModalOpen"
        :logs="store.scanLive.logs"
        :stream-tail="store.scanLive.streamTail"
        :live="isLive"
      />
    </div>

    <div v-else class="review">
      <p v-if="!risks.length" class="empty">未发现需改写的语义指纹，可直接进入确认。</p>
      <p v-else-if="missingRewrite && store.semanticLoading" class="empty">正在批量生成改写，请稍候…</p>
      <p v-else-if="missingRewrite" class="empty warn">部分条目未能自动生成改写，可直接取消勾选或手动编辑。</p>
      <table v-if="risks.length" class="table">
        <thead>
          <tr>
            <th>启用</th>
            <th>类别</th>
            <th>写回</th>
            <th>原文</th>
            <th>改写</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in risks"
            :key="r.risk_id as string"
            :class="{ 'row-warn': r.writable === false }"
          >
            <td>
              <input
                type="checkbox"
                :checked="r.enabled !== false"
                @change="toggleEnabled(r.risk_id as string, ($event.target as HTMLInputElement).checked)"
              />
            </td>
            <td class="cat">{{ semanticCatLabel(r.category) }}</td>
            <td class="writable">
              <span v-if="r.writable === false" class="warn-badge" title="跨段或无法在单段内写回">不可写回</span>
              <span v-else-if="r.writable" class="ok-badge">可写回</span>
              <span v-else class="muted-badge">—</span>
            </td>
            <td class="orig deid-mono">{{ r.original }}</td>
            <td>
              <textarea
                class="deid-input rewrite"
                rows="2"
                :value="rewriteValue(r as Record<string, unknown>)"
                placeholder="自动生成改写…"
                @input="updateRewrite(r.risk_id as string, ($event.target as HTMLInputElement).value)"
              />
            </td>
          </tr>
        </tbody>
      </table>
      <footer class="foot">
        <button type="button" class="deid-btn deid-btn--primary" @click="onProceed">
          下一步：确认
        </button>
      </footer>
    </div>
  </section>
</template>

<style scoped>
.semantic-stage {
  margin-top: 1rem;
  padding: 1.25rem 1.5rem !important;
}
.idle-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  margin-top: 1rem;
}
.offline-hint {
  width: 100%;
  margin: 0;
  font-size: 0.875rem;
  color: var(--deid-danger);
}
.semantic-live {
  margin-top: 1rem;
  padding: 1rem 1.15rem !important;
  background: var(--deid-surface-2);
  border-color: color-mix(in srgb, var(--deid-primary) 30%, var(--deid-border));
}
.semantic-live__head {
  margin-bottom: 0.75rem;
}
.semantic-live__title-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0.55rem;
  font-size: 0.9375rem;
}
.semantic-live__spin {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}
.semantic-live__label {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  color: var(--deid-ink);
}
.semantic-live__pct {
  font-weight: 600;
  color: var(--deid-primary);
  font-variant-numeric: tabular-nums;
}
.semantic-live__track {
  height: 6px;
  border-radius: 999px;
  background: var(--deid-border);
  overflow: hidden;
}
.semantic-live__bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--deid-primary), var(--deid-primary-hover));
  transition: width 0.35s ease;
}
.semantic-live__meta {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.45rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.semantic-live__dot {
  color: var(--deid-success, #059669);
  font-weight: 500;
}
.semantic-live__dot::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 0.35rem;
  border-radius: 50%;
  background: currentColor;
  animation: sem-pulse 1.2s ease-in-out infinite;
}
@keyframes sem-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
.semantic-live__tech-label {
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
.semantic-live__tech-icon {
  color: #00ff88;
  animation: sem-pulse 1.2s ease-in-out infinite;
}
.empty {
  margin: 1rem 0;
  color: var(--deid-ink-muted);
}
.empty.warn {
  color: var(--deid-warning, #b45309);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  margin-top: 0.5rem;
}
.table th,
.table td {
  border-bottom: 1px solid var(--deid-border);
  padding: 0.5rem 0.35rem;
  text-align: left;
  vertical-align: top;
}
.cat {
  white-space: nowrap;
  color: var(--deid-ink-muted);
}
.writable {
  white-space: nowrap;
}
.ok-badge {
  font-size: 0.75rem;
  color: #166534;
}
.warn-badge {
  font-size: 0.75rem;
  color: var(--deid-warning, #b45309);
}
.muted-badge {
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
}
.row-warn {
  background: rgba(180, 83, 9, 0.06);
}
.orig {
  max-width: 14rem;
  word-break: break-all;
}
.rewrite {
  width: 100%;
  min-width: 10rem;
  font-size: 0.8125rem;
}
.foot {
  margin-top: 1rem;
  display: flex;
  justify-content: flex-end;
}
</style>
