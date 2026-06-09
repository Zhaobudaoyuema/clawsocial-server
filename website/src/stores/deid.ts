import { defineStore } from 'pinia'
import { ref } from 'vue'

const API = '/api/deid'

export const DEFAULT_ENTITY_TYPES = [
  { code: 'company', label: '公司', placeholder_prefix: '公司' },
  { code: 'person', label: '姓名', placeholder_prefix: '姓名' },
  { code: 'org', label: '机构', placeholder_prefix: '机构' },
] as const

async function readJson<T = unknown>(r: Response): Promise<T> {
  const text = await r.text()
  if (!r.ok) {
    throw new Error(text || r.statusText || '请求失败')
  }
  if (text.startsWith('错误 ')) {
    throw new Error(text.replace(/^错误 \d+：/, ''))
  }
  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(text || '服务器返回无效 JSON')
  }
}

export const useDeidStore = defineStore('deid', () => {
  const jobs = ref<Record<string, unknown>[]>([])
  const currentJob = ref<Record<string, unknown> | null>(null)
  const entities = ref<Record<string, unknown>[]>([])
  const libraryEntities = ref<Record<string, unknown>[]>([])
  const entityTypes = ref<{ code: string; label: string; placeholder_prefix: string }[]>([])
  const previews = ref<{ before: string; after: string }[]>([])
  const loading = ref(false)
  const loadingMessage = ref('')
  const error = ref<string | null>(null)
  const scanSummary = ref<Record<string, unknown> | null>(null)
  const scanProgress = ref<{
    phase: string
    percent: number
    message: string
    queue_position?: number
    fallback?: string
  } | null>(null)
  const showConclusionView = ref(false)
  const showEntitiesPanel = ref(false)
  const entityDirty = ref(false)
  const aiSummary = ref<string | null>(null)
  const queueStatus = ref<{
    current_job_id: number | null
    waiting_job_ids: number[]
    waiting_count: number
  }>({ current_job_id: null, waiting_job_ids: [], waiting_count: 0 })
  const workerStatus = ref<{
    online: boolean
    state: string
    model: string | null
    hostname: string | null
    version: string | null
  }>({
    online: false,
    state: 'offline',
    model: null,
    hostname: null,
    version: null,
  })
  const workerWasOffline = ref(false)
  const jobsError = ref<string | null>(null)

  /** Worker 在线且任务启用 Worker 时才需要结论卡 */
  function needsConclusionStep(job?: Record<string, unknown> | null): boolean {
    const j = job ?? currentJob.value
    if (!j) return false
    const useWorker = (j as { use_worker?: boolean }).use_worker !== false
    return useWorker && workerStatus.value.online
  }

  function openConclusionView() {
    showConclusionView.value = true
    showEntitiesPanel.value = false
  }

  function closeConclusionView() {
    showConclusionView.value = false
  }

  function openEntitiesPanel() {
    showEntitiesPanel.value = true
    showConclusionView.value = false
  }

  function closeEntitiesPanel() {
    showEntitiesPanel.value = false
  }

  /** scanned 且未在结论页时显示 banner */
  function showPendingBanner(job?: Record<string, unknown> | null): boolean {
    const j = job ?? currentJob.value
    if (!j) return false
    const st = (j as { status?: string }).status
    if (st !== 'scanned' && st !== 'confirmed') return false
    if (showConclusionView.value) return false
    return entities.value.length > 0 && needsConclusionStep(j)
  }

  async function fetchJobSnapshot(jobId: number) {
    return readJson<Record<string, unknown>>(await fetch(`${API}/jobs/${jobId}`))
  }

  async function loadEntitiesSnapshot(jobId: number) {
    return readJson<Record<string, unknown>[]>(await fetch(`${API}/jobs/${jobId}/entities`))
  }

  async function fetchPreviewSnapshot(jobId: number) {
    const r = await fetch(`${API}/jobs/${jobId}/preview`, { method: 'POST' })
    if (!r.ok) return []
    const data = await readJson<{ previews?: { before: string; after: string }[] }>(r)
    return data.previews ?? []
  }

  async function autoRunAfterScan(jobId: number) {
    const ents = await loadEntities(jobId)
    const ids = ents
      .filter((e) => !(e as { is_excluded?: boolean }).is_excluded)
      .map((e) => (e as { id: number }).id)
    if (!ids.length) {
      openConclusionView()
      return ents
    }
    await confirmAndRun(jobId, ids, [])
    return ents
  }

  async function fetchWorkerStatus() {
    try {
      const r = await fetch(`${API}/worker/status`)
      if (r.ok) {
        const prev = workerStatus.value.online
        workerStatus.value = await readJson(r)
        if (!prev && workerStatus.value.online) {
          workerWasOffline.value = true
        }
      }
    } catch {
      workerStatus.value = {
        online: false,
        state: 'offline',
        model: null,
        hostname: null,
        version: null,
      }
    }
  }

  function clearWorkerToast() {
    workerWasOffline.value = false
  }

  async function fetchJobs() {
    jobsError.value = null
    try {
      const r = await fetch(`${API}/jobs`)
      jobs.value = await readJson(r)
    } catch (e) {
      jobsError.value = e instanceof Error ? e.message : '加载任务列表失败'
      jobs.value = []
    }
  }

  function clearJobsError() {
    jobsError.value = null
  }

  async function fetchQueueStatus() {
    try {
      const r = await fetch(`${API}/queue/status`)
      if (r.ok) {
        queueStatus.value = await readJson(r)
      }
    } catch {
      queueStatus.value = { current_job_id: null, waiting_job_ids: [], waiting_count: 0 }
    }
  }

  async function fetchJob(jobId: number) {
    const job = await readJson<Record<string, unknown>>(await fetch(`${API}/jobs/${jobId}`))
    currentJob.value = job
    const progress = job.progress as typeof scanProgress.value
    if (progress) scanProgress.value = progress
    const summary = job.ai_summary as { text?: string } | null
    aiSummary.value = summary?.text ?? null
    return job
  }

  async function loadEntities(jobId: number) {
    const r = await fetch(`${API}/jobs/${jobId}/entities`)
    entities.value = await readJson(r)
    return entities.value
  }

  async function restoreCurrentJob() {
    const incomplete = jobs.value.find(
      (j) => (j as { status: string }).status !== 'done',
    ) as { id: number; status: string } | undefined
    if (!incomplete) return

    await fetchJob(incomplete.id)
    const status = incomplete.status

    if (status === 'scanned' || status === 'confirmed') {
      await loadEntities(incomplete.id)
      if (needsConclusionStep(currentJob.value)) {
        /* 刷新恢复：选项 C — 仅 banner，不自动弹结论 */
      } else {
        await autoRunAfterScan(incomplete.id)
      }
    } else if (status === 'scanning' || status === 'queued') {
      await pollScanUntilDone(incomplete.id)
    } else if (status === 'done') {
      await loadEntities(incomplete.id)
      await fetchPreview(incomplete.id)
    }
  }

  async function selectJob(job: Record<string, unknown>) {
    currentJob.value = job
    error.value = null
    entityDirty.value = false
    showConclusionView.value = false
    showEntitiesPanel.value = false
    const id = job.id as number
    const status = job.status as string

    if (status === 'done') {
      await fetchJob(id)
      await loadEntities(id)
      await fetchPreview(id)
      return
    }
    if (status === 'scanned' || status === 'confirmed') {
      await fetchJob(id)
      await loadEntities(id)
      if (needsConclusionStep(currentJob.value)) {
        /* banner only unless user clicks */
      } else {
        await autoRunAfterScan(id)
      }
      return
    }
    if (status === 'scanning' || status === 'queued') {
      await pollScanUntilDone(id)
      return
    }
    entities.value = []
  }

  async function newTask() {
    currentJob.value = null
    entities.value = []
    previews.value = []
    error.value = null
    scanProgress.value = null
    showConclusionView.value = false
    showEntitiesPanel.value = false
    entityDirty.value = false
    aiSummary.value = null
  }

  async function uploadJob(
    file: File,
    opts?: { promptExtra?: string; useWorker?: boolean },
  ) {
    loading.value = true
    loadingMessage.value = '正在上传…'
    error.value = null
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (opts?.promptExtra?.trim()) {
        fd.append('prompt_extra', opts.promptExtra.trim())
      }
      fd.append('use_worker', opts?.useWorker !== false ? 'true' : 'false')
      const r = await fetch(`${API}/jobs`, { method: 'POST', body: fd })
      currentJob.value = await readJson(r)
      entityDirty.value = false
      showConclusionView.value = false
    showEntitiesPanel.value = false
      await fetchJobs()
      return currentJob.value
    } catch (e) {
      error.value = e instanceof Error ? e.message : '上传失败'
      throw e
    } finally {
      loading.value = false
      loadingMessage.value = ''
    }
  }

  async function startScan(jobId: number) {
    error.value = null
    scanProgress.value = { phase: 'starting', percent: 0, message: '提交任务…' }
    const data = await readJson<{ status: string; queue_position?: number }>(
      await fetch(`${API}/jobs/${jobId}/start`, { method: 'POST' }),
    )
    await fetchJob(jobId)
    await fetchQueueStatus()
    if (data.queue_position && data.queue_position > 0) {
      scanProgress.value = {
        phase: 'queued',
        percent: 0,
        message: `排队中（第 ${data.queue_position} 位）`,
        queue_position: data.queue_position,
      }
    }
    return data
  }

  async function pollScanUntilDone(jobId: number) {
    loading.value = true
    error.value = null
    try {
      for (;;) {
        await new Promise((r) => setTimeout(r, 800))
        await fetchQueueStatus()
        const job = await fetchJob(jobId)
        const status = job.status as string
        const progress = job.progress as typeof scanProgress.value
        if (progress) {
          scanProgress.value = progress
          loadingMessage.value = progress.message
        }
        if (status === 'scanned') {
          await loadEntities(jobId)
          scanProgress.value = null
          if (needsConclusionStep(job)) {
            openConclusionView()
          } else {
            await autoRunAfterScan(jobId)
          }
          return entities.value
        }
        if (status === 'draft' && progress?.phase === 'error') {
          if (progress.fallback === 'manual') {
            await loadEntities(jobId)
            scanProgress.value = null
            if (needsConclusionStep(job)) {
              openConclusionView()
            } else {
              await autoRunAfterScan(jobId)
            }
            return entities.value
          }
          throw new Error(progress.message || '扫描失败')
        }
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : '扫描失败'
      scanProgress.value = null
      throw e
    } finally {
      loading.value = false
      loadingMessage.value = ''
    }
  }

  async function fetchPreview(jobId: number) {
    const r = await fetch(`${API}/jobs/${jobId}/preview`, { method: 'POST' })
    if (r.ok) {
      const data = await readJson<{ previews?: { before: string; after: string }[] }>(r)
      previews.value = data.previews ?? []
    }
  }

  async function addManual(jobId: number, body: Record<string, unknown>) {
    entities.value = await readJson(
      await fetch(`${API}/jobs/${jobId}/entities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
    entityDirty.value = true
  }

  async function deleteEntity(jobId: number, entityId: number) {
    entities.value = await readJson(
      await fetch(`${API}/jobs/${jobId}/entities/${entityId}`, { method: 'DELETE' }),
    )
    entityDirty.value = true
  }

  async function patchEntity(jobId: number, entityId: number, body: Record<string, unknown>) {
    entities.value = await readJson(
      await fetch(`${API}/jobs/${jobId}/entities/${entityId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
  }

  async function confirmAndRun(
    jobId: number,
    entityIds: number[],
    rememberIds: number[],
  ) {
    loading.value = true
    loadingMessage.value = '正在脱敏…'
    error.value = null
    showConclusionView.value = false
    showEntitiesPanel.value = false
    try {
      const r = await fetch(`${API}/jobs/${jobId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_ids: entityIds, remember_ids: rememberIds }),
      })
      const data = await readJson<Record<string, unknown>>(r)
      if (currentJob.value) {
        currentJob.value = { ...currentJob.value, ...data, status: data.status }
      }
      entityDirty.value = false
      aiSummary.value = null
      await loadEntities(jobId)
      await fetchPreview(jobId)
      await fetchJobs()
      return data
    } finally {
      loading.value = false
      loadingMessage.value = ''
    }
  }

  async function rerun(jobId: number, entityIds: number[], rememberIds: number[]) {
    loading.value = true
    loadingMessage.value = '正在重新脱敏…'
    error.value = null
    try {
      const r = await fetch(`${API}/jobs/${jobId}/rerun`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_ids: entityIds, remember_ids: rememberIds }),
      })
      const data = await readJson<Record<string, unknown>>(r)
      if (currentJob.value) {
        currentJob.value = { ...currentJob.value, ...data, status: data.status }
      }
      entityDirty.value = false
      aiSummary.value = null
      await fetchJob(jobId)
      await loadEntities(jobId)
      await fetchPreview(jobId)
      await fetchJobs()
      return data
    } finally {
      loading.value = false
      loadingMessage.value = ''
    }
  }

  async function fetchAiSummary(jobId: number) {
    loading.value = true
    loadingMessage.value = 'AI 解读中…'
    try {
      const data = await readJson<{ text: string }>(
        await fetch(`${API}/jobs/${jobId}/ai-summary`, { method: 'POST' }),
      )
      aiSummary.value = data.text
      return data.text
    } finally {
      loading.value = false
      loadingMessage.value = ''
    }
  }

  async function deleteJob(jobId: number) {
    await fetch(`${API}/jobs/${jobId}`, { method: 'DELETE' })
    if ((currentJob.value as { id?: number } | null)?.id === jobId) {
      await newTask()
    }
    await fetchJobs()
  }

  function exportUrl(jobId: number, overrideAck: boolean, reason?: string) {
    const q = new URLSearchParams({ override_ack: String(overrideAck) })
    if (reason) q.set('override_reason', reason)
    return `${API}/jobs/${jobId}/export?${q}`
  }

  async function fetchLibrary(q?: string) {
    const url = q ? `${API}/entities?q=${encodeURIComponent(q)}` : `${API}/entities`
    libraryEntities.value = await readJson(await fetch(url))
  }

  async function fetchEntityTypes() {
    try {
      const data = await readJson<{ code: string; label: string; placeholder_prefix: string }[]>(
        await fetch(`${API}/entity-types`),
      )
      entityTypes.value = data.length ? data : [...DEFAULT_ENTITY_TYPES]
    } catch {
      entityTypes.value = [...DEFAULT_ENTITY_TYPES]
    }
  }

  function entityTypeLabel(code: string) {
    return entityTypes.value.find((t) => t.code === code)?.label ?? code
  }

  async function createEntityType(body: { code: string; label: string; placeholder_prefix: string }) {
    await readJson(
      await fetch(`${API}/entity-types`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
    await fetchEntityTypes()
  }

  async function updateEntityType(
    code: string,
    body: { label?: string; placeholder_prefix?: string },
  ) {
    await readJson(
      await fetch(`${API}/entity-types/${encodeURIComponent(code)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
    await fetchEntityTypes()
  }

  async function deleteEntityType(code: string) {
    await readJson(
      await fetch(`${API}/entity-types/${encodeURIComponent(code)}`, { method: 'DELETE' }),
    )
    await fetchEntityTypes()
  }

  return {
    jobs,
    currentJob,
    entities,
    libraryEntities,
    entityTypes,
    previews,
    loading,
    loadingMessage,
    error,
    scanSummary,
    scanProgress,
    showConclusionView,
    showEntitiesPanel,
    openConclusionView,
    closeConclusionView,
    openEntitiesPanel,
    closeEntitiesPanel,
    showPendingBanner,
    entityDirty,
    aiSummary,
    queueStatus,
    workerStatus,
    workerWasOffline,
    jobsError,
    clearJobsError,
    needsConclusionStep,
    fetchJobSnapshot,
    loadEntitiesSnapshot,
    fetchPreviewSnapshot,
    autoRunAfterScan,
    fetchWorkerStatus,
    clearWorkerToast,
    fetchJobs,
    fetchQueueStatus,
    fetchJob,
    loadEntities,
    restoreCurrentJob,
    selectJob,
    newTask,
    uploadJob,
    startScan,
    pollScanUntilDone,
    fetchPreview,
    addManual,
    deleteEntity,
    patchEntity,
    confirmAndRun,
    rerun,
    fetchAiSummary,
    deleteJob,
    exportUrl,
    fetchLibrary,
    fetchEntityTypes,
    entityTypeLabel,
    createEntityType,
    updateEntityType,
    deleteEntityType,
    DEFAULT_ENTITY_TYPES,
  }
})
