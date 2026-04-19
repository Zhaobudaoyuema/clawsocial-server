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
      <!-- ── About Section（仅博客根路径显示） ─────────── -->
      <section v-if="!browsePrefix" class="about-section">
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

      <!-- ── Browse：文件夹分层 + 当前层文章 ───────────── -->
      <section class="articles-section">
        <div class="articles-inner">
          <h2 class="section-title">{{ browsePrefix ? '目录' : '文章' }}</h2>

          <div v-if="loading" class="loading">加载中...</div>

          <div v-else-if="browseInvalid" class="empty">
            找不到该文件夹
            <button type="button" class="back-link-btn" @click="goJournalRoot">← 返回博客首页</button>
          </div>

          <div v-else-if="currentFolders.length === 0 && currentFiles.length === 0" class="empty">
            暂无内容
          </div>

          <div v-else class="browse-stack">
            <!-- 面包屑：与 docs/home 设计稿 URL 分层一致，用 /journal/ 前缀浏览 -->
            <nav v-if="breadcrumb.length" class="breadcrumb" aria-label="面包屑">
              <button type="button" class="crumb" @click="goJournalRoot">首页</button>
              <template v-for="(c, i) in breadcrumb" :key="c.path">
                <span class="crumb-sep">/</span>
                <button
                  type="button"
                  class="crumb"
                  :class="{ 'crumb-current': i === breadcrumb.length - 1 }"
                  :disabled="i === breadcrumb.length - 1"
                  @click="goJournalPath(c.path)"
                >
                  {{ c.label }}
                </button>
              </template>
            </nav>

            <!-- 子文件夹：点击进入下一层 -->
            <div v-if="currentFolders.length" class="folder-list">
              <button
                v-for="folder in currentFolders"
                :key="folder.path"
                type="button"
                class="folder-row"
                @click="enterFolder(folder.name)"
              >
                <span class="folder-row-icon" aria-hidden="true">📁</span>
                <span class="folder-row-name">{{ folder.name }}</span>
                <span class="folder-row-meta">{{ folderChildCount(folder) }} 项</span>
                <span class="folder-row-chevron" aria-hidden="true">›</span>
              </button>
            </div>

            <!-- 当前目录下的文章 -->
            <div v-if="currentFiles.length" class="files-block">
              <h3 v-if="currentFolders.length" class="files-block-title">文章</h3>
              <div class="article-list">
                <article
                  v-for="file in fileRows"
                  :key="file.slug"
                  class="article-card"
                  @click="goToPost(file.slug)"
                >
                  <h3 class="card-title">{{ file.title }}</h3>
                  <div class="card-footer">
                    <span v-if="file.date" class="card-date">{{ formatDate(file.date) }}</span>
                    <span class="card-link">阅读 →</span>
                  </div>
                </article>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

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
import { ref, computed, onMounted } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

interface BlogFile {
  type: 'file'
  name: string
  slug: string
  path: string
}

interface BlogFolder {
  type: 'folder'
  name: string
  path: string
  children: BlogItem[]
}

type BlogItem = BlogFile | BlogFolder

const route = useRoute()
const router = useRouter()

const treeItems = ref<BlogItem[]>([])
const loading = ref(true)

function normalizePathMatch(raw: unknown): string {
  if (raw == null || raw === '') return ''
  if (Array.isArray(raw)) return raw.map(String).join('/')
  return String(raw)
}

/** 当前浏览的 docs/home 相对路径，如「重构」或「技术/笔记」；根为空 */
const browsePrefix = computed(() => {
  if (route.name !== 'journal-browse') return ''
  return normalizePathMatch(route.params.pathMatch)
})

function getChildrenAtPath(items: BlogItem[], prefix: string): BlogItem[] {
  if (!prefix) return items
  const segments = prefix.split('/').filter(Boolean)
  let level = items
  for (const seg of segments) {
    const folder = level.find(
      (i): i is BlogFolder => i.type === 'folder' && i.name === seg,
    )
    if (!folder?.children) return []
    level = folder.children
  }
  return level
}

