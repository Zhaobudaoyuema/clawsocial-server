<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidBadge from './DeidBadge.vue'
import DeidEmptyState from './DeidEmptyState.vue'
import DeidStepper from './DeidStepper.vue'
import DeidEntityTypeSelect from './DeidEntityTypeSelect.vue'

const store = useDeidStore()
const emit = defineEmits<{ confirmed: [] }>()

const selected = ref<Set<number>>(new Set())
const remember = ref<Set<number>>(new Set())
const adding = ref(false)
const search = ref('')
const sortByHits = ref(true)
const showEntities = ref(false)
const showManual = ref(false)
const manualName = ref('')
const manualType = ref('company')

const jobId = computed(() => (store.currentJob as { id?: number } | null)?.id)
const jobStatus = computed(() => (store.currentJob as { status?: string } | null)?.status || '')
const isDoneJob = computed(() => jobStatus.value === 'done')
const canConfirm = computed(() => selected.value.size > 0 && !store.loading)
const selectedCount = computed(() => selected.value.size)
const totalCount = computed(() => store.entities.length)
const jobFilename = computed(
  () => (store.currentJob as { original_filename?: string } | null)?.original_filename || '',
)

const allSelected = computed(() => {
  const ids = activeEntities.value.map((e) => entityId(e))
  return ids.length > 0 && ids.every((id) => selected.value.has(id))
})

const confirmLabel = computed(() => {
  if (store.loading) return '处理中…'
  return isDoneJob.value ? '重新脱敏' : '确认并脱敏'
})

const activeEntities = computed(() =>
  store.entities.filter((e) => !(e as { is_excluded?: boolean }).is_excluded),
)

const totalHits = computed(() =>
  activeEntities.value.reduce(
    (sum, e) => sum + ((e as { hit_count: number }).hit_count || 0),
    0,
  ),
)

const sourceCounts = computed(() => {
  const counts = { llm: 0, remembered: 0, manual: 0 }
  for (const e of activeEntities.value) {
    const src = (e as { source: string }).source
    if (src === 'llm') counts.llm++
    else if (src === 'remembered') counts.remembered++
    else if (src === 'manual') counts.manual++
  }
  return counts
})

const topNames = computed(() => {
  const names = [...activeEntities.value]
    .sort(
      (a, b) =>
        ((b as { hit_count: number }).hit_count || 0) -
        ((a as { hit_count: number }).hit_count || 0),
    )
    .slice(0, 3)
    .map((e) => entityName(e))
  if (!names.length) return ''
  const more = Math.max(0, totalCount.value - names.length)
  return more > 0 ? `${names.join('、')} 等` : names.join('、')
})

const filteredEntities = computed(() => {
  const q = search.value.trim().toLowerCase()
  let list = activeEntities.value
  if (q) {
    list = list.filter((e) => entityName(e).toLowerCase().includes(q))
  }
  if (sortByHits.value) {
    list = [...list].sort(
      (a, b) =>
        ((b as { hit_count: number }).hit_count || 0) -
        ((a as { hit_count: number }).hit_count || 0),
    )
  }
  return list
})

watch(
  () => store.entities,
  (ents) => {
    selected.value = new Set(
      ents.filter((e) => !(e as { is_excluded?: boolean }).is_excluded).map((e) => (e as { id: number }).id),
    )
    remember.value = new Set(
      ents
        .filter((e) => {
          const src = (e as { source: string }).source
          return src === 'manual' || src === 'llm'
        })
        .map((e) => (e as { id: number }).id),
    )
  },
  { immediate: true },
)

function entityId(e: Record<string, unknown>) {
  return (e as { id: number }).id
}

function entityName(e: Record<string, unknown>) {
  return (e as { canonical_name: string }).canonical_name
}

function toggleSelect(id: number) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}

function selectAll() {
  selected.value = new Set(activeEntities.value.map((e) => entityId(e)))
}

function deselectAll() {
  selected.value = new Set()
}

