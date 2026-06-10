<script setup lang="ts">
export type WizardStepId = 'upload' | 'entity_scan' | 'semantic' | 'confirm' | 'finish'

const props = withDefaults(
  defineProps<{
    current: WizardStepId
    finished?: boolean
    compact?: boolean
    prominent?: boolean
    embedded?: boolean
  }>(),
  { embedded: false },
)

const steps = [
  { id: 'upload' as const, label: '上传', short: '传' },
  { id: 'entity_scan' as const, label: '实体扫描', short: '实' },
  { id: 'semantic' as const, label: '语义扫描', short: '义' },
  { id: 'confirm' as const, label: '确认', short: '认' },
  { id: 'finish' as const, label: '完成', short: '完' },
]

const order: WizardStepId[] = ['upload', 'entity_scan', 'semantic', 'confirm', 'finish']

function stepIndex(id: string) {
  return order.indexOf(id as WizardStepId)
}

function isDone(id: string) {
  if (props.finished && id === 'finish') return true
  return stepIndex(id) < stepIndex(props.current)
}

function isCurrent(id: string) {
  return id === props.current
}
</script>

<template>
  <nav class="stepper" :class="{ compact, prominent, embedded }" aria-label="脱敏流程">
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
        <span class="label-short">{{ step.short }}</span>
        <span v-if="i < steps.length - 1" class="line" aria-hidden="true" />
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.stepper.embedded {
  margin-bottom: 0;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--deid-border);
}
.stepper.embedded .dot {
  width: 24px;
  height: 24px;
  font-size: 0.6875rem;
}
.stepper.embedded .label {
  font-size: 0.8125rem;
  margin-left: 0.4rem;
}
.stepper.embedded .line {
  height: 2px;
  margin: 0 0.5rem;
  border-radius: 999px;
}
.stepper.embedded .step.current .label {
  font-size: 0.8125rem;
}
@media (max-width: 640px) {
  .stepper.embedded .label {
    display: none;
  }
  .stepper.embedded .label-short {
    display: inline;
    margin-left: 0.35rem;
    font-size: 0.75rem;
  }
}
.stepper {
  margin-bottom: 2rem;
}
.stepper.compact {
  margin-bottom: 0;
}
.stepper.compact .dot {
  width: 24px;
  height: 24px;
  font-size: 0.75rem;
}
.stepper.compact .label {
  font-size: 0.875rem;
}
.stepper.compact .line {
  height: 3px;
  margin: 0 0.5rem;
  border-radius: 999px;
}
.stepper.prominent {
  margin-bottom: 0;
  padding: 1.1rem 0.75rem 1.35rem;
}
.stepper.prominent .dot {
  width: 36px;
  height: 36px;
  font-size: 0.9375rem;
  border-width: 2px;
}
.stepper.prominent .label {
  font-size: 1rem;
  margin-left: 0.65rem;
}
.stepper.prominent .step.current .label {
  font-size: 1.0625rem;
}
.stepper.prominent .line {
  height: 4px;
  margin: 0 1rem;
  border-radius: 999px;
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
.label-short {
  display: none;
  margin-left: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--deid-ink-muted);
  white-space: nowrap;
}
.step.current .label-short {
  color: var(--deid-ink);
  font-weight: 600;
}
.step.done .label-short {
  color: var(--deid-ink-secondary);
}
@media (max-width: 640px) {
  .label {
    display: none;
  }
  .label-short {
    display: inline;
  }
  .line {
    margin: 0 0.35rem;
  }
}
</style>