const currentLevel = computed(() => getChildrenAtPath(treeItems.value, browsePrefix.value))

const currentFolders = computed(() =>
  currentLevel.value.filter((i): i is BlogFolder => i.type === 'folder'),
)

const currentFiles = computed(() =>
  currentLevel.value.filter((i): i is BlogFile => i.type === 'file'),
)

const browseInvalid = computed(() => {
  if (!browsePrefix.value) return false
  return currentLevel.value.length === 0
})

function folderChildCount(folder: BlogFolder): number {
  return folder.children?.length ?? 0
}

const breadcrumb = computed(() => {
  const p = browsePrefix.value
  if (!p) return []
  const segments = p.split('/').filter(Boolean)
  const out: { label: string; path: string }[] = []
  let acc = ''
  for (const seg of segments) {
    acc = acc ? `${acc}/${seg}` : seg
    out.push({ label: seg, path: acc })
  }
  return out
})

const fileRows = computed(() =>
  currentFiles.value.map((f) => {
    const dateMatch = f.name.match(/^(\d{4}-\d{2}-\d{2})[-_]?/)
    return {
      slug: f.slug,
      title: parseTitle(f.name),
      date: dateMatch ? dateMatch[1] : '',
    }
  }),
)

function parseTitle(name: string): string {
  const withoutDate = name.replace(/^\d{4}-\d{2}-\d{2}[-_]?/, '')
  const withoutExt = withoutDate.replace(/\.md$/, '')
  return withoutExt.replace(/[-_]/g, ' ').trim() || name
}

function formatDate(raw: string): string {
  if (!raw) return ''
  const [y, m, d] = raw.split('-')
  return `${y} 年 ${parseInt(m)} 月 ${parseInt(d)} 日`
}

async function loadTree() {
  loading.value = true
  try {
    const res = await fetch('/api/blog/list')
    if (!res.ok) return
    const data = await res.json()
    treeItems.value = data.items ?? []
  } catch {
    treeItems.value = []
  } finally {
    loading.value = false
  }
}

function enterFolder(name: string) {
  const next = browsePrefix.value ? `${browsePrefix.value}/${name}` : name
  router.push({
    name: 'journal-browse',
    params: { pathMatch: next },
  })
}

function goJournalPath(path: string) {
  router.push({ name: 'journal-browse', params: { pathMatch: path } })
}

function goJournalRoot() {
  router.push({ name: 'blog' })
}

function goToPost(slug: string) {
  router.push(`/blog/${slug}`)
}

onMounted(loadTree)
</script>

