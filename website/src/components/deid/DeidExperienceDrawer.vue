<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  phase: 'loading' | 'edit' | 'saving'
  text: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [text: string]
}>()

const draft = ref('')

watch(
  () => props.text,
  (v) => {
    if (props.phase === 'edit') draft.value = v
  },
  { immediate: true },
)

function close() {
  if (props.phase === 'loading' || props.phase === 'saving') return
  emit('update:open', false)
}

function onConfirm() {
  const t = draft.value.trim().slice(0, 100)
  if (!t) return
  emit('confirm', t)
}
</script>

<template>
  <Transition name="exp-pop">
    <div
      v-if="open"
      class="exp-popover deid-panel"
      role="dialog"
      aria-labelledby="exp-pop-title"
      aria-live="polite"
      @click.stop
    >
      <header class="exp-popover__head">
        <div class="exp-popover__title-wrap">
          <span v-if="phase === 'loading' || phase === 'saving'" class="deid-spinner exp-popover__spin" aria-hidden="true" />
          <h2 id="exp-pop-title" class="exp-popover__title">
            {{ phase === 'loading' ? '提取经验中' : phase === 'saving' ? '保存中' : '经验结果' }}
          </h2>
        </div>
        <button
          type="button"
          class="exp-popover__close"
          aria-label="关闭"
          :disabled="phase === 'loading' || phase === 'saving'"
          @click="close"
        >
          ×
        </button>
      </header>

      <div v-if="phase === 'loading'" class="exp-popover__body">
        <p class="exp-popover__desc">对比初次与再识别差异，提炼规则…</p>
        <ul class="exp-popover__steps" aria-hidden="true">
          <li class="exp-popover__step exp-popover__step--on">分析差异</li>
          <li class="exp-popover__step exp-popover__step--pulse">提炼规则</li>
          <li class="exp-popover__step">生成文案</li>
        </ul>
      </div>

      <div v-else class="exp-popover__body">
        <textarea
          v-model="draft"
          class="deid-textarea exp-popover__input"
          maxlength="100"
          rows="2"
          :disabled="phase === 'saving'"
          placeholder="编辑经验（≤100 字）"
        />
        <div class="exp-popover__foot">
          <span class="exp-popover__count">{{ draft.length }}/100</span>
          <div class="exp-popover__actions">
            <button type="button" class="deid-btn deid-btn--ghost deid-btn--sm" :disabled="phase === 'saving'" @click="close">
              放弃
            </button>
            <button
              type="button"
              class="deid-btn deid-btn--primary deid-btn--sm"
              :disabled="!draft.trim() || phase === 'saving'"
              @click="onConfirm"
            >
              {{ phase === 'saving' ? '保存中…' : '保存到全局' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.exp-popover {
  position: absolute;
  bottom: calc(100% + 0.45rem);
  right: 0;
  z-index: 30;
  width: min(360px, calc(100vw - 2.5rem));
  padding: 0.75rem 0.85rem;
  border-radius: var(--deid-radius);
  background: var(--deid-surface);
  border: 1px solid color-mix(in srgb, var(--deid-preset) 35%, var(--deid-border));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--deid-preset) 6%, transparent),
    0 8px 24px rgba(15, 15, 15, 0.12);
}
.exp-popover__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.55rem;
}
.exp-popover__title-wrap {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}
.exp-popover__title {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.exp-popover__spin {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
}
.exp-popover__close {
  border: none;
  background: none;
  color: var(--deid-ink-muted);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  padding: 0.1rem 0.3rem;
  border-radius: var(--deid-radius-sm);
}
.exp-popover__close:hover:not(:disabled) {
  color: var(--deid-ink);
  background: var(--deid-surface-2);
}
.exp-popover__close:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.exp-popover__desc {
  margin: 0 0 0.55rem;
  font-size: 0.8125rem;
  color: var(--deid-ink-secondary);
  line-height: 1.45;
}
.exp-popover__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.exp-popover__step {
  font-size: 0.6875rem;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  border: 1px solid var(--deid-border);
  color: var(--deid-ink-muted);
  background: var(--deid-surface-2);
}
.exp-popover__step--on {
  color: var(--deid-primary);
  border-color: var(--deid-primary);
  background: var(--deid-primary-soft);
}
.exp-popover__step--pulse {
  animation: exp-step-pulse 1.2s ease-in-out infinite;
}
@keyframes exp-step-pulse {
  0%,
  100% {
    opacity: 0.45;
  }
  50% {
    opacity: 1;
    color: var(--deid-preset);
  }
}
.exp-popover__input {
  width: 100%;
  box-sizing: border-box;
  font-size: 0.8125rem;
  min-height: 3.25rem;
  resize: vertical;
}
.exp-popover__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.45rem;
}
.exp-popover__count {
  font-size: 0.6875rem;
  color: var(--deid-ink-muted);
  font-variant-numeric: tabular-nums;
}
.exp-popover__actions {
  display: flex;
  gap: 0.35rem;
  margin-left: auto;
}
.deid-btn--sm {
  min-height: 30px;
  padding: 0.2rem 0.65rem;
  font-size: 0.8125rem;
}
.exp-pop-enter-active,
.exp-pop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.exp-pop-enter-from,
.exp-pop-leave-to {
  opacity: 0;
  transform: translateY(4px) scale(0.98);
}
</style>
