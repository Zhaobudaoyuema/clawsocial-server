<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidBadge from './DeidBadge.vue'
import DeidEmptyState from './DeidEmptyState.vue'

const store = useDeidStore()

const selectedJobId = ref<number | null>(null)
const inputText = ref('')
const resultText = ref('')
const resolved = ref<string[]>([])
const unresolved = ref<string[]>([])
const busy = ref(false)
const localError = ref<string | null>(null)
const copied = ref(false)

const doneJobs = computed(() =>
  store.jobs.filter((j) =>
    ['done', 'archived'].includes((j as { status?: string }).status || ''),
  ),
)

const eligibleJobs = computed(() =>
  store.jobs.filter((j) => (j as { rehydrate_available?: boolean }).rehydrate_available),
)

const emptyTitle = computed(() =>
  doneJobs.value.length && !eligibleJobs.value.length
    ? '已完成任务暂无映射'
    : '暂无可回显任务',
)

const emptyHint = computed(() => {
  if (doneJobs.value.length && !eligibleJobs.value.length) {
    return '请刷新页面或重新脱敏一次以生成占位符映射；完成后 90 天内可回显'
  }
  return '完成脱敏后 90 天内可使用映射还原结论；文件清理后仍可回显'
})

const selectedJob = computed(() =>
  eligibleJobs.value.find((j) => (j as { id: number }).id === selectedJobId.value) ?? null,
)

const canSubmit = computed(
  () => !!selectedJobId.value && !!inputText.value.trim() && !busy.value,
)

const hasResult = computed(() => !!resultText.value)
const inputChars = computed(() => inputText.value.length)

function fmtTime(iso: string | null | undefined) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

function shortFilename(name: string) {
  if (name.length <= 42) return name
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : ''
  const stem = ext ? name.slice(0, name.length - ext.length) : name
  return `${stem.slice(0, 34)}…${ext}`
}

onMounted(async () => {
  await store.fetchJobs()
  const first = eligibleJobs.value[0] as { id?: number } | undefined
  if (first?.id) selectedJobId.value = first.id
})

async function doRehydrate() {
  if (!canSubmit.value || !selectedJobId.value) return
  busy.value = true
  localError.value = null
  copied.value = false
  try {
    const data = await store.rehydrate(selectedJobId.value, inputText.value)
    resultText.value = data.text
    resolved.value = data.resolved
    unresolved.value = data.unresolved
  } catch (e) {
    localError.value = e instanceof Error ? e.message : '还原失败'
    resultText.value = ''
    resolved.value = []
    unresolved.value = []
  } finally {
    busy.value = false
  }
}

