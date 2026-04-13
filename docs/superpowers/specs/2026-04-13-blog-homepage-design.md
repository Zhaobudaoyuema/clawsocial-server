# 博客首页重构设计

- **日期**: 2026-04-13
- **状态**: 已批准，待实施
- **背景**: 将 ClawSocial 首页从平台介绍页重构为以博客文章为核心的首页

---

## 1. 目标

将 `website/src/views/HomeView.vue` 从"平台介绍首页"重构为"博客文章首页"，同时保留 Hero 区域作为品牌入口。用户在首页可直接浏览 `docs/home/` 下的 Markdown 文章，无需登录。

---

## 2. 首页结构

```
┌─────────────────────────────────────┐
│  Header（品牌名 + 导航，保留）       │
├─────────────────────────────────────┤
│  Hero Section（保留，标题/副标题/CTA）│
├─────────────────────────────────────┤
│  Blog Section（新增，博客内容区）     │
│    ├── 折叠式文件夹列表              │
│    └── 卡片式文章列表                │
├─────────────────────────────────────┤
│  CTA Section（保留，"准备好认识..."）  │
├─────────────────────────────────────┤
│  Footer（保留）                      │
└─────────────────────────────────────┘
```

> FeatureSection（功能卡片区）完全移除，不保留。

---

## 3. 目录结构与 URL 映射

### 3.1 物理目录

```
docs/home/                      ← 博客内容根目录（由后端读取）
├── 技术/
│   ├── vue3-进阶.md
│   └── fastapi-入门.md
├── 随笔/
│   └── 2026-04-13-随手记.md
└── 平台即感官系统-本质讨论.md   ← 根级文章（无文件夹）
```

### 3.2 URL 映射规则

| 文件路径 | URL |
|----------|-----|
| `docs/home/技术/vue3-进阶.md` | `/blog/技术/vue3-进阶` |
| `docs/home/随笔/2026-04-13-随手记.md` | `/blog/随笔/2026-04-13-随手记` |
| `docs/home/平台即感官系统-本质讨论.md` | `/blog/平台即感官系统-本质讨论` |

**规则**: `/blog/文件夹名/文件名`（文件夹名不参与路径则文章直接在 `/blog/文件名`）。URL 无需 `.md` 后缀。

### 3.3 文章标题显示

文章标题 = 文件名（去除 `.md` 后缀），不解析元数据。

---

## 4. 后端接口

### 4.1 `GET /api/blog/list`

返回 `docs/home/` 的完整目录结构（支持嵌套文件夹）。

**响应示例**:

```json
{
  "items": [
    {
      "type": "folder",
      "name": "技术",
      "path": "技术",
      "children": [
        { "type": "file", "name": "vue3-进阶", "slug": "技术/vue3-进阶", "path": "技术/vue3-进阶.md" }
      ]
    },
    {
      "type": "file",
      "name": "平台即感官系统-本质讨论",
      "slug": "平台即感官系统-本质讨论",
      "path": "平台即感官系统-本质讨论.md"
    }
  ]
}
```

**实现要点**:
- 使用 `pathlib` 递归遍历 `docs/home/` 目录
- 文件夹排在前，文件排在后（字母序）
- 路径分隔符统一用 `/`
- 仅返回 `.md` 文件，忽略其他文件

### 4.2 `GET /api/blog/{slug}`

读取并返回指定文章的 Markdown 原始内容。

- `slug` 对应 URL 中的路径部分，如 `技术/vue3-进阶`
- 后端拼接为 `docs/home/{slug}.md`
- 返回 `Content-Type: text/markdown`，HTTP 200
- 文件不存在返回 404 JSON

---

## 5. 前端路由

### 5.1 新增路由

```ts
// website/src/router/index.ts
{
  path: '/blog/:slug+',         // slug+ 支持多级路径
  name: 'blog-post',
  component: () => import('../views/BlogPostView.vue'),
}
```

### 5.2 路由参数

| URL | `$route.params.slug` |
|-----|----------------------|
| `/blog/技术/vue3-进阶` | `['技术', 'vue3-进阶']` |

拼接 slug: `slug.join('/')` → `技术/vue3-进阶` → 请求 `/api/blog/技术/vue3-进阶`。

---

## 6. 组件设计

### 6.1 `BlogSection.vue`（新增，嵌入 HomeView）

位置：Hero 和 CTA 之间。结构：

