<script setup lang="ts">
import DeidBadge from './DeidBadge.vue'

defineProps<{
  entities: Record<string, unknown>[]
  editable?: boolean
}>()

const emit = defineEmits<{ delete: [id: number] }>()

function sourceBadge(e: Record<string, unknown>) {
  const src = (e as { source: string }).source
  const label = (e as { source_label?: string }).source_label
  if (src === 'manual') return { variant: 'manual' as const, label: label || '手动' }
  if (src === 'llm') return { variant: 'llm' as const, label: label || '智能发现' }
  if (src === 'remembered') return { variant: 'preset' as const, label: label || '已记住' }
  return { variant: 'preset' as const, label: label || src }
}
</script>

<template>
  <section class="entity-list deid-panel">
    <h3 class="title">实体列表</h3>
    <table v-if="entities.length" class="table">
      <thead>
        <tr>
          <th>实体</th>
          <th>来源</th>
          <th>占位符</th>
          <th v-if="editable" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in entities" :key="(e as { id: number }).id">
          <td>{{ (e as { canonical_name: string }).canonical_name }}</td>
          <td><DeidBadge v-bind="sourceBadge(e)" /></td>
          <td class="deid-mono">{{ (e as { placeholder?: string }).placeholder || '—' }}</td>
          <td v-if="editable">
            <button
              type="button"
              class="deid-btn deid-btn--ghost deid-btn--danger del-btn"
              @click="emit('delete', (e as { id: number }).id)"
            >
              删除
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">暂无实体</p>
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
.del-btn {
  min-height: 32px;
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
}
.empty {
  color: var(--deid-ink-muted);
  text-align: center;
  padding: 1.5rem;
}
</style>
