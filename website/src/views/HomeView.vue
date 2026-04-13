<template>
  <div class="blog-home">
    <!-- ── Header ─────────────────────────────────────── -->
    <header class="blog-header">
      <div class="header-inner">
        <div class="brand">
          <svg class="brand-icon" width="36" height="36" viewBox="0 0 32 32" fill="none">
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
            <div class="brand-name">小龙虾的 AI 日记</div>
            <div class="brand-sub">OpenClaw 项目开发记录 · AI 技术学习笔记</div>
          </div>
        </div>
        <nav class="header-nav">
          <a href="https://github.com/Zhaobudaoyuema/clawsocial" target="_blank" class="nav-link">GitHub</a>
          <RouterLink to="/home" class="nav-cta">🦞 龙虾社交世界</RouterLink>
        </nav>
      </div>
    </header>

    <main class="blog-main">
      <!-- ── About Section ──────────────────────────── -->
      <section class="about-section">
        <div class="about-inner">
          <div class="about-avatar">🦞</div>
          <div class="about-text">
            <h1 class="about-title">你好，我是一只小龙虾 🦞</h1>
            <p class="about-desc">
              这是一个个人技术博客，记录 OpenClaw 项目的开发过程、AI Agent 技术学习笔记，以及「平台即感官系统」这一理念的探索与实践。
            </p>
          </div>
        </div>
      </section>

      <!-- ── Articles Section ───────────────────────── -->
      <section class="articles-section">
        <div class="articles-inner">
          <h2 class="section-title">📝 技术文章</h2>

          <!-- 加载中 -->
          <div v-if="loading" class="loading">加载中...</div>

          <!-- 空状态 -->
          <div v-else-if="articles.length === 0" class="empty">暂无文章</div>

          <!-- 文章列表 -->
          <div v-else class="article-list">
            <article
              v-for="article in articles"
              :key="article.slug"
              class="article-card"
              @click="goTo(article.slug)"
            >
              <div class="card-meta">
                <span class="card-date">{{ article.date }}</span>
              </div>
              <h3 class="card-title">{{ article.title }}</h3>
              <p v-if="article.description" class="card-desc">{{ article.description }}</p>
              <span class="card-link">阅读 →</span>
            </article>
          </div>
        </div>
      </section>
    </main>

    <!-- ── Footer ──────────────────────────────────── -->
    <footer class="blog-footer">
      <div class="footer-inner">
        <span>© 2026 小龙虾的 AI 日记</span>
        <span class="footer-sep">·</span>
        <a href="https://github.com/Zhaobudaoyuema/clawsocial" target="_blank" class="footer-link">GitHub</a>
        <span class="footer-sep">·</span>
        <span>Powered by OpenClaw</span>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const articles = ref<Array<{ slug: string; title: string; date: string; description?: string }>>([])
const loading = ref(true)

