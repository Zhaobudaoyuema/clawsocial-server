<script setup lang="ts">
import DeidBadge from './DeidBadge.vue'

defineProps<{
  entities: Record<string, unknown>[]
  editable?: boolean
}>()

const emit = defineEmits<{ delete: [id: number] }>()

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
  if (src === 'remembered') return { variant: 'preset' as const, label: label || '已记住' }
  return { variant: 'preset' as const, label: label || src }
}
</script>

<template>
  <section class="entity-list deid-panel">
    <h3 class="title">实体列表</h3>

    <table v-if="entities.length" class="table entity-desktop">
      <thead>
        <tr>
          <th>实体</th>
          <th>来源</th>
          <th>占位符</th>
          <th v-if="editable" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in entities" :key="entityId(e)">
          <td>{{ entityName(e) }}</td>
          <td><DeidBadge v-bind="sourceBadge(e)" /></td>
          <td class="deid-mono">{{ (e as { placeholder?: string }).placeholder || '—' }}</td>
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

    <ul v-if="entities.length" class="entity-cards entity-mobile">
      <li v-for="e in entities" :key="entityId(e)" class="entity-card">
        <div class="entity-card__name">{{ entityName(e) }}</div>
        <div class="entity-card__meta">
          <DeidBadge v-bind="sourceBadge(e)" />
          <span class="deid-mono placeholder">{{ (e as { placeholder?: string }).placeholder || '—' }}</span>
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
  </section>
</template>

<style scoped>
.title {
  margin: 0 0 1.25rem;
  font-size: 1.0625rem;
  font-weight: 600;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 1rem;
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
@media (max-width: 768px) {
  .entity-desktop {
    display: none;
  }
  .entity-mobile {
    display: flex;
    flex-direction: column;
  }
}
</style>
