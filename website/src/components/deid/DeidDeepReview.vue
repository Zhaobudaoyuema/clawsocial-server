<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDeidStore } from '../../stores/deid'

const props = defineProps<{
  jobId: number
}>()

const emit = defineEmits<{
  close: []
  applied: []
}>()

const store = useDeidStore()
const suggestLoading = ref<string | null>(null)

const risks = computed(() => store.deepRisks)

async function loadSuggest(riskId: string) {
  suggestLoading.value = riskId
  try {
    await store.deepSuggest(props.jobId, riskId)
  } finally {
    suggestLoading.value = null
  }
}

function toggleEnabled(riskId: string, enabled: boolean) {
  store.patchDeepRisk(riskId, { enabled })
}

function updateRewrite(riskId: string, value: string) {
  store.patchDeepRisk(riskId, { rewritten: value })
}

async function applySelected() {
  await store.deepApply(props.jobId)
  emit('applied')
}
</script>

<template>
  <section class="deep-review deid-panel">
    <header class="head">
      <h3>深度脱敏预览</h3>
      <p class="sub">勾选需改写的指纹项，可编辑 AI 建议后应用</p>
      <button type="button" class="deid-btn deid-btn--ghost close" @click="emit('close')">关闭</button>
    </header>

    <p v-if="!risks.length" class="empty">未发现需深度改写的指纹项</p>

    <table v-else class="table">
      <thead>
        <tr>
          <th>启用</th>
          <th>类别</th>
          <th>原文</th>
          <th>改写</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in risks" :key="r.risk_id as string">
          <td>
            <input
              type="checkbox"
              :checked="r.enabled !== false"
              @change="toggleEnabled(r.risk_id as string, ($event.target as HTMLInputElement).checked)"
            />
          </td>
          <td class="cat">{{ r.category }}</td>
          <td class="orig deid-mono">{{ r.original }}</td>
          <td>
            <textarea
              class="deid-input rewrite"
              rows="2"
              :value="(r.rewritten as string) || (r.suggested_rewrite as string) || ''"
              placeholder="改写文本"
              @input="updateRewrite(r.risk_id as string, ($event.target as HTMLTextAreaElement).value)"
            />
          </td>
          <td>
            <button
              type="button"
              class="deid-btn deid-btn--ghost"
              :disabled="suggestLoading === r.risk_id"
              @click="loadSuggest(r.risk_id as string)"
            >
              {{ suggestLoading === r.risk_id ? '…' : 'AI 建议' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="foot">
      <button type="button" class="deid-btn deid-btn--primary" :disabled="store.deepLoading" @click="applySelected">
        {{ store.deepLoading ? '应用中…' : '应用深度改写' }}
      </button>
    </footer>
  </section>
</template>

<style scoped>
.deep-review {
  margin-bottom: 1.25rem;
  padding: 1.25rem 1.5rem;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
}
.head h3 {
  margin: 0;
  flex: 1 1 100%;
}
.sub {
  margin: 0;
  flex: 1;
  color: var(--deid-ink-muted);
  font-size: 0.9375rem;
}
.close {
  margin-left: auto;
}
.empty {
  color: var(--deid-ink-muted);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9375rem;
}
.table th,
.table td {
  border-bottom: 1px solid var(--deid-border);
  padding: 0.5rem 0.35rem;
  vertical-align: top;
  text-align: left;
}
.cat {
  white-space: nowrap;
  color: var(--deid-ink-muted);
}
.orig {
  max-width: 200px;
  word-break: break-all;
}
.rewrite {
  width: 100%;
  min-width: 160px;
  resize: vertical;
}
.foot {
  margin-top: 1rem;
  display: flex;
  justify-content: flex-end;
}
</style>