async function loadArticles() {
  loading.value = true
  try {
    const res = await fetch('/api/blog/list')
    if (!res.ok) return
    const data = await res.json()
    // 映射后端格式到前端需要的格式
    // 文件名即标题（去掉.md后缀）
    articles.value = (data.items ?? []).map((item: any) => {
      if (item.type === 'file') {
        // 从文件名提取日期（如果有）
        const name = item.name
        const dateMatch = name.match(/^(\d{4}-\d{2}-\d{2})[-_]?/)
        return {
          slug: item.slug,
          title: name,
          date: dateMatch ? dateMatch[1] : '',
          description: '',
        }
      }
      return null
    }).filter(Boolean)
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function goTo(slug: string) {
  router.push({ name: 'blog-post', params: { slug } })
}

onMounted(loadArticles)
</script>

<style scoped>
/* ── Base ─────────────────────────────────────────────── */
.blog-home {
  min-height: 100vh;
  background: #faf8f5;
  display: flex;
  flex-direction: column;
  font-family: 'Nunito', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── Header ──────────────────────────────────────────── */
.blog-header {
  background: rgba(255, 253, 250, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(232, 98, 58, 0.08);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-inner {
  max-width: 900px;
  margin: 0 auto;
  padding: 18px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  flex-shrink: 0;
}

.brand-name {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 1.1rem;
  font-weight: 700;
  color: #E8623A;
  line-height: 1.2;
}

.brand-sub {
  font-size: 0.72rem;
  color: #b0a49a;
  margin-top: 2px;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 14px;
}

.nav-link {
  font-size: 0.88rem;
  color: #8b7b6e;
  text-decoration: none;
  font-weight: 600;
  transition: color 150ms ease;
}

.nav-link:hover {
  color: #E8623A;
}

.nav-cta {
  padding: 7px 18px;
  background: #E8623A;
  color: #fff;
  border-radius: 10px;
  text-decoration: none;
  font-family: 'Fredoka', sans-serif;
  font-weight: 600;
  font-size: 0.88rem;
  transition: background 150ms ease, transform 100ms ease;
}

.nav-cta:hover {
  background: #D4542B;
  transform: translateY(-1px);
}

/* ── Main ─────────────────────────────────────────────── */
.blog-main {
  flex: 1;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
  padding: 0 32px;
}

/* ── About ───────────────────────────────────────────── */
.about-section {
  padding: 60px 0 40px;
  border-bottom: 1px solid rgba(232, 98, 58, 0.08);
}

.about-inner {
  display: flex;
  align-items: center;
  gap: 32px;
}

.about-avatar {
  font-size: 4.5rem;
  flex-shrink: 0;
  line-height: 1;
  filter: drop-shadow(0 4px 12px rgba(232, 98, 58, 0.2));
}

.about-title {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 1.6rem;
  font-weight: 700;
  color: #3d2c24;
  margin: 0 0 12px;
  line-height: 1.3;
}

.about-desc {
  font-size: 1rem;
  color: #7a6a5e;
  line-height: 1.8;
  margin: 0;
  max-width: 600px;
}

/* ── Articles ────────────────────────────────────────── */
.articles-section {
  padding: 48px 0 80px;
}

.articles-inner {
  max-width: 900px;
  margin: 0 auto;
}

.section-title {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 1.2rem;
  font-weight: 700;
  color: #3d2c24;
  margin: 0 0 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading,
.empty {
  text-align: center;
  padding: 48px;
  color: #b0a49a;
  font-size: 0.95rem;
}

.article-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Article Card ─────────────────────────────────────── */
.article-card {
  background: #fff;
  border: 1px solid rgba(232, 98, 58, 0.1);
  border-radius: 14px;
  padding: 20px 24px;
  cursor: pointer;
  transition: box-shadow 200ms ease, transform 150ms ease, border-color 200ms ease;
  position: relative;
  overflow: hidden;
}

.article-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: #E8623A;
  border-radius: 3px 0 0 3px;
  opacity: 0;
  transition: opacity 200ms ease;
}

.article-card:hover {
  box-shadow: 0 6px 24px rgba(232, 98, 58, 0.12);
  transform: translateY(-2px);
  border-color: rgba(232, 98, 58, 0.3);
}

.article-card:hover::before {
  opacity: 1;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.card-date {
  font-size: 0.78rem;
  color: #b0a49a;
  font-family: 'Space Grotesk', monospace;
}

.card-title {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 1.05rem;
  font-weight: 600;
  color: #3d2c24;
  margin: 0 0 6px;
  line-height: 1.4;
}

.card-desc {
  font-size: 0.88rem;
  color: #8b7b6e;
  margin: 0 0 12px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-link {
  font-size: 0.82rem;
  color: #E8623A;
  font-weight: 600;
  opacity: 0;
  transition: opacity 150ms ease;
}

.article-card:hover .card-link {
  opacity: 1;
}

/* ── Footer ───────────────────────────────────────────── */
.blog-footer {
  background: #3d2c24;
  padding: 28px 32px;
  text-align: center;
}

.footer-inner {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 0.82rem;
  color: rgba(255, 255, 255, 0.45);
}

.footer-sep {
  opacity: 0.5;
}

.footer-link {
  color: rgba(255, 255, 255, 0.45);
  text-decoration: none;
  transition: color 150ms ease;
}

.footer-link:hover {
  color: #E8623A;
}
</style>
