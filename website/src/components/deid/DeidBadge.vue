<script setup lang="ts">
defineProps<{
  variant: 'preset' | 'manual' | 'draft' | 'scanned' | 'done' | 'failed' | 'running' | 'llm' | 'rule' | 'pattern'
  label?: string
}>()
</script>

<template>
  <span class="badge" :class="variant">{{ label }}</span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.55rem;
  border-radius: 5px;
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.35;
  letter-spacing: 0.01em;
}
.preset {
  background: var(--deid-preset-bg);
  color: var(--deid-preset);
}
.manual {
  background: var(--deid-manual-bg);
  color: var(--deid-manual);
}
.draft {
  background: var(--deid-badge-draft-bg);
  color: var(--deid-badge-draft-fg);
}
.scanned {
  background: var(--deid-badge-scanned-bg);
  color: var(--deid-badge-scanned-fg);
}
.done {
  background: var(--deid-success-bg);
  color: var(--deid-success);
}
.failed {
  background: var(--deid-danger-bg);
  color: var(--deid-danger);
}
.running {
  background: var(--deid-badge-running-bg);
  color: var(--deid-badge-running-fg);
}
.llm {
  background: var(--deid-llm-bg);
  color: var(--deid-llm);
}
.rule,
.pattern {
  background: var(--deid-surface-2);
  color: var(--deid-ink-secondary);
}
</style>
