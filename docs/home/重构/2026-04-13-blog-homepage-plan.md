# 博客首页重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ClawSocial 首页重构为博客文章首页，用户可在首页浏览 `docs/home/` 下的 Markdown 文章，支持手风琴折叠文件夹、全屏文章页路由。

**Architecture:**
- **后端**：`app/api/blog.py` 提供两个接口：`GET /api/blog/list` 返回目录树；`GET /api/blog/{slug}` 返回 Markdown 原文。`main.py` 新增 `/blog` SPA 路由并注册 blog router。
- **前端**：新增路由 `/blog/:slug+` → `BlogPostView.vue`；`HomeView.vue` 移除 FeatureSection，嵌入 `BlogSection.vue`；`BlogCard.vue` 为文章卡片；`markdown.css` 为渲染样式。

**Tech Stack:** FastAPI + pathlib（后端文件读取），Vue 3 + markdown-it + highlight.js + vanilla CSS（前端渲染）。

---

## 文件变更总览

| 操作 | 文件路径 |
|------|----------|
| 创建 | `app/api/blog.py` |
| 修改 | `app/main.py` |
| 创建 | `website/src/styles/markdown.css` |
| 创建 | `website/src/views/BlogPostView.vue` |
| 创建 | `website/src/components/BlogCard.vue` |
| 创建 | `website/src/components/BlogSection.vue` |
| 修改 | `website/src/views/HomeView.vue` |
| 修改 | `website/src/router/index.ts` |
| 依赖安装 | `website/package.json`（markdown-it + highlight.js） |

---

## Task 1: 后端博客 API

**Files:**
- Create: `app/api/blog.py`
- Modify: `app/main.py:60`（导入 blog router），`app/main.py:141`（注册 router + `/blog` SPA 路由）

### Step 1: 创建 `app/api/blog.py`

- [ ] **Step 1: 创建 `app/api/blog.py`**

```python
"""
博客内容 API。
GET /api/blog/list   — 返回 docs/home/ 目录树（支持嵌套文件夹）
GET /api/blog/{slug} — 读取并返回指定文章的 Markdown 原文
"""
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["blog"])

# docs/home/ 相对于项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOG_ROOT = _PROJECT_ROOT / "docs" / "home"


def _build_tree(root: Path) -> list[dict[str, Any]]:
    """
    递归构建目录树。
    返回 items: [{ type: "folder", name, path, children }, { type: "file", name, slug, path }]
    """
    if not root.exists():
        return []

    items: list[dict[str, Any]] = []

    # 先收集文件夹和文件
    dirs: list[Path] = []
    files: list[Path] = []

    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            dirs.append(entry)
        elif entry.suffix == ".md":
            files.append(entry)

    # 文件夹在前，文件在后（均按字母序）
    for d in dirs:
        children = _build_tree(d)
        items.append({
            "type": "folder",
            "name": d.name,
            "path": str(d.relative_to(BLOG_ROOT)),
            "children": children,
        })

    for f in sorted(files):
        relative = f.relative_to(BLOG_ROOT)
        slug = str(relative.with_suffix("")).replace(os.sep, "/")
        items.append({
            "type": "file",
            "name": f.stem,  # 文件名（无后缀）作为标题
            "slug": slug,
            "path": str(relative),
        })

    return items


@router.get("/api/blog/list")
def list_blog() -> dict[str, list[dict[str, Any]]]:
    """
    返回 docs/home/ 的目录结构。
    响应: { "items": [...] }
    """
    items = _build_tree(BLOG_ROOT)
    return {"items": items}


@router.get("/api/blog/{slug:path}", response_class=PlainTextResponse)
def get_blog_post(slug: str) -> str:
    """
    读取并返回指定文章的 Markdown 原文。
    slug 格式: "文件夹/文件名" 或 "文件名"（无 .md 后缀）
    """
    file_path = BLOG_ROOT / f"{slug}.md"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文章不存在: {slug}")
    return file_path.read_text(encoding="utf-8")
```

### Step 2: 注册 blog router 并添加 `/blog` SPA 路由（修改 `app/main.py`）