```
<aside class="blog-section">
  <h2 class="blog-section-title">博客</h2>

  <!-- 手风琴折叠列表 -->
  <div class="blog-accordion">
    <div v-for="folder in folders" :key="folder.name" class="blog-folder">
      <button class="folder-header" @click="toggle(folder)">
        <span class="folder-icon">{{ folder.open ? '▼' : '▶' }}</span>
        <span class="folder-name">{{ folder.name }}</span>
        <span class="folder-count">{{ folder.children.length }}</span>
      </button>
      <div v-if="folder.open" class="folder-content">
        <BlogCard v-for="file in folder.children" :key="file.slug" :file="file" />
      </div>
    </div>

    <!-- 根级文件（无文件夹） -->
    <div class="root-files">
      <BlogCard v-for="file in rootFiles" :key="file.slug" :file="file" />
    </div>
  </div>
</aside>
```

### 6.2 `BlogCard.vue`（新增）

单个文章卡片，点击跳转到 `/blog/{slug}`。

```
┌────────────────────────────────────┐
│  📄  vue3-进阶                     │
│  点击阅读 →                        │
└────────────────────────────────────┘
```

样式：白底卡片，lobster 红色边框，hover 时微微上浮（`box-shadow` 加深）。

### 6.3 `BlogPostView.vue`（新增，全屏文章页）

全屏渲染 Markdown 内容。

```
┌─────────────────────────────────────┐
│  Header                            │
├─────────────────────────────────────┤
│  ← 返回首页                         │
│                                    │
│  # 文章标题（h1）                   │
│                                    │
│  [渲染后的 Markdown 内容]           │
│                                    │
├─────────────────────────────────────┤
│  Footer                            │
└─────────────────────────────────────┘
```

**Markdown 渲染流程**:
1. `onMounted` 时根据 `$route.params.slug` 拼接请求 `/api/blog/{slug}`
2. 用 `markdown-it` + `highlight.js` 将 Markdown 转为 HTML
3. 插入 `<div v-html="renderedHtml">` 渲染

**返回按钮**: 点击 → `router.push('/')`（回到首页，不是回到列表页）。

---

## 7. Markdown 渲染样式（vanilla CSS）

### 7.1 样式文件

新建 `website/src/styles/markdown.css`。

### 7.2 样式规则

遵循 ClawSocial 设计系统（Warm Adventure · Cozy Intelligence）:

| 元素 | 样式 |
|------|------|
| `h1` | `#3d2c24`，`font-size: 2rem`，下方 `1px solid #f0e6d8` 分隔线 |
| `h2` | `#E8623A`，`font-size: 1.5rem` |
| `h3` | `#3d2c24`，`font-size: 1.2rem` |
| `p` | `#3d2c24`，`line-height: 1.8` |
| `code`（行内）| 背景 `rgba(232,98,58,0.08)`，圆角 4px |
| `pre > code` | 深色背景 `#2d2520`，代码高亮由 `highlight.js` 主题覆盖 |
| `blockquote` | 左侧 `4px solid #E8623A`，背景 `rgba(232,98,58,0.05)`，斜体 |
| `a` | `#E8623A`，hover 加下划线 |
| `table` | 全宽，`th` 背景 `rgba(232,98,58,0.1)` |
| `img` | `max-width: 100%`，圆角 8px |

**引入位置**: `BlogPostView.vue` 中 `<style>` 引入 `@import '../styles/markdown.css'`。

---

## 8. Vite 开发代理

确保 `website/vite.config.ts` 中 `/api` 代理到 `:8000`（FastAPI 后端）。已有 World 相关代理可参考。

---

## 9. 实现顺序

1. **后端接口** → `app/api/blog.py`
   - `GET /api/blog/list`
   - `GET /api/blog/{slug}`
2. **前端路由** → `website/src/router/index.ts`
3. **`BlogSection.vue`** → 嵌入 `HomeView.vue`
4. **`BlogCard.vue`** → 文章卡片组件
5. **`markdown.css`** → Markdown 渲染样式
6. **`BlogPostView.vue`** → 全屏文章页
7. **HomeView.vue** → 移除 FeatureSection，引入 BlogSection
8. **测试** → 文章列表加载、手风琴折叠、文章详情渲染

---

## 10. 错误处理

| 场景 | 处理 |
|------|------|
| `docs/home/` 不存在或为空 | 返回 `items: []`，BlogSection 区域显示"暂无文章" |
| 文章文件不存在（slug 404） | 渲染 404 提示页，返回首页按钮 |
| Markdown 内容读取失败 | 错误日志 + 友好错误提示 |
| 前端请求失败 | 卡片显示"加载失败"，点击提示重试 |

---

## 11. 不在本次范围内

- 元数据（标题、日期、摘要、标签、作者）
- 搜索功能
- 分页
- 文章目录（TOC）
- 博客首页独立路由（非首页）
