<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidUploadCard from './DeidUploadCard.vue'
import DeidCompletionHero from './DeidCompletionHero.vue'
import DeidReplaceSamples from './DeidReplaceSamples.vue'
import DeidEntityList from './DeidEntityList.vue'
import DeidConclusionView from './DeidConclusionView.vue'
import DeidMyEntities from './DeidMyEntities.vue'
import DeidRehydrateView from './DeidRehydrateView.vue'
import DeidStepper from './DeidStepper.vue'
import DeidStepNav from './DeidStepNav.vue'
import DeidWorkerBanner from './DeidWorkerBanner.vue'
import DeidScanErrorPanel from './DeidScanErrorPanel.vue'
import DeidModal from './DeidModal.vue'
import DeidEntityScanStage from './DeidEntityScanStage.vue'
import DeidSemanticScanStage from './DeidSemanticScanStage.vue'

const store = useDeidStore()

const selectedFile = ref<File | null>(null)
const uploadError = ref<string | null>(null)
const useWorker = ref(true)
const overrideReason = ref('')
const manualName = ref('')
const jobsToastDismissed = ref(false)
const showOverrideModal = ref(false)
const modalOverrideAck = ref(false)

const job = computed(() => store.currentJob)
const jobId = computed(() => (job.value as { id?: number } | null)?.id)
const status = computed(() => (job.value as { status?: string } | null)?.status || 'idle')
const workerOnline = computed(() => store.workerStatus.online)
const isScanning = computed(
  () =>
    status.value === 'scanning' ||
    status.value === 'queued' ||
    status.value === 're_scanning' ||
    store.reScanning ||
    (!!store.scanProgress && store.scanProgress.phase !== 'error' && store.scanProgress.phase !== 'done'),
)
const isDone = computed(() => status.value === 'done' || status.value === 'archived')
const filesPurged = computed(
  () =>
    status.value === 'archived' ||
    !!(job.value as { files_purged_at?: string | null } | null)?.files_purged_at,
)
const canDownload = computed(() => isDone.value && !filesPurged.value)

const verification = computed(
  () => ((job.value as { verification?: Record<string, unknown> })?.verification) || {},
)
const verificationPassed = computed(() => !!verification.value.passed)
const verificationSummary = computed(() => (verification.value.summary as string) || '')
const verificationResiduals = computed(
  () => (verification.value.residuals as string[]) || [],
)
const finishVerifyMode = computed(
  () => (verification.value.finish_verify_mode as string) || '',
)
const showFinishVerifyNote = computed(
  () => isDone.value && finishVerifyMode.value === 'program_only',
)
const semanticSummary = computed(() => {
  const sem = (verification.value.semantic as Record<string, unknown>) || {}
  const applied = Number(sem.applied_count ?? 0)
  const selected = Number(sem.selected_count ?? 0)
  const missed = Number(sem.missed_count ?? 0)
  if (job.value && (job.value as { semantic_skipped?: boolean }).semantic_skipped) {
    return '未进行语义扫描'
  }
  if (selected > 0) {
    let msg = `已应用 ${applied}/${selected} 条语义改写`
    if (missed > 0) msg += `（${missed} 条未落地）`
    return msg
  }
  return applied > 0 ? `已应用 ${applied} 条语义改写` : '未应用语义改写'
})

const readinessInfo = computed(() => {
  const rd = (verification.value.readiness as Record<string, unknown>) || {}
  return {
    ready: rd.ready as boolean | null | undefined,
    level: (rd.level as string) || 'standard',
    blockers: (rd.blockers as string[]) || [],
    notes: (rd.notes as string[]) || [],
  }
})

const semanticMissedWarning = computed(() => {
  const sem = (verification.value.semantic as Record<string, unknown>) || {}
  const missed = Number(sem.missed_count ?? 0)
  const blockers = readinessInfo.value.blockers
  if (blockers.length) return blockers[0]
  if (missed <= 0) return null
  const readiness = sem.readiness as string | undefined
  return readiness || `${missed} 条语义改写未能写入文档`
})

function onSemanticProceedConfirm() {
  store.proceedToConfirm()
}

function onEntityScanProceedSemantic() {
  /* semantic stage shown via semanticStageEntered */
}

const scanFailed = computed(
  () =>
    wizardPhase.value === 'scan-draft' &&
    !!(uploadError.value || store.error),
)

const scanErrorMessage = computed(() => uploadError.value || store.error || '扫描失败')

const currentStep = computed(() => store.wizardStep())

