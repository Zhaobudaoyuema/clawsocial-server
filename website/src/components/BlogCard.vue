<template>
  <RouterLink :to="`/blog/${file.slug}`" class="blog-card">
    <div class="card-icon">📄</div>
    <div class="card-body">
      <div class="card-title">{{ file.name }}</div>
      <div class="card-hint">点击阅读 →</div>
    </div>
  </RouterLink>
</template>

<script setup lang="ts">
defineProps<{
  file: {
    name: string
    slug: string
    path: string
  }
}>()
</script>

<style scoped>
.blog-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: #fff;
  border: 1px solid rgba(232, 98, 58, 0.2);
  border-radius: 10px;
  text-decoration: none;
  color: #3d2c24;
  transition: box-shadow 0.2s ease, transform 0.15s ease;
  cursor: pointer;
}

.blog-card:hover {
  box-shadow: 0 4px 16px rgba(232, 98, 58, 0.18);
  transform: translateY(-1px);
  border-color: #E8623A;
}

.card-icon {
  font-size: 1.25rem;
  flex-shrink: 0;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-title {
  font-weight: 600;
  font-size: 0.95rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-hint {
  font-size: 0.78rem;
  color: #8b7b6e;
  margin-top: 0.15rem;
}
</style>