async function copyResult() {
  if (!resultText.value) return
  try {
    await navigator.clipboard.writeText(resultText.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    localError.value = '复制失败，请手动选择文本'
  }
}

function clearInput() {
  inputText.value = ''
  resultText.value = ''
  resolved.value = []
  unresolved.value = []
  localError.value = null
}
</script>

<template>
  <div class="rehydrate">
    <DeidEmptyState
      v-if="!eligibleJobs.length"
      :title="emptyTitle"
      :hint="emptyHint"
      cta-label="新建任务"
      @action="store.closeRehydratePanel(); store.newTask()"
    />

    <div v-else class="rehydrate-card deid-panel">
      <header class="page-head">
        <div class="page-head-text">
          <h2 class="title">结论回显</h2>
          <p class="subtitle">
            支持 <code>[公司_1]</code> 或 <code>公司_1</code> 等占位符，还原为原文实体名
          </p>
        </div>
      </header>

      <div class="job-bar">
        <label class="job-label" for="rehydrate-job">来源任务</label>
        <div class="job-controls">
          <select id="rehydrate-job" v-model="selectedJobId" class="job-select deid-input">
            <option
              v-for="job in eligibleJobs"
              :key="(job as { id: number }).id"
              :value="(job as { id: number }).id"
            >
              {{ shortFilename((job as { original_filename: string }).original_filename) }}
              · {{ fmtTime((job as { completed_at?: string }).completed_at) }}
              {{ (job as { status: string }).status === 'archived' ? '· 已归档' : '' }}
            </option>
          </select>
          <DeidBadge
            v-if="selectedJob && (selectedJob as { status: string }).status === 'archived'"
            variant="scanned"
            label="已归档·可回显"
          />
          <span v-else-if="selectedJob" class="expiry-chip">
            映射保留至 {{ fmtTime((selectedJob as { mapping_expires_at?: string }).mapping_expires_at) }}
          </span>
        </div>
      </div>

      <div class="workspace">
        <section class="pane pane--input">
          <div class="pane-head">
            <div>
              <h3 class="pane-title">脱敏结论</h3>
              <p class="pane-desc">粘贴含占位符的外部 LLM 分析结论</p>
            </div>
            <span v-if="inputChars" class="pane-meta">{{ inputChars }} 字</span>
          </div>
          <textarea
            v-model="inputText"
            class="pane-editor"
            placeholder="例如：报告认为 [公司_1]（或 公司_1）在 姓名_2 负责的项目中存在合规风险…"
            spellcheck="false"
          />
        </section>

        <div class="bridge" aria-hidden="true">
          <span class="bridge-arrow">→</span>
        </div>

        <section class="pane pane--output" :class="{ 'pane--empty': !hasResult }">
          <div class="pane-head">
            <div>
              <h3 class="pane-title">还原结果</h3>
              <p class="pane-desc">本地映射替换后的原文实体名</p>
            </div>
            <div v-if="hasResult" class="pane-actions">
              <span v-if="resolved.length" class="stat-chip stat-chip--ok">
                {{ resolved.length }} 已还原
              </span>
              <span v-if="unresolved.length" class="stat-chip stat-chip--warn">
                {{ unresolved.length }} 未识别
              </span>
              <button type="button" class="deid-btn deid-btn--ghost copy-btn" @click="copyResult">
                {{ copied ? '已复制' : '复制' }}
              </button>
            </div>
          </div>

          <div v-if="hasResult" class="pane-body">
            <pre class="result-text">{{ resultText }}</pre>
            <div v-if="unresolved.length" class="unresolved">
              <p class="unresolved-label">未识别占位符</p>
              <div class="unresolved-tags">
                <code v-for="ph in unresolved" :key="ph" class="ph-tag">{{ ph }}</code>
              </div>
            </div>
          </div>
          <div v-else class="pane-placeholder">
            <span class="placeholder-icon" aria-hidden="true">⎘</span>
            <p>点击底部「还原为原文」后，结果将显示在这里</p>
          </div>
        </section>
      </div>

      <footer class="action-bar">
        <p class="security-note">
          <span class="security-dot" aria-hidden="true" />
          还原结果含敏感信息，请勿外传或上传至公共大模型
        </p>
        <div class="action-group">
          <button
            type="button"
            class="deid-btn"
            :disabled="!inputText.trim() || busy"
            @click="clearInput"
          >
            清空
          </button>
          <button
            type="button"
            class="deid-btn deid-btn--primary action-primary"
            :disabled="!canSubmit"
            @click="doRehydrate"
          >
            <span v-if="busy" class="deid-spinner" aria-hidden="true" />
            {{ busy ? '还原中…' : '还原为原文' }}
          </button>
        </div>
      </footer>

      <p v-if="localError" class="err" role="alert">{{ localError }}</p>
    </div>
  </div>
</template>

<style scoped>
.rehydrate {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
}

.rehydrate-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 0 !important;
  overflow: hidden;
  box-shadow: var(--deid-shadow-sm);
}

.page-head {
  flex-shrink: 0;
  padding: 1.35rem 1.5rem 0;
}

.page-head-text {
  min-width: 0;
}

.title {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--deid-ink);
}

.subtitle {
  margin: 0.4rem 0 0;
  font-size: 0.875rem;
  color: var(--deid-ink-muted);
  line-height: 1.5;
  max-width: 36rem;
}

.subtitle code {
  font-family: var(--deid-font-mono);
  font-size: 0.8125rem;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
}

.job-bar {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  flex-shrink: 0;
  margin: 1.1rem 1.5rem 0;
  padding: 0.75rem 1rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
}

