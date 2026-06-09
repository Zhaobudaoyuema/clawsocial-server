<script setup lang="ts">
defineProps<{
  passed?: boolean
  summary?: string
  residuals?: string[]
}>()
</script>

<template>
  <div
    class="card"
    :class="passed ? 'ok' : 'err'"
    role="status"
    aria-live="polite"
  >
    <div class="head">
      <span class="icon">{{ passed ? '✓' : '✕' }}</span>
      <div>
        <h3>{{ passed ? '验证通过' : '验证未通过' }}</h3>
        <p v-if="summary" class="sub">{{ summary }}</p>
      </div>
    </div>
    <details v-if="!passed && residuals?.length" class="details">
      <summary>展开残留明细（{{ residuals.length }} 处）</summary>
      <ul>
        <li v-for="(r, i) in residuals" :key="i" class="deid-mono">{{ r }}</li>
      </ul>
    </details>
    <slot />
  </div>
</template>

<style scoped>
.card {
  border-radius: var(--deid-radius);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
}
.ok {
  background: var(--deid-success-bg);
  border: 1px solid var(--deid-success-border);
}
.err {
  background: var(--deid-danger-bg);
  border: 1px solid var(--deid-danger-border);
}
.head {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
}
.icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}
.ok .icon {
  background: var(--deid-success);
  color: #fff;
}
.err .icon {
  background: var(--deid-danger);
  color: #fff;
}
h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}
.sub {
  margin: 0.35rem 0 0;
  font-size: 1rem;
  color: var(--deid-ink-muted);
}
.details {
  margin-top: 1rem;
  font-size: 0.8125rem;
}
.details summary {
  cursor: pointer;
  color: var(--deid-danger);
  font-weight: 500;
}
.details ul {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}
</style>
