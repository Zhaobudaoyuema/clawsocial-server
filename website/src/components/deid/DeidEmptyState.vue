<script setup lang="ts">
defineProps<{
  title: string
  hint?: string
  ctaLabel?: string
}>()
defineEmits<{ action: [] }>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon" aria-hidden="true">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 8v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </div>
    <p class="empty-title">{{ title }}</p>
    <p v-if="hint" class="empty-hint">{{ hint }}</p>
    <button v-if="ctaLabel" type="button" class="deid-btn deid-btn--primary" @click="$emit('action')">
      {{ ctaLabel }}
    </button>
  </div>
</template>

<style scoped>
.empty-state {
  text-align: center;
  padding: 2.5rem 1.5rem;
}
.empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  margin-bottom: 1rem;
  border-radius: 16px;
  background: var(--deid-surface-2);
  color: var(--deid-ink-muted);
}
.empty-title {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--deid-ink);
}
.empty-hint {
  margin: 0.5rem 0 1.25rem;
  font-size: 1rem;
  color: var(--deid-ink-secondary);
  line-height: 1.5;
}
</style>
