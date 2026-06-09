<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidUploadCard from './DeidUploadCard.vue'
import DeidScanProgress from './DeidScanProgress.vue'
import DeidCompletionHero from './DeidCompletionHero.vue'
import DeidReplaceSamples from './DeidReplaceSamples.vue'
import DeidEntityList from './DeidEntityList.vue'
import DeidConclusionView from './DeidConclusionView.vue'
import DeidMyEntities from './DeidMyEntities.vue'
import DeidStepper from './DeidStepper.vue'
import DeidWorkerBanner from './DeidWorkerBanner.vue'

const store = useDeidStore()

const selectedFile = ref<File | null>(null)
const uploadError = ref<string | null>(null)
const useWorker = ref(true)
const overrideAck = ref(false)
const overrideReason = ref('')
const manualName = ref('')
const jobsToastDismissed = ref(false)

const job = computed(() => store.currentJob)
const jobId = computed(() => (job.value as { id?: number } | null)?.id)
const status = computed(() => (job.value as { status?: string } | null)?.status || 'idle')
const workerOnline = computed(() => store.workerStatus.online)
const isScanning = computed(() => status.value === 'scanning' || status.value === 'queued')
const isDone = computed(() => status.value === 'done')
const isDraft = computed(() => !!job.value && status.value === 'draft')
const isAwaitingConfirm = computed(() => {
  if (!job.value || isDone.value) return false
  const st = status.value
  return st === 'scanned' || st === 'confirmed'
})
const isRunningDeid = computed(() => status.value === 'running')
const hasJob = computed(() => !!job.value && !isDone.value && !isAwaitingConfirm.value && !isRunningDeid.value)

const verification = computed(
  () => ((job.value as { verification?: Record<string, unknown> })?.verification) || {},
)
const canDownload = computed(() => verification.value.passed || overrideAck.value)

const pendingCount = computed(() =>
  store.entities.filter((e) => !(e as { is_excluded?: boolean }).is_excluded).length,
)

const currentStep = computed((): 'upload' | 'scan' | 'confirm' | 'done' => {
  if (store.showEntitiesPanel) return 'upload'
  if (isDone.value) return 'done'
  if (store.showConclusionView) return 'confirm'
  const st = status.value
  if (st === 'scanned' || st === 'confirmed') return 'confirm'
  if (st === 'scanning' || st === 'queued') return 'scan'
  return 'upload'
})

const showWorkerBanner = computed(
  () => !workerOnline.value && !isDone.value && !store.showEntitiesPanel,
)

