<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidBadge from './DeidBadge.vue'

const store = useDeidStore()

const props = withDefaults(
  defineProps<{
    entities: Record<string, unknown>[]
    editable?: boolean
    showNewBadge?: boolean
    showPlaceholderColumn?: boolean
    filterable?: boolean
  }>(),
  {
    showPlaceholderColumn: true,
    filterable: false,
  },
)

const emit = defineEmits<{ delete: [id: number] }>()

const searchQuery = ref('')
const sourceFilter = ref<'all' | 'llm' | 'remembered' | 'manual' | 'leak_verify'>('all')
const newOnly = ref(false)

const filteredEntities = computed(() => {
  let list = props.entities
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((e) => entityName(e).toLowerCase().includes(q))
  }
  if (sourceFilter.value !== 'all') {
    list = list.filter((e) => (e as { source: string }).source === sourceFilter.value)
  }
  if (newOnly.value) {
    list = list.filter(
      (e) => !!(e as { is_new_since_initial?: boolean }).is_new_since_initial,
    )
  }
  return list
})

const hasActiveFilter = computed(
  () =>
    !!searchQuery.value.trim() ||
    sourceFilter.value !== 'all' ||
    newOnly.value,
)

function clearFilters() {
  searchQuery.value = ''
  sourceFilter.value = 'all'
  newOnly.value = false
}

function entityId(e: Record<string, unknown>) {
  return (e as { id: number }).id
}

function entityName(e: Record<string, unknown>) {
  return (e as { canonical_name: string }).canonical_name
}

function sourceBadge(e: Record<string, unknown>) {
  const src = (e as { source: string }).source
  const label = (e as { source_label?: string }).source_label
  if (src === 'manual') return { variant: 'manual' as const, label: label || '手动' }
  if (src === 'llm') return { variant: 'llm' as const, label: 'AI 识别' }
  if (src === 'remembered') return { variant: 'preset' as const, label: '词库' }
  if (src === 'leak_verify') return { variant: 'llm' as const, label: '验漏' }
  return { variant: 'preset' as const, label: label || src }
}

function entityTypeLabel(e: Record<string, unknown>) {
  return store.entityTypeLabel((e as { entity_type: string }).entity_type || '')
}

const sourceChips = [
  { id: 'all' as const, label: '全部' },
  { id: 'llm' as const, label: 'AI' },
  { id: 'remembered' as const, label: '词库' },
  { id: 'manual' as const, label: '手动' },
  { id: 'leak_verify' as const, label: '验漏' },
]
</script>

<template>
  <section class="entity-list deid-panel">
    <h3 class="title">实体列表</h3>

    <div v-if="filterable && entities.length" class="filter-bar">
      <input
        v-model="searchQuery"
        type="search"
        class="deid-input filter-search"
        placeholder="搜索实体名称…"
        aria-label="搜索实体"
      />
      <div class="filter-chips" role="group" aria-label="按来源筛选">
        <button
          v-for="chip in sourceChips"
          :key="chip.id"
          type="button"
          class="filter-chip"
          :class="{ active: sourceFilter === chip.id }"
          @click="sourceFilter = chip.id"
        >
          {{ chip.label }}
        </button>
      </div>
      <label v-if="showNewBadge" class="filter-new">
        <input v-model="newOnly" type="checkbox" />
        仅新增
      </label>
    </div>

    <table v-if="filteredEntities.length" class="table entity-desktop">
      <thead>
        <tr>
          <th>实体</th>
          <th class="col-type">分类</th>
          <th>来源</th>
          <th v-if="showPlaceholderColumn">占位符</th>
          <th v-if="editable" />
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="e in filteredEntities"
          :key="entityId(e)"
          :class="{ 'row-new': showNewBadge && (e as { is_new_since_initial?: boolean }).is_new_since_initial }"
        >
          <td class="name-cell" :title="entityName(e)">
            <span class="name-text">{{ entityName(e) }}</span>
            <DeidBadge
              v-if="showNewBadge && (e as { is_new_since_initial?: boolean }).is_new_since_initial"
              variant="llm"
              label="新增"
              class="new-badge"
            />
          </td>
          <td class="type-cell">{{ entityTypeLabel(e) }}</td>
          <td><DeidBadge v-bind="sourceBadge(e)" /></td>
          <td v-if="showPlaceholderColumn" class="deid-mono">
            {{ (e as { placeholder?: string }).placeholder || '—' }}
          </td>
          <td v-if="editable">
            <button
              type="button"
              class="deid-btn deid-btn--ghost deid-btn--danger del-btn"
              @click="emit('delete', entityId(e))"
            >
              删除
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <ul v-if="filteredEntities.length" class="entity-cards entity-mobile">
      <li v-for="e in filteredEntities" :key="entityId(e)" class="entity-card">
        <div class="entity-card__name">
          {{ entityName(e) }}
          <DeidBadge
            v-if="showNewBadge && (e as { is_new_since_initial?: boolean }).is_new_since_initial"
            variant="llm"
            label="新增"
            class="new-badge"
          />
        </div>
        <div class="entity-card__meta">
          <span class="type-tag">{{ entityTypeLabel(e) }}</span>
          <DeidBadge v-bind="sourceBadge(e)" />
          <span v-if="showPlaceholderColumn" class="deid-mono placeholder">
            {{ (e as { placeholder?: string }).placeholder || '—' }}
          </span>
        </div>
        <button
          v-if="editable"
          type="button"
          class="deid-btn deid-btn--ghost deid-btn--danger del-btn del-btn--touch"
          @click="emit('delete', entityId(e))"
        >
          删除
        </button>
      </li>
    </ul>

    <p v-if="!entities.length" class="empty">暂无实体</p>
    <div v-else-if="!filteredEntities.length" class="empty filtered-empty">
      <p>未找到匹配实体，试试清除筛选</p>
      <button v-if="hasActiveFilter" type="button" class="deid-btn deid-btn--ghost" @click="clearFilters">
        清除筛选
      </button>
    </div>
  </section>
