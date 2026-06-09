<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ disabled?: boolean; embedded?: boolean }>()
const emit = defineEmits<{ select: [file: File] }>()
const dragOver = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

function onPick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) emit('select', f)
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) emit('select', f)
}
</script>

<template>
  <div
    class="dropzone"
    :class="{ over: dragOver, disabled: props.disabled, embedded: props.embedded }"
    role="button"
    tabindex="0"
    aria-label="上传 Word 文档"
    @dragover.prevent="dragOver = true"
    @dragleave="dragOver = false"
    @drop="props.disabled ? undefined : onDrop($event)"
    @keydown.enter="props.disabled ? undefined : inputRef?.click()"
    @click="props.disabled ? undefined : inputRef?.click()"
  >
    <input
      ref="inputRef"
      type="file"
      accept=".docx"
      class="hidden"
      :disabled="props.disabled"
      @change="onPick"
    />
    <div class="icon-wrap" aria-hidden="true">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
        <path
          d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
        <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
      </svg>
    </div>
    <p class="title">拖放 Word 文档到此处</p>
    <p class="hint">或点击选择文件 · 仅支持 .docx 格式</p>
  </div>
</template>

<style scoped>
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 280px;
  border: 2px dashed var(--deid-border-strong);
  border-radius: var(--deid-radius-lg);
  padding: 2.5rem 2rem;
  text-align: center;
  background: var(--deid-surface);
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
  cursor: pointer;
}
.dropzone.embedded {
  border: none;
  border-radius: 0;
  background: transparent;
  min-height: 260px;
  box-shadow: none;
}
.dropzone.embedded:hover:not(.disabled) {
  background: var(--deid-primary-soft);
}
.dropzone:hover:not(.disabled):not(.embedded) {
  border-color: var(--deid-primary);
  background: var(--deid-primary-soft);
}
.dropzone.disabled {
  opacity: 0.5;
  pointer-events: none;
  cursor: not-allowed;
}
.dropzone.over {
  border-color: var(--deid-primary);
  background: var(--deid-primary-soft);
  box-shadow: var(--deid-shadow-md);
}
.dropzone.embedded.over {
  box-shadow: none;
}
.hidden {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}
.icon-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  margin-bottom: 1.25rem;
  border-radius: 16px;
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
}
.dropzone:hover .icon-wrap,
.dropzone.over .icon-wrap {
  background: var(--deid-surface);
  color: var(--deid-primary);
}
.title {
  margin: 0;
  font-weight: 600;
  font-size: 1.25rem;
  color: var(--deid-ink);
}
.hint {
  margin: 0.5rem 0 0;
  color: var(--deid-ink-muted);
  font-size: 1rem;
}
</style>
