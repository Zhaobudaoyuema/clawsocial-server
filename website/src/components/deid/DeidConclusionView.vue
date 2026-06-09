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
const manualName = ref('')
const manualType = ref('company')
const adding = ref(false)

const jobId = computed(() => (store.currentJob as { id?: number } | null)?.id)
const canConfirm = computed(() => selected.value.size > 0 && !store.loading)

watch(
  () => store.entities,
  (ents) => {
    selected.value = new Set(
      ents.filter((e) => !(e as { is_excluded?: boolean }).is_excluded).map((e) => (e as { id: number }).id),
    )
    remember.value = new Set(
      ents.filter((e) => (e as { source: string }).source === 'manual').map((e) => (e as { id: number }).id),
    )
  },
  { immediate: true },
)

function toggleSelect(id: number) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
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
  if (src === 'llm') return { variant: 'llm' as const, label: label || '智能发现' }
  if (src === 'remembered') return { variant: 'preset' as const, label: label || '已记住' }
  return { variant: 'preset' as const, label: label || src }
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
  } finally {
    adding.value = false
  }
}

async function onConfirm() {
  if (!jobId.value || !canConfirm.value) return
  await store.confirmAndRun(jobId.value, [...selected.value], [...remember.value])
  emit('confirmed')
}
</script>

<template>
  <div class="conclusion">
    <DeidStepper current="confirm" />

    <header class="head">
      <div>
        <h2 class="deid-page-title">扫描结论</h2>
        <p class="deid-page-sub">勾选要脱敏的实体，确认后开始替换</p>
      </div>
      <button type="button" class="deid-btn deid-btn--ghost" @click="store.closeConclusionView()">
        关闭
      </button>
    </header>

    <DeidEmptyState
      v-if="!store.entities.length"
      class="deid-panel"
      title="未发现实体"
      hint="请在下方手动添加至少一个实体后继续"
    />

    <div v-else class="table-wrap deid-panel">
      <table class="entity-table">
        <thead>
          <tr>
            <th />
            <th>实体</th>
            <th>来源</th>
            <th>命中</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in store.entities" :key="(e as { id: number }).id">
            <td>
              <input
                type="checkbox"
                :checked="selected.has((e as { id: number }).id)"
                @change="toggleSelect((e as { id: number }).id)"
              />
            </td>
            <td>{{ (e as { canonical_name: string }).canonical_name }}</td>
            <td><DeidBadge v-bind="sourceBadge(e)" /></td>
            <td class="muted">{{ (e as { hit_count: number }).hit_count }}</td>
            <td>
              <button
                v-if="(e as { source: string }).source !== 'manual'"
                type="button"
                class="star"
                :class="{ on: remember.has((e as { id: number }).id) }"
                title="记住"
                @click="toggleRemember((e as { id: number }).id)"
              >
                ☆
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="manual-add">
      <input v-model="manualName" class="deid-input" placeholder="手动添加实体" @keyup.enter="addManual" />
      <DeidEntityTypeSelect v-model="manualType" width="120px" />
      <button type="button" class="deid-btn" :disabled="adding || !manualName.trim()" @click="addManual">
        添加
      </button>
    </div>

    <footer class="foot">
      <button type="button" class="deid-btn deid-btn--ghost" @click="store.closeConclusionView()">
        返回
      </button>
      <button
        type="button"
        class="deid-btn deid-btn--primary"
        :disabled="!canConfirm"
        @click="onConfirm"
      >
        {{ store.loading ? '处理中…' : '确认并脱敏' }}
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
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}
.head h2 {
  margin: 0;
}
.head p {
  margin: 0.35rem 0 0;
}
.empty {
  text-align: center;
  padding: 2.5rem 1.5rem;
}
.empty p {
  margin: 0;
  font-weight: 500;
  color: var(--deid-ink);
}
.empty-hint {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.table-wrap {
  padding: 0;
  overflow: hidden;
}
.entity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 1rem;
}
.entity-table th {
  text-align: left;
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid var(--deid-border);
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
  font-weight: 500;
  font-size: 0.875rem;
}
.entity-table td {
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid var(--deid-border);
}
.entity-table tbody tr:hover {
  background: var(--deid-primary-soft);
}
.muted {
  color: var(--deid-ink-muted);
}
.star {
  border: none;
  background: none;
  font-size: 1.1rem;
  cursor: pointer;
  color: var(--deid-ink-muted);
}
.star.on {
  color: var(--deid-warning);
}
.manual-add {
  display: flex;
  gap: 0.5rem;
  margin: 1.25rem 0;
  flex-wrap: wrap;
}
.foot {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--deid-border);
  position: sticky;
  bottom: 0;
  background: linear-gradient(to top, var(--deid-bg) 80%, transparent);
}
</style>
