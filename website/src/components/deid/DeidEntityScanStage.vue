<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidStepper from './DeidStepper.vue'
import DeidSubStepper from './DeidSubStepper.vue'
import DeidScanLivePanel from './DeidScanLivePanel.vue'
import DeidEntityList from './DeidEntityList.vue'
import DeidExperienceDrawer from './DeidExperienceDrawer.vue'
import DeidEntityTypeSelect from './DeidEntityTypeSelect.vue'

const props = defineProps<{
  jobId: number
  filename: string
  mode: 'scanning' | 'ready' | 're_scanning'
}>()

const emit = defineEmits<{ proceedSemantic: [] }>()

const store = useDeidStore()
const experiencePhase = ref<'loading' | 'edit' | 'saving' | null>(null)
const experienceText = ref('')
const actionBusy = ref(false)
const noChangeHint = ref(false)
const manualName = ref('')
const manualType = ref('company')
const addingManual = ref(false)
const showManual = ref(false)

const innerSteps = [
  { id: 'initial', label: '初次识别' },
  { id: 'review', label: '核对和再识别' },
]

const currentInnerStep = computed(() => {
  if (props.mode === 'scanning') return 'initial'
  return 'review'
})

const isLoading = computed(() => props.mode === 'scanning' || props.mode === 're_scanning')

const showLivePanel = computed(() => {
  const sp = store.scanProgress
  if (!sp) return false
  if (props.mode === 'scanning') return isLoading.value || sp.phase === 'done'
  return false
})

const showRescanPanel = computed(() => {
  if (store.scanSession === 'rescan') return true
  if (props.mode === 're_scanning') return true
  if (actionBusy.value) return true
  const sp = store.scanProgress
  if (!sp) return false
  if (sp.phase === 're_discover') return true
  if (sp.phase === 'done' && !String(sp.message || '').includes('初次识别')) return true
  if (sp.phase === 'error' && String(sp.message || '').includes('再识别')) return true
  return false
})

const rescanBusy = computed(
  () => props.mode === 're_scanning' || actionBusy.value || store.reScanning,
)

const rescanRunIndex = computed(() => {
  const fromMsg = store.scanProgress?.message?.match(/第\s*(\d+)\s*次/)
  if (fromMsg) return Number(fromMsg[1])
  if (store.lastRescanResult?.run) return store.lastRescanResult.run
  return Number(job.value?.re_run_count ?? 0) + (rescanBusy.value ? 1 : 0)
})

const rescanPanelMessage = computed(() => {
  const sp = store.scanProgress
  const msg = sp?.message || ''
  if (msg && !msg.includes('初次识别')) return msg
  if (rescanBusy.value) return `第 ${rescanRunIndex.value} 次再识别中…`
  if (store.lastRescanResult) {
    const { run, delta, noChange } = store.lastRescanResult
    return noChange ? `第 ${run} 次再识别完成，本轮无新增` : `第 ${run} 次再识别完成，新增 ${delta} 个`
  }
  return `第 ${rescanRunIndex.value} 次再识别中…`
})

const rescanPanelPhase = computed(() => {
  const sp = store.scanProgress
  if (sp?.phase) return sp.phase
  if (store.lastRescanResult && !rescanBusy.value) return 'done'
  return 're_discover'
})

const rescanPanelPercent = computed(() => {
  const sp = store.scanProgress
  const msg = sp?.message || ''
  if (msg.includes('初次识别')) {
    if (rescanBusy.value) return Math.max(5, Math.min(sp?.percent ?? 8, 95))
    if (store.lastRescanResult) return 100
    return 8
  }
  if (sp?.percent != null) return sp.percent
  if (rescanBusy.value) return 8
  if (store.lastRescanResult) return 100
  return 0
})
const job = computed(() => store.currentJob as Record<string, unknown> | null)
const deltaCount = computed(() => Number(job.value?.delta_vs_initial_count ?? 0))
const experienceEligible = computed(() => !!job.value?.experience_eligible)
const experienceBusy = computed(
  () => experiencePhase.value === 'loading' || experiencePhase.value === 'saving',
)

const sourceStats = computed(() => {
  const counts = { llm: 0, remembered: 0, manual: 0 }
  for (const e of store.entities) {
    const src = (e as { source: string }).source
    if (src === 'llm') counts.llm++
    else if (src === 'remembered') counts.remembered++
    else if (src === 'manual') counts.manual++
  }
  return counts
})

const summaryLine = computed(() => {
  const total = store.entities.length
  const { llm, remembered, manual } = sourceStats.value
  const parts = [`共 ${total} 个`, `AI ${llm}`, `词库 ${remembered}`]
  if (manual > 0) parts.push(`手动 ${manual}`)
  if (deltaCount.value > 0) parts.push(`+${deltaCount.value} 相对初次`)
  return parts.join(' · ')
})

