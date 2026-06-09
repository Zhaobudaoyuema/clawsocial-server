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
    stats?: {
      paragraphs?: number
      chars?: number
      chunks?: number
      tables?: number
    }
    metrics?: {
      elapsed_ms?: number
      prompt_tokens?: number
      completion_tokens?: number
      model?: string | null
    }
    log_tail?: string[]
  } | null>(null)
  const scanLive = ref({
    stats: null as {
      paragraphs?: number
      chars?: number
      chunks?: number
      tables?: number
    } | null,
    metrics: null as {
      elapsed_ms?: number
      prompt_tokens?: number
      completion_tokens?: number
      model?: string | null
    } | null,
    logs: [] as string[],
    entitiesFound: 0,
    streamConnected: false,
    startedAt: null as number | null,
    doneSummary: null as string | null,
    streamTail: '',
  })
  let scanEventSource: EventSource | null = null

  function resetScanLive() {
    scanLive.value = {
      stats: null,
      metrics: null,
      logs: [],
      entitiesFound: 0,
      streamConnected: false,
      startedAt: null,
      doneSummary: null,
      streamTail: '',
    }
  }

  function appendScanLog(line: string) {
    if (!line) return
    const logs = scanLive.value.logs
    if (logs.length > 0 && logs[logs.length - 1] === line) return
    logs.push(line)
    if (logs.length > 80) logs.splice(0, logs.length - 80)
  }

  function handleScanEvent(event: Record<string, unknown>) {
    const type = event.type as string
    if (type === 'phase') {
      const phase = String(event.phase || '')
      scanProgress.value = {
        ...(scanProgress.value || { phase: 'starting', percent: 0, message: '' }),
        phase,
        percent: Number(event.percent ?? scanProgress.value?.percent ?? 0),
        message: String(event.message || ''),
      }
      if (phase === 'extract' && !scanLive.value.stats) {
        appendScanLog('正在解析文档…')
      }
    } else if (type === 'stats') {
      scanLive.value.stats = {
        paragraphs: event.paragraphs as number | undefined,
        chars: event.chars as number | undefined,
        chunks: event.chunks as number | undefined,
        tables: event.tables as number | undefined,
      }
      if (scanProgress.value) scanProgress.value.stats = scanLive.value.stats
    } else if (type === 'metrics') {
      scanLive.value.metrics = {
        elapsed_ms: event.elapsed_ms as number | undefined,
        prompt_tokens: event.prompt_tokens as number | undefined,
        completion_tokens: event.completion_tokens as number | undefined,
        model: (event.model as string | null | undefined) ?? null,
      }
      if (scanProgress.value) scanProgress.value.metrics = scanLive.value.metrics
    } else if (type === 'log') {
      appendScanLog(String(event.line || ''))
    } else if (type === 'token') {
      const chunk = String(event.content || '')
      scanLive.value.streamTail = (scanLive.value.streamTail + chunk).slice(-3000)
    } else if (type === 'entity') {
      scanLive.value.entitiesFound += 1
      appendScanLog(`发现实体：${String(event.name || '')}`)
    } else if (type === 'remembered') {
      const count = Number(event.count ?? 0)
      appendScanLog(`词库匹配 ${count} 个实体`)
    } else if (type === 'chunk_start') {
      scanLive.value.streamTail = ''
      appendScanLog(`—— 第 ${event.index}/${event.total} 段 ——`)
    } else if (type === 'done') {
      const summary = event.scan_summary as Record<string, unknown> | undefined
      if (summary) scanSummary.value = summary
      const count = Number(event.entity_count ?? 0)
      const ms = Number(summary?.elapsed_ms ?? scanLive.value.metrics?.elapsed_ms ?? 0)
      const tokens =
        Number(summary?.prompt_tokens ?? 0) + Number(summary?.completion_tokens ?? 0)
      scanLive.value.doneSummary = `发现 ${count} 个实体 · 用时 ${formatScanDuration(ms)}${
        tokens > 0 ? ` · Token ${tokens.toLocaleString('zh-CN')}` : ''
      }`
    } else if (type === 'error') {
      appendScanLog(`错误：${String(event.message || '扫描失败')}`)
    }
  }

  function formatScanDuration(ms: number) {
    const sec = Math.max(0, Math.floor(ms / 1000))
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${String(s).padStart(2, '0')}`
  }

  function disconnectScanStream() {
    if (scanEventSource) {
      scanEventSource.close()
      scanEventSource = null
    }
    scanLive.value.streamConnected = false
  }

  function connectScanStream(jobId: number) {
    disconnectScanStream()
    resetScanLive()
    scanLive.value.startedAt = Date.now()
    const es = new EventSource(`${API}/jobs/${jobId}/scan-stream`)
    scanEventSource = es
    es.onopen = () => {
      scanLive.value.streamConnected = true
    }
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as Record<string, unknown>
        handleScanEvent(data)
        if (data.type === 'done' || data.type === 'error') {
          disconnectScanStream()
        }
      } catch {
        /* ignore malformed */
      }
    }
    es.onerror = () => {
      scanLive.value.streamConnected = false
    }
  }
  const showConclusionView = ref(false)
  const showEntitiesPanel = ref(false)
  /** 用户主动打开「我的实体」时，禁止异步 restore/scan 抢回结论页 */
  const suppressAutoConclusion = ref(false)
  const entityDirty = ref(false)
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
    mode?: string
    relay_url?: string | null
  }>({
    online: false,
    state: 'offline',
    model: null,
    hostname: null,
    version: null,
    mode: undefined,
    relay_url: null,
  })
  const workerWasOffline = ref(false)
  const jobsError = ref<string | null>(null)
  const jobsLoading = ref(false)

  /** Worker 在线且任务启用 Worker 时才需要结论卡 */
  function needsConclusionStep(job?: Record<string, unknown> | null): boolean {
    const j = job ?? currentJob.value
    if (!j) return false
    const useWorker = (j as { use_worker?: boolean }).use_worker !== false
    return useWorker && workerStatus.value.online
  }

  type WizardPhase =
    | 'upload'
    | 'scan-draft'
    | 'scanning'
    | 'confirm-detail'
    | 'deid-running'
    | 'done'

  function wizardPhase(): WizardPhase {
    if (showEntitiesPanel.value) return 'upload'
    const job = currentJob.value as { status?: string } | null
    if (!job) return 'upload'
    if (showConclusionView.value) return 'confirm-detail'
    const st = job.status || ''
    if (st === 'done') return 'done'
    if (st === 'running') return 'deid-running'
    if (st === 'scanning' || st === 'queued') return 'scanning'
    const sp = scanProgress.value
    if (sp && sp.phase !== 'error' && sp.phase !== 'done') return 'scanning'
    if (st === 'scanned' || st === 'confirmed') return 'confirm-detail'
    if (st === 'draft') return 'scan-draft'
    return 'upload'
  }

  function wizardStep(): 'upload' | 'scan' | 'confirm' | 'done' {
    const phase = wizardPhase()
    if (phase === 'upload') return 'upload'
    if (phase === 'scan-draft' || phase === 'scanning') return 'scan'
    if (phase === 'confirm-detail') return 'confirm'
    return 'done'
  }

  function openConclusionView() {
    if (showEntitiesPanel.value || suppressAutoConclusion.value) return
    showConclusionView.value = true
    showEntitiesPanel.value = false
  }

  function closeConclusionView() {
    showConclusionView.value = false
  }

  function openEntitiesPanel() {
    suppressAutoConclusion.value = true
    showEntitiesPanel.value = true
    showConclusionView.value = false
  }

  function closeEntitiesPanel() {
    showEntitiesPanel.value = false
    suppressAutoConclusion.value = false
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
        mode: undefined,
        relay_url: null,
      }
    }
  }

  function clearWorkerToast() {
    workerWasOffline.value = false
  }

  async function fetchJobs() {
    jobsError.value = null
    jobsLoading.value = true
    try {
      const r = await fetch(`${API}/jobs`)
      jobs.value = await readJson(r)
    } catch (e) {
      jobsError.value = e instanceof Error ? e.message : '加载任务列表失败'
      jobs.value = []
    } finally {
      jobsLoading.value = false
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
        openConclusionView()
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
    suppressAutoConclusion.value = false
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
        openConclusionView()
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
    suppressAutoConclusion.value = false
    currentJob.value = null
    entities.value = []
    previews.value = []
    error.value = null
    disconnectScanStream()
    resetScanLive()
    scanProgress.value = null
    showConclusionView.value = false
    showEntitiesPanel.value = false
    entityDirty.value = false
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

  function beginScan(jobId: number) {
    error.value = null
    resetScanLive()
    scanProgress.value = { phase: 'starting', percent: 0, message: '正在提交扫描…' }
    connectScanStream(jobId)
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 'scanning' }
    }
  }

  async function startScan(jobId: number) {
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
    } else if (scanProgress.value?.phase === 'starting') {
      scanProgress.value = {
        ...scanProgress.value,
        message: '扫描已开始…',
      }
    }
    return data
  }

  async function pollScanUntilDone(jobId: number) {
    error.value = null
    try {
      for (;;) {
        await new Promise((r) => setTimeout(r, 600))
        await fetchQueueStatus()
        const job = await fetchJob(jobId)
        const status = job.status as string
        const progress = job.progress as typeof scanProgress.value
        if (progress) {
          scanProgress.value = progress
          loadingMessage.value = progress.message
          if (progress.stats) scanLive.value.stats = progress.stats
          if (progress.metrics) scanLive.value.metrics = progress.metrics
          if (progress.log_tail?.length && !scanLive.value.streamConnected) {
            for (const line of progress.log_tail) {
              appendScanLog(line)
            }
          }
        }
        if (status === 'scanned') {
          await loadEntities(jobId)
          disconnectScanStream()
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
            disconnectScanStream()
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
      disconnectScanStream()
      scanProgress.value = null
      throw e
    } finally {
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
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 'running' }
    }
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
      await loadEntities(jobId)
      await fetchPreview(jobId)
      await fetchJobs()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : '脱敏失败'
      if (currentJob.value) {
        currentJob.value = { ...currentJob.value, status: 'scanned' }
      }
      openConclusionView()
      throw e
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
      await fetchJob(jobId)
      await loadEntities(jobId)
      await fetchPreview(jobId)
      await fetchJobs()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : '重新脱敏失败'
      throw e
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
    scanLive,
    showConclusionView,
    showEntitiesPanel,
    suppressAutoConclusion,
    wizardPhase,
    wizardStep,
    openConclusionView,
    closeConclusionView,
    openEntitiesPanel,
    closeEntitiesPanel,
    entityDirty,
    queueStatus,
    workerStatus,
    workerWasOffline,
    jobsError,
    jobsLoading,
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
    beginScan,
    startScan,
    pollScanUntilDone,
    fetchPreview,
    addManual,
    deleteEntity,
    patchEntity,
    confirmAndRun,
    rerun,
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