.job-label {
  flex-shrink: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--deid-ink-secondary);
}

.job-controls {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex: 1;
  min-width: 0;
}

.job-select {
  flex: 1;
  min-width: 0;
  max-width: 480px;
  font-size: 0.875rem;
}

.expiry-chip {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
  white-space: nowrap;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
}

.workspace {
  flex: 1;
  min-height: 0;
  max-height: min(520px, calc(100vh - 340px));
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0.85rem;
  align-items: stretch;
  margin: 1.15rem 1.5rem 0;
}

.pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-sm);
  background: var(--deid-surface);
  overflow: hidden;
}

.pane--output.pane--empty {
  border-style: dashed;
  background: var(--deid-rail-bg);
}

.pane-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.8rem 1rem;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface);
  flex-shrink: 0;
}

.pane-title {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
}

.pane-desc {
  margin: 0.2rem 0 0;
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
}

.pane-meta {
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
  font-variant-numeric: tabular-nums;
}

.pane-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.stat-chip {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
}

.stat-chip--ok {
  background: var(--deid-success-bg);
  color: var(--deid-success);
}

.stat-chip--warn {
  background: var(--deid-warning-bg);
  color: var(--deid-warning);
}

.copy-btn {
  font-size: 0.8125rem;
  padding: 0.3rem 0.65rem;
}

.pane-editor {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: none;
  resize: none;
  padding: 1rem 1.1rem;
  font-family: var(--deid-font);
  font-size: 0.9375rem;
  line-height: 1.65;
  color: var(--deid-ink);
  background: transparent;
  outline: none;
}

.pane-editor::placeholder {
  color: var(--deid-ink-muted);
  opacity: 0.75;
}

.pane-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 1rem 1.1rem;
}

.result-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--deid-font);
  font-size: 0.9375rem;
  line-height: 1.65;
}

.pane-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.65rem;
  padding: 2rem 1.5rem;
  text-align: center;
  color: var(--deid-ink-muted);
  font-size: 0.875rem;
}

.placeholder-icon {
  font-size: 1.75rem;
  opacity: 0.35;
}

.bridge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  align-self: center;
}

.bridge-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 999px;
  background: var(--deid-primary-soft);
  color: var(--deid-primary);
  font-size: 1rem;
  font-weight: 600;
}

.unresolved {
  margin-top: 1rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--deid-border);
}

.unresolved-label {
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--deid-ink-secondary);
}

.unresolved-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.ph-tag {
  font-family: var(--deid-font-mono);
  font-size: 0.75rem;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  background: var(--deid-warning-bg);
  color: var(--deid-warning);
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-shrink: 0;
  margin-top: auto;
  padding: 1rem 1.5rem 1.25rem;
  border-top: 1px solid var(--deid-border);
  background: var(--deid-surface);
}

.security-note {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0;
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
}

.security-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--deid-warning);
  flex-shrink: 0;
}

.action-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.action-primary {
  min-width: 9.5rem;
  padding: 0.6rem 1.35rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
}

.err {
  margin: 0 1.5rem 1rem;
  padding: 0.55rem 0.75rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-danger-bg);
  color: var(--deid-danger);
  font-size: 0.8125rem;
}

@media (max-width: 900px) {
  .job-bar {
    flex-direction: column;
    align-items: stretch;
    margin-inline: 1rem;
  }

  .job-controls {
    flex-wrap: wrap;
  }

  .job-select {
    max-width: none;
  }

  .workspace {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto;
    margin-inline: 1rem;
    max-height: none;
    min-height: 380px;
  }

  .bridge {
    width: auto;
    padding: 0.15rem 0;
  }

  .bridge-arrow {
    transform: rotate(90deg);
  }

  .page-head {
    padding-inline: 1rem;
  }

  .action-bar {
    flex-direction: column-reverse;
    align-items: stretch;
    padding-inline: 1rem;
  }

  .action-group .deid-btn {
    flex: 1;
  }

  .pane-editor,
  .pane-body {
    min-height: 160px;
  }
}
</style>
