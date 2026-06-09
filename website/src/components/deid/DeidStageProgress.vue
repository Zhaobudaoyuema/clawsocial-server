<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  current: 'upload' | 'scan' | 'confirm' | 'done'
}>()

const steps = ['upload', 'scan', 'confirm', 'done'] as const

const stepIndex = computed(() => {
  const i = steps.indexOf(props.current)
  return i >= 0 ? i : 0
})

const fillPct = computed(() => `${((stepIndex.value + 1) / steps.length) * 100}%`)

const stepLabel = computed(() => {
  const labels: Record<string, string> = {
    upload: '上传',
    scan: '扫描',
    confirm: '确认',
    done: '完成',
  }
  return labels[props.current] || props.current
})
</script>

<template>
  <div
    class="stage-progress"
    role="progressbar"
    :aria-valuenow="stepIndex + 1"
    aria-valuemin="1"
    aria-valuemax="4"
    :aria-label="`脱敏流程：${stepLabel}`"
  >
    <div class="stage-progress__track">
      <div class="stage-progress__fill" :style="{ width: fillPct }" />
    </div>
    <span class="stage-progress__label">{{ stepLabel }}</span>
  </div>
</template>

<style scoped>
.stage-progress {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.stage-progress__track {
  flex: 1;
  height: var(--deid-progress-height, 4px);
  border-radius: 999px;
  background: var(--deid-border);
  overflow: hidden;
}
.stage-progress__fill {
  height: 100%;
  border-radius: 999px;
  background: var(--deid-primary);
  transition: width 0.25s ease;
}
.stage-progress__label {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--deid-ink-muted);
  letter-spacing: 0.02em;
  min-width: 2rem;
  text-align: right;
}
</style>