const statusTitle = computed(() => {
  if (props.mode === 'scanning') return '正在初次识别实体…'
  if (rescanBusy.value) return `正在第 ${rescanRunIndex.value} 次再识别…`
  if (store.lastRescanResult) {
    const { run, delta, noChange } = store.lastRescanResult
    return noChange ? `第 ${run} 次再识别完成` : `第 ${run} 次再识别完成，新增 ${delta} 个实体`
  }
  const rerunCount = Number(job.value?.re_run_count ?? 0)
  if (rerunCount > 0) {
    if (deltaCount.value > 0) {
      return `已完成 ${rerunCount} 次再识别，累计新增 ${deltaCount.value} 个实体`
    }
    return `已完成 ${rerunCount} 次再识别，请核对实体列表`
  }
  return '初次识别完成，请核对实体列表'
})

const statusSub = computed(() => {
  if (rescanBusy.value) return store.scanProgress?.message || 'Worker 正在核对文档并补充遗漏实体…'
  if (store.lastRescanResult?.noChange) return '本轮未发现新实体，可继续再识别或进入下一步'
  if (store.lastRescanResult && store.lastRescanResult.delta > 0) {
    return `本轮再识别新增 ${store.lastRescanResult.delta} 个，列表中已标「新增」`
  }
  if (noChangeHint.value) return '本轮未发现新实体，可继续再识别或进入下一步'
  if (deltaCount.value > 0) return `相对初次累计新增 ${deltaCount.value} 个实体`
  return '误报可删除，遗漏可手动添加或点「再识别」'
})

async function onDeleteEntity(id: number) {
  await store.deleteEntity(props.jobId, id)
  const j = await store.fetchJobSnapshot(props.jobId)
  store.currentJob = j
}

async function onAddManual() {
  if (!manualName.value.trim()) return
  addingManual.value = true
  try {
    await store.addManual(props.jobId, {
      canonical_name: manualName.value.trim(),
      entity_type: manualType.value,
      aliases: [manualName.value.trim()],
      save_to_library: true,
    })
    manualName.value = ''
    showManual.value = false
    const j = await store.fetchJobSnapshot(props.jobId)
    store.currentJob = j
  } finally {
    addingManual.value = false
  }
}

async function onReRun() {
  actionBusy.value = true
  noChangeHint.value = false
  store.lastRescanResult = null
  try {
    const data = await store.reRunScan(props.jobId)
    if (data.no_change) noChangeHint.value = true
    await store.loadEntitiesSnapshot(props.jobId)
    const j = await store.fetchJobSnapshot(props.jobId)
    store.currentJob = j
  } finally {
    actionBusy.value = false
  }
}

async function onExperienceExtract() {
  experiencePhase.value = 'loading'
  try {
    const data = await store.generateExperience(props.jobId)
    experienceText.value = (data.text as string) || ''
    experiencePhase.value = 'edit'
  } catch {
    experiencePhase.value = null
  }
}

async function onExperienceConfirm(text: string) {
  experiencePhase.value = 'saving'
  try {
    await store.confirmExperience(props.jobId, text)
    experiencePhase.value = null
    const j = await store.fetchJobSnapshot(props.jobId)
    store.currentJob = j
  } catch {
    experiencePhase.value = 'edit'
  }
}

function onExperienceClose() {
  if (experiencePhase.value === 'loading' || experiencePhase.value === 'saving') return
  experiencePhase.value = null
}

function onProceedSemantic() {
  store.enterSemanticStage()
  emit('proceedSemantic')
}
</script>

