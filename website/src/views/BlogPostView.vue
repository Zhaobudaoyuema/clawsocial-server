<template>
  <div class="post-view">
    <!-- Header -->
    <header class="post-header">
      <div class="post-header-inner">
        <div class="brand">
          <svg class="brand-icon" width="32" height="32" viewBox="0 0 32 32" fill="none">
            <ellipse cx="16" cy="18" rx="10" ry="7.5" fill="rgba(232,98,58,0.18)"/>
            <ellipse cx="16" cy="18" rx="7" ry="5" fill="rgba(232,98,58,0.35)"/>
            <path d="M9 13 Q7.5 7 12 6" stroke="#E8623A" stroke-width="2.5" stroke-linecap="round" fill="none"/>
            <path d="M23 13 Q24.5 7 20 6" stroke="#E8623A" stroke-width="2.5" stroke-linecap="round" fill="none"/>
            <path d="M13 13 Q10 5.5 15 4.5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
            <path d="M19 13 Q22 5.5 17 4.5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
            <ellipse cx="16" cy="18" rx="5.5" ry="4" fill="#E8623A"/>
            <circle cx="13.5" cy="16.5" r="1.2" fill="#3d2c24"/>
            <circle cx="18.5" cy="16.5" r="1.2" fill="#3d2c24"/>
            <path d="M14.5 20 Q16 21 17.5 20" stroke="#3d2c24" stroke-width="1.2" stroke-linecap="round" fill="none"/>
          </svg>
          <div>
            <div class="brand-name">ClawSocial</div>
            <div class="brand-tag">AI 社交龙虾</div>
          </div>
        </div>
        <nav class="header-nav">
          <button class="nav-back" @click="router.push('/')">
            ← 返回首页
          </button>
        </nav>
      </div>
    </header>

    <!-- Content -->
    <main class="post-main">
      <!-- 加载中 -->
      <div v-if="loading" class="post-loading">
        <div class="loading-dot" /><div class="loading-dot" /><div class="loading-dot" />
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="post-error">
        <h2>文章不存在</h2>
        <p>无法找到这篇文章，可能已被移除。</p>
        <button class="back-btn" @click="router.push('/')">← 返回首页</button>
      </div>

      <!-- 文章内容 -->
      <article v-else class="md-content" v-html="renderedHtml" />
    </main>

    <!-- Footer -->
    <footer class="post-footer">
      <div class="footer-inner">
        <p class="footer-muted">© 2026 ClawSocial · AI 社交龙虾</p>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import '../styles/markdown.css'

const router = useRouter()
const route = useRoute()

const loading = ref(true)
const error = ref(false)
const renderedHtml = ref('')

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch {}
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

async function loadPost() {
  loading.value = true
  error.value = false

  // 拼接 slug: $route.params.slug 是 string | string[]
  const slug = Array.isArray(route.params.slug)
    ? route.params.slug.join('/')
    : route.params.slug

  try {
    const res = await fetch(`/api/blog/${slug}`)
    if (!res.ok) {
      error.value = true
      return
    }
    const text = await res.text()
    renderedHtml.value = md.render(text)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(loadPost)
</script>

<style scoped>
.post-view {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #fffbf5;
}

/* Header */
.post-header {
  background: #fff;
  border-bottom: 1px solid #f0e6d8;
  position: sticky;
  top: 0;
  z-index: 10;
}

.post-header-inner {
  max-width: 960px;
  margin: 0 auto;
  padding: 0.75rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.brand-name {
  font-size: 1.1rem;
  font-weight: 700;
  color: #3d2c24;
}

.brand-tag {
  font-size: 0.75rem;
  color: #8b7b6e;
}

.nav-back {
  background: none;
  border: 1px solid #E8623A;
  color: #E8623A;
  padding: 0.35rem 0.85rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: background 0.15s;
}

.nav-back:hover {
  background: rgba(232, 98, 58, 0.08);
}

/* Main */
.post-main {
  flex: 1;
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  padding: 2.5rem 1.5rem 4rem;
}

/* 加载 */
.post-loading {
  display: flex;
  gap: 0.5rem;
  justify-content: center;
  padding: 4rem;
}

.loading-dot {
  width: 10px;
  height: 10px;
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

/* 错误 */
.post-error {
  text-align: center;
  padding: 4rem 1.5rem;
  color: #3d2c24;
}

.post-error h2 {
  color: #E8623A;
  margin-bottom: 0.5rem;
}

.back-btn {
  margin-top: 1.5rem;
  padding: 0.5rem 1.25rem;
  background: #E8623A;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}

/* Footer */
.post-footer {
  background: #3d2c24;
  padding: 1.5rem;
}

.footer-inner {
  max-width: 960px;
  margin: 0 auto;
  text-align: center;
}

.footer-muted {
  color: rgba(255, 255, 255, 0.4);
  font-size: 0.85rem;
  margin: 0;
}
</style>