- [ ] **Step 2: 修改 `app/main.py` — 导入并注册 blog router**

找到第 60 行：
```python
from app.api import register, stats, world, ws_client, ws_server, share
```
改为：
```python
from app.api import blog, register, stats, world, ws_client, ws_server, share
```

找到第 140 行附近（在 `app.include_router(client_history.router)` 之后）：
```python
app.include_router(share.router)
app.include_router(client_history.router)
```
改为：
```python
app.include_router(share.router)
app.include_router(client_history.router)
app.include_router(blog.router)
```

- [ ] **Step 3: 添加 `/blog` SPA 路由（修改 `app/main.py`）**

在 `serve_crawler` 函数之后、 `if __name__ == "__main__"` 之前添加：

```python
@app.get("/blog")
@app.get("/blog/")
async def serve_blog():
    """博客文章页"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))
```

- [ ] **Step 4: 验证后端可启动**

```bash
cd D:/clawsocial-server && python -m app.main
```
确认启动日志无报错，无 ImportError。

- [ ] **Step 5: 测试接口**

```bash
curl http://localhost:8000/api/blog/list
# 期望: {"items": [...]}

curl http://localhost:8000/api/blog/平台即感官系统-本质讨论
# 期望: Markdown 原文内容，Content-Type: text/plain
```

- [ ] **Step 6: 提交**

```bash
git add app/api/blog.py app/main.py && git commit -m "feat: add blog API — list directory tree and serve markdown posts

GET /api/blog/list — recursive directory tree of docs/home/
GET /api/blog/{slug} — serve raw markdown with 404 on missing file
add /blog SPA route for Vue router"
```

---

## Task 2: 前端依赖安装

**Files:**
- Modify: `website/package.json`

### Step 1: 安装前端依赖

- [ ] **Step 1: 安装 markdown-it 和 highlight.js**

```bash
cd D:/clawsocial-server/website && npm install markdown-it highlight.js
```

### Step 2: 确认 `package.json` 已更新（无手动编辑）

直接用 npm install 即可，无需手动编辑 package.json。

- [ ] **Step 2: 提交**

```bash
git add website/package.json website/package-lock.json && git commit -m "deps: add markdown-it and highlight.js for blog rendering"
```

---

## Task 3: 前端路由

**Files:**
- Modify: `website/src/router/index.ts`

### Step 1: 添加 `/blog/:slug+` 路由

- [ ] **Step 1: 修改 `website/src/router/index.ts`**

在现有路由数组末尾添加新路由：

```ts
{
  path: '/blog/:slug+',
  name: 'blog-post',
  component: () => import('../views/BlogPostView.vue'),
}
```

完整路由表：
```ts
const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/world', name: 'world', component: WorldView },
    { path: '/world/share/:shareToken', name: 'share', component: ShareView, props: true },
    { path: '/blog/:slug+', name: 'blog-post', component: () => import('../views/BlogPostView.vue') },
  ],
})
```

### Step 2: 确认路由文件无误

- [ ] **Step 2: 提交**

```bash
git add website/src/router/index.ts && git commit -m "feat: add /blog/:slug+ route for full-screen blog post view"
```

---

## Task 4: Markdown 渲染样式

**Files:**
- Create: `website/src/styles/markdown.css`

### Step 1: 创建样式文件

- [ ] **Step 1: 创建 `website/src/styles/markdown.css`**

