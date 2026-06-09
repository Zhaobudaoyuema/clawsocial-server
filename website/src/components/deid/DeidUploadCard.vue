<script setup lang="ts">
import DeidDropzone from './DeidDropzone.vue'

const props = defineProps<{
  disabled?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{ select: [file: File] }>()
</script>

<template>
  <div class="upload-card deid-panel" :class="{ loading: props.loading }">
    <DeidDropzone
      embedded
      :disabled="props.disabled || props.loading"
      @select="emit('select', $event)"
    />
    <div v-if="props.loading" class="loading-row">
      <span class="deid-spinner" aria-hidden="true" />
      <span>正在上传…</span>
    </div>
    <p v-else class="hint-text">选择或拖放 .docx 文件，将自动开始上传</p>
  </div>
</template>

<style scoped>
.upload-card {
  width: 100%;
  max-width: 720px;
  padding: 0 !important;
  overflow: hidden;
}
.upload-card.loading {
  opacity: 0.9;
}
.loading-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.65rem;
  padding: 0 1.5rem 1.25rem;
  font-size: 1rem;
  color: var(--deid-ink-secondary);
}
.hint-text {
  margin: 0;
  padding: 0 1.5rem 1.25rem;
  text-align: center;
  font-size: 0.9375rem;
  color: var(--deid-ink-muted);
}
</style>