function toggleRemember(id: number) {
  const s = new Set(remember.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  remember.value = s
}

function sourceBadge(e: Record<string, unknown>) {
  const src = (e as { source: string }).source
  const label = (e as { source_label?: string }).source_label
  if (src === 'manual') return { variant: 'manual' as const, label: label || '手动' }
  if (src === 'llm') return { variant: 'llm' as const, label: 'AI 识别' }
  if (src === 'remembered') return { variant: 'preset' as const, label: label || '已记住' }
  return { variant: 'preset' as const, label: label || src }
}

function showRememberControl(e: Record<string, unknown>) {
  return (e as { source: string }).source === 'manual'
}

async function addManual() {
  if (!jobId.value || !manualName.value.trim()) return
  adding.value = true
  try {
    await store.addManual(jobId.value, {
      canonical_name: manualName.value.trim(),
      entity_type: manualType.value,
      aliases: [manualName.value.trim()],
      save_to_library: true,
    })
    const last = store.entities[store.entities.length - 1] as { id: number }
    if (last?.id) {
      selected.value = new Set([...selected.value, last.id])
      remember.value = new Set([...remember.value, last.id])
    }
    manualName.value = ''
    showManual.value = false
    showEntities.value = true
  } finally {
    adding.value = false
  }
}

function dismissError() {
  store.error = null
}

async function onConfirm() {
  if (!jobId.value || !canConfirm.value) return
  try {
    if (isDoneJob.value) {
      await store.rerun(jobId.value, [...selected.value], [...remember.value])
    } else {
      await store.confirmAndRun(jobId.value, [...selected.value], [...remember.value])
    }
    store.error = null
    emit('confirmed')
  } catch {
    /* store.error 已设置 */
  }
}
</script>

<template>
  <div class="conclusion">
    <header class="conclusion-head">
      <DeidStepper class="conclusion-stepper" prominent current="confirm" />
    </header>

    <div v-if="store.error" class="run-error" role="alert">
      <span>脱敏未完成：{{ store.error }}</span>
      <button type="button" class="run-error__dismiss" @click="dismissError">知道了</button>
    </div>

    <main class="conclusion-main">
      <section class="approve-hero" aria-labelledby="approve-title">
        <div class="approve-hero__badge" aria-hidden="true">✓</div>
        <h2 id="approve-title" class="approve-hero__title">扫描完成，可开始脱敏</h2>
        <p v-if="jobFilename" class="approve-hero__file">{{ jobFilename }}</p>

        <DeidEmptyState
          v-if="!store.entities.length"
          class="approve-empty"
          title="未发现实体"
          hint="可手动添加实体后继续脱敏"
        />

        <template v-else>
          <p class="approve-hero__summary">
            发现 <strong>{{ totalCount }}</strong> 个敏感实体，共
            <strong>{{ totalHits }}</strong> 处命中 · 已选 <strong>{{ selectedCount }}</strong> 个
          </p>
          <p v-if="topNames" class="approve-hero__teaser">{{ topNames }}</p>

          <div class="approve-stats">
            <span v-if="sourceCounts.llm" class="approve-stat">AI 识别 {{ sourceCounts.llm }}</span>
            <span v-if="sourceCounts.remembered" class="approve-stat">已记住 {{ sourceCounts.remembered }}</span>
            <span v-if="sourceCounts.manual" class="approve-stat">手动 {{ sourceCounts.manual }}</span>
          </div>

          <button
            type="button"
            class="deid-btn deid-btn--primary approve-cta"
            :disabled="!canConfirm"
            @click="onConfirm"
          >
            {{ confirmLabel }}
          </button>
          <p class="approve-hero__trust">
            脱敏完成后将自动验证，确保敏感信息已清除，再提供下载
          </p>
        </template>
      </section>

      <section v-if="store.entities.length" class="entity-drawer">
        <button
          type="button"
          class="entity-drawer__toggle"
          :aria-expanded="showEntities"
          @click="showEntities = !showEntities"
        >
          <span>{{ showEntities ? '收起实体列表' : '查看或调整实体' }}</span>
          <span class="entity-drawer__count">{{ selectedCount }} / {{ totalCount }}</span>
          <span class="entity-drawer__chevron" :class="{ open: showEntities }" aria-hidden="true">›</span>
        </button>

        <div v-show="showEntities" class="entity-drawer__body">
          <p class="entity-drawer__hint">通常无需修改，默认已全部选中。仅在需要排除个别实体时展开调整。</p>
          <div class="data-toolbar">
            <input
              v-model="search"
              class="deid-input data-search"
              type="search"
              placeholder="搜索实体"
              aria-label="搜索实体"
            />
            <div class="data-toolbar__actions">
              <button v-if="!allSelected" type="button" class="bulk-link" @click="selectAll">全选</button>
              <button v-else type="button" class="bulk-link" @click="deselectAll">取消全选</button>
              <button type="button" class="bulk-link" @click="sortByHits = !sortByHits">
                {{ sortByHits ? '按命中 ↓' : '默认顺序' }}
              </button>
            </div>
          </div>

          <div class="table-wrap deid-panel entity-desktop">
            <table class="entity-table">
              <thead>
                <tr>
                  <th class="col-check" scope="col" />
                  <th scope="col">实体</th>
                  <th class="col-hits" scope="col">命中</th>
                  <th class="col-more" scope="col" />
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in filteredEntities" :key="entityId(e)">
                  <td class="col-check">
                    <input
                      type="checkbox"
                      class="entity-check"
                      :checked="selected.has(entityId(e))"
                      :aria-label="`选择实体 ${entityName(e)}`"
                      @change="toggleSelect(entityId(e))"
                    />
                  </td>
                  <td class="entity-cell">
                    <span class="entity-name" :title="entityName(e)">{{ entityName(e) }}</span>
                    <DeidBadge class="entity-badge" v-bind="sourceBadge(e)" />
                  </td>
                  <td class="col-hits deid-mono muted">{{ (e as { hit_count: number }).hit_count }}</td>
                  <td class="col-more">
                    <button
                      v-if="showRememberControl(e)"
                      type="button"
                      class="star"
                      :class="{ on: remember.has(entityId(e)) }"
                      title="记住此实体"
                      aria-label="记住此实体"
                      @click="toggleRemember(entityId(e))"
                    >
                      ☆
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="!filteredEntities.length" class="no-match">无匹配实体</p>
          </div>

          <ul class="entity-cards entity-mobile">
            <li v-for="e in filteredEntities" :key="entityId(e)" class="entity-card">
              <label class="entity-card__main">
                <input
                  type="checkbox"
                  class="entity-card__check"
                  :checked="selected.has(entityId(e))"
                  :aria-label="`选择实体 ${entityName(e)}`"
                  @change="toggleSelect(entityId(e))"
                />
                <span class="entity-card__name">{{ entityName(e) }}</span>
              </label>
              <div class="entity-card__meta">
                <DeidBadge v-bind="sourceBadge(e)" />
                <span class="muted deid-mono">命中 {{ (e as { hit_count: number }).hit_count }}</span>
              </div>
            </li>
          </ul>

          <div class="manual-add">
            <button
              v-if="!showManual"
              type="button"
              class="deid-btn deid-btn--ghost manual-toggle"
              @click="showManual = true"
            >
              + 手动添加实体
            </button>
            <div v-else class="manual-form">
              <input v-model="manualName" class="deid-input" placeholder="实体名称" @keyup.enter="addManual" />
              <DeidEntityTypeSelect v-model="manualType" width="100%" />
              <div class="manual-form__btns">
                <button type="button" class="deid-btn deid-btn--ghost" @click="showManual = false">取消</button>
                <button
                  type="button"
                  class="deid-btn deid-btn--primary"
                  :disabled="adding || !manualName.trim()"
                  @click="addManual"
                >
                  添加
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer class="conclusion-footer">
      <span class="conclusion-footer__count">已选 {{ selectedCount }} 个实体</span>
      <button
        type="button"
        class="deid-btn deid-btn--primary deid-btn--lg"
        :disabled="!canConfirm"
        @click="onConfirm"
      >
        {{ confirmLabel }}
      </button>
    </footer>
  </div>
</template>

<style scoped>
.conclusion {
  width: 100%;
  max-width: var(--deid-content-max);
  margin: 0 auto;
  padding: var(--deid-stage-pad);
  padding-bottom: 5rem;
}
.conclusion-head {
  flex-shrink: 0;
  margin-bottom: 1.25rem;
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-lg);
  box-shadow: var(--deid-shadow-sm);
  overflow: hidden;
}
.conclusion-stepper {
  border-bottom: none;
}
.conclusion-main {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: 0;
}
.approve-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 2rem 1.5rem 1.75rem;
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-lg);
  box-shadow: var(--deid-shadow-sm);
}
.approve-hero__badge {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--deid-success);
  background: var(--deid-success-bg);
  border: 2px solid var(--deid-success-border);
  margin-bottom: 1rem;
}
.approve-hero__title {
  margin: 0 0 0.5rem;
  font-size: 1.375rem;
  font-weight: 600;
  color: var(--deid-ink);
  line-height: 1.3;
}
.approve-hero__file {
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  max-width: 28rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.approve-hero__summary {
  margin: 0 0 0.35rem;
  font-size: 0.9375rem;
  color: var(--deid-ink-secondary);
  line-height: 1.5;
}
.approve-hero__summary strong {
  color: var(--deid-primary);
  font-weight: 600;
}
.approve-hero__teaser {
  margin: 0 0 1rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  max-width: 32rem;
  line-height: 1.45;
}
.approve-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.45rem;
  margin-bottom: 1.25rem;
}
.approve-stat {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--deid-ink-secondary);
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
}
.approve-cta {
  min-width: 220px;
  padding: 0.75rem 2rem;
  font-size: 1rem;
  font-weight: 600;
}
.approve-hero__trust {
  margin: 0.85rem 0 0;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  line-height: 1.45;
  max-width: 26rem;
}
.approve-empty {
  margin-top: 0.5rem;
}
.entity-drawer {
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-lg);
  overflow: hidden;
}
.entity-drawer__toggle {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  width: 100%;
  padding: 0.85rem 1.15rem;
  border: none;
  background: none;
  font-family: inherit;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--deid-ink-secondary);
  cursor: pointer;
  text-align: left;
}
.entity-drawer__toggle:hover {
  background: var(--deid-surface-2);
}
.entity-drawer__count {
  margin-left: auto;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  font-variant-numeric: tabular-nums;
}
.entity-drawer__chevron {
  display: inline-block;
  font-size: 1.125rem;
  color: var(--deid-ink-muted);
  transition: transform 0.2s ease;
}
.entity-drawer__chevron.open {
  transform: rotate(90deg);
}
.entity-drawer__body {
  padding: 0 1.15rem 1rem;
  border-top: 1px solid var(--deid-border);
}
.entity-drawer__hint {
  margin: 0.75rem 0 0.65rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
  line-height: 1.45;
}
.run-error {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-danger-bg);
  border: 1px solid var(--deid-danger-border);
  color: var(--deid-danger);
  font-size: 0.9375rem;
  line-height: 1.45;
}
.run-error__dismiss {
  flex-shrink: 0;
  border: none;
  background: none;
  color: var(--deid-danger);
  font-weight: 600;
  font-size: 0.875rem;
  font-family: inherit;
  cursor: pointer;
  min-height: 44px;
  padding: 0 0.35rem;
}
.data-toolbar {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin-bottom: 0.5rem;
  flex-shrink: 0;
}
.data-search {
  flex: 1;
  min-width: 0;
  min-height: 36px;
  font-size: 0.875rem;
}
.data-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-shrink: 0;
}
.bulk-link {
  border: none;
  background: none;
  padding: 0;
  color: var(--deid-primary);
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  white-space: nowrap;
}
.bulk-link:hover {
  text-decoration: underline;
}
.table-wrap {
  padding: 0;
  overflow: hidden;
  border-radius: var(--deid-radius);
  border: 1px solid var(--deid-border);
  background: var(--deid-bg);
  max-height: 240px;
  overflow-y: auto;
}
.entity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}
.entity-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  text-align: left;
  padding: 0.35rem 0.65rem;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface-2);
  color: var(--deid-ink-muted);
  font-weight: 500;
  font-size: 0.6875rem;
}
.entity-table td {
  padding: 0;
  height: 32px;
  border-bottom: 1px solid var(--deid-border);
  vertical-align: middle;
}
.entity-table tbody tr:hover {
  background: var(--deid-primary-soft);
}
.col-check {
  width: 36px;
  padding-left: 0.65rem !important;
}
.col-hits {
  width: 48px;
  text-align: right;
  padding-right: 0.65rem !important;
}
.col-more {
  width: 36px;
  text-align: center;
}
.entity-check {
  width: 16px;
  height: 16px;
  accent-color: var(--deid-primary);
  cursor: pointer;
}
.entity-cell {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
  padding-right: 0.5rem !important;
}
.entity-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.entity-badge {
  flex-shrink: 0;
  transform: scale(0.9);
  transform-origin: left center;
}
.muted {
  color: var(--deid-ink-muted);
}
.no-match {
  margin: 0;
  padding: 1.5rem;
  text-align: center;
  color: var(--deid-ink-muted);
  font-size: 0.875rem;
}
.star {
  border: none;
  background: none;
  font-size: 1rem;
  cursor: pointer;
  color: var(--deid-ink-muted);
  padding: 0;
  line-height: 1;
}
.star.on {
  color: var(--deid-warning);
}
.entity-mobile {
  display: none;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: 0.5rem;
  max-height: 280px;
  overflow-y: auto;
}
.entity-card {
  background: var(--deid-bg);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-sm);
  padding: 0.65rem 0.85rem;
}
.entity-card__main {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  cursor: pointer;
}
.entity-card__check {
  width: 18px;
  height: 18px;
  margin-top: 0.1rem;
  flex-shrink: 0;
  accent-color: var(--deid-primary);
}
.entity-card__name {
  font-weight: 500;
  font-size: 0.9375rem;
  line-height: 1.35;
  word-break: break-word;
}
.entity-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.4rem;
  margin-left: 1.65rem;
  font-size: 0.8125rem;
}
.manual-add {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--deid-border);
}
.manual-toggle {
  width: 100%;
  justify-content: center;
}
.manual-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.manual-form__btns {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
.conclusion-footer {
  display: none;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.conclusion-footer__count {
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--deid-ink-secondary);
}

@media (min-width: 769px) {
  .conclusion {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    max-width: 720px;
    margin: 0 auto;
    padding: 1.25rem 1.5rem 1.5rem;
    overflow-y: auto;
  }
  .conclusion-head {
    margin-bottom: 1rem;
  }
  .approve-hero {
    padding: 2.25rem 2rem 2rem;
  }
  .entity-desktop {
    display: block;
  }
  .conclusion-footer {
    display: none;
  }
}

@media (max-width: 768px) {
  .entity-desktop {
    display: none;
  }
  .entity-mobile {
    display: flex;
    flex-direction: column;
  }
  .approve-hero {
    padding: 1.5rem 1rem 1.25rem;
  }
  .approve-cta {
    display: none;
  }
  .conclusion-footer {
    display: flex;
    position: sticky;
    bottom: 0;
    z-index: 3;
    margin: 0.75rem -1rem 0;
    padding: 0.85rem 1rem;
    background: var(--deid-bg);
    border-top: 1px solid var(--deid-border);
    box-shadow: 0 -4px 12px rgba(15, 15, 15, 0.06);
  }
  .conclusion-footer .deid-btn {
    flex: 1;
    max-width: 220px;
  }
}

@media (max-width: 640px) {
  .conclusion {
    padding-bottom: 5.5rem;
  }
}
</style>
