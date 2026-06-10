<script setup lang="ts">
const props = defineProps<{
  steps: { id: string; label: string }[]
  current: string
  /** 当前步骤正在执行（显示转圈） */
  busy?: boolean
}>()

const order = () => props.steps.map((s) => s.id)

function stepIdx(id: string) {
  return order().indexOf(id)
}

function isDone(id: string) {
  return stepIdx(id) < stepIdx(props.current)
}

function isCurrent(id: string) {
  return id === props.current
}
</script>

<template>
  <nav class="segment-nav" aria-label="子进度">
    <ol class="segment-list">
      <li
        v-for="(step, i) in steps"
        :key="step.id"
        class="segment"
        :class="{ current: isCurrent(step.id), done: isDone(step.id), busy: busy && isCurrent(step.id) }"
      >
        <span class="segment-marker" aria-hidden="true">
          <span v-if="busy && isCurrent(step.id)" class="deid-spinner segment-spin" />
          <span v-else-if="isDone(step.id)">✓</span>
          <span v-else-if="isCurrent(step.id)" class="segment-pulse" />
          <span v-else class="segment-idle" />
        </span>
        <span class="segment-label">{{ step.label }}</span>
        <span v-if="i < steps.length - 1" class="segment-connector" aria-hidden="true" />
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.segment-nav {
  margin: 0;
}
.segment-list {
  display: flex;
  align-items: stretch;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: 0.5rem;
}
.segment {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  padding: 0.55rem 0.75rem;
  border-radius: var(--deid-radius-sm);
  background: var(--deid-surface-2);
  border: 1px solid var(--deid-border);
  position: relative;
}
.segment.done {
  background: var(--deid-success-bg);
  border-color: var(--deid-success-border);
}
.segment.current {
  background: var(--deid-primary-soft);
  border-color: color-mix(in srgb, var(--deid-primary) 35%, var(--deid-border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--deid-primary) 12%, transparent);
}
.segment.busy {
  border-color: var(--deid-primary);
  animation: segment-busy 1.4s ease-in-out infinite;
}
@keyframes segment-busy {
  0%,
  100% {
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--deid-primary) 12%, transparent);
  }
  50% {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--deid-primary) 18%, transparent);
  }
}
.segment-spin {
  width: 1rem;
  height: 1rem;
}
.segment-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--deid-success);
}
.segment.current .segment-marker {
  color: var(--deid-primary);
}
.segment-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--deid-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--deid-primary) 25%, transparent);
}
.segment-idle {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--deid-border-strong);
}
.segment-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--deid-ink-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.segment.current .segment-label {
  color: var(--deid-ink);
  font-weight: 600;
}
.segment.done .segment-label {
  color: var(--deid-ink-secondary);
}
.segment-connector {
  display: none;
}
@media (max-width: 520px) {
  .segment-list {
    flex-direction: column;
  }
  .segment-label {
    white-space: normal;
  }
}
</style>
