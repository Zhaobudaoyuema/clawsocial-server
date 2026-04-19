import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import WorldView from '../views/WorldView.vue'
import ShareView from '../views/ShareView.vue'

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/',
      name: 'blog',
      component: HomeView,
    },
    {
      path: '/journal',
      redirect: { name: 'blog' },
    },
    {
      // 分层浏览 docs/home 子文件夹（先进文件夹再看到文章；path 对应 docs/home 下相对路径）
      path: '/journal/:pathMatch(.*)*',
      name: 'journal-browse',
      component: HomeView,
    },
    {
      path: '/home',
      name: 'home',
      component: () => import('../views/HomePage.vue'),
    },
    {
      path: '/world',
      name: 'world',
      component: WorldView,
    },
    {
      path: '/world/share/:shareToken',
      name: 'share',
      component: ShareView,
      props: true,
    },
    {
      path: '/blog/:slug+',
      name: 'blog-post',
      component: () => import('../views/BlogPostView.vue'),
    },
  ],
})

export default router