<template>
  <div class="entity-scan-stage">
    <header class="stage-header deid-panel" :class="{
      loading: isLoading || rescanBusy,
      hint: (noChangeHint || store.lastRescanResult?.noChange) && !rescanBusy && !isLoading,
      'rescan-done': store.lastRescanResult && !rescanBusy && !showRescanPanel,
    }">
      <DeidStepper embedded :current="store.wizardStep()" />

      <div class="file-row">
        <span class="file-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linejoin="round"
            />
            <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </span>
        <h2 class="file-name" :title="filename">{{ filename }}</h2>
      </div>

      <DeidSubStepper :steps="innerSteps" :current="currentInnerStep" :busy="rescanBusy" />

      <div v-if="!showLivePanel && !showRescanPanel" class="status-block">
        <p class="status-title">{{ statusTitle }}</p>
        <p class="status-sub">{{ statusSub }}</p>
        <p v-if="store.entities.length" class="summary-line">{{ summaryLine }}</p>
      </div>

      <DeidScanLivePanel
        v-if="showRescanPanel"
        variant="rescan"
        :re-run-index="rescanRunIndex"
        :percent="rescanPanelPercent"
        :message="rescanPanelMessage"
        :phase="rescanPanelPhase"
        :stats="rescanBusy ? null : store.scanLive.stats || store.scanProgress?.stats"
        :metrics="store.scanLive.metrics || store.scanProgress?.metrics"
        :logs="store.scanLive.logs"
        :stream-tail="store.scanLive.streamTail"
        :entities-found="store.scanLive.entitiesFound"
        :stream-connected="store.scanLive.streamConnected"
        :started-at="store.scanLive.startedAt"
        class="header-live"
      />
    </header>

    <div v-if="showLivePanel && mode === 'scanning'" class="progress-panel deid-panel">
      <DeidScanLivePanel
        variant="initial"
        :percent="store.scanProgress!.percent"
        :message="store.scanProgress!.message"
        :phase="store.scanProgress!.phase"
        :queue-position="store.scanProgress!.queue_position"
        :stats="store.scanLive.stats || store.scanProgress!.stats"
        :metrics="store.scanLive.metrics || store.scanProgress!.metrics"
        :logs="store.scanLive.logs"
        :stream-tail="store.scanLive.streamTail"
        :entities-found="store.scanLive.entitiesFound"
        :stream-connected="store.scanLive.streamConnected"
        :started-at="store.scanLive.startedAt"
      />
    </div>

    <DeidEntityList
      v-if="!isLoading || store.entities.length"
      :entities="store.entities"
      :show-new-badge="true"
      :editable="!isLoading"
      :show-placeholder-column="false"
      filterable
      @delete="onDeleteEntity"
    />

    <div v-if="!isLoading" class="manual-add deid-panel">
      <button
        v-if="!showManual"
        type="button"
        class="deid-btn deid-btn--ghost manual-toggle"
        @click="showManual = true"
      >
        + 手动添加实体
      </button>
      <div v-else class="manual-form">
        <input v-model="manualName" class="deid-input" placeholder="实体名称" @keyup.enter="onAddManual" />
        <DeidEntityTypeSelect v-model="manualType" width="100%" />
        <div class="manual-form__btns">
          <button type="button" class="deid-btn deid-btn--ghost" @click="showManual = false">取消</button>
          <button
            type="button"
            class="deid-btn deid-btn--primary"
            :disabled="addingManual || !manualName.trim()"
            @click="onAddManual"
          >
            添加
          </button>
        </div>
      </div>
    </div>

    <footer class="action-bar">
      <button
        type="button"
        class="deid-btn"
        :disabled="isLoading || experienceBusy || actionBusy || !store.workerStatus.online"
        @click="onReRun"
      >
        {{ actionBusy ? '…' : '再识别' }}
      </button>
      <div v-if="experienceEligible" class="exp-anchor">
        <button
          type="button"
          class="deid-btn"
          :disabled="isLoading || !!experiencePhase || actionBusy"
          @click="onExperienceExtract"
        >
          <span v-if="experiencePhase === 'loading'" class="deid-spinner action-spin" aria-hidden="true" />
          {{ experiencePhase === 'loading' ? '提取中…' : '经验提取' }}
        </button>
        <DeidExperienceDrawer
          v-if="experiencePhase"
          :open="true"
          :phase="experiencePhase"
          :text="experienceText"
          @update:open="(v) => { if (!v) onExperienceClose() }"
          @confirm="onExperienceConfirm"
        />
      </div>
      <button
        type="button"
        class="deid-btn deid-btn--primary"
        :disabled="isLoading || experienceBusy || actionBusy"
        @click="onProceedSemantic"
      >
        进入语义扫描 →
      </button>
    </footer>
  </div>
</template>

<style scoped>
.entity-scan-stage {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.stage-header {
  padding: 1rem 1.25rem 1.15rem;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.stage-header.loading {
  border-color: color-mix(in srgb, var(--deid-primary) 40%, var(--deid-border));
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--deid-primary) 5%, var(--deid-surface)) 0%,
    var(--deid-surface) 100%
  );
}
.stage-header.hint {
  border-color: var(--deid-warning-border);
  background: var(--deid-warning-bg);
}
.stage-header.rescan-done {
  border-color: var(--deid-success-border);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--deid-success) 6%, var(--deid-surface)) 0%,
    var(--deid-surface) 100%
  );
}
.file-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
}
.file-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-primary-soft);
  color: var(--deid-primary);
  flex-shrink: 0;
}
.file-name {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.35;
  color: var(--deid-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-block {
  padding-top: 0.15rem;
}
.status-title {
  margin: 0 0 0.25rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.status-sub {
  margin: 0;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
  line-height: 1.45;
}
.summary-line {
  margin: 0.45rem 0 0;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--deid-ink-muted);
}
.header-live {
  margin-top: 0.15rem;
}
.manual-add {
  padding: 0.85rem 1rem;
}
.manual-toggle {
  width: 100%;
  justify-content: center;
}
.manual-form {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}
.manual-form__btns {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.75rem 0;
  position: sticky;
  bottom: 0;
  background: var(--deid-bg, #fff);
  border-top: 1px solid var(--deid-border, #e2e6ee);
}
.exp-anchor {
  position: relative;
}
.action-bar .deid-btn--primary {
  margin-left: auto;
}
.action-bar .deid-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.action-spin {
  width: 0.95rem;
  height: 0.95rem;
}
</style>
