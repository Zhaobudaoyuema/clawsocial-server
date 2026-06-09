<script setup lang="ts">
const props = defineProps<{
  current: 'upload' | 'scan' | 'confirm' | 'done'
}>()

const steps = [
  { id: 'upload' as const, label: '上传' },
  { id: 'scan' as const, label: '扫描' },
  { id: 'confirm' as const, label: '确认' },
  { id: 'done' as const, label: '完成' },
]

const order = ['upload', 'scan', 'confirm', 'done']

function stepIndex(id: string) {
  return order.indexOf(id)
}

function isDone(id: string) {
  return stepIndex(id) < stepIndex(props.current)
}

function isCurrent(id: string) {
  return id === props.current
}
</script>

<template>
  <nav class="stepper" aria-label="脱敏流程">
    <ol class="stepper-list">
      <li
        v-for="(step, i) in steps"
        :key="step.id"
        class="step"
        :class="{ current: isCurrent(step.id), done: isDone(step.id) }"
      >
        <span class="dot" aria-hidden="true">
          <span v-if="isDone(step.id)">✓</span>
          <span v-else>{{ i + 1 }}</span>
        </span>
        <span class="label">{{ step.label }}</span>
        <span v-if="i < steps.length - 1" class="line" aria-hidden="true" />
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.stepper {
  margin-bottom: 2rem;
}
.stepper-list {
  display: flex;
  align-items: center;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: 0;
}
.step {
  display: flex;
  align-items: center;
  flex: 1;
  position: relative;
  min-width: 0;
}
.dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--deid-surface-2);
  color: var(--deid-ink-muted);
  border: 2px solid var(--deid-border);
  flex-shrink: 0;
}
.step.current .dot {
  background: var(--deid-primary);
  border-color: var(--deid-primary);
  color: #fff;
}
.step.done .dot {
  background: var(--deid-success-bg);
  border-color: var(--deid-success-border);
  color: var(--deid-success);
}
.label {
  margin-left: 0.5rem;
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--deid-ink-muted);
  white-space: nowrap;
}
.step.current .label {
  color: var(--deid-ink);
  font-weight: 600;
}
.step.done .label {
  color: var(--deid-ink-secondary);
}
.line {
  flex: 1;
  height: 2px;
  margin: 0 0.75rem;
  background: var(--deid-border);
  min-width: 12px;
}
.step.done .line {
  background: var(--deid-success-border);
}
@media (max-width: 640px) {
  .label {
    display: none;
  }
  .line {
    margin: 0 0.35rem;
  }
}
</style>