const wizardPhase = computed(() => store.wizardPhase())

const showWorkerBanner = computed(
  () => !workerOnline.value && !isDone.value && !store.showEntitiesPanel,
)

const showJobsError = computed(
  () => !!store.jobsError && !jobsToastDismissed.value,
)

const showWorkerToast = computed(() => {
  const phase = wizardPhase.value
  const toastPhases = ['upload', 'scan-draft', 'scanning', 'entity-scanned']
  return (
    store.workerWasOffline &&
    store.workerStatus.online &&
    !store.showConclusionView &&
    !store.showEntitiesPanel &&
    !isDone.value &&
    toastPhases.includes(phase)
  )
})

const workerToastMessage = computed(() => {
  if (wizardPhase.value === 'entity-scanned') {
    return 'Worker 已恢复，可继续再识别'
  }
  return '智能扫描已恢复，可使用 AI 发现实体'
})

const stageBodyRef = ref<HTMLElement | null>(null)

const showTopStepper = computed(() => {
  const p = wizardPhase.value
  return p !== 'scanning' && p !== 'entity-scanned'
})

watch(
  () =>
    [
      store.showConclusionView,
      store.showEntitiesPanel,
      wizardPhase.value,
      jobId.value,
    ] as const,
  () => {
    stageBodyRef.value?.scrollTo(0, 0)
  },
)


function onSelect(file: File) {
  uploadError.value = null
  if (!file.name.toLowerCase().endsWith('.docx')) {
    uploadError.value = '仅支持 .docx'
    selectedFile.value = null
    return
  }
  selectedFile.value = file
  void doUpload()
}

async function doUpload() {
  if (!selectedFile.value) return
  try {
    await store.uploadJob(selectedFile.value, { useWorker: useWorker.value })
    selectedFile.value = null
  } catch {
    uploadError.value = store.error || '上传失败'
  }
}

async function doScan() {
  if (!jobId.value) return
  uploadError.value = null
  store.beginScan(jobId.value)
  try {
    await store.startScan(jobId.value)
    await store.pollScanUntilDone(jobId.value)
  } catch {
    uploadError.value = store.error || '扫描失败'
    if (store.currentJob && (store.currentJob as { status?: string }).status === 'scanning') {
      store.currentJob = { ...store.currentJob, status: 'draft' }
    }
    store.scanProgress = null
  }
}

async function onDeleteEntity(id: number) {
  if (!jobId.value) return
  await store.deleteEntity(jobId.value, id)
}

async function addManualDone() {
  if (!jobId.value || !manualName.value.trim()) return
  await store.addManual(jobId.value, {
    canonical_name: manualName.value.trim(),
    entity_type: 'company',
    aliases: [manualName.value.trim()],
    save_to_library: true,
  })
  manualName.value = ''
}

async function doRerun() {
  if (!jobId.value) return
  const ids = store.entities
    .filter((e) => !(e as { is_excluded?: boolean }).is_excluded)
    .map((e) => (e as { id: number }).id)
  await store.rerun(jobId.value, ids, [])
}

async function retryJobs() {
  jobsToastDismissed.value = false
  await store.fetchJobs()
}

function openOverrideModal() {
  modalOverrideAck.value = false
  showOverrideModal.value = true
}

function confirmOverrideDownload() {
  if (!modalOverrideAck.value || !jobId.value) return
  const url = store.exportUrl(jobId.value, true, overrideReason.value.trim() || undefined)
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  a.click()
  showOverrideModal.value = false
}
</script>

