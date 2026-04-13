<template>
  <aside class="blog-section">
    <h2 class="blog-section-title">博客</h2>

    <!-- 加载中 -->
    <div v-if="loading" class="blog-loading">
      <div class="loading-dot" /><div class="loading-dot" /><div class="loading-dot" />
    </div>

    <!-- 加载失败 -->
    <div v-else-if="error" class="blog-error">
      <p>加载失败</p>
      <button class="retry-btn" @click="load">重试</button>
    </div>

    <!-- 空状态 -->
    <div v-else-if="items.length === 0" class="blog-empty">
      <p>暂无文章</p>
    </div>

    <!-- 博客内容 -->
    <div v-else class="blog-accordion">
      <!-- 文件夹列表 -->
      <div v-for="item in folders" :key="item.path" class="blog-folder">
        <button class="folder-header" @click="toggle(item)">
          <span class="folder-icon">{{ item.open ? '▼' : '▶' }}</span>
          <span class="folder-name">{{ item.name }}</span>
          <span class="folder-count">{{ item.children.length }}</span>
        </button>
        <div v-if="item.open" class="folder-content">
          <BlogCard
            v-for="file in item.children"
            :key="file.slug"
            :file="file"
          />
        </div>
      </div>

      <!-- 根级文件 -->
      <div v-if="rootFiles.length" class="root-files">
        <BlogCard
          v-for="file in rootFiles"
          :key="file.slug"
          :file="file"
        />
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import BlogCard from './BlogCard.vue'

interface BlogItem {
  type: 'folder' | 'file'
  name: string
  slug?: string
  path: string
  children?: BlogItem[]
  open?: boolean
}

const items = ref<BlogItem[]>([])
const loading = ref(true)
const error = ref(false)

const folders = computed(() =>
  items.value
    .filter(i => i.type === 'folder')
    .map(i => ({ ...i, open: false }))
)

const rootFiles = computed(() =>
  items.value.filter(i => i.type === 'file')
)

async function load() {
  loading.value = true
  error.value = false
  try {
    const res = await fetch('/api/blog/list')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    items.value = data.items ?? []
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

function toggle(item: BlogItem) {
  item.open = !item.open
}

onMounted(load)
</script>

<style scoped>
.blog-section {
  max-width: 900px;
  margin: 0 auto;
  padding: 3rem 1.5rem;
}

.blog-section-title {
  font-size: 1.5rem;
  color: #3d2c24;
  font-weight: 700;
  margin: 0 0 1.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #E8623A;
  display: inline-block;
}

/* 加载动画 */
.blog-loading {
  display: flex;
  gap: 0.5rem;
  justify-content: center;
  padding: 2rem;
}

.loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #E8623A;
  animation: bounce 0.6s infinite alternate;
}

.loading-dot:nth-child(2) { animation-delay: 0.2s; }
.loading-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  from { opacity: 0.3; transform: translateY(0); }
  to   { opacity: 1;   transform: translateY(-6px); }
}

/* 错误 / 空状态 */
.blog-error,
.blog-empty {
  text-align: center;
  padding: 2rem;
  color: #8b7b6e;
}

.retry-btn {
  margin-top: 0.75rem;
  padding: 0.4rem 1rem;
  background: #E8623A;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
}

/* 手风琴 */
.blog-accordion {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.blog-folder {
  border: 1px solid #f0e6d8;
  border-radius: 10px;
  overflow: hidden;
}

.folder-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(232, 98, 58, 0.06);
  border: none;
  cursor: pointer;
  text-align: left;
  font-size: 0.95rem;
  color: #3d2c24;
  font-weight: 600;
  transition: background 0.15s;
}

.folder-header:hover {
  background: rgba(232, 98, 58, 0.12);
}

.folder-icon {
  font-size: 0.7rem;
  color: #E8623A;
  width: 1rem;
}

.folder-name {
  flex: 1;
}

.folder-count {
  background: rgba(232, 98, 58, 0.15);
  color: #E8623A;
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: 99px;
}

.folder-content {
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  background: #fff;
}

.root-files {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
</style>