</template>

<style scoped>
.title {
  margin: 0 0 1.25rem;
  font-size: 1.0625rem;
  font-weight: 600;
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
  margin-bottom: 1rem;
}
.filter-search {
  flex: 1 1 180px;
  min-width: 0;
  max-width: 280px;
}
.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.filter-chip {
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  border: 1px solid var(--deid-border);
  background: var(--deid-surface);
  font-size: 0.8125rem;
  color: var(--deid-ink-secondary);
  cursor: pointer;
}
.filter-chip.active {
  border-color: var(--deid-primary);
  background: var(--deid-primary-soft);
  color: var(--deid-primary);
  font-weight: 500;
}
.filter-new {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
  cursor: pointer;
  user-select: none;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 1rem;
  table-layout: fixed;
}
.table th {
  text-align: left;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
  font-size: 0.875rem;
  font-weight: 500;
}
.table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--deid-border);
}
.table tbody tr:hover {
  background: var(--deid-primary-soft);
}
.name-cell {
  max-width: 0;
  overflow: hidden;
}
.col-type,
.type-cell {
  width: 6.5rem;
  white-space: nowrap;
}
.type-cell {
  color: var(--deid-ink-secondary);
  font-size: 0.9375rem;
}
.type-tag {
  font-size: 0.8125rem;
  color: var(--deid-ink-secondary);
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  background: var(--deid-surface-2);
}
.name-text {
  display: inline-block;
  max-width: calc(100% - 4rem);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.new-badge {
  margin-left: 0.35rem;
  vertical-align: middle;
}
.entity-mobile {
  display: none;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: 0.65rem;
}
.entity-card {
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--deid-border);
}
.entity-card:last-child {
  border-bottom: none;
}
.entity-card__name {
  font-weight: 500;
  font-size: 1rem;
  word-break: break-word;
  margin-bottom: 0.4rem;
}
.entity-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
}
.placeholder {
  color: var(--deid-ink-muted);
  word-break: break-all;
}
.del-btn {
  min-height: 32px;
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
}
.del-btn--touch {
  min-height: 44px;
  padding: 0.35rem 0.75rem;
}
.empty {
  color: var(--deid-ink-muted);
  text-align: center;
  padding: 1.5rem;
}
.filtered-empty p {
  margin: 0 0 0.75rem;
}
@media (max-width: 768px) {
  .entity-desktop {
    display: none;
  }
  .entity-mobile {
    display: flex;
    flex-direction: column;
  }
  .filter-search {
    max-width: none;
    flex: 1 1 100%;
  }
}
</style>
