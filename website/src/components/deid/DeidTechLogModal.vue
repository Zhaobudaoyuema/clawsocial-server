<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useDeidStore } from '../../stores/deid'
import DeidTechLogTerminal from './DeidTechLogTerminal.vue'
import DeidWorkerCallsPanel from './DeidWorkerCallsPanel.vue'

const props = defineProps<{
  open: boolean
  logs: string[]
  streamTail?: string
  live?: boolean
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const store = useDeidStore()
const tab = ref<'log' | 'calls'>('log')

const jobId = computed(() => (store.currentJob as { id?: number } | null)?.id ?? null)

function close() {
  emit('update:open', false)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    e.preventDefault()
    close()
  }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="term-modal">
      <div v-if="open" class="term-modal-root">
        <div class="term-modal-backdrop" aria-hidden="true" @click="close" />
        <div class="term-modal-panel" role="dialog" aria-modal="true" aria-labelledby="term-modal-title">
          <header class="term-modal-header">
            <div>
              <h2 id="term-modal-title" class="term-modal-title">// TECH_LOG</h2>
              <p class="term-modal-sub">Worker 调试 · ESC 关闭</p>
            </div>
            <button type="button" class="term-modal-close" aria-label="关闭" @click="close">×</button>
          </header>
          <nav class="term-modal-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              :aria-selected="tab === 'log'"
              :class="{ active: tab === 'log' }"
              @click="tab = 'log'"
            >
              实时日志
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="tab === 'calls'"
              :class="{ active: tab === 'calls' }"
              @click="tab = 'calls'"
            >
              Worker 调用
            </button>
          </nav>
          <DeidTechLogTerminal
            v-show="tab === 'log'"
            mode="full"
            :logs="logs"
            :stream-tail="streamTail"
            :live="live"
          />
          <DeidWorkerCallsPanel v-show="tab === 'calls'" :job-id="jobId" :active="open && tab === 'calls'" />
          <footer class="term-modal-foot">
            <span v-if="tab === 'log'">{{ logs.length }} 行</span>
            <span v-else>任务 #{{ jobId ?? '—' }} · 调用与任务绑定，删任务即删记录</span>
            <button type="button" class="term-modal-btn" @click="close">关闭</button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.term-modal-root {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}
.term-modal-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(2, 8, 6, 0.72);
  backdrop-filter: blur(4px);
}
.term-modal-panel {
  position: relative;
  width: 100%;
  max-width: 720px;
  padding: 1rem 1.15rem 1.15rem;
  border-radius: 12px;
  background: #050809;
  border: 1px solid #1a3d2e;
  box-shadow:
    0 0 40px rgba(0, 255, 136, 0.08),
    0 24px 64px rgba(0, 0, 0, 0.65);
}
.term-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.65rem;
}
.term-modal-tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}
.term-modal-tabs button {
  padding: 0.35rem 0.75rem;
  border: 1px solid #1a3d2e;
  border-radius: 6px;
  background: #0a1210;
  color: #6ee7b7;
  font-family: var(--deid-font-mono, Consolas, monospace);
  font-size: 0.75rem;
  cursor: pointer;
}
.term-modal-tabs button.active {
  border-color: #2dd4a0;
  color: #00ff88;
  background: rgba(0, 255, 136, 0.08);
}
.term-modal-title {
  margin: 0;
  font-family: var(--deid-font-mono, 'IBM Plex Mono', Consolas, monospace);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #00ff88;
  text-shadow: 0 0 12px rgba(0, 255, 136, 0.4);
}
.term-modal-sub {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: #5a8f72;
}
.term-modal-close {
  border: none;
  background: none;
  color: #5a8f72;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  padding: 0.25rem;
  min-width: 36px;
  min-height: 36px;
}
.term-modal-close:hover {
  color: #00ff88;
}
.term-modal-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.75rem;
  font-size: 0.6875rem;
  color: #4b7c5f;
  font-family: var(--deid-font-mono, Consolas, monospace);
}
.term-modal-btn {
  padding: 0.35rem 0.85rem;
  border: 1px solid #1a3d2e;
  border-radius: 6px;
  background: #0a1210;
  color: #6ee7b7;
  font-family: inherit;
  font-size: 0.75rem;
  cursor: pointer;
}
.term-modal-btn:hover {
  border-color: #2dd4a0;
  color: #00ff88;
}
.term-modal-enter-active,
.term-modal-leave-active {
  transition: opacity 0.2s ease;
}
.term-modal-enter-active .term-modal-panel,
.term-modal-leave-active .term-modal-panel {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.term-modal-enter-from,
.term-modal-leave-to {
  opacity: 0;
}
.term-modal-enter-from .term-modal-panel,
.term-modal-leave-to .term-modal-panel {
  transform: scale(0.96) translateY(8px);
  opacity: 0;
}
</style>
