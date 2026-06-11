import { defineStore } from 'pinia'
import { ref } from 'vue'
import { semanticCatLabel } from '../components/deid/semanticCategories'
import { deidEventSourceUrl, deidFetch, getDeidAccessToken } from '../utils/deidAccess'
import type { SourceMarkdownPayload } from '../utils/deidFormats'

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
  const workerCalls = ref<Record<string, unknown>[]>([])
  const semanticRisks = ref<Record<string, unknown>[]>([])
  const semanticLoading = ref(false)
  const semanticSelection = ref<Record<string, unknown>[]>([])
  const scanSnapshotEntities = ref<Record<string, unknown>[]>([])
  const semanticStageEntered = ref(false)
  const markdownStageEntered = ref(false)
  const sourceMarkdown = ref<SourceMarkdownPayload | null>(null)
  const sourceMarkdownLoading = ref(false)
  const reScanning = ref(false)
  const scanSession = ref<'initial' | 'rescan' | 'semantic' | null>(null)
  const rescanGateOpen = ref(false)
  const lastRescanResult = ref<{
    run: number
    delta: number
    noChange: boolean
  } | null>(null)
  const globalExperience = ref<Record<string, unknown>[]>([])

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

    if (scanSession.value === 'semantic' && type === 'done') return

    if (scanSession.value === 'rescan') {
      if (type === 'rescan_start') {
        rescanGateOpen.value = true
      } else if (!rescanGateOpen.value) {
        if (type !== 'log' && type !== 'entity' && type !== 'token' && type !== 'chunk_start') {
          return
        }
      }
      if (type === 'done') return
      if (type === 'phase') {
        const phase = String(event.phase || '')
        if (phase !== 're_discover' && phase !== 'done' && phase !== 'error') return
        const msg = String(event.message || '')
        if (msg.includes('初次识别')) return
      }
    }

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
      const name = String(event.name || '')
      const typeCode = String(event.entity_type || '')
      const typeLabel = typeCode ? entityTypeLabel(typeCode) : ''
      appendScanLog(
        typeLabel ? `发现实体 [${typeLabel}]：${name}` : `发现实体：${name}`,
      )
    } else if (type === 'remembered') {
      const count = Number(event.count ?? 0)
      appendScanLog(`词库匹配 ${count} 个实体`)
    } else if (type === 'rescan_start') {
      rescanGateOpen.value = true
      resetScanLive()
      const n = Number(event.re_run_count ?? 1)
      scanProgress.value = {
        phase: 're_discover',
        percent: 5,
        message: `开始第 ${n} 次再识别…`,
      }
      appendScanLog(`—— 第 ${n} 次再识别 ——`)
    } else if (type === 'chunk_start') {
      scanLive.value.streamTail = ''
      appendScanLog(`—— 第 ${event.index}/${event.total} 段 ——`)
    } else if (type === 'risk') {
      const original = String(event.original || '')
      const catCode = String(event.category || '')
      const catLabel = semanticCatLabel(catCode)
      const label = original.length > 40 ? `${original.slice(0, 40)}…` : original
      appendScanLog(`发现语义风险 [${catLabel}]：${label}`)
    } else if (type === 'semantic_done') {
      const count = Number(event.risk_count ?? 0)
      const filled = Number(event.rewrite_count ?? 0)
      appendScanLog(
        count > 0
          ? `语义扫描完成，发现 ${count} 条风险，已生成 ${filled} 条改写`
          : '语义扫描完成，未发现语义指纹',
      )
      scanProgress.value = {
        phase: 'semantic_review',
        percent: 100,
        message:
          count > 0
            ? `发现 ${count} 条语义风险，已生成 ${filled} 条改写`
            : '未发现需改写的语义指纹',
      }
    } else if (type === 'entities_snapshot') {
      const list = event.entities as Record<string, unknown>[] | undefined
      const round = String(event.round || '')
      if (Array.isArray(list)) {
        scanSnapshotEntities.value = list
        appendScanLog(`实体列表更新（${round || '快照'}，${list.length} 个）`)
      }
    } else if (type === 'scan_round_done') {
      const round = String(event.round || '')
      if (round === 're_run') {
        const run = Number(event.re_run_count ?? 0)
        const delta = Number(event.delta ?? 0)
        const noChange = Boolean(event.no_change)
        appendScanLog(
          delta > 0
            ? `再识别完成，新增 ${delta} 个实体`
            : '再识别完成，本轮无新增实体',
        )
        lastRescanResult.value = { run, delta, noChange }
        scanProgress.value = {
          phase: 'done',
          percent: 100,
          message: delta > 0 ? `第 ${run} 次再识别完成，新增 ${delta} 个` : `第 ${run} 次再识别完成，本轮无新增`,
        }
      }
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
      semanticStageEntered.value = false
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

  function connectScanStream(jobId: number, opts?: { reset?: boolean; fresh?: boolean }) {
    disconnectScanStream()
    if (opts?.reset !== false) {
      resetScanLive()
    }
    scanLive.value.startedAt = Date.now()
    const qs = opts?.fresh ? '?fresh=1' : ''
    const es = new EventSource(deidEventSourceUrl(`${API}/jobs/${jobId}/scan-stream${qs}`))
    scanEventSource = es
    es.onopen = () => {
      scanLive.value.streamConnected = true
    }
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as Record<string, unknown>
        handleScanEvent(data)
        if (data.type === 'done' || data.type === 'error') {
          if (scanSession.value !== 'rescan' && scanSession.value !== 'semantic') {
            disconnectScanStream()
          }
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
  const showRehydratePanel = ref(false)
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
    | 'markdown-preview'
    | 'scan-draft'
    | 'scanning'
    | 'entity-scanned'
    | 'semantic-idle'
    | 'semantic-scanning'
    | 'semantic-review'
    | 'program-running'
    | 'program-review'
    | 'confirm-detail'
    | 'finishing'
    | 'done'

  type ProgramScanChange = {
    id: string
    action: 'add_alias' | 'new_entity'
    entity_id?: number
    canonical_name?: string
    text: string
    hit_count?: number
    reverted?: boolean
  }

  type ProgramScanPayload = {
    run_at?: string | null
    residual_before?: number
    residual_after?: number
    changes?: ProgramScanChange[]
  }

  const programStageEntered = ref(false)
  const programScanRunning = ref(false)
  const programScan = ref<ProgramScanPayload | null>(null)

  function wizardPhase(): WizardPhase {
    if (showEntitiesPanel.value || showRehydratePanel.value) return 'upload'
    const job = currentJob.value as { status?: string } | null
    if (!job) return 'upload'
    if (showConclusionView.value) return 'confirm-detail'
    const st = job.status || ''
    if (st === 'done' || st === 'archived') return 'done'
    if (st === 'finishing' || st === 'running') return 'finishing'
    if (st === 'semantic_scanning') return 'semantic-scanning'
    if (programScanRunning.value) return 'program-running'
    if (st === 'program_review') return 'program-review'
    if (st === 'semantic_review') return 'semantic-review'
    if (
      (st === 'scanned' || st === 're_scanning' || st === 'confirmed') &&
      !semanticStageEntered.value
    ) {
      return 'entity-scanned'
    }
    if (st === 'scanned' || st === 'confirmed') return 'semantic-idle'
    if (st === 'scanning' || st === 'queued' || reScanning.value) return 'scanning'
    const sp = scanProgress.value
    if (sp && sp.phase !== 'error' && sp.phase !== 'done') return 'scanning'
    if (st === 'draft') {
      if (!markdownStageEntered.value) return 'markdown-preview'
      return 'scan-draft'
    }
    return 'upload'
  }

  function entityScanMode(): 'scanning' | 'ready' | 're_scanning' {
    const st = (currentJob.value as { status?: string } | null)?.status || ''
    const sp = scanProgress.value
    if (
      reScanning.value ||
      scanSession.value === 'rescan' ||
      st === 're_scanning' ||
      sp?.phase === 're_discover'
    ) {
      return 're_scanning'
    }
    if (st === 'scanning' || st === 'queued') return 'scanning'
    if (
      sp &&
      sp.phase !== 'error' &&
      sp.phase !== 'done' &&
      !String(sp.phase).startsWith('semantic')
    ) {
      return 'scanning'
    }
    return 'ready'
  }

  function enterSemanticStage() {
    semanticStageEntered.value = true
  }

  function enterMarkdownStage() {
    markdownStageEntered.value = true
  }

  function wizardStep():
    | 'upload'
    | 'convert'
    | 'entity_scan'
    | 'semantic'
    | 'program_scan'
    | 'confirm'
    | 'finish' {
    const phase = wizardPhase()
    if (phase === 'upload') return 'upload'
    if (phase === 'markdown-preview' || phase === 'scan-draft') return 'convert'
    if (phase === 'scanning' || phase === 'entity-scanned') return 'entity_scan'
    if (phase === 'semantic-idle' || phase === 'semantic-scanning' || phase === 'semantic-review') {
      return 'semantic'
    }
    if (phase === 'program-running' || phase === 'program-review') return 'program_scan'
    if (phase === 'confirm-detail') return 'confirm'
    return 'finish'
  }

  function openConclusionView() {
    if (showEntitiesPanel.value || showRehydratePanel.value || suppressAutoConclusion.value) return
    showConclusionView.value = true
    showEntitiesPanel.value = false
    showRehydratePanel.value = false
  }

  function closeConclusionView() {
    showConclusionView.value = false
  }

  function openEntitiesPanel() {
    suppressAutoConclusion.value = true
    showEntitiesPanel.value = true
    showConclusionView.value = false
    showRehydratePanel.value = false
  }

  function closeEntitiesPanel() {
    showEntitiesPanel.value = false
    suppressAutoConclusion.value = false
  }

  function openRehydratePanel() {
    suppressAutoConclusion.value = true
    showRehydratePanel.value = true
    showEntitiesPanel.value = false
    showConclusionView.value = false
  }

  function closeRehydratePanel() {
    showRehydratePanel.value = false
    suppressAutoConclusion.value = false
  }

  async function rehydrate(jobId: number, text: string) {
    return readJson<{ text: string; resolved: string[]; unresolved: string[] }>(
      await deidFetch(`${API}/jobs/${jobId}/rehydrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }),
    )
  }

  async function fetchJobSnapshot(jobId: number) {
    return readJson<Record<string, unknown>>(await deidFetch(`${API}/jobs/${jobId}`))
  }

  async function loadEntitiesSnapshot(jobId: number) {
    return readJson<Record<string, unknown>[]>(await deidFetch(`${API}/jobs/${jobId}/entities`))
  }

  async function fetchPreviewSnapshot(jobId: number) {
    const r = await deidFetch(`${API}/jobs/${jobId}/preview`, { method: 'POST' })
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
      const r = await deidFetch(`${API}/worker/status`)
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
      const r = await deidFetch(`${API}/jobs`)
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
      const r = await deidFetch(`${API}/queue/status`)
      if (r.ok) {
        queueStatus.value = await readJson(r)
      }
    } catch {
      queueStatus.value = { current_job_id: null, waiting_job_ids: [], waiting_count: 0 }
    }
  }

  async function fetchJob(jobId: number) {
    const job = await readJson<Record<string, unknown>>(await deidFetch(`${API}/jobs/${jobId}`))
    currentJob.value = job
    const progress = job.progress as typeof scanProgress.value
    if (progress) scanProgress.value = progress
    return job
  }

  async function fetchWorkerCalls(jobId: number) {
    const data = await readJson<{ calls?: Record<string, unknown>[] }>(
      await deidFetch(`${API}/jobs/${jobId}/worker-calls`),
    )
    workerCalls.value = data.calls ?? []
    return workerCalls.value
  }

  async function loadEntities(jobId: number) {
    const r = await deidFetch(`${API}/jobs/${jobId}/entities`)
    entities.value = await readJson(r)
    return entities.value
  }

  async function restoreCurrentJob() {
    const incomplete = jobs.value.find(
      (j) => !['done', 'archived'].includes((j as { status: string }).status),
    ) as { id: number; status: string } | undefined
    if (!incomplete) return

    await fetchJob(incomplete.id)
    const status = incomplete.status

    if (status === 'semantic_review' || status === 'semantic_scanning') {
      await loadEntities(incomplete.id)
      await fetchSemanticRisks(incomplete.id)
    } else if (status === 'program_review') {
      programStageEntered.value = true
      await loadEntities(incomplete.id)
      await fetchProgramScan(incomplete.id)
    } else if (status === 'scanned' || status === 'confirmed') {
      await loadEntities(incomplete.id)
      const ack = (currentJob.value as { program_scan_ack_at?: string | null } | null)
        ?.program_scan_ack_at
      if (ack) {
        openConclusionView()
      }
    } else if (status === 'scanning' || status === 'queued') {
      await pollScanUntilDone(incomplete.id)
    } else if (status === 'draft') {
      markdownStageEntered.value = false
      await fetchSourceMarkdown(incomplete.id)
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
    showRehydratePanel.value = false
    const id = job.id as number
    const status = job.status as string

    if (status === 'done' || status === 'archived') {
      await fetchJob(id)
      await loadEntities(id)
      if (status === 'done') {
        await fetchPreview(id)
      }
      return
    }
    if (status === 'semantic_review' || status === 'semantic_scanning') {
      await fetchJob(id)
      await loadEntities(id)
      await fetchSemanticRisks(id)
      return
    }
    if (status === 'program_review') {
      programStageEntered.value = true
      await fetchJob(id)
      await loadEntities(id)
      await fetchProgramScan(id)
      return
    }
    if (status === 'scanned' || status === 'confirmed') {
      await fetchJob(id)
      await loadEntities(id)
      const ack = (currentJob.value as { program_scan_ack_at?: string | null } | null)
        ?.program_scan_ack_at
      if (ack) {
        openConclusionView()
      }
      return
    }
    if (status === 'scanning' || status === 'queued') {
      await pollScanUntilDone(id)
      return
    }
    if (status === 'draft') {
      markdownStageEntered.value = false
      await fetchSourceMarkdown(id)
    }
    entities.value = []
  }

  async function fetchSourceMarkdown(jobId: number) {
    sourceMarkdownLoading.value = true
    try {
      sourceMarkdown.value = await readJson<SourceMarkdownPayload>(
        await deidFetch(`${API}/jobs/${jobId}/source-markdown`),
      )
      return sourceMarkdown.value
    } finally {
      sourceMarkdownLoading.value = false
    }
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
    showRehydratePanel.value = false
    entityDirty.value = false
    markdownStageEntered.value = false
    sourceMarkdown.value = null
    programStageEntered.value = false
    programScanRunning.value = false
    programScan.value = null
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
      const r = await deidFetch(`${API}/jobs`, { method: 'POST', body: fd })
      currentJob.value = await readJson(r)
      entityDirty.value = false
      showConclusionView.value = false
      showEntitiesPanel.value = false
      showRehydratePanel.value = false
      await fetchJobs()
      await fetchSourceMarkdown((currentJob.value as { id: number }).id)
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
    semanticStageEntered.value = false
    scanSnapshotEntities.value = []
    scanProgress.value = { phase: 'starting', percent: 0, message: '正在提交扫描…' }
    connectScanStream(jobId)
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 'scanning' }
    }
  }

  async function startScan(jobId: number) {
    const data = await readJson<{ status: string; queue_position?: number }>(
      await deidFetch(`${API}/jobs/${jobId}/start`, { method: 'POST' }),
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
          scanSnapshotEntities.value = []
          if (!needsConclusionStep(job)) {
            await autoRunAfterScan(jobId)
          }
          return entities.value
        }
        if (status === 'draft' && progress?.phase === 'error') {
          if (progress.fallback === 'manual') {
            await loadEntities(jobId)
            disconnectScanStream()
            scanProgress.value = null
            if (!needsConclusionStep(job)) {
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
    const r = await deidFetch(`${API}/jobs/${jobId}/preview`, { method: 'POST' })
    if (r.ok) {
      const data = await readJson<{ previews?: { before: string; after: string }[] }>(r)
      previews.value = data.previews ?? []
    }
  }

  async function addManual(jobId: number, body: Record<string, unknown>) {
    entities.value = await readJson(
      await deidFetch(`${API}/jobs/${jobId}/entities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
    entityDirty.value = true
  }

  async function deleteEntity(jobId: number, entityId: number) {
    entities.value = await readJson(
      await deidFetch(`${API}/jobs/${jobId}/entities/${entityId}`, { method: 'DELETE' }),
    )
    entityDirty.value = true
  }

  async function patchEntity(jobId: number, entityId: number, body: Record<string, unknown>) {
    entities.value = await readJson(
      await deidFetch(`${API}/jobs/${jobId}/entities/${entityId}`, {
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
    showRehydratePanel.value = false
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 'finishing' }
    }
    try {
      const r = await deidFetch(`${API}/jobs/${jobId}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_ids: entityIds,
          remember_ids: rememberIds,
          semantic_selection: semanticSelection.value,
        }),
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
      const r = await deidFetch(`${API}/jobs/${jobId}/rerun`, {
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
    await readJson(await deidFetch(`${API}/jobs/${jobId}`, { method: 'DELETE' }))
    if ((currentJob.value as { id?: number } | null)?.id === jobId) {
      await newTask()
    }
    await fetchJobs()
  }

  function exportUrl(jobId: number, overrideAck: boolean, reason?: string) {
    const q = new URLSearchParams({ override_ack: String(overrideAck) })
    if (reason) q.set('override_reason', reason)
    const token = getDeidAccessToken()
    if (token) q.set('access_token', token)
    return `${API}/jobs/${jobId}/export?${q}`
  }

  function patchSemanticRisk(riskId: string, patch: Record<string, unknown>) {
    semanticRisks.value = semanticRisks.value.map((r) =>
      r.risk_id === riskId ? { ...r, ...patch } : r,
    )
  }

  function saveSemanticSelection() {
    semanticSelection.value = semanticRisks.value.map((r) => ({
      risk_id: r.risk_id,
      enabled: r.enabled !== false,
      original: r.original,
      rewritten: (r.rewritten as string) || (r.suggested_rewrite as string) || undefined,
    }))
  }

  function proceedToProgramScan() {
    saveSemanticSelection()
    enterSemanticStage()
    programStageEntered.value = true
    const id = (currentJob.value as { id?: number } | null)?.id
    if (id) void runProgramScan(id)
  }

  function proceedToConfirm() {
    const ack = (currentJob.value as { program_scan_ack_at?: string | null } | null)
      ?.program_scan_ack_at
    if (!ack) {
      proceedToProgramScan()
      return
    }
    saveSemanticSelection()
    openConclusionView()
  }

  async function fetchProgramScan(jobId: number) {
    const data = await readJson<ProgramScanPayload & { entities?: Record<string, unknown>[] }>(
      await deidFetch(`${API}/jobs/${jobId}/program-scan`),
    )
    programScan.value = data
    if (data.entities) entities.value = data.entities
    return data
  }

  async function runProgramScan(jobId: number) {
    programScanRunning.value = true
    error.value = null
    try {
      const data = await readJson<
        ProgramScanPayload & { status?: string; entities?: Record<string, unknown>[] }
      >(await deidFetch(`${API}/jobs/${jobId}/program-scan/run`, { method: 'POST' }))
      programScan.value = data
      if (data.entities) entities.value = data.entities
      if (currentJob.value) {
        currentJob.value = {
          ...currentJob.value,
          status: data.status || 'program_review',
          program_scan_ack_at: null,
        }
      }
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : '程序扫描失败'
      throw e
    } finally {
      programScanRunning.value = false
    }
  }

  async function revertProgramScanChange(jobId: number, changeId: string) {
    const data = await readJson<ProgramScanPayload & { entities?: Record<string, unknown>[] }>(
      await deidFetch(`${API}/jobs/${jobId}/program-scan/revert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ change_id: changeId }),
      }),
    )
    programScan.value = data
    if (data.entities) entities.value = data.entities
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, program_scan_ack_at: null }
    }
    return data
  }

  async function confirmProgramScan(jobId: number) {
    const data = await readJson<{ program_scan_ack_at?: string | null; status?: string }>(
      await deidFetch(`${API}/jobs/${jobId}/program-scan/confirm`, { method: 'POST' }),
    )
    if (currentJob.value) {
      currentJob.value = {
        ...currentJob.value,
        program_scan_ack_at: data.program_scan_ack_at,
        status: data.status || currentJob.value.status,
      }
    }
    openConclusionView()
    return data
  }

  async function fetchSemanticRisks(jobId: number) {
    const data = await readJson<{ risks: Record<string, unknown>[] }>(
      await deidFetch(`${API}/jobs/${jobId}/semantic/risks`),
    )
    semanticRisks.value = data.risks ?? []
    return semanticRisks.value
  }

  async function semanticStart(jobId: number) {
    semanticLoading.value = true
    error.value = null
    scanSession.value = 'semantic'
    resetScanLive()
    scanProgress.value = { phase: 'semantic_detect', percent: 8, message: '正在提交语义扫描…' }
    connectScanStream(jobId, { fresh: true, reset: false })
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 'semantic_scanning' }
    }
    try {
      const data = await readJson<{ risks: Record<string, unknown>[]; status: string }>(
        await deidFetch(`${API}/jobs/${jobId}/semantic/start`, { method: 'POST' }),
      )
      semanticRisks.value = data.risks ?? []
      if (currentJob.value) {
        currentJob.value = { ...currentJob.value, status: data.status }
      }
      const count = data.risks?.length ?? 0
      if (String(scanProgress.value?.phase || '') !== 'semantic_review') {
        scanProgress.value = {
          phase: 'semantic_review',
          percent: 100,
          message: count > 0 ? `发现 ${count} 条语义风险` : '未发现需改写的语义指纹',
        }
      }
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : '语义扫描失败'
      scanProgress.value = {
        phase: 'error',
        percent: scanProgress.value?.percent ?? 0,
        message: error.value,
      }
      throw e
    } finally {
      semanticLoading.value = false
      disconnectScanStream()
      window.setTimeout(() => {
        scanSession.value = null
        if (String(scanProgress.value?.phase || '').startsWith('semantic')) {
          scanProgress.value = null
        }
      }, 3500)
    }
  }

  async function semanticSuggestAll(jobId: number) {
    semanticLoading.value = true
    error.value = null
    scanSession.value = 'semantic'
    resetScanLive()
    scanProgress.value = { phase: 'semantic_suggest', percent: 10, message: '正在生成改写…' }
    connectScanStream(jobId, { fresh: true, reset: false })
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 'semantic_scanning' }
    }
    try {
      const data = await readJson<{ risks: Record<string, unknown>[]; status: string }>(
        await deidFetch(`${API}/jobs/${jobId}/semantic/suggest-all`, { method: 'POST' }),
      )
      semanticRisks.value = data.risks ?? semanticRisks.value
      if (currentJob.value) {
        currentJob.value = { ...currentJob.value, status: data.status }
      }
      const filled = (data.risks ?? []).filter(
        (r) => (r as { suggested_rewrite?: string; rewritten?: string }).suggested_rewrite
          || (r as { rewritten?: string }).rewritten,
      ).length
      scanProgress.value = {
        phase: 'semantic_review',
        percent: 100,
        message: `已生成 ${filled} 条改写建议`,
      }
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : '改写生成失败'
      scanProgress.value = {
        phase: 'error',
        percent: scanProgress.value?.percent ?? 0,
        message: error.value,
      }
      throw e
    } finally {
      semanticLoading.value = false
      disconnectScanStream()
      window.setTimeout(() => {
        scanSession.value = null
        if (String(scanProgress.value?.phase || '').startsWith('semantic')) {
          scanProgress.value = null
        }
      }, 2500)
    }
  }

  async function semanticSkip(jobId: number) {
    const data = await readJson<{ semantic_skipped: boolean }>(
      await deidFetch(`${API}/jobs/${jobId}/semantic/skip`, { method: 'POST' }),
    )
    if (currentJob.value) {
      currentJob.value = {
        ...currentJob.value,
        semantic_skipped: data.semantic_skipped,
      }
    }
    semanticRisks.value = []
    semanticSelection.value = []
    return data
  }

  async function semanticSuggest(jobId: number, riskId: string) {
    const data = await readJson<{ risk_id: string; suggested_rewrite: string | null }>(
      await deidFetch(`${API}/jobs/${jobId}/semantic/suggest/${encodeURIComponent(riskId)}`, {
        method: 'POST',
      }),
    )
    if (data.suggested_rewrite) {
      patchSemanticRisk(riskId, { suggested_rewrite: data.suggested_rewrite })
    }
    return data
  }

  async function reRunScan(jobId: number) {
    reScanning.value = true
    error.value = null
    scanSession.value = 'rescan'
    rescanGateOpen.value = false
    resetScanLive()
    scanProgress.value = { phase: 're_discover', percent: 5, message: '正在提交再识别…' }
    connectScanStream(jobId, { fresh: true, reset: false })
    if (currentJob.value) {
      currentJob.value = { ...currentJob.value, status: 're_scanning' }
    }
    try {
      const data = await readJson<{
        entities: Record<string, unknown>[]
        re_run_count: number
        delta: number
        no_change: boolean
        experience_eligible: boolean
      }>(await deidFetch(`${API}/jobs/${jobId}/scan/re-run`, { method: 'POST' }))
      entities.value = data.entities ?? entities.value
      lastRescanResult.value = {
        run: data.re_run_count,
        delta: data.delta,
        noChange: data.no_change,
      }
      if (currentJob.value) {
        currentJob.value = {
          ...currentJob.value,
          status: 'scanned',
          re_run_count: data.re_run_count,
          experience_eligible: data.experience_eligible,
        }
      }
      if (scanProgress.value?.phase !== 'done') {
        scanProgress.value = {
          phase: 'done',
          percent: 100,
          message: data.no_change
            ? `第 ${data.re_run_count} 次再识别完成，本轮无新增`
            : `第 ${data.re_run_count} 次再识别完成，新增 ${data.delta} 个`,
        }
      }
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : '再识别失败'
      scanProgress.value = {
        phase: 'error',
        percent: scanProgress.value?.percent ?? 0,
        message: error.value,
      }
      throw e
    } finally {
      reScanning.value = false
      disconnectScanStream()
      window.setTimeout(() => {
        scanSession.value = null
        rescanGateOpen.value = false
        if (scanProgress.value?.phase === 'done' || scanProgress.value?.phase === 'error') {
          scanProgress.value = null
        }
      }, 4500)
    }
  }

  async function generateExperience(jobId: number) {
    return readJson<{ text: string | null; message?: string }>(
      await deidFetch(`${API}/jobs/${jobId}/scan/experience`, { method: 'POST' }),
    )
  }

  async function confirmExperience(jobId: number, text: string) {
    return readJson(
      await deidFetch(`${API}/jobs/${jobId}/scan/experience/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }),
    )
  }

  async function fetchGlobalExperience() {
    globalExperience.value = await readJson<Record<string, unknown>[]>(
      await deidFetch(`${API}/settings/global-experience`),
    )
    return globalExperience.value
  }

  async function createGlobalExperience(text: string) {
    const row = await readJson<Record<string, unknown>>(
      await deidFetch(`${API}/settings/global-experience`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }),
    )
    await fetchGlobalExperience()
    return row
  }

  async function updateGlobalExperience(id: number, text: string) {
    const row = await readJson<Record<string, unknown>>(
      await deidFetch(`${API}/settings/global-experience/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }),
    )
    await fetchGlobalExperience()
    return row
  }

  async function deleteGlobalExperience(id: number) {
    await readJson(await deidFetch(`${API}/settings/global-experience/${id}`, { method: 'DELETE' }))
    await fetchGlobalExperience()
  }

  async function fetchLibrary(q?: string) {
    const url = q ? `${API}/entities?q=${encodeURIComponent(q)}` : `${API}/entities`
    libraryEntities.value = await readJson(await deidFetch(url))
  }

  async function fetchEntityTypes() {
    try {
      const data = await readJson<{ code: string; label: string; placeholder_prefix: string }[]>(
        await deidFetch(`${API}/entity-types`),
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
      await deidFetch(`${API}/entity-types`, {
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
      await deidFetch(`${API}/entity-types/${encodeURIComponent(code)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
    await fetchEntityTypes()
  }

  async function deleteEntityType(code: string) {
    await readJson(
      await deidFetch(`${API}/entity-types/${encodeURIComponent(code)}`, { method: 'DELETE' }),
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
    showRehydratePanel,
    suppressAutoConclusion,
    wizardPhase,
    wizardStep,
    openConclusionView,
    closeConclusionView,
    openEntitiesPanel,
    closeEntitiesPanel,
    openRehydratePanel,
    closeRehydratePanel,
    rehydrate,
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
    semanticRisks,
    semanticLoading,
    semanticSelection,
    scanSnapshotEntities,
    semanticStageEntered,
    programStageEntered,
    programScanRunning,
    programScan,
    markdownStageEntered,
    sourceMarkdown,
    sourceMarkdownLoading,
    enterMarkdownStage,
    fetchSourceMarkdown,
    reScanning,
    scanSession,
    lastRescanResult,
    globalExperience,
    entityScanMode,
    enterSemanticStage,
    patchSemanticRisk,
    saveSemanticSelection,
    proceedToConfirm,
    proceedToProgramScan,
    fetchProgramScan,
    runProgramScan,
    revertProgramScanChange,
    confirmProgramScan,
    fetchSemanticRisks,
    semanticStart,
    semanticSuggestAll,
    semanticSkip,
    semanticSuggest,
    reRunScan,
    generateExperience,
    confirmExperience,
    fetchGlobalExperience,
    createGlobalExperience,
    updateGlobalExperience,
    deleteGlobalExperience,
    workerCalls,
    fetchWorkerCalls,
  }
})
