<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  danger?: boolean
  /** 为 true 时点击遮罩不关闭（用于删除等危险操作） */
  persistent?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const panelRef = ref<HTMLElement | null>(null)

function close() {
  emit('update:open', false)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open && !props.persistent) {
    e.preventDefault()
    close()
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    await nextTick()
    const el = panelRef.value?.querySelector<HTMLElement>(
      'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])',
    )
    el?.focus()
  },
)

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="deid-modal-root deid-app">
      <div class="deid-modal-backdrop" aria-hidden="true" @click="!persistent && close()" />
      <div
        ref="panelRef"
        class="deid-modal-panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="danger ? 'deid-modal-title-danger' : 'deid-modal-title'"
      >
        <header class="deid-modal-header">
          <h2 :id="danger ? 'deid-modal-title-danger' : 'deid-modal-title'" class="deid-modal-title">
            {{ title }}
          </h2>
          <button type="button" class="deid-modal-close" aria-label="关闭" @click="close">×</button>
        </header>
        <div class="deid-modal-body">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="deid-modal-footer">
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.deid-modal-root {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}
.deid-modal-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(15, 15, 15, 0.4);
}
.deid-modal-panel {
  position: relative;
  width: 100%;
  max-width: 480px;
  max-height: calc(100vh - 2rem);
  overflow-y: auto;
  background: var(--deid-surface);
  border: 1px solid var(--deid-border);
  border-radius: var(--deid-radius-lg);
  box-shadow: var(--deid-shadow-md);
}
.deid-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.25rem 1.5rem 0;
}
.deid-modal-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.deid-modal-close {
  border: none;
  background: none;
  font-size: 1.5rem;
  line-height: 1;
  color: var(--deid-ink-muted);
  cursor: pointer;
  padding: 0.25rem;
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.deid-modal-close:hover {
  color: var(--deid-ink);
}
.deid-modal-body {
  padding: 1rem 1.5rem;
  font-size: 1rem;
  color: var(--deid-ink-secondary);
  line-height: 1.5;
}
.deid-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.65rem;
  padding: 0 1.5rem 1.25rem;
  flex-wrap: wrap;
}

.deid-modal-footer :deep(.deid-btn) {
  font-synthesis: none;
}
</style>
