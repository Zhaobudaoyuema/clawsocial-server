<script setup lang="ts">
defineProps<{
  message: string
  canRetry?: boolean
  hasEntities?: boolean
}>()

defineEmits<{
  retry: []
  viewConclusion: []
}>()
</script>

<template>
  <div class="scan-error deid-panel" role="alert">
    <div class="scan-error__icon" aria-hidden="true">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 8v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </div>
    <h3 class="scan-error__title">扫描未完成</h3>
    <p class="scan-error__msg">{{ message }}</p>
    <div class="scan-error__actions">
      <button
        v-if="canRetry !== false"
        type="button"
        class="deid-btn deid-btn--primary"
        @click="$emit('retry')"
      >
        重试扫描
      </button>
      <button
        v-if="hasEntities"
        type="button"
        class="deid-btn"
        @click="$emit('viewConclusion')"
      >
        查看已匹配实体
      </button>
    </div>
  </div>
</template>

<style scoped>
.scan-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 2rem 1.75rem;
  background: var(--deid-danger-bg);
  border-color: var(--deid-danger-border);
}
.scan-error__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 14px;
  background: var(--deid-surface);
  color: var(--deid-danger);
  margin-bottom: 1rem;
}
.scan-error__title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.scan-error__msg {
  margin: 0.5rem 0 1.25rem;
  font-size: 1rem;
  color: var(--deid-ink-secondary);
  line-height: 1.5;
  max-width: 480px;
}
.scan-error__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  justify-content: center;
}
</style>
