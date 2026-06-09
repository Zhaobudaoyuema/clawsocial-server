<script setup lang="ts">
defineProps<{
  percent: number
  message: string
  phase?: string
  queuePosition?: number | null
}>()
</script>

<template>
  <div class="scan-progress" role="status" aria-live="polite">
    <div class="scan-progress__head">
      <span class="scan-progress__label">{{ message }}</span>
      <span class="scan-progress__pct">{{ percent }}%</span>
    </div>
    <div class="scan-progress__track">
      <div class="scan-progress__bar" :style="{ width: `${percent}%` }" />
    </div>
    <p v-if="phase === 'queued' && queuePosition && queuePosition > 0" class="scan-progress__hint">
      Worker 正在处理其他任务，请稍候…
    </p>
  </div>
</template>

<style scoped>
.scan-progress {
  margin-top: 0;
  padding: 1.25rem 1.35rem;
  border-radius: var(--deid-radius);
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
}
.scan-progress__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 1rem;
}
.scan-progress__label {
  color: var(--deid-ink);
  font-weight: 500;
}
.scan-progress__pct {
  color: var(--deid-primary);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.scan-progress__track {
  height: 8px;
  border-radius: 999px;
  background: var(--deid-border);
  overflow: hidden;
}
.scan-progress__bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--deid-primary), var(--deid-primary-hover));
  transition: width 0.35s ease;
}
.scan-progress__hint {
  margin: 0.65rem 0 0;
  font-size: 0.9375rem;
  color: var(--deid-ink-muted);
}
</style>