<template>
  <main class="stage">
    <div
      ref="stageBodyRef"
      class="stage-body"
      :class="{ 'stage-body--rehydrate': store.showRehydratePanel }"
    >
    <div v-if="showWorkerToast" class="toast toast--ok">
      {{ workerToastMessage }}
      <button type="button" class="toast-x" @click="store.clearWorkerToast()">×</button>
    </div>

    <div v-if="showJobsError" class="toast toast--err">
      <span>任务列表加载失败：{{ store.jobsError }}</span>
      <div class="toast-actions">
        <button type="button" class="deid-btn deid-btn--ghost" @click="retryJobs">重试</button>
        <button type="button" class="toast-x" @click="jobsToastDismissed = true">×</button>
      </div>
    </div>
    <Transition name="deid-fade" mode="out-in">
      <!-- 结论回显 -->
      <DeidRehydrateView v-if="store.showRehydratePanel" key="rehydrate" class="panel-fill panel-fill--rehydrate" />

      <!-- 词库 -->
      <DeidMyEntities v-else-if="store.showEntitiesPanel" key="entities" class="panel-fill panel-fill--lexicon" />

      <!-- 结论全屏 -->
      <DeidConclusionView v-else-if="store.showConclusionView" key="conclusion" class="panel-fill" />

      <!-- 完成页 -->
      <div v-else-if="wizardPhase === 'done' && job" key="done" class="done-wrap wizard-panel">
        <div class="wizard-toolbar">
          <DeidStepper :current="currentStep" :finished="isDone" />
          <DeidStepNav>
          <template v-if="canDownload">
            <a
              v-if="verificationPassed && jobId"
              class="deid-btn deid-btn--primary"
              :href="store.exportUrl(jobId, false, undefined)"
              download
            >
              下载文档
            </a>
            <button
              v-else-if="jobId"
              type="button"
              class="deid-btn deid-btn--primary"
              @click="openOverrideModal"
            >
              下载文档
            </button>
          </template>
          <p v-else-if="filesPurged" class="archived-hint">文件已清理，可使用左侧「结论回显」还原外部结论</p>
          <button v-if="store.entityDirty && canDownload" type="button" class="deid-btn" @click="doRerun">
            重新脱敏
          </button>
          </DeidStepNav>
        </div>
        <DeidCompletionHero :job="job" :entities="store.entities" />
        <p v-if="showFinishVerifyNote && readinessInfo.notes.length" class="finish-verify-banner">
          {{ readinessInfo.notes[0] }}
        </p>
        <p v-if="isDone" class="readiness-banner">{{ semanticSummary }}</p>
        <p v-if="isDone && readinessInfo.level" class="readiness-banner">
          外发就绪：{{ readinessInfo.ready === true ? '通过' : readinessInfo.ready === false ? '未通过' : '待确认' }}
          （{{ readinessInfo.level }}）
        </p>
        <p v-if="isDone && semanticMissedWarning" class="readiness-banner readiness-banner--warn">
          {{ semanticMissedWarning }}
        </p>
        <DeidReplaceSamples :previews="store.previews" />
        <DeidEntityList :entities="store.entities" editable @delete="onDeleteEntity" />
        <div class="manual-add">
          <input v-model="manualName" class="deid-input" placeholder="添加实体后需重新脱敏" />
          <button type="button" class="deid-btn" @click="addManualDone">添加</button>
        </div>
      </div>

      <!-- 上传 / 扫描 -->
      <div v-else key="upload" class="upload-wrap wizard-panel">
        <div class="deid-workbench-column">
        <div v-if="showTopStepper" class="wizard-toolbar">
          <DeidStepper :current="currentStep" :finished="isDone" />
        </div>

        <DeidWorkerBanner v-if="showWorkerBanner" />

        <div v-if="wizardPhase === 'upload'" class="upload-stage">
          <div class="upload-head">
            <h2 class="deid-page-title">上传 Word 文档</h2>
            <p class="deid-page-sub">选择 .docx 文件，自动上传并开始流程</p>
          </div>
          <label v-if="workerOnline" class="worker-opt">
            <input v-model="useWorker" type="checkbox" :disabled="store.loading" />
            使用智能扫描（AI 发现更多实体）
          </label>
          <DeidUploadCard
            :disabled="store.loading || isScanning"
            :loading="store.loading"
            @select="onSelect"
          />
          <p v-if="uploadError || store.error" class="err">{{ uploadError || store.error }}</p>
        </div>

        <!-- 脱敏进行中 -->
        <div v-else-if="wizardPhase === 'finishing' && job" key="running" class="running-stage">
          <h2 class="deid-page-title">{{ (job as { original_filename: string }).original_filename }}</h2>
          <p class="deid-page-sub">正在写入脱敏文档，请稍候…</p>
          <div class="job-card deid-panel confirm-card">
            <span class="deid-spinner" aria-hidden="true" />
            <p class="confirm-text">替换敏感实体中</p>
          </div>
        </div>

        <div v-else-if="wizardPhase === 'scan-draft'" class="job-stage">
          <h2 class="deid-page-title">{{ (job as { original_filename: string }).original_filename }}</h2>
          <p class="deid-page-sub">{{ scanFailed ? '扫描遇到问题' : '确认无误后开始扫描' }}</p>

          <DeidScanErrorPanel
            v-if="scanFailed"
            class="job-card"
            :message="scanErrorMessage"
            :has-entities="store.entities.length > 0"
            @retry="doScan"
            @view-conclusion="store.openConclusionView()"
          />

          <div v-else class="job-card deid-panel">
            <div class="job-ready">
              <div class="file-icon" aria-hidden="true">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                  <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                </svg>
              </div>
              <p class="ready-text">文档已就绪，点击开始实体扫描</p>
            </div>

            <div class="cta">
              <button
                type="button"
                class="deid-btn deid-btn--primary deid-btn--lg"
                :disabled="store.loading || isScanning"
                @click="doScan"
              >
                {{ workerOnline ? '开始实体扫描' : '匹配词库实体' }}
              </button>
            </div>
          </div>
        </div>

        <div
          v-else-if="(wizardPhase === 'scanning' || wizardPhase === 'entity-scanned') && job && jobId"
          class="job-stage"
        >
          <DeidEntityScanStage
            :job-id="jobId"
            :filename="(job as { original_filename: string }).original_filename"
            :mode="store.entityScanMode()"
            @proceed-semantic="onEntityScanProceedSemantic"
          />
        </div>

        <DeidSemanticScanStage
          v-else-if="(wizardPhase === 'semantic-idle' || wizardPhase === 'semantic-scanning' || wizardPhase === 'semantic-review') && jobId"
          :job-id="jobId"
          :mode="wizardPhase === 'semantic-scanning' ? 'scanning' : wizardPhase === 'semantic-review' ? 'review' : 'idle'"
          @proceed-confirm="onSemanticProceedConfirm"
        />
        </div>
      </div>
    </Transition>

    </div>

    <DeidModal v-model:open="showOverrideModal" title="验证未通过，确认下载？" danger>
      <p v-if="verificationSummary" class="override-summary">{{ verificationSummary }}</p>
      <p v-if="verificationResiduals.length" class="override-residuals-title">
        残留明细（共 {{ verificationResiduals.length }} 处）
      </p>
      <ul v-if="verificationResiduals.length" class="override-residuals">
        <li v-for="(r, i) in verificationResiduals.slice(0, 5)" :key="i" class="deid-mono">{{ r }}</li>
        <li v-if="verificationResiduals.length > 5" class="override-more">
          另有 {{ verificationResiduals.length - 5 }} 处未列出
        </li>
      </ul>
      <label class="override-ack">
        <input v-model="modalOverrideAck" type="checkbox" />
        本人已审阅残留风险，确认下载
      </label>
      <textarea
        v-model="overrideReason"
        class="deid-textarea override-reason"
        placeholder="备注原因（可选）"
        rows="2"
      />
      <template #footer>
        <button type="button" class="deid-btn" @click="showOverrideModal = false">取消</button>
        <button
          type="button"
          class="deid-btn deid-btn--primary"
          :disabled="!modalOverrideAck"
          @click="confirmOverrideDownload"
        >
          确认下载
        </button>
      </template>
    </DeidModal>
  </main>
