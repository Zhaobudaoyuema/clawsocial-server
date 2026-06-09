<script setup lang="ts">
import { ref } from 'vue'
import DeidEntityTypeSelect from './DeidEntityTypeSelect.vue'

export type PreviewEntity = {
  id: number
  name: string
  hits: number
  badge: { variant: 'manual' | 'llm' | 'preset'; label: string }
}

const props = defineProps<{
  selectedCount: number
  totalCount: number
  preview: PreviewEntity[]
  moreCount: number
  canConfirm: boolean
  confirmLabel: string
  error?: string | null
  adding?: boolean
}>()

const emit = defineEmits<{
  confirm: []
  dismissError: []
  addManual: [payload: { name: string; type: string }]
}>()

const showManual = ref(false)
const manualName = ref('')
const manualType = ref('company')

function submitManual() {
  if (!manualName.value.trim()) return
  emit('addManual', { name: manualName.value.trim(), type: manualType.value })
  manualName.value = ''
  showManual.value = false
}
</script>

<template>
  <aside class="inspector" aria-label="确认决策">
    <div v-if="error" class="inspector-error" role="alert">
      <span>{{ error }}</span>
      <button type="button" class="inspector-error__x" @click="emit('dismissError')">×</button>
    </div>

    <header class="inspector-head">
      <h2 class="inspector-title">确认操作</h2>
      <p class="inspector-hint">核对已选实体，确认后开始脱敏处理</p>
      <p class="inspector-stats" aria-live="polite">
        <span class="inspector-stats__num">{{ selectedCount }}</span>
        <span class="inspector-stats__sep">/</span>
        <span>{{ totalCount }}</span>
        <span class="inspector-stats__unit">已选</span>
      </p>
    </header>

    <section v-if="preview.length" class="inspector-preview">
      <h3 class="inspector-preview__label">已选预览</h3>
      <ul class="preview-list">
        <li v-for="item in preview" :key="item.id" class="preview-item">
          <span class="preview-item__name" :title="item.name">{{ item.name }}</span>
          <span class="preview-item__hits deid-mono">{{ item.hits }}</span>
        </li>
        <li v-if="moreCount > 0" class="preview-more">+{{ moreCount }} 更多</li>
      </ul>
    </section>

    <section v-else-if="totalCount === 0" class="inspector-empty">
      <p>未发现实体，请手动添加后继续。</p>
    </section>

    <div class="inspector-actions">
      <button
        v-if="!showManual"
        type="button"
        class="deid-btn deid-btn--ghost manual-toggle"
        @click="showManual = true"
      >
        + 手动添加实体
      </button>
      <div v-else class="manual-form">
        <input
          v-model="manualName"
          class="deid-input"
          placeholder="实体名称"
          @keyup.enter="submitManual"
        />
        <DeidEntityTypeSelect v-model="manualType" width="100%" />
        <div class="manual-form__btns">
          <button type="button" class="deid-btn deid-btn--ghost" @click="showManual = false">取消</button>
          <button
            type="button"
            class="deid-btn deid-btn--primary"
            :disabled="adding || !manualName.trim()"
            @click="submitManual"
          >
            添加
          </button>
        </div>
      </div>

      <button
        type="button"
        class="deid-btn deid-btn--primary deid-btn--lg confirm-btn"
        :disabled="!canConfirm"
        :aria-describedby="'inspector-selected-count'"
        @click="emit('confirm')"
      >
        {{ confirmLabel }}
      </button>
      <span id="inspector-selected-count" class="sr-only">已选择 {{ selectedCount }} 个实体</span>
    </div>
  </aside>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 1.35rem 1.5rem;
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-lg);
  box-shadow: var(--deid-shadow-sm);
}
.inspector-error {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding: 0.55rem 0.65rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-danger-bg);
  border: 1px solid var(--deid-danger-border);
  color: var(--deid-danger);
  font-size: 0.8125rem;
  line-height: 1.4;
}
.inspector-error__x {
  border: none;
  background: none;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  color: inherit;
  padding: 0;
}
.inspector-head {
  flex-shrink: 0;
  margin-bottom: 1.25rem;
}
.inspector-title {
  margin: 0 0 0.35rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.inspector-hint {
  margin: 0 0 1rem;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
  line-height: 1.45;
}
.inspector-stats {
  margin: 0;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
}
.inspector-stats__num {
  font-size: 2.25rem;
  font-weight: 600;
  color: var(--deid-primary);
  letter-spacing: -0.02em;
  line-height: 1;
}
.inspector-stats__sep {
  color: var(--deid-ink-muted);
  margin: 0 0.1rem;
}
.inspector-stats__unit {
  margin-left: 0.35rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.inspector-preview {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-bottom: 1rem;
}
.inspector-preview__label {
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--deid-ink-muted);
}
.preview-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.preview-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--deid-border);
  font-size: 0.875rem;
}
.preview-item__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--deid-ink);
}
.preview-item__hits {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--deid-ink-muted);
}
.preview-more {
  padding: 0.5rem 0 0;
  font-size: 0.8125rem;
  color: var(--deid-ink-muted);
}
.inspector-empty {
  flex: 1;
  font-size: 0.875rem;
  color: var(--deid-ink-secondary);
  line-height: 1.5;
}
.inspector-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: auto;
  padding-top: 1rem;
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
.confirm-btn {
  width: 100%;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
</style>