const showJobsError = computed(
  () => !!store.jobsError && !jobsToastDismissed.value,
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
  try {
    await store.startScan(jobId.value)
    await store.pollScanUntilDone(jobId.value)
  } catch {
    uploadError.value = store.error || '扫描失败'
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
</script>

<template>
  <main class="stage">
    <div v-if="store.workerWasOffline && store.workerStatus.online" class="toast toast--ok">
      Worker 已上线，可使用智能发现
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
      <!-- 我的实体 -->
      <DeidMyEntities v-if="store.showEntitiesPanel" key="entities" class="panel-fill" />

      <!-- 结论全屏 -->
      <DeidConclusionView v-else-if="store.showConclusionView" key="conclusion" />

      <!-- 完成页 -->
      <div v-else-if="isDone && job" key="done" class="done-wrap">
        <DeidStepper :current="currentStep" />
        <DeidCompletionHero :job="job" :entities="store.entities" />
        <DeidReplaceSamples :previews="store.previews" />
        <DeidEntityList :entities="store.entities" editable @delete="onDeleteEntity" />
        <div class="manual-add">
          <input v-model="manualName" class="deid-input" placeholder="添加实体后需重新脱敏" />
          <button type="button" class="deid-btn" @click="addManualDone">添加</button>
        </div>
        <div v-if="store.aiSummary" class="ai-box">{{ store.aiSummary }}</div>
        <div v-if="!verification.passed" class="override">
          <label><input v-model="overrideAck" type="checkbox" /> 本人已知晓风险，仍要下载</label>
        </div>
        <div class="actions">
          <a
            v-if="canDownload && jobId"
            class="deid-btn deid-btn--primary"
            :href="store.exportUrl(jobId, overrideAck, overrideReason || undefined)"
            download
          >
            下载文档
          </a>
          <button v-if="store.entityDirty" type="button" class="deid-btn" @click="doRerun">
            重新脱敏
          </button>
          <button
            v-if="store.workerStatus.online && jobId"
            type="button"
            class="deid-btn deid-btn--ghost"
            @click="store.fetchAiSummary(jobId!)"
          >
            AI 解读
          </button>
        </div>
      </div>

      <!-- 上传 / 扫描 -->
      <div v-else key="upload" class="upload-wrap">
        <DeidStepper :current="currentStep" />

        <DeidWorkerBanner v-if="showWorkerBanner" />

        <div v-if="!hasJob && !isAwaitingConfirm && !isRunningDeid" class="upload-stage">
          <div class="upload-head">
            <h2 class="deid-page-title">上传 Word 文档</h2>
            <p class="deid-page-sub">选择 .docx 文件，自动上传并开始流程</p>
          </div>
          <label v-if="workerOnline" class="worker-opt">
            <input v-model="useWorker" type="checkbox" :disabled="store.loading" />
            使用 Mac Worker 智能发现
          </label>
          <DeidUploadCard
            :disabled="store.loading || isScanning"
            :loading="store.loading"
            @select="onSelect"
          />
          <p v-if="uploadError || store.error" class="err">{{ uploadError || store.error }}</p>
        </div>

        <!-- 扫描完成，待确认实体 -->
        <div v-else-if="isAwaitingConfirm && job" class="confirm-stage">
          <h2 class="deid-page-title">{{ (job as { original_filename: string }).original_filename }}</h2>
          <p class="deid-page-sub">
            {{ pendingCount > 0 ? `发现 ${pendingCount} 个实体待确认` : '未发现实体，请手动添加后继续' }}
          </p>
          <div class="confirm-card deid-panel">
            <div class="confirm-icon" aria-hidden="true">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
                <path d="M9 12l2 2 4-4M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>
            <p class="confirm-text">
              {{ pendingCount > 0 ? '请查看扫描结论，勾选要脱敏的实体' : '打开结论页手动添加实体' }}
            </p>
            <button type="button" class="deid-btn deid-btn--primary deid-btn--lg" @click="store.openConclusionView()">
              查看结论
            </button>
          </div>
        </div>

        <!-- 脱敏进行中 -->
        <div v-else-if="isRunningDeid && job" class="job-stage">
          <h2 class="deid-page-title">{{ (job as { original_filename: string }).original_filename }}</h2>
          <p class="deid-page-sub">正在脱敏，请稍候…</p>
          <div class="job-card deid-panel confirm-card">
            <span class="deid-spinner" aria-hidden="true" />
            <p class="confirm-text">替换敏感实体中</p>
          </div>
        </div>

        <div v-else-if="job" class="job-stage">
          <h2 class="deid-page-title">{{ (job as { original_filename: string }).original_filename }}</h2>
          <p class="deid-page-sub">
            {{ isScanning ? '正在扫描文档…' : '确认无误后开始扫描' }}
          </p>

          <div class="job-card deid-panel">
            <DeidScanProgress
              v-if="isScanning && store.scanProgress"
              :percent="store.scanProgress.percent"
              :message="store.scanProgress.message"
              :phase="store.scanProgress.phase"
              :queue-position="store.scanProgress.queue_position"
            />

            <div v-else class="job-ready">
              <div class="file-icon" aria-hidden="true">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                  <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                </svg>
              </div>
              <p class="ready-text">文档已就绪，点击开始扫描</p>
            </div>

            <p v-if="uploadError || store.error" class="err">{{ uploadError || store.error }}</p>

            <div v-if="isDraft" class="cta">
              <button
                type="button"
                class="deid-btn deid-btn--primary deid-btn--lg"
                :disabled="store.loading || isScanning"
                @click="doScan"
              >
                {{ workerOnline ? '开始扫描' : '匹配已记住实体' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </main>
</template>

<style scoped>
.stage {
  flex: 1;
  min-height: calc(100vh - var(--deid-topbar-height));
  overflow-y: auto;
  background: var(--deid-bg);
}
.toast {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 2.5rem 0;
  padding: 0.75rem 1rem;
  border-radius: var(--deid-radius-sm);
  font-size: 1rem;
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
.pending-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
  background: var(--deid-preset-bg);
  border: 1px solid var(--deid-primary-soft);
  border-left: 4px solid var(--deid-primary);
  border-radius: var(--deid-radius);
  font-size: 1.0625rem;
  font-weight: 500;
  color: var(--deid-ink);
  box-shadow: var(--deid-shadow-sm);
}
.confirm-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - var(--deid-topbar-height) - 12rem);
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
  max-width: 720px;
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
.ai-box {
  padding: 1.1rem 1.25rem;
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius);
  font-size: 1rem;
  margin-bottom: 1.25rem;
  color: var(--deid-ink-secondary);
  line-height: 1.65;
}
.override {
  font-size: 1rem;
  margin-bottom: 1.25rem;
}
.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
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