</template>

<style scoped>
.stage {
  flex: 1;
  min-height: calc(100vh - var(--deid-topbar-height));
  overflow-y: auto;
  background: var(--deid-bg);
}
@media (min-width: 769px) {
  .stage {
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .stage-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .stage-body > .panel-fill {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .stage-body > .panel-fill.panel-fill--lexicon {
    flex: 0 0 auto;
    min-height: auto;
    height: auto;
    overflow: visible;
    display: block;
  }
  .stage-body--rehydrate {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding: 1.5rem 2.5rem 1.75rem 3rem;
    box-sizing: border-box;
  }
  .stage-body--rehydrate > .toast {
    margin: 0 !important;
    flex-shrink: 0;
  }
  .stage-body--rehydrate > .panel-fill--rehydrate {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .wizard-panel {
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 1rem 2rem 1.25rem;
  }
  .wizard-toolbar {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 1rem 1.5rem;
    margin-bottom: 0.75rem;
  }
  .wizard-toolbar :deep(.stepper) {
    margin-bottom: 0;
  }
  .wizard-toolbar :deep(.step-nav) {
    margin-bottom: 0;
  }
  .archived-hint {
    margin: 0;
    font-size: 0.875rem;
    color: var(--deid-ink-muted);
  }
  .stage-body > .toast {
    flex-shrink: 0;
    margin: 0.75rem 2.75rem 1rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
  }
}
.toast {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin: 0 1rem 0.5rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--deid-radius-sm);
  font-size: 0.9375rem;
}
@media (min-width: 769px) {
  .stage-body > .toast {
    margin: 0.75rem 2.75rem 1rem;
  }
}
.toast--ok {
  background: var(--deid-success-bg);
  border: 1px solid var(--deid-success-border);
  color: var(--deid-success);
}
.toast--err {
  background: var(--deid-danger-bg);
  border: 1px solid var(--deid-danger-border);
  color: var(--deid-danger);
}
.toast-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}
.toast-x {
  border: none;
  background: none;
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
  color: inherit;
}
.upload-wrap,
.done-wrap {
  width: 100%;
  max-width: var(--deid-content-max);
  margin: 0 auto;
  padding: var(--deid-stage-pad);
}
.panel-fill {
  width: 100%;
  max-width: var(--deid-content-max);
  margin: 0 auto;
  padding: var(--deid-stage-pad);
}
@media (min-width: 769px) {
  .panel-fill {
    max-width: none;
    margin: 0;
    padding: 0;
    height: 100%;
  }
  .panel-fill--rehydrate {
    background: var(--deid-bg);
  }
  .panel-fill--lexicon {
    max-width: none;
    margin: 0;
    padding: 0;
    height: auto;
  }
}
.running-stage {
  max-width: 720px;
  margin: 0 auto;
  text-align: center;
}
.confirm-card {
  margin-top: 1.5rem;
  padding: 2rem 1.75rem !important;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  width: 100%;
}
.confirm-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 14px;
  background: var(--deid-preset-bg);
  color: var(--deid-primary);
}
.confirm-text {
  margin: 0;
  font-size: 1.0625rem;
  color: var(--deid-ink-secondary);
}
.confirm-card .deid-btn {
  min-width: 200px;
}
.finish-verify-banner,
.readiness-banner {
  margin: 0 0 1rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--deid-radius-sm);
  font-size: 0.9375rem;
}
.finish-verify-banner {
  background: rgba(37, 99, 235, 0.08);
  border: 1px solid rgba(37, 99, 235, 0.25);
  color: var(--deid-primary);
}
.readiness-banner {
  background: var(--deid-success-bg);
  border: 1px solid var(--deid-success-border);
  color: var(--deid-success);
}
.readiness-banner--warn {
  background: rgba(180, 83, 9, 0.08);
  border-color: var(--deid-warning, #b45309);
  color: var(--deid-warning, #b45309);
}
.snapshot-list {
  margin: 1rem 0;
  padding: 0.85rem 1rem !important;
}
.snapshot-title {
  margin: 0 0 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.snapshot-ul {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
}
.snapshot-more {
  color: var(--deid-ink-muted);
  list-style: none;
  margin-left: -1.1rem;
}
.worker-opt {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 1rem;
  font-size: 1rem;
  cursor: pointer;
  color: var(--deid-ink-secondary);
}
.worker-opt input {
  width: 18px;
  height: 18px;
  accent-color: var(--deid-primary);
}
.upload-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - var(--deid-topbar-height) - 10rem);
  gap: 1.5rem;
}
.upload-head {
  text-align: center;
  max-width: 720px;
}
.err {
  color: var(--deid-danger);
  font-size: 1rem;
  margin: 0;
  text-align: center;
}
.job-stage {
  width: 100%;
}
.job-card {
  margin-top: 1.5rem;
}
.job-ready {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 1rem 0;
}
.file-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 14px;
  background: var(--deid-primary-soft);
  color: var(--deid-primary);
  flex-shrink: 0;
}
.ready-text {
  margin: 0;
  font-size: 1.0625rem;
  color: var(--deid-ink-secondary);
}
.cta {
  margin-top: 1rem;
}
.manual-add {
  display: flex;
  gap: 0.75rem;
  margin: 1.25rem 0;
}
.override-summary {
  margin: 0 0 0.75rem;
  color: var(--deid-ink-secondary);
}
.override-residuals-title {
  margin: 0 0 0.35rem;
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--deid-danger);
}
.override-residuals {
  margin: 0 0 1rem;
  padding-left: 1.25rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-secondary);
}
.override-more {
  color: var(--deid-ink-muted);
  font-style: italic;
}
.override-ack {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  font-size: 0.9375rem;
  color: var(--deid-ink);
  cursor: pointer;
}
.override-ack input {
  margin-top: 0.2rem;
  accent-color: var(--deid-primary);
}
.override-reason {
  margin-top: 0.25rem;
}
@media (max-width: 768px) {
  .toast {
    margin: 0.75rem 1rem 0;
  }
  .upload-stage {
    min-height: auto;
    padding-bottom: 2rem;
  }
}
</style>