<style scoped>
.blog-home {
  min-height: 100vh;
  background: #faf8f5;
  display: flex;
  flex-direction: column;
  font-family: 'Inter', 'Nunito', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.blog-header {
  background: rgba(255, 253, 250, 0.97);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-inner {
  max-width: 900px;
  margin: 0 auto;
  padding: 16px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  flex-shrink: 0;
}

.brand-name {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 1.05rem;
  font-weight: 700;
  color: #E8623A;
  line-height: 1.2;
  letter-spacing: -0.2px;
}

.brand-sub {
  font-size: 0.7rem;
  color: #a39e98;
  margin-top: 2px;
  letter-spacing: 0.1px;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-link {
  font-size: 0.875rem;
  color: #615d59;
  text-decoration: none;
  font-weight: 500;
  transition: color 150ms ease;
}

.nav-link:hover {
  color: rgba(0, 0, 0, 0.9);
}

.nav-cta {
  padding: 6px 16px;
  background: #E8623A;
  color: #fff;
  border-radius: 6px;
  text-decoration: none;
  font-family: 'Fredoka', sans-serif;
  font-weight: 600;
  font-size: 0.875rem;
  transition: background 150ms ease, transform 100ms ease;
}

.nav-cta:hover {
  background: #d4542b;
  transform: translateY(-1px);
}

.blog-main {
  flex: 1;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
  padding: 0 32px;
}

.about-section {
  padding: 48px 0 36px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.about-inner {
  display: flex;
  align-items: center;
  gap: 28px;
}

.about-avatar {
  font-size: 4rem;
  flex-shrink: 0;
  line-height: 1;
  filter: drop-shadow(0 4px 12px rgba(232, 98, 58, 0.18));
}

.about-title {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 1.5rem;
  font-weight: 700;
  color: rgba(0, 0, 0, 0.9);
  margin: 0 0 10px;
  line-height: 1.3;
  letter-spacing: -0.5px;
}

.about-desc {
  font-size: 0.95rem;
  color: #615d59;
  line-height: 1.7;
  margin: 0;
  max-width: 580px;
}

.articles-section {
  padding: 40px 0 80px;
}

.articles-inner {
  max-width: 900px;
  margin: 0 auto;
}

.section-title {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 0.8rem;
  font-weight: 600;
  color: #a39e98;
  margin: 0 0 20px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.loading,
.empty {
  text-align: center;
  padding: 48px;
  color: #a39e98;
  font-size: 0.9rem;
}

.back-link-btn {
  display: block;
  margin: 16px auto 0;
  padding: 8px 16px;
  background: transparent;
  border: 1px solid rgba(232, 98, 58, 0.35);
  color: #e8623a;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.875rem;
}

.back-link-btn:hover {
  background: rgba(232, 98, 58, 0.08);
}

.browse-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  font-size: 0.85rem;
  color: #615d59;
}

.crumb {
  background: none;
  border: none;
  padding: 2px 4px;
  cursor: pointer;
  color: #e8623a;
  font: inherit;
  border-radius: 4px;
}

.crumb:hover:not(:disabled) {
  text-decoration: underline;
}

.crumb:disabled,
.crumb-current {
  color: #3d2c24;
  font-weight: 600;
  cursor: default;
  text-decoration: none;
}

.crumb-sep {
  color: #a39e98;
  user-select: none;
}

.folder-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.04);
}

.folder-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  text-align: left;
  padding: 18px 22px;
  background: #fff;
  border: none;
  cursor: pointer;
  transition: background 150ms ease;
  font: inherit;
}

.folder-row:hover {
  background: #faf8f5;
}

.folder-row-icon {
  font-size: 1.25rem;
  flex-shrink: 0;
}

.folder-row-name {
  flex: 1;
  font-weight: 600;
  font-size: 1rem;
  color: rgba(0, 0, 0, 0.85);
}

.folder-row-meta {
  font-size: 0.78rem;
  color: #a39e98;
}

.folder-row-chevron {
  font-size: 1.25rem;
  color: #e8623a;
  font-weight: 300;
  line-height: 1;
}

.files-block-title {
  font-family: 'Fredoka', 'PingFang SC', sans-serif;
  font-size: 0.85rem;
  font-weight: 600;
  color: #615d59;
  margin: 0 0 10px;
  padding-left: 2px;
}

.article-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.04);
}

.article-card {
  background: #fff;
  padding: 20px 24px;
  cursor: pointer;
  transition: background 150ms ease;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.article-card:hover {
  background: #faf8f5;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.85);
  margin: 0;
  line-height: 1.4;
  letter-spacing: -0.2px;
  flex: 1;
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

.card-date {
  font-size: 0.76rem;
  color: #a39e98;
  font-weight: 400;
  white-space: nowrap;
}

.card-link {
  font-size: 0.82rem;
  color: #e8623a;
  font-weight: 600;
  opacity: 0;
  transition: opacity 150ms ease;
  white-space: nowrap;
}

.article-card:hover .card-link {
  opacity: 1;
}

.blog-footer {
  background: #31302e;
  padding: 24px 32px;
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
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.35);
}

.footer-sep {
  opacity: 0.4;
}

.footer-link {
  color: rgba(255, 255, 255, 0.35);
  text-decoration: none;
  transition: color 150ms ease;
}

.footer-link:hover {
  color: rgba(255, 255, 255, 0.7);
}
</style>
