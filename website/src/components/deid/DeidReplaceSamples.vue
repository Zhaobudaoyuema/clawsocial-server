<script setup lang="ts">
defineProps<{
  previews: { before: string; after: string }[]
}>()
</script>

<template>
  <section v-if="previews.length" class="samples deid-panel">
    <h3 class="title">替换抽样</h3>
    <ul class="sample-list">
      <li v-for="(p, i) in previews.slice(0, 3)" :key="i" class="sample-item">
        <div class="before">{{ p.before }}</div>
        <div class="arrow">→</div>
        <div class="after deid-mono">{{ p.after }}</div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.title {
  margin: 0 0 1rem;
  font-size: 0.9375rem;
  font-weight: 600;
}
.sample-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.sample-item {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0.5rem;
  align-items: start;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--deid-border);
  font-size: 0.8125rem;
}
.sample-item:last-child {
  border-bottom: none;
}
.before {
  color: var(--deid-ink-muted);
  word-break: break-all;
}
.arrow {
  color: var(--deid-ink-muted);
  padding-top: 0.1rem;
}
.after {
  color: var(--deid-primary);
  word-break: break-all;
}
</style>