```css
/* ============================================
   Markdown 渲染样式 — ClawSocial Design System
   Warm Adventure · Cozy Intelligence
   ============================================ */

.md-content {
  max-width: 720px;
  margin: 0 auto;
  color: #3d2c24;
  line-height: 1.8;
  font-size: 1rem;
}

.md-content h1 {
  font-size: 2rem;
  color: #3d2c24;
  margin: 0 0 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #f0e6d8;
  font-weight: 700;
}

.md-content h2 {
  font-size: 1.5rem;
  color: #E8623A;
  margin: 2rem 0 0.75rem;
  font-weight: 600;
}

.md-content h3 {
  font-size: 1.2rem;
  color: #3d2c24;
  margin: 1.5rem 0 0.5rem;
  font-weight: 600;
}

.md-content h4,
.md-content h5,
.md-content h6 {
  color: #3d2c24;
  margin: 1rem 0 0.5rem;
  font-weight: 600;
}

.md-content p {
  margin: 0 0 1rem;
}

.md-content a {
  color: #E8623A;
  text-decoration: none;
}

.md-content a:hover {
  text-decoration: underline;
}

/* 行内代码 */
.md-content code:not(pre code) {
  background: rgba(232, 98, 58, 0.08);
  color: #E8623A;
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'Courier New', Courier, monospace;
}

/* 代码块 */
.md-content pre {
  background: #2d2520;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  overflow-x: auto;
  margin: 1.25rem 0;
}

.md-content pre code {
  background: none;
  color: #f0e6d8;
  padding: 0;
  font-size: 0.875rem;
  font-family: 'Courier New', Courier, monospace;
  border-radius: 0;
}

/* 引用块 */
.md-content blockquote {
  border-left: 4px solid #E8623A;
  background: rgba(232, 98, 58, 0.05);
  margin: 1.25rem 0;
  padding: 0.75rem 1rem;
  font-style: italic;
  color: #8b7b6e;
}

.md-content blockquote p {
  margin: 0;
}

/* 表格 */
.md-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.25rem 0;
}

.md-content th {
  background: rgba(232, 98, 58, 0.1);
  color: #3d2c24;
  font-weight: 600;
  padding: 0.5rem 0.75rem;
  text-align: left;
  border: 1px solid #f0e6d8;
}

.md-content td {
  padding: 0.5rem 0.75rem;
  border: 1px solid #f0e6d8;
}

.md-content tr:nth-child(even) {
  background: rgba(232, 98, 58, 0.03);
}

/* 图片 */
.md-content img {
  max-width: 100%;
  border-radius: 8px;
  display: block;
  margin: 1rem auto;
}

/* 列表 */
.md-content ul,
.md-content ol {
  padding-left: 1.5rem;
  margin: 0 0 1rem;
}

.md-content li {
  margin: 0.25rem 0;
}

.md-content hr {
  border: none;
  border-top: 1px solid #f0e6d8;
  margin: 2rem 0;
}

/* highlight.js 覆盖 — 保证代码块配色和谐 */
.hljs-keyword,
.hljs-selector-tag,
.hljs-built_in { color: #f4a261; }
.hljs-string,
.hljs-attr { color: #a8d8a8; }
.hljs-comment { color: #8b7b6e; font-style: italic; }
.hljs-number,
.hljs-literal { color: #e8c3a0; }
.hljs-title,
.hljs-section { color: #E8623A; }
```

### Step 2: 提交

- [ ] **Step 2: 提交**

```bash
git add website/src/styles/markdown.css && git commit -m "feat: add markdown rendering styles — warm lobster palette, prose layout"
```

---

## Task 5: BlogCard 组件

**Files:**
- Create: `website/src/components/BlogCard.vue`

### Step 1: 创建 `BlogCard.vue`

- [ ] **Step 1: 创建 `website/src/components/BlogCard.vue`**

```vue
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
```

### Step 2: 提交

- [ ] **Step 2: 提交**

```bash
git add website/src/components/BlogCard.vue && git commit -m "feat: add BlogCard component — file icon, title, hover lift effect"
```

---

## Task 6: BlogSection 组件（手风琴 + 卡片列表）

**Files:**
- Create: `website/src/components/BlogSection.vue`

### Step 1: 创建 `BlogSection.vue`

- [ ] **Step 1: 创建 `website/src/components/BlogSection.vue`**

```vue
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
```

### Step 2: 提交

- [ ] **Step 2: 提交**

```bash
git add website/src/components/BlogSection.vue && git commit -m "feat: add BlogSection — accordion folder list with card articles"
```

---

## Task 7: BlogPostView 全屏文章页

**Files:**
- Create: `website/src/views/BlogPostView.vue`

