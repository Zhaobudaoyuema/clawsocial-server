<script setup lang="ts">
import { computed } from 'vue'
import DeidBadge from './DeidBadge.vue'

const props = defineProps<{
  entities: Record<string, unknown>[]
  loading?: boolean
}>()

const sorted = computed(() =>
  [...props.entities].sort((a, b) => {
    const sa = (a as { source: string }).source === 'manual' ? 1 : 0
    const sb = (b as { source: string }).source === 'manual' ? 1 : 0
    if (sa !== sb) return sb - sa
    return (
      ((b as { hit_count: number }).hit_count || 0) -
      ((a as { hit_count: number }).hit_count || 0)
    )
  }),
)

const totalHits = computed(() =>
  props.entities.reduce((s, e) => s + ((e as { hit_count: number }).hit_count || 0), 0),
)

function sourceBadge(e: Record<string, unknown>) {
  const src = (e as { source: string }).source
  const label = (e as { source_label?: string }).source_label
  if (src === 'manual') return { variant: 'manual' as const, label: label || '手动补充' }
  if (src === 'llm') return { variant: 'llm' as const, label: label || '智能发现' }
  if (src === 'rule') return { variant: 'rule' as const, label: label || '文档规则' }
  if (src === 'pattern') return { variant: 'pattern' as const, label: label || '规则' }
  return { variant: 'preset' as const, label: label || '词库' }
}
</script>

<template>
  <div class="table-wrap">
    <div v-if="loading" class="skeleton">
      <div v-for="i in 5" :key="i" class="sk-row" />
    </div>
    <div v-else-if="!entities.length" class="empty">
      <p class="empty-title">未发现预设主体</p>
      <p class="empty-hint">可手动补充公司/人名，或检查是否选对了词库包</p>
    </div>
    <table v-else class="entity-table">
      <thead>
        <tr>
          <th scope="col">实体</th>
          <th scope="col">类型</th>
          <th scope="col">来源</th>
          <th scope="col">命中</th>
          <th scope="col">占位符</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="e in sorted"
          :key="(e as { id: number }).id"
          :class="{ manual: (e as { source: string }).source === 'manual' }"
        >
          <td>{{ (e as { canonical_name: string }).canonical_name }}</td>
          <td>{{ (e as { entity_type: string }).entity_type }}</td>
          <td>
            <DeidBadge v-bind="sourceBadge(e)" />
            <DeidBadge
              v-if="(e as { low_confidence?: boolean }).low_confidence"
              variant="running"
              label="低置信"
              style="margin-left: 0.25rem"
            />
          </td>
          <td>
            <span :class="{ warn: !(e as { hit_count: number }).hit_count }">
              {{ (e as { hit_count: number }).hit_count }}
            </span>
          </td>
          <td class="deid-mono">
            {{ (e as { placeholder?: string }).placeholder || '—' }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="entities.length" class="foot">
      共 {{ entities.length }} 个实体 · {{ totalHits }} 处命中
    </p>
  </div>
</template>

<style scoped>
.table-wrap {
  overflow-x: auto;
}
.entity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
.entity-table th {
  text-align: left;
  padding: 0.65rem 0.75rem;
  border-bottom: 2px solid var(--deid-border);
  color: var(--deid-ink-muted);
  font-weight: 500;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.entity-table td {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid var(--deid-border);
}
tr.manual td {
  background: var(--deid-manual-bg);
}
.warn {
  color: var(--deid-manual);
  font-weight: 600;
}
.foot {
  margin: 0.75rem 0 0;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.empty {
  padding: 2rem;
  text-align: center;
}
.empty-title {
  margin: 0;
  font-weight: 600;
}
.empty-hint {
  margin: 0.35rem 0 0;
  color: var(--deid-ink-muted);
  font-size: 0.875rem;
}
.skeleton .sk-row {
  height: 40px;
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%;
  animation: shimmer 1.2s infinite;
  border-radius: 4px;
  margin-bottom: 0.5rem;
}
@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