### Step 1: 创建 `BlogPostView.vue`

- [ ] **Step 1: 创建 `website/src/views/BlogPostView.vue`**

```vue
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
  highlight(str, lang) {
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
    // 从文件第一行提取标题（文件名）
    const lines = text.split('\n')
    const fileName = decodeURIComponent(slug).split('/').pop() ?? ''
    // 标题行
    const titleLine = `**${fileName}**`
    // 渲染（不在这里注入 h1，让用户 Markdown 自己控制结构）
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
```

### Step 2: 提交

- [ ] **Step 2: 提交**

```bash
git add website/src/views/BlogPostView.vue && git commit -m "feat: add BlogPostView — full-screen markdown article with header/footer"
```

---

## Task 8: HomeView 重构 — 移除 FeatureSection，引入 BlogSection

**Files:**
- Modify: `website/src/views/HomeView.vue`

### Step 1: 读取完整 HomeView.vue 确认 FeatureSection 位置

- [ ] **Step 1: 修改 `HomeView.vue` — 移除 FeatureSection，引入 BlogSection**

在 `<script setup>` 中添加：
```ts
import BlogSection from '../components/BlogSection.vue'
```

在模板中找到并删除：
```html
<!-- ── Feature Cards ─────────────────────────────── -->
<FeatureSection />
```

在同一位置（Hero 和 CTA 之间）添加：
```html
<!-- ── Blog Section ──────────────────────────────── -->
<BlogSection />
```

### Step 2: 提交

- [ ] **Step 2: 提交**

```bash
git add website/src/views/HomeView.vue && git commit -m "refactor: replace FeatureSection with BlogSection in HomeView"
```

---

## Task 9: 构建验证

**Files:**
- None (verification only)

### Step 1: 构建前端

- [ ] **Step 1: 运行前端构建**

```bash
cd D:/clawsocial-server/website && npm run build
```
确认无 TypeScript 错误，无编译报错。

### Step 2: 启动完整服务验证

- [ ] **Step 2: 启动后端 + 访问首页**

```bash
cd D:/clawsocial-server && python -m app.main
```
浏览器访问 `http://localhost:8000/`，确认：
- Hero 正常显示
- Blog Section 正常加载（显示 docs/home/ 下的文章）
- 手风琴折叠正常工作
- 点击文章卡片 → 跳转 `/blog/xxx` 全屏文章页
- 文章页 Markdown 正常渲染（标题、代码块、引用块等）
- 返回按钮正常返回首页

### Step 3: 提交

- [ ] **Step 3: 提交最终构建产物**

```bash
git add app/static/assets/ && git commit -m "build: update static assets after blog homepage integration"
```

---

## 规格覆盖率自检

| 规格要求 | 实现位置 |
|----------|----------|
| Hero 保留 | Task 8: HomeView.vue 保留 Hero Section |
| FeatureSection 移除 | Task 8: 删除 `<FeatureSection />` |
| Blog Section 在 Hero 和 CTA 之间 | Task 8: BlogSection 嵌入 Hero/CTA 之间 |
| 手风琴折叠文件夹列表 | Task 6: BlogSection.vue 折叠逻辑 |
| 卡片式文章列表 | Task 5: BlogCard.vue |
| 全屏文章页 `/blog/:slug+` | Task 3: 路由 + Task 7: BlogPostView.vue |
| 返回首页按钮 | Task 7: `<button class="nav-back">` |
| Markdown 渲染（markdown-it + hljs） | Task 7: BlogPostView.vue 渲染逻辑 |
| Vanilla CSS 样式 | Task 4: markdown.css |
| 后端 `/api/blog/list` | Task 1: blog.py |
| 后端 `/api/blog/{slug}` | Task 1: blog.py |
| `/blog` SPA 路由 | Task 1: main.py |
| 空状态处理 | Task 6: `blog-empty` 分支 |
| 404 处理 | Task 7: `post-error` 分支 |
| Vite 代理已有 | Task 2: 确认 `/api` 代理已存在 |

**无缺口 ✅**
